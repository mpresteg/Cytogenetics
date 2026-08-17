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
iscn-tool/
  backend/
    main.py            FastAPI app: /api/parse, /api/examples, serves the frontend
    iscn_parser.py      All parsing/validation/interpretation logic (no framework deps)
    requirements.txt
    static/
      index.html
      style.css
      app.js
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

I unit-tested `iscn_parser.py` directly (pure Python, no dependencies) against
~15 real ISCN strings covering numerical, structural, mosaic, and FISH cases,
and fixed one regex bug that surfaced (isochromosome band parsing). I was
**not able to actually launch the FastAPI server** in the sandbox this was
built in (no network access to install FastAPI/uvicorn), so the HTTP layer —
`main.py` and the frontend's `fetch()` calls — is unverified end-to-end,
though it follows a very standard, low-risk pattern. When you run it locally,
if anything doesn't wire up, the most likely culprits are the JSON shape
returned by `/api/parse` vs. what `app.js` expects — check the `/docs` page
first to see the raw response shape.

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
  count, and findings from both concatenated. Before this, the whole
  string went through the plain karyotype parser, which has no notion of
  a trailing FISH clause — everything from `nuc ish` onward silently
  corrupted `sex_chromosomes` and every individual probe came back
  "unrecognized."
- Probe results: presence/absence (`ABL1+`, `BCR-`), copy number (`D21S259x3`),
  fusion (`ABL1 con BCR`)
- **Reference notes:** a small, non-exhaustive lookup table (`PROBE_KNOWLEDGE`,
  `FUSION_KNOWLEDGE` in `iscn_parser.py`) attaches a short clinical-context
  note to well-known probes/fusions (e.g. BCR-ABL1 → CML/ALL, IGH-BCL2 →
  follicular lymphoma). Every such note is explicitly labeled "reference
  note, not diagnostic" in the output — this is a starting scaffold, not a
  validated knowledge base.
- **Known gap:** in a multi-probe list written as `locus(PROBE),locus(PROBE),...`
  (e.g. `1p32(CDKN2Cx2),13q34(LAMP1x2)`), the leading band-locus text
  (`1p32`, `13q34`) isn't captured anywhere in the output — only what's
  inside each probe's own parens. Pre-existing, not introduced by the
  combined-clone work above; flagged, not yet fixed.

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

An "Upload .txt file…" button next to the textarea reads a local
plain-text file client-side via `FileReader` (one ISCN string per line —
same shape the textarea expects), drops its contents into the textarea,
and runs it through the same batch-parse path — no upload to the backend,
nothing persisted. CSV/XLSX and other formats needing column-mapping are
out of scope; see task 7 in `TASKS.md`.

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
note), not by mutating what's in the textarea. An earlier version
prefixed OCR-sourced lines with `# OCR — verify against original:`
directly in the textarea so an unedited line would fail to parse — but
that meant the caution couldn't be separated from the content itself: a
user who'd already reviewed and confirmed a line was correct still had
to manually strip the prefix before it would parse at all. A report with
zero candidates says so plainly rather than leaving a blank textarea
that reads as "nothing to report." Extracting anything beyond the
karyotype string itself (patient name, specimen ID, etc.) is out of
scope, as is "correcting" likely OCR misreads against ISCN grammar — a
misread character surfaces through the existing error/warning UI as-is,
never silently patched; see tasks 8 and 11 in `TASKS.md`.

`find_candidate_iscn_lines()` also handles a real-world wrinkle,
confirmed against an actual lab report PDF: some report-generation
software hard-wraps a long ISCN string across several physical lines
*within the PDF's own text layer* (nothing to do with OCR — this happens
even when the page has a full, real text layer). Rather than grabbing
only the first fragment, it recognizes when a candidate can't have
legally ended where a physical line did (an unclosed `(`, a trailing
`,`, or ending in the word `ish`, which ISCN grammar always follows with
more content) and folds subsequent lines in — joined with no separator
by default (most wraps land mid-token) except right after `ish`, which
grammar guarantees a following space — capped
(`MAX_CANDIDATE_CONTINUATION_LINES`) so it can never run away across an
entire document. See task 16 in `TASKS.md`.

That cap alone wasn't enough for OCR-sourced text (task 11): confirmed
against real OCR output from an actual scanned report, a single misread
character (Tesseract dropping one closing `)`) can leave the
unbalanced-parens signal permanently true, so folding never resolves on
its own and runs all the way to the line cap — pulling unrelated report
sections (e.g. a "CULTURES" header and a disclaimer footer) into one
long garbled candidate. `_looks_like_section_boundary()` is a second,
independent stop condition: a standalone all-uppercase, digit-free line
is specific enough to never collide with real ISCN content (which always
mixes in numbers), so folding stops cleanly before a section header no
matter what the paren-balance signal says. See task 17 in `TASKS.md`.

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
(task 8) has a section introduced by "Interpretation," "Overall
Interpretation," "Clinical Interpretation," or "Clinical Correlation" —
either as its own header line, or inline with the text on the same line
("Interpretation: Normal karyotype...", a real second report's
convention — an explicit colon is required for the inline form, so
ordinary prose starting with "Interpretation" doesn't false-trigger)
(`find_lab_interpretation()` in `iscn_parser.py`) — that text is
extracted and shown once, at the top of the results, labeled
"Lab-reported interpretation" — and every case-level assessment panel
below it now carries an explicit "This tool's interpretation" label,
always, so the two voices are never conflated. Neither is auto-compared
or scored; a human reads both.

"Comment" is **not** a trigger header (starting the section), but *is*
now included as regular content once an interpretation section has
started — it stopped extraction early in an earlier version, on the
reasoning that one real report's "Comment" section was generic FDA/CLIA
disclaimer boilerplate. That didn't generalize: a second real report's
"Comment" turned out to be a genuine, case-specific caveat sitting right
next to a named reviewer. Guessing which convention a given PDF follows
isn't reliable, and dropping real content is worse than occasionally
showing boilerplate a human can plainly see and ignore — so extraction
is deliberately inclusive here, stopping only at a handful of other real
section names ("Signature," "Results," "Cultures," "Karyotypes," "FISH
Images," "CPT Codes") that mark a genuine structural boundary. If no
interpretation section is found, that's stated plainly rather than a
blank space that reads as "nothing to report."

Anything outside all of the above grammar is returned as
`category: "unrecognized"` with an explicit warning — it's never silently
mis-parsed or dropped. This matters a lot for a clinical-adjacent tool: false
confidence is worse than an honest "I don't understand this token."

## Testing

Three modules under `backend/tests/`, all stdlib `unittest`, all
pytest-discoverable if that's your preferred runner:

- `test_iscn_parser.py` — 88 tests, zero dependencies beyond the stdlib,
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
  application dependency as of task 8, not a test-only addition).
  Builds small PDFs entirely in-code (raw PDF syntax, no external
  PDF-authoring library or binary fixture files) and runs them through
  the same extract-then-detect pipeline `/api/extract-pdf` uses: one
  clean single-karyotype report, one with two karyotype lines, one with
  none.
- `test_ocr_extraction.py` — 3 tests, depends on `pytesseract`/`Pillow`
  *and* a real local Tesseract install (task 11) — there's no mocked
  fallback for "Tesseract isn't installed" here, since without it there's
  nothing to test. Builds a small image-only PDF (a PIL-rendered bitmap
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

90 tests total, all passing as of this build — I ran them in the sandbox
this was built in, they're not just claimed to pass.

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
