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
   *before* changing `iscn_parser.py` — the existing test suite is the
   regression net; new behavior should get the same treatment.
3. Run `python3 -m unittest discover -s tests -v` from `backend/` until
   everything passes (this runs every `test_*.py` module under
   `backend/tests/`, not just `test_iscn_parser.py`).
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

Whoever has primary-source ISCN access for this task should also
re-verify `APPROX_TERMINAL_BANDS` (same file) against it. That table is
currently sourced from a GRCh38 genome-assembly proxy (NCBI ideogram data
via Wikipedia, task 2), not the ISCN nomenclature committee's own
publication — a reasonable public stand-in, but not the actual standard,
and assembly-derived coordinate data can drift slightly across genome
versions in a way the classical ISCN band names themselves don't. Same
trigger condition as the edition-differences work above (someone with
real ISCN text in hand), so bundling it in here avoids tracking staleness
on a separate, arbitrary schedule.

**Done when**: at least 2 more sourced, dated edition differences are in
`EDITION_NOTES`, each with a code comment citing where the difference comes
from. A test per new entry, following the pattern of
`test_rob_edition_note_present`. Separately: `APPROX_TERMINAL_BANDS`
checked against the primary ISCN source consulted for this task, with any
corrections noted (including "no changes needed" if it already checks
out) and the table's source comment updated to cite the primary text
instead of (or alongside) the genome-assembly proxy.

**Out of scope**: don't guess at plausible-sounding differences without a
source — an unsourced "note" here is worse than no note, since it reads as
authoritative. If a difference can't be confirmed, leave it out and say so
in the PR/commit description instead of including it anyway. Re-deriving
sub-band-level (decimal) precision for `APPROX_TERMINAL_BANDS` is still
out of scope per task 2 — this only covers re-verifying the major band
numbers already there.

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

### 12. Incorporate clinical review feedback on the hematologic-malignancy flag (task 9)

**Context**: Task 9 added a case-level assessment (`MALIGNANCY_KNOWLEDGE`,
`assess_case()` in `iscn_parser.py`) that flags karyotype findings
recurrently associated with hematologic malignancy. Before that feature is
trusted, it was sent out for clinical review — see the review document:
https://claude.ai/code/artifact/eedf8fc3-071a-4d6b-9ede-715b86094b4a —
which lays out five specific open questions: (1) whether matching should
require the exact breakpoint band rather than just the chromosome pair,
(2) whether the 9-entry reference table is itself accurate, (3) whether
"3+ unrelated abnormalities" is the right complex-karyotype threshold,
(4) whether "Reference note (not diagnostic)" is strong enough wording,
(5) what's missing from the table. This task is blocked on that feedback
arriving — see the review doc for the full framing of each question.

**Done when**: clinician feedback has come back on the review document,
and each of its five open questions has either been acted on (a code,
table, or wording change) or explicitly resolved as "no change needed" —
with the resolution recorded here. If band-level matching is requested
(question 1), that's a real logic change to the matchers in
`iscn_parser.py`, not just a data edit. Any resulting change gets test
coverage the same as task 9's did.

**Out of scope**: guessing at answers to the open questions without actual
clinician input — if feedback hasn't arrived yet, this task stays exactly
as blocked/under-review, not "resolved" preemptively.

---

### 14. Batch mode breaks on ISCN strings with embedded line-wraps

**Context**: `runParse()` in `app.js` splits pasted text on every `\n`
and treats each resulting line as one independent ISCN string (task 6).
That assumption breaks when a *single* ISCN string has been copy-pasted
from a source that word-wrapped it across multiple physical lines (a PDF
viewer, a Word doc, some EMR "copy" buttons) — confirmed live while
fixing task 13: a real user-reported string with mid-token line wraps got
shredded into 5 broken fragments instead of being parsed as one string.

**Done when**: investigate whether a safe, non-guessing improvement
exists — e.g. only treating a `\n` as a batch-entry boundary when bracket
depth is balanced at that point (mirroring how `split_top_level()`
already respects bracket depth for commas), which would fix line wraps
that happen to fall mid-parenthesis. Confirmed during investigation: this
alone does **not** fully solve the reported case, since some wraps land
at bracket-depth-zero points (e.g. right after a comma) that are
genuinely indistinguishable from an intentional new batch entry — so the
"done" bar here is "meaningfully reduces the failure without introducing
false merges of genuinely separate entries," explicitly not "handles
every possible line-wrapped paste." If no safe improvement is found,
"done" can also mean: documented clearly (in the UI, not just this file)
that a single ISCN string must be one unbroken line, with test coverage
proving today's behavior (whatever it ends up being) is intentional, not
accidental.

