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

## Git / PR workflow

- **Docs-only edits** (`TASKS.md` and/or `README.md`, no code touched) —
  commit straight to `main`, no branch, no PR. Nothing functional is at
  risk, so the overhead of a PR doesn't pay for itself.
- **Anything touching code** (`backend/`, `.github/workflows/`, etc.) —
  create a branch, open a PR, and **wait for an explicit instruction to
  merge it** before merging — even if CI is green. CI passing only means
  the tests that already exist still pass; it doesn't catch design or
  criteria problems, which in this repo's history have repeatedly turned
  up in review rather than in a test run (e.g. the OCR-prefix marker that
  silently broke parsing, the `COMMENT`-as-terminator logic that dropped
  real content, an incomplete test fixture). There's no auto-merge policy
  layered on top of this — since docs-only changes already skip the PR
  step entirely, every PR that exists is by definition a real code
  change, so "manual review before merge" already covers 100% of PRs by
  construction, not as a separate rule bolted on top.
- After a PR is merged, delete the branch (`gh pr merge --squash
  --delete-branch` does both in one step). Stale branches left around
  after merging accumulate as clutter with no unmerged content behind
  them — periodically confirmed and cleaned up (all merged PRs' branches
  were pruned as of task 19).
- `main` has branch protection: PRs can't merge unless the `test` GitHub
  Actions check (`.github/workflows/tests.yml`, task 19) passes.
  Direct pushes to `main` (the docs-only case above) are **not** blocked
  by this — required-status-checks only gate PR merges, not direct
  pushes, and `enforce_admins` is off.
- If CI fails on a PR, diagnose the actual root cause and push a real
  fix, then report what broke and what changed — don't just adjust an
  assertion until the check goes green without understanding why it
  failed. (Precedent: task 19's CI run caught a genuine cross-environment
  OCR/font bug this way, not something to paper over.)
- After merging, only re-run the full test suite locally on `main` if the
  merge wasn't a clean fast-forward (i.e. it needed conflict resolution
  or a rebase, producing a genuinely new combination of code nothing has
  tested yet). A clean fast-forward merge's content is byte-identical to
  what was already tested locally *and* independently by CI — a third
  full run on identical content isn't new verification, just ceremony.
  Confirm via `git log`/`git status` that the expected commit landed
  instead.
- Write-up depth in a task's "Done" resolution should scale with how
  subtle or risky the change was — full Context/Done-when/resolution
  detail (with root-cause explanation, what was tried, what the
  verification actually checked) for anything non-obvious or bug-fix-y;
  a few sentences suffice for small, low-risk, self-evident changes. Not
  every task needs the same depth just for consistency's sake.

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

**Context**: `backend/static/app.js` (`renderClones()`/`runParse()`,
which hold the currently-rendered parse result) and `backend/main.py`.
No export functionality exists yet — findings are only ever rendered
live in the DOM.

**Done when**: a "Copy interpretation" button in the results area copies a
plain-text rendering of the current parse result to the clipboard (modal
number, sex chromosomes, each finding's interpretation, warnings) —
client-side only, no new backend endpoint needed. Formatting should be
readable as plain text (e.g. in an email), not just a JSON dump.

**Out of scope**: PDF export, or any backend-side report generation —
client-side plain text first; PDF can be a separate follow-up task if the
plain-text version turns out to be insufficient.

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

## In progress

*(none)*

## Done

### 25. Export a parsed report as an mCODE-shaped FHIR genomics resource (stage 1)

**Context**: The long-term goal is using this tool's output to help
populate CIBMTR transplant-outcomes forms. CIBMTR does publish its own
FHIR Implementation Guide with a dedicated Cytogenetics profile, but it
shows real staleness signals on inspection: its own QA page describes it
as "the first publication," pins an outdated IG-Publisher toolchain and
an older `hl7.us.core` version than what's current, and (at the time we
checked) its package-list endpoint was returning a live "Service
Unavailable" error. We could not confirm actual cytogenetics-specific
use of it in the wild, as distinct from CIBMTR's broader (and real,
Epic-integrated) Data Transformation Initiative for other data types.

Targeted **mCODE** instead — HL7's oncology-specific US FHIR
Implementation Guide — as the primary shape for this stage. Specifically
mCODE's **Genomic Variant Profile** and **Genomics Report Profile**,
which formally derive (`baseDefinition`) from HL7's own Genomics
Reporting IG (Variant profile and
`http://hl7.org/fhir/uv/genomics-reporting/STU2/StructureDefinition-genomics-report`
respectively) — confirmed by fetching both profiles' actual
`StructureDefinition` pages. So this isn't a competing spec to CIBMTR's:
mCODE is a formal, oncology-flavored specialization of the same
domain-agnostic genomics model CIBMTR's profile only loosely tracks, and
it has meaningfully stronger real-world footing — 70+ implementations,
built into Epic, active CodeX use cases in clinical trials matching and
cancer registry reporting.

The core clinical vocabulary is shared regardless of which profile is
ultimately targeted, so nothing here is thrown away if a CIBMTR-specific
adapter gets added later: CIBMTR's own example Cytogenetics Observation
uses LOINC `69548-6` ("Genetic variant assessment") as the main code,
LOINC `81291-7` for a component carrying the raw ISCN string itself
(value system `https://iscn.karger.com`), and LOINC `48002-0` ("Genomic
source class") valued `LA6684-0` ("Somatic"). These are standard
genomics LOINC codes, not CIBMTR-specific.

**Done when**:
- A parsed, error-free clone can be exported as FHIR JSON matching
  mCODE's Genomic Variant / Genomics Report profile shape (ISCN
  component = the validated raw ISCN string, reusing the LOINC codes
  above where they fit mCODE's actual element definitions; genomic
  source class = Somatic; method inferred from clone type — karyotype
  vs FISH-only vs combined).
