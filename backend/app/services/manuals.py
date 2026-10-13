"""Vehicle manual lookup (C08): Firestore vector search over manual_chunks with Gemini embeddings.
Manuals are global (the same for every garage); the lookup is audited in the asking garage's audit_log.
Lookup only, never diagnosis: the agent answers from the passages returned here or says it isn't in the manual."""

import json
import re
from functools import lru_cache
from pathlib import Path

from app import config, db, gemini
from app.services import core

CATALOG = Path(__file__).resolve().parent.parent.parent / "manuals" / "catalog.json"


@lru_cache(maxsize=1)
def known_models() -> list[str]:
    """Every model name the manuals use (catalog + procedure sheets), e.g. "Splendor Plus", "Activa 6G"."""
    names = set()
    data = json.loads(CATALOG.read_text()) if CATALOG.exists() else {}
    for key, meta in data.items():
        if not key.startswith("_"):
            names.update(meta.get("models", []))
    for sheet in (CATALOG.parent / "procedures").glob("*.md"):
        match = re.search(r"^models:\s*\[(.*)\]", sheet.read_text(), re.M)
        if match:
            names.update(m.strip().strip("'\"") for m in match.group(1).split(",") if m.strip())
    return sorted(names, key=len, reverse=True)  # longest first: "Splendor Plus" before "Splendor"


def _plain(name: str) -> str:
    name = name.lower().replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def normalise_model(vehicle: str) -> str:
    """Spoken or stored vehicle name -> the model name used in manual_chunks.models.
    "Splendor+" -> "Splendor Plus", "hero splendor plus" -> "Splendor Plus", "activa" -> "Activa"."""
    plain = _plain(vehicle or "")
    if not plain:
        return ""
    models = known_models()
    for model in models:  # exact
        if _plain(model) == plain:
            return model
    for model in models:  # the name inside a longer phrase ("Hero Splendor Plus 2021")
        if re.search(rf"\b{re.escape(_plain(model))}\b", plain):
            return model
    return vehicle.strip().title()


def search(question: str, vehicle: str, k: int | None = None) -> list[dict]:
    """The best passages for a question about one vehicle model, best first. Weak matches are dropped."""
    model = normalise_model(vehicle)
    if not model or not question.strip():
        return []
    vector = gemini.embed([question], "RETRIEVAL_QUERY")[0]
    query = (db.client().collection("manual_chunks")
             .where(filter=db.FieldFilter("models", "array_contains", model))
             .find_nearest("embedding", db.Vector(vector), limit=k or config.MANUAL_TOP_K,
                           distance_measure=db.DistanceMeasure.COSINE, distance_result_field="distance"))
    hits = []
    for snap in query.stream():
        d = snap.to_dict()
        score = round(1 - d["distance"], 3)
        if score >= config.MANUAL_MIN_SCORE:
            hits.append({"manual_id": d["manual_id"], "title": d["title"], "kind": d.get("kind", ""),
                         "page": d["page"], "section": d.get("section", ""), "text": d["text"], "score": score})
    return hits


def source_label(hit: dict) -> str:
    return f"{hit['title']} p.{hit['page']}" if hit.get("kind") != "procedure" else hit["title"]


def lookup(who: dict, garage_id: str, request_id: str, question: str, vehicle: str) -> dict:
    """search() for a staff member, recorded in the garage's activity feed
    ("Raju looked up: clutch free play (Splendor Plus owner's manual p.42)")."""
    model = normalise_model(vehicle)
    hits: list[dict] = []

    def work():
        hits[:] = search(question, model)
        return {"question": question, "vehicle": model, "found": bool(hits),
                "source": source_label(hits[0]) if hits else ""}, []

    summary = core.run(who, garage_id, request_id, "lookup_manual", work)
    if summary["found"] and not hits:  # a repeated request id returns the stored summary: search again (read-only)
        hits = search(question, model)
    return {"found": bool(hits), "vehicle": model, "sources": hits}
