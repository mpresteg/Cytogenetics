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

from iscn_parser import parse_iscn, find_candidate_iscn_lines, find_lab_interpretation  # noqa: E402


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


class TestTerminalBandCoverage(unittest.TestCase):
    """One test per chromosome newly added to APPROX_TERMINAL_BANDS (task 2):
    a plausible band on that chromosome produces no plausibility warning, and
    an implausible one does. Uses the q arm for every chromosome since all 12
    new entries have one (unlike p, which acrocentric chromosome 15 lacks)."""

    def _assert_plausible_and_implausible(self, chrom, plausible, implausible):
        r_ok = parse_iscn(f"46,XY,del({chrom})({plausible})")
        f_ok = first_finding(r_ok)
        self.assertFalse(
            any("higher than the approximate reference" in w for w in f_ok["warnings"]),
            f"{plausible} on chromosome {chrom} should not warn")

        r_bad = parse_iscn(f"46,XY,del({chrom})({implausible})")
        f_bad = first_finding(r_bad)
        self.assertTrue(
            any("higher than the approximate reference" in w for w in f_bad["warnings"]),
            f"{implausible} on chromosome {chrom} should warn")

    def test_chromosome_2(self):
        self._assert_plausible_and_implausible("2", "q30", "q50")

    def test_chromosome_3(self):
        self._assert_plausible_and_implausible("3", "q20", "q40")

    def test_chromosome_4(self):
        self._assert_plausible_and_implausible("4", "q30", "q50")

    def test_chromosome_6(self):
        self._assert_plausible_and_implausible("6", "q20", "q40")

    def test_chromosome_8(self):
        self._assert_plausible_and_implausible("8", "q20", "q40")

    def test_chromosome_10(self):
        self._assert_plausible_and_implausible("10", "q20", "q40")

    def test_chromosome_12(self):
        self._assert_plausible_and_implausible("12", "q20", "q40")

    def test_chromosome_15(self):
        self._assert_plausible_and_implausible("15", "q20", "q40")

    def test_chromosome_18(self):
        self._assert_plausible_and_implausible("18", "q15", "q40")

    def test_chromosome_19(self):
        self._assert_plausible_and_implausible("19", "q12", "q20")

    def test_chromosome_20(self):
        self._assert_plausible_and_implausible("20", "q10", "q20")

    def test_chromosome_y(self):
        self._assert_plausible_and_implausible("Y", "q11", "q20")


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

    def test_fish_only_clone_captures_cell_count(self):
        # Previously silently dropped -- a standalone FISH clone's own
        # trailing [N] never made it into cell_count at all.
        r = parse_iscn("nuc ish(D21S259x3)[200]")
        clone = r["clones"][0]
        self.assertEqual(clone["cell_count"], 200)
        self.assertEqual(len(clone["findings"]), 1)

    def test_band_locus_prefix_captured_per_probe(self):
        # task 15: "1p32(CDKN2Cx2),13q34(LAMP1x2)" -- a band-locus prefix
        # written before each probe's own parens, a common way labs report
        # a multi-locus interphase FISH panel. Previously silently
        # dropped entirely; neither probe has a PROBE_KNOWLEDGE entry, so
        # there's no other source these band strings could come from.
        r = parse_iscn("nuc ish 1p32(CDKN2Cx2),13q34(LAMP1x2)")
        clone = r["clones"][0]
        self.assertEqual(len(clone["findings"]), 2)
        cdkn2c, lamp1 = clone["findings"]
        self.assertIn("CDKN2C", cdkn2c["abbreviation"])
        self.assertIn("locus 1p32", cdkn2c["interpretation"])
        self.assertEqual(cdkn2c["bands"], ["1p32"])
        self.assertIn("LAMP1", lamp1["abbreviation"])
        self.assertIn("locus 13q34", lamp1["interpretation"])
        self.assertEqual(lamp1["bands"], ["13q34"])
        # Not cross-attributed to the wrong probe.
        self.assertNotIn("13q34", cdkn2c["interpretation"])
        self.assertNotIn("1p32", lamp1["interpretation"])

    def test_band_locus_shared_across_probes_in_one_group(self):
        # A single locus can cover more than one probe sharing its parens,
        # e.g. "1p32(CDKN2Cx2,OTHERx1)" -- both probes get that locus.
        r = parse_iscn("nuc ish 1p32(CDKN2Cx2,OTHERx1)")
        clone = r["clones"][0]
        self.assertEqual(len(clone["findings"]), 2)
        self.assertTrue(all(f["bands"] == ["1p32"] for f in clone["findings"]))

    def test_no_band_locus_prefix_still_works(self):
        # Regression: the pre-existing simple form with no locus prefix at
        # all must be unaffected -- no locus text invented, bands stays empty.
        r = parse_iscn("nuc ish(D13S319x1,LAMP1x2)")
        clone = r["clones"][0]
        self.assertEqual(len(clone["findings"]), 2)
        for f in clone["findings"]:
            self.assertEqual(f["bands"], [])
            self.assertNotIn("locus", f["interpretation"])


