"""For each affected ship, walk its entity XML's SVehicleObjectContainerParams
references and count PersonalStorage_* object placements in the linked socpaks.

This proves the structural derivation of interior-storage counts that REF reports
(Bucket A in storage_diffs_audit.md) — driven entirely by:

  ship entity XML
    └─ SVehicleObjectContainerParams.fileName -> Data/ObjectContainers/Ships/.../X.socpak
        └─ X_editor.xml inside socpak
            └─ <Object type="PersonalStorage_*"/> placements

Compare extraction count vs REF entry_2.json Storage.InstalledItems.
"""
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

CACHE = "cache"
REF = "temp/reference/entry_2.json"


def ship_socpaks(entity_xml_path):
    try:
        tree = ET.parse(entity_xml_path)
    except Exception:
        return []
    paks = []
    for elem in tree.getroot().iter("SVehicleObjectContainerParams"):
        fn = elem.get("fileName", "")
        if fn.lower().endswith(".socpak"):
            paks.append(fn)
    return paks


def count_storage_in_socpak(socpak_path):
    if not os.path.isfile(socpak_path):
        return Counter(), False
    counts = Counter()
    try:
        with zipfile.ZipFile(socpak_path) as z:
            for n in z.namelist():
                if not n.endswith("_editor.xml"):
                    continue
                content = z.read(n).decode("utf-8", errors="ignore")
                for m in re.findall(r'type="(PersonalStorage_\w+)"', content):
                    counts[m] += 1
    except Exception:
        return Counter(), False
    return counts, True


def main():
    ref = {r["ClassName"]: r for r in json.load(open(REF, encoding="utf-8-sig"))}

    affected = [
        "AEGS_Reclaimer", "AEGS_Retaliator",
        "ANVL_Valkyrie", "MRAI_Guardian", "MRAI_Guardian_QI",
        "CRUS_Intrepid", "CRUS_Starlifter_A2", "CRUS_Starlifter_C2", "CRUS_Starlifter_M2",
        "MISC_Fortune", "MISC_Starlancer_Max",
        "ORIG_400i",
        "RSI_Constellation_Andromeda", "RSI_Constellation_Aquila",
        "RSI_Constellation_Phoenix", "RSI_Constellation_Taurus",
        "RSI_Polaris", "RSI_Zeus_CL", "RSI_Zeus_ES",
    ]

    rows = []
    for cn in affected:
        entity_xml = os.path.join(
            CACHE, "Data", "Libs", "Foundry", "Records", "entities",
            "spaceships", cn.lower() + ".xml",
        )
        paks = ship_socpaks(entity_xml)
        total = Counter()
        for pak in paks:
            full = os.path.join(CACHE, "Data", pak.replace("/", os.sep))
            counts, ok = count_storage_in_socpak(full)
            if ok:
                total.update(counts)
        ref_items = (
            (ref.get(cn, {}).get("Hardpoints", {}).get("Components", {}).get("Storage", {})
             .get("InstalledItems") or [])
        )
        ref_count = len(ref_items)
        rows.append((cn, sum(total.values()), ref_count, dict(total)))

    print(f"{'Ship':<32} {'socpak_total':>12} {'ref_count':>10}  details")
    print("-" * 90)
    for cn, derived, ref_n, det in rows:
        match = "OK " if derived == ref_n else "   "
        print(f"{match} {cn:<30} {derived:>12} {ref_n:>10}  {det}")


if __name__ == "__main__":
    main()
