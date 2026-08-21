"""
iscn_parser.py

A rule-based parser/interpreter for a useful subset of ISCN
(International System for Human Cytogenomic Nomenclature) strings —
both full karyotype descriptions and FISH (ish / nuc ish) results.

This is NOT a complete implementation of the ISCN grammar (which is
large, versioned, and has many edge cases / free-text allowances).
It covers the abnormality types clinical cytogenetics labs use most
often, validates structure, and produces a plain-English
interpretation of each token. Anything it doesn't recognize is
flagged clearly as "unrecognized" rather than silently dropped or
mis-parsed — see README for the supported-grammar list and where to
extend it.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

# ---------------------------------------------------------------------------
# Shared building-block regexes
# ---------------------------------------------------------------------------

CHROM = r'(?:[1-9]|1[0-9]|2[0-2]|X|Y)'
BAND = r'(?:p|q)(?:\d{1,2}(?:\.\d{1,3})?|ter|cen)?'
VALID_CHROMS = {str(i) for i in range(1, 23)} | {"X", "Y"}


def split_top_level(s: str, sep: str = ',') -> List[str]:
    """Split on `sep` but only at bracket depth 0, so commas inside
    t(9;22)(q34;q11.2) or nuc ish(...) don't get split."""
    tokens, current, depth = [], '', 0
    for ch in s:
        if ch in '([':
            depth += 1
            current += ch
        elif ch in ')]':
            depth -= 1
            current += ch
        elif ch == sep and depth == 0:
            tokens.append(current)
            current = ''
        else:
            current += ch
    if current.strip():
        tokens.append(current)
    return [t.strip() for t in tokens if t.strip()]


def valid_band(b: str) -> bool:
    return bool(re.fullmatch(BAND, b))


def split_concatenated_bands(s: str) -> List[str]:
    """ISCN often writes two bands back-to-back with no separator,
    e.g. 'p13q22' in inv(16)(p13q22) or 'q13q33' in del(5)(q13q33).
    Split on the p/q boundary."""
    return [m.group(0) for m in re.finditer(r'[pq](?:\d{1,2}(?:\.\d{1,3})?|ter|cen)?', s)]


def parse_band(b: str):
    """Break a band string like 'q13.3' into (arm, major:int|None, minor:tuple).
    Returns None if it doesn't look like a standard numbered band (e.g. 'ter'/'cen')."""
    mm = re.match(r'^([pq])(\d{1,2})(?:\.(\d{1,3}))?$', b)
    if not mm:
        return None
    arm, major, minor = mm.group(1), int(mm.group(2)), mm.group(3)
    minor_tuple = tuple(int(c) for c in minor) if minor else ()
    return arm, major, minor_tuple


# ---------------------------------------------------------------------------
# Approximate terminal-band reference table, for SANITY-CHECKING ONLY.
#
# Highest major band number per arm, for all 24 chromosomes. The intent is
# to catch obviously-impossible bands (e.g. 'q90' on a chromosome that tops
# out around q35), not to certify correctness — this only checks the major
# band number, never the sub-band decimal.
#
# The original 12 entries (1, 5, 7, 9, 11, 13, 14, 16, 17, 21, 22, X) were
# added without a cited source and flagged as such. The remaining 12
# (2, 3, 4, 6, 8, 10, 12, 15, 18, 19, 20, Y) were added by taking the
# terminal band of each arm from the per-chromosome cytogenetic band tables
# on English Wikipedia (e.g. https://en.wikipedia.org/wiki/Chromosome_2),
# which are themselves derived from NCBI's GRCh38 ideogram data — retrieved
# August 2026. Acrocentric chromosomes (13, 14, 15, 21, 22) have no
# meaningfully-numbered p arm and so have no "p" entry, matching the
# original 4 acrocentric entries. Still worth spot-checking against a
# current ISCN reference chart before relying on this for anything beyond
# "does this look obviously wrong."
#
# A note on staleness: the major band NAMES here (classical G-banding,
# e.g. "q37") are quite stable and don't move with genome-assembly
# revisions — but the GRCh38-derived data this was sourced from is a
# sequence-coordinate mapping, not the ISCN nomenclature committee's own
# publication, and that mapping can shift slightly across assembly
# versions. This table is a soft-warning-only heuristic specifically
# because of that gap between "good public proxy" and "actual ISCN
# standard." See task 4 in TASKS.md, which already covers sourcing real
# ISCN edition text — if/when that's ever picked up, re-verifying this
# table against the primary source (rather than a genome-assembly proxy)
# should happen at the same time, not on a separate schedule.
# ---------------------------------------------------------------------------
APPROX_TERMINAL_BANDS = {
    "1": {"p": 36, "q": 44},
    "2": {"p": 25, "q": 37},
    "3": {"p": 26, "q": 29},
    "4": {"p": 16, "q": 35},
    "5": {"p": 15, "q": 35},
    "6": {"p": 25, "q": 27},
    "7": {"p": 22, "q": 36},
    "8": {"p": 23, "q": 24},
    "9": {"p": 24, "q": 34},
    "10": {"p": 15, "q": 26},
    "11": {"p": 15, "q": 25},
    "12": {"p": 13, "q": 24},
    "13": {"q": 34},
    "14": {"q": 32},
    "15": {"q": 26},
    "16": {"p": 13, "q": 24},
    "17": {"p": 13, "q": 25},
    "18": {"p": 11, "q": 23},
    "19": {"p": 13, "q": 13},
    "20": {"p": 13, "q": 13},
    "21": {"q": 22},
    "22": {"q": 13},
    "X": {"p": 22, "q": 28},
    "Y": {"p": 11, "q": 12},
}


def check_band_plausibility(chrom: str, band: str) -> Optional[str]:
    """Soft sanity check against APPROX_TERMINAL_BANDS. Returns a warning
    string if the band's major number looks out of range, else None.
    Deliberately conservative: only fires for chromosomes in the reference
    table and only for a clear overshoot, never a hard error."""
    parsed = parse_band(band)
    if not parsed:
        return None
    arm, major, _ = parsed
    limits = APPROX_TERMINAL_BANDS.get(chrom)
    if not limits or arm not in limits:
        return None
    if major > limits[arm]:
        return (f"Band {band} on chromosome {chrom} is higher than the approximate "
                f"reference terminal band ({arm}{limits[arm]}) — double-check against "
                f"an ISCN idiogram; this reference table is approximate.")
    return None


def check_breakpoint_order(bands: List[str]) -> Optional[str]:
    """ISCN convention lists two-band breakpoints proximal-to-distal (closer
    to the centromere first). Soft-warn if the bands look reversed on the
    same arm — never a hard error, since real-world usage varies."""
    if len(bands) != 2:
        return None
    a, b = parse_band(bands[0]), parse_band(bands[1])
    if not a or not b or a[0] != b[0]:
        return None
    if a[1] > b[1] or (a[1] == b[1] and a[2] > b[2]):
        return (f"Breakpoints '{bands[0]}' then '{bands[1]}' look listed distal-to-proximal; "
                f"ISCN convention is usually proximal breakpoint first.")
    return None


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    raw: str
    category: str            # "numerical" | "structural" | "fish" | "unrecognized"
    abbreviation: Optional[str] = None
    chromosomes: List[str] = field(default_factory=list)
    bands: List[str] = field(default_factory=list)
    interpretation: str = ""
    valid: bool = True
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CloneResult:
    raw: str
    modal_number: Optional[int]
    modal_number_raw: Optional[str]
    sex_chromosomes: Optional[str]
    cell_count: Optional[int]
    findings: List[Finding]
    fish_only: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # Only set for a combined "<karyotype>[N].nuc ish ...[M]" clone (see
    # parse_combined_karyotype_and_fish()) — the FISH clause's own cell
    # count (e.g. interphase nuclei scored), distinct from `cell_count`
    # (the karyotype clause's metaphase count).
    fish_cell_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Abnormality interpreters (karyotype tokens)
