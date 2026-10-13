"""Import vehicle manuals into Firestore for manual lookup (C08).

    python -m app.manuals_ingest [<folder or gs://bucket/prefix/>] [--force]

Reads the owner's manuals (PDF, each page transcribed by Gemini) from the source (default MANUALS_SOURCE: gs://<GCS_BUCKET>/manuals/ in
production, backend/manuals/pdf/ in development) plus the team's procedure sheets (manuals/procedures/*.md,
shipped in the image). Each file becomes manuals/{manual_id} and its text chunks manual_chunks/{manual_id}-NNNN
with a Gemini embedding. Safe to re-run: a manual's chunks are replaced, and an unchanged file is skipped.
In production this runs as the Cloud Run Job "manuals-ingest" (same image, see cloudbuild.yaml).

PDFs are mapped to models by manuals/catalog.json (exact file name); a PDF not in the catalog is skipped.
The manufacturer PDFs are never committed; only extracted text goes into Firestore.
"""

import hashlib
import io
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import config, db, gemini, storage
from app.services import core

log = logging.getLogger("manuals_ingest")

MANUALS_DIR = Path(__file__).resolve().parent.parent / "manuals"
CHUNK_WORDS = 450  # a long passage is split into chunks of about this size (300-600 words)
OVERLAP_WORDS = 40  # ...with this many words repeated at the start of the next chunk
MIN_SECTION_WORDS = 40  # a heading starts a new chunk once the current one has this much text


# ---------------------------------------------------------------- reading files


def manual_id(name: str) -> str:
    """Stable id from a file name: "Hero-Splendour-Plus-owner's-manual.pdf" -> "hero-splendour-plus-owners-manual"."""
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-")


TRANSCRIBE_PROMPT = ("Transcribe this owner's-manual page as plain text. Keep headings. Write every table row as "
                     "'label: value unit' lines, keeping each value next to its own label. Copy numbers and units "
                     "exactly. Don't add, explain or guess anything. If the page has no text, reply EMPTY.")
RETRY_WAIT_SECONDS = 2  # before the one retry of a page


def split_pdf(data: bytes) -> list[tuple[bytes, str]]:
    """[(the page as a one-page PDF, the page's own PDF text)] for every page."""
    from pypdf import PdfReader, PdfWriter

    pages = []
    for page in PdfReader(io.BytesIO(data)).pages:
        writer, buf = PdfWriter(), io.BytesIO()
        writer.add_page(page)
        writer.write(buf)
        pages.append((buf.getvalue(), page.extract_text() or ""))
    return pages


def transcribe(page_pdf: bytes) -> str:
    """One page read by Gemini: works for scanned pages and keeps spec-table values next to their labels
    (the PDF's own text often lists all labels, then all values)."""
    text = gemini.generate(config.TRANSCRIBE_MODEL, TRANSCRIBE_PROMPT, page_pdf, "application/pdf").strip()
    return "" if text.upper() == "EMPTY" else text


def read_page(name: str, page_no: int, page_pdf: bytes, pdf_text: str) -> tuple[str, bool]:
    """(text, fell_back): Gemini's transcription, tried twice; then the PDF's own text so one bad page
    never stops the manual."""
    for attempt in (1, 2):
        try:
            return transcribe(page_pdf), False
        except Exception as e:
            if attempt == 1:
                time.sleep(RETRY_WAIT_SECONDS)
            else:
                log.warning("%s page %d: transcription failed (%s); using the PDF text", name, page_no, e)
    return pdf_text, True


def pdf_pages(data: bytes, name: str = "") -> tuple[list[str], int]:
    """Text per page (TRANSCRIBE_WORKERS pages at a time, in page order) and how many pages fell back."""
    pages = split_pdf(data)
    with ThreadPoolExecutor(max_workers=max(1, config.TRANSCRIBE_WORKERS)) as pool:
        results = list(pool.map(lambda n: read_page(name, n + 1, *pages[n]), range(len(pages))))
    return [text for text, _ in results], sum(fell_back for _, fell_back in results)


def front_matter(text: str) -> tuple[dict, str]:
    """`---` key: value lines `---`, then the body. Values in [a, b] become lists."""
    if not text.startswith("---"):
        return {}, text
    head, _, body = text[3:].partition("\n---")
    meta = {}
    for line in head.strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
        meta[key.strip()] = value
    return meta, body.lstrip("\n")


# ---------------------------------------------------------------- chunking


def _is_heading(line: str, markdown: bool) -> str:
    """The heading text if the line is one, else ''."""
    line = line.strip()
    if markdown:
        return line.lstrip("#").strip() if line.startswith("#") else ""
    words = line.split()
    if not 1 <= len(words) <= 8 or ":" in line or line[-1] in ".,;" or not line[0].isalpha():
        return ""
    return line if line.isupper() or all(w[0].isupper() for w in words if w[0].isalpha()) else ""


def chunk(pages: list[str], markdown: bool = False, first_section: str = "") -> list[dict]:
    """Split page texts into chunks with the page (1-based) and the nearest heading above (`section`).
    A chunk never spans a page break, so its page number is exact. Within a page a heading starts a new chunk
    once the current one has MIN_SECTION_WORDS, and a long passage is split every CHUNK_WORDS words with an
    OVERLAP_WORDS overlap."""
    out = []
    section = first_section
    for page_no, text in enumerate(pages, start=1):
        words, start_section = [], section

        def close(keep_overlap=False):
            nonlocal words, start_section
            if words:  # line breaks are kept: a table row "label: value unit" stays one line
                out.append({"page": page_no, "section": start_section,
                            "text": " ".join(words).replace("\n ", "\n").strip()})
            words = words[-OVERLAP_WORDS:] if keep_overlap else []
            start_section = section

        for line in text.splitlines():
            heading = _is_heading(line, markdown)
            if heading:
                if len(words) >= MIN_SECTION_WORDS:
                    close()
                section = heading
                if not words:
                    start_section = section
                words += heading.split()  # keep the heading words searchable
            else:
                for word in line.split():
                    words.append(word)
                    if len(words) >= CHUNK_WORDS:
                        close(keep_overlap=True)
            if words and not words[-1].endswith("\n"):
                words[-1] += "\n"
        if len(words) > (OVERLAP_WORDS if out and out[-1]["page"] == page_no else 0):
            close()
    return out


