"""
fhir_export.py

Task 25, stage 1: export a parsed report as FHIR JSON shaped to mCODE's
Genomic Variant / Genomics Report profiles, entirely locally — no
persistence, no network call. See TASKS.md task 25 for the full
rationale on targeting mCODE over CIBMTR's own (comparatively stale,
unconfirmed-in-production) Cytogenetics profile.

Two independent pieces live here:

1. `extract_subject_candidates()` — a PDF-text scan for labeled
   subject/demographic fields (patient name, DOB, specimen ID,
   collection/report date), in the same spirit as
   `find_candidate_iscn_lines()` / `find_lab_interpretation()` in
   iscn_parser.py: a small, structural, label-based pattern set,
   returned as unmodified candidate text for the user to review, never
   trusted or auto-applied.

2. `build_mcode_export()` — turns an already-parsed result (the dict
   `parse_iscn()` returns) plus reviewed/confirmed subject fields into a
   FHIR `Bundle`. Raises `FhirExportError` if any clone was flagged by
   this tool's own validation (errors, or an unrecognized-token finding)
   and the caller hasn't set `override=True` — this tool's validation is
   a pre-export QC gate, not something bypassed silently.

Verified this session against the actual published `StructureDefinition`
pages (not just guessed from memory):
  - mCODE's Genomics Report Profile is `DiagnosticReport`-based, derives
    from the HL7 Genomics Reporting IG's own `genomics-report` profile,
    fixes `category` to Genetics (`http://terminology.hl7.org/CodeSystem/
    v2-0074`, code `GE`), and carries child variant observations via
    `result` (a plain array of `Observation` references — the standard
    FHIR "report wraps its result observations" pattern).
  - mCODE's Genomic Variant Profile is `Observation`-based, fixes `code`
    to LOINC 69548-6 ("Genetic variant assessment") and `category` to
    "laboratory", and defines a `cytogenomic-nomenclature` component at
    LOINC 81291-7 — the same code CIBMTR's own real example used for its
    "Variant ISCN" component. That match is reassuring, not
    coincidental: 81291-7 is standard genomics LOINC vocabulary, not a
    CIBMTR invention, so reusing it here is correct under mCODE too.

NOT independently verified this session, and called out below via
`caveats` in the returned dict rather than asserted as fact:
  - The exact LOINC answer-list codes for `Observation.method` (bound to
    answer list LL4048-6) — e.g. the correct coded value for
    "karyotyping" specifically. Populated as free text only.
  - Whether "Genomic source class" (LOINC 48002-0, valued `LA6684-0`
    "Somatic") is an officially defined component slice on mCODE's
    Genomic Variant profile, as opposed to vocabulary CIBMTR's own
    (looser) profile happened to reuse. Included anyway, since it's
    real, standard LOINC vocabulary and near-universally true for a
    cytogenetics finding (see MALIGNANCY_KNOWLEDGE's own note style:
    flagged as a caveat, not silently asserted as spec-confirmed).
  - `DiagnosticReport.code` and `Observation.method` are populated as
    text-only `CodeableConcept`s (no asserted coding) for the same
    "don't guess a code" reason — mCODE's binding for `code` is
    "preferred," not a fixed required code, so this satisfies the
    element's cardinality without fabricating a LOINC value.
"""

import re
import uuid
from typing import Any, Dict, List, Optional

LOINC = "http://loinc.org"
ISCN_SYSTEM = "https://iscn.karger.com"
OBSERVATION_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
V2_0074_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0074"

MCODE_GENOMIC_VARIANT_PROFILE = "http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-genomic-variant"
MCODE_GENOMICS_REPORT_PROFILE = "http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-genomics-report"


class FhirExportError(Exception):
    """Raised when an export can't proceed as requested — either nothing
    to export, or a clone this tool itself flagged (errors, or an
    unrecognized-token finding) without an explicit override."""


