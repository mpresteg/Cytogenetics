# ISCN Validator & Interpreter (prototype)

A small web app that parses ISCN karyotype and FISH nomenclature strings,
validates their structure, and produces a plain-English interpretation of
each abnormality.

**Stack:** Python (FastAPI) backend doing all the parsing, vanilla HTML/CSS/JS
frontend. No database, no build step, no frontend framework — deliberately
minimal so the parsing logic (the actual hard/valuable part of this problem)
is easy to read, test, and extend.

## Why this stack

- The core problem is *string parsing + domain rules*, not UI complexity — a
  templated regex/rule engine in plain Python is easier to get right and
  extend than trying to encode ISCN grammar in JS.
- FastAPI gives you a typed JSON API almost for free, plus auto-generated
  docs at `/docs` for exploring the parser without touching the UI.
- Keeping the frontend framework-free means the whole thing runs with one
  `pip install` and no `npm`/build tooling — useful for a prototype you'll
  want to hand to a colleague or run on a lab machine quickly.

## Project layout

```
Cytogenetics/
  .github/workflows/
    tests.yml            CI: runs the backend test suite on every push/PR
  TASKS.md                Backlog of self-contained tasks (see "Working on this repo")
  backend/
    main.py                FastAPI app: /api/parse, /api/extract-pdf, /api/editions,
                            /api/examples, serves the frontend
    iscn_parser.py          All parsing/validation/interpretation logic (no framework deps)
    requirements.txt
    static/
      index.html
      style.css
      app.js
    tests/
      test_iscn_parser.py
      test_pdf_extraction.py
      test_ocr_extraction.py
```

## Visual design

The interface uses a clinical-slide palette (cool white, ink text, one
disciplined cobalt accent) rather than a generic dark theme or cream/serif
template. The recurring motif — a striped bar echoing a G-banded chromosome
ideogram — appears in the header and the small logo mark; category badges
(structural / numerical / FISH / unrecognized) get a small color-coded dot
and left edge instead, loosely referencing real staining/microscopy
conventions without overstating precision.

Headings and data use IBM Plex Mono, body text uses IBM Plex Sans, both
loaded from Google Fonts. If the browser has no internet access, the page
falls back to the system sans/monospace fonts automatically — layout and
color are unaffected either way.

## Running it

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**OCR support (scanned PDF reports) needs one extra, non-pip step:** the
Tesseract OCR binary, installed at the OS level, not via `pip`:

```bash
brew install tesseract          # macOS
apt-get install tesseract-ocr   # Debian/Ubuntu
```

Everything else works fine without it — this is only needed for uploading
*scanned* (image-only) PDF reports; text-layer PDFs, typed/pasted strings,
and `.txt` upload are unaffected. Without Tesseract installed, uploading a
scanned PDF returns a clear error telling you what's missing, rather than
crashing.

Then open **http://127.0.0.1:8000** in a browser. Try the example dropdown,
or paste a string like:

```
46,XX,t(9;22)(q34;q11.2)
47,XY,+21[20]/46,XY[5]
nuc ish(D13S319x1,LAMP1x2)
ish t(9;22)(q34;q11.2)(ABL1+,BCR+)
```

The textarea also accepts multiple strings at once, one per line (paste the
block above as-is) — each line is parsed and rendered independently, labeled
"Input N of M". See **Batch mode** below for how that's wired up.

The interactive API docs (for testing the parser directly, or wiring up a
different frontend later) are at **http://127.0.0.1:8000/docs**.

## A note on testing

`iscn_parser.py`'s logic is covered by the automated suite described below
(103 tests, run on every push/PR by CI). Beyond that, every feature in this
tool has also been verified live — the actual FastAPI server launched, the
actual UI driven in a browser, against both synthetic fixtures and real
(de-identified) lab report PDFs — not just unit-tested in isolation. If
something doesn't wire up when you run it locally, the `/docs` page is the
fastest way to check the raw JSON shape `/api/parse` and `/api/extract-pdf`
actually return, versus what `app.js` expects.

## What this prototype covers

**Karyotype tokens:**
- Numerical: `+21`, `-Y`, `+mar`
- Structural: `t()`, `del()`, `dup()`, `inv()`, `i()`, `r()`, `add()`, `ins()`,
  `mar`, `dmin`, `hsr()`
