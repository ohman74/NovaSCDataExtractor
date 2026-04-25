"""Walk vehicle_hardpoints diffs and count signatures by path."""
import json
import sys
from collections import Counter


def eq(a, b):
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


def diff(ref, out, path, sigs, examples, max_examples=3):
    if eq(ref, out):
        return
    # Both dicts → recurse on union of keys
    if isinstance(ref, dict) and isinstance(out, dict):
        keys = set(ref.keys()) | set(out.keys())
        for k in keys:
            if k not in ref:
                sig = f"{path}.{k} (out-only)"
                sigs[sig] += 1
                if len(examples[sig]) < max_examples:
                    examples[sig].append(("out-only", out.get(k)))
            elif k not in out:
                sig = f"{path}.{k} (ref-only)"
                sigs[sig] += 1
                if len(examples[sig]) < max_examples:
                    examples[sig].append(("ref-only", ref.get(k)))
            else:
                diff(ref[k], out[k], f"{path}.{k}", sigs, examples, max_examples)
        return
    # Both lists with equal len → recurse element-wise; else mark whole list
    if isinstance(ref, list) and isinstance(out, list):
        # Try to match by PortName / ClassName when entries are dicts
        if ref and out and isinstance(ref[0], dict):
            # Match by key
            key = None
            for cand in ("PortName", "ClassName", "Name"):
                if all(cand in r for r in ref) and all(cand in o for o in out):
                    key = cand
                    break
            if key:
                ref_by = {r[key]: r for r in ref}
                out_by = {o[key]: o for o in out}
                all_keys = set(ref_by) | set(out_by)
                for k in all_keys:
                    if k not in ref_by:
                        sig = f"{path}[entry] (out-only)"
                        sigs[sig] += 1
                        if len(examples[sig]) < max_examples:
                            examples[sig].append((k, out_by.get(k)))
                    elif k not in out_by:
                        sig = f"{path}[entry] (ref-only)"
                        sigs[sig] += 1
                        if len(examples[sig]) < max_examples:
                            examples[sig].append((k, ref_by.get(k)))
                    else:
                        diff(ref_by[k], out_by[k], path, sigs, examples, max_examples)
                return
        if len(ref) != len(out):
            sig = f"{path} (list-len)"
            sigs[sig] += 1
            if len(examples[sig]) < max_examples:
                examples[sig].append((f"len {len(ref)} vs {len(out)}", None))
            return
        for r, o in zip(ref, out):
            diff(r, o, path, sigs, examples, max_examples)
        return
    # Scalar mismatch
    sig = f"{path} (value)"
    sigs[sig] += 1
    if len(examples[sig]) < max_examples:
        examples[sig].append((repr(ref)[:80], repr(out)[:80]))


def main():
    with open("output/vehicle_hardpoints.json", encoding="utf-8") as f:
        out_list = json.load(f)
    with open("temp/reference_data_new/entry_2.json", encoding="utf-8-sig") as f:
        ref_list = json.load(f)
    out_by_cn = {r["ClassName"]: r for r in out_list}

    sigs = Counter()
    examples = {}
    from collections import defaultdict
    examples = defaultdict(list)

    ships_with_diff = 0
    for ref_item in ref_list:
        cn = ref_item["ClassName"]
        if cn not in out_by_cn:
            continue
        out_item = out_by_cn[cn]
        ref_hp = ref_item.get("Hardpoints", {})
        out_hp = out_item.get("Hardpoints", {})
        before = sum(sigs.values())
        diff(ref_hp, out_hp, "Hardpoints", sigs, examples)
        if sum(sigs.values()) > before:
            ships_with_diff += 1

    print(f"Total diffs: {sum(sigs.values())}")
    print(f"Ships with diffs: {ships_with_diff}")
    print()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    show_examples = "--examples" in sys.argv
    for sig, count in sigs.most_common(n):
        print(f"{count:5d}  {sig}")
        if show_examples:
            for ex in examples[sig][:2]:
                print(f"        {ex}")


if __name__ == "__main__":
    main()
