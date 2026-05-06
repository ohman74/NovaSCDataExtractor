"""Compare output/vehicle_metadata.json against the RSI ship-matrix flight-ready set.

Source of truth: https://robertsspaceindustries.com/ship-matrix/index
(cached to cache/rsi_flight_ready.json by the earlier download step.)

Usage:
    py compare_matrix.py                      # summary of all three diff categories
    py compare_matrix.py --matched            # list matched pairs
    py compare_matrix.py --ours-only          # list ships in our output not in matrix
    py compare_matrix.py --matrix-only        # list flight-ready ships missing from our output
    py compare_matrix.py --dupes              # list cases where >1 ClassName matches one matrix entry

Matching strategy:
    key = (manufacturer_code, normalized_name)

    manufacturer_code:
        - ours:   ClassName prefix (DRAK_Caterpillar -> DRAK)
        - matrix: manufacturer.code
        A manual alias table folds the handful of divergent codes.

    normalized_name:
        - lowercase
        - drop the first whitespace-separated token (the manufacturer's short name
          that our Name field carries but the matrix strips)
        - roman numerals -> arabic (Mk I -> Mk 1)
        - "BIS" / "Best In Show Edition" canonicalised
        - collapse non-alphanumerics to single spaces
        - fallback: sort the tokens to catch word-order swaps

    A match is either exact-normalized or fallback (sorted-tokens). Fallback
    matches are flagged so we can audit them.

Intentional exclusions:
    - In-game-only earnables (Teach's Ship Shop, Wikelo/Collector variants,
      Fleetweek paint variants) will appear in our output but not in the
      matrix. That is expected — not a bug.
"""

import json
import re
import sys
from collections import defaultdict


MATRIX_PATH = "cache/rsi_flight_ready.json"
OURS_PATH = "output/vehicle_metadata.json"
COSMETIC_VARIANTS_PATH = "cache/cosmetic_variants.json"

# ClassName-prefix -> matrix manufacturer_code aliases. Only put codes here
# that actually diverge (most align on their own).
MFR_ALIASES = {
    # (none yet — fill in as the comparison surfaces them)
}

# Per-ClassName override: the matrix entry this ClassName should pair with.
# Use when CIG's marketing name (matrix) differs from the in-game localised
# name but both describe the same ship. Our Name is authoritative for the
# extractor output; this map only drives comparison.
_CLASSNAME_TO_MATRIX_NAME = {
    # Matrix abbreviates, our resolved Name is longer — both correct.
    "ANVL_C8R_Pisces":                "C8R Pisces",
    "ANVL_Hornet_F7CM_Heartseeker":   "F7C-M Super Hornet Heartseeker Mk I",
    "ANVL_Hornet_F7CM_Mk2_Heartseeker": "F7C-M Super Hornet Heartseeker Mk II",
    "ANVL_Valkyrie_CitizenCon":       "Valkyrie Liberator Edition",
    "CRUS_Starlifter_A2":             "A2 Hercules",
    "CRUS_Starlifter_C2":             "C2 Hercules",
    "CRUS_Starlifter_M2":             "M2 Hercules",
    "CRUS_Starfighter_Inferno":       "Ares Inferno",
    "CRUS_Starfighter_Ion":           "Ares Ion",
    "CRUS_Star_Runner":               "Mercury",
    "DRAK_Dragonfly":                 "Dragonfly Black",
    "ORIG_85X":                       "85X",
    "ORIG_m50":                       "M50",
    # Matrix splits the 600i into two purchasable SKUs (Area 18). Our base
    # ORIG_600i is the Explorer variant; ORIG_600i_Touring matches directly.
    "ORIG_600i":                      "600i Explorer",
    # CIG's localised vehicleName literally omits "Black": "Drake Cutlass
    # 2949 Best In Show Edition". Our extractor preserves the localised
    # string; the matrix uses the fuller name.
    "DRAK_Cutlass_Black_ShipShowdown": "Cutlass Black Best In Show Edition 2949",
    # Matrix name for the Yellowjacket adds the "jacket" suffix we don't have.
    "DRAK_Dragonfly_Yellow":           "Dragonfly Yellowjacket",
}

