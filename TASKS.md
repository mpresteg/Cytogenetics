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

---

## In progress

*(none)*

## Done

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