- `der()` — both forms:
  - Single-chromosome `der(14)t(14;18)(q32;q21)`: the content after `der(N)`
    is decomposed by re-running it through the same single-event rules used
    for standalone tokens (so `t()`, `del()`, `dup()`, `inv()`, `ins()`,
    `add()` embedded inside a `der()` are fully broken into chromosomes/bands,
    not just captured as raw text). Anything inside that still isn't
    recognized is reported as unparsed leftover text, never silently dropped.
  - Whole-arm / Robertsonian-style `der(13;14)(q10;q10)`: parsed into its two
    chromosomes and breakpoints; if both chromosomes are acrocentric
    (13/14/15/21/22) with centromeric (`q10`) breakpoints, the tool notes that
    current guidance generally prefers explicit `rob()` notation for the same
    event.
- `rob(13;14)(q10;q10)` — explicit Robertsonian translocation notation,
  parsed directly; warns if used on non-acrocentric chromosomes.
- Mosaicism: multiple clones separated by `/`, with `[N]` cell counts
- A soft consistency check between the stated modal number and the net
  effect of numerical (`+`/`-`) abnormalities listed
- **Band plausibility (approximate):** two-band structural events (`del`,
  `dup`, `inv`, `add`) are checked against a reference table of approximate
  terminal band numbers covering all 24 chromosomes, and against ISCN's
  proximal-then-distal breakpoint ordering convention. Both checks only
  ever produce a *warning*, never a hard error. 12 of the 24 entries are
  sourced (NCBI GRCh38 ideogram data via Wikipedia's per-chromosome
  cytogenetic band tables, cited in a code comment); the original 12 remain
  unsourced and flagged as such — see `iscn_parser.py`
  (`APPROX_TERMINAL_BANDS`).

**FISH:**
- `nuc ish(...)` and `ish(...)` (standalone or attached to a karyotype
  rearrangement like `ish t(9;22)(...)(ABL1+,BCR+)`), including their own
  trailing `[N]` cell count (interphase nuclei scored) — e.g.
  `nuc ish(D21S259x3)[200]`.
