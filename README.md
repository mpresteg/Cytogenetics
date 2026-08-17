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

Then open **http://127.0.0.1:8000** in a browser. Try the example dropdown,
or paste a string like:

```
46,XX,t(9;22)(q34;q11.2)
47,XY,+21[20]/46,XY[5]
nuc ish(D13S319x1,LAMP1x2)
ish t(9;22)(q34;q11.2)(ABL1+,BCR+)
```

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
  `dup`, `inv`, `add`) are checked against a small reference table of
  approximate terminal band numbers for commonly-rearranged chromosomes, and
  against ISCN's proximal-then-distal breakpoint ordering convention. Both
  checks only ever produce a *warning*, never a hard error, and the reference
  table is explicitly labeled as approximate — see the disclaimer in
  `iscn_parser.py` (`APPROX_TERMINAL_BANDS`).

**FISH:**
- `nuc ish(...)` and `ish(...)` (standalone or attached to a karyotype
  rearrangement like `ish t(9;22)(...)(ABL1+,BCR+)`)
- Probe results: presence/absence (`ABL1+`, `BCR-`), copy number (`D21S259x3`),
  fusion (`ABL1 con BCR`)
- **Reference notes:** a small, non-exhaustive lookup table (`PROBE_KNOWLEDGE`,
  `FUSION_KNOWLEDGE` in `iscn_parser.py`) attaches a short clinical-context
  note to well-known probes/fusions (e.g. BCR-ABL1 → CML/ALL, IGH-BCL2 →
  follicular lymphoma). Every such note is explicitly labeled "reference
  note, not diagnostic" in the output — this is a starting scaffold, not a
  validated knowledge base.

**ISCN edition awareness (scaffold):** the API and UI accept an `edition`
parameter (2016 / 2020 / 2024, default 2024). This does **not** fully model
edition-by-edition grammar differences yet — that requires a domain expert
working from the actual ISCN volumes for each edition. What's implemented is
the plumbing plus one illustrative example (`der()` vs `rob()` for
Robertsonian translocations) to show where a real edition-difference table
would plug in. See `EDITION_NOTES` in `iscn_parser.py`.

Anything outside all of the above grammar is returned as
`category: "unrecognized"` with an explicit warning — it's never silently
mis-parsed or dropped. This matters a lot for a clinical-adjacent tool: false
confidence is worse than an honest "I don't understand this token."

## Testing

`backend/tests/test_iscn_parser.py` — 31 tests, stdlib `unittest` (zero
dependencies, so it's runnable without `pip install` anything), also
pytest-discoverable if that's your preferred runner.

```bash
cd backend
python3 -m unittest tests.test_iscn_parser -v
# or, if you have pytest installed:
pytest tests/ -v
```

Covers: normal karyotypes, numerical abnormalities and the modal-number
consistency check, every structural token type, `der()` decomposition (both
forms) and its `rob()` suggestion, mosaicism with cell counts, FISH probe
parsing (copy number / presence-absence / fusion) and the knowledge-base
notes, unrecognized-token handling, and the edition parameter. All 31 pass
as of this build — I ran them in the sandbox this was built in, they're not
just claimed to pass.

## What I'd extend next

Now that the items below are done, here's what's next in line:

1. **Deeper `der()` grammar.** The decomposition handles the common cases
   (single embedded rearrangement, whole-arm/Robertsonian form) but not
   multi-step der() chains with several sequential events, or der()
   describing a chromosome built from three or more source chromosomes.

2. **Grow the band reference table and the probe knowledge table.** Both are
   deliberately small scaffolds right now (a dozen chromosomes, a dozen
   probes). Expanding either is low-risk, additive work — just more entries
   in a dict — and pytest cases should be added alongside each addition.

3. **Real ISCN edition differences.** The scaffold is wired up; what's
   missing is a domain expert (or careful sourcing from the actual ISCN
   text) working through what changed release-to-release and encoding those
   as additional `EDITION_NOTES` / pattern-level flags.

4. **Export / report generation.** A "copy interpretation as text" or
   "export as PDF" button would make this usable in an actual reporting
   workflow rather than just an exploratory tool.

5. **Multi-string / batch mode.** Cytogenetics reports often list several
   ISCN strings (one per specimen or per analysis). A textarea that accepts
   one-per-line and shows results in sequence would be a quick, high-value UI
   addition.
