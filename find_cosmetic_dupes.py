"""CLI audit tool: list pairs of ships in output/vehicle_metadata.json
whose entity XMLs differ only in cosmetic fields.

Implementation lives in nova/cosmetic_classifier.py so the extractor
build uses the same classification logic at filter time.

Usage:
    py find_cosmetic_dupes.py              # list cosmetic-only pairs
    py find_cosmetic_dupes.py --mixed      # also list functional pair summaries
    py find_cosmetic_dupes.py --pair A B   # deep-diff two specific ClassNames
"""

import json
import os
import sys
from collections import defaultdict

from nova.cosmetic_classifier import (
    classify_pair,
    load_impl_xml_modifications,
)


OUT_PATH = "output/vehicle_metadata.json"
RAW_PATH = "cache/parsed_vehicles.json"
ITEMS_PATH = "cache/parsed_items.json"
ENTITY_DIRS = [
    "cache/Data/Libs/Foundry/Records/entities/spaceships",
    "cache/Data/Libs/Foundry/Records/entities/groundvehicles",
]
IMPL_DIRS = [
    "cache/Data/Scripts/Entities/Vehicles/Implementations/Xml",
]


def _load():
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        out_ships = json.load(f)
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    by_cn = {
        r.get("className", ""): r
        for r in (raw.values() if isinstance(raw, dict) else raw)
        if isinstance(r, dict)
    }
    with open(ITEMS_PATH, "r", encoding="utf-8") as f:
        raw_items = json.load(f)
    items_db = {
        r.get("className", ""): r
        for r in (raw_items.values() if isinstance(raw_items, dict) else raw_items)
        if isinstance(r, dict)
    }
    entity_idx = {}
    for d in ENTITY_DIRS:
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".xml"):
                    entity_idx[os.path.splitext(fn)[0].lower()] = os.path.join(d, fn)
    impl_mods = load_impl_xml_modifications(IMPL_DIRS)
    return out_ships, by_cn, entity_idx, impl_mods, items_db


def _impl_xml_for_vehicle(veh_record):
    return (veh_record.get("vehicle") or {}).get("vehicleDefinition", "")


def _pairs_by_impl(out_ships, by_cn):
    by_impl = defaultdict(list)
    for r in out_ships:
        cn = r.get("ClassName", "")
        vd = (by_cn.get(cn, {}).get("vehicle") or {}).get("vehicleDefinition", "").lower()
        if vd:
            by_impl[vd].append(cn)
    return by_impl


def main(argv):
    out_ships, by_cn, entity_idx, impl_mods, items_db = _load()

    if len(argv) >= 2 and argv[1] == "--pair":
        if len(argv) < 4:
            print("Usage: --pair CLASSNAME_A CLASSNAME_B", file=sys.stderr)
            sys.exit(2)
        a_cn, b_cn = argv[2], argv[3]
        a_path = entity_idx.get(a_cn.lower())
        b_path = entity_idx.get(b_cn.lower())
        if not a_path or not b_path:
            print("Entity XML not found for one of the class names", file=sys.stderr)
            sys.exit(2)
        base_impl = _impl_xml_for_vehicle(by_cn.get(a_cn, {}))
        kind, d = classify_pair(a_path, b_path, base_impl, impl_mods, items_db)
        print(f"Verdict: {kind.upper()}")
        for label, items in (
            ("cosmetic paths", d["cosmetic_paths"]),
            ("cosmetic ports", d["cosmetic_ports"]),
            ("functional paths", d["functional_paths"]),
            ("functional ports", [p[0] for p in d["functional_ports"]]),
        ):
            if items:
                print(f"  {label}:")
                for it in items[:10]:
                    print(f"    {it}")
                if len(items) > 10:
                    print(f"    … +{len(items)-10} more")
        return

    show_mixed = "--mixed" in argv
    by_impl = _pairs_by_impl(out_ships, by_cn)

    cosmetic_pairs = []
    functional_pairs = []
    for _impl, members in by_impl.items():
        if len(members) < 2:
            continue
        members_sorted = sorted(members, key=lambda x: (len(x), x))
        base_cn = members_sorted[0]
        base_path = entity_idx.get(base_cn.lower())
        if not base_path:
            continue
        base_impl = _impl_xml_for_vehicle(by_cn.get(base_cn, {}))
        for cn in members_sorted[1:]:
            p = entity_idx.get(cn.lower())
            if not p:
                continue
            try:
                kind, d = classify_pair(base_path, p, base_impl, impl_mods, items_db)
            except Exception:
                continue
            if kind == "cosmetic":
                cosmetic_pairs.append((base_cn, cn, d))
            elif kind == "functional":
                functional_pairs.append((base_cn, cn, d))

    print(f"COSMETIC-ONLY pairs ({len(cosmetic_pairs)}):")
    for base_cn, cn, d in sorted(cosmetic_pairs):
        marks = []
        if d["cosmetic_paths"]:
            marks.append(f"paths={[p.split('/')[-1] for p in d['cosmetic_paths'][:3]]}")
        if d["cosmetic_ports"]:
            marks.append(f"ports={d['cosmetic_ports'][:3]}")
        print(f"  {base_cn:45}  <->  {cn:45}  {' '.join(marks)}")

    if show_mixed:
        print(f"\nFUNCTIONAL pairs ({len(functional_pairs)}):")
        for base_cn, cn, d in sorted(functional_pairs):
            fp = d["functional_paths"][:2]
            fports = [n for n, _, _ in d["functional_ports"][:3]]
            print(f"  {base_cn:45}  <->  {cn}")
            if fp:
                print(f"      paths: {fp}")
            if fports:
                print(f"      ports: {fports}")


if __name__ == "__main__":
    main(sys.argv)
