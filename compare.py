"""Compare output/ship_equipment.json to temp/reference_data/entry_3.json and report match rates per field.

Usage:
    py compare.py                  # summary of stdItem fields
    py compare.py <className>      # deep-diff a single item
    py compare.py --field <name>   # show mismatches for a single field
    py compare.py --missing        # show items that have a field in ref but not out (or vice versa)
"""
import json
import sys
from collections import Counter, defaultdict


def load_data():
    with open("output/ship_equipment.json", encoding="utf-8") as f:
        out = json.load(f)
    with open("temp/reference_data_new/entry_3.json", encoding="utf-8-sig") as f:
        ref = json.load(f)
    return {r["className"]: r for r in ref}, {o["className"]: o for o in out}


def eq(a, b):
    """Deep-equal with float tolerance and whitespace-insensitive string compare."""
    if type(a) != type(b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) < 1e-6
        return False
    if isinstance(a, float):
        return abs(a - b) < 1e-6
    if isinstance(a, str):
        # Ignore leading/trailing whitespace differences
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


def summary(ref_by, out_by):
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
            r = ref_std.get(k)
            o = out_std.get(k)
            if k in ref_std:
                ref_has[k] += 1
            if k in out_std:
                out_has[k] += 1
            if k in ref_std and k in out_std and eq(r, o):
                match_fields[k] += 1

    # Total-entry full stdItem match
    full_match = sum(1 for cn in common if eq(ref_by[cn].get("stdItem") or {}, out_by[cn].get("stdItem") or {}))

    print(f"Common items: {len(common)}")
    print(f"Full stdItem match: {full_match}/{len(common)} ({100*full_match/len(common):.1f}%)\n")

    print(f"{'Field':<25} {'Match':>7} {'Ref':>6} {'Out':>6} {'Rate':>7}")
    print("-" * 60)
    for k, total in sorted(all_fields.items(), key=lambda x: -x[1]):
        m = match_fields[k]
        r = ref_has[k]
        o = out_has[k]
        rate = 100 * m / r if r else 0
        print(f"{k:<25} {m:>7} {r:>6} {o:>6} {rate:>6.1f}%")


def show_field(field, ref_by, out_by, limit=20):
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

    print(f"Field: {field}")
    print(f"  In ref only: {len(ref_only)}")
    print(f"  In out only: {len(out_only)}")
    print(f"  Value mismatches: {len(mismatches)}\n")

    if ref_only:
        print(f"--- Sample ref-only (need to add to builder): {ref_only[:10]}")
    if out_only:
        print(f"--- Sample out-only (shouldn't be there): {out_only[:10]}")
    if mismatches:
        print(f"--- Sample mismatches:")
        for cn, r, o in mismatches[:limit]:
            print(f"\n[{cn}]")
            print(f"  REF: {json.dumps(r, indent=2)[:500]}")
            print(f"  OUT: {json.dumps(o, indent=2)[:500]}")


def deep_diff(item_name, ref_by, out_by):
    r = ref_by.get(item_name)
    o = out_by.get(item_name)
    if not r:
        print(f"Item not in ref: {item_name}")
        return
    if not o:
        print(f"Item not in out: {item_name}")
        return
    r_std = r.get("stdItem") or {}
    o_std = o.get("stdItem") or {}
    print(f"=== {item_name} ===")
    for k in sorted(set(r_std.keys()) | set(o_std.keys())):
        rv = r_std.get(k, "<missing>")
        ov = o_std.get(k, "<missing>")
        if not eq(rv, ov):
            print(f"\n[{k}]")
            print(f"  REF: {json.dumps(rv, indent=2)[:2000]}")
            print(f"  OUT: {json.dumps(ov, indent=2)[:2000]}")


def main():
    ref_by, out_by = load_data()
    args = sys.argv[1:]
    if not args:
        summary(ref_by, out_by)
    elif args[0] == "--field":
        show_field(args[1], ref_by, out_by, limit=int(args[2]) if len(args) > 2 else 5)
    elif args[0] == "--missing":
        common = set(ref_by) & set(out_by)
        print("Items with any stdItem field mismatch:")
        for cn in sorted(common):
            if not eq(ref_by[cn].get("stdItem") or {}, out_by[cn].get("stdItem") or {}):
                print(cn)
    else:
        deep_diff(args[0], ref_by, out_by)


if __name__ == "__main__":
    main()
