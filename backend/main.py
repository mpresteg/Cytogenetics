import io

import pytesseract
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from iscn_parser import (
    parse_iscn,
    find_candidate_iscn_lines,
    find_lab_interpretation,
    SUPPORTED_EDITIONS,
    DEFAULT_EDITION,
)
from fhir_export import (
    build_mcode_export,
    extract_subject_candidates,
    normalize_date,
    FhirExportError,
)

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


# task 25, stage 1: export a parsed report as mCODE-shaped FHIR JSON —
# see fhir_export.py for the full rationale and what's verified vs. not.
# Re-parses `iscn` server-side rather than trusting a client-supplied
# parse result, for the same reason /api/parse itself is stateless: no
# server-side session to reference a prior parse by ID, and re-parsing
# is cheap and guarantees the export always reflects what this tool's
# own validation actually found for that exact string, not a stale or
# tampered copy of it.
class SubjectFields(BaseModel):
    patient_name: str = ""
    date_of_birth: str = ""
    specimen_id: str = ""
    collection_date: str = ""
    report_date: str = ""


class ExportFhirRequest(BaseModel):
    iscn: str
    edition: str = DEFAULT_EDITION
    subject: SubjectFields = SubjectFields()
    # Set only after the user has explicitly acknowledged that this tool
    # flagged one or more clones (errors, or an unrecognized token) and
    # chosen to export anyway — see build_mcode_export()'s pre-export QC
    # gate. Never set by default.
    override: bool = False


@app.post("/api/export-fhir")
def export_fhir(req: ExportFhirRequest):
    parsed = parse_iscn(req.iscn, edition=req.edition)
    try:
        return build_mcode_export(parsed, req.subject.model_dump(), override=req.override)
    except FhirExportError as e:
        raise HTTPException(status_code=422, detail=str(e))


# task 11: below this many non-whitespace characters, a page's embedded
# text layer is treated as effectively absent (scanned paper, not a real
# text layer) and routed through OCR instead. "Near-zero," not "exactly
# zero," since some scanned PDFs leak a stray character or two of
# metadata/whitespace into extract_text() without having a real layer.
MIN_TEXT_LAYER_CHARS = 10


def _extract_page_candidates(page):
    """Returns (candidates, source, raw_text) for one PDF page. Prefers
    the embedded text layer (fast, exact); falls back to OCR — task 11 —
    only when that layer is effectively empty, i.e. this looks like a
    scanned image rather than a real text-layer PDF. `raw_text` is
    whichever text was actually used (task 10 also scans the full
    document's raw text for a lab-reported interpretation section)."""
    text = page.extract_text() or ""
    if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
        return find_candidate_iscn_lines(text), "text", text

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
    ocr_text = "\n".join(ocr_parts)
    return find_candidate_iscn_lines(ocr_text), "ocr", ocr_text


# task 8: PDF lab report upload. Extracts embedded text where a page has
# a real text layer; falls back to OCR (task 11) for pages that don't,
# e.g. scanned paper reports. Scans whatever text results for lines
# shaped like an ISCN karyotype string. Candidates are returned as-is —
# each tagged with where it came from — for the frontend to surface for
# review; never auto-parsed here, and OCR-sourced candidates need *more*
# scrutiny before parsing, not the same amount, given OCR's materially
# higher error rate on dense, punctuation-heavy ISCN strings.
#
# task 10: also scans the full document (all pages' text concatenated,
# whichever source each page used) for a lab-reported interpretation
# section, so the frontend can show it alongside this tool's own
# case-level assessment — never auto-compared, just shown together.
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
    full_text_parts = []
    used_ocr = False
    for page in reader.pages:
        page_candidates, source, page_text = _extract_page_candidates(page)
        candidates.extend({"text": c, "source": source} for c in page_candidates)
        full_text_parts.append(page_text)
        if source == "ocr":
            used_ocr = True

    full_text = "\n".join(full_text_parts)
    lab_interpretation = find_lab_interpretation(full_text)

    # task 25: candidate subject/demographic fields (patient name, DOB,
    # specimen ID, collection/report date) for the FHIR export form —
    # same "surface for review, never auto-apply" discipline as the
    # karyotype candidates above. `_normalized` gives each date field's
    # best-effort ISO form too, purely to best-effort pre-fill the
    # frontend's <input type="date"> fields; the raw extracted text is
    # always included as well, in case normalization failed or looks
    # wrong, so nothing found in the PDF is silently dropped.
    subject_candidates = extract_subject_candidates(full_text)
    for date_field in ("date_of_birth", "collection_date", "report_date"):
        subject_candidates[f"{date_field}_normalized"] = normalize_date(subject_candidates[date_field])

    return {
        "filename": file.filename,
        "page_count": len(reader.pages),
        "candidates": candidates,
        "lab_interpretation": lab_interpretation,
        # Whether OCR was used anywhere in the document — only meaningful
        # (and only sent as true) when an interpretation was actually
        # found, so the frontend can add a "verify against original"
        # caveat to that text specifically, same discipline as OCR'd
        # candidates already get.
        "lab_interpretation_used_ocr": bool(lab_interpretation) and used_ocr,
        "subject_candidates": subject_candidates,
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
