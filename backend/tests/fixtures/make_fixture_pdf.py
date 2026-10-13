"""Writes manuals/zephyr-z100-owners-manual.pdf: a FICTIONAL owner's manual for tests (no real vehicle, all specs
made up). Run from backend/: python tests/fixtures/make_fixture_pdf.py. A tiny hand-written PDF, no libraries."""

from pathlib import Path

PAGES = [
    ["ZEPHYR Z100 OWNER'S MANUAL", "Fictional test manual. Every number here is made up.",
     "Demo Motors thanks you for choosing the Zephyr Z100."],
    ["BATTERY", "The Zephyr Z100 battery is a sealed 99 V 42 Ah test battery.",
     "Check the battery terminals for corrosion every month.",
     "SPARK PLUG", "Spark plug type ZX-TEST-1. The spark plug gap is 7.7 mm on this fictional model."],
    ["TYRE PRESSURE", "Front tyre pressure 123 psi. Rear tyre pressure 456 psi. Check when the tyres are cold.",
     "ENGINE OIL", "Engine oil grade ZZ-99 test oil. Engine oil quantity 9.9 litres at oil change."],
]


def pdf(pages: list[list[str]]) -> bytes:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        text = "BT /F1 11 Tf 14 TL 50 780 Td " + " ".join(
            "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines) + " ET"
        objects.append(f"<< /Length {len(text)} >>\nstream\n{text}\nendstream")
        content = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content} 0 R "
                       "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


if __name__ == "__main__":
    target = Path(__file__).parent / "manuals" / "zephyr-z100-owners-manual.pdf"
    target.write_bytes(pdf(PAGES))
    print(f"wrote {target}")
