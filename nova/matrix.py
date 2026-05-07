"""RSI ship-matrix fetcher.

The ship-matrix is CIG's authoritative list of pledge-store ships and their
production status (`flight-ready` vs `in-concept`). It's fetched once per
extractor run and cached at `<cache_root>/rsi_flight_ready.json`. Both Live
and PTU channels read the same cache file — the matrix is channel-agnostic.

The build uses this data to tag emitted ships with `FlightReady: true` and
to populate Store / Career / Role / Cargo placeholders in
`vehicle_metadata.json` and `vehicle_stats.json`.
"""
import json
import os

import requests


MATRIX_URL = "https://robertsspaceindustries.com/ship-matrix/index"
MATRIX_CACHE_NAME = "rsi_flight_ready.json"
USER_AGENT = "NovaSCDataExtractor/0.1"


def _matrix_cache_path(cache_root):
    return os.path.join(cache_root, MATRIX_CACHE_NAME)


def _normalize_entry(entry):
    """Flatten manufacturer.{code,name} to top-level fields and prefix the
    relative pledge-store path to a full URL.

    The wrapped API returns each ship with a nested `manufacturer` object
    and a relative `url` like `/pledge/ships/rsi-aurora/...`. We add
    `manufacturer_code` / `manufacturer_name` / `store_url` at the top
    level so callers don't have to repeat the unwrap.
    """
    out = dict(entry)
    mfr = entry.get("manufacturer") or {}
    out["manufacturer_code"] = (mfr.get("code") or "").strip()
    out["manufacturer_name"] = (mfr.get("name") or "").strip()
    rel = (entry.get("url") or "").strip()
    if rel.startswith("/"):
        out["store_url"] = "https://robertsspaceindustries.com" + rel
    else:
        out["store_url"] = rel
    return out


def fetch_matrix(cache_root):
    """Fetch the RSI ship-matrix and write it to the cache root.

    Called once per extractor run, before the channel loop. Live and PTU
    runs share the same cached file.

    Returns the normalized list of ship entries on success. On network
    failure, falls back to the existing cached file if one exists. If
    neither fetch nor cache works, prints a warning and returns None —
    the build continues without matrix data, and tagged fields are
    simply omitted from output.
    """
    path = _matrix_cache_path(cache_root)
    print(f"\n[MATRIX] Fetching RSI ship-matrix from {MATRIX_URL}...")
    try:
        resp = requests.get(
            MATRIX_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("success") != 1:
            raise RuntimeError(
                f"matrix returned success={payload.get('success')!r}, "
                f"msg={payload.get('msg')!r}"
            )
        data = payload.get("data") or []
        normalized = [_normalize_entry(e) for e in data]

        os.makedirs(cache_root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)

        n_fr = sum(1 for e in normalized if e.get("production_status") == "flight-ready")
        n_ic = sum(1 for e in normalized if e.get("production_status") == "in-concept")
        print(f"  Cached {len(normalized)} ships -> {path}")
        print(f"  ({n_fr} flight-ready, {n_ic} in-concept)")
        return normalized

    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"  [WARN] Fetch failed: {exc}")
        cached = load_matrix(cache_root)
        if cached is not None:
            print(f"  Falling back to existing cache: {path}")
            return cached
        print(f"  No cached matrix available — build will continue without matrix tags.")
        return None