**Out of scope**: any heuristic that tries to *guess* how to rejoin two
fragments (e.g. detecting "this line doesn't look like a complete
ISCN string, glue it to the previous one") — too easy to silently
misjoin two genuinely separate, intentional batch entries. See task 13's
resolution notes for why this was deferred rather than attempted inline.

**Update (task 16)**: a structurally-grounded version of exactly this —
not a content guess, just "this can't have legally ended here" (unbalanced
parens / trailing comma / ends in "ish") — turned out to work well for the
*backend* PDF-text-extraction path (task 16), reconstructing a real
hard-wrapped report string byte-for-byte correctly. The same technique
(`_candidate_needs_continuation()` / `_continuation_separator()` in
`iscn_parser.py`) is a reasonable starting point if this task is picked
up — it would need porting to `app.js` (client-side, no access to the
Python logic), and batch mode's "one line = one entry" contract is a
stronger assumption to bend than PDF-text scanning's "no per-line
contract at all," so re-validate the false-merge risk in that context
before reusing it as-is.

---

### 15. Capture band-locus prefix in multi-probe nuc ish lists

**Context**: `parse_fish_only_clone()` in `iscn_parser.py`, "Case 2"
branch (a `nuc ish(...)` body shaped like `locus(PROBE),locus(PROBE),...`,
e.g. `1p32(CDKN2Cx2),13q34(LAMP1x2)`). Discovered while fixing task 13:
`groups = re.findall(r'\(([^()]*)\)', body)` only ever captures what's
*inside* each probe's own parens — the leading band-locus text (`1p32`,
`13q34`) immediately before each `(` is silently dropped, never appearing
anywhere in that probe's `Finding` or its `raw`/`interpretation`. This is
a real information loss for any multi-locus interphase FISH panel, one of
the more common way labs report a "FISH panel" result. Pre-existing —
not introduced by task 13 (which reuses this same branch), just newly
surfaced by a test exercising a 15-probe real-world panel.

**Done when**: each probe's `Finding` retains its band-locus text, if
one was given (e.g. as a new field, or folded into `interpretation` — pick
whichever fits the existing `Finding` shape best and document the choice).
Tests: a multi-probe list with loci confirms each is captured against the
right probe (not just present somewhere in the combined output).

**Out of scope**: validating the locus itself against `APPROX_TERMINAL_BANDS`
or any other plausibility check — this task is just "don't silently drop
data that was given," not new validation.

---

## In progress

*(none)*

## Done

### 16. Fix multi-line ISCN strings in PDF text extraction

