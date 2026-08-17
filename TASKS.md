# TASKS

A backlog of self-contained tasks for this repo. Each one is written so it
can be handed off and worked independently: **Context** says where to look,
**Done when** is the acceptance check (usually: tests pass, plus a manual
spot-check), and **Out of scope** exists so a task doesn't quietly grow into
three tasks.

Convention: when a task is picked up, move it under `## In progress`, and
when it's done, move it under `## Done` with the commit hash. Add new tasks
at the bottom of `## Backlog` following the same three-field format.

## How to pick up a task

1. Read the task's **Context** and open those files first.
2. Write/extend tests under `backend/tests/` that encode **Done when**
   *before* changing `iscn_parser.py` — the existing 31 tests are the
   regression net; new behavior should get the same treatment.
3. Run `python3 -m unittest tests.test_iscn_parser -v` from `backend/`
   until everything passes.
4. Update `README.md`'s "What this prototype covers" section if the task
   changed what the parser understands — that section is the source of
   truth for scope, and it drifting from reality is worse than a missing
   feature.
5. Commit with a message that names the task.

---

## Backlog

### 1. Multi-step der() chains

**Context**: `_decompose_der_body()` and `interpret_derivative_single()` in
`backend/iscn_parser.py`. Currently decomposes a *single* embedded
rearrangement inside `der()`, e.g. `der(9)t(9;22)(q34;q11.2)`. Real reports
sometimes chain two, e.g. `der(9)t(9;22)(q34;q11.2)t(9;11)(p13;q14)` — a
chromosome 9 derivative shaped by two separate translocation events.
`SUB_EVENT_RE` already finds all embedded events via `finditer`, so the
sub-finding *list* should already come back with two entries — the gap is
likely in how the interpretation text and leftover-detection handle three+
consumed spans, and this needs a test to confirm either way.

**Done when**: `der(9)t(9;22)(q34;q11.2)t(9;11)(p13;q14)` parses to a single
`Finding` with `category: "structural"`, two sub-events reflected in the
interpretation text (in order), and no spurious "not decomposed" warning.
At least 2 new test cases in `TestDerivativeDecomposition`.

**Out of scope**: der() chains mixing more than two event types, or der()
built from three-or-more source chromosomes — flag those as a follow-up
task rather than solving them here.

---

### 2. Expand APPROX_TERMINAL_BANDS coverage

**Context**: `APPROX_TERMINAL_BANDS` in `backend/iscn_parser.py` currently
covers 12 chromosomes (1, 5, 7, 9, 11, 13, 14, 16, 17, 21, 22, X). The
remaining autosomes (2, 3, 4, 6, 8, 10, 12, 15, 18, 19, 20) and Y aren't
checked at all, so bands on those chromosomes get no plausibility warning
regardless of how implausible.

**Done when**: table covers all 24 chromosomes with sourced terminal-band
values (cite the source — an ISCN idiogram reference or cytogenetics atlas
— in a code comment, since the existing entries are explicitly flagged as
approximate and unsourced). One test per newly-added chromosome confirming
both a plausible and an implausible band.

**Out of scope**: sub-band-level validation (i.e. confirming q13.3 exists
vs just q13) — that needs a much larger data table and should be its own
task if pursued.

---

### 3. Grow PROBE_KNOWLEDGE / FUSION_KNOWLEDGE

**Context**: `PROBE_KNOWLEDGE` and `FUSION_KNOWLEDGE` dicts in
`backend/iscn_parser.py`, currently ~11 and 4 entries respectively. Good
candidates to add: TP53 (17p13.1), EGFR (7p11.2), PTEN (10q23), RB1
(13q14.2), N-MYC/MYCN (2p24), ALK (2p23), PML-RARA fusion (t(15;17), APL),
ETV6-RUNX1 fusion (t(12;21), pediatric ALL).

**Done when**: each new entry follows the existing format (locus + one-line
clinical association, no dosing/staging/prognostic claims), and
`test_unknown_probe_no_note_no_crash`-style coverage confirms each new
probe surfaces its note. Update the README's probe-table description if
the count changes meaningfully.

**Out of scope**: turning this into a queryable/searchable reference (e.g.
an API endpoint to browse the table) — that's a feature, this task is just
data entry against the existing shape.

---

### 4. Real ISCN edition differences