# Matrix entries intentionally excluded from the "matrix-only" gap report.
# These are SKUs that don't correspond to a separate game record (bundle
# packaging, cosmetic-only color editions, power-suit exoskeletons without
# customisable components). Keyed by matrix id for stability.
_MATRIX_IGNORE_IDS = {
    204,  # ANVL Carrack w/C8X                 (bundle SKU)
    205,  # ANVL Carrack Expedition w/C8X     (bundle SKU)
    277,  # ARGO ATLS                          (power suit, no components)
    296,  # ARGO ATLS GEO                      (power suit, no components)
    202,  # ARGO Mole Carbon Edition           (cosmetic color variant)
    203,  # ARGO Mole Talus Edition            (cosmetic color variant)
    172,  # CNOU Mustang Alpha Vindicator      (not in game data)
}

# ClassNames that legitimately appear in our output but are not in the RSI
# ship-matrix. All are earnable in-game ships — variants obtained from
# Wikelo's Web (*_Collector_*), Teach's Ship Shop (*_Teach), Pyro faction
# Exec missions (*_Exec_*), or similar in-game sources. Not on the pledge
# store (hence matrix-absent) but legitimate player-flyable vehicles.
_OURS_IGNORE_CLASSNAMES = frozenset({
    # Wikelo's Web — Collector variants
    "AEGS_Idris_P_Collector_Military",
    "AEGS_Sabre_Firebird_Collector_Milt",
    "AEGS_Sabre_Peregrine_Collector_Competition",
    "ANVL_Asgard_Collector_Military",
    "ANVL_Hornet_F7_Mk2_Collector_Mod",
    "ANVL_Lightning_F8C_Collector_Military",
    "ANVL_Lightning_F8C_Collector_Stealth",
    "ANVL_Terrapin_Medic_Collector_Medic",
    "ARGO_RAFT_Collector_Indust",
    "CRUS_Intrepid_Collector_Indust",
    "CRUS_Spirit_C1_Civilian",
    "CRUS_Starfighter_Inferno_Collector_Military",
    "CRUS_Starfighter_Ion_Collector_Stealth",
    "CRUS_Starlifter_A2_Collector_Military",
    "DRAK_Golem_Collector_Indust",
    "ESPR_Prowler_Utility_Collector_Indust",
    "KRIG_L21_Wolf_Collector_Military",
    "KRIG_L21_Wolf_Collector_Stealth",
    "MISC_Fortune_Collector_Industrial",
    "MISC_Prospector_Collector_Indust",
    "MISC_Starlancer_Max_Collector_Indust",
    "MISC_Starlancer_TAC_Collector_Military",
    "MRAI_Guardian_Military",
    "MRAI_Guardian_MX_Collector_Military",
    "MRAI_Guardian_QI_Collector_Indust",
    "MRAI_Pulse_Collector_Civ",
    "RSI_Apollo_Triage_Collector_Stealth",
    "RSI_Constellation_Taurus_Military",
    "RSI_Meteor_Collector_Stealth",
    "RSI_Scorpius_Stealth",
    "RSI_Ursa_Medivac_Stealth",
    "RSI_Zeus_ES_Collector_Indust",
    "XIAN_Nox_Collector_Mod",
    # Teach's Ship Shop — Nyx
    "AEGS_Reclaimer_Teach",
    "ARGO_MOLE_Teach",
    "CNOU_Nomad_Teach",
    "DRAK_Golem_Teach",
    "DRAK_Vulture_Teach",
    "MISC_Fortune_Teach",
    "MISC_Starfarer_Teach",
    # Pyro faction — PYAM Exec variants
    "ANVL_Hornet_F7A_Mk2_Exec_Military",
    "ANVL_Hornet_F7A_Mk2_Exec_Stealth",
    "ANVL_Lightning_F8C_Exec_Military",
    "ANVL_Lightning_F8C_Exec_Stealth",
    "DRAK_Corsair_Exec_Military",
    "DRAK_Corsair_Exec_StealthIndustrial",
    "DRAK_Cutlass_Black_Exec_Military",
    "DRAK_Cutlass_Black_Exec_Stealth",
    "GAMA_Syulen_Exec_Military",
    "GAMA_Syulen_Exec_Stealth",
    "RSI_Meteor_Collector_Military",        # Pyro Exec despite _Collector_ naming
    # Other in-game earnables
    "AEGS_Gladius_Dunlevy",                 # recruitment reward
    "ANVL_Hornet_F7CM_Mk2_Heartseeker",     # in-game Mk II Heartseeker variant
})