**Context**: Bug report from live use, with a real (de-identified example)
lab report PDF attached — task 8's `find_candidate_iscn_lines()` scans
extracted PDF text line by line, and a real report-generation software
(Warde Medical Laboratory's layout, confirmed against the actual PDF) hard-
wraps a long ISCN string across several physical lines *within the PDF's
own text layer*. Nothing to do with OCR (task 11) — every page of the
reported PDF had a full, substantial text layer (1900+ characters), so
OCR was never invoked; nothing to do with how the string was pasted
anywhere either (task 14, still open, is the separate frontend/batch-mode
version of this same underlying problem: line wraps in *pasted* text).
`find_candidate_iscn_lines()`, before this fix, grabbed only the first
physical line of a wrapped candidate and silently discarded everything
after it — for the actual reported PDF, that meant capturing
`"46,XY[20].nuc ish"` and losing the entire 15-probe FISH panel plus the
final cell count.

**Done when**: a candidate that can't have legally ended where a physical
line did (an unclosed `(`, a trailing `,`, or ending in the word `ish` —
structural signals, not content guesses) keeps folding subsequent lines
in until none of those hold anymore, capped so it can never run away
across an entire document. Verified against the actual reported PDF, not
just a synthetic case.

**Out of scope**: perfect reconstruction in every conceivable case — this
is deliberately a structural, not semantic, heuristic; porting the same
technique to fix task 14 (the frontend/batch-mode version of this
problem) — different code (JS, no access to this Python logic) and a
different risk profile (batch mode's "one line = one entry" is a
stronger contract to bend than PDF text scanning's "no per-line contract
at all").

Done: `_candidate_needs_continuation()` checks the three structural
signals above; `_continuation_separator()` joins with no separator by
default (most real-world wraps land mid-token, e.g. `"TP53x"` + `"2"` →
`"TP53x2"`) except right after `"ish"`, which ISCN grammar always follows
with a space before the probe/rearrangement content — a narrow,
grammar-grounded exception, not a guess.
`MAX_CANDIDATE_CONTINUATION_LINES` (15) caps runaway consumption.

6 new tests in `TestCandidateLineDetection` (77 total, all passing),
including the exact real-world wrapped text from the reported PDF as a
byte-for-byte reconstruction check, a capped-runaway case, and confirming
a genuinely separate second candidate right after a terminated one still
comes back as its own entry. Verified live end-to-end with the actual
PDF file uploaded through the real UI (temporarily served via the dev
server's static mount, removed after testing — never committed to the
repo): both candidates found (the full FISH panel, correctly
reconstructed, plus a separate plain `46,XY` from the report's
"KARYOTYPES" section), both parsed cleanly with zero errors.

### 13. Support combined karyotype + FISH clone notation (period-joined)

**Context**: Bug report from live use — a real ISCN string of the form
`46,XY[20].nuc ish 1p32(CDKN2Cx2),...,12cen(D12Z3x2)[200]` failed to
parse: `sex_chromosomes` came back as garbage
(`"XY[20].nuc ish 1p32(CDKN2Cx2)"`) and every individual FISH probe came
back `unrecognized`. Root cause: `parse_iscn()` had zero concept of
ISCN's `.` (period) convention, which joins a karyotype clone to a FISH
result for the *same* cell population (as opposed to `/`, which starts a
genuinely different clone) — the whole string was going through
`parse_karyotype_clone()`, which has no notion of a trailing FISH clause,
so everything from `nuc ish` onward got glued onto whatever top-level
comma-token it fell into.

**Done when**: `<karyotype>[N].nuc ish ...[M]` and `<karyotype>[N].ish
...[M]` both parse into one combined clone: the karyotype's own
`modal_number`/`sex_chromosomes`/`cell_count` intact, a new
`fish_cell_count` for the FISH clause's own count, and findings from both
halves concatenated (karyotype findings first, then FISH findings, in
order) with no errors. The join-point detection must not collide with
band sub-decimals (e.g. `13q14.3`), which are real and common in FISH
locus lists.

**Out of scope** (surfaced while fixing this, deliberately not addressed
here — see their own task entries): batch mode's newline-splitting still
breaks on a *pasted* version of this string if it has mid-token line
wraps from the source document (task 14); the leading band-locus text in
a `locus(PROBE),locus(PROBE),...` list isn't captured anywhere in the
output, a separate pre-existing gap in the same code path (task 15).

Done: new `COMBINED_KARYOTYPE_FISH_RE` in `iscn_parser.py` finds the
`.` immediately followed by `nuc ish`/`ish` (optionally across
whitespace, including a stray newline — that part is free, since `\s`
already spans newlines) and splits there; `parse_combined_karyotype_and_
fish()` runs the existing `parse_karyotype_clone()` and
`parse_fish_only_clone()` on each half and merges the results. Also fixed
a related gap found in the same investigation: `parse_fish_only_clone()`
was silently dropping ANY standalone FISH clone's own trailing `[N]`
cell count (e.g. `nuc ish(D21S259x3)[200]` never populated `cell_count`)
— now it strips and captures it the same way the karyotype parser always
has. New `fish_cell_count` field on `CloneResult`; `app.js` shows it
("N FISH nuclei") alongside the existing cell-count meta line.

7 new tests in `TestCombinedKaryotypeFish` plus 1 in `TestFish` (72
total, all passing) — including the actual reported string (cleaned of
its incidental line-wraps; see task 14) as a real-world regression case,
and an explicit check that a band sub-decimal never false-triggers the
new split. Verified live in the browser with both the wrapped-as-pasted
version (demonstrating task 14's separate, deliberately-deferred issue)
and the single-line version (clean parse, all 15 probes recognized,
`200 FISH nuclei` shown).

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

Done: chose `pypdf` over `pdfplumber` specifically for having zero
transitive dependencies of its own (`pip show pypdf` → `Requires:`
empty), matching this project's stated minimal-dependency stance —
`pdfplumber` pulls in `pdfminer.six`, `Pillow`, and more, which felt like
too much weight for "extract embedded text from typically-simple
single-column lab reports." Also added `python-multipart`, a runtime
requirement of FastAPI's `UploadFile` support, not something either PDF
library needed. New endpoint `POST /api/extract-pdf` in `main.py`;
detection logic (`find_candidate_iscn_lines()`, a modal-number +
sex-chromosome-prefix regex) lives in `iscn_parser.py`, keeping it
framework-agnostic like the rest of that file. Frontend deliberately does
**not** auto-run parse after a PDF upload (unlike the `.txt` upload) —
candidates are loaded into the textarea for review only, since PDF
extraction is inherently a guess, not a trusted input.

Tests: 6 new in `TestCandidateLineDetection` (pure text-scanning logic,
zero extra dependencies) plus a new module `test_pdf_extraction.py` (3
tests) that builds small PDFs entirely in-code — hand-rolled raw PDF
syntax, no external PDF-authoring library, no binary fixture files
committed — covering exactly task 8's three required cases (single
candidate, two candidates, none). Deliberately skipped FastAPI's
`TestClient` (needs `httpx`, not otherwise a dependency); the actual HTTP
route was verified by hand in the browser instead — a real generated PDF
uploaded through the live UI via a dispatched `change` event, covering
the success, zero-candidate, and non-PDF-file-rejected paths. 65 tests
total, all passing. README and the "How to pick up a task" test command
both updated for the new two-module test suite.

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

Done: all 12 missing chromosomes (2, 3, 4, 6, 8, 10, 12, 15, 18, 19, 20, Y)
added, sourced from NCBI's GRCh38 ideogram data as tabulated on each
chromosome's English Wikipedia page (cited in a code comment, with the
retrieval date) — pulled live via WebFetch this session rather than
recalled from memory. Chromosome 15 got a q-only entry, matching the
existing acrocentric-chromosome convention (13, 14, 21, 22). 12 new tests
in `TestTerminalBandCoverage` (56 total, all passing), one per newly-added
chromosome, each confirming a plausible band produces no warning and an
implausible one does. The original 12 entries remain unsourced and still
flagged as such — out of scope for this task to backfill their sourcing.

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