# ---------------------------------------------------------------------------

def _chrom_label(c: str) -> str:
    return f"chromosome {c}"


def interpret_numerical(m: re.Match) -> Finding:
    sign, target = m.group(1), m.group(2)
    raw = m.group(0)
    if target == "mar":
        text = f"{'Gain' if sign == '+' else 'Loss'} of a marker chromosome"
    else:
        verb = "Gain (trisomy/extra copy)" if sign == '+' else "Loss (monosomy/missing copy)"
        text = f"{verb} of {_chrom_label(target)}"
    chroms = [] if target == "mar" else [target]
    return Finding(raw=raw, category="numerical", abbreviation=sign,
                    chromosomes=chroms, bands=[], interpretation=text)


def interpret_marker(m: re.Match) -> Finding:
    raw = m.group(0)
    n = m.group(1)
    n_txt = n if n else "one or more"
    text = f"Presence of {n_txt} structurally unidentifiable marker chromosome(s)"
    return Finding(raw=raw, category="structural", abbreviation="mar",
                    interpretation=text)


def interpret_translocation(m: re.Match) -> Finding:
    raw = m.group(0)
    chroms = [c.strip() for c in m.group(1).split(';')]
    bands = [b.strip() for b in m.group(2).split(';')]
    warnings = []
    if len(chroms) != len(bands):
        warnings.append("Number of chromosomes and breakpoint bands do not match.")
    pairs = ", ".join(f"{c} at {b}" for c, b in zip(chroms, bands))
    n_way = "reciprocal" if len(chroms) == 2 else f"{len(chroms)}-way"
    text = f"Translocation ({n_way}) with breakpoints on {pairs}"
    return Finding(raw=raw, category="structural", abbreviation="t",
                    chromosomes=chroms, bands=bands, interpretation=text,
                    warnings=warnings)


def interpret_two_band_structural(name: str, verb: str):
    def _fn(m: re.Match) -> Finding:
        raw = m.group(0)
        chrom = m.group(1)
        band_blob = m.group(2)
        bands = split_concatenated_bands(band_blob) or [band_blob]
        warnings = []
        for b in bands:
            if not valid_band(b):
                warnings.append(f"'{b}' does not look like a valid band designation.")
            else:
                plaus = check_band_plausibility(chrom, b)
                if plaus:
                    warnings.append(plaus)
        order_warn = check_breakpoint_order(bands)
        if order_warn:
            warnings.append(order_warn)
        if len(bands) >= 2:
            text = f"{verb} of {_chrom_label(chrom)} from {bands[0]} to {bands[-1]}"
        elif len(bands) == 1:
            text = f"{verb} of {_chrom_label(chrom)} at {bands[0]}"
        else:
            text = f"{verb} of {_chrom_label(chrom)}"
        return Finding(raw=raw, category="structural", abbreviation=name,
                        chromosomes=[chrom], bands=bands, interpretation=text,
                        warnings=warnings)
    return _fn


def interpret_isochromosome(m: re.Match) -> Finding:
    raw = m.group(0)
    chrom, band = m.group(1), m.group(2)
    arm = "long (q)" if band.startswith('q') else "short (p)" if band.startswith('p') else band
    text = (f"Isochromosome of {_chrom_label(chrom)}: mirror-image duplication of the "
            f"{arm} arm with loss of the other arm")
    return Finding(raw=raw, category="structural", abbreviation="i",
                    chromosomes=[chrom], bands=[band], interpretation=text)


def interpret_ring(m: re.Match) -> Finding:
    raw = m.group(0)
    chrom = m.group(1)
    band = m.group(2)
    text = f"Ring chromosome formed from {_chrom_label(chrom)}"
    if band:
        text += f" (breakpoints {band})"
    return Finding(raw=raw, category="structural", abbreviation="r",
                    chromosomes=[chrom], bands=[band] if band else [],
                    interpretation=text)


SUB_EVENT_RE = re.compile(r'([a-z]+)\(([^()]*)\)\(([^()]*)\)')


def _decompose_der_body(rest: str):
    """Given everything after der(chrom), find embedded rearrangement events
    like t(14;18)(q32;q21) or del(5)(q13q33) and parse each with the
    existing single-event patterns (recursion into the same rule table used
    for top-level tokens). Returns (sub_findings, leftover_text)."""
    sub_findings: List[Finding] = []
    consumed_spans = []
    for match in SUB_EVENT_RE.finditer(rest):
        token = match.group(0)
        sub = parse_karyotype_token(token)
        if sub.category != "unrecognized":
            sub_findings.append(sub)
            consumed_spans.append(match.span())
    leftover_parts = []
    last_end = 0
    for start, end in consumed_spans:
        chunk = rest[last_end:start].strip(' ,')
        if chunk:
            leftover_parts.append(chunk)
        last_end = end
    tail = rest[last_end:].strip(' ,')
    if tail:
        leftover_parts.append(tail)
    return sub_findings, " ".join(leftover_parts)


def interpret_derivative_single(m: re.Match) -> Finding:
    raw = m.group(0)
    chrom = m.group(1)
    rest = m.group(2).strip()
    warnings: List[str] = []

    if not rest:
        text = f"Derivative {_chrom_label(chrom)} (rearrangement details not further specified)"
        return Finding(raw=raw, category="structural", abbreviation="der",
                        chromosomes=[chrom], interpretation=text)

    sub_findings, leftover = _decompose_der_body(rest)
    if sub_findings:
        parts = "; then ".join(f.interpretation for f in sub_findings)
        text = f"Derivative {_chrom_label(chrom)}, formed via: {parts}"
        for sf in sub_findings:
            warnings.extend(sf.warnings)
    else:
        text = f"Derivative chromosome based on {_chrom_label(chrom)}"
        leftover = rest

    if leftover:
        text += f" (additional content not decomposed: '{leftover}')"
        warnings.append("Part of this der() token wasn't recognized as one of the supported "
                         "rearrangement types (t/del/dup/inv/ins/add) — reported as raw text. "
                         "See README for extending der() decomposition.")
    return Finding(raw=raw, category="structural", abbreviation="der",
                    chromosomes=[chrom], interpretation=text, warnings=warnings)


ACROCENTRIC = {"13", "14", "15", "21", "22"}


def interpret_der_whole_arm(m: re.Match) -> Finding:
    raw = m.group(0)
    chroms = [c.strip() for c in m.group(1).split(';')]
    bands = [b.strip() for b in m.group(2).split(';')]
    text = (f"Derivative chromosome combining {chroms[0]} (breakpoint {bands[0]}) and "
            f"{chroms[1]} (breakpoint {bands[1]}) — whole-arm / centromeric-fusion type rearrangement")
    warnings = []
    if set(chroms) <= ACROCENTRIC and all(b.endswith('10') for b in bands):
        warnings.append(
            "This looks like a centromeric fusion between two acrocentric chromosomes. "
            "Current ISCN practice generally prefers explicit rob() notation for Robertsonian "
            "translocations (e.g. rob(13;14)(q10;q10)) over the older der() form — worth "
            "confirming which convention the source report is using."
        )
    return Finding(raw=raw, category="structural", abbreviation="der",
                    chromosomes=chroms, bands=bands, interpretation=text, warnings=warnings)