def load_matrix(cache_root):
    """Load the cached matrix file. Returns the list, or None if missing
    or unreadable. Does not perform a network fetch — call `fetch_matrix`
    first to populate the cache."""
    path = _matrix_cache_path(cache_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ───────────────────────── matching: matrix ↔ our records ──────────────

import re


# ClassName-prefix → matrix manufacturer_code aliases. Most align on their own.
MFR_ALIASES = {}

# Per-ClassName override: the matrix entry this ClassName should pair with.
# Used when CIG's marketing name (matrix) differs from the in-game localised
# name but both describe the same ship.
_CLASSNAME_TO_MATRIX_NAME = {
    "ANVL_C8R_Pisces":                  "C8R Pisces",
    "ANVL_Hornet_F7CM_Heartseeker":     "F7C-M Super Hornet Heartseeker Mk I",
    "ANVL_Hornet_F7CM_Mk2_Heartseeker": "F7C-M Super Hornet Heartseeker Mk II",
    "ANVL_Valkyrie_CitizenCon":         "Valkyrie Liberator Edition",
    "CRUS_Starlifter_A2":               "A2 Hercules",
    "CRUS_Starlifter_C2":               "C2 Hercules",
    "CRUS_Starlifter_M2":               "M2 Hercules",
    "CRUS_Starfighter_Inferno":         "Ares Inferno",
    "CRUS_Starfighter_Ion":             "Ares Ion",
    "CRUS_Star_Runner":                 "Mercury",
    "DRAK_Dragonfly":                   "Dragonfly Black",
    "ORIG_85X":                         "85X",
    "ORIG_m50":                         "M50",
    # Matrix splits the 600i into two purchasable SKUs (Area 18). Our base
    # ORIG_600i is the Explorer variant; ORIG_600i_Touring matches directly.
    "ORIG_600i":                        "600i Explorer",
    # Matrix uses fuller "Best In Show Edition" naming.
    "DRAK_Cutlass_Black_ShipShowdown":  "Cutlass Black Best In Show Edition 2949",
    "DRAK_Dragonfly_Yellow":            "Dragonfly Yellowjacket",
}

# ClassNames legitimately in our output but absent from the RSI ship-matrix.
# All are earnable in-game ships — not on the pledge store. They get
# `FlightReady: true` even without a matrix match.
_INGAME_FLIGHT_READY = frozenset({
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

# Short manufacturer name our Name field uses as a prefix, per mfr code.
# (Normalized: lowercase, non-alphanumerics → single space.)
_MFR_SHORT = {
    "AEGS": "aegis",
    "ANVL": "anvil",
    "ARGO": "argo",
    "BANU": "banu",
    "CNOU": "c o",          # "C.O." → periods collapse to space
    "CRUS": "crusader",
    "DRAK": "drake",
    "ESPR": "esperia",
    "GAMA": "gatac",
    "GREY": "grey",
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

# Reverse lookup: first-word-of-Name → canonical matrix mfr code. Used when
# the ClassName prefix diverges from the ship's actual brand (MISC_Fury is
# Mirai-branded, VNCL_Blade is Esperia-branded, XIAN_Nox is Aopoa-branded).
_NAME_PREFIX_TO_MFR = {
    "aegis":    "AEGS",
    "anvil":    "ANVL",
    "argo":     "ARGO",
    "banu":     "BANU",
    "c":        "CNOU",     # "C.O." → "c o" → first token is "c"
    "crusader": "CRUS",
    "drake":    "DRAK",
    "esperia":  "ESPR",
    "gatac":    "GAMA",
    "grey":     "GREY",
    "greycat":  "GRIN",
    "kruger":   "KRIG",
    "misc":     "MISC",
    "mirai":    "MRAI",
    "origin":   "ORIG",
    "rsi":      "RSI",
    "tumbril":  "TMBL",
    "vanduul":  "VNCL",
    "aopoa":    "XNAA",
}

# Sentinel matrix entry for in-game earnables (not on pledge store).
_INGAME_ENTRY = {
    "production_status": "flight-ready",
    "_source": "ingame",
}


def _normalize(name, mfr_code=""):
    """Lowercase, strip known mfr short-name prefix, strip noise, canonicalise.

    `mfr_code` is the ClassName prefix on our side; pass "" for matrix
    names (matrix names already strip the manufacturer).
    """
    if not name:
        return ""
    n = name.strip().lower()
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    if mfr_code:
        short = _MFR_SHORT.get(mfr_code, "")
        if short:
            prefix = short + " "
            if n.startswith(prefix):
                n = n[len(prefix):]
            elif n == short:
                n = ""
            if n.startswith("s "):
                n = n[2:]
    padded = f" {n} "
    for k, v in [(" i ", " 1 "), (" ii ", " 2 "), (" iii ", " 3 "),
                 (" iv ", " 4 "), (" v ", " 5 "),
                 (" mk i ", " mk 1 "), (" mk ii ", " mk 2 "), (" mk iii ", " mk 3 ")]:
        padded = padded.replace(k, v)
    n = padded.strip()
    n = n.replace(" bis ", " best in show edition ")
    n = re.sub(r"(\d{4}) best in show edition", r"best in show edition \1", n)
    n = n.replace("pirate edition", "pirate")
    return " ".join(n.split())


def _sorted_tokens(normalized):
    return " ".join(sorted(normalized.split()))


def _mfr_code_for_ours(class_name, name):
    """Resolve our ClassName/Name pair to the matrix manufacturer_code.

    Prefers the brand token from Name (CIG occasionally packs ships under
    a different ClassName prefix than the actual brand — MISC_Fury is
    Mirai, VNCL_Blade is Esperia, XIAN_Nox is Aopoa). Falls back to
    ClassName prefix when Name doesn't start with a known brand.
    """
    if name:
        tokens = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
        if tokens:
            code = _NAME_PREFIX_TO_MFR.get(tokens[0])
            if code:
                return code
    prefix = class_name.split("_", 1)[0] if "_" in class_name else class_name
    return MFR_ALIASES.get(prefix, prefix)


def match_ships(matrix, records):
    """Match our ship records against matrix entries.

    Args:
        matrix: list of normalized matrix entries (from fetch/load_matrix)
        records: iterable of dicts with at least `ClassName` and `Name` keys

    Returns:
        Dict {ClassName: matrix_entry}. Includes:
        - matrix-matched ships (entry has all matrix fields)
        - in-game earnable ships not in matrix (entry is the _INGAME_ENTRY
          sentinel — production_status="flight-ready", _source="ingame")

        Records not in matrix and not in the in-game allow-list are not
        present in the result (caller treats them as "no signal").
    """
    if not matrix:
        # Still tag the in-game allow-list even when matrix fetch failed.
        return {cn: _INGAME_ENTRY for cn in _INGAME_FLIGHT_READY}

    matrix_exact = {}
    matrix_fallback = {}
    for m in matrix:
        code = m.get("manufacturer_code") or ""
        n = _normalize(m.get("name", ""), mfr_code=code)
        if not n:
            continue
        matrix_exact.setdefault((code, n), m)
        matrix_fallback.setdefault((code, _sorted_tokens(n)), m)

    matches = {}
    for r in records:
        cn = r.get("ClassName", "")
        if not cn:
            continue
        name = r.get("Name", "")
        code = _mfr_code_for_ours(cn, name)

        # Explicit override wins.
        override = _CLASSNAME_TO_MATRIX_NAME.get(cn)
        if override:
            key = (code, _normalize(override, mfr_code=code))
            entry = matrix_exact.get(key)
            if entry:
                matches[cn] = entry
                continue

        # Exact normalised match.
        norm = _normalize(name, mfr_code=code)
        entry = matrix_exact.get((code, norm))
        if entry:
            matches[cn] = entry
            continue

        # Fallback: sorted-tokens match (catches word-order swaps).
        entry = matrix_fallback.get((code, _sorted_tokens(norm)))
        if entry:
            matches[cn] = entry
            continue

        # Not in matrix, but a known in-game earnable.
        if cn in _INGAME_FLIGHT_READY:
            matches[cn] = _INGAME_ENTRY

    # Also tag earnables that didn't appear in `records` (defensive — they
    # should always appear, but if a build filters them upstream we still
    # surface the tag for downstream tools).
    for cn in _INGAME_FLIGHT_READY:
        matches.setdefault(cn, _INGAME_ENTRY)

    return matches
