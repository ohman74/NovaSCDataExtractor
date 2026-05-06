"""Count Storage/Cargo/Thruster diffs in vehicle_hardpoints, with/without rounding+whitespace tolerance."""
import json
from collections import Counter, defaultdict


def is_sct_path(path: str) -> bool:
    return (".Storage" in path
            or ".CargoGrids" in path
            or ".CargoContainers" in path
            or ".Thrusters." in path
            or ".HydrogenFuelTanks" in path)


def diff(ref, out, path, sigs, tolerant: bool):
    """Walk and count diffs. tolerant=True applies ±0.01 float / strip-string equality."""
    if _eq(ref, out, tolerant):
        return
    if isinstance(ref, dict) and isinstance(out, dict):
        for k in set(ref.keys()) | set(out.keys()):
            if k not in ref:
                if is_sct_path(path):
                    sigs[f"{path}.{k} (out-only)"] += 1
            elif k not in out:
                if is_sct_path(path):
                    sigs[f"{path}.{k} (ref-only)"] += 1
            else:
                diff(ref[k], out[k], f"{path}.{k}", sigs, tolerant)
        return
    if isinstance(ref, list) and isinstance(out, list):
        if ref and out and isinstance(ref[0], dict):
            for cand in ("PortName", "ClassName", "Name"):
                if all(cand in r for r in ref) and all(cand in o for o in out):
                    ref_by = {r[cand]: r for r in ref}
                    out_by = {o[cand]: o for o in out}
                    for k in set(ref_by) | set(out_by):
                        if k not in ref_by:
                            if is_sct_path(path):
                                sigs[f"{path}[entry] (out-only)"] += 1
                        elif k not in out_by:
                            if is_sct_path(path):
                                sigs[f"{path}[entry] (ref-only)"] += 1
                        else:
                            diff(ref_by[k], out_by[k], path, sigs, tolerant)
                    return
        if len(ref) != len(out):
            if is_sct_path(path):
                sigs[f"{path} (list-len)"] += 1
            return
        for r, o in zip(ref, out):
            diff(r, o, path, sigs, tolerant)
        return
    if is_sct_path(path):
        sigs[f"{path} (value)"] += 1


def _eq(a, b, tolerant: bool) -> bool:
    if type(a) != type(b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) <= 0.01 if tolerant else float(a) == float(b)
        return False
    if isinstance(a, float):
        return abs(a - b) <= 0.01 if tolerant else a == b
    if isinstance(a, str):
        return (a.strip() == b.strip()) if tolerant else a == b
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_eq(x, y, tolerant) for x, y in zip(a, b))
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_eq(a[k], b[k], tolerant) for k in a)
    return a == b


def run(tolerant: bool):
    out_list = json.load(open("output/vehicle_hardpoints.json", encoding="utf-8"))
    ref_list = json.load(open("temp/reference/entry_2.json", encoding="utf-8-sig"))
    out_by_cn = {r["ClassName"]: r for r in out_list}
    sigs = Counter()
    for ref_item in ref_list:
        cn = ref_item["ClassName"]
        if cn not in out_by_cn:
            continue
        diff(ref_item.get("Hardpoints", {}),
             out_by_cn[cn].get("Hardpoints", {}),
             "Hardpoints", sigs, tolerant)
    return sigs


def bucket(sig: str) -> str:
    if ".Storage" in sig:
        return "Storage"
    if ".CargoGrids" in sig or ".CargoContainers" in sig:
        return "Cargo"
    if ".Thrusters." in sig:
        return "Thrusters"
    if ".HydrogenFuelTanks" in sig:
        return "FuelTanks"
    return "Other"


for label, tolerant in [("STRICT (no tolerance)", False),
                         ("TOLERANT (<=0.01 floats / strip strings)", True)]:
    sigs = run(tolerant)
    by_bucket = defaultdict(int)
    for sig, cnt in sigs.items():
        by_bucket[bucket(sig)] += cnt
    total = sum(sigs.values())
    print(f"=== {label} ===")
    for b in ("Storage", "Cargo", "Thrusters", "FuelTanks"):
        print(f"  {b:<10} {by_bucket[b]:>5}")
    print(f"  {'TOTAL':<10} {total:>5}")
    print()