def interpret_rob(m: re.Match) -> Finding:
    raw = m.group(0)
    chroms = [c.strip() for c in m.group(1).split(';')]
    bands = [b.strip() for b in m.group(2).split(';')]
    warnings = []
    if not (set(chroms) <= ACROCENTRIC):
        warnings.append("rob() is conventionally used for the acrocentric chromosomes "
                         "(13, 14, 15, 21, 22); one or both chromosomes here are outside that set.")
    text = (f"Robertsonian translocation between chromosome {chroms[0]} and chromosome {chroms[1]} "
            f"(centromeric fusion, breakpoints {bands[0]}/{bands[1]})")
    return Finding(raw=raw, category="structural", abbreviation="rob",
                    chromosomes=chroms, bands=bands, interpretation=text, warnings=warnings)


def interpret_insertion(m: re.Match) -> Finding:
    raw = m.group(0)
    chroms = [c.strip() for c in m.group(1).split(';')]
    bands = [b.strip() for b in m.group(2).split(';')]
    text = f"Insertion involving {', '.join(chroms)} (bands {', '.join(bands)})"
    return Finding(raw=raw, category="structural", abbreviation="ins",
                    chromosomes=chroms, bands=bands, interpretation=text)


def interpret_dmin(m: re.Match) -> Finding:
    return Finding(raw=m.group(0), category="structural", abbreviation="dmin",
                    interpretation="Double minutes present (extrachromosomal gene amplification)")


def interpret_hsr(m: re.Match) -> Finding:
    raw = m.group(0)
    chrom, band = m.group(1), m.group(2)
    return Finding(raw=raw, category="structural", abbreviation="hsr",
                    chromosomes=[chrom], bands=[band],
                    interpretation=f"Homogeneously staining region on {_chrom_label(chrom)} at {band} (gene amplification)")


# Ordered so more specific patterns are tried before generic fallbacks.
KARYOTYPE_PATTERNS = [
    ("numerical", re.compile(rf'^([+-])(mar|{CHROM})$'), interpret_numerical),
    ("dmin", re.compile(r'^dmin$'), interpret_dmin),
    ("mar", re.compile(r'^(\d+)?mar$'), interpret_marker),
    ("hsr", re.compile(rf'^hsr\(({CHROM})\)\(({BAND})\)$'), interpret_hsr),
    ("translocation", re.compile(rf'^t\(({CHROM}(?:;{CHROM})+)\)\(([^;()]+(?:;[^;()]+)+)\)$'),
     interpret_translocation),
    ("insertion", re.compile(rf'^ins\(({CHROM}(?:;{CHROM})+)\)\(([^;()]+(?:;[^;()]+)*)\)$'),
     interpret_insertion),
    ("deletion", re.compile(rf'^del\(({CHROM})\)\(([^()]*)\)$'),
     interpret_two_band_structural("del", "Deletion")),
    ("duplication", re.compile(rf'^dup\(({CHROM})\)\(([^()]*)\)$'),
     interpret_two_band_structural("dup", "Duplication")),
    ("inversion", re.compile(rf'^inv\(({CHROM})\)\(([^()]*)\)$'),
     interpret_two_band_structural("inv", "Inversion")),
    ("addition", re.compile(rf'^add\(({CHROM})\)\(([^()]*)\)$'),
     interpret_two_band_structural("add", "Addition of unknown material")),
    ("isochromosome", re.compile(rf'^i\(({CHROM})\)\(({BAND})\)$'), interpret_isochromosome),
    ("ring", re.compile(rf'^r\(({CHROM})\)(?:\(([^()]*)\))?$'), interpret_ring),
    ("rob", re.compile(rf'^rob\(({CHROM};{CHROM})\)\(({BAND};{BAND})\)$'), interpret_rob),
    ("der_whole_arm", re.compile(rf'^der\(({CHROM};{CHROM})\)\(({BAND};{BAND})\)$'), interpret_der_whole_arm),
    ("der_single", re.compile(rf'^der\(({CHROM})\)(.*)$'), interpret_derivative_single),
]

SEX_RE = re.compile(r'^[XY]{1,5}$')
MODAL_RE = re.compile(r'^(\d{1,3})(?:~(\d{1,3}))?$')


def parse_karyotype_token(token: str) -> Finding:
    for name, pattern, fn in KARYOTYPE_PATTERNS:
        m = pattern.match(token)
        if m:
            return fn(m)
    return Finding(raw=token, category="unrecognized", interpretation="",
                    valid=False,
                    warnings=[f"'{token}' did not match any supported abnormality pattern."])


# ---------------------------------------------------------------------------
# FISH (ish / nuc ish) interpretation
# ---------------------------------------------------------------------------

# Small, illustrative, NON-EXHAUSTIVE reference table of well-known probe/
# gene loci and their typical clinical association. This is a starting
# scaffold, not a diagnostic database — always verify against the actual
# test's validated probe documentation. Keys are matched case-insensitively.
PROBE_KNOWLEDGE = {
    "BCR": "22q11.2 — commonly paired with ABL1 to detect BCR-ABL1 fusion (Philadelphia chromosome), associated with CML and a subset of ALL.",
    "ABL1": "9q34 — commonly paired with BCR to detect BCR-ABL1 fusion (Philadelphia chromosome), associated with CML and a subset of ALL.",
    "D13S319": "13q14.2 — frequently used to detect 13q14 deletion in chronic lymphocytic leukemia (CLL).",
    "D21S259": "21q22 — commonly used interphase FISH probe for detecting trisomy 21.",
    "HER2": "17q12 — amplification status is a standard biomarker in breast and gastric cancer.",
    "ERBB2": "17q12 — same locus as HER2; amplification is a standard breast/gastric cancer biomarker.",
    "TOP2A": "17q21 — often assessed alongside HER2 in breast cancer FISH panels.",
    "MYC": "8q24 — rearrangement or amplification associated with Burkitt lymphoma and other B-cell malignancies.",
    "IGH": "14q32 — frequent translocation partner in B-cell lymphomas (e.g. IGH-MYC, IGH-BCL2, IGH-CCND1).",
    "BCL2": "18q21 — commonly rearranged with IGH in follicular lymphoma.",
    "CCND1": "11q13 — commonly rearranged with IGH in mantle cell lymphoma.",
}

# Fusion-specific notes, keyed by a frozenset of the two probe names involved
# (case-insensitive). Checked when a FISH token uses "con"/"amp" notation.
FUSION_KNOWLEDGE = {
    frozenset({"ABL1", "BCR"}): "Classic probe combination for detecting BCR-ABL1 fusion "
                                 "(Philadelphia chromosome), characteristic of CML and seen in some ALL.",
    frozenset({"IGH", "MYC"}): "Associated with Burkitt lymphoma and other aggressive B-cell lymphomas.",
    frozenset({"IGH", "BCL2"}): "Associated with follicular lymphoma (t(14;18)).",
    frozenset({"IGH", "CCND1"}): "Associated with mantle cell lymphoma (t(11;14)).",
}


def _probe_knowledge_note(name: str) -> Optional[str]:
    return PROBE_KNOWLEDGE.get(name.strip().upper())