- If a PDF was the source, candidate `subject`/demographic fields
  (patient name, DOB, specimen ID, collection/report date) are extracted
  the same structural way karyotype candidates already are, and shown
  to the user for explicit review/edit/confirmation before being
  included in the export — **never** silently auto-populated into the
  exported resource. If typed/pasted input was used instead (no PDF),
  these fields are just blank, user-fillable inputs.
- A clone the tool itself flagged with errors or unrecognized tokens
  cannot be exported without an explicit override — the tool's own
  validation becomes a pre-export QC gate, not bypassed silently.
- No data is persisted server-side and no network call is made to
  mCODE, CIBMTR, or anywhere else — this is a local "produce the JSON,
  let the user save/copy it" feature, same trust boundary the tool has
  always had.

**Out of scope**: actual submission anywhere, including CIBMTR's Direct
FHIR API (needs real OAuth2/OIDC credentials issued per institution,
and its own explicit go/no-go decision); a CIBMTR-specific adapter/thin
wrapper on top of the mCODE output (worth revisiting if CIBMTR's own
FHIR pathway is later confirmed actually live, but not now); any
server-side storage of extracted patient data; decomposing the ISCN
string into finer-grained FHIR elements than mCODE's own profile asks
for — this tool's internal `Finding` structure doesn't need to be
re-modeled into FHIR; supporting FHIR profiles/resources beyond the
genomics observation(s) themselves (e.g. full Patient/Specimen
resources) unless mCODE's profile actually requires them as separate
resources rather than reference stubs.

Done: new module `fhir_export.py` (kept separate from `iscn_parser.py`
— this is output-shaping for a specific downstream consumer, a
different concern from ISCN grammar). Two independent pieces:
`extract_subject_candidates()` (label-based regex scan for the five
subject fields, deliberately narrower/stricter than the existing
karyotype-candidate and lab-interpretation scanners, since a
false-positive here feeds a clinical-shaped export rather than just a
review textarea) and `build_mcode_export()` (turns a `parse_iscn()`
result into a FHIR `Bundle`).

Before writing code, fetched the actual mCODE `StructureDefinition`
pages rather than relying on memory: confirmed the Genomics Report
Profile is `DiagnosticReport`-based (category fixed to Genetics,
`result` = array of Observation references — the standard FHIR
report-wraps-results pattern) and the Genomic Variant Profile is
`Observation`-based (`code` fixed to LOINC 69548-6, a
`cytogenomic-nomenclature` component at LOINC 81291-7 — the same code
CIBMTR's real example used, confirming it's genuinely shared genomics
vocabulary and not a CIBMTR invention). Two things could *not* be
verified this way — the exact LOINC answer-list code for
`Observation.method`, and whether "genomic source class" (48002-0) is
an officially defined mCODE component slice — so rather than fabricate
either, `method`/the report's top-level `code` are populated as
text-only `CodeableConcept`s (mCODE's binding for `code` is
"preferred," not fixed, so this is spec-compliant, just not maximally
coded), and every export response carries a `caveats` list naming
exactly what wasn't verified, shown to the user next to the JSON.

Date handling: rather than parse ambiguous free-text dates
server-side (which would mean guessing MM/DD vs. DD/MM), the frontend
uses native `<input type="date">` for every date field, so by the time
a date reaches the export endpoint it's already an unambiguous ISO
string. `normalize_date()` still exists for two narrower purposes:
best-effort pre-filling those date inputs from a raw PDF-extracted
candidate (US slash/dash format assumed, ISO passed through, anything
else left for the human to type), and defense-in-depth validation if
the endpoint is ever called directly. An extracted date that can't be
normalized isn't lost — the raw text is shown as a hint next to the
still-blank date input.

The pre-export QC gate reuses exactly the same "errors or an
unrecognized finding" condition the UI already labels "Needs review" on
a clone-card, so the export button's default-disabled state and the
on-screen status badge can never disagree; an explicit override
checkbox unlocks export anyway, matching `build_mcode_export()`'s own
`override` parameter (also enforced server-side — the frontend check is
a UX convenience, not the actual gate).

23 new tests in `test_fhir_export.py` (136 total, all passing): subject
extraction (each field, alternate labels, no false-positive on
unrelated labels), date normalization (ISO, US slash/dash,
out-of-range/unrecognized formats rejected), the bundle shape (report +
one Observation per clone, `result` references matching, ISCN and
genomic-source-class component values, Patient/Specimen only present
when subject fields are given, an invalid date omitted with a caveat),
and the QC gate (blocked by errors, blocked by an unrecognized token,
allowed through with `override=True`, empty-input case). Verified live
in the browser end-to-end: parsed a real mosaic karyotype, filled in
all five subject fields, exported, and inspected the resulting Bundle
JSON (correct `DiagnosticReport`/`Observation`/`Patient`/`Specimen`
shape, correct references, correct dates); separately confirmed a
clone with an unrecognized token disables the export button by default
and the override checkbox correctly unlocks it.

### 24. Grow MALIGNANCY_KNOWLEDGE with a CLL panel and 6 more entries

**Context**: Follow-up from task 23. Two research passes: (1) a general
search for well-established recurrent cytogenetic markers not yet in the
table, and (2) cross-checking against CIBMTR's own Disease Classification
form (2402) — what a real-world transplant-outcomes data-collection
operation considers worth a standardized field, an independent signal
from the WHO-classification framing the table started from. CIBMTR's
form confirmed most of pass (1)'s findings and surfaced one more
concretely addable candidate (t(1;19)). Biggest single gap found: chronic
lymphocytic leukemia (CLL) had zero representation in the table at all,
despite being one of the most common adult leukemias and a textbook case
of FISH-panel-driven prognosis.

