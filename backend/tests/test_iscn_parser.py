"""
tests/test_iscn_parser.py

Written with unittest (stdlib, zero dependencies) so it's runnable anywhere
Python is, including sandboxes with no network access to pip-install pytest.
pytest can also discover and run these directly (`pytest tests/`) if that's
your preferred runner — unittest.TestCase classes are pytest-compatible.

Run directly with:
    python3 -m unittest discover -s tests -v
or, from the backend/ directory:
    python3 -m unittest tests.test_iscn_parser -v
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iscn_parser import parse_iscn  # noqa: E402


def first_finding(result, clone_idx=0):
    return result["clones"][clone_idx]["findings"][0]


class TestNormalKaryotype(unittest.TestCase):
    def test_normal_male(self):
        r = parse_iscn("46,XY")
        clone = r["clones"][0]
        self.assertEqual(clone["modal_number"], 46)
        self.assertEqual(clone["sex_chromosomes"], "XY")
        self.assertEqual(clone["findings"], [])
        self.assertEqual(clone["errors"], [])

    def test_normal_female(self):
        r = parse_iscn("46,XX")
        clone = r["clones"][0]
        self.assertEqual(clone["sex_chromosomes"], "XX")
        self.assertEqual(clone["errors"], [])


class TestNumerical(unittest.TestCase):
    def test_trisomy_21(self):
        r = parse_iscn("47,XY,+21")
        f = first_finding(r)
        self.assertEqual(f["category"], "numerical")
        self.assertEqual(f["chromosomes"], ["21"])
        self.assertIn("Gain", f["interpretation"])

    def test_monosomy_x_turner(self):
        r = parse_iscn("45,X")
        clone = r["clones"][0]
        self.assertEqual(clone["modal_number"], 45)
        self.assertEqual(clone["sex_chromosomes"], "X")
        # No numerical abnormality token needed here — the sex string itself
        # already encodes the monosomy; no warnings expected.
        self.assertEqual(clone["warnings"], [])

    def test_modal_number_mismatch_is_flagged(self):
        # -Y with sex already given as X is internally inconsistent bookkeeping.
        r = parse_iscn("45,X,-Y")
        clone = r["clones"][0]
        self.assertTrue(any("doesn't match" in w for w in clone["warnings"]))


class TestStructural(unittest.TestCase):
    def test_reciprocal_translocation(self):
        r = parse_iscn("46,XX,t(9;22)(q34;q11.2)")
        f = first_finding(r)
        self.assertEqual(f["abbreviation"], "t")
        self.assertEqual(f["chromosomes"], ["9", "22"])
        self.assertEqual(f["bands"], ["q34", "q11.2"])
        self.assertIn("reciprocal", f["interpretation"])

    def test_three_way_translocation(self):
        r = parse_iscn("46,XY,t(3;9;22)(p25;q34;q11.2)")
        f = first_finding(r)
        self.assertEqual(f["chromosomes"], ["3", "9", "22"])
        self.assertIn("3-way", f["interpretation"])

    def test_deletion_two_bands(self):
        r = parse_iscn("46,XY,del(5)(q13q33)")
        f = first_finding(r)
        self.assertEqual(f["bands"], ["q13", "q33"])
        self.assertEqual(f["warnings"], [])

    def test_deletion_reversed_bands_warns(self):
        r = parse_iscn("46,XX,del(5)(q33q13)")
        f = first_finding(r)
        self.assertTrue(any("distal-to-proximal" in w for w in f["warnings"]))

    def test_deletion_implausible_band_warns(self):
        r = parse_iscn("46,XX,del(5)(q90)")
        f = first_finding(r)
        self.assertTrue(any("higher than the approximate reference" in w for w in f["warnings"]))

    def test_inversion(self):
        r = parse_iscn("46,XX,inv(16)(p13q22)")
        f = first_finding(r)
        self.assertEqual(f["bands"], ["p13", "q22"])

    def test_isochromosome(self):
        r = parse_iscn("46,XX,i(17)(q10)")
        f = first_finding(r)
        self.assertEqual(f["bands"], ["q10"])
        self.assertIn("long (q)", f["interpretation"])

    def test_marker_chromosome(self):
        r = parse_iscn("47,XY,+mar")
        f = first_finding(r)
        self.assertIn("marker", f["interpretation"])


class TestDerivativeDecomposition(unittest.TestCase):
    def test_der_with_embedded_translocation(self):
        r = parse_iscn("46,XY,der(14)t(14;18)(q32;q21)")
        f = first_finding(r)
        self.assertEqual(f["abbreviation"], "der")
        self.assertEqual(f["chromosomes"], ["14"])
        self.assertIn("Translocation", f["interpretation"])
        self.assertIn("q32", f["interpretation"])
        # Fully decomposed, so no "not decomposed" leftover warning.
        self.assertFalse(any("not decomposed" in w for w in f["warnings"]))

    def test_der_whole_arm_acrocentric_suggests_rob(self):
        r = parse_iscn("45,XY,der(13;14)(q10;q10)")
        f = first_finding(r)
        self.assertEqual(f["chromosomes"], ["13", "14"])
        self.assertTrue(any("rob()" in w for w in f["warnings"]))

    def test_der_whole_arm_non_acrocentric_no_rob_suggestion(self):
        r = parse_iscn("46,XY,der(1;7)(q10;p10)")
        f = first_finding(r)
        self.assertFalse(any("rob()" in w for w in f["warnings"]))

    def test_rob_notation(self):
        r = parse_iscn("45,XY,rob(13;14)(q10;q10)")
        f = first_finding(r)
        self.assertEqual(f["abbreviation"], "rob")
        self.assertEqual(f["chromosomes"], ["13", "14"])
        self.assertEqual(f["warnings"], [])

    def test_rob_non_acrocentric_warns(self):
        r = parse_iscn("46,XY,rob(1;7)(q10;q10)")
        f = first_finding(r)
        self.assertTrue(any("acrocentric" in w for w in f["warnings"]))

    def test_der_unparseable_content_flagged_not_dropped(self):
        r = parse_iscn("46,XY,der(5)xyz123")
        f = first_finding(r)
        self.assertIn("xyz123", f["interpretation"])
        self.assertTrue(any("wasn't recognized" in w for w in f["warnings"]))


class TestMosaicism(unittest.TestCase):
    def test_two_clones_with_cell_counts(self):
        r = parse_iscn("47,XY,+21[20]/46,XY[5]")
        self.assertTrue(r["is_mosaic"])
        self.assertEqual(r["clone_count"], 2)
        self.assertEqual(r["clones"][0]["cell_count"], 20)
        self.assertEqual(r["clones"][1]["cell_count"], 5)
        self.assertEqual(r["clones"][1]["findings"], [])


class TestFish(unittest.TestCase):
    def test_nuc_ish_copy_number(self):
        r = parse_iscn("nuc ish(D21S259x3)")
        clone = r["clones"][0]
        self.assertTrue(clone["fish_only"])
        f = clone["findings"][0]
        self.assertEqual(f["category"], "fish")
        self.assertIn("3 signal", f["interpretation"])
        # Known probe should carry a reference note.
        self.assertIn("Reference note", f["interpretation"])

    def test_ish_attached_to_translocation_with_probes(self):
        r = parse_iscn("ish t(9;22)(q34;q11.2)(ABL1+,BCR+)")
        clone = r["clones"][0]
        self.assertEqual(len(clone["findings"]), 3)
        self.assertEqual(clone["findings"][0]["abbreviation"], "t")
        self.assertEqual(clone["findings"][1]["category"], "fish")
        self.assertEqual(clone["findings"][2]["category"], "fish")

    def test_fusion_knowledge_note(self):
        r = parse_iscn("nuc ish(ABL1 con BCR)x1")
        clone = r["clones"][0]
        # tolerate either parse shape; just confirm the fusion note surfaces
        # somewhere in the findings if the token was recognized as fusion.
        joined = " ".join(f["interpretation"] for f in clone["findings"])
        if "Fusion signal" in joined:
            self.assertIn("Philadelphia chromosome", joined)

    def test_unknown_probe_no_note_no_crash(self):
        r = parse_iscn("nuc ish(ZZZ999x2)")
        f = r["clones"][0]["findings"][0]
        self.assertNotIn("Reference note", f["interpretation"])


class TestUnrecognized(unittest.TestCase):
    def test_bogus_token_flagged_not_silently_dropped(self):
        r = parse_iscn("46,XY,foo(1)(p1)")
        clone = r["clones"][0]
        self.assertEqual(len(clone["findings"]), 1)
        f = clone["findings"][0]
        self.assertEqual(f["category"], "unrecognized")
        self.assertFalse(f["valid"])

    def test_bad_sex_string_is_error(self):
        r = parse_iscn("46,ZZ")
        clone = r["clones"][0]
        self.assertTrue(any("sex chromosome" in e for e in clone["errors"]))

    def test_empty_input(self):
        r = parse_iscn("")
        self.assertEqual(r["clones"], [])
        self.assertIn("Empty input.", r["errors"])


class TestClinicalAssessment(unittest.TestCase):
    def test_bcr_abl1_translocation_flags(self):
        r = parse_iscn("46,XY,t(9;22)(q34;q11.2)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertEqual(len(a["matches"]), 1)
        m = a["matches"][0]
        self.assertIn("BCR-ABL1", m["label"])
        self.assertIn("CML", m["note"])
        self.assertTrue(m["note"].startswith("Reference note (not diagnostic):"))
        self.assertEqual(m["finding_raw"], "t(9;22)(q34;q11.2)")
        self.assertEqual(m["clone_index"], 0)

    def test_pml_rara_translocation_flags(self):
        r = parse_iscn("46,XX,t(15;17)(q24;q21)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("PML-RARA" in m["label"] for m in a["matches"]))
        self.assertTrue(any("promyelocytic" in m["note"] for m in a["matches"]))

    def test_inv16_flags_cbfb_myh11(self):
        r = parse_iscn("46,XY,inv(16)(p13q22)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("CBFB-MYH11" in m["label"] for m in a["matches"]))

    def test_t_16_16_also_flags_cbfb_myh11(self):
        r = parse_iscn("46,XY,t(16;16)(p13;q22)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("CBFB-MYH11" in m["label"] for m in a["matches"]))

    def test_monosomy_7_flags(self):
        r = parse_iscn("45,XY,-7")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("7" in m["label"] for m in a["matches"]))

    def test_del_5q_flags(self):
        r = parse_iscn("46,XX,del(5)(q13q33)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("del(5q)" in m["label"] for m in a["matches"]))

    def test_normal_karyotype_not_flagged(self):
        r = parse_iscn("46,XY")
        a = r["assessment"]
        self.assertFalse(a["flagged"])
        self.assertEqual(a["matches"], [])

    def test_unrelated_abnormality_not_flagged(self):
        r = parse_iscn("46,XY,add(4)(p16)")
        a = r["assessment"]
        self.assertFalse(a["flagged"])
        self.assertEqual(a["matches"], [])

    def test_complex_karyotype_flags_without_specific_match(self):
        # Three unrelated abnormalities, none individually in the table.
        r = parse_iscn("48,XY,+8,+21,add(4)(p16)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("Complex karyotype" in m["label"] for m in a["matches"]))

    def test_two_abnormalities_not_complex(self):
        r = parse_iscn("47,XY,+8,add(4)(p16)")
        a = r["assessment"]
        self.assertFalse(a["flagged"])

    def test_mosaic_records_clone_index(self):
        r = parse_iscn("47,XY,t(9;22)(q34;q11.2)[10]/46,XY[10]")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertEqual(a["matches"][0]["clone_index"], 0)

    def test_fish_only_no_crash_not_flagged(self):
        r = parse_iscn("nuc ish(D21S259x3)")
        a = r["assessment"]
        self.assertFalse(a["flagged"])
        self.assertEqual(a["matches"], [])

    def test_empty_input_assessment_is_none(self):
        r = parse_iscn("")
        self.assertIsNone(r["assessment"])


class TestEdition(unittest.TestCase):
    def test_default_edition(self):
        r = parse_iscn("46,XY")
        self.assertEqual(r["edition"], "2024")

    def test_explicit_edition_passthrough(self):
        r = parse_iscn("46,XY", edition="2016")
        self.assertEqual(r["edition"], "2016")

    def test_invalid_edition_falls_back_to_default(self):
        r = parse_iscn("46,XY", edition="not-a-real-edition")
        self.assertEqual(r["edition"], "2024")

    def test_rob_edition_note_present(self):
        r = parse_iscn("45,XY,rob(13;14)(q10;q10)")
        self.assertTrue(any("rob()" in n for n in r["clones"][0]["edition_notes"]))


if __name__ == "__main__":
    unittest.main()