# Trailing result suffix: xN (copy count) or a single +/- (present/absent).
_RESULT_SUFFIX_RE = re.compile(r'(x\d+|[+-])$')
# Trailing (...) locus annotation, once any result suffix has been stripped.
_LOCUS_SUFFIX_RE = re.compile(r'\(([^()]*)\)$')
# What's left after stripping result/locus must look like a probe/gene name,
# optionally a "A con B" / "A amp B" pair.
_PROBE_NAME_RE = re.compile(r'^[A-Za-z0-9\-]+(?:\s(?:con|amp)\s[A-Za-z0-9\-]+)?$')
# A parenthesized probe list, optionally preceded by a band-locus at the top
# level (not inside any parens) -- task 15's "1p32(CDKN2Cx2)" form. The
# locus group matches "" (not None) when absent, e.g. a bare "(D13S319x1)".
_GROUP_WITH_LOCUS_RE = re.compile(r'([^(),]*)\(([^()]*)\)')


def interpret_fish_token(token: str, prefix_locus: Optional[str] = None) -> Finding:
    # Parse right-to-left: strip an optional result suffix, then an optional
    # locus in parens, and whatever remains must be a valid probe name. This
    # avoids the greedy-regex trap where a probe name like 'D21S259' would
    # otherwise swallow a trailing 'x3' result into its own name.
    #
    # `prefix_locus` (task 15) covers a different, also-real locus form:
    # "1p32(CDKN2Cx2),13q34(LAMP1x2)" -- a band-locus written *before* each
    # probe's own parens, at the caller's (parse_fish_only_clone's) level,
    # not inside this token at all. Only used when the token has no locus
    # of its own (the suffix form above), so the two never conflict.
    remainder = token
    result = None
    m = _RESULT_SUFFIX_RE.search(remainder)
    if m:
        result = m.group(1)
        remainder = remainder[:m.start()]
    locus = None
    m = _LOCUS_SUFFIX_RE.search(remainder)
    if m:
        locus = m.group(1)
        remainder = remainder[:m.start()]
    elif prefix_locus:
        locus = prefix_locus
    probes = remainder.strip()
    if not probes or not _PROBE_NAME_RE.match(probes):
        return Finding(raw=token, category="unrecognized", interpretation="",
                        valid=False,
                        warnings=[f"'{token}' did not match a recognized FISH probe/result pattern."])
    knowledge_note = None
    if " con " in probes:
        a, b = [p.strip() for p in probes.split("con")]
        base = f"Fusion signal between probes {a} and {b}"
        knowledge_note = FUSION_KNOWLEDGE.get(frozenset({a.upper(), b.upper()}))
    elif " amp " in probes:
        a, b = [p.strip() for p in probes.split("amp")]
        base = f"Co-localization/amplification signal between {a} and {b}"
        knowledge_note = FUSION_KNOWLEDGE.get(frozenset({a.upper(), b.upper()}))
    else:
        base = f"Probe {probes}"
        knowledge_note = _probe_knowledge_note(probes)
    if locus:
        base += f" (locus {locus})"
    if result is None:
        text = f"{base}: signal reported, count/status not specified"
        warnings = ["No '+/-' or 'xN' result given for this probe — result is ambiguous."]
    elif result.startswith('x'):
        n = result[1:]
        text = f"{base}: {n} signal(s) detected"
        warnings = []
    elif result == '+':
        text = f"{base}: signal present"
        warnings = []
    else:
        text = f"{base}: signal absent"
        warnings = []
    if knowledge_note:
        text += f" | Reference note (not diagnostic): {knowledge_note}"
    return Finding(raw=token, category="fish", abbreviation=probes,
                    interpretation=text, warnings=warnings,
                    bands=[locus] if locus else [])


def parse_fish_only_clone(raw: str) -> CloneResult:
    """Parses an ISH-only string, e.g.
    'nuc ish(D13S319x1,LAMP1x2)' or 'ish t(9;22)(q34;q11.2)(ABL1+,BCR+)'
    These have no leading modal chromosome number, but may carry their own
    trailing cell count, e.g. 'nuc ish(D21S259x3)[200]' — 200 interphase
    nuclei scored, a number worth keeping since it's typically different
    from (and larger than) a karyotype clone's metaphase count."""
    body = raw
    cell_count = None
    cc_match = re.search(r'\[(\d+)\]\s*$', body)
    if cc_match:
        cell_count = int(cc_match.group(1))
        body = body[:cc_match.start()].strip()

    is_nuc = False
    if body.startswith("nuc ish"):
        is_nuc = True
        body = body[len("nuc ish"):].strip()
    elif body.startswith("ish"):
        body = body[len("ish"):].strip()

    findings: List[Finding] = []
    errors: List[str] = []

    # Case 1: ish attached to a structural rearrangement, e.g. t(9;22)(q34;q11.2)(ABL1+,BCR+)
    struct_match = re.match(rf'^([a-z]+\([^)]*\)\([^)]*\))\(([^()]+(?:,[^()]+)*)\)$', body)
    if struct_match:
        struct_token, probe_blob = struct_match.groups()
        findings.append(parse_karyotype_token(struct_token))
        for p in split_top_level(probe_blob):
            findings.append(interpret_fish_token(p))
    else:
        # Case 2: parenthesized probe list(s): (probe1,probe2)(probe1,probe2)...
        # each optionally preceded by its own band-locus, e.g.
        # "1p32(CDKN2Cx2),13q34(LAMP1x2)" -- a common way labs report a
        # multi-locus interphase FISH panel. Capturing the locus text
        # alongside its group (task 15), not just the parenthesized part,
        # so it isn't silently dropped; a locus covers every probe in that
        # same group when more than one shares it, e.g. "1p32(A,B)".
        matches = list(_GROUP_WITH_LOCUS_RE.finditer(body))
        if not matches:
            errors.append(f"Could not find any probe list in '{raw}'.")
        for locus_text, g in (m.groups() for m in matches):
            locus_text = locus_text.strip() or None
            for p in split_top_level(g):
                findings.append(interpret_fish_token(p, prefix_locus=locus_text))

    return CloneResult(raw=raw, modal_number=None, modal_number_raw=None,
                        sex_chromosomes=None, cell_count=cell_count,
                        findings=findings, fish_only=True, errors=errors)


# ---------------------------------------------------------------------------
# Full karyotype clone parsing
# ---------------------------------------------------------------------------