# Short manufacturer name that our Name field uses as a prefix, per mfr code.
# (Normalized: lowercase, non-alphanumerics -> single space.)
# Our Name is "Drake Caterpillar" / "C.O. Mustang Alpha" / "MISC Freelancer";
# matrix name strips this. Drop it from our side to line up.
_MFR_SHORT = {
    "AEGS": "aegis",
    "ANVL": "anvil",
    "ARGO": "argo",
    "BANU": "banu",
    "CNOU": "c o",          # "C.O." -> periods collapse to space
    "CRUS": "crusader",
    "DRAK": "drake",
    "ESPR": "esperia",
    "GAMA": "gatac",
    "GREY": "grey",         # our Name: "Grey's Shiv" -> "grey s shiv"
    "GRIN": "greycat",
    "KRIG": "kruger",
    "MISC": "misc",
    "MRAI": "mirai",
    "ORIG": "origin",
    "RSI": "rsi",
    "TMBL": "tumbril",
    "VNCL": "vanduul",
    "XNAA": "aopoa",
}

# Reverse lookup: first-word-of-Name -> canonical matrix mfr code.
# Used when the ClassName prefix diverges from the ship's actual brand
# (CIG reuses `MISC_*` classnames for Mirai ships, `VNCL_*` classnames for
# Esperia-branded Vanduul ships, `XIAN_*` for Aopoa ships, etc.).
_NAME_PREFIX_TO_MFR = {
    "aegis": "AEGS",
    "anvil": "ANVL",
    "argo": "ARGO",
    "banu": "BANU",
    "c": "CNOU",            # "C.O." -> "c o" -> first token is "c"
    "crusader": "CRUS",
    "drake": "DRAK",
    "esperia": "ESPR",
    "gatac": "GAMA",
    "grey": "GREY",
    "greycat": "GRIN",
    "kruger": "KRIG",
    "misc": "MISC",
    "mirai": "MRAI",
    "origin": "ORIG",
    "rsi": "RSI",
    "tumbril": "TMBL",
    "vanduul": "VNCL",
    "aopoa": "XNAA",
}


def _normalize(name: str, mfr_code: str = "") -> str:
    """Lowercase, strip known mfr short-name prefix, strip noise, canonicalise.

    mfr_code: pass the ClassName prefix for our side to enable stripping.
              Matrix names don't carry the manufacturer, so pass "".
    """
    if not name:
        return ""
    n = name.strip().lower()
    # Collapse non-alphanumerics to single space (handles "C.O." -> "c o").
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    # Strip the known short manufacturer prefix from the front.
    if mfr_code:
        short = _MFR_SHORT.get(mfr_code, "")
        if short:
            prefix = short + " "
            if n.startswith(prefix):
                n = n[len(prefix):]
            elif n == short:
                n = ""
            # Drop leftover "s " from possessive-s (e.g. "Grey's" -> "grey s").
            if n.startswith("s "):
                n = n[2:]
    # Roman numerals (bounded on both sides) → arabic.
    padded = f" {n} "
    for k, v in [(" i ", " 1 "), (" ii ", " 2 "), (" iii ", " 3 "),
                  (" iv ", " 4 "), (" v ", " 5 "),
                  (" mk i ", " mk 1 "), (" mk ii ", " mk 2 "), (" mk iii ", " mk 3 ")]:
        padded = padded.replace(k, v)
    n = padded.strip()
    # BIS abbreviation
    n = n.replace(" bis ", " best in show edition ")
    # Canonicalise "<year> best in show edition" -> "best in show edition <year>"
    n = re.sub(r"(\d{4}) best in show edition", r"best in show edition \1", n)
    # Pirate Edition / Pirate
    n = n.replace("pirate edition", "pirate")
    return " ".join(n.split())


def _sorted_tokens(normalized: str) -> str:
    return " ".join(sorted(normalized.split()))


def _mfr_code_for_ours(class_name: str, name: str) -> str:
    """Resolve our ClassName/Name pair to the matrix manufacturer_code.

    Prefer the brand token from Name (first alphanum token) since CIG
    occasionally packs ships under a different ClassName prefix than the
    actual brand (MISC_Fury is Mirai-branded, VNCL_Blade is Esperia-branded,
    XIAN_Nox is Aopoa-branded). Fall back to the ClassName prefix if the
    Name doesn't start with a known brand.
    """
    if name:
        tokens = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
        if tokens:
            code = _NAME_PREFIX_TO_MFR.get(tokens[0])
            if code:
                return code
    prefix = class_name.split("_", 1)[0] if "_" in class_name else class_name
    return MFR_ALIASES.get(prefix, prefix)


