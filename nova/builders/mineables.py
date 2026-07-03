"""Mineable-element physics catalog (mining/mineableelements records).

Each MineableElement record carries the mining-minigame parameters for one
ore / raw material: rock instability, laser resistance, optimal charge-window
shape, overcharge explosion multiplier, and cluster factor. The record's
`resourceType` GUID is the same resource GUID space used by crafting costs
(resources.json) and cargo commodities, so consumers can join on it.

Name resolution: the record className (e.g. Agricium_Ore, Quantainium_Raw)
lowercased is the localization suffix — `items_commodities_agricium_ore` →
"Agricium (Ore)". Falls back to the suffix-less key, then title-cased
className.
"""

import os
import re
import xml.etree.ElementTree as ET

from ..utils import safe_float

_ORE_RAW_SUFFIX_RE = re.compile(r"_(ore|raw)$")


def _display_name(class_name, translations):
    for key in (f"items_commodities_{class_name.lower()}",
                f"items_commodities_{_ORE_RAW_SUFFIX_RE.sub('', class_name.lower())}"):
        val = translations.get(key)
        if val and not val.startswith("@"):
            return val
    return " ".join(t.capitalize() for t in class_name.split("_"))


def build_mineables(ctx):
    """Build mineables.json from Libs/Foundry/Records/mining/mineableelements."""
    base = os.path.join(ctx.cache_dir, "Data", "Libs", "Foundry", "Records",
                        "mining", "mineableelements")
    out = []
    if not os.path.isdir(base):
        print("  mineableelements records not found")
        return out
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".xml"):
            continue
        try:
            root = ET.parse(os.path.join(base, fn)).getroot()
        except ET.ParseError:
            print(f"  ! mineable parse failed: {fn}")
            continue
        if root.get("__type") != "MineableElement":
            continue
        tag = root.tag
        class_name = tag.split(".", 1)[1] if "." in tag else tag
        out.append({
            "ClassName": class_name,
            "GUID": root.get("__ref", ""),
            "ResourceGUID": (root.get("resourceType", "") or "").lower(),
            "Name": _display_name(class_name, ctx.translations),
            "Instability": safe_float(root.get("elementInstability", "0")),
            "Resistance": safe_float(root.get("elementResistance", "0")),
            "OptimalWindow": {
                "Midpoint": safe_float(root.get("elementOptimalWindowMidpoint", "0")),
                "MidpointRandomness": safe_float(
                    root.get("elementOptimalWindowMidpointRandomness", "0")),
                "Thinness": safe_float(root.get("elementOptimalWindowThinness", "0")),
            },
            "ExplosionMultiplier": safe_float(root.get("elementExplosionMultiplier", "0")),
            "ClusterFactor": safe_float(root.get("elementClusterFactor", "0")),
        })
    out.sort(key=lambda e: (e["Name"], e["ClassName"]))
    print(f"  Built {len(out)} mineable elements")
    return out