def parse_karyotype_clone(raw: str) -> CloneResult:
    body = raw
    cell_count = None
    cc_match = re.search(r'\[(\d+)\]\s*$', body)
    if cc_match:
        cell_count = int(cc_match.group(1))
        body = body[:cc_match.start()].strip()

    tokens = split_top_level(body)
    errors: List[str] = []
    warnings: List[str] = []
    findings: List[Finding] = []

    modal_raw = tokens[0] if tokens else None
    modal_number = None
    if modal_raw:
        mm = MODAL_RE.match(modal_raw)
        if mm:
            modal_number = int(mm.group(1))
            if mm.group(2):
                warnings.append(f"Modal number given as a range ({modal_raw}); using {modal_number} for checks.")
        else:
            errors.append(f"'{modal_raw}' is not a valid modal chromosome number.")
    else:
        errors.append("Missing modal chromosome number.")

    sex = tokens[1] if len(tokens) > 1 else None
    if sex:
        if not SEX_RE.match(sex):
            errors.append(f"'{sex}' is not a valid sex chromosome constitution (expected e.g. XX, XY, XXY).")
    else:
        errors.append("Missing sex chromosome constitution.")

    remaining = tokens[2:]
    fish_only = False
    i = 0
    while i < len(remaining):
        tok = remaining[i]
        if tok == "ish" or tok.startswith("ish ") or tok.startswith("ish("):
            # Everything from here on is FISH content attached to this karyotype.
            fish_body = " ".join(remaining[i:])
            fish_body = re.sub(r'^ish\s*', '', fish_body).strip()
            for sub in re.findall(r'\(([^()]*)\)', fish_body):
                for p in split_top_level(sub):
                    findings.append(interpret_fish_token(p))
            break
        findings.append(parse_karyotype_token(tok))
        i += 1

    # Soft consistency check: count net numerical change vs stated modal number
    if modal_number is not None and sex:
        base = len(sex)  # sex chromosome count (2 for XX/XY, 3 for XXY, etc.)
        net_numeric = sum(1 if f.abbreviation == '+' else -1
                           for f in findings if f.category == "numerical")
        expected = 44 + base + net_numeric  # 44 autosomes + sex chromosomes, +/- numerical changes
        if abs(expected - modal_number) > 0 and not any(f.category == "unrecognized" for f in findings):
            warnings.append(
                f"Stated modal number ({modal_number}) doesn't match 44 autosomes + "
                f"{base} sex chromosome(s) adjusted for the numerical changes listed "
                f"(expected ~{expected}). This can be normal if structural events like "
                f"unbalanced translocations also change chromosome count, or der()/rob() "
                f"combos were used — but it's worth double-checking."
            )

    return CloneResult(raw=raw, modal_number=modal_number, modal_number_raw=modal_raw,
                        sex_chromosomes=sex, cell_count=cell_count,
                        findings=findings, fish_only=False,
                        errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# ISCN edition awareness (scaffold)
#
# Nomenclature has evolved across ISCN editions (e.g. 2016 / 2020 / 2024),
# and some conventions used in older reports differ from current guidance.
# This prototype does NOT attempt to fully model edition-by-edition grammar
# differences — that requires a domain expert working from the actual ISCN
# text for each edition. What's here is a small, clearly-labeled scaffold:
# a per-pattern "note" that can surface when relevant, plus an `edition`
# parameter threaded through so a real edition-difference table can be
# dropped in later without changing the calling code.
# ---------------------------------------------------------------------------

SUPPORTED_EDITIONS = ["2016", "2020", "2024"]
DEFAULT_EDITION = "2024"

# Illustrative only — extend this as edition-specific differences are
# confirmed against the actual ISCN volumes. Keyed by abbreviation.
EDITION_NOTES = {
    "rob": "Robertsonian translocations are expected to use explicit rob() "
           "notation under current ISCN guidance; some older reports instead "
           "used der() for the same event.",
}


def _edition_notes_for(findings: List[Finding]) -> List[str]:
    seen = set()
    notes = []
    for f in findings:
        if f.abbreviation in EDITION_NOTES and f.abbreviation not in seen:
            seen.add(f.abbreviation)
            notes.append(EDITION_NOTES[f.abbreviation])
    return notes


# ---------------------------------------------------------------------------
# Case-level clinical assessment
#
# Rolls per-finding structural/numerical results up into one case-level
# assessment: a plain-English summary, plus an explicit flag when findings
# match a small, sourced reference table of cytogenetic abnormalities named
# as recurrent in the WHO Classification of Haematolymphoid Tumours (5th
# ed., 2022) as characteristic of specific leukemias/lymphomas, or when the
# case meets the common clinical convention for a "complex karyotype"
# (>= 3 unrelated abnormalities in one clone).
#
# This is a REFERENCE NOTE, not a diagnosis, staging, or prognosis — it
# names a recurrently-associated pattern and nothing more. In particular it
# cannot and does not distinguish a constitutional finding from an acquired
# one (e.g. +21 here could be constitutional Down syndrome or an acquired
# finding in a blood specimen) — that needs clinical context (specimen
# type, patient history) this tool doesn't have.
# ---------------------------------------------------------------------------

COMPLEX_KARYOTYPE_MIN_ABNORMALITIES = 3


def _chrom_set_matcher(chroms, count=None):
    """Matches a structural finding with abbreviation 't' whose chromosome
    list, as a set, equals `chroms` (order-independent — t(9;22) and
    t(22;9) are the same event). `count`, if given, also requires
    len(chromosomes) == count, which is what tells t(16;16) (two entries,
    one chromosome) apart from some other lone chromosome-16 event."""
    chrom_set = set(chroms)

    def matcher(f: Finding) -> bool:
        if f.abbreviation != "t":
            return False
        if set(f.chromosomes) != chrom_set:
            return False
        if count is not None and len(f.chromosomes) != count:
            return False
        return True
    return matcher


def _single_chrom_matcher(abbreviation, chrom, category="structural"):
    def matcher(f: Finding) -> bool:
        return (f.category == category and f.abbreviation == abbreviation
                and f.chromosomes == [chrom])
    return matcher


def _any_of(*matchers):
    def matcher(f: Finding) -> bool:
        return any(m(f) for m in matchers)
    return matcher


# Each entry: (matcher, label, note). A finding is checked against every
# entry (in practice these are specific enough that at most one ever
# matches, but nothing relies on that). Starting set drawn from the
# recurrent genetic abnormalities named in the WHO Classification of
# Haematolymphoid Tumours (5th ed., 2022) — this table only names the
# pairing, never a stage/prognosis/treatment implication. Not exhaustive;
# see task 9 in TASKS.md for the list this was seeded from.
#
# Not every entry is a WHO-defined disease-subtype-specific fusion event
# like the ones above, though — trisomy 8 (task 22's follow-up) is a
# common recurrent finding across several myeloid neoplasms rather than
# a single defining lesion, so it's cited to its own, more accurate
# source (the IPSS-R cytogenetic risk scoring system for MDS) instead of
# the WHO-classification framing that fits the fusion-defined entries.
#
# Task 24 grew the table further by cross-checking it against what
# CIBMTR's own Disease Classification form (2402) asks transplant
# centers to report — a second, independent signal (real-world data-
# collection practice, not just the WHO text) for which findings are
# considered worth standardizing a field for. Each addition is cited to
# its own accurate primary source below, not just tagged "CIBMTR," since
# a form field confirms something is *tracked*, not why it matters
# clinically. The CLL entries (del(17p)/del(11q)/+12/del(13q)) are the
# first in this table for a lymphoid-not-myeloid leukemia; del(17p) in
# particular is deliberately worded to note it's not CLL-specific (TP53
# loss is adverse across CLL, MDS, and AML alike), unlike del(11q)/+12/
# del(13q), which are more specifically characteristic of CLL.
MALIGNANCY_KNOWLEDGE = [
    (_chrom_set_matcher({"9", "22"}, count=2),
     "t(9;22) — BCR-ABL1",
     "Recurrently associated with chronic myeloid leukemia (CML), and seen "
     "in a subset of acute lymphoblastic leukemia (ALL)."),
    (_chrom_set_matcher({"15", "17"}, count=2),
     "t(15;17) — PML-RARA",
     "Recurrently associated with acute promyelocytic leukemia (APL), a "
     "subtype of AML."),
    (_chrom_set_matcher({"8", "21"}, count=2),
     "t(8;21) — RUNX1-RUNX1T1",
     "Recurrently associated with acute myeloid leukemia (AML), "
     "core-binding-factor subtype."),
    (_any_of(_single_chrom_matcher("inv", "16"), _chrom_set_matcher({"16"}, count=2)),
     "inv(16)/t(16;16) — CBFB-MYH11",
     "Recurrently associated with acute myeloid leukemia (AML), "
     "core-binding-factor subtype."),
    (_chrom_set_matcher({"12", "21"}, count=2),
     "t(12;21) — ETV6-RUNX1",
     "Recurrently associated with pediatric B-lymphoblastic leukemia (B-ALL)."),
    (_chrom_set_matcher({"11", "14"}, count=2),
     "t(11;14) — CCND1-IGH",
     "Recurrently associated with mantle cell lymphoma."),
    (_chrom_set_matcher({"14", "18"}, count=2),
     "t(14;18) — IGH-BCL2",
     "Recurrently associated with follicular lymphoma."),
    (_any_of(_single_chrom_matcher("-", "7", category="numerical"), _single_chrom_matcher("del", "7")),
     "-7/del(7q)",
     "Recurrently associated with myelodysplastic syndrome (MDS) and AML, "
     "particularly therapy-related cases."),
    (_single_chrom_matcher("del", "5"),
     "del(5q)",
     "Recurrently associated with myelodysplastic syndrome (MDS) and AML."),
    (_single_chrom_matcher("+", "8", category="numerical"),
     "+8 (trisomy 8)",
     "One of the most common recurrent abnormalities in myeloid neoplasms "
     "(MDS, AML, MPN) — a scored cytogenetic risk category in the IPSS-R "
     "for MDS (Greenberg, Tuechler, Schanz et al., Blood 120:2454, 2012), "
     "rather than a single defining fusion event."),
    (_single_chrom_matcher("del", "17"),
     "del(17p)",
     "TP53 region loss — one of the most consistently adverse cytogenetic "
     "findings across chronic lymphocytic leukemia (CLL), MDS, and AML "
     "alike, not specific to any one of them (Döhner et al., N Engl J Med "
     "343:1910, 2000)."),
    (_single_chrom_matcher("del", "11"),
     "del(11q)",
     "ATM region loss — recurrently associated with a poor-prognosis "
     "subset of chronic lymphocytic leukemia (CLL) (Döhner et al., N Engl "
     "J Med 343:1910, 2000)."),
    (_single_chrom_matcher("+", "12", category="numerical"),
     "+12 (trisomy 12)",
     "Recurrently associated with chronic lymphocytic leukemia (CLL), "
     "intermediate prognosis in the Döhner hierarchy (Döhner et al., "
     "N Engl J Med 343:1910, 2000)."),
    (_single_chrom_matcher("del", "13"),
     "del(13q)",
     "The most common cytogenetic finding in chronic lymphocytic leukemia "
     "(CLL) — favorable prognosis when it's the sole abnormality (Döhner "
     "et al., N Engl J Med 343:1910, 2000)."),
    (_chrom_set_matcher({"8", "14"}, count=2),
     "t(8;14) — MYC-IGH",
     "The most common of Burkitt lymphoma's three MYC-partner "
     "translocations (~80% of cases)."),
    (_chrom_set_matcher({"2", "8"}, count=2),
     "t(2;8) — MYC-IGK",
     "One of Burkitt lymphoma's three MYC-partner translocations, a less "
     "common variant of t(8;14)."),
    (_chrom_set_matcher({"8", "22"}, count=2),
     "t(8;22) — MYC-IGL",
     "One of Burkitt lymphoma's three MYC-partner translocations, a less "
     "common variant of t(8;14)."),
    (_chrom_set_matcher({"4", "11"}, count=2),
     "t(4;11) — KMT2A-AFF1",
     "Recurrently associated with high-risk B-lymphoblastic leukemia "
     "(B-ALL), particularly in infants; one specific, well-characterized "
     "partner of KMT2A (MLL) rearrangements, which have many other "
     "possible partners not covered by this entry."),
    (_chrom_set_matcher({"1", "19"}, count=2),
     "t(1;19) — TCF3-PBX1",
     "Recurrently associated with B-lymphoblastic leukemia (B-ALL)."),
    (_single_chrom_matcher("del", "20"),
     "del(20q)",
     "Recurrently associated with myelodysplastic syndrome (MDS) and "
     "myeloproliferative neoplasms (MPN)."),
]


def _malignancy_matches_for_finding(f: Finding):
    return [(label, note) for matcher, label, note in MALIGNANCY_KNOWLEDGE if matcher(f)]


def assess_case(clones: List[CloneResult]) -> Dict[str, Any]:
    """Rolls the whole case (all clones parsed from one ISCN string) up
    into one assessment. See the module comment above for what this is
    (a reference-table lookup) and isn't (a diagnosis)."""
    matches: List[Dict[str, Any]] = []

    for idx, clone in enumerate(clones):
        recognized = [f for f in clone.findings if f.category in ("structural", "numerical")]
        for f in recognized:
            for label, note in _malignancy_matches_for_finding(f):
                matches.append({
                    "clone_index": idx,
                    "clone_raw": clone.raw,
                    "finding_raw": f.raw,
                    "label": label,
                    "note": f"Reference note (not diagnostic): {note}",
                })
        if len(recognized) >= COMPLEX_KARYOTYPE_MIN_ABNORMALITIES:
            matches.append({
                "clone_index": idx,
                "clone_raw": clone.raw,
                "finding_raw": None,
                "label": f"Complex karyotype ({len(recognized)} abnormalities)",
                "note": ("Reference note (not diagnostic): three or more unrelated "
                         "abnormalities in one clone is recurrently associated with "
                         "higher-risk myelodysplastic syndrome (MDS) and acute "
                         "myeloid leukemia (AML)."),
            })

    flagged = len(matches) > 0
    if flagged:
        summary = (f"{len(matches)} finding(s) in this case match a pattern this "
                   f"tool's reference table recurrently associates with hematologic "
                   f"malignancy — see below. This is a reference note, not a diagnosis.")
    else:
        summary = ("No findings in this case match a pattern in this tool's "
                   "hematologic-malignancy reference table.")

    return {"flagged": flagged, "summary": summary, "matches": matches}


# ---------------------------------------------------------------------------
# Candidate-line detection (task 8: PDF report upload; task 11: OCR fallback)
#
# Finds substrings shaped like an ISCN karyotype string inside a larger
# block of free text (e.g. text extracted from a lab report PDF, or OCR'd
# from a scanned one). This is deliberately loose — a real modal-number-
# then-sex-chromosome prefix is the strongest, simplest signal available,
# and full validation is already parse_iscn()'s job, not this function's.
# Candidates are surfaced for human review before ever being parsed; this
# never auto-corrects or trims what it finds (e.g. trailing prose caught
# on the same line), by design — see task 8's "Out of scope" in TASKS.md.
#
# Tolerates one thing beyond plain text-layer extraction: optional
# whitespace after the modal-number comma (e.g. "46, XY," not just
# "46,XY,"). That's not an auto-correction of the captured text — the
# candidate is still returned exactly as found — it's just widening what
# the detector will notice, because real Tesseract OCR output routinely
# inserts a stray space after a comma (confirmed empirically while
# building task 11) even when the source text-layer PDF never would.
#
# A real lab report PDF (Warde Medical Laboratory's report layout,
# confirmed against an actual example) hard-wraps a long ISCN string
# across several physical lines *within the PDF's own text layer* —
# nothing to do with OCR, nothing to do with how it's pasted anywhere;
# pypdf's extract_text() faithfully reproduces those embedded line
# breaks. A naive per-line scan (the original version of this function)
# grabbed only the first fragment and silently dropped everything after
# it. The continuation logic below recognizes when a candidate can't
# legally have ended where a physical line did — an unclosed '(', a
# trailing ',', or ending in the word "ish" (which per ISCN grammar is
# always followed by more content) — and keeps folding subsequent lines
# in until none of those hold anymore. Lines are joined with no
# separator by default (most real-world wraps land mid-token, e.g.
# "TP53x" + "2" -> "TP53x2") except right after "ish", which ISCN syntax
# always follows with a space before the probe/rearrangement content.
# This does not attempt perfect reconstruction in every case — it's a
# best-effort expansion of what gets surfaced for review, capped so it
# can never run away across an entire document.
#
# That cap turned out not to be enough on its own for OCR-sourced text
# (task 11): confirmed against real OCR output from an actual scanned
# report, a single misread character — Tesseract dropping/garbling one
# closing ')' — leaves the unbalanced-parens signal permanently true, so
# continuation never resolves on its own and runs all the way to the
# line cap, folding unrelated report sections (e.g. a "CULTURES" header
# and the lab's disclaimer footer) into one long garbled candidate —
# arguably worse than the original one-line truncation. The section-
# boundary check below is a second, independent stop condition: a
# standalone all-uppercase, digit-free line (e.g. "CULTURES", "COMMENT",
# "SIGNATURE" — a real, recurring pattern across this report's own
# sections) is specific enough to never collide with actual ISCN
# content, which always mixes in numbers. It stops the fold *before*
# consuming a line like that, regardless of what the paren-balance signal
# says, so a corrupted bracket can no longer drag unrelated sections in.
# ---------------------------------------------------------------------------

CANDIDATE_LINE_RE = re.compile(r'\b\d{2,3}(?:~\d{2,3})?,\s?[XY]{1,5}\b.*')

MAX_CANDIDATE_CONTINUATION_LINES = 15


def _candidate_needs_continuation(candidate: str) -> bool:
    """True if `candidate` can't legally have ended on the line it's on —
    a structural signal (unbalanced parens, a trailing list comma, or the
    "ish" keyword expecting more), not a guess about content."""
    stripped = candidate.rstrip()
    if not stripped:
        return False
    if stripped.count('(') > stripped.count(')'):
        return True
    if stripped.endswith(','):
        return True
    if re.search(r'\bish$', stripped):
        return True
    return False


def _continuation_separator(candidate: str) -> str:
    """How to join the next line onto `candidate`. Defaults to no
    separator (most wraps are mid-token); "ish" is the one case ISCN
    grammar guarantees a following space ("nuc ish "/"ish " always
    precede the probe/rearrangement content)."""
    if re.search(r'\bish$', candidate.rstrip()):
        return " "
    return ""


_CLOSING_BRACKET_RE = re.compile(r'\]')


def _trim_trailing_garbage(candidate: str) -> str:
    """Truncates `candidate` right after the first "[N]" cell count whose
    following content (ignoring whitespace) isn't a legal continuation —
    another clone ("/"), a combined karyotype+FISH clause ("."), or the
    end of the string. Never invents or alters any character of the
    candidate itself; only narrows where it ends.

    Confirmed against a real report (Diagnostic Cytogenetics
    Incorporated's template): its whole text layer emits "value"
    immediately followed by "Label:" with no separator throughout the
    document ("XX-XXXXCust. Specimen ID:", "11/08/2016Collection
    Date:", etc.) — a real, reproducible pypdf text-extraction ordering
    quirk in that software's PDF output, not something to guess at
    generally. It collides badly when it lands on the karyotype line
    itself: the section's own label glued directly onto a real, valid
    karyotype string with zero separator, all one physical line, so the
    naive "grab to end of line" rule (CANDIDATE_LINE_RE below) can't
    tell where the real content ends. ISCN grammar can: nothing legal
    follows a closed "[N]" except "/", ".", or end of string.

    Deliberately narrower than "trim any trailing prose caught on the
    line" (out of scope — see test_captures_rest_of_line_without_
    correction) — this only fires on that one specific, grammar-
    grounded signal, the same "structural signal, not a content guess"
    discipline the continuation-folding logic above already follows."""
    for m in _CLOSING_BRACKET_RE.finditer(candidate):
        rest = candidate[m.end():].lstrip()
        if rest and rest[0] not in '/.':
            return candidate[:m.end()]
    return candidate


# Small, explicit vocabulary of real report-section-header words this
# project has already confirmed recurring across real reports (the same
# list find_lab_interpretation()'s LAB_INTERPRETATION_TERMINATOR_RE uses
# below, plus task 22's own "abnormal results" instance, which already
# contains "results" as a substring so isn't listed separately) — a
# structural signal (these are real, recurring section labels, not a
# guess about arbitrary content), not a general "any capitalized word"
# rule, which would risk false-triggering on ordinary report prose.
_TRAILING_LABEL_RE = re.compile(
    r'(?<=\S)(?:signature|results|cultures|karyotypes|fish images|cpt codes)\s*:\s*$',
    re.IGNORECASE,
)


def _trim_trailing_known_label(candidate: str) -> str:
    """Truncates `candidate` right before a known report-section label
    (see `_TRAILING_LABEL_RE`) glued directly (zero whitespace — the
    `(?<=\\S)` lookbehind) onto its end. Confirmed against a second real
    report from the same software family as `_trim_trailing_garbage`
    above: its normal-result line reads
    "46,XX ; FEMALE KARYOTYPEResults:" — the section's own "Results:"
    label glued straight onto the end with zero separator, same quirk,
    just with no "[N]" cell count for that function to anchor on (a
    clean/normal karyotype has no cell count to report), so it was a
    no-op there.

    Deliberately narrower than trimming everything after the sex
    chromosomes, or any other guess about where "real" content ends —
    this only recognizes a *known* label, glued with *zero* separator,
    at the very end of the candidate. A label preceded by a real space
    (a standalone section header on its own effective content) or
    genuine trailing prose that happens to mention one of these words
    with normal spacing is left completely alone, same as any other
    trailing prose this tool has always declined to guess at (see
    test_captures_rest_of_line_without_correction) — the remaining
    content, if any, still gets the parser's normal error/warning
    treatment, never silently dropped."""
    m = _TRAILING_LABEL_RE.search(candidate)
    if m:
        return candidate[:m.start()].rstrip()
    return candidate


def _looks_like_section_boundary(line: str) -> bool:
    """True if `line` looks like a standalone report section header
    (e.g. "CULTURES", "COMMENT", "SIGNATURE") rather than more
    karyotype/FISH content — never fold a line like this into a
    candidate, no matter what the paren-balance signal says. All
    cased characters uppercase and no digits at all is specific enough
    to never match real ISCN content, which always mixes in numbers
    (locus bands, copy counts, cell counts)."""
    stripped = line.strip()
    if not stripped or any(ch.isdigit() for ch in stripped):
        return False
    return stripped.isupper()


def find_candidate_iscn_lines(text: str) -> List[str]:
    """Scan `text` line by line for substrings that look like they start an
    ISCN karyotype string (a modal number followed by a sex-chromosome
    constitution, e.g. "46,XY,"). Each match extends from that starting
    point to the end of its line — and, if the result still looks
    structurally incomplete there, folds in subsequent lines too (see
    module comment above) — in the order encountered. Never raises on
    unparseable/garbled input; worst case is an empty or noisy result,
    which is exactly what surfacing-for-review is meant to catch."""
    lines = text.splitlines()
    candidates = []
    i = 0
    while i < len(lines):
        m = CANDIDATE_LINE_RE.search(lines[i])
        if not m:
            i += 1
            continue
        candidate = m.group(0).strip()
        i += 1
        continuations = 0
        while (_candidate_needs_continuation(candidate)
               and i < len(lines)
               and not _looks_like_section_boundary(lines[i])
               and continuations < MAX_CANDIDATE_CONTINUATION_LINES):
            candidate = candidate.rstrip() + _continuation_separator(candidate) + lines[i].strip()
            i += 1
            continuations += 1
        candidate = _trim_trailing_known_label(candidate)
        candidate = _trim_trailing_garbage(candidate)
        if candidate:
            candidates.append(candidate)
    return candidates


# ---------------------------------------------------------------------------
# Lab-reported interpretation extraction (task 10)
#
# Looks for a section in an uploaded PDF's text introduced by a small,
# documented set of header strings real reports use for their own
# clinical interpretation, so it can be shown side-by-side with this
# tool's own case-level assessment (task 9) — never compared or scored
# automatically, just shown together for a human to read both.
#
# Revised after checking a second real report (a different lab/template
# than the Warde one this was first built against): "COMMENT" used to be
# a stop signal rather than a trigger, on the reasoning that Warde's
# COMMENT section was generic FDA/CLIA disclaimer boilerplate, not
# case-specific content. That doesn't generalize — this second report's
# COMMENT is a genuine, case-specific caveat ("We cannot rule out the
# possibility that the cells analyzed... are of maternal origin"),
# immediately following its INTERPRETATION line and preceding a named
# reviewer. Guessing which lab's "COMMENT" convention applies to a given
# PDF isn't reliable, and silently dropping real content is worse than
# occasionally including boilerplate a human can plainly see and ignore
# — so COMMENT is no longer a terminator; it's just included as part of
# the captured block, same as everything else between the header and the
# next real terminator.
#
# Also revised: the header regex used to require the header word ALONE
# on its own line ("INTERPRETATION" then the text below, Warde's style).
# That same second report instead writes "INTERPRETATION: <text>" inline
# on one line (its whole layout follows a "Label: value" convention
# throughout) — the old regex didn't match that at all, so this report's
# interpretation wasn't found even before the COMMENT question came up.
# Now matches either form: bare header (optionally with a trailing
# colon), or header + colon + inline content on the same line. Deliberately
# still requires an explicit colon for the inline-content form (not just
# "starts with the word interpretation") to avoid matching ordinary prose
# that happens to start with "Interpretation of these results...".
#
# The remaining terminator list (SIGNATURE, RESULTS, CULTURES,
# KARYOTYPES, FISH IMAGES, CPT CODES) is where extraction STOPS. A
# generic "any all-caps line" stop rule — like find_candidate_iscn_lines'
# own _looks_like_section_boundary — doesn't work here: a genuine
# sub-heading *within* an interpretation section (e.g. "OVERALL
# INTERPRETATION" itself, confirmed present in the Warde report) can also
# be all-uppercase, so a generic rule would cut extraction off after just
# the header line. A specific, small terminator list avoids that.
# ---------------------------------------------------------------------------

LAB_INTERPRETATION_HEADER_RE = re.compile(
    r'^(?:(?:overall|clinical)\s+)?interpretation\s*(?::\s*(?:\S.*)?)?$'
    r'|^clinical\s+correlation\s*(?::\s*(?:\S.*)?)?$',
    re.IGNORECASE,
)

LAB_INTERPRETATION_TERMINATOR_RE = re.compile(
    r'^(?:signature|results|cultures|karyotypes|fish images|cpt codes)\s*:?\s*$',
    re.IGNORECASE,
)

MAX_LAB_INTERPRETATION_LINES = 80


def find_lab_interpretation(text: str) -> Optional[str]:
    """Finds and extracts a lab-reported interpretation section from
    `text`, if the document has one. Returns None if no matching header
    is found — callers should surface that plainly (see task 10's Done
    when), not leave a blank space that reads as "nothing to report."
    Real-world PDF text extraction is noisy (page headers/footers can
    land mid-section — confirmed against an actual report); this doesn't
    attempt to clean that up, just bounds it with a line cap, consistent
    with this tool's "never silently patch extracted text" rule."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not LAB_INTERPRETATION_HEADER_RE.match(line.strip()):
            continue
        collected = [line.strip()]
        j = i + 1
        while (j < len(lines)
               and not LAB_INTERPRETATION_TERMINATOR_RE.match(lines[j].strip())
               and len(collected) < MAX_LAB_INTERPRETATION_LINES):
            collected.append(lines[j].strip())
            j += 1
        block = re.sub(r'\n{3,}', '\n\n', "\n".join(collected)).strip()
        return block if block else None
    return None


# ---------------------------------------------------------------------------
# Combined karyotype + FISH clone (ISCN's '<karyotype>.nuc ish ...' form)
#
# ISCN uses '/' to separate genuinely different clones (different cell
# populations), but a bare '.' to join a karyotype clone to a FISH result
# reported for that SAME cell population, e.g.:
#   46,XY[20].nuc ish 1p32(CDKN2Cx2),13q34(LAMP1x2)[200]
# — a 20-metaphase karyotype, followed by a 200-nucleus interphase FISH
# panel on the same specimen. Before this, parse_iscn() had no concept of
# this form at all: the whole string went through parse_karyotype_clone(),
# which has no notion of a trailing FISH clause, so everything from
# "nuc ish" onward got glued onto whatever top-level comma-token it
# happened to fall into (usually corrupting sex_chromosomes) and every
# individual FISH probe became "unrecognized".
#
# The '.' itself is unambiguous as a split point: real ISCN band sub-band
# decimals (e.g. '13q14.3') are always followed by more digits, never by
# the literal word "ish" — so searching for '.' immediately (optionally
# across whitespace, including a stray newline from a line-wrapped paste)
# followed by "ish"/"nuc ish" cannot collide with band notation.
# ---------------------------------------------------------------------------

COMBINED_KARYOTYPE_FISH_RE = re.compile(r'\.\s*(?=(?:nuc\s+ish|ish)\b)')


def parse_combined_karyotype_and_fish(raw: str, split_match) -> CloneResult:
    """Splits `raw` at `split_match` (a COMBINED_KARYOTYPE_FISH_RE match)
    into a karyotype clause and a FISH clause, parses each with the
    existing single-purpose functions, and merges them into one
    CloneResult — same cell population, not a separate clone."""
    karyo_part = raw[:split_match.start()].strip()
    fish_part = raw[split_match.end():].strip()

    karyo_clone = parse_karyotype_clone(karyo_part)
    fish_clone = parse_fish_only_clone(fish_part)

    return CloneResult(
        raw=raw,
        modal_number=karyo_clone.modal_number,
        modal_number_raw=karyo_clone.modal_number_raw,
        sex_chromosomes=karyo_clone.sex_chromosomes,
        cell_count=karyo_clone.cell_count,
        fish_cell_count=fish_clone.cell_count,
        findings=karyo_clone.findings + fish_clone.findings,
        fish_only=False,
        errors=karyo_clone.errors + fish_clone.errors,
        warnings=karyo_clone.warnings + fish_clone.warnings,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_iscn(raw: str, edition: str = DEFAULT_EDITION) -> Dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {"input": raw, "clones": [], "errors": ["Empty input."], "assessment": None}
    if edition not in SUPPORTED_EDITIONS:
        edition = DEFAULT_EDITION

    clone_strings = split_top_level(raw, sep='/')
    clone_objs: List[CloneResult] = []
    clones = []
    for cs in clone_strings:
        cs = cs.strip()
        combo_match = COMBINED_KARYOTYPE_FISH_RE.search(cs)
        if cs.startswith("ish") or cs.startswith("nuc ish"):
            clone = parse_fish_only_clone(cs)
        elif combo_match:
            clone = parse_combined_karyotype_and_fish(cs, combo_match)
        else:
            clone = parse_karyotype_clone(cs)
        clone_objs.append(clone)
        clone_dict = clone.to_dict()
        clone_dict["edition_notes"] = _edition_notes_for(clone.findings)
        clones.append(clone_dict)

    return {
        "input": raw,
        "edition": edition,
        "clone_count": len(clones),
        "is_mosaic": len(clones) > 1,
        "clones": clones,
        "assessment": assess_case(clone_objs),
    }
