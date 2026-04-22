"""Compare output/vehicle_equipment.json + fps_equipment.json against the reference.

Usage:
    py compare_equipment.py                  # summary of stdItem fields (both slices)
    py compare_equipment.py <className>      # deep-diff a single item
    py compare_equipment.py --field <name>   # show mismatches for one field
    py compare_equipment.py --missing        # items with any stdItem field mismatch

Slices:
    vehicle_equipment ↔ temp/reference_data_new/entry_3.json (ship gear)
    fps_equipment     ↔ temp/reference_data_new/entry_4.json (FPS weapons + attachments)
"""
import json
import sys
from collections import Counter


def eq(a, b):
    """Deep-equal with float tolerance and whitespace-insensitive string compare."""
    if type(a) != type(b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) < 1e-6
        return False
    if isinstance(a, float):
        return abs(a - b) < 1e-6
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


def summary(ref_by, out_by, label):
    common = set(ref_by) & set(out_by)
    all_fields = Counter()
    match_fields = Counter()
    ref_has = Counter()
    out_has = Counter()

    for cn in common:
        ref_std = ref_by[cn].get("stdItem") or {}
        out_std = out_by[cn].get("stdItem") or {}
        for k in set(ref_std.keys()) | set(out_std.keys()):
            all_fields[k] += 1
            if k in ref_std:
                ref_has[k] += 1
            if k in out_std:
                out_has[k] += 1
            if k in ref_std and k in out_std and eq(ref_std[k], out_std[k]):
                match_fields[k] += 1

    full_match = sum(
        1 for cn in common
        if eq(ref_by[cn].get("stdItem") or {}, out_by[cn].get("stdItem") or {})
    )

    print(f"=== {label} ===")
    print(f"Ref: {len(ref_by)}, Out: {len(out_by)}, Common: {len(common)}")
    print(f"Ref-only items: {len(set(ref_by) - set(out_by))}")
    print(f"Out-only items: {len(set(out_by) - set(ref_by))}")
    print(f"Full stdItem match: {full_match}/{len(common)} "
          f"({100*full_match/max(len(common),1):.1f}%)\n")
    print(f"{'Field':<30} {'Match':>7} {'Ref':>6} {'Out':>6} {'Rate':>7}")
    print("-" * 65)
    for k, total in sorted(all_fields.items(), key=lambda x: -x[1]):
        m = match_fields[k]
        r = ref_has[k]
        o = out_has[k]
        rate = 100 * m / r if r else 0
        print(f"{k:<30} {m:>7} {r:>6} {o:>6} {rate:>6.1f}%")
    print()


def show_field(field, ref_by, out_by, label, limit=5):
    common = set(ref_by) & set(out_by)
    mismatches = []
    ref_only = []
    out_only = []
    for cn in common:
        ref_std = ref_by[cn].get("stdItem") or {}
        out_std = out_by[cn].get("stdItem") or {}
        r = ref_std.get(field)
        o = out_std.get(field)
        if field in ref_std and field not in out_std:
            ref_only.append(cn)
        elif field in out_std and field not in ref_std:
            out_only.append(cn)
        elif field in ref_std and field in out_std and not eq(r, o):
            mismatches.append((cn, r, o))

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
            print(f"  REF: {json.dumps(r, indent=2)[:500]}")
            print(f"  OUT: {json.dumps(o, indent=2)[:500]}")


def deep_diff(class_name, slices):
    for label, ref_by, out_by in slices:
        r = ref_by.get(class_name)
        o = out_by.get(class_name)
        if not r and not o:
            continue
        print(f"=== {label}: {class_name} ===")
        if not r:
            print("  (not in ref)")
            continue
        if not o:
            print("  (not in out)")
            continue
        r_std = r.get("stdItem") or {}
        o_std = o.get("stdItem") or {}
        for k in sorted(set(r_std.keys()) | set(o_std.keys())):
            rv = r_std.get(k, "<missing>")
            ov = o_std.get(k, "<missing>")
            if not eq(rv, ov):
                print(f"\n[{k}]")
                print(f"  REF: {json.dumps(rv, indent=2)[:2000]}")
                print(f"  OUT: {json.dumps(ov, indent=2)[:2000]}")
        print()


def missing(ref_by, out_by, label):
    common = set(ref_by) & set(out_by)
    print(f"=== {label}: items with stdItem mismatch ===")
    for cn in sorted(common):
        if not eq(ref_by[cn].get("stdItem") or {}, out_by[cn].get("stdItem") or {}):
            print(cn)


def _load(path, bom):
    enc = "utf-8-sig" if bom else "utf-8"
    with open(path, encoding=enc) as f:
        return json.load(f)


def main():
    ve_out = {r["className"]: r for r in _load("output/vehicle_equipment.json", bom=False)}
    fps_out = {r["className"]: r for r in _load("output/fps_equipment.json", bom=False)}
    e3 = {r["className"]: r for r in _load("temp/reference_data_new/entry_3.json", bom=True)}
    e4 = {r["className"]: r for r in _load("temp/reference_data_new/entry_4.json", bom=True)}

    slices = [
        ("vehicle_equipment (entry_3)", e3, ve_out),
        ("fps_equipment (entry_4)",     e4, fps_out),
    ]

    args = sys.argv[1:]
    if not args:
        for label, ref_by, out_by in slices:
            summary(ref_by, out_by, label)
    elif args[0] == "--field":
        field = args[1]
        limit = int(args[2]) if len(args) > 2 else 5
        for label, ref_by, out_by in slices:
            show_field(field, ref_by, out_by, label, limit=limit)
    elif args[0] == "--missing":
        for label, ref_by, out_by in slices:
            missing(ref_by, out_by, label)
    else:
        deep_diff(args[0], slices)


if __name__ == "__main__":
    main()