**Done when**: 10 new entries, each fitting the existing matcher shape
(a specific chromosome pair or single-chromosome event, no new matcher
architecture needed) and each cited to an accurate primary source, not
just tagged "CIBMTR" (a form field confirms something is tracked, not
why it matters clinically):
- CLL panel (Döhner et al., *N Engl J Med* 343:1910, 2000 hierarchy):
  del(17p), del(11q), +12 (trisomy 12), del(13q).
- Burkitt lymphoma's three MYC-partner translocations: t(8;14), t(2;8),
  t(8;22).
- Two more B-ALL-associated translocations CIBMTR's own form tracks:
  t(4;11) (KMT2A-AFF1), t(1;19) (TCF3-PBX1).
- del(20q), an MDS/MPN-recurrent deletion alongside the existing
  del(5q)/-7 entries.

**Out of scope**: "monosomal karyotype" — also found via the CIBMTR
cross-check (MDS), but it's a case-level pattern (2+ distinct autosomal
monosomies, or one plus a structural abnormality), architecturally more
like the existing "complex karyotype" rule in `assess_case()` than a
`MALIGNANCY_KNOWLEDGE` row — real design work, not a quick add; flagged
for a future task if wanted. CEBPA/TP53 "mutation" (also CIBMTR-tracked
for AML) — molecular/sequencing findings, not visible in an ISCN
karyotype string at all, out of scope by the tool's own input model, not
a gap in the table. KMT2A rearrangements generally (t(4;11) is one
specific, well-known partner of 90+ possible ones) — a generic "any
translocation touching 11q23" rule would need a new band-aware matcher,
not just a table row.

Done: 10 new `MALIGNANCY_KNOWLEDGE` entries using only the existing
`_single_chrom_matcher`/`_chrom_set_matcher` helpers — no new matcher
logic needed. Checked for chromosome-set collisions against all 10
existing entries before writing any code; none found. del(17p)'s note
is deliberately worded to flag that it's *not* CLL-specific (TP53 loss
is adverse across CLL, MDS, and AML alike) — unlike del(11q)/+12/
del(13q), which are more genuinely characteristic of CLL specifically.

10 new tests in `TestClinicalAssessment` (113 total, all passing), one
per entry, confirming the correct label appears and nothing cross-
matches an unrelated existing entry (spot-checked directly: each of the
10 new cases produces exactly one match, none bleed into e.g. the
existing t(11;14)/t(14;18) entries despite sharing chromosome 14 or 11
with some of them). Verified live in the browser.

### 23. Add trisomy 8 to MALIGNANCY_KNOWLEDGE

**Context**: Follow-up from task 22's real report — a de-identified
MDS-workup report whose own interpretation calls trisomy 8 "a recurrent
abnormality seen primarily in myeloid neoplasms including MDS, MPNs and
AML," yet this tool's case-level assessment (`MALIGNANCY_KNOWLEDGE`,
task 9) didn't flag `+8` at all. Unlike every existing entry, trisomy 8
isn't a single WHO-defined disease-subtype-specific fusion event — it's
a common recurrent finding across several myeloid neoplasms, better
characterized via the IPSS-R cytogenetic risk scoring system for MDS
(Greenberg, Tuechler, Schanz et al., Blood 120:2454, 2012) than the
WHO-classification framing the rest of the table cites, and the actual
real report cited that exact paper independently.

**Done when**: `+8` (trisomy 8) is a matchable entry in
`MALIGNANCY_KNOWLEDGE`, same shape and same "reference note, not
diagnostic" discipline as the existing entries, with an accurate
citation (not the generic WHO-classification framing, which doesn't fit
this entry). Test coverage the same as the other entries.

**Out of scope**: growing the table further beyond trisomy 8 (e.g. +9,
del(20q), other MDS/AML-recurrent numerical findings) — narrowly scoped
to what task 22 actually surfaced; a broader table expansion is its own
future task if wanted.

Done: new entry in `MALIGNANCY_KNOWLEDGE` using the existing
`_single_chrom_matcher("+", "8", category="numerical")` helper (same
pattern already used for `-7`). Caught and fixed while implementing:
two existing tests
(`test_complex_karyotype_flags_without_specific_match`,
`test_two_abnormalities_not_complex`) used `+8` as one of their "not
individually in the table" example abnormalities — both would have
silently changed meaning (one still passing for the wrong reason via
`assertTrue`/`any(...)`, the other failing outright) once `+8` became
individually flaggable; swapped to `+9` in both, which isn't in the
table.

Also caught in review before finalizing: the note text's first draft
said "not... like the entries above," phrasing that only makes sense
read in the source file next to the other entries — reworded so the
note stands on its own when read in isolation in the UI, which is how
a user actually encounters it.

2 new tests in `TestClinicalAssessment` (103 total, all passing): a
minimal `+8` case, and the actual real-world string from task 22's
report (`47,XY,+8[10]/46,XY[10]`) confirming the flag is attributed to
the correct (abnormal) clone, not the normal one in the same mosaic
pair. Verified live in the browser: the "Reference flag" panel now
renders correctly for that exact string.

### 22. Trim a report-generation label glued onto the end of a candidate

