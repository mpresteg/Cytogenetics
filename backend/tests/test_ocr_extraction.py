"""
tests/test_ocr_extraction.py

Covers task 11's OCR-fallback requirement: builds a small, valid,
image-only PDF entirely in-code (a PIL-rendered bitmap of report text,
embedded as a JPEG XObject — no text operators at all, so pypdf's
extract_text() correctly comes back empty) and runs it through the same
per-page routing logic /api/extract-pdf uses in main.py: if a page's text
layer is near-empty, extract its embedded image(s) and OCR them instead
of giving up.

This is the real Tesseract binary running via pytesseract — not mocked —
so these tests need Tesseract installed locally (see README/requirements
.txt) the same way the app itself does; there's no fallback path in the
tests for "Tesseract isn't installed" the way there is in the endpoint,
since without it there's nothing to test.

Doesn't literally re-render task 8's existing text-layer PDF fixture
pixel-by-pixel (that would need a real PDF rendering engine, its own can
of worms) — instead builds a fresh bitmap with equivalent content via
PIL, which exercises the same "this is a scanned image, OCR it" path a
literally-scanned version of that report would.

Run directly with:
    python3 -m unittest tests.test_ocr_extraction -v
"""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))  # so `import test_pdf_extraction` works
# regardless of whether this module was loaded as "test_ocr_extraction" (discover
# mode, tests/ added as a root) or "tests.test_ocr_extraction" (named directly).

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from pypdf import PdfReader  # noqa: E402
import pytesseract  # noqa: E402

from iscn_parser import find_candidate_iscn_lines  # noqa: E402
from test_pdf_extraction import make_test_pdf  # noqa: E402 — reuse task 8's text-layer PDF builder

MIN_TEXT_LAYER_CHARS = 10  # mirrors main.py's threshold


def make_test_image_pdf(lines, size=(900, 300)):
    """Builds a minimal, valid, single-page, IMAGE-ONLY PDF: renders
    `lines` onto a bitmap with PIL, embeds it as a JPEG XObject, and
    writes a page whose content stream just draws that image — no text
    operators anywhere, so pypdf's extract_text() correctly returns
    nothing and the OCR fallback path is what has to recover the text."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=24)
    y = 10
    for line in lines:
        draw.text((20, y), line, fill="black", font=font)
        y += 35

    jpeg_buf = io.BytesIO()
    img.save(jpeg_buf, format="JPEG", quality=90)
    jpeg_bytes = jpeg_buf.getvalue()
    w, h = img.size

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im1 4 0 R >> >> "
         f"/MediaBox [0 0 {w} {h}] /Contents 5 0 R >>").encode("ascii"),
        (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
         f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
         f"/Length {len(jpeg_bytes)} >>\nstream\n").encode("ascii") + jpeg_bytes + b"\nendstream",
    ]
    content = f"q {w} 0 0 {h} 0 0 cm /Im1 Do Q".encode("ascii")
    objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")

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


def extract_page_candidates(page):
    """Mirrors _extract_page_candidates() in main.py exactly, minus the
    HTTPException/FastAPI plumbing."""
    text = page.extract_text() or ""
    if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
        return find_candidate_iscn_lines(text), "text"
    ocr_parts = [pytesseract.image_to_string(img.image) for img in page.images]
    return find_candidate_iscn_lines("\n".join(ocr_parts)), "ocr"


def normalize(s):
    """Strips all whitespace, since real Tesseract output introduces
    spacing artifacts (e.g. "46, XY," instead of "46,XY,") that vary by
    font/rendering but don't change the actual characters recognized."""
    return "".join(s.split())


class TestOcrFallback(unittest.TestCase):
    def test_scanned_single_karyotype_report(self):
        pdf_bytes = make_test_image_pdf([
            "Patient: Jane Doe",
            "Karyotype:",
            "46,XY,t(9;22)(q34;q11.2)",
            "Interpretation: Consistent with CML.",
        ])
        page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]

        # Confirm this fixture actually has no text layer — otherwise this
        # test would pass for the wrong reason (never exercising OCR).
        self.assertEqual((page.extract_text() or "").strip(), "")

        candidates, source = extract_page_candidates(page)
        self.assertEqual(source, "ocr")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(normalize(candidates[0]), "46,XY,t(9;22)(q34;q11.2)")

    def test_scanned_report_with_no_karyotype(self):
        pdf_bytes = make_test_image_pdf([
            "Patient: John Smith",
            "This report contains only narrative text.",
            "No cytogenetic testing was performed.",
        ])
        page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]
        candidates, source = extract_page_candidates(page)
        self.assertEqual(source, "ocr")
        self.assertEqual(candidates, [])

    def test_text_layer_page_does_not_use_ocr(self):
        # A normal (task 8-style) text-layer PDF should take the "text"
        # path, not fall through to OCR, even though both paths exist.
        pdf_bytes = make_test_pdf(["Karyotype:", "46,XY,t(9;22)(q34;q11.2)"])
        page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]
        candidates, source = extract_page_candidates(page)
        self.assertEqual(source, "text")
        self.assertEqual(candidates, ["46,XY,t(9;22)(q34;q11.2)"])


if __name__ == "__main__":
    unittest.main()
