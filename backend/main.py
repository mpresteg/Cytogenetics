import io

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


# task 8: PDF lab report upload. Extracts embedded text (not OCR — see
# task 11 in TASKS.md for scanned-image PDFs) and scans it for lines
# shaped like an ISCN karyotype string. Candidates are returned as-is for
# the frontend to surface for review, never auto-parsed here.
@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file.")

    contents = await file.read()
    try:
        reader = PdfReader(io.BytesIO(contents))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as e:
        raise HTTPException(status_code=400, detail=f"Could not read this PDF: {e}")

    candidates = find_candidate_iscn_lines(text)
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