**Context**: Bug report from live use, with a real (de-identified example)
lab report PDF attached (Diagnostic Cytogenetics Incorporated's template).
`find_candidate_iscn_lines()` returned
`"47,XY,+8[10]/46,XY[10]ABNORMAL RESULTS:"` — a real, valid karyotype
string with the report's own section label (`ABNORMAL RESULTS:`) glued
directly onto the end, zero separator, both on one physical line.
Confirmed against the actual PDF's raw `pypdf.extract_text()` output:
this report-generation software consistently emits *value* immediately
followed by *label* with no separator throughout its whole text layer
(`"XX-XXXXCust. Specimen ID:"`, `"11/08/2016Collection Date:"`, etc.) —
the same underlying quirk as the `find_lab_interpretation()` inline-
header case from task 10's revisit, just landing on the karyotype line
itself this time, where `CANDIDATE_LINE_RE`'s "grab to end of line" rule
has no way to know where the real content stops.

**Done when**: a candidate whose trailing content, immediately after a
closed `[N]` cell count, isn't a legal ISCN continuation (another clone
via `/`, a combined FISH clause via `.`, or end of string) is trimmed
right there — using ISCN's own grammar as the stop signal, not a guess
about what looks like prose, and without altering any character of the
actual candidate. Verified against the real reported PDF, not just a
synthetic case.

**Out of scope**: general trimming of trailing prose caught on a line
with no bracket to anchor on (e.g. `"46,XY normal male karyotype, no
abnormality detected."`) — that's still surfaced as-is for human review,
unchanged from task 8's original scope; only the specific, grammar-
grounded closed-bracket signal is a new exception.

Done: new `_trim_trailing_garbage()` in `iscn_parser.py`, applied to
each candidate in `find_candidate_iscn_lines()` right after continuation
folding completes (so it composes cleanly with tasks 16/17's folding
logic rather than interacting with it). Scans for the first `]` whose
following content (ignoring whitespace) isn't `/` or `.`, and truncates
there. A candidate with no bracket at all is untouched, so the existing
"no general auto-trimming" behavior and its test are unaffected.

6 new tests in `TestCandidateLineDetection` (101 total, all passing):
the minimal reproduction, valid `/` and `.` continuations confirmed *not*
trimmed, the ordinary "nothing glued after" case confirmed not trimmed,
and the real report's actual extracted text as a byte-preserving
regression case. Verified against the real PDF directly
(`find_candidate_iscn_lines()` on its actual `pypdf` output) and live
end-to-end through the real UI: candidate loads clean, parses with zero
errors, lab-reported interpretation panel renders correctly alongside it.

Noted in passing, not fixed here (out of scope for this bug): the
report's own interpretation calls trisomy 8 "a recurrent abnormality
seen primarily in myeloid neoplasms including MDS, MPNs and AML," but
`MALIGNANCY_KNOWLEDGE` (task 9) has no `+8` entry, so this tool's own
assessment doesn't flag it. Worth a future backlog item if this table
gets grown further (task 3 is the adjacent one, though that's scoped to
`PROBE_KNOWLEDGE`/`FUSION_KNOWLEDGE`, not the malignancy table).

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

Done: ported as `foldLineWrappedEntries()` / `lineNeedsContinuation()` /
`continuationSeparator()` in `app.js`, run as a pre-pass in `runParse()`
before the existing per-line loop. Same three structural signals as the
Python original (unclosed `(`, trailing list comma, ends in "ish"),
same `MAX_LINE_WRAP_CONTINUATIONS` (15) cap against a genuine unclosed-
paren typo silently swallowing every subsequent entry. Only ever folds a
line into the *immediately preceding* entry when that entry itself looks
structurally incomplete — never merges two lines that both look complete
on their own — so the false-merge risk the task called out for batch
mode's stronger "one line = one entry" contract doesn't apply: this
never guesses that two complete-looking entries belong together, only
that an incomplete-looking one continues.

One addition beyond the ported logic: a blank line always breaks
folding, even if the preceding entry still looks structurally
incomplete — there's no legitimate reason a real line wrap would land on
a blank line, so this is a free, unambiguous extra safety margin the PDF
version didn't need (PDF-extracted text doesn't have user-intentional
blank-line separators the way a batch paste can). Caught a real bug in
this exact piece during manual testing: the first implementation reset
the continuation *counter* on a blank line but didn't actually block the
fold itself, so it silently folded across the blank line anyway —
fixed with an explicit `blockedByBlankLine` flag, re-verified after the
fix.

Confirmed the task's own predicted limitation still holds and is
correctly *not* "fixed": a wrap landing right after a complete
`t(9;22)` pair (balanced parens at that point) is structurally
indistinguishable from an intentional new entry, so it's left as two
separate (one broken, one garbage) entries — exactly the acknowledged
tradeoff, not a regression.

No backend changes; no new backend tests (frontend-only, consistent
with tasks 18/20/21). Verified live in the browser: the real 6-line
hard-wrapped FISH panel string (same one used in task 16's regression
test) now parses as one clean entry with all 15 probes and their loci
(task 15) correctly recognized; a mixed paste (a mid-comma-wrapped
`nuc ish(...)` entry alongside separate simple entries) folds only the
wrapped one, leaving the others untouched (`Input 1 of 4` .. `Input 4 of
4`, each independently correct); the blank-line-breaks-folding and
15-line-cap cases confirmed directly via the console.

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

Done: `interpret_fish_token()` gained an optional `prefix_locus`
parameter (used only when the token has no locus of its own via the
pre-existing suffix form, `_LOCUS_SUFFIX_RE`, so the two never
conflict); folded into `interpretation` the same way the suffix form
already was (`"(locus {locus})"`), and into a new `bands=[locus]` on
the `Finding` — reusing the same field structural findings already use
for breakpoint bands, rather than inventing a new one.

`parse_fish_only_clone()`'s Case 2 branch now extracts each
`(locus, probe_list)` pair with a new `_GROUP_WITH_LOCUS_RE` (a locus
group, possibly empty, followed by its parens) instead of the old
paren-only `re.findall`, and passes that locus to every probe found in
`split_top_level()` of that group — so a locus shared by multiple probes
inside one set of parens (`1p32(CDKN2Cx2,OTHERx1)`) applies to both, and
a list with no locus prefix at all behaves exactly as before (regression
covered explicitly).

