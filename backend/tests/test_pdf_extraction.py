"""
tests/test_pdf_extraction.py

Covers task 8's "hand-built sample PDFs" requirement: builds small,
valid, single-page PDFs entirely in-code (no external PDF-authoring
library, no binary fixture files committed to the repo — just enough
raw PDF syntax to round-trip through pypdf) and runs them through the
same extract-then-detect pipeline /api/extract-pdf uses in main.py:
PdfReader -> extract_text() -> find_candidate_iscn_lines().

Deliberately does NOT go through FastAPI's TestClient/httpx — the rest
of this test suite is dependency-free by design (see the module
docstring in test_iscn_parser.py), and pypdf is a real application
dependency now (task 8), not a new test-only one. HTTP-layer wiring
(the actual route, multipart handling) is verified by hand in the
browser, matching how this repo has always treated the FastAPI layer.

Run directly with:
    python3 -m unittest tests.test_pdf_extraction -v
"""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pypdf import PdfReader  # noqa: E402
from iscn_parser import find_candidate_iscn_lines  # noqa: E402


def make_test_pdf(lines):
    """Builds a minimal, valid single-page PDF (one Helvetica text stream,
    one `lines` entry per line) using raw PDF syntax — no external
    PDF-writing library. Only meant to produce something pypdf can read
    back via extract_text(); not a general-purpose PDF writer."""
    def esc(s):
        return s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')

    content_lines = ["BT", "/F1 11 Tf", "72 750 Td", "13 TL"]
    for i, line in enumerate(lines):
        if i > 0:
            content_lines.append("T*")
        content_lines.append(f"({esc(line)}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_offset = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += (
        b"trailer\n" + f"<< /Size {n} /Root 1 0 R >>\n".encode("ascii") +
        b"startxref\n" + f"{xref_offset}\n".encode("ascii") + b"%%EOF"
    )
    return bytes(out)


def extract_and_detect(pdf_bytes):
    """Mirrors extract_pdf() in main.py exactly, minus the HTTP plumbing."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return find_candidate_iscn_lines(text), len(reader.pages)


class TestPdfExtractionPipeline(unittest.TestCase):
    def test_single_karyotype_report(self):
        pdf = make_test_pdf([
            "Patient: Jane Doe",
            "Specimen: Peripheral blood",
            "Karyotype:",
            "46,XY,t(9;22)(q34;q11.2)",
            "Interpretation: Consistent with CML.",
        ])
        candidates, pages = extract_and_detect(pdf)
        self.assertEqual(pages, 1)
        self.assertEqual(candidates, ["46,XY,t(9;22)(q34;q11.2)"])

    def test_two_karyotype_lines(self):
        pdf = make_test_pdf([
            "Specimen 1 (bone marrow): 46,XY",
            "Specimen 2 (peripheral blood): 47,XY,+21",
            "Both specimens from the same patient.",
        ])
        candidates, pages = extract_and_detect(pdf)
        self.assertEqual(pages, 1)
        self.assertEqual(candidates, ["46,XY", "47,XY,+21"])

    def test_no_karyotype_present(self):
        pdf = make_test_pdf([
            "Patient: John Smith",
            "This report contains only narrative text.",
            "No cytogenetic testing was performed.",
        ])
        candidates, pages = extract_and_detect(pdf)
        self.assertEqual(pages, 1)
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
