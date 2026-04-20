"""Compare output/ships.json against the reference ship metadata / stats / hardpoints files.

Usage:
    py compare_ships.py              # summary of all three refs
    py compare_ships.py <ClassName>  # deep diff for a single ship
    py compare_ships.py --field <name> [<limit>]  # mismatches for one field

Ignores:
- Leading/trailing whitespace in strings
- Float differences ≤ 0.01
- Reference-only fields that ships.json doesn't emit (CommLink, ProgressTracker,
  Store, PU, Buy — external/website metadata).
"""
import json
import sys
from collections import Counter

# Fields present in ref but we don't emit (external/website-sourced).
_SKIP_FIELDS_E0 = {"CommLink", "ProgressTracker", "Store", "PU", "New Ship", "New Vehicle"}
_SKIP_FIELDS_E1 = {"Buy", "New Ship", "New Vehicle"}
_SKIP_FIELDS_E2 = set()


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
    """Compare every ref item against our output for overlapping classNames.
    Report per-field match counts."""
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


def deep_diff(class_name, refs, out_by_cn):
    out = out_by_cn.get(class_name)
    if not out:
        print(f"Not in ships.json: {class_name}")
        return
    for label, ref_list, skip_fields in refs:
        ref_item = next((r for r in ref_list if r["ClassName"] == class_name), None)
        if not ref_item:
            continue
        print(f"=== {label}: {class_name} ===")
        for k in sorted(set(ref_item.keys()) | set(out.keys())):
            if k in skip_fields:
                continue
            rv = ref_item.get(k, "<missing>")
            ov = out.get(k, "<missing>")
            if not eq(rv, ov):
                print(f"\n[{k}]")
                print(f"  REF: {json.dumps(rv, indent=2)[:2000]}")
                print(f"  OUT: {json.dumps(ov, indent=2)[:2000]}")
        print()


def load():
    """Load ref files and merge ships.json + vehicles.json into a single lookup.
    Ref files combine ships and vehicles, so we must too. For overlapping
    classNames, vehicles.json fills in missing fields (e.g. IsGravlev,
    MovementClass) while ships.json keeps everything else."""
    with open("output/ships.json", encoding="utf-8") as f:
        ships = json.load(f)
    with open("output/vehicles.json", encoding="utf-8") as f:
        vehicles = json.load(f)
    with open("temp/reference_data_new/entry_0.json", encoding="utf-8-sig") as f:
        e0 = json.load(f)
    with open("temp/reference_data_new/entry_1.json", encoding="utf-8-sig") as f:
        e1 = json.load(f)
    with open("temp/reference_data_new/entry_2.json", encoding="utf-8-sig") as f:
        e2 = json.load(f)

    out_by_cn = {r["ClassName"]: r for r in vehicles}
    # ships.json takes precedence for shared classNames; missing keys are filled
    # from vehicles.json (vehicle-specific fields).
    for r in ships:
        cn = r["ClassName"]
        if cn in out_by_cn:
            merged = dict(out_by_cn[cn])
            merged.update(r)  # ships fields win
            out_by_cn[cn] = merged
        else:
            out_by_cn[cn] = r
    return out_by_cn, e0, e1, e2


def main():
    out_by_cn, e0, e1, e2 = load()
    args = sys.argv[1:]
    refs = [
        ("entry_0 (metadata)", e0, _SKIP_FIELDS_E0),
        ("entry_1 (stats)",    e1, _SKIP_FIELDS_E1),
        ("entry_2 (hardpoints)", e2, _SKIP_FIELDS_E2),
    ]
    if not args:
        for label, ref_list, skip in refs:
            _field_report(ref_list, out_by_cn, skip, label)
    elif args[0] == "--field":
        field = args[1]
        limit = int(args[2]) if len(args) > 2 else 5
        for label, ref_list, skip in refs:
            if field in skip:
                continue
            show_field(field, ref_list, out_by_cn, label, limit=limit)
    else:
        deep_diff(args[0], refs, out_by_cn)


if __name__ == "__main__":
    main()