# ---------------------------------------------------------------- sources


def load_catalog(path: Path | None = None) -> dict:
    data = json.loads((path or MANUALS_DIR / "catalog.json").read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def list_source(source: str) -> list[dict]:
    """[{name, fingerprint, read}] for every file in a local folder or under a gs://bucket/prefix/."""
    if source.startswith("gs://"):
        bucket, _, prefix = source[5:].partition("/")
        return [{"name": f["path"][len(prefix):].lstrip("/"), "fingerprint": f"md5:{f['md5']}",
                 "read": (lambda p=f["path"]: storage.read(p, bucket))}
                for f in storage.list_files(prefix, bucket) if "/" not in f["path"][len(prefix):].lstrip("/")]
    folder = Path(source)
    if not folder.is_dir():
        log.warning("manuals folder %s not found", folder)
        return []
    return [{"name": p.name, "fingerprint": f"{p.stat().st_size}-{int(p.stat().st_mtime)}", "read": p.read_bytes}
            for p in sorted(folder.iterdir()) if p.is_file()]


# ---------------------------------------------------------------- import


def store(mid: str, meta: dict, source: str, fingerprint: str, pages: list[str], markdown: bool) -> int:
    chunks = chunk(pages, markdown, first_section=meta["title"] if markdown else "")
    vectors = gemini.embed([f"{meta['title']}\n{c['section']}\n{c['text']}" for c in chunks], "RETRIEVAL_DOCUMENT")
    client = db.client()
    old = client.collection("manual_chunks").where(filter=db.FieldFilter("manual_id", "==", mid))
    for snap in old.stream():
        snap.reference.delete()
    for n, (c, vector) in enumerate(zip(chunks, vectors)):
        client.collection("manual_chunks").document(f"{mid}-{n:04d}").set({
            "manual_id": mid, "title": meta["title"], "models": meta["models"], "kind": meta["kind"],
            "page": c["page"], "section": c["section"], "text": c["text"], "embedding": db.Vector(vector)})
    client.collection("manuals").document(mid).set({
        "title": meta["title"], "make": meta.get("make", ""), "models": meta["models"], "kind": meta["kind"],
        "source": source, "pages": len(pages), "chunks": len(chunks), "fingerprint": fingerprint,
        "ingested_at": core.now()})
    return len(chunks)


def ingest(source: str | None = None, procedures: str | Path | None = None, catalog: Path | None = None,
           force: bool = False) -> list[str]:
    """Import every manual; returns one report line per file."""
    source = source or config.MANUALS_SOURCE
    if not source.startswith("gs://") and not Path(source).is_absolute():
        source = str(Path(__file__).resolve().parent.parent / source)
    known = load_catalog(catalog)
    client = db.client()
    files = [(f, "pdf") for f in list_source(source)]
    files += [(f, "md") for f in list_source(str(procedures or MANUALS_DIR / "procedures"))]
    report = []
    for f, origin in files:
        name, mid = f["name"], manual_id(f["name"])
        is_pdf, is_md = name.lower().endswith(".pdf"), name.lower().endswith(".md")
        if not (is_pdf and origin == "pdf") and not (is_md and origin == "md"):
            report.append(f"skipped {name}: not a PDF (manuals) or Markdown (procedures) file")
            continue
        if is_pdf and name not in known:
            report.append(f"skipped {name}: not in manuals/catalog.json (add title, make, models, kind)")
            continue
        data = None if is_pdf else f["read"]()  # Markdown is small: fingerprint by content
        fingerprint = f["fingerprint"] if is_pdf else "sha:" + hashlib.sha256(data).hexdigest()[:16]
        saved = client.collection("manuals").document(mid).get().to_dict() or {}
        if not force and saved.get("fingerprint") == fingerprint:
            report.append(f"unchanged {name}")
            continue
        fell_back = 0
        if is_pdf:
            try:
                meta, (pages, fell_back) = known[name], pdf_pages(f["read"](), name)
            except Exception as e:
                report.append(f"failed {name}: could not read the PDF ({e})")
                continue
        else:
            meta, body = front_matter(data.decode("utf-8"))
            if not meta.get("title") or not meta.get("models"):
                report.append(f"skipped {name}: front matter needs title and models")
                continue
            meta.setdefault("kind", "procedure")
            pages = [body]
        try:
            n = store(mid, meta, name, fingerprint, pages, markdown=is_md)
        except Exception as e:  # one bad file (or an embedding error) must not stop the others
            log.exception("failed on %s", name)
            report.append(f"failed {name}: {e}")
            continue
        note = f" ({fell_back} page(s) from the PDF text: transcription failed)" if fell_back else ""
        report.append(f"ingested {name}: {len(pages)} page(s), {n} chunk(s) for {', '.join(meta['models'])}{note}")
    return report


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = [a for a in argv if not a.startswith("--")]
    report = ingest(args[0] if args else None, force="--force" in argv)
    for line in report:
        log.info(line)
    failed = [line for line in report if line.startswith("failed")]
    log.info("done: %d file(s) looked at, %d failed", len(report), len(failed))
    return 1 if failed else 0  # a failed Cloud Run Job execution shows up in the console and is retried once


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
