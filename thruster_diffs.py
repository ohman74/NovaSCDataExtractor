"""Detailed Thruster diff dump (tolerant mode: ignore <=0.01 floats / strip strings)."""
import json
import re
import sys
from collections import Counter, defaultdict


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


def diffs(ref, out, path, acc):
    if eq(ref, out):
        return
    if isinstance(ref, dict) and isinstance(out, dict):
        for k in set(ref.keys()) | set(out.keys()):
            if k not in ref:
                acc.append((f"{path}.{k}", "OUT-ONLY", None, out[k]))
            elif k not in out:
                acc.append((f"{path}.{k}", "REF-ONLY", ref[k], None))
            else:
                diffs(ref[k], out[k], f"{path}.{k}", acc)
        return
    if isinstance(ref, list) and isinstance(out, list):
        if ref and out and isinstance(ref[0], dict):
            for cand in ("PortName", "ClassName", "Name"):
                if all(cand in r for r in ref) and all(cand in o for o in out):
                    ref_by = {r[cand]: r for r in ref}
                    out_by = {o[cand]: o for o in out}
                    for k in set(ref_by) | set(out_by):
                        if k not in ref_by:
                            acc.append((f"{path}[{cand}={k}]", "OUT-ONLY", None, out_by[k]))
                        elif k not in out_by:
                            acc.append((f"{path}[{cand}={k}]", "REF-ONLY", ref_by[k], None))
                        else:
                            diffs(ref_by[k], out_by[k], f"{path}[{cand}={k}]", acc)
                    return
        if len(ref) != len(out):
            acc.append((f"{path}", "LIST-LEN", f"len={len(ref)}", f"len={len(out)}"))
            return
        for i, (r, o) in enumerate(zip(ref, out)):
            diffs(r, o, f"{path}[{i}]", acc)
        return
    acc.append((path, "VALUE", ref, out))


def main():
    out_list = json.load(open("output/vehicle_hardpoints.json", encoding="utf-8"))
    ref_list = json.load(open("temp/reference/entry_2.json", encoding="utf-8-sig"))
    out_by_cn = {r["ClassName"]: r for r in out_list}

    target = sys.argv[1] if len(sys.argv) > 1 else None

    by_ship = defaultdict(list)
    for ref_item in ref_list:
        cn = ref_item["ClassName"]
        if cn not in out_by_cn:
            continue
        ref_thr = (ref_item.get("Hardpoints", {}).get("Components", {})
                   .get("Propulsion", {}).get("Thrusters", {}))
        out_thr = (out_by_cn[cn].get("Hardpoints", {}).get("Components", {})
                   .get("Propulsion", {}).get("Thrusters", {}))
        if not ref_thr and not out_thr:
            continue
        acc = []
        diffs(ref_thr, out_thr, "Thrusters", acc)
        if acc:
            by_ship[cn] = acc

    if target:
        if target not in by_ship:
            print(f"No thruster diffs for {target}")
            return
        print(f"=== {target} ({len(by_ship[target])} diffs) ===")
        for path, kind, r, o in by_ship[target]:
            print(f"\n  [{kind}] {path}")
            if r is not None:
                rs = json.dumps(r, indent=2) if not isinstance(r, str) else r
                print(f"    REF: {rs[:600]}")
            if o is not None:
                os_ = json.dumps(o, indent=2) if not isinstance(o, str) else o
                print(f"    OUT: {os_[:600]}")
        return

    total = sum(len(v) for v in by_ship.values())
    print(f"Ships with thruster diffs: {len(by_ship)}")
    print(f"Total thruster diffs: {total}\n")

    sig_counts = Counter()
    for cn, lst in by_ship.items():
        for path, kind, r, o in lst:
            sig = re.sub(r"\[(PortName|ClassName|Name)=[^\]]+\]", "[*]", path)
            sig = re.sub(r"\[\d+\]", "[i]", sig)
            sig_counts[(sig, kind)] += 1
    print(f"{'Signature':<70} {'Kind':<10} {'Count':>5}")
    print("-" * 90)
    for (sig, kind), cnt in sig_counts.most_common():
        print(f"{sig:<70} {kind:<10} {cnt:>5}")

    print()
    print("=== Per-ship diff counts ===")
    for cn, lst in sorted(by_ship.items(), key=lambda x: -len(x[1]))[:30]:
        print(f"  {cn:<40} {len(lst):>3}")


if __name__ == "__main__":
    main()
