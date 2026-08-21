"""
tests/test_fhir_export.py

Covers task 25 (stage 1): mCODE-shaped FHIR export. Like
test_iscn_parser.py, tests the pure functions directly (stdlib
unittest, zero dependencies) rather than going through FastAPI's
TestClient — HTTP-layer wiring (the actual /api/export-fhir route) is
verified by hand in the browser, matching how this repo has always
treated the FastAPI layer (see test_pdf_extraction.py's docstring).

Run directly with:
    python3 -m unittest tests.test_fhir_export -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fhir_export import (  # noqa: E402
    build_mcode_export,
    extract_subject_candidates,
    normalize_date,
    FhirExportError,
    MCODE_GENOMIC_VARIANT_PROFILE,
    MCODE_GENOMICS_REPORT_PROFILE,
    _valid_iso_date,
)
from iscn_parser import parse_iscn  # noqa: E402


def find_resource(bundle, resource_type):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == resource_type]


class TestSubjectCandidateExtraction(unittest.TestCase):
    def test_finds_all_labeled_fields(self):
        text = (
            "PATIENT: Jane Doe\n"
            "DOB: 03/04/1975\n"
            "Specimen ID: S24-00123\n"
            "Collection Date: 01/02/2024\n"
            "Report Date: 01/10/2024\n"
        )
        c = extract_subject_candidates(text)
        self.assertEqual(c["patient_name"], "Jane Doe")
        self.assertEqual(c["date_of_birth"], "03/04/1975")
        self.assertEqual(c["specimen_id"], "S24-00123")
        self.assertEqual(c["collection_date"], "01/02/2024")
        self.assertEqual(c["report_date"], "01/10/2024")

    def test_missing_fields_are_none(self):
        c = extract_subject_candidates("Nothing relevant here.\nJust some prose.\n")
        for v in c.values():
            self.assertIsNone(v)

    def test_alternate_labels(self):
        text = (
            "Date of Birth: 1980-05-06\n"
            "Accession Number: ACC-9\n"
            "Date Collected: 2024-02-02\n"
            "Date Reported: 2024-02-09\n"
        )
        c = extract_subject_candidates(text)
        self.assertEqual(c["date_of_birth"], "1980-05-06")
        self.assertEqual(c["specimen_id"], "ACC-9")
        self.assertEqual(c["collection_date"], "2024-02-02")
        self.assertEqual(c["report_date"], "2024-02-09")

    def test_does_not_match_unrelated_labels(self):
        # "Physician Name:" and "Ordering Facility:" should not be
        # mistaken for the patient's own name/specimen fields.
        text = "Physician Name: Dr. Smith\nOrdering Facility: Example Lab\n"
        c = extract_subject_candidates(text)
        self.assertIsNone(c["patient_name"])
        self.assertIsNone(c["specimen_id"])

    def test_reversed_value_before_label_real_report_fragments(self):
        # Confirmed real extract_text() fragments from task 22's report
        # (Diagnostic Cytogenetics Incorporated's template) -- this
        # report-generation software glues the value immediately before
        # its own label with zero separator throughout its whole text
        # layer, not just on the karyotype line task 22 originally fixed.
        text = "XX-XXXXCust. Specimen ID:\n11/08/2016Collection Date:\n"
        c = extract_subject_candidates(text)
        self.assertEqual(c["specimen_id"], "XX-XXXX")
        self.assertEqual(c["collection_date"], "11/08/2016")

    def test_reversed_date_before_label_all_date_fields(self):
        text = (
            "03/04/1975DOB:\n"
            "01/02/2024Collection Date:\n"
            "01/10/2024Report Date:\n"
        )
        c = extract_subject_candidates(text)
        self.assertEqual(c["date_of_birth"], "03/04/1975")
        self.assertEqual(c["collection_date"], "01/02/2024")
        self.assertEqual(c["report_date"], "01/10/2024")

    def test_reversed_name_before_label(self):
        c = extract_subject_candidates("John SmithPatient:\n")
        self.assertEqual(c["patient_name"], "John Smith")
        c2 = extract_subject_candidates("Jane Q DoePatient Name:\n")
        self.assertEqual(c2["patient_name"], "Jane Q Doe")

    def test_reversed_accession_before_label(self):
        c = extract_subject_candidates("ACC-42Accession Number:\n")
        self.assertEqual(c["specimen_id"], "ACC-42")

    def test_forward_pattern_still_preferred_when_both_present(self):
        # If a document happens to contain both a normal "Label: value"
        # line and something that could coincidentally look like the
        # reversed form elsewhere, the straightforward forward match (the
        # more common convention) should win since it's tried first.
        text = "Specimen ID: S24-00123\n"
        c = extract_subject_candidates(text)
        self.assertEqual(c["specimen_id"], "S24-00123")


class TestDateNormalization(unittest.TestCase):
    def test_iso_passthrough(self):
        self.assertEqual(normalize_date("2024-01-02"), "2024-01-02")

    def test_us_slash_format(self):
        self.assertEqual(normalize_date("3/4/1975"), "1975-03-04")
        self.assertEqual(normalize_date("03/04/1975"), "1975-03-04")

    def test_us_dash_format(self):
        self.assertEqual(normalize_date("03-04-1975"), "1975-03-04")

    def test_unrecognized_format_returns_none(self):
        self.assertIsNone(normalize_date("March 4th, 1975"))
        self.assertIsNone(normalize_date("not a date"))

    def test_none_and_empty(self):
        self.assertIsNone(normalize_date(None))
        self.assertIsNone(normalize_date(""))

    def test_out_of_range_month_rejected(self):
        # 13/04/1975 isn't a valid MM/DD/YYYY date under the assumed
        # convention -- don't guess a swapped day/month.
        self.assertIsNone(normalize_date("13/04/1975"))


class TestValidIsoDate(unittest.TestCase):
    """_valid_iso_date() is the strict export-time check -- documented as
    a defense-in-depth guard for direct API callers (bypassing the
    browser's own <input type="date">), so it needs to reject a
    syntactically-shaped but nonexistent date, not just check the regex
    pattern."""

    def test_real_date_accepted(self):
        self.assertEqual(_valid_iso_date("2024-01-02"), "2024-01-02")

    def test_nonexistent_day_rejected(self):
        self.assertIsNone(_valid_iso_date("2024-02-30"))  # Feb never has 30 days

    def test_nonexistent_month_rejected(self):
        self.assertIsNone(_valid_iso_date("2024-13-01"))

    def test_malformed_string_rejected(self):
        self.assertIsNone(_valid_iso_date("not-a-date"))

    def test_none_and_empty(self):
        self.assertIsNone(_valid_iso_date(None))
        self.assertIsNone(_valid_iso_date(""))


class TestMcodeExportShape(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_iscn("47,XY,+8[10]/46,XY[10]")

    def test_bundle_has_report_and_observations(self):
        result = build_mcode_export(self.parsed, {})
        bundle = result["bundle"]
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "collection")
        reports = find_resource(bundle, "DiagnosticReport")
        observations = find_resource(bundle, "Observation")
        self.assertEqual(len(reports), 1)
        self.assertEqual(len(observations), 2)  # one clone-mosaic, two clones
        self.assertEqual(reports[0]["meta"]["profile"], [MCODE_GENOMICS_REPORT_PROFILE])
        for obs in observations:
            self.assertEqual(obs["meta"]["profile"], [MCODE_GENOMIC_VARIANT_PROFILE])

    def test_report_result_references_every_observation(self):
        result = build_mcode_export(self.parsed, {})
        bundle = result["bundle"]
        report = find_resource(bundle, "DiagnosticReport")[0]
        obs_urls = {e["fullUrl"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"}
        result_refs = {r["reference"] for r in report["result"]}
        self.assertEqual(obs_urls, result_refs)

    def test_iscn_component_carries_raw_clone_string(self):
        result = build_mcode_export(self.parsed, {})
        bundle = result["bundle"]
        observations = find_resource(bundle, "Observation")
        raws = set()
        for obs in observations:
            iscn_component = next(
                c for c in obs["component"]
                if c["code"]["coding"][0]["code"] == "81291-7"
            )
            raws.add(iscn_component["valueCodeableConcept"]["coding"][0]["code"])
        self.assertEqual(raws, {"47,XY,+8[10]", "46,XY[10]"})

    def test_genomic_source_class_is_somatic(self):
        result = build_mcode_export(self.parsed, {})
        obs = find_resource(result["bundle"], "Observation")[0]
        source_class = next(
            c for c in obs["component"] if c["code"]["coding"][0]["code"] == "48002-0"
        )
        self.assertEqual(source_class["valueCodeableConcept"]["coding"][0]["code"], "LA6684-0")

    def test_no_subject_fields_means_no_patient_or_specimen(self):
        result = build_mcode_export(self.parsed, {})
        bundle = result["bundle"]
        self.assertEqual(find_resource(bundle, "Patient"), [])
        self.assertEqual(find_resource(bundle, "Specimen"), [])
        report = find_resource(bundle, "DiagnosticReport")[0]
        self.assertNotIn("subject", report)

    def test_subject_fields_populate_patient_and_are_referenced(self):
        subject = {
            "patient_name": "Jane Doe",
            "date_of_birth": "1975-03-04",
            "specimen_id": "S24-00123",
            "collection_date": "2024-01-02",
            "report_date": "2024-01-10",
        }
        result = build_mcode_export(self.parsed, subject)
        bundle = result["bundle"]
        patients = find_resource(bundle, "Patient")
        specimens = find_resource(bundle, "Specimen")
        self.assertEqual(len(patients), 1)
        self.assertEqual(patients[0]["name"], [{"text": "Jane Doe"}])
        self.assertEqual(patients[0]["birthDate"], "1975-03-04")
        self.assertEqual(len(specimens), 1)
        self.assertEqual(specimens[0]["identifier"], [{"value": "S24-00123"}])

        report = find_resource(bundle, "DiagnosticReport")[0]
        patient_url = next(e["fullUrl"] for e in bundle["entry"] if e["resource"] is patients[0])
        specimen_url = next(e["fullUrl"] for e in bundle["entry"] if e["resource"] is specimens[0])
        self.assertEqual(report["subject"]["reference"], patient_url)
        self.assertEqual(report["specimen"][0]["reference"], specimen_url)
        self.assertEqual(report["issued"], "2024-01-10T00:00:00Z")

        for obs in find_resource(bundle, "Observation"):
            self.assertEqual(obs["subject"]["reference"], patient_url)
            self.assertEqual(obs["effectiveDateTime"], "2024-01-02")

    def test_invalid_date_is_omitted_with_caveat(self):
        result = build_mcode_export(self.parsed, {"date_of_birth": "not-a-date",
                                                    "patient_name": "Jane Doe"})
        bundle = result["bundle"]
        patient = find_resource(bundle, "Patient")[0]
        self.assertNotIn("birthDate", patient)
        self.assertTrue(any("date_of_birth" in c for c in result["caveats"]))

    def test_nonexistent_calendar_date_is_omitted_with_caveat(self):
        # A syntactically ISO-shaped but nonexistent date (Feb never has
        # 30 days) should be caught the same way as an unparseable one --
        # not just pattern-matched.
        result = build_mcode_export(self.parsed, {"date_of_birth": "2024-02-30",
                                                    "patient_name": "Jane Doe"})
        patient = find_resource(result["bundle"], "Patient")[0]
        self.assertNotIn("birthDate", patient)
        self.assertTrue(any("date_of_birth" in c for c in result["caveats"]))

    def test_issued_carries_a_placeholder_time_caveat(self):
        result = build_mcode_export(self.parsed, {"report_date": "2024-01-10"})
        report = find_resource(result["bundle"], "DiagnosticReport")[0]
        self.assertEqual(report["issued"], "2024-01-10T00:00:00Z")
        self.assertTrue(any("placeholder" in c and "issued" in c for c in result["caveats"]))

    def test_no_report_date_means_no_issued_caveat(self):
        result = build_mcode_export(self.parsed, {})
        self.assertFalse(any("issued" in c for c in result["caveats"]))

    def test_conclusion_carries_assessment_summary_when_flagged(self):
        parsed = parse_iscn("47,XY,+8[20]")
        result = build_mcode_export(parsed, {})
        report = find_resource(result["bundle"], "DiagnosticReport")[0]
        self.assertEqual(report.get("conclusion"), parsed["assessment"]["summary"])

    def test_method_reflects_fish_only_clone(self):
        parsed = parse_iscn("nuc ish(D21S259x3)")
        result = build_mcode_export(parsed, {})
        obs = find_resource(result["bundle"], "Observation")[0]
        self.assertIn("FISH", obs["method"]["text"])


class TestExportBlockedByValidation(unittest.TestCase):
    def test_unrecognized_token_blocks_export(self):
        parsed = parse_iscn("46,XY,zzz(1)(q10)")
        with self.assertRaises(FhirExportError):
            build_mcode_export(parsed, {})

    def test_override_allows_export_despite_unrecognized_token(self):
        parsed = parse_iscn("46,XY,zzz(1)(q10)")
        result = build_mcode_export(parsed, {}, override=True)
        self.assertEqual(len(find_resource(result["bundle"], "Observation")), 1)

    def test_clone_error_blocks_export(self):
        # An invalid modal number is a real, existing parser error (not
        # an unrecognized-token case), so this exercises the `errors`
        # half of the QC gate independently.
        parsed = parse_iscn("abc,XY,+8[10]")
        self.assertTrue(any(c["errors"] for c in parsed["clones"]))
        with self.assertRaises(FhirExportError):
            build_mcode_export(parsed, {})

    def test_empty_parse_result_raises(self):
        parsed = parse_iscn("")
        with self.assertRaises(FhirExportError):
            build_mcode_export(parsed, {})


if __name__ == "__main__":
    unittest.main()
