"""Investigate one specific diff signature with examples.

Usage:
    py investigate_diff.py <jq-style-path>
    py investigate_diff.py Hardpoints.Components.Storage.InstalledItems.Uneditable
"""
import json
import sys


def get_path(obj, path):
    parts = path.split(".")
    cur = obj
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            # lists of dicts: collect from all entries
            results = []
            for item in cur:
                v = get_path(item, ".".join(parts[parts.index(p):]))
                if v is not None:
                    results.append(v)
            return results
        else:
            return None
    return cur


def find_examples(path, target):
    """For the given dot path, return [(class_name, ref_value, out_value, port_name)]"""
    with open("output/vehicle_hardpoints.json", encoding="utf-8") as f:
        out_list = json.load(f)
    with open("temp/reference_data_new/entry_2.json", encoding="utf-8-sig") as f:
        ref_list = json.load(f)
    out_by_cn = {r["ClassName"]: r for r in out_list}

    # Path examples like:
    # Hardpoints.Components.Storage.InstalledItems.Uneditable
    parts = path.split(".")
    # Find the field name
    field = parts[-1]
    container_path = parts[:-1]

    examples = []
    for ref_item in ref_list:
        cn = ref_item["ClassName"]
        if cn not in out_by_cn:
            continue
        out_item = out_by_cn[cn]
        ref_container = ref_item
        out_container = out_item
        for p in container_path:
            if isinstance(ref_container, dict):
                ref_container = ref_container.get(p, {})
            if isinstance(out_container, dict):
                out_container = out_container.get(p, {})
        if isinstance(ref_container, dict) and isinstance(out_container, dict):
            if "InstalledItems" in container_path:
                # already drilled in
                pass
            # Compare scalar field
            r = ref_container.get(field, "<missing>")
            o = out_container.get(field, "<missing>")
            if r != o:
                examples.append((cn, r, o, ""))
        elif isinstance(ref_container, list) and isinstance(out_container, list):
            # Match by PortName
            ref_by = {x.get("PortName"): x for x in ref_container if isinstance(x, dict)}
            out_by = {x.get("PortName"): x for x in out_container if isinstance(x, dict)}
            for pn, ri in ref_by.items():
                oi = out_by.get(pn)
                if not oi:
                    continue
                r = ri.get(field, "<missing>")
                o = oi.get(field, "<missing>")
                if r != o:
                    examples.append((cn, r, o, pn))
    return examples


if __name__ == "__main__":
    path = sys.argv[1]
    examples = find_examples(path, None)
    print(f"Found {len(examples)} mismatches for {path}")
    print()
    for ex in examples[:30]:
        cn, r, o, pn = ex
        pn_s = pn if pn else ""
        print(f"{cn:30s} {pn_s:50s} REF={r!r}  OUT={o!r}")
