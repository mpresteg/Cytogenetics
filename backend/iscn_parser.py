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
# These are commonly-cited approximate highest major band numbers per arm
# for a handful of frequently-rearranged chromosomes. They are NOT sourced
# from an authoritative ISCN idiogram in this prototype and should be
# verified against a current ISCN reference chart before any clinical use.
# The intent here is to catch obviously-impossible bands (e.g. 'q90' on a
# chromosome that tops out around q35), not to certify correctness.
# ---------------------------------------------------------------------------
APPROX_TERMINAL_BANDS = {
    "1": {"p": 36, "q": 44},
    "5": {"p": 15, "q": 35},
    "7": {"p": 22, "q": 36},
    "9": {"p": 24, "q": 34},
    "11": {"p": 15, "q": 25},
    "13": {"q": 34},
    "14": {"q": 32},
    "16": {"p": 13, "q": 24},
    "17": {"p": 13, "q": 25},
    "21": {"q": 22},
    "22": {"q": 13},
    "X": {"p": 22, "q": 28},
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


def interpret_fish_token(token: str) -> Finding:
    # Parse right-to-left: strip an optional result suffix, then an optional
    # locus in parens, and whatever remains must be a valid probe name. This
    # avoids the greedy-regex trap where a probe name like 'D21S259' would
    # otherwise swallow a trailing 'x3' result into its own name.
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
                    interpretation=text, warnings=warnings)


def parse_fish_only_clone(raw: str) -> CloneResult:
    """Parses an ISH-only string, e.g.
    'nuc ish(D13S319x1,LAMP1x2)' or 'ish t(9;22)(q34;q11.2)(ABL1+,BCR+)'
    These have no leading modal chromosome number."""
    body = raw
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
        groups = re.findall(r'\(([^()]*)\)', body)
        if not groups:
            errors.append(f"Could not find any probe list in '{raw}'.")
        for g in groups:
            for p in split_top_level(g):
                findings.append(interpret_fish_token(p))

    return CloneResult(raw=raw, modal_number=None, modal_number_raw=None,
                        sex_chromosomes=None, cell_count=None,
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
        if cs.startswith("ish") or cs.startswith("nuc ish"):
            clone = parse_fish_only_clone(cs)
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
