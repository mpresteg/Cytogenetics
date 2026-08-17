import io

import pytesseract
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from iscn_parser import parse_iscn, find_candidate_iscn_lines, SUPPORTED_EDITIONS, DEFAULT_EDITION

app = FastAPI(title="ISCN Validator & Interpreter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseRequest(BaseModel):
    iscn: str
    edition: str = DEFAULT_EDITION


@app.post("/api/parse")
def parse(req: ParseRequest):
    return parse_iscn(req.iscn, edition=req.edition)


# task 11: below this many non-whitespace characters, a page's embedded
# text layer is treated as effectively absent (scanned paper, not a real
# text layer) and routed through OCR instead. "Near-zero," not "exactly
# zero," since some scanned PDFs leak a stray character or two of
# metadata/whitespace into extract_text() without having a real layer.
MIN_TEXT_LAYER_CHARS = 10


def _extract_page_candidates(page):
    """Returns (candidates, source) for one PDF page. Prefers the
    embedded text layer (fast, exact); falls back to OCR — task 11 —
    only when that layer is effectively empty, i.e. this looks like a
    scanned image rather than a real text-layer PDF."""
    text = page.extract_text() or ""
    if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
        return find_candidate_iscn_lines(text), "text"

    ocr_parts = []
    for img in page.images:
        try:
            ocr_parts.append(pytesseract.image_to_string(img.image))
        except pytesseract.TesseractNotFoundError:
            raise HTTPException(
                status_code=500,
                detail=(
                    "This looks like a scanned PDF, which needs OCR — but the "
                    "Tesseract binary isn't installed on this server. See "
                    "README's \"Running it\" section (e.g. `brew install "
                    "tesseract` on macOS)."
                ),
            )
    return find_candidate_iscn_lines("\n".join(ocr_parts)), "ocr"


# task 8: PDF lab report upload. Extracts embedded text where a page has
# a real text layer; falls back to OCR (task 11) for pages that don't,
# e.g. scanned paper reports. Scans whatever text results for lines
# shaped like an ISCN karyotype string. Candidates are returned as-is —
# each tagged with where it came from — for the frontend to surface for
# review; never auto-parsed here, and OCR-sourced candidates need *more*
# scrutiny before parsing, not the same amount, given OCR's materially
# higher error rate on dense, punctuation-heavy ISCN strings.
@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file.")

    contents = await file.read()
    try:
        reader = PdfReader(io.BytesIO(contents))
    except PdfReadError as e:
        raise HTTPException(status_code=400, detail=f"Could not read this PDF: {e}")

    candidates = []
    for page in reader.pages:
        page_candidates, source = _extract_page_candidates(page)
        candidates.extend({"text": c, "source": source} for c in page_candidates)

    return {
        "filename": file.filename,
        "page_count": len(reader.pages),
        "candidates": candidates,
    }


@app.get("/api/editions")
def editions():
    return {"editions": SUPPORTED_EDITIONS, "default": DEFAULT_EDITION}


@app.get("/api/examples")
def examples():
    return {
        "karyotype": [
            "46,XY",
            "47,XY,+21",
            "46,XX,t(9;22)(q34;q11.2)",
            "46,XY,del(5)(q13q33)",
            "45,X,-Y[10]/46,XY[15]",
            "46,XX,der(14)t(14;18)(q32;q21)",
        ],
        "fish": [
            "nuc ish(D21S259x3)",
            "nuc ish(D13S319x1,LAMP1x2)",
            "ish t(9;22)(q34;q11.2)(ABL1+,BCR+)",
        ],
    }


# Serve the frontend last so /api routes above take priority.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