# ---------------------------------------------------------------------------
# Subject/demographic candidate extraction (PDF text)
# ---------------------------------------------------------------------------
#
# Deliberately narrower than find_lab_interpretation()'s label matching:
# these values get exported into a clinical-shaped FHIR resource once
# confirmed, so a false-positive match here is a materially bigger deal
# than one in the karyotype-candidate or interpretation scanners (which
# only ever populate a review textarea). Each pattern requires the
# specific label at the start of a line, immediately followed by a
# colon and the value on the same line — "Physician Name:", "Ordering
# Facility:", etc. are deliberately NOT matched by the patient-name
# pattern, even though a looser "name" pattern would catch them too.
#
# Like every other PDF-derived value in this tool, a match here is a
# *candidate* — returned as unmodified text for the frontend to show for
# explicit review/edit/confirmation, never applied to an export directly.

_SUBJECT_FIELD_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "patient_name": re.compile(
        r'^\s*patient(?:\s*name)?\s*:\s*(\S.*)$', re.IGNORECASE | re.MULTILINE),
    "date_of_birth": re.compile(
        r'^\s*(?:date\s+of\s+birth|dob)\s*:\s*(\S.*)$', re.IGNORECASE | re.MULTILINE),
    "specimen_id": re.compile(
        r'^\s*(?:specimen(?:\s*id)?|accession(?:\s*(?:#|no\.?|number))?)\s*:\s*(\S.*)$',
        re.IGNORECASE | re.MULTILINE),
    "collection_date": re.compile(
        r'^\s*(?:collection\s+date|date\s+collected|specimen\s+collected)\s*:\s*(\S.*)$',
        re.IGNORECASE | re.MULTILINE),
    "report_date": re.compile(
        r'^\s*(?:report\s+date|date\s+reported)\s*:\s*(\S.*)$', re.IGNORECASE | re.MULTILINE),
}


def extract_subject_candidates(text: str) -> Dict[str, Optional[str]]:
    """Scans `text` (a full document's extracted/OCR'd text) for a small,
    fixed set of labeled subject/demographic fields. Returns a dict with
    exactly the keys in `_SUBJECT_FIELD_PATTERNS`, each either the
    matched line's value (raw, unmodified, first match only) or None if
    that label wasn't found. Never raises on no-match — a missing field
    just means the frontend leaves that input blank, same as
    typed/pasted input with no PDF at all."""
    result: Dict[str, Optional[str]] = {}
    for field, pattern in _SUBJECT_FIELD_PATTERNS.items():
        m = pattern.search(text)
        result[field] = m.group(1).strip() if m else None
    return result


# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------
#
# The frontend uses <input type="date"> for every date field, which only
# ever submits a well-formed ISO date (YYYY-MM-DD) or an empty string —
# so by the time a date reaches build_mcode_export() below, it should
# already be unambiguous. normalize_date() exists for two reasons: (1)
# best-effort pre-filling of those <input type="date"> fields from a raw
# PDF-extracted candidate string, which is NOT yet unambiguous (e.g.
# "03/04/1975"), and (2) defense in depth if this endpoint is ever called
# directly rather than through the browser form. It intentionally
# recognizes only ISO and unambiguous-enough US slash/dash formats
# (assuming MM/DD/YYYY, the convention every real report seen so far has
# used) — anything else is left for the human to type in directly rather
# than guessed at, consistent with this tool's general "don't guess"
# rule for anything downstream of raw extracted text.