def _load():
    with open(MATRIX_PATH, "r", encoding="utf-8") as f:
        matrix = json.load(f)
    with open(OURS_PATH, "r", encoding="utf-8") as f:
        ours = json.load(f)
    # Optional: list of ClassNames the extractor identified as cosmetic
    # variants of another ship and intentionally dropped. Used to auto-
    # exclude their matrix counterparts from the gap report (algorithmic,
    # so no need to hardcode per-SKU ignore ids here).
    import os as _os
    cosmetic_variants = []
    if _os.path.isfile(COSMETIC_VARIANTS_PATH):
        with open(COSMETIC_VARIANTS_PATH, "r", encoding="utf-8") as f:
            cosmetic_variants = json.load(f)
    return matrix, ours, cosmetic_variants


def _build_indexes(matrix, ours):
    # matrix: (mfr_code, normalized) -> matrix_entry
    # matrix_sorted: (mfr_code, sorted_tokens) -> matrix_entry  (fallback)
    matrix_exact = {}
    matrix_fallback = {}
    for m in matrix:
        code = m["manufacturer_code"]
        # Matrix names occasionally carry the manufacturer prefix too
        # ("Anvil Ballista Dunestalker"). Strip it symmetrically.
        n = _normalize(m["name"], mfr_code=code)
        if not n:
            continue
        matrix_exact.setdefault((code, n), m)
        matrix_fallback.setdefault((code, _sorted_tokens(n)), m)

    ours_normalised = []
    for r in ours:
        cn = r.get("ClassName", "")
        name = r.get("Name", "")
        code = _mfr_code_for_ours(cn, name)
        n = _normalize(name, mfr_code=code)
        ours_normalised.append({
            "ClassName": cn,
            "Name": name,
            "mfr_code": code,
            "normalized": n,
            "sorted_tokens": _sorted_tokens(n),
        })
    return matrix_exact, matrix_fallback, ours_normalised


def _classify(matrix_exact, matrix_fallback, ours_normalised,
              cosmetic_variant_keys=None):
    matched = []             # list of (our_entry, matrix_entry, match_kind)
    unmatched_ours = []      # list of our_entry
    matched_matrix_keys = set()
    cosmetic_variant_keys = cosmetic_variant_keys or set()

    for o in ours_normalised:
        m = None
        kind = "exact"
        # Explicit override: CIG's marketing (matrix) name differs from our
        # in-game localised name, but both refer to the same ship.
        override = _CLASSNAME_TO_MATRIX_NAME.get(o["ClassName"])
        if override:
            override_key = (o["mfr_code"],
                            _normalize(override, mfr_code=o["mfr_code"]))
            m = matrix_exact.get(override_key)
            kind = "mapped"
        if not m:
            key_exact = (o["mfr_code"], o["normalized"])
            m = matrix_exact.get(key_exact)
            kind = "exact"
        if not m:
            key_fallback = (o["mfr_code"], o["sorted_tokens"])
            m = matrix_fallback.get(key_fallback)
            kind = "fuzzy"
        if m:
            matched.append((o, m, kind))
            matched_matrix_keys.add((m["manufacturer_code"], _normalize(m["name"], mfr_code=m["manufacturer_code"])))
        elif o["ClassName"] in _OURS_IGNORE_CLASSNAMES:
            # Legitimately in our output but not in matrix (earnable in-game).
            pass
        else:
            unmatched_ours.append(o)

    # Matrix entries with no match on our side.
    unmatched_matrix = []
    for m in sorted(matrix_fallback.values(), key=lambda x: (x["manufacturer_code"], x["name"])):
        if m["id"] in _MATRIX_IGNORE_IDS:
            continue
        k = (m["manufacturer_code"], _normalize(m["name"], mfr_code=m["manufacturer_code"]))
        if k in matched_matrix_keys:
            continue
        # Algorithmic cosmetic-SKU auto-ignore: if a ClassName the
        # extractor filtered as a cosmetic variant normalises to the same
        # key as this matrix entry, the matrix SKU is represented by the
        # base ship we emitted — not a gap.
        if k in cosmetic_variant_keys:
            continue
        unmatched_matrix.append(m)

    # Duplicate collapse: multiple ClassNames -> same matrix entry.
    by_matrix_id = defaultdict(list)
    for o, m, kind in matched:
        by_matrix_id[m["id"]].append((o, m, kind))
    dupes = [group for group in by_matrix_id.values() if len(group) > 1]

    return matched, unmatched_ours, unmatched_matrix, dupes