**Context**: `EDITION_NOTES`, `SUPPORTED_EDITIONS`, `_edition_notes_for()`
in `backend/iscn_parser.py`. Currently one illustrative entry (der() vs
rob() for Robertsonian translocations). This is the task most likely to
need primary-source research rather than just coding — it needs someone
working from the actual ISCN 2016/2020/2024 text to identify real notation
changes between editions (candidates to verify: marker chromosome /
supernumerary marker chromosome (sSMC) terminology, complex rearrangement
`cx` notation, uncertainty marker conventions).

**Done when**: at least 2 more sourced, dated edition differences are in
`EDITION_NOTES`, each with a code comment citing where the difference comes
from. A test per new entry, following the pattern of
`test_rob_edition_note_present`.

**Out of scope**: don't guess at plausible-sounding differences without a
source — an unsourced "note" here is worse than no note, since it reads as
authoritative. If a difference can't be confirmed, leave it out and say so
in the PR/commit description instead of including it anyway.

---

### 5. Export interpretation as text

**Context**: `backend/static/app.js` (`render()` function) and
`backend/main.py`. No export functionality exists yet — findings are only
ever rendered live in the DOM.

**Done when**: a "Copy interpretation" button in the results area copies a
plain-text rendering of the current parse result to the clipboard (modal
number, sex chromosomes, each finding's interpretation, warnings) —
client-side only, no new backend endpoint needed. Formatting should be
readable as plain text (e.g. in an email), not just a JSON dump.

**Out of scope**: PDF export, or any backend-side report generation —
client-side plain text first; PDF can be a separate follow-up task if the
plain-text version turns out to be insufficient.

---

### 8. Upload a lab PDF report and detect the ISCN string

**Context**: New capability — no existing code path touches PDFs.
`backend/main.py` currently only accepts an ISCN string typed, pasted, or
(tasks 6/7) loaded from a plain-text file, always client-side. Real lab
cytogenetics reports are mostly prose (patient/specimen info, methodology,
interpretation) with the karyotype buried in it as a short, distinctively-
shaped line — almost always starting with a valid modal-number pattern
(e.g. `46,XY,` or `47,XX,+21...`), which `iscn_parser.py` already knows how
to recognize and is the strongest signal to search on. Extracting text from
a PDF needs a new Python dependency (e.g. `pdfplumber` or `pypdf`) added to
`backend/requirements.txt` — there's no precedent for this in the repo, so
whichever is picked should be noted in the commit message along with why.

**Done when**:
- A file input accepts a PDF; its text is extracted **server-side** (new
  endpoint, since this needs a Python PDF library — not doable client-side
  the way tasks 6/7 were) and scanned for line(s) shaped like an ISCN
  karyotype string.
- Detected candidate string(s) are surfaced for review, not silently
  auto-parsed as ground truth — e.g. pre-filled into the existing batch
  textarea (reusing tasks 6/7's batch-parse path) so the user sees exactly
  what was extracted before it's interpreted, since real-world PDF layouts
  can break lines or introduce extraction artifacts.
- A report with zero confident candidates says so plainly rather than
  faking a result — same "honest unrecognized" principle the parser
  already follows for tokens it can't parse.
- A report with multiple karyotype lines (e.g. several specimens) surfaces
  all of them through the batch path, labeled as today.
- Covered by a few small hand-built sample PDFs: one clean single-karyotype
  report, one with two karyotype lines, one with none.

**Out of scope**: OCR / scanned-image PDFs with no text layer — real lab
reports are frequently scanned paper, so this isn't hypothetical, but it's
a different enough extraction path (and dependency) that it's split out as
task 11 rather than folded in here; extracting anything beyond the
karyotype string itself (patient name, specimen ID, ordering physician,
etc.); auto-correcting malformed extracted text before parsing — if
extraction produces something that doesn't parse cleanly, that surfaces
through the existing error/warning UI as-is, not patched.

---

### 10. Compare tool assessment against an uploaded lab report's interpretation

**Context**: Depends on task 8 (PDF upload + ISCN-string detection) and
task 9 (case-level assessment) both existing first. Task 8's scope
explicitly excludes extracting anything beyond the karyotype string
itself, so a lab report's own written interpretation/comment section isn't
captured yet. This task adds extracting *that* section (when present) and
displaying it next to this tool's own generated assessment from task 9,
so a user can compare them — not attempting to automatically judge
agreement or disagreement between two pieces of free text.

**Done when**: when a PDF uploaded via task 8's flow contains a section
introduced by one of a small, documented set of header strings (e.g.
"Interpretation:", "Comment:", "Clinical Correlation:"), that section's
text is extracted and shown side-by-side with this tool's task-9
assessment, each clearly and separately labeled ("Lab-reported
interpretation" vs. "This tool's interpretation") so the two are never
visually conflated or merged into one voice. If no such section is found,
that's stated plainly rather than leaving a blank space that reads as
"nothing to report." Covered by extending task 8's sample PDFs with one
that includes a labeled interpretation section and one that doesn't.

**Out of scope**: any automated concordance/discordance scoring or NLP
comparison between the two texts — the human reads both, the tool doesn't
judge them; editing, correcting, or annotating the lab's interpretation;
any recommendation or next-step guidance based on discordance between the
two.

---

### 11. OCR fallback for scanned-image PDF reports

**Context**: Depends on task 8 existing first. Task 8 extracts embedded
text from PDFs that have a text layer; scanned paper reports don't — the
PDF is just page images, so that extraction returns nothing. This is a
realistic, not hypothetical, case for lab reports, so it needs its own
path rather than staying permanently out of scope. It's a different
extraction mechanism and a different (likely heavier) dependency than
task 8's — e.g. `pytesseract` wrapping a local Tesseract install — and
whichever is picked, plus how it's installed/documented as a system
dependency (Tesseract isn't pure-Python), should be noted in the commit
message the way task 8 already does for its PDF library choice.

**Done when**: when a PDF page yields no (or near-zero) embedded text via
task 8's extraction, it's treated as image-only and routed through OCR
instead; the OCR'd text is scanned using the same modal-number-shaped-line
heuristic task 8 already uses. Every candidate string sourced from OCR is
visibly labeled as such (e.g. "from OCR — verify against the original")
wherever task 8 surfaces candidates for review, kept distinct from
text-layer-derived candidates — OCR's error rate on dense,
punctuation-heavy ISCN strings (commas/semicolons/parens, `1`/`l`/`I`,
`0`/`O`) is materially higher than direct text extraction, and a misread
character can silently shift a breakpoint, so this needs *more* scrutiny
before parsing, not the same amount. Covered by rasterizing one of task
8's existing sample PDFs into an image-only PDF and confirming the OCR
path recovers the same karyotype string, plus a no-candidate-found case
behaving the same as task 8's.

**Out of scope**: automatically "correcting" likely OCR misreads against
ISCN grammar (fuzzy-matching to a plausible band/chromosome) — too easy to
silently invent a wrong breakpoint instead of a missing one; non-English
reports or non-Latin scripts; unusual multi-column or heavily stylized
report layouts beyond a typical single-column lab report; any cloud OCR
API — keep it local, matching the rest of this prototype's no-external-
service posture.

---

## In progress

*(none)*

## Done

### 9. Case-level clinical assessment, with a hematologic-malignancy flag

**Context**: `iscn_parser.py` currently attaches a plain-English
`interpretation` to each individual `Finding`, and a separate reference
note to known probes/fusions (`PROBE_KNOWLEDGE`/`FUSION_KNOWLEDGE`, task 3)
— but nothing rolls the findings for a clone/case up into one overall
assessment, and nothing flags whether the pattern of findings is one
recurrently associated with a hematologic malignancy (leukemia/lymphoma).
That needs a new small, sourced, explicitly-non-diagnostic reference table
of recurrent malignancy-associated abnormalities — same shape and same
discipline as `PROBE_KNOWLEDGE`/`FUSION_KNOWLEDGE` (locus/event + one-line
association + citation), just keyed off the higher-level rearrangement
instead of a single probe. Starting candidates: t(9;22) BCR-ABL1 (CML);
t(15;17) PML-RARA (APL); t(8;21) RUNX1-RUNX1T1 (AML); inv(16)/t(16;16)
CBFB-MYH11 (AML); t(12;21) ETV6-RUNX1 (pediatric B-ALL); t(11;14)
CCND1-IGH (mantle cell lymphoma); t(14;18) IGH-BCL2 (follicular lymphoma);
-7/del(7q), del(5q), complex karyotype (MDS/AML association).

**Done when**: parsing a karyotype produces, alongside the existing
per-finding interpretations, one case-level assessment: a plain-English
summary, and — only if a finding matches the new reference table — an
explicit, clearly-labeled flag naming which finding(s) triggered it, with
the same "reference note, not diagnostic" disclaimer used elsewhere,
never phrased as an actual diagnosis. Rendered in the UI as its own
visually distinct section (`app.js`), not buried inside a per-finding
line. Tests: a set of known malignancy-associated karyotypes each raise
the flag naming the right finding; a normal karyotype and an abnormality
absent from the table both correctly raise no flag.

**Out of scope**: differential diagnosis, staging, or prognosis of any
kind; disambiguating constitutional vs. acquired abnormalities (e.g. +21
on a blood specimen could be constitutional Down syndrome *or* acquired in
AML — noting that ambiguity explicitly is fine, resolving it is not; this
tool has no clinical context to resolve it with); generating the
assessment via free-text summarization of the raw string — it's templated
from the same structured `Finding` data the parser already produces, not
LLM- or NLP-generated prose.

Done as specced: `MALIGNANCY_KNOWLEDGE` in `iscn_parser.py` covers all 9
starting candidates plus the complex-karyotype (≥3 abnormalities) rule;
`assess_case()` rolls findings from every clone up into one top-level
`assessment` (`flagged`, `summary`, `matches[]`, each match naming its
clone index, triggering finding, label, and a "Reference note (not
diagnostic)"-prefixed note). Rendered as its own amber-highlighted panel
above the clone cards (`renderAssessment()` in `app.js`), neutral/quiet
when nothing matched. 13 new tests in `TestClinicalAssessment` (44 total,
all passing) — one per malignancy rule, the complex-karyotype threshold
(and just-under-threshold), mosaic clone-index attribution, FISH-only and
empty-input edge cases. Verified in-browser for both the flagged and
unflagged rendering.

### 7. File upload of a list of cytogenetics strings

**Context**: `backend/static/index.html` and `app.js`. Task 6 (batch mode)
already parses multiple ISCN strings pasted into the textarea, one per
line, via a client-side loop over `/api/parse`. Right now getting strings
into that textarea means copy-pasting; a lab handling many cases at once
is more likely to have them in a local `.txt` file already.

**Done when**: a file input next to the textarea lets the user choose a
local plain-text file (one ISCN string per line — same shape the textarea
already expects); its contents are read client-side (`FileReader`) and fed
into the existing batch-parse path (`runParse()` / `renderClones()` from
task 6), so results render exactly as they do for pasted batch input,
labeled by input order. Uploading a file with a mix of valid/garbage lines
renders each line correctly, same as a pasted mix does today. Client-side
only — no new backend endpoint, no file persisted to disk.

**Out of scope**: CSV/XLSX or any format needing column-mapping (plain
text, one string per line, only); multi-file upload; drag-and-drop (fine
as a fast-follow if trivial, but don't block this task on it); storing or
re-serving the uploaded file.

Done client-side, same pattern as task 6: an "Upload .txt file…" button
reads the chosen file via `FileReader.readAsText`, drops the text into the
existing textarea, and calls the existing `runParse()`. `main.py` /
`iscn_parser.py` untouched; only `app.js`, `index.html`, and `style.css`
changed. Verified in-browser with a 4-line file (3 valid + 1 garbage
line) — all 4 rendered correctly, labeled "Input N of 4".

### 6. Batch / multi-string mode

**Context**: `backend/static/index.html`, `app.js`, and `main.py`'s
`/api/parse` endpoint. Currently the UI and API both handle exactly one
ISCN string per request.

**Done when**: the textarea accepts multiple ISCN strings (one per line),
and results render as a sequence of the existing per-string result blocks,
each clearly labeled by input order. Decide and document whether this is a
client-side loop over the existing single-string endpoint, or a new
batch endpoint — either is fine, but pick one and note the reasoning in
the commit message.

**Out of scope**: saving/persisting batch results, CSV import/export.

Done client-side (loop over `/api/parse` per line, `Promise.all`) — see
README's "Batch mode" section for the reasoning. `main.py` / `iscn_parser.py`
untouched; only `app.js`, `index.html`, and `style.css` changed.