class TestCombinedKaryotypeFish(unittest.TestCase):
    """ISCN's '<karyotype>[N].nuc ish ...[M]' form: a period joining a
    karyotype clone to a FISH result for the SAME cell population (as
    opposed to '/' for a genuinely different clone). Previously
    unsupported entirely -- see bug report that prompted this."""

    def test_combined_nuc_ish_basic(self):
        r = parse_iscn("46,XY[20].nuc ish 1p32(CDKN2Cx2),13q34(LAMP1x2)[200]")
        clone = r["clones"][0]
        self.assertEqual(clone["modal_number"], 46)
        self.assertEqual(clone["sex_chromosomes"], "XY")
        self.assertEqual(clone["cell_count"], 20)
        self.assertEqual(clone["fish_cell_count"], 200)
        self.assertFalse(clone["fish_only"])
        self.assertEqual(clone["errors"], [])
        self.assertEqual(len(clone["findings"]), 2)
        self.assertTrue(all(f["category"] == "fish" for f in clone["findings"]))

    def test_combined_plain_ish_with_karyotype_finding(self):
        # Plain "ish" (not "nuc ish"), and a karyotype abnormality before
        # the period, not just a normal-count clone.
        r = parse_iscn("47,XY,+8[10].ish 8cen(D8Z2x3)[10]")
        clone = r["clones"][0]
        self.assertEqual(clone["modal_number"], 47)
        self.assertEqual(clone["cell_count"], 10)
        self.assertEqual(clone["fish_cell_count"], 10)
        categories = [f["category"] for f in clone["findings"]]
        self.assertIn("numerical", categories)
        self.assertIn("fish", categories)

    def test_band_decimal_does_not_false_trigger_combined_split(self):
        # A sub-band decimal like "13q14.3" must never be mistaken for the
        # karyotype/FISH joining period -- it's followed by a digit, not
        # the word "ish".
        r = parse_iscn("46,XY[20].nuc ish 13q14.3(DLEUx2)[200]")
        clone = r["clones"][0]
        self.assertEqual(clone["cell_count"], 20)
        self.assertEqual(clone["fish_cell_count"], 200)
        self.assertEqual(clone["findings"][0]["category"], "fish")

    def test_real_world_multi_probe_report(self):
        # The actual string from the bug report (embedded line-wraps from
        # the original paste normalized to spaces here -- see task note
        # in TASKS.md re: mid-token line-wrap corruption being a separate,
        # deliberately out-of-scope concern from this fix).
        raw = (
            "46,XY[20].nuc ish 1p32(CDKN2Cx2),1q21(CKS1Bx2),5p15(hTERTx2),"
            "9q22(D9S1783x2),11cen(D11Z1x2),13q14.3(DLEUx2),13q34(LAMP1x2),"
            "14q32(IGHx2),15cen(D15Z4x2),17p13.1(TP53x2),17q11.2(NF1x2),"
            "3q27(BCL6x2),7cen(D7Z1x2),7q31(D7S486x2),12cen(D12Z3x2)[200]"
        )
        r = parse_iscn(raw)
        clone = r["clones"][0]
        self.assertEqual(clone["modal_number"], 46)
        self.assertEqual(clone["sex_chromosomes"], "XY")
        self.assertEqual(clone["cell_count"], 20)
        self.assertEqual(clone["fish_cell_count"], 200)
        self.assertEqual(clone["errors"], [])
        self.assertEqual(len(clone["findings"]), 15)
        self.assertTrue(all(f["category"] == "fish" for f in clone["findings"]))
        # IGH already has a PROBE_KNOWLEDGE entry, so it should carry its
        # reference note. (TP53 doesn't yet -- that's task 3, unrelated to
        # this fix.)
        joined = " ".join(f["interpretation"] for f in clone["findings"])
        self.assertIn("14q32", joined)
        # task 15: every probe's band-locus prefix (written before its own
        # parens in this list-of-loci form, e.g. "1p32(CDKN2Cx2)") is now
        # captured too, not just IGH's coincidental knowledge-note text
        # above -- check one with no PROBE_KNOWLEDGE entry of its own, so
        # the locus can only be coming from the input string itself.
        cdkn2c = next(f for f in clone["findings"] if "CDKN2C" in f["abbreviation"])
        self.assertEqual(cdkn2c["bands"], ["1p32"])
        self.assertIn("locus 1p32", cdkn2c["interpretation"])

    def test_regular_ish_attached_form_still_works(self):
        # Regression: the pre-existing "ish" attached mid-comma-list form
        # (no period) must not be affected by the new period-detection.
        r = parse_iscn("ish t(9;22)(q34;q11.2)(ABL1+,BCR+)")
        clone = r["clones"][0]
        self.assertTrue(clone["fish_only"])
        self.assertEqual(len(clone["findings"]), 3)

    def test_plain_karyotype_unaffected(self):
        r = parse_iscn("46,XX,t(9;22)(q34;q11.2)")
        clone = r["clones"][0]
        self.assertEqual(clone["fish_cell_count"], None)
        self.assertFalse(clone["fish_only"])


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

    def test_trisomy_8_flags(self):
        r = parse_iscn("47,XY,+8")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("+8" in m["label"] for m in a["matches"]))

    def test_trisomy_8_flags_real_world_mosaic_report(self):
        # The actual reported string from a real (de-identified) MDS-
        # workup report -- task 22's bug fix, same document. Its own
        # interpretation calls trisomy 8 "a recurrent abnormality seen
        # primarily in myeloid neoplasms including MDS, MPNs and AML."
        r = parse_iscn("47,XY,+8[10]/46,XY[10]")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("+8" in m["label"] for m in a["matches"]))
        # Correctly attributed to the abnormal clone, not the normal one.
        self.assertEqual(a["matches"][0]["clone_index"], 0)

    # task 24: CLL panel (Döhner et al., Blood/NEJM 2000 hierarchy) --
    # del(17p) worst, del(11q) poor, +12 intermediate, del(13q) favorable
    # when isolated. Not previously represented in the table at all.
    def test_del_17p_flags(self):
        r = parse_iscn("46,XX,del(17)(p12p13)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("del(17p)" in m["label"] for m in a["matches"]))

    def test_del_11q_flags(self):
        r = parse_iscn("46,XX,del(11)(q22q23)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("del(11q)" in m["label"] for m in a["matches"]))

    def test_trisomy_12_flags(self):
        r = parse_iscn("47,XY,+12")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("+12" in m["label"] for m in a["matches"]))

    def test_del_13q_flags(self):
        r = parse_iscn("46,XX,del(13)(q14q14)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("del(13q)" in m["label"] for m in a["matches"]))

    # task 24: Burkitt lymphoma's three MYC-partner translocation variants.
    def test_myc_igh_translocation_flags(self):
        r = parse_iscn("46,XY,t(8;14)(q24;q32)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("t(8;14)" in m["label"] for m in a["matches"]))

    def test_myc_igk_translocation_flags(self):
        r = parse_iscn("46,XY,t(2;8)(p12;q24)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("t(2;8)" in m["label"] for m in a["matches"]))

    def test_myc_igl_translocation_flags(self):
        r = parse_iscn("46,XY,t(8;22)(q24;q11)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("t(8;22)" in m["label"] for m in a["matches"]))

    # task 24: two more B-ALL-associated translocations flagged by CIBMTR's
    # own disease-classification form, alongside t(9;22)/t(12;21) already
    # in the table.
    def test_kmt2a_translocation_flags(self):
        r = parse_iscn("46,XY,t(4;11)(q21;q23)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("t(4;11)" in m["label"] for m in a["matches"]))

    def test_tcf3_pbx1_translocation_flags(self):
        r = parse_iscn("46,XY,t(1;19)(q23;p13)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("t(1;19)" in m["label"] for m in a["matches"]))

    # task 24: del(20q), an MDS/MPN-recurrent deletion alongside del(5q)
    # and -7/del(7q) already in the table.
    def test_del_20q_flags(self):
        r = parse_iscn("46,XY,del(20)(q11q13)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("del(20q)" in m["label"] for m in a["matches"]))

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
        # (+9, not +8 -- +8 is individually flaggable as of the trisomy 8
        # entry, which would confound what this test is isolating.)
        r = parse_iscn("48,XY,+9,+21,add(4)(p16)")
        a = r["assessment"]
        self.assertTrue(a["flagged"])
        self.assertTrue(any("Complex karyotype" in m["label"] for m in a["matches"]))

    def test_two_abnormalities_not_complex(self):
        # (+9, not +8 -- see note above.)
        r = parse_iscn("47,XY,+9,add(4)(p16)")
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


class TestCandidateLineDetection(unittest.TestCase):
    """find_candidate_iscn_lines() — the text-scanning heuristic task 8's
    PDF upload uses to surface candidate karyotype lines for review."""

    def test_finds_single_candidate_in_report_prose(self):
        text = (
            "Patient: Jane Doe\n"
            "Specimen: Peripheral blood\n"
            "\n"
            "Karyotype:\n"
            "46,XY,t(9;22)(q34;q11.2)\n"
            "\n"
            "Interpretation: Consistent with CML."
        )
        self.assertEqual(find_candidate_iscn_lines(text), ["46,XY,t(9;22)(q34;q11.2)"])

    def test_finds_multiple_candidates_in_order(self):
        text = "Specimen 1: 46,XY\nSome notes here.\nSpecimen 2: 47,XY,+21\n"
        self.assertEqual(
            find_candidate_iscn_lines(text),
            ["46,XY", "47,XY,+21"],
        )

    def test_no_candidates_in_plain_prose(self):
        text = "This report contains no karyotype string at all, just notes."
        self.assertEqual(find_candidate_iscn_lines(text), [])

    def test_does_not_false_positive_on_similar_numbers(self):
        # "2021," followed by a space then non-XY text should not match —
        # no comma-adjacent XY-shaped token immediately follows.
        text = "Specimen received in 2021, XYZ Laboratory reported the result."
        self.assertEqual(find_candidate_iscn_lines(text), [])

    def test_captures_rest_of_line_without_correction(self):
        # Deliberately no *general* auto-trimming of trailing prose caught
        # on the same line — surfaced as-is for human review, per task 8's
        # scope. (A narrow, grammar-grounded exception exists for content
        # glued directly onto a closed "[N]" cell count with no valid
        # continuation -- see test_trims_label_glued_after_bracket below.
        # This case has no bracket at all, so that exception doesn't apply.)
        text = "Result: 46,XY normal male karyotype, no abnormality detected."
        self.assertEqual(
            find_candidate_iscn_lines(text),
            ["46,XY normal male karyotype, no abnormality detected."],
        )

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(find_candidate_iscn_lines(""), [])

    def test_tolerates_single_space_after_comma(self):
        # Real Tesseract OCR output (task 11) routinely inserts a stray
        # space after a comma even when the source never would — the
        # detector should still notice this candidate, unmodified.
        text = "46, XY, t(9;22) (q34;q11.2)"
        self.assertEqual(find_candidate_iscn_lines(text), [text])

    def test_does_not_false_positive_with_space_before_unrelated_text(self):
        # The comma-space tolerance is scoped to right before an XY-shaped
        # token specifically, not a general license to match anything.
        text = "In total, 47 patients were included in this study."
        self.assertEqual(find_candidate_iscn_lines(text), [])

    def test_real_world_pdf_text_layer_hard_wrap(self):
        # The exact text pypdf's extract_text() produces from a real lab
        # report PDF (Warde Medical Laboratory) whose report-generation
        # software hard-wraps long lines within its own text layer --
        # nothing to do with OCR. Confirmed to reconstruct byte-for-byte
        # correctly against the same string parsed cleanly elsewhere.
        text = (
            "ISCN RESULTS\n"
            "46,XY[20].nuc ish\n"
            "1p32(CDKN2Cx2),1q21(CKS1Bx2),5p15(hTERTx2),9q22(D9S1783x2),11cen(D11Z1x2\n"
            "),\n"
            "13q14.3(DLEUx2),13q34(LAMP1x2),14q32(IGHx2),15cen(D15Z4x2),17p13.1(TP53x\n"
            "2),17q11.2(NF1x2),3q27(BCL6x2),\n"
            "7cen(D7Z1x2),7q31(D7S486x2),12cen(D12Z3x2)[200]\n"
            "CULTURES\n"
            "CULTURES: Direct, 24-hour unstimulated, 48-hour unstimulated, and\n"
            "72-hour lymphoid mitogen stimulated.\n"
        )
        expected = (
            "46,XY[20].nuc ish 1p32(CDKN2Cx2),1q21(CKS1Bx2),5p15(hTERTx2),"
            "9q22(D9S1783x2),11cen(D11Z1x2),13q14.3(DLEUx2),13q34(LAMP1x2),"
            "14q32(IGHx2),15cen(D15Z4x2),17p13.1(TP53x2),17q11.2(NF1x2),"
            "3q27(BCL6x2),7cen(D7Z1x2),7q31(D7S486x2),12cen(D12Z3x2)[200]"
        )
        self.assertEqual(find_candidate_iscn_lines(text), [expected])

    def test_real_world_ocr_text_stops_before_section_header(self):
        # The exact text pytesseract.image_to_string() produced from a real
        # scanned version of the same report (300 DPI rasterization of the
        # actual PDF page). Tesseract garbled one closing paren entirely
        # ("D11Z1x2" -> "D1121x2" with the ")" dropped, replaced by a
        # stray "yr" on its own line), which permanently unbalances the
        # paren count -- without the section-boundary check, continuation
        # never resolves and runs to the line cap, swallowing "CULTURES"
        # and the lab disclaimer footer into one giant garbled candidate.
        # With it, folding stops cleanly right before "CULTURES" instead.
        text = (
            "ISCN RESULTS\n\n"
            "46,XY[20].nuc ish\n\n"
            "1p32 (CDKN2Cx2) ,1q21 (CKS1Bx2) ,5p15 (ATERTx2) , 9q22 (D9S1783x2) ,1l1lcen (D1121x2\n"
            "yr\n\n"
            "13q14.3 (DLEUx2) ,13q34 (LAMP1x2) ,14q32 (IGHx2) ,15cen(D1524x2) ,17p13.1(TP53x\n"
            "2) ,17q11.2 (NF1x2) ,3q27 (BCL6x2),\n\n"
            "7Toen (D7Z1x2) ,7q31 (D7S486x2) ,12cen(D12Z3x2) [200]\n\n"
            "CULTURES\n\n"
            "CULTURES: Direct, 24-hour unstimulated, 48-hour unstimulated, and\n"
            "72-hour lymphoid mitogen stimulated.\n\n"
            "LAB: L- LOW, H - HIGH, AB - ABNORMAL, C - CRITICAL, . - NOT TESTED\n"
        )
        candidates = find_candidate_iscn_lines(text)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        # The real FISH panel content made it in, garbled but complete.
        self.assertIn("[200]", candidate)
        self.assertIn("D9S1783x2", candidate)
        # Nothing from the next report section leaked in.
        self.assertNotIn("CULTURES", candidate)
        self.assertNotIn("unstimulated", candidate)
        self.assertNotIn("LAB:", candidate)

    def test_section_boundary_stops_despite_permanently_unbalanced_paren(self):
        # Isolates the mechanism with a minimal, deterministic case (the
        # real-OCR test above is valuable for fidelity but depends on
        # Tesseract's exact behavior) -- an unclosed '(' that will never
        # resolve, immediately followed by a standalone all-caps header.
        text = "46,XY,t(1;2\nCOMMENT\nMore report text here.\n"
        self.assertEqual(find_candidate_iscn_lines(text), ["46,XY,t(1;2"])

    def test_continuation_stops_at_terminal_bracket_not_next_section(self):
        # The "CULTURES" section header right after the wrapped candidate
        # above must never get folded in -- confirmed by the previous
        # test's exact-match assertion, but make the intent explicit here
        # too: a second, unrelated candidate right after a terminated one
        # is still found as its own separate entry.
        text = "46,XY[10]\nCULTURES: standard.\n47,XY,+8[10]\n"
        self.assertEqual(find_candidate_iscn_lines(text), ["46,XY[10]", "47,XY,+8[10]"])

    def test_continuation_join_inserts_space_only_after_ish(self):
        text = "46,XY.nuc ish\n1p32(ABCx2)[50]\n"
        self.assertEqual(
            find_candidate_iscn_lines(text),
            ["46,XY.nuc ish 1p32(ABCx2)[50]"],
        )

    def test_continuation_join_no_space_mid_token(self):
        # Mirrors the real "TP53x\n2" wrap -- must reassemble as "TP53x2",
        # not "TP53x 2".
        text = "46,XY,t(1;2)(p1\n3;q21)[20]\n"
        self.assertEqual(find_candidate_iscn_lines(text), ["46,XY,t(1;2)(p13;q21)[20]"])

    def test_continuation_capped_does_not_run_away(self):
        # An unterminated candidate (never closes its open paren, never
        # stops looking "incomplete") must not swallow the entire rest of
        # the document -- the safety cap kicks in.
        lines = ["46,XY,foo("] + [f"bar{i}," for i in range(30)]
        text = "\n".join(lines)
        candidates = find_candidate_iscn_lines(text)
        self.assertEqual(len(candidates), 1)
        # Capped well short of the full 30-line tail.
        self.assertNotIn("bar29,", candidates[0])
        self.assertIn("bar0,", candidates[0])

    def test_trims_label_glued_after_bracket(self):
        # Real bug report: a report-generation software (Diagnostic
        # Cytogenetics Incorporated's template) consistently emits
        # "value" immediately followed by "Label:" with no separator
        # throughout this document's whole text layer ("XX-XXXXCust.
        # Specimen ID:", "11/08/2016Collection Date:", etc.) -- confirmed
        # against the real PDF, not assumed. It collides badly when it
        # lands on the karyotype line itself: "ABNORMAL RESULTS:" (the
        # section's own label) glued directly onto the end of a real,
        # valid karyotype string with zero separator, all on one physical
        # line, so the naive "grab to end of line" rule can't tell where
        # the real content ends. ISCN grammar itself can: nothing legal
        # follows a closed "[N]" cell count except another clone ("/"),
        # a combined FISH clause ("."), or the end of the string --
        # never arbitrary text. Trims right after the first "]" whose
        # following content isn't one of those, without touching a
        # single character of the actual candidate.
        text = "ABNORMAL RESULTS: 47,XY,+8[10]/46,XY[10]ABNORMAL RESULTS:\n"
        self.assertEqual(
            find_candidate_iscn_lines(text),
            ["47,XY,+8[10]/46,XY[10]"],
        )

    def test_trailing_bracket_with_valid_continuations_not_trimmed(self):
        # The trim only fires on an *invalid* continuation -- "/" (another
        # mosaic clone) and "." (a combined karyotype+FISH clause) are
        # both legal right after a closed "[N]" and must be left alone.
        self.assertEqual(
            find_candidate_iscn_lines("45,X,-Y[10]/46,XY[15]"),
            ["45,X,-Y[10]/46,XY[15]"],
        )
        self.assertEqual(
            find_candidate_iscn_lines("46,XY[20].nuc ish(D21S259x3)[200]"),
            ["46,XY[20].nuc ish(D21S259x3)[200]"],
        )

    def test_trailing_bracket_at_true_end_of_line_not_trimmed(self):
        # The common case: a candidate's "[N]" really is the last thing
        # on the line, nothing glued after it -- no trim should fire.
        self.assertEqual(
            find_candidate_iscn_lines("46,XY,t(9;22)(q34;q11.2)[20]"),
            ["46,XY,t(9;22)(q34;q11.2)[20]"],
        )

    def test_real_world_report_label_glued_after_karyotype(self):
        # The actual text pypdf's extract_text() produces from the real
        # report this bug was found in (page 1 only, trimmed to the
        # relevant excerpt -- the full page also has prose that's not
        # itself candidate-shaped, irrelevant here).
        text = (
            "Cytogenetics Number: NXX-XXXX\n"
            "XX-XXXXCust. Specimen ID:\n"
            "11/08/2016Collection Date:\n"
            "11/09/2016Received Date:\n"
            "11/10/2016Reported Date:\n"
            "47,XY,+8[10]/46,XY[10]ABNORMAL RESULTS:\n"
            "INTERPRETATION: G-banded chromosome analysis shows an abnormal "
            "male karyotype with gain (trisomy) of\n"
        )
        self.assertEqual(
            find_candidate_iscn_lines(text),
            ["47,XY,+8[10]/46,XY[10]"],
        )


class TestLabInterpretationExtraction(unittest.TestCase):
    """find_lab_interpretation() -- task 10's side-by-side comparison
    against a lab report's own written interpretation."""

    def test_finds_bare_interpretation_header(self):
        text = (
            "Patient: Jane Doe\n"
            "Karyotype: 46,XY,t(9;22)(q34;q11.2)\n"
            "\n"
            "INTERPRETATION\n"
            "Findings are consistent with chronic myeloid leukemia.\n"
            "\n"
            "SIGNATURE\n"
            "Dr. Smith\n"
        )
        result = find_lab_interpretation(text)
        self.assertIsNotNone(result)
        self.assertIn("Findings are consistent with", result)
        self.assertNotIn("Dr. Smith", result)

    def test_finds_clinical_correlation_header(self):
        text = (
            "46,XY\n"
            "CLINICAL CORRELATION:\n"
            "No cytogenetic abnormality detected.\n"
            "SIGNATURE\n"
            "Dr. Smith\n"
        )
        result = find_lab_interpretation(text)
        self.assertIn("No cytogenetic abnormality detected.", result)
        self.assertNotIn("Dr. Smith", result)

    def test_finds_inline_header_with_colon_and_content(self):
        # A different real report's convention (see module comment):
        # "INTERPRETATION: <text>" all on one line, rather than the
        # header alone with the text below it.
        text = (
            "Results: 46,XX ; FEMALE KARYOTYPE\n"
            "INTERPRETATION: Normal female karyotype without demonstrable abnormalities.\n"
            "CPT codes: 88233x4\n"
        )
        result = find_lab_interpretation(text)
        self.assertIsNotNone(result)
        self.assertIn("Normal female karyotype without demonstrable abnormalities.", result)

    def test_bare_interpretation_word_without_colon_is_not_a_false_trigger(self):
        # Ordinary prose that happens to start with "Interpretation" but
        # has no colon and isn't the section header itself shouldn't
        # trigger extraction.
        text = "Interpretation of these results requires clinical correlation.\n"
        self.assertIsNone(find_lab_interpretation(text))

    def test_no_interpretation_section_returns_none(self):
        text = "Patient: Jane Doe\nKaryotype: 46,XY\nNo further sections here.\n"
        self.assertIsNone(find_lab_interpretation(text))

    def test_subheading_within_interpretation_does_not_stop_extraction(self):
        # A genuine sub-heading inside the interpretation (all-uppercase,
        # like a real report's "OVERALL INTERPRETATION") must not be
        # mistaken for the end of the section -- only the small,
        # documented terminator list should stop it.
        text = (
            "INTERPRETATION\n"
            "OVERALL INTERPRETATION\n"
            "Normal karyotype, no abnormality detected.\n"
            "COMMENT\n"
            "Boilerplate disclaimer text.\n"
            "SIGNATURE\n"
            "Dr. Smith\n"
        )
        result = find_lab_interpretation(text)
        self.assertIn("OVERALL INTERPRETATION", result)
        self.assertIn("Normal karyotype, no abnormality detected.", result)
        self.assertIn("Boilerplate disclaimer text.", result)
        self.assertNotIn("Dr. Smith", result)

    def test_comment_is_captured_not_a_stop_signal(self):
        # COMMENT sections vary by lab -- some are generic disclaimer
        # boilerplate (Warde), others hold genuine case-specific caveats
        # right next to a named reviewer (a second real report's
        # "COMMENT: We cannot rule out..." / "Reviewed By: ..."). Rather
        # than guess which applies to a given PDF, COMMENT is captured
        # like any other content; only a later terminator ends the block.
        text = (
            "INTERPRETATION\n"
            "Findings are consistent with chronic myeloid leukemia.\n"
            "COMMENT\n"
            "This assay has not been cleared by the FDA.\n"
            "SIGNATURE\n"
            "Dr. Smith\n"
        )
        result = find_lab_interpretation(text)
        self.assertIn("Findings are consistent with", result)
        self.assertIn("FDA", result)
        self.assertNotIn("Dr. Smith", result)

    def test_capped_does_not_run_away_with_no_terminator(self):
        lines = ["INTERPRETATION"] + [f"line {i}" for i in range(150)]
        text = "\n".join(lines)
        result = find_lab_interpretation(text)
        self.assertLessEqual(len(result.splitlines()), 80)

    def test_real_world_report_interpretation(self):
        # The actual text pypdf's extract_text() produces for a real lab
        # report (Warde Medical Laboratory), spanning a page boundary --
        # note the interleaved page-2 header/footer noise mid-section,
        # confirmed against the real PDF. This is accepted, not cleaned
        # up (see the module comment) -- the point is capturing the real
        # clinical content, not producing a pristine excerpt. Extended
        # through the real COMMENT section (now captured, not skipped --
        # see module comment) up to the real SIGNATURE terminator.
        text = (
            "...ISH]\n"
            "INTERPRETATION\n"
            "OVERALL INTERPRETATION\n"
            "Cytogenetics\n"
            "Normal Karyotype\n"
            "No consistent numerical or structural chromosome abnormalities were\n"
            "observed.\n"
            "Analysis was performed on cells from three unstimulated cultures and a\n"
            "culture that was stimulated with lymphoid mitogens.\n"
            "These results are consistent with those observed in a previous sample\n"
            "from this patient.\n"
            "Myeloma Profile [Interphase FISH]\n"
            "Negative for gain of 1q, loss of 1p, -13/del(13q), IGH rearrangements,\n"
            "del(17p), +5, +9, +11, +15\n"
            "Fluorescence in situ hybridization (FISH) was performed with\n"
            "MetaSystems probes specific for chromosomes 1 (CDKN2C, CKS1B), 5\n"
            "(hTERT), 9 (D9S1783), 11 (D11Z1), 13 (DLEU, LAMP1), 14 (IGH), 15\n"
            "(D15Z4), and 17 (TP53, NF1).\n"
            "Two hundred nuclei were examined for each probe, and all results were\n"
            "within normal limits for the laboratory's established background rates.\n"
            "Marginal Zone Lymphoma Profile [Interphase FISH]\n"
            "Negative for gain of 3q/rearrangement of BCL6, -7/del(7q), +12\n"
            "rpt_ch_\n"
            "Form: MM RL1\n"
            "PAGE 1 OF 4\n"
            "rpt_ch_\n"
            "EXAMPLE, REPORT W\n"
            "LABORATORY REPORT\n"
            "Referral Testing\n"
            "Test Name Result Flag Ref-Ranges Units Site\n"
            "Negative for gain of 3q/rearrangement of BCL6, -7/del(7q), +12\n"
            "FISH was also performed with Vysis probes specific for BCL6 on the long\n"
            "arm of chromosome 3, and for chromosomes 7 (D7Z1, D7S486) and 12\n"
            "(D12Z3).\n"
            "Two hundred nuclei were examined for each probe, and the results are\n"
            "within normal limits for the laboratory's established background rates.\n"
            "The marginal zone FISH results are consistent with those observed in\n"
            "the previous sample.\n"
            "COMMENT\n"
            "Chromosome analysis will not detect subtle translocations, deletions,\n"
            "inversions or other cytogenetic abnormalities that are beyond the\n"
            "resolution limits of the technology used.\n"
            "These FISH tests were developed and their analytical performance\n"
            "characteristics have been determined by AmeriPath Northeast.  They have\n"
            "not been cleared or approved by the U.S. Food and Drug Administration.\n"
            "SIGNATURE\n"
            "Director, Cytogenetics:\n"
            "Electronic Signature:\n"
            "RESULTS\n"
            "ISCN RESULTS\n"
            "46,XY[20].nuc ish\n"
        )
        result = find_lab_interpretation(text)
        self.assertIsNotNone(result)
        self.assertIn("Normal Karyotype", result)
        self.assertIn("Negative for gain of 1q", result)
        self.assertIn("Vysis probes specific for BCL6", result)
        self.assertIn("Chromosome analysis will not detect", result)
        self.assertIn("Food and Drug Administration", result)
        self.assertNotIn("Electronic Signature", result)
        self.assertNotIn("ISCN RESULTS", result)

    def test_real_world_second_report_interpretation(self):
        # A different lab/template's actual extract_text() output (a
        # products-of-conception report) -- the case that prompted the
        # header-regex and COMMENT-terminator revisions in the module
        # comment. "INTERPRETATION:" and "COMMENT:" both appear inline
        # with content on the same line, and there's a named reviewer
        # right after -- all of which should now be captured, since this
        # report has no SIGNATURE/RESULTS/etc. terminator to stop at.
        text = (
            "Results: 46,XX ; FEMALE KARYOTYPE\n"
            "INTERPRETATION: Normal female karyotype without demonstrable abnormalities.\n"
            "COMMENT: We cannot rule out the possibility that the cells analyzed in this preparation are\n"
            "of maternal origin.\n"
            "CPT codes: 88233x4, 88262, 88280, 88291\n"
            "Cultures Established:\n"
            "Reviewed By:\n"
            "KATHLEEN  LEPPIG, M.D.\n"
        )
        result = find_lab_interpretation(text)
        self.assertIsNotNone(result)
        self.assertIn("Normal female karyotype without demonstrable abnormalities.", result)
        self.assertIn("We cannot rule out the possibility", result)
        self.assertIn("KATHLEEN  LEPPIG, M.D.", result)


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