def _print_summary(matched, unmatched_ours, unmatched_matrix, dupes):
    total_ours = len(matched) + len(unmatched_ours)
    exact = sum(1 for _, _, k in matched if k == "exact")
    mapped = sum(1 for _, _, k in matched if k == "mapped")
    fuzzy = sum(1 for _, _, k in matched if k == "fuzzy")
    print(f"Our vehicles:            {total_ours}")
    print(f"Matrix flight-ready:     {len(matched) + len(unmatched_matrix)}")
    print()
    print(f"  Matched (exact):       {exact}")
    print(f"  Matched (mapped):      {mapped}")
    print(f"  Matched (fuzzy):       {fuzzy}")
    print(f"  Ours, no matrix match: {len(unmatched_ours)}")
    print(f"  Matrix, no ours match: {len(unmatched_matrix)}")
    print(f"  Multi-ours -> 1 matrix: {len(dupes)} (covering "
          f"{sum(len(g) for g in dupes)} ClassNames)")


def _print_matched(matched):
    print(f"=== Matched ({len(matched)}) ===")
    for o, m, kind in sorted(matched, key=lambda t: (t[0]["mfr_code"], t[1]["name"])):
        tag = "" if kind == "exact" else "  [fuzzy]"
        print(f"  {o['ClassName']:45}  ->  {m['manufacturer_code']} {m['name']}{tag}")


def _print_ours_only(unmatched_ours):
    print(f"=== In our output, not in matrix ({len(unmatched_ours)}) ===")
    by_mfr = defaultdict(list)
    for o in unmatched_ours:
        by_mfr[o["mfr_code"]].append(o)
    for code in sorted(by_mfr):
        print(f"\n  {code}:")
        for o in sorted(by_mfr[code], key=lambda x: x["ClassName"]):
            print(f"    {o['ClassName']:45}  Name={o['Name']!r}")


def _print_matrix_only(unmatched_matrix):
    print(f"=== In matrix, not in our output ({len(unmatched_matrix)}) ===")
    by_mfr = defaultdict(list)
    for m in unmatched_matrix:
        by_mfr[m["manufacturer_code"]].append(m)
    for code in sorted(by_mfr):
        print(f"\n  {code}:")
        for m in sorted(by_mfr[code], key=lambda x: x["name"]):
            print(f"    {m['name']}")


def _print_dupes(dupes):
    print(f"=== Multi-ours -> 1 matrix ({len(dupes)} groups) ===")
    for group in sorted(dupes, key=lambda g: (g[0][1]["manufacturer_code"], g[0][1]["name"])):
        m = group[0][1]
        print(f"\n  {m['manufacturer_code']} {m['name']}  (matrix id={m['id']}):")
        for o, _, kind in group:
            tag = "" if kind == "exact" else "  [fuzzy]"
            print(f"    {o['ClassName']:45}  Name={o['Name']!r}{tag}")


def main(argv):
    matrix, ours, cosmetic_variants = _load()
    matrix_exact, matrix_fallback, ours_normalised = _build_indexes(matrix, ours)
    # Build lookup keys for cosmetic-variant ClassNames. When a filtered
    # ClassName has an explicit mapping in _CLASSNAME_TO_MATRIX_NAME use
    # that; otherwise fall back to a synthetic name from the ClassName
    # (strip mfr prefix + underscores-to-spaces). Same normalisation
    # pipeline as ours_normalised so matrix entries align by (mfr_code,
    # normalized).
    cosmetic_variant_keys = set()
    for cn in cosmetic_variants:
        code = _mfr_code_for_ours(cn, "")
        override = _CLASSNAME_TO_MATRIX_NAME.get(cn)
        if override:
            cosmetic_variant_keys.add(
                (code, _normalize(override, mfr_code=code))
            )
            continue
        synthetic_name = cn.split("_", 1)[1].replace("_", " ") if "_" in cn else cn
        cosmetic_variant_keys.add((code, _normalize(synthetic_name)))
    matched, unmatched_ours, unmatched_matrix, dupes = _classify(
        matrix_exact, matrix_fallback, ours_normalised, cosmetic_variant_keys
    )

    if len(argv) == 1:
        _print_summary(matched, unmatched_ours, unmatched_matrix, dupes)
        return

    flag = argv[1]
    if flag == "--matched":
        _print_matched(matched)
    elif flag == "--ours-only":
        _print_ours_only(unmatched_ours)
    elif flag == "--matrix-only":
        _print_matrix_only(unmatched_matrix)
    elif flag == "--dupes":
        _print_dupes(dupes)
    else:
        print(f"Unknown flag: {flag}", file=sys.stderr)
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
