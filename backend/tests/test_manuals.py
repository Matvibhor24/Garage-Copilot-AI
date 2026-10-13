"""C08 manual lookup: chunking, ingestion (local folder and gs://), vector search, the tool and the agent.
Uses the FICTIONAL Zephyr Z100 manual in tests/fixtures/manuals and bag-of-words fake embeddings (conftest)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import agent, config, db, gemini, manuals_ingest, seed, storage, tools
from app.services import core, jobs, manuals

FIXTURES = Path(__file__).parent / "fixtures" / "manuals"
PDF = "zephyr-z100-owners-manual.pdf"
G = "shree-auto"


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setattr(config, "MANUAL_MIN_SCORE", 0.2)  # bag-of-words scores are lower than real embeddings
    monkeypatch.setattr(config, "MANUAL_TOP_K", 3)


def ingest(source=str(FIXTURES), **kw):
    return manuals_ingest.ingest(source, procedures=FIXTURES / "procedures", catalog=FIXTURES / "catalog.json", **kw)


# ---------------------------------------------------------------- reading and chunking


def test_chunks_keep_page_and_section_with_overlap():
    pages = ["INTRO\nHello there.", "BATTERY\nBattery text here.\nSPARK PLUG\n" + " ".join(f"w{i}" for i in range(1000))]
    out = manuals_ingest.chunk(pages)
    assert out[0] == {"page": 1, "section": "INTRO", "text": "INTRO\nHello there."}
    assert {c["page"] for c in out[1:]} == {2}  # a chunk never spans a page break
    assert out[1]["section"] == "BATTERY"  # short sections stay together under the first heading
    long = [c["text"].split() for c in out[1:]]
    assert all(len(words) <= manuals_ingest.CHUNK_WORDS for words in long)
    assert long[0][-manuals_ingest.OVERLAP_WORDS:] == long[1][:manuals_ingest.OVERLAP_WORDS]  # overlap


def test_markdown_front_matter_and_headings():
    meta, body = manuals_ingest.front_matter((FIXTURES / "procedures" / "zephyr-chain-check.md").read_text())
    assert meta == {"title": "Chain check (Zephyr Z100)", "make": "Demo Motors", "models": ["Zephyr Z100"],
                    "kind": "procedure"}
    [only] = manuals_ingest.chunk([body], markdown=True, first_section=meta["title"])
    assert only["section"] == "Chain check (Zephyr Z100)" and "Check the chain" in only["text"]
    assert "# " not in only["text"]


def test_manual_ids_and_model_names():
    assert manuals_ingest.manual_id("Hero-Splendour-Plus-owner's-manual.pdf") == "hero-splendour-plus-owners-manual"
    assert manuals_ingest.manual_id("Honda-activa-6g-owner's manual.pdf") == "honda-activa-6g-owners-manual"
    assert manuals.normalise_model("Splendor+") == "Splendor Plus"
    assert manuals.normalise_model("hero splendor plus 2021") == "Splendor Plus"
    assert manuals.normalise_model("splendor") == "Splendor"
    assert manuals.normalise_model("Activa 6G") == "Activa 6G"
    assert manuals.normalise_model("pulsar150") == "Pulsar150"  # unknown spelling: kept, finds nothing
    assert manuals.normalise_model("zephyr z100") == "Zephyr Z100"
    assert manuals.normalise_model("") == ""


def test_real_catalog_covers_the_four_manuals():
    catalog = manuals_ingest.load_catalog()
    assert set(catalog) == {"Hero-Splendour-Plus-owner's-manual.pdf", "Honda-activa-6g-owner's manual.pdf",
                            "Bajaj-pulsar-owner's-manul.pdf", "maruti-swift-owner's-manual.pdf"}
    assert all(set(m) == {"title", "make", "models", "kind"} and m["kind"] == "owner" for m in catalog.values())


def test_drafted_procedure_sheets_follow_the_rules():
    for sheet in (manuals_ingest.MANUALS_DIR / "procedures").glob("*.md"):
        meta, body = manuals_ingest.front_matter(sheet.read_text())
        assert meta["kind"] == "procedure" and meta["models"] and meta["title"], sheet.name
        assert body.startswith("Team-written general steps, check against the workshop manual."), sheet.name


# ---------------------------------------------------------------- ingestion


def test_ingest_from_a_local_folder_is_safe_to_rerun(fake_db, settings, tmp_path):
    (tmp_path / PDF).write_bytes((FIXTURES / PDF).read_bytes())
    (tmp_path / "unknown-manual.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.txt").write_text("hi")
    report = ingest(str(tmp_path))
    assert f"ingested {PDF}: 3 page(s), 3 chunk(s) for Zephyr Z100" in report
    assert "skipped unknown-manual.pdf: not in manuals/catalog.json (add title, make, models, kind)" in report
    assert any(r.startswith("ingested zephyr-chain-check.md") for r in report)
    manual = fake_db.collection("manuals").document("zephyr-z100-owners-manual").get().to_dict()
    assert manual["title"] == "Zephyr Z100 owner's manual" and manual["pages"] == 3 and manual["kind"] == "owner"
    chunks = [d.to_dict() for d in fake_db.collection("manual_chunks").stream()]
    assert {c["page"] for c in chunks if c["manual_id"] == "zephyr-z100-owners-manual"} == {1, 2, 3}
    assert all(isinstance(c["embedding"], db.Vector) and c["models"] == ["Zephyr Z100"] for c in chunks)

    again = ingest(str(tmp_path))
    assert f"unchanged {PDF}" in again and "unchanged zephyr-chain-check.md" in again
    forced = ingest(str(tmp_path), force=True)
    assert f"ingested {PDF}: 3 page(s), 3 chunk(s) for Zephyr Z100" in forced
    assert len(list(fake_db.collection("manual_chunks").stream())) == len(chunks)  # replaced, not duplicated


def test_ingest_from_cloud_storage(fake_db, settings):
    storage.upload(f"manuals/{PDF}", (FIXTURES / PDF).read_bytes(), "application/pdf")
    storage.upload("photos/shree-auto/J-1/a.jpg", b"jpeg", "image/jpeg")  # other prefixes are ignored
    report = ingest("gs://test-bucket/manuals/")
    assert f"ingested {PDF}: 3 page(s), 3 chunk(s) for Zephyr Z100" in report
    assert not any("a.jpg" in r for r in report)
    assert f"unchanged {PDF}" in ingest("gs://test-bucket/manuals/")  # same md5: skipped
    storage.upload(f"manuals/{PDF}", (FIXTURES / PDF).read_bytes() + b"\n", "application/pdf")
    assert f"ingested {PDF}: 3 page(s), 3 chunk(s) for Zephyr Z100" in ingest("gs://test-bucket/manuals/")


def test_pages_are_transcribed_with_gemini_and_fall_back_to_the_pdf_text(fake_db, settings, monkeypatch):
    """C08b: page 1 is EMPTY (a blank scan), page 2 is a spec table, page 3 fails twice and uses the PDF text."""
    import io

    from pypdf import PdfReader

    calls = []

    def transcriber(model, prompt, image=None, mime_type=""):
        page = PdfReader(io.BytesIO(image)).pages[0].extract_text()  # which fixture page this is
        calls.append((model, mime_type, page.split("\n")[0]))
        assert "'label: value unit'" in prompt and "reply EMPTY" in prompt
        if page.startswith("ZEPHYR"):
            return "EMPTY"
        if page.startswith("BATTERY"):
            return "SPECIFICATIONS\nSpark plug gap: 7.7 mm\nBattery: 99 V 42 Ah\nSpark plug type: ZX-TEST-1"
        raise RuntimeError("quota")

    monkeypatch.setattr(gemini, "generate", transcriber)
    monkeypatch.setattr(config, "TRANSCRIBE_MODEL", "test-transcriber")
    monkeypatch.setattr(config, "TRANSCRIBE_WORKERS", 3)
    monkeypatch.setattr(manuals_ingest, "RETRY_WAIT_SECONDS", 0)
    report = ingest()
    assert (f"ingested {PDF}: 3 page(s), 2 chunk(s) for Zephyr Z100 (1 page(s) from the PDF text: "
            "transcription failed)") in report
    assert sorted(c[2] for c in calls) == ["BATTERY", "TYRE PRESSURE", "TYRE PRESSURE", "ZEPHYR Z100 OWNER’S MANUAL"]
    assert {c[:2] for c in calls} == {("test-transcriber", "application/pdf")}

    chunks = {c["page"]: c for c in (d.to_dict() for d in fake_db.collection("manual_chunks").stream())
              if c["manual_id"] == "zephyr-z100-owners-manual"}
    assert set(chunks) == {2, 3}  # the EMPTY page has no chunk, page numbers stay exact
    assert "Spark plug gap: 7.7 mm\n" in chunks[2]["text"]  # the value stays on its label's line
    assert chunks[2]["section"] == "SPECIFICATIONS"
    assert "Front tyre pressure 123 psi" in chunks[3]["text"]  # pypdf text for the failed page
    hit = manuals.search("spark plug gap", "Zephyr Z100")[0]
    assert hit["page"] == 2 and "Spark plug gap: 7.7 mm" in hit["text"]


def test_headings_and_rows_in_a_transcribed_page():
    page = "ELECTRICAL\nBattery: 99 V 42 Ah\nHeadlamp: 99 W\nTYRES\nFront: 123 psi"
    [only] = manuals_ingest.chunk([page])
    assert only["text"] == "ELECTRICAL\nBattery: 99 V 42 Ah\nHeadlamp: 99 W\nTYRES\nFront: 123 psi"
    assert only["section"] == "ELECTRICAL"  # "Battery: 99 V 42 Ah" is a row, not a heading


# ---------------------------------------------------------------- search and the tool


@pytest.fixture
def library(fake_db, settings):
    seed.seed(fake_db)
    ingest()
    return fake_db


def test_search_finds_the_right_page_and_filters_by_model(library):
    hits = manuals.search("spark plug gap", "Zephyr Z100")
    assert hits[0]["page"] == 2 and "7.7 mm" in hits[0]["text"] and hits[0]["title"] == "Zephyr Z100 owner's manual"
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    assert manuals.search("front tyre pressure", "zephyr z100")[0]["page"] == 3
    assert manuals.search("spark plug gap", "Splendor Plus") == []  # other model: nothing
    assert manuals.search("chain adjuster bolts", "Zephyr Z100")[0]["title"] == "Chain check (Zephyr Z100)"


def test_weak_matches_are_not_found(library, monkeypatch):
    assert manuals.search("windscreen wiper blade replacement", "Zephyr Z100") == []
    monkeypatch.setattr(config, "MANUAL_MIN_SCORE", 0.99)
    assert manuals.search("spark plug gap", "Zephyr Z100") == []


def ctx(call_id, state):
    return SimpleNamespace(state=state, function_call_id=call_id)


def test_lookup_tool_uses_the_jobs_vehicle_and_is_audited(library):
    raju = {"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"}
    tools.create_job("MH12 ZZ 0001", "Zephyr Z100", "Test Owner", "", "test", ctx("c1", raju))
    out = tools.lookup_manual("battery voltage", "", ctx("c2", raju))
    assert out["found"] and out["vehicle"] == "Zephyr Z100" and out["source"] == "Zephyr Z100 owner's manual p.2"
    assert out["answer_sources"][0]["page"] == 2 and "99 V 42 Ah" in out["answer_sources"][0]["text"]
    assert set(out["answer_sources"][0]) == {"title", "page", "section", "text"}

    missing = tools.lookup_manual("windscreen wiper blade", "", ctx("c3", raju))
    assert missing == {"found": False, "vehicle": "Zephyr Z100", "source": "", "answer_sources": []}

    audit = {a["request_id"]: a for a in (d.to_dict() for d in core.garage(G).collection("audit_log").stream())}
    assert audit["c2"]["action"] == "lookup_manual"
    assert audit["c2"]["details"] == {"question": "battery voltage", "vehicle": "Zephyr Z100", "found": True,
                                      "source": "Zephyr Z100 owner's manual p.2"}
    assert audit["c3"]["details"]["found"] is False
    assert tools.lookup_manual("battery voltage", "", ctx("c2", raju))["answer_sources"]  # repeated call id
    stock = {d.id: d.to_dict()["qty"] for d in core.garage(G).collection("inventory").stream()}
    assert jobs.list_jobs(core.actor(G, "m-raju", "mechanic"), G)[-1]["stage"] == "intake"  # a lookup changes nothing
    assert stock == {d.id: d.to_dict()["qty"] for d in core.garage(G).collection("inventory").stream()}


def test_lookup_tool_needs_a_vehicle(library):
    raju = {"garage_id": G, "uid": "m-raju", "name": "Raju", "role": "mechanic"}
    assert "error" in tools.lookup_manual("battery voltage", "", ctx("c1", raju))
    owner = {"garage_id": G, "uid": "o-asha", "name": "Asha", "role": "owner"}
    assert tools.lookup_manual("spark plug gap", "Zephyr Z100", ctx("o1", owner))["found"]  # read-only for owners too


def test_agents_have_the_tool_and_the_never_guess_rule():
    live = agent.build_live_agent()
    assert "lookup_manual" in {getattr(t, "__name__", "") for t in live.tools}
    assert "lookup_manual" in {t.__name__ for t in agent.build_owner_agent().tools}
    text = agent.instruction(SimpleNamespace(state={}))
    assert "Answer only from the passages it returns" in text and "Never guess a spec" in text
    assert "isn't in" in text and "the manual" in text


def test_command_line_reports_and_fails_on_errors(fake_db, settings, tmp_path, monkeypatch):
    (tmp_path / PDF).write_bytes((FIXTURES / PDF).read_bytes())
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    monkeypatch.setattr(manuals_ingest, "MANUALS_DIR", FIXTURES)  # fixture catalog + procedures
    assert manuals_ingest.main([str(tmp_path)]) == 0  # broken.pdf is not in the catalog: skipped, not failed
    catalog = tmp_path / "catalog.json"
    catalog.write_text('{"broken.pdf": {"title": "Broken", "make": "X", "models": ["X"], "kind": "owner"}}')
    report = manuals_ingest.ingest(str(tmp_path), procedures=FIXTURES / "procedures", catalog=catalog)
    assert any(r.startswith("failed broken.pdf: could not read the PDF") for r in report)
    monkeypatch.setattr(manuals_ingest, "load_catalog", lambda path=None: {"broken.pdf": {}})
    assert manuals_ingest.main([str(tmp_path)]) == 1