_ISO_DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_US_SLASHDASH_DATE_RE = re.compile(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$')


def normalize_date(raw: Optional[str]) -> Optional[str]:
    """Best-effort conversion of a free-text date candidate to ISO
    YYYY-MM-DD. Returns None (never a guess) if `raw` isn't in a
    recognized, unambiguous-enough format."""
    if not raw:
        return None
    raw = raw.strip()
    if _ISO_DATE_RE.match(raw):
        return raw
    m = _US_SLASHDASH_DATE_RE.match(raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"
    return None


def _valid_iso_date(raw: Optional[str]) -> Optional[str]:
    """Strict check used at export time: only a literal YYYY-MM-DD
    string is accepted (what <input type="date"> submits); anything else
    is dropped rather than reinterpreted, per normalize_date()'s doc
    above."""
    if raw and _ISO_DATE_RE.match(raw.strip()):
        return raw.strip()
    return None


# ---------------------------------------------------------------------------
# FHIR bundle construction
# ---------------------------------------------------------------------------

def _urn() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def _entry(full_url: str, resource: Dict[str, Any]) -> Dict[str, Any]:
    resource = dict(resource)
    resource["id"] = full_url.split(":")[-1]
    return {"fullUrl": full_url, "resource": resource}


def _clone_method_text(clone: Dict[str, Any]) -> str:
    if clone.get("fish_only"):
        return "FISH (fluorescence in situ hybridization)"
    if clone.get("fish_cell_count") is not None:
        return "Karyotyping (chromosome analysis) and FISH"
    return "Karyotyping (chromosome analysis)"


def _clone_blocking_issues(clone: Dict[str, Any]) -> List[str]:
    """What this tool's own validation already found for one clone —
    parse errors, plus any finding it couldn't recognize at all. Mirrors
    exactly what the frontend already labels "Needs review" on a
    clone-card (see renderClones() in app.js), so the export gate and
    the on-screen status badge never disagree."""
    issues = list(clone.get("errors") or [])
    unrecognized = [f["raw"] for f in clone.get("findings", []) if f.get("category") == "unrecognized"]
    if unrecognized:
        issues.append("Unrecognized token(s): " + ", ".join(unrecognized))
    return issues


def build_mcode_export(
    parsed: Dict[str, Any],
    subject_fields: Optional[Dict[str, Optional[str]]] = None,
    override: bool = False,
) -> Dict[str, Any]:
    """Builds an mCODE-shaped FHIR `Bundle` from a `parse_iscn()` result.

    Returns {"bundle": <FHIR Bundle dict>, "caveats": [<str>, ...]} — the
    caveats are stage-1 honesty notes (see this module's docstring),
    meant to be surfaced to the user alongside the JSON, not swallowed.

    Raises FhirExportError if there's nothing to export, or if any clone
    was flagged by this tool's own validation and `override` isn't set —
    this tool's validation is a pre-export QC gate (task 25's "Done
    when"), not bypassed silently.
    """
    subject_fields = subject_fields or {}
    clones = parsed.get("clones") or []
    if not clones:
        raise FhirExportError("Nothing to export — no clones were parsed from this input.")

    if not override:
        blocked = []
        for idx, clone in enumerate(clones):
            issues = _clone_blocking_issues(clone)
            if issues:
                blocked.append(f"clone {idx + 1} ({clone.get('raw', '')!r}): {'; '.join(issues)}")
        if blocked:
            raise FhirExportError(
                "This tool's own validation flagged one or more clones — export blocked "
                "without an explicit override: " + " | ".join(blocked)
            )

    caveats: List[str] = list(_MODULE_CAVEATS)
    entries: List[Dict[str, Any]] = []

    patient_ref = None
    patient_name = (subject_fields.get("patient_name") or "").strip()
    dob = _valid_iso_date(subject_fields.get("date_of_birth"))
    if subject_fields.get("date_of_birth") and not dob:
        caveats.append(f"date_of_birth {subject_fields['date_of_birth']!r} wasn't a valid "
                        f"YYYY-MM-DD date — omitted from the export.")
    if patient_name or dob:
        patient_url = _urn()
        patient: Dict[str, Any] = {"resourceType": "Patient"}
        if patient_name:
            patient["name"] = [{"text": patient_name}]
        if dob:
            patient["birthDate"] = dob
        entries.append(_entry(patient_url, patient))
        patient_ref = {"reference": patient_url}

    specimen_ref = None
    specimen_id = (subject_fields.get("specimen_id") or "").strip()
    collection_date = _valid_iso_date(subject_fields.get("collection_date"))
    if subject_fields.get("collection_date") and not collection_date:
        caveats.append(f"collection_date {subject_fields['collection_date']!r} wasn't a valid "
                        f"YYYY-MM-DD date — omitted from the export.")
    if specimen_id or collection_date:
        specimen_url = _urn()
        specimen: Dict[str, Any] = {"resourceType": "Specimen"}
        if specimen_id:
            specimen["identifier"] = [{"value": specimen_id}]
        if collection_date:
            specimen["collection"] = {"collectedDateTime": collection_date}
        entries.append(_entry(specimen_url, specimen))
        specimen_ref = {"reference": specimen_url}

    report_date = _valid_iso_date(subject_fields.get("report_date"))
    if subject_fields.get("report_date") and not report_date:
        caveats.append(f"report_date {subject_fields['report_date']!r} wasn't a valid "
                        f"YYYY-MM-DD date — omitted from the export.")

    result_refs: List[Dict[str, str]] = []
    for clone in clones:
        obs_url = _urn()
        observation: Dict[str, Any] = {
            "resourceType": "Observation",
            "meta": {"profile": [MCODE_GENOMIC_VARIANT_PROFILE]},
            "status": "final",
            "category": [{"coding": [{"system": OBSERVATION_CATEGORY_SYSTEM,
                                       "code": "laboratory", "display": "Laboratory"}]}],
            "code": {"coding": [{"system": LOINC, "code": "69548-6",
                                  "display": "Genetic variant assessment"}]},
            "method": {"text": _clone_method_text(clone)},
            "component": [
                {
                    "code": {"coding": [{"system": LOINC, "code": "81291-7",
                                          "display": "Cytogenomic nomenclature"}]},
                    "valueCodeableConcept": {"coding": [{"system": ISCN_SYSTEM,
                                                          "code": clone.get("raw", "")}]},
                },
                {
                    "code": {"coding": [{"system": LOINC, "code": "48002-0",
                                          "display": "Genomic source class"}]},
                    "valueCodeableConcept": {"coding": [{"system": LOINC, "code": "LA6684-0",
                                                          "display": "Somatic"}]},
                },
            ],
        }
        if patient_ref:
            observation["subject"] = patient_ref
        if collection_date:
            observation["effectiveDateTime"] = collection_date
        entries.append(_entry(obs_url, observation))
        result_refs.append({"reference": obs_url})

    assessment = parsed.get("assessment") or {}
    report_url = _urn()
    report: Dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "meta": {"profile": [MCODE_GENOMICS_REPORT_PROFILE]},
        "status": "final",
        "category": [{"coding": [{"system": V2_0074_SYSTEM, "code": "GE", "display": "Genetics"}]}],
        "code": {"text": "Cytogenetic analysis"},
        "result": result_refs,
    }
    if patient_ref:
        report["subject"] = patient_ref
    if specimen_ref:
        report["specimen"] = [specimen_ref]
    if collection_date:
        report["effectiveDateTime"] = collection_date
    if report_date:
        report["issued"] = f"{report_date}T00:00:00Z"
    if assessment.get("summary"):
        report["conclusion"] = assessment["summary"]
    entries.insert(0, _entry(report_url, report))

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries,
    }
    return {"bundle": bundle, "caveats": caveats}


# Always-present caveats — not conditional on any particular input, just
# the honest state of this stage-1 implementation (see module docstring).
_MODULE_CAVEATS = [
    "Stage-1 prototype export: DiagnosticReport.code and Observation.method are free text "
    "(no LOINC code asserted) — not verified against mCODE's exact preferred coding this session.",
    "The 'Genomic source class' component (LOINC 48002-0 = Somatic) is standard genomics LOINC "
    "vocabulary, reused from CIBMTR's own published example — its presence as an official mCODE "
    "Genomic Variant component slice was not independently confirmed this session.",
]