3 new tests (91 in `test_iscn_parser.py`, 97 total): per-probe locus
correctly attributed and not cross-attributed to the wrong probe, a
locus shared across multiple probes in one group, and the no-locus-
prefix form still producing empty `bands`/no "locus" text. Also
strengthened the existing 15-probe real-world regression test, which
previously only incidentally passed via IGH's own `PROBE_KNOWLEDGE` note
text (its reference note text happens to start with "14q32", its actual
genomic locus, coincidentally masking that the fix wasn't actually being
tested) — now separately asserts on CDKN2C, which has no knowledge-note
of its own, so the locus can only be coming from the input string.
Verified against the real CHRTU-1.pdf FISH panel (all 15 probes) and
live in the browser: every probe's locus renders correctly in its own
interpretation text, no cross-attribution.

### 20. Clearer in-progress indicator for slow file loads (PDF/OCR)

**Context**: `pdfFileInput` change handler in `backend/static/app.js`.
The only sign of work happening today is a text swap via
`showUploadStatus('Reading "..."…')` — same small, muted-gray
`.upload-status` paragraph (`backend/static/style.css`) used for the
final result message, no visual distinction between "still working" and
"done." For a text-layer PDF this resolves fast enough that it barely
matters, but the OCR fallback (task 11, `_extract_page_candidates()` in
`main.py`) rasterizes and OCRs each image-only page and can take several
seconds per page — during which nothing on screen changes, the upload
button stays clickable, and a user has no way to tell "still working"
from "silently did nothing." The plain-text `.txt` upload path
(`fileInput` handler, same file) is synchronous/instant and doesn't
need this.

**Done when**: while a PDF upload request is in flight, the UI shows an
unambiguous busy signal distinct from the resting/result state — e.g. a
spinner or animated indicator alongside the status text, plus
`upload-pdf-btn` (and ideally `pdf-file-input`) disabled for the duration
so a second upload can't be started mid-request. The indicator clears and
returns to normal on both success and failure (including the `catch`
branch). Manually verify against a scanned/image-only PDF fixture (see
`backend/tests/` OCR fixtures from task 11) where the delay is actually
noticeable, not just a fast text-layer PDF.

**Out of scope**: a real page-by-page progress bar (the backend doesn't
currently report per-page progress to the client — that's a bigger,
separate change); changing OCR performance itself.

Done: `upload-pdf-btn` and `pdf-file-input` are disabled and a small
CSS spin animation (`.spinner` in `style.css`, next to the upload
button) shows for the duration of the `/api/extract-pdf` request, set
right before the `fetch` call and cleared in a `finally` block so it
resets on every exit path — the success path, a handled non-OK response,
and a thrown exception — not just the happy path. Deliberately kept
separate from task 21 (touches the same handler, but a different moment
— in-flight vs. just-landed — and needs different verification: an
actual slow OCR case here vs. an instant text-layer case there).

No backend changes. Verified live against a synthetic OCR-sourced PDF
(built with `test_ocr_extraction.py`'s own fixture helper, so the delay
is real, not simulated): confirmed both the button and file input are
disabled and the spinner visible partway through the request (checked
50ms after dispatch, before the response returns), and that both
re-enable and the spinner hides after completion — on the success path,
and separately on an error path (a corrupt, non-PDF file).

**Revisited** (user report, live use right after merge): the spinner
never actually hid — it was visible at rest, not just during an upload.
Root cause: `.spinner { display: inline-block; ... }` and the browser's
own UA-stylesheet rule `[hidden] { display: none }` have *equal* CSS
specificity (one class selector each), and author CSS wins a
specificity tie against UA styles — so `.spinner`'s own `display`
declaration silently overrode `hidden` every time, regardless of the
JS toggling `element.hidden`. This is exactly why the original
verification above didn't catch it: it checked `element.hidden` (the
DOM property/attribute, which *did* toggle correctly) but never checked
`getComputedStyle(element).display` (the actual rendered state, which
never left `"block"`) — attribute state and rendered state silently
diverged. Fixed with an explicit `.spinner[hidden] { display: none; }`
rule (two selectors = higher specificity than `.spinner` alone, so it
reliably wins). Re-verified with the correct check this time —
`getComputedStyle`, not just the attribute — confirming `none` at rest,
`block` mid-upload, `none` again after completion.

### 21. Visible "click Parse" cue after PDF/.txt upload

**Context**: User observation from live use, right after task 18 shipped.
Task 18 made the lab-reported interpretation panel render immediately on
PDF upload, in the same results area `renderAssessment()`'s "This tool's
interpretation" panel normally occupies after Parse. That created a new
problem: once that panel appears, the screen already has visible content
in the results area, so there's no obvious cue that a second, different
kind of information (this tool's own interpretation, including whether
anything matched the hematologic-malignancy reference table) hasn't been
generated yet and still needs an explicit Parse click. The same gap
exists for `.txt` upload (also non-auto-parsing since task 18), just
less visually deceptive there since the results area is simply empty
rather than looking complete.

**Done when**: after a PDF or `.txt` upload that loads parseable content
into the textarea, the results area shows an explicit, visible cue that
this tool's interpretation hasn't been generated yet and Parse needs to
be clicked — not just relying on the small `.upload-status` text near
the textarea.

**Out of scope**: auto-parsing on upload (already deliberately rejected
per tasks 8/18); a persistent/animated attention-grabber on the Parse
button itself — a static placeholder in the results area was judged
sufficient without extra motion/urgency.

