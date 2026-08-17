import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_ocr_extraction import make_test_image_pdf
from pypdf import PdfReader
import pytesseract
import io

pdf_bytes = make_test_image_pdf([
    "Patient: Jane Doe",
    "Karyotype:",
    "46,XY,t(9;22)(q34;q11.2)",
    "Interpretation: Consistent with CML.",
])
page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]
img = list(page.images)[0].image
text = pytesseract.image_to_string(img)
print("=== TESSERACT VERSION ===")
print(pytesseract.get_tesseract_version())
print("=== RAW OCR TEXT (repr) ===")
print(repr(text))
