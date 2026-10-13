"""Firestore client, plus a small in-memory fake with the same calls.

Only the service layer imports this module. The fake supports exactly what the service
layer uses: document get/set/update/create/delete, collection stream, where(filter=FieldFilter),
order_by and limit, the Increment / ArrayUnion transforms, and find_nearest (cosine) for manual lookup.
"""

import copy
import math

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud.firestore import ArrayUnion, Increment
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app import config

__all__ = ["client", "use_fake", "FakeClient", "FieldFilter", "Increment", "ArrayUnion", "AlreadyExists",
           "Vector", "DistanceMeasure"]

_client = None


def client():
    """Return the process-wide Firestore client (real or fake, per DB_BACKEND)."""
    global _client
    if _client is None:
        if config.DB_BACKEND == "memory":
            _client = FakeClient()
        else:
            from google.cloud import firestore

            _client = firestore.Client(project=config.GCP_PROJECT or None)
    return _client


def use_fake():
    """Swap in a fresh in-memory fake (tests call this)."""
    global _client
    _client = FakeClient()
    return _client


# ---------------------------------------------------------------- in-memory fake


class FakeSnapshot:
    def __init__(self, ref, data):
        self.reference = ref
        self.id = ref.id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None

    def get(self, field):
        return (self._data or {}).get(field)


def _apply(old, new, dotted=False):
    out = copy.deepcopy(old)
    for key, value in new.items():
        if dotted and "." in key:  # update() treats "a.b" as a nested field path
            head, rest = key.split(".", 1)
            out[head] = _apply(out.get(head) or {}, {rest: value}, dotted=True)
        elif isinstance(value, Increment):
            out[key] = out.get(key, 0) + value.value
        elif isinstance(value, ArrayUnion):
            out[key] = list(out.get(key, [])) + [v for v in value.values if v not in out.get(key, [])]
        else:
            out[key] = copy.deepcopy(value)
    return out


class FakeDocument:
    def __init__(self, store, path):
        self._store = store
        self.path = path
        self.id = path.rsplit("/", 1)[-1]

    def collection(self, name):
        return FakeCollection(self._store, f"{self.path}/{name}")

    def get(self):
        return FakeSnapshot(self, self._store.get(self.path))

    def set(self, data, merge=False):
        old = self._store.get(self.path, {}) if merge else {}
        self._store[self.path] = _apply(old, data)

    def create(self, data):
        if self.path in self._store:
            raise AlreadyExists(f"{self.path} already exists")
        self._store[self.path] = _apply({}, data)

    def update(self, data):
        if self.path not in self._store:
            raise NotFound(f"{self.path} not found")
        self._store[self.path] = _apply(self._store[self.path], data, dotted=True)

    def delete(self):
        self._store.pop(self.path, None)


class FakeQuery:
    def __init__(self, store, path, filters=(), order=None, limit_n=None):
        self._store = store
        self.path = path
        self._filters = list(filters)
        self._order = order
        self._limit = limit_n

    def where(self, filter):
        return FakeQuery(self._store, self.path, self._filters + [filter], self._order, self._limit)

    def order_by(self, field, direction="ASCENDING"):
        return FakeQuery(self._store, self.path, self._filters, (field, direction), self._limit)

    def limit(self, n):
        return FakeQuery(self._store, self.path, self._filters, self._order, n)

    def stream(self):
        prefix = self.path + "/"
        docs = [
            FakeSnapshot(FakeDocument(self._store, p), copy.deepcopy(d))
            for p, d in sorted(self._store.items())
            if p.startswith(prefix) and "/" not in p[len(prefix):]
        ]
        for f in self._filters:
            docs = [d for d in docs if _match(d.to_dict().get(f.field_path), f.op_string, f.value)]
        if self._order:
            field, direction = self._order
            docs.sort(key=lambda d: d.to_dict().get(field) or 0, reverse=direction == "DESCENDING")
        return iter(docs[: self._limit] if self._limit else docs)

    def find_nearest(self, vector_field, query_vector, limit, distance_measure, *, distance_result_field=None,
                     distance_threshold=None):
        if distance_measure != DistanceMeasure.COSINE:
            raise NotImplementedError("the fake only does COSINE")
        return FakeVectorQuery(self, vector_field, list(query_vector), limit, distance_result_field)


class FakeVectorQuery:
    """Cosine distance (1 - similarity) over the base query's documents, nearest first."""

    def __init__(self, base, field, vector, limit, result_field):
        self._base, self._field, self._vector, self._limit, self._result_field = base, field, vector, limit, result_field

    def stream(self):
        scored = []
        for snap in self._base.stream():
            stored = snap.get(self._field)
            if stored is None:
                continue
            distance = 1 - _cosine(self._vector, list(stored))
            data = snap.to_dict()
            if self._result_field:
                data[self._result_field] = distance
            scored.append((distance, FakeSnapshot(snap.reference, data)))
        scored.sort(key=lambda pair: pair[0])
        return iter([snap for _, snap in scored[: self._limit]])


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _match(actual, op, value):
    if op == "==":
        return actual == value
    if op == "!=":
        return actual != value
    if op == "in":
        return actual in value
    if op == "array_contains":
        return value in (actual or [])
    if actual is None:
        return False
    return {"<": actual < value, "<=": actual <= value, ">": actual > value, ">=": actual >= value}[op]


class FakeCollection(FakeQuery):
    def __init__(self, store, path):
        super().__init__(store, path)
        self.id = path.rsplit("/", 1)[-1]

    def document(self, doc_id):
        return FakeDocument(self._store, f"{self.path}/{doc_id}")


class FakeClient:
    def __init__(self):
        self.store = {}  # full document path -> dict

    def collection(self, path):
        return FakeCollection(self.store, path)

    def document(self, path):
        return FakeDocument(self.store, path)