Done: `renderPendingParsePlaceholder()` in `app.js` renders a dashed-
border card using the exact same `.assessment-panel` markup and "This
tool's interpretation" eyebrow label `renderAssessment()` uses for the
real thing — same slot, same label, so it reads as "this is where that
goes, not filled in yet" rather than a generic notice. Body text names
the concrete thing being deferred ("...including any hematologic-
malignancy reference flag") rather than a vague "click Parse." Called
right after content is loaded into the textarea in both the PDF handler
(after the lab-interpretation panel, so it appears directly below it)
and the `.txt` handler (guarded on the file having at least one non-
blank line). `runParse()` already fully clears and rebuilds `resultsEl`
on completion, so the placeholder is naturally replaced by the real
panel with no extra logic needed — verified live: exactly one
`.assessment-panel` and zero `.pending-parse` elements remain after
clicking Parse.

No backend changes; no new backend tests (frontend-only, consistent with
tasks 13/18's OCR-prefix and auto-parse fixes). Verified live end-to-end
in the browser for both upload paths.

### 19. CI workflow to run the test suite on every push/PR

**Context**: User noticed the "CI" section on a GitHub PR showed nothing
running, and the auto-merge checkbox couldn't be checked — there was no
CI workflow in the repo at all (no `.github/workflows/`), so there was
nothing to report a check. Test verification up to this point relied
entirely on running the suite locally before every PR and stating the
result in the PR body — real, but not independently verifiable by
GitHub itself.

**Done when**: a GitHub Actions workflow runs `backend/tests/`'s full
suite on every push to `main` and every pull request, including the OCR
tests, which need a real local Tesseract binary (no mocked fallback —
see `test_ocr_extraction.py`'s module docstring).

**Out of scope** (deferred, discussed but not requested this round):
enabling the repo's "Allow auto-merge" setting, and branch protection
requiring this check before merging into `main`. Without a required
check, auto-merge would just merge immediately (nothing to wait for) —
so this workflow existing is the prerequisite for either, not the whole
picture. Branch protection would also need care not to break the
existing convention of pushing `TASKS.md`-only edits straight to `main`
without a PR.

Done: `.github/workflows/tests.yml` — checks out the repo, sets up
Python 3.12, installs Tesseract via `apt-get` (the same OS-level,
non-pip dependency documented in `requirements.txt` and the README's
"Running it" section), installs `backend/requirements.txt`, and runs
`python3 -m unittest discover -s tests -v` from `backend/`. Triggers on
push to `main` and on every pull request, so both the OCR path and the
rest of the suite (94 tests total) run without relying on whoever's
merging to have run them locally first.

This workflow's first real run caught a genuine cross-environment bug
in `test_ocr_extraction.py`, not a bug in this project's own code: the
test fixture rendered its sample text with PIL's own bundled default
font, and real Tesseract — on *both* the CI runner's older build (5.3.4,
Ubuntu's apt package) and, once actually compared side by side, a newer
local build too (5.5.3, Homebrew/macOS) — misread that font's "4" glyph
as "A" (`"46,XY,"` → `"AG,XY,"` / `"A6,XY,"`), confirmed directly with a
temporary debug step printing the raw OCR output before diagnosing.
Switching to a real system font fixed it: `_load_test_font()` in
`test_ocr_extraction.py` now tries a short list of well-known TrueType
paths (DejaVu, Liberation, Arial) before falling back to PIL's default,
and the CI workflow installs `fonts-dejavu-core` alongside
`tesseract-ocr` so a real font is guaranteed present there. No font
binary vendored into the repo — every path tried is either an
OS-installable package or a common existing system font, consistent
with treating Tesseract itself as a declared OS-level dependency rather
than bundling a copy of it.

### 18. Consistent auto-parse behavior across input sources; show lab interpretation immediately on PDF upload

**Context**: User observation from live use — the four ways to get text
into the tool disagreed on whether loading it also ran Parse: pasting
(no auto-parse), the example dropdown (auto-parses), `.txt` upload
(auto-parsed), and PDF upload (no auto-parse, deliberately, per task 8).
Separately, the lab-reported interpretation panel (task 10) was only
rendered inside `runParse()`, so it stayed invisible until the user
clicked Parse even though it's extracted at upload time and has nothing
to do with what gets parsed.

**Done when**: one consistent rule replaces the four ad hoc behaviors —
anything loaded from outside the box (paste, `.txt` upload, PDF upload)
requires an explicit Parse click; anything chosen from inside the box
(the example dropdown) runs immediately, since choosing it *is* the
deliberate action. Separately, the lab-reported interpretation panel
renders as soon as PDF extraction finishes, independent of Parse.

**Out of scope**: changing the example dropdown's auto-parse behavior
(it's a deliberate "try this and see" affordance for curated content,
not an inconsistency to fix); auto-parsing on paste (would mean firing
requests mid-edit, a different and riskier problem than this task's
scope).

Done: removed `.txt` upload's `runParse()` call in `app.js` — it now
loads the file into the textarea and updates the status message
("...— review before parsing.") to match PDF's phrasing, same as every
other externally-sourced input. Both `.txt` and PDF upload now also
clear stale results from a previous document (`resultsEl.innerHTML =
''`) at the start of a new upload, so old parsed output can't be
mistaken for a reflection of newly-loaded, not-yet-parsed content.

For the lab interpretation panel: `renderLabInterpretationPanel()` is
now called directly in the `pdfFileInput` handler right after
`/api/extract-pdf` responds — before the "no candidates found" check, so
it shows (including the "none found" message, not just when one exists)
regardless of whether any candidate lines were detected. `runParse()`
still re-renders the same panel from the same `currentLabInterpretation`
value afterward, so the upload-time and parse-time renders never
disagree, and clicking Parse doesn't duplicate it (verified: exactly one
`.lab-interpretation-panel` in the DOM before and after Parse).

No backend changes, so no new backend tests (this suite doesn't cover
`app.js`, consistent with the OCR-prefix fix). Verified live end-to-end
in the browser: example dropdown still auto-parses; a `.txt` upload
loads text and stays unparsed until Parse is clicked, with `results`
empty in between; a real PDF upload (`Sample-Normal-POC-Cyto-Report.pdf`)
shows the "Lab-reported interpretation" panel immediately after
upload, before Parse; clicking Parse afterward shows exactly one copy of
that panel alongside the newly-parsed "This tool's interpretation"
results.

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

Done, with one deliberate deviation from the starting header list,
confirmed against the same real report used in tasks 13/16/17: its
"COMMENT" section is generic FDA/CLIA disclaimer boilerplate, not
case-specific interpretation. Treating "Comment" as a trigger header
would have mislabeled that boilerplate as "the lab's interpretation" —
actively misleading, worse than finding nothing — so it's left out as a
*header*, used instead (along with "Signature", "Results", "Cultures",
"Karyotypes", "FISH Images", "CPT Codes" — all real section names from
that report) as a *terminator*: extraction stops there. A generic "any
all-caps line stops extraction" rule (reusing task 17's
`_looks_like_section_boundary()`) doesn't work for this — a genuine
sub-heading *inside* the interpretation ("OVERALL INTERPRETATION" itself,
confirmed present in that report) is also all-uppercase, so that rule
would cut extraction off after just the header line. A small, specific
terminator list avoids that.

New `find_lab_interpretation()` in `iscn_parser.py`; `main.py`'s
`/api/extract-pdf` now scans the full document (all pages' text
concatenated, whichever source — text layer or OCR — each page used) and
returns `lab_interpretation` plus `lab_interpretation_used_ocr`. Real
extracted text is noisy across a page boundary (confirmed: page-2
header/footer content lands mid-section in the raw pypdf output) —
accepted as-is rather than cleaned up, consistent with this tool's
"never silently patch extracted text" rule; bounded by
`MAX_LAB_INTERPRETATION_LINES` (80) either way.

Frontend: the lab interpretation is captured at upload time but can only
be shown once the user parses (assessments are computed per parse), so
it's held client-side (`currentLabInterpretation`) and rendered once,
at the top of the results, above all batch "Input N of M" blocks — it's
whole-document information, not tied to one candidate line, so repeating
it per input would misrepresent the actual N:1 relationship between
batch entries and one PDF's interpretation. Every case-level assessment
panel (task 9) now carries an explicit "This tool's interpretation"
label, always (not just when a lab interpretation is also present), so
the pairing is predictable rather than appearing/disappearing based on
hidden state. Uploading a `.txt` file clears any prior PDF's
interpretation context; a fresh PDF upload replaces it; manual edits to
the textarea after a PDF upload do not clear it, since the comparison is
still about the same underlying source document.

11 new tests in `TestLabInterpretationExtraction` (90 total, all
passing), including the real report's actual interpretation section
(with its real page-boundary noise) as a byte-preserving regression
case, and an explicit check that a genuine in-section sub-heading doesn't
prematurely stop extraction. Verified live end-to-end with the real PDF
uploaded through the actual UI: both panels render, correctly labeled,
in the right order, with the full real interpretation text (noise and
all) captured — and confirmed the comparison persists across manual
textarea edits but clears on a `.txt` upload.

**Revisited** (user review, before merge — asked to see what criteria
the extraction used before signing off): checked a *second* real report
(a different lab/template — a products-of-conception cytogenetics
report), and both deliberate design choices above turned out not to
generalize:

1. Its `INTERPRETATION:` line has the actual interpretation text inline
   on the same line ("INTERPRETATION: Normal female karyotype without
   demonstrable abnormalities."), not on separate lines below a bare
   header the way Warde's report does. The old header regex required the
   header word alone on its own line and didn't match this at all — the
   feature found nothing, not even a truncated result.
2. Its `COMMENT:` section is genuine, case-specific content ("We cannot
   rule out the possibility that the cells analyzed... are of maternal
   origin"), immediately followed by a named reviewer — not generic
   disclaimer boilerplate like Warde's. Treating `COMMENT` as a
   terminator (the original call, correct for the one report it was
   checked against) would have silently cut this off.

Fixed both in `iscn_parser.py`: `LAB_INTERPRETATION_HEADER_RE` now
matches either the bare-header form or `header: inline content` on one
line (still requires an explicit colon for the inline form, so ordinary
prose starting with the word "interpretation" doesn't false-trigger);
`COMMENT` was removed from `LAB_INTERPRETATION_TERMINATOR_RE` entirely —
it's now captured like any other content, terminated only by the
remaining structural section names (`SIGNATURE`, `RESULTS`, `CULTURES`,
`KARYOTYPES`, `FISH IMAGES`, `CPT CODES`). Rationale: guessing which
lab's "COMMENT" convention applies to a given PDF isn't reliable from
the text alone, and silently dropping real content is a worse failure
mode than occasionally including boilerplate a human reviewing the panel
can plainly see and ignore themselves — "be inclusive, let the human
filter" rather than the tool guessing what's significant. More precise
inclusion/exclusion rules can follow later if a clearer signal turns up.

4 new tests added (94 total, all passing): the inline-header form, a
sanity check that bare colon-less prose doesn't false-trigger, `COMMENT`
content now being captured rather than dropped, and a byte-preserving
regression case using the second real report's actual extracted text
(including the "Reviewed By:" line and named reviewer, now captured).
The original real-report regression test was extended through the real
`SIGNATURE` terminator to confirm the `COMMENT` paragraph is now
included but extraction still correctly stops before `RESULTS`.
Re-verified live end-to-end against both real PDFs through the actual
UI.

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

Done: chose `pytesseract` (thin wrapper around a local Tesseract binary)
as anticipated — Tesseract itself is an OS-level install
(`brew install tesseract` / `apt-get install tesseract-ocr`), documented
in `requirements.txt`, the README's "Running it", and the endpoint's own
error message when it's missing. Page images come from `pypdf`'s
`page.images` (no separate rasterization library like `pdf2image`/poppler
needed — a scanned PDF's page content *is* typically one embedded raster
image, and `pypdf` already exposes it) — a nice side-effect of not having
switched PDF libraries for this task. Routing is per-page in `main.py`
(`_extract_page_candidates()`): under `MIN_TEXT_LAYER_CHARS` (10) of
extracted text, a page is treated as image-only and OCR'd instead.

Along the way, found (by actually running real OCR against a rendered
image, not assuming) that Tesseract routinely inserts a stray space after
a comma that a text-layer PDF never would — loosened the shared
`CANDIDATE_LINE_RE` in `iscn_parser.py` to tolerate it, benefiting both
extraction paths, not just OCR's.

OCR-sourced candidates are prefixed with `# OCR — verify against
original:` right in the textarea (not just a separate status message) —
not valid ISCN syntax, so an unedited OCR line always comes back marked
"Needs review" if parsed as-is. Verified live that this doesn't
necessarily blank out every downstream finding (comma-split tokens after
the mangled prefix can still parse independently) — that's fine; the
requirement was visible labeling before review, not a guarantee that
parsing fails outright.

Tests: `test_ocr_extraction.py` (3 tests, needs a real local Tesseract
install — no mocked fallback, since without it there's nothing to test)
builds an image-only PDF entirely in-code (PIL-rendered bitmap embedded
as a JPEG XObject, no text operators) and covers OCR recovering a
karyotype string, a scanned report with none, and confirming a normal
text-layer PDF still takes the text path rather than OCR. Plus 2 new
tests in `TestCandidateLineDetection` for the comma-space tolerance.
Verified end-to-end live in the browser: a real scanned-style PDF
(canvas-rendered, JPEG-embedded) uploaded through the actual UI,
confirming the OCR-labeled candidate, the status message's source
breakdown, the zero-candidate case, and the "Needs review" behavior on an
unedited OCR line. Later re-verified after tasks 16/17 landed, using an
actual 300 DPI rasterization of a real report run through real Tesseract
OCR (not synthetic) — see task 17, which that testing directly prompted.

**Revisited** (user review, after testing this live against a real
scanned report): the `# OCR — verify against original:` prefix turned
out to actively prevent parsing rather than just flag for review — a
user who reviewed an OCR line, confirmed it correct, and clicked Parse
without editing still hit a guaranteed error, because the prefix itself
isn't valid ISCN syntax. That's a stricter cost than "needs more
scrutiny" was meant to impose. Fixed in `app.js`: the textarea now always
holds the plain, unmodified extracted text (what a user would type or
paste themselves); OCR provenance is instead surfaced in a separate
`#ocr-review-panel`, listing each OCR-sourced line with a "verify against
the original" caution, visible but outside the parseable input. Same
underlying goal (OCR needs more scrutiny, visibly), different mechanism
(a warning alongside the input, not a mutation of it).

### 17. Stop OCR continuation folding from swallowing unrelated report sections

**Context**: Follow-up from testing PR #8 (task 11, OCR fallback) with an
actual scanned PDF, rather than a synthetic one — a 300 DPI rasterization
of the real report used in tasks 13/16, re-embedded as a genuine
image-only PDF (no text layer) and run through real Tesseract OCR.
Task 16's continuation logic (folding subsequent lines into a candidate
that looks structurally incomplete) works well against clean text-layer
extraction, but real OCR output includes real character-level misreads —
in this case, Tesseract garbled one closing `)` entirely, permanently
unbalancing the paren-count signal task 16 relies on to know when to
stop. Confirmed directly: running task 16's actual logic against the
real OCR text never resolved "complete," ran to the 15-line safety cap,
and folded in the report's `CULTURES` section header and its disclaimer
footer — a worse outcome than task 16's fix was meant to prevent, not a
neutral one.

**Done when**: a candidate stops folding in more lines the moment the
next line looks like a standalone report section header, independent of
what the paren-balance signal says — verified against the real OCR text
that exposed this.

**Out of scope**: any attempt to correct or interpret the OCR
misread itself (the dropped `)`) — this task is only about where folding
stops, not about repairing corrupted content, consistent with this
tool's standing rule against auto-correcting extracted text.

Done: `_looks_like_section_boundary()` in `iscn_parser.py` — a line that,
stripped, is non-empty, contains no digits, and is entirely uppercase
(e.g. `CULTURES`, `COMMENT`, `SIGNATURE` — a real, recurring pattern
across this exact report's own sections) is specific enough to never
collide with actual ISCN content, which always mixes in numbers (locus
bands, copy counts, cell counts). The continuation loop in
`find_candidate_iscn_lines()` now also stops before folding in a line
matching this, regardless of the paren-balance/trailing-comma/`ish`
signals from task 16. Verified against the exact real OCR text
(hardcoded in a test): folding now stops cleanly right before
`CULTURES`, capturing the complete (still OCR-garbled, but bounded and
complete) FISH panel rather than either the original one-line truncation
or the section-swallowing regression this task fixes. 3 new tests (79
total, all passing): the real OCR text case, a minimal deterministic
case isolating just the mechanism, and confirmed against all of task
16's existing tests with no regressions.

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