- **Combined karyotype + FISH clone**, ISCN's `<karyotype>[N].nuc ish
  ...[M]` form — a period joining a karyotype clone to a FISH result for
  the *same* cell population (as opposed to `/` for a genuinely different
  clone), e.g. `46,XY[20].nuc ish 1p32(CDKN2Cx2),13q34(LAMP1x2)[200]`.
  Parsed by splitting at the period (`COMBINED_KARYOTYPE_FISH_RE` in
  `iscn_parser.py` — safe against colliding with a band sub-decimal like
  `13q14.3`, since that's always followed by more digits, never the word
  "ish") and merging the two halves into one clone: the karyotype's own
  `cell_count` plus a separate `fish_cell_count` for the FISH clause's
  count, and findings from both concatenated.
- Probe results: presence/absence (`ABL1+`, `BCR-`), copy number (`D21S259x3`),
  fusion (`ABL1 con BCR`)
- **Reference notes:** a small, non-exhaustive lookup table (`PROBE_KNOWLEDGE`,
  `FUSION_KNOWLEDGE` in `iscn_parser.py`) attaches a short clinical-context
  note to well-known probes/fusions (e.g. BCR-ABL1 → CML/ALL, IGH-BCL2 →
  follicular lymphoma). Every such note is explicitly labeled "reference
  note, not diagnostic" in the output — this is a starting scaffold, not a
  validated knowledge base.
- **Band-locus prefix:** in a multi-probe list written as
  `locus(PROBE),locus(PROBE),...` (e.g. `1p32(CDKN2Cx2),13q34(LAMP1x2)`,
  a common way labs report a multi-locus interphase FISH panel), the
  leading band-locus text is captured against its own probe — surfaced in
  that probe's `interpretation` ("Probe CDKN2C (locus 1p32): ...") and in
  a `bands` field on its `Finding`, the same field structural findings
  use for breakpoint bands. A locus shared by more than one probe inside
  the same parens (`1p32(CDKN2Cx2,OTHERx1)`) applies to both.

**ISCN edition awareness (scaffold):** the API and UI accept an `edition`
parameter (2016 / 2020 / 2024, default 2024). This does **not** fully model
edition-by-edition grammar differences yet — that requires a domain expert
working from the actual ISCN volumes for each edition. What's implemented is
the plumbing plus one illustrative example (`der()` vs `rob()` for
Robertsonian translocations) to show where a real edition-difference table
would plug in. See `EDITION_NOTES` in `iscn_parser.py`.

**Batch mode:** the textarea accepts multiple ISCN strings, one per line.
This is a **client-side loop over the existing single-string `/api/parse`
endpoint** (`parseOne()`/`runParse()` in `app.js`), not a new batch endpoint
— `main.py` and `iscn_parser.py` are untouched. Each line is fired as its
own request (`Promise.all`), and each result renders as its own existing
clone-card block, labeled "Input N of M" when there's more than one line.
Reasoning: every line is already fully independent (its own errors,
warnings, mosaic state), so there's no shared parsing state a batch endpoint
would actually save; looping client-side keeps `iscn_parser.py`'s contract
at "one ISCN string in, one result out," which is easier to reason about and
test than adding a second, list-shaped API contract to maintain.

Before splitting on `\n`, `runParse()` first runs `foldLineWrappedEntries()`
to fold back together a *single* ISCN string that's been copy-pasted from
a source that word-wrapped it across several physical lines (a PDF
viewer, a Word doc, some EMR "copy" buttons) — a structural signal, not a
content guess: a line can't legally have ended where it did if it has an
unclosed `(`, a trailing list comma, or ends in "ish," so genuinely
separate batch entries are never at risk of a false merge, only ever a
line that looks structurally incomplete on its own. A blank line always
breaks folding, since a user's own paste can have intentional blank-line
separators; capped so a genuine unclosed-paren typo can't silently
swallow every following entry. Some wraps (landing right where a paren
pair happens to already be balanced) are structurally indistinguishable
from an intentional new entry and are deliberately left unfixed rather
than guessed at.

An "Upload .txt file…" button next to the textarea reads a local
plain-text file client-side via `FileReader` (one ISCN string per line —
same shape the textarea expects) and drops its contents into the
textarea — no upload to the backend, nothing persisted. Does **not**
auto-run parse: that content hasn't been seen *inside this tool* yet,
same as a PDF upload, so it gets the same explicit-Parse-click treatment
as paste and PDF upload, rather than the example dropdown's "selecting
it is the action" treatment. CSV/XLSX and other formats needing
column-mapping are out of scope; see task 7 in `TASKS.md`.

**PDF lab report upload:** an "Upload PDF report…" button sends the file
to a new `POST /api/extract-pdf` endpoint — this one **can't** be
client-side the way `.txt` upload is, since PDF/OCR extraction needs
Python libraries (`pypdf`, chosen for having zero transitive dependencies
of its own, in keeping with this project's minimal-dependency stance;
`python-multipart` is also required, since FastAPI's file-upload support
depends on it). For each page, the endpoint (`_extract_page_candidates()`
in `main.py`) prefers the embedded text layer; if that's near-empty
(under `MIN_TEXT_LAYER_CHARS` — this looks like a scanned image, not a
real text-layer PDF), it falls back to **OCR**: extracting the page's
embedded image via `pypdf`'s `page.images` and running it through a local
Tesseract install via `pytesseract`. Tesseract is a real OS-level binary,
not `pip`-installable — see "Running it" above for the install step; a
scanned PDF uploaded without Tesseract installed returns a clear error
rather than a crash. Whatever text results (from either path) is scanned
with `find_candidate_iscn_lines()` for substrings shaped like a karyotype
string (a modal number immediately followed by a sex-chromosome
constitution, e.g. `46,XY,` — tolerant of a stray space after the comma,
since real Tesseract output routinely inserts one even where a
text-layer PDF never would).

Candidates are loaded into the batch textarea for review — **unlike**
the `.txt` upload flow, this does **not** auto-run parse, since text
pulled from a real-world PDF layout (doubly so for OCR) is a guess, not a
trusted input. The textarea itself always holds the plain, unmodified
extracted text — exactly what a user would type or paste themselves —
never decorated with markers of our own. OCR-sourced candidates need
*more* scrutiny before parsing, not the same amount, given OCR's
materially higher error rate on dense, punctuation-heavy ISCN strings;
that caution is surfaced in a separate panel below the upload status
(listing each OCR-derived line, with a "verify against the original"
note), not by mutating what's in the textarea. A report with zero
candidates says so plainly rather than leaving a blank textarea that
reads as "nothing to report." Extracting anything beyond the karyotype
string itself (patient name, specimen ID, etc.) is out of scope, as is
"correcting" likely OCR misreads against ISCN grammar — a misread
character surfaces through the existing error/warning UI as-is, never
silently patched.

`find_candidate_iscn_lines()` also handles a real-world wrinkle: some
report-generation software hard-wraps a long ISCN string across several
physical lines *within the PDF's own text layer* (nothing to do with
OCR — this happens even on a page with a full, real text layer). Rather
than grabbing only the first fragment, it recognizes when a candidate
can't have legally ended where a physical line did (an unclosed `(`, a
trailing `,`, or ending in the word `ish`, which ISCN grammar always
follows with more content) and folds subsequent lines in — joined with
no separator by default (most wraps land mid-token) except right after
`ish`, which grammar guarantees a following space — capped
(`MAX_CANDIDATE_CONTINUATION_LINES`) so it can never run away across an
entire document. A second, independent stop condition
(`_looks_like_section_boundary()`) halts folding before a standalone
all-uppercase, digit-free line (a real report-section header, e.g.
"CULTURES") regardless of what the paren-balance signal says — real
ISCN content always mixes in numbers, so this is specific enough to
never collide with it, and guards against a single OCR-garbled
character permanently corrupting the paren-balance check and folding
the candidate all the way to the line cap through unrelated report
sections.

The reverse problem also happens: some report-generation software
emits a section's own label glued directly onto the *end* of the
candidate on the same physical line, no separator (e.g. a karyotype
string immediately followed by `ABNORMAL RESULTS:`, confirmed against
a real report whose whole text layer consistently puts value before
label with no space). `_trim_trailing_garbage()` truncates a candidate
right after the first `[N]` cell count whose following content isn't a
legal continuation (`/` for another clone, `.` for a combined FISH
clause, or end of string) — a structural signal from ISCN grammar
itself, not a guess about what looks like prose, and it never alters a
single character of the actual candidate, only narrows where it ends.

**Case-level clinical assessment:** every parse also returns a top-level
`assessment` (`assess_case()` in `iscn_parser.py`) that rolls the case's
findings up into one plain-English summary, plus an explicit flag when a
finding matches `MALIGNANCY_KNOWLEDGE` — a small, sourced reference table
of cytogenetic abnormalities named as recurrent in the WHO Classification
of Haematolymphoid Tumours (5th ed., 2022) — or when a clone has 3+
unrelated abnormalities (the common "complex karyotype" convention).
Rendered as its own visually distinct panel in the UI (`renderAssessment()`
in `app.js`), amber-highlighted only when something matched. Same
discipline as the FISH `PROBE_KNOWLEDGE`/`FUSION_KNOWLEDGE` notes: every
match's note is explicitly prefixed "Reference note (not diagnostic)" —
this names a recurrently-associated pattern, never a diagnosis, stage, or
prognosis, and it cannot distinguish a constitutional finding (e.g. +21)
from an acquired one, since that needs clinical context (specimen type,
patient history) this tool doesn't have.

**Comparing against the lab's own interpretation:** when a PDF upload
has a section introduced by "Interpretation," "Overall Interpretation,"
"Clinical Interpretation," or "Clinical Correlation" — either as its own
header line, or inline with the text on the same line ("Interpretation:
Normal karyotype...", a convention some labs use — an explicit colon is
required for the inline form, so ordinary prose starting with
"Interpretation" doesn't false-trigger) (`find_lab_interpretation()` in
`iscn_parser.py`) — that text is extracted and shown at the top of the
results, labeled "Lab-reported interpretation," **immediately once the
PDF is read**, not gated behind clicking Parse. It comes straight from
the PDF's own text, independent of which candidate lines get parsed or
whether the user parses at all. Parse re-renders the same panel
afterward alongside this tool's own case-level assessment, which always
carries an explicit "This tool's interpretation" label, so the two
voices are never conflated. Neither is auto-compared or scored; a human
reads both.

"Comment" is **not** a trigger header (starting the section), but *is*
included as regular content once an interpretation section has started.
Different labs use "Comment" differently — sometimes generic FDA/CLIA
disclaimer boilerplate, sometimes a genuine case-specific caveat sitting
right next to a named reviewer — and guessing which convention a given
PDF follows isn't reliable. Dropping real content is worse than
occasionally showing boilerplate a human can plainly see and ignore, so
extraction is deliberately inclusive here, stopping only at a handful of
other real section names ("Signature," "Results," "Cultures,"
"Karyotypes," "FISH Images," "CPT Codes") that mark a genuine structural
boundary. If no interpretation section is found, that's stated plainly
rather than a blank space that reads as "nothing to report."

Anything outside all of the above grammar is returned as
`category: "unrecognized"` with an explicit warning — it's never silently
mis-parsed or dropped. This matters a lot for a clinical-adjacent tool: false
confidence is worse than an honest "I don't understand this token."

## Testing

A GitHub Actions workflow (`.github/workflows/tests.yml`) runs the full
suite below — including the OCR tests, via `apt-get install tesseract-
ocr fonts-dejavu-core` steps — on every push to `main` and every pull
request. The font install matters, not just Tesseract itself: real
Tesseract can misread digits rendered in PIL's own bundled default font
(a "4" read as "A," confirmed across Tesseract builds) —
`test_ocr_extraction.py` renders its fixture text with a real system
font when one's available (DejaVu on Linux, Arial on macOS), falling
back to PIL's default only if neither is installed.

Three modules under `backend/tests/`, all stdlib `unittest`, all
pytest-discoverable if that's your preferred runner:

- `test_iscn_parser.py` — 97 tests, zero dependencies beyond the stdlib,
  so it's runnable without `pip install` anything. Covers: normal
  karyotypes, numerical abnormalities and the modal-number consistency
  check, every structural token type, `der()` decomposition (both forms)
  and its `rob()` suggestion, mosaicism with cell counts, FISH probe
  parsing (copy number / presence-absence / fusion), FISH cell counts,
  the combined karyotype+FISH clone form, and the knowledge-base notes,
  unrecognized-token handling, the edition parameter, the case-level
  clinical assessment (each malignancy-associated pattern, the
  complex-karyotype threshold, mosaic clone attribution, and the no-flag
  paths), terminal-band plausibility for every chromosome in
  `APPROX_TERMINAL_BANDS`, the PDF/OCR candidate-line detection heuristic
  (`find_candidate_iscn_lines()`, including its tolerance for a stray
  space after the comma and its multi-line continuation logic), and the
  lab-reported-interpretation extraction heuristic
  (`find_lab_interpretation()`).
- `test_pdf_extraction.py` — 3 tests, depends on `pypdf` (a real
  application dependency, not a test-only addition). Builds small PDFs
  entirely in-code (raw PDF syntax, no external PDF-authoring library or
  binary fixture files) and runs them through the same extract-then-detect
  pipeline `/api/extract-pdf` uses: one clean single-karyotype report, one
  with two karyotype lines, one with none.
- `test_ocr_extraction.py` — 3 tests, depends on `pytesseract`/`Pillow`
  *and* a real local Tesseract install — there's no mocked fallback for
  "Tesseract isn't installed" here, since without it there's nothing to
  test. Builds a small image-only PDF (a PIL-rendered bitmap
  embedded as a JPEG XObject, no text operators at all) and confirms the
  OCR path recovers the karyotype string from it, a scanned report with
  no karyotype content returns no candidates, and — the routing decision
  itself — a normal text-layer PDF takes the text path, not OCR, even
  though both code paths exist side by side.

Both PDF-related modules deliberately skip FastAPI's `TestClient` (which
needs `httpx`, not otherwise a dependency here) — the actual HTTP route
is verified by hand in the browser instead, consistent with how this repo
has always treated the FastAPI layer (see "A note on testing" above).

```bash
cd backend
python3 -m unittest discover -s tests -v
# or, if you have pytest installed:
pytest tests/ -v
```

103 tests total, all passing — verified locally and independently by CI
on every push, not just claimed to pass.

## Working on this repo

Ongoing work is tracked in `TASKS.md` — a backlog of self-contained tasks,
each with the context to start from, an acceptance check, and an explicit
out-of-scope list. Pick a task, follow the "How to pick up a task" steps at
the top of that file (write tests first, run the suite, update this README
if scope changed), and move it to `## Done` when it's finished.

## What I'd extend next

See `TASKS.md` for the actively-tracked backlog (this used to be a plain
list here, but that duplicated `TASKS.md` and the two would drift out of
sync — `TASKS.md` is now the source of truth).
