"""Compare output/vehicle_{metadata,stats,hardpoints}.json against the reference.

Usage:
    py compare_vehicles.py                       # summary of all three slices
    py compare_vehicles.py <ClassName>           # deep-diff one vehicle across all slices
    py compare_vehicles.py --field <name>        # show mismatches for one field

Slices:
    vehicle_metadata   ↔ temp/reference_data_new/entry_0.json
    vehicle_stats      ↔ temp/reference_data_new/entry_1.json
    vehicle_hardpoints ↔ temp/reference_data_new/entry_2.json

Ignores:
- Leading/trailing whitespace in strings
- Float differences ≤ 0.01
- External-web placeholder fields we can't derive from the game files
  (kept in output for shape parity, but skipped during comparison)
"""
import json
import sys
from collections import Counter

# Fields we emit as empty placeholders to match reference shape but can't
# actually fill from game data. Skip them in comparison.
_SKIP_FIELDS_METADATA = {"CommLink", "ProgressTracker", "Store", "PU", "New Ship", "New Vehicle"}
_SKIP_FIELDS_STATS = {"Buy", "New Ship", "New Vehicle"}

# Nested sub-fields stripped from both ref and out before comparison. AccelerationG
# inside FlightCharacteristics is curated external data (IsValidated/CheckDate)
# we can't derive from game files, same convention as the top-level external skips.
_SKIP_NESTED_STATS = [("FlightCharacteristics", "AccelerationG")]
_SKIP_FIELDS_HARDPOINTS = set()


def eq(a, b):
    """Tolerant deep-equal: whitespace-insensitive strings, ±0.01 for floats."""
    if type(a) != type(b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) <= 0.01
        return False
    if isinstance(a, float):
        return abs(a - b) <= 0.01
    if isinstance(a, str):
        return a.strip() == b.strip()
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(eq(a[k], b[k]) for k in a)
    return a == b


def _field_report(ref_list, out_by_cn, skip_fields, label):
    common = [r for r in ref_list if r["ClassName"] in out_by_cn]
    all_fields = Counter()
    match_fields = Counter()
    full_matches = 0

    for ref_item in common:
        cn = ref_item["ClassName"]
        out_item = out_by_cn[cn]
        item_full_match = True
        for k in ref_item:
            if k in skip_fields:
                continue
            all_fields[k] += 1
            if k in out_item and eq(ref_item[k], out_item[k]):
                match_fields[k] += 1
            else:
                item_full_match = False
        if item_full_match:
            full_matches += 1

    ref_only = [r["ClassName"] for r in ref_list if r["ClassName"] not in out_by_cn]
    out_only_count = len(set(out_by_cn) - {r["ClassName"] for r in ref_list})

    print(f"=== {label} ===")
    print(f"Ref: {len(ref_list)}, Out: {len(out_by_cn)}, Common: {len(common)}")
    print(f"Ref-only: {len(ref_only)}, Out-only: {out_only_count}")
    if ref_only:
        print(f"  ref-only sample: {ref_only[:10]}")
    print(f"Full match (all compared fields): {full_matches}/{len(common)} "
          f"({100*full_matches/max(len(common),1):.1f}%)")
    print()
    print(f"{'Field':<30} {'Match':>7} {'Total':>7} {'Rate':>7}")
    print("-" * 55)
    for k, t in sorted(all_fields.items(), key=lambda x: -x[1]):
        m = match_fields[k]
        rate = 100 * m / t if t else 0
        print(f"{k:<30} {m:>7} {t:>7} {rate:>6.1f}%")
    print()


def show_field(field, ref_list, out_by_cn, label, limit=5):
    common = [r for r in ref_list if r["ClassName"] in out_by_cn]
    mismatches = []
    ref_only = []
    out_only = []
    for ref_item in common:
        cn = ref_item["ClassName"]
        out_item = out_by_cn[cn]
        if field in ref_item and field not in out_item:
            ref_only.append(cn)
        elif field in out_item and field not in ref_item:
            out_only.append(cn)
        elif field in ref_item and field in out_item and not eq(ref_item[field], out_item[field]):
            mismatches.append((cn, ref_item[field], out_item[field]))

    print(f"=== {label}: {field} ===")
    print(f"  In ref only: {len(ref_only)}")
    print(f"  In out only: {len(out_only)}")
    print(f"  Value mismatches: {len(mismatches)}\n")

    if ref_only:
        print(f"--- Sample ref-only: {ref_only[:10]}")
    if out_only:
        print(f"--- Sample out-only: {out_only[:10]}")
    if mismatches:
        print(f"--- Sample mismatches:")
        for cn, r, o in mismatches[:limit]:
            print(f"\n[{cn}]")
            print(f"  REF: {json.dumps(r, indent=2)[:700]}")
            print(f"  OUT: {json.dumps(o, indent=2)[:700]}")


def deep_diff(class_name, slices):
    for label, ref_list, out_by_cn, skip_fields in slices:
        ref_item = next((r for r in ref_list if r["ClassName"] == class_name), None)
        out_item = out_by_cn.get(class_name)
        if not ref_item and not out_item:
            continue
        print(f"=== {label}: {class_name} ===")
        if not ref_item:
            print("  (not in ref)")
            continue
        if not out_item:
            print("  (not in out)")
            continue
        for k in sorted(set(ref_item.keys()) | set(out_item.keys())):
            if k in skip_fields:
                continue
            rv = ref_item.get(k, "<missing>")
            ov = out_item.get(k, "<missing>")
            if not eq(rv, ov):
                print(f"\n[{k}]")
                print(f"  REF: {json.dumps(rv, indent=2)[:2000]}")
                print(f"  OUT: {json.dumps(ov, indent=2)[:2000]}")
        print()


def _load_json(path, bom=True):
    enc = "utf-8-sig" if bom else "utf-8"
    with open(path, encoding=enc) as f:
        return json.load(f)


def _strip_nested(records, nested_skips):
    for r in records:
        for parent, child in nested_skips:
            if isinstance(r.get(parent), dict):
                r[parent].pop(child, None)
    return records


def main():
    out_meta = {r["ClassName"]: r for r in _load_json("output/vehicle_metadata.json", bom=False)}
    out_stats = {r["ClassName"]: r for r in _load_json("output/vehicle_stats.json", bom=False)}
    out_hp = {r["ClassName"]: r for r in _load_json("output/vehicle_hardpoints.json", bom=False)}
    e0 = _load_json("temp/reference_data_new/entry_0.json")
    e1 = _strip_nested(_load_json("temp/reference_data_new/entry_1.json"), _SKIP_NESTED_STATS)
    e2 = _load_json("temp/reference_data_new/entry_2.json")

    slices = [
        ("entry_0 (metadata)",   e0, out_meta,  _SKIP_FIELDS_METADATA),
        ("entry_1 (stats)",      e1, out_stats, _SKIP_FIELDS_STATS),
        ("entry_2 (hardpoints)", e2, out_hp,    _SKIP_FIELDS_HARDPOINTS),
    ]

    args = sys.argv[1:]
    if not args:
        for label, ref_list, out_by_cn, skip in slices:
            _field_report(ref_list, out_by_cn, skip, label)
    elif args[0] == "--field":
        field = args[1]
        limit = int(args[2]) if len(args) > 2 else 5
        for label, ref_list, out_by_cn, skip in slices:
            if field in skip:
                continue
            show_field(field, ref_list, out_by_cn, label, limit=limit)
    else:
        deep_diff(args[0], slices)


if __name__ == "__main__":
    main()
