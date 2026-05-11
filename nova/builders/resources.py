"""Resources catalog for crafting cost lookups.

Crafting blueprints (`stdItem.Crafting.costs`) reference resources via
opaque GUIDs. There are two types:

- **Resource** (SCU-based) — raw materials like Agricium / Iron / Quartz.
  GUIDs are not defined as `__ref` records anywhere in the DCB, only
  referenced. We resolve them by walking `entities/scitem/carryables/`
  for `<ResourceContainerDefaultCompositionEntry entry="GUID">` entries
  and deriving the resource name from the carryable filename
  (`carryable_*_commodity_{category}_{name}[_a].xml`).

- **Item** (unit-based) — hand-mineable harvestables like Aphorite /
  Hadanite. These resolve cleanly via `items_db` (entity className).

Emits `resources.json` with one entry per unique GUID — flat, sorted by
GUID, suitable for the UI to build a `{GUID: Name}` lookup map.
"""

import os
import re


# Match a carryable filename stem like:
#   carryable_tbo_fl_1scu_commodity_metal_agricium
#   carryable_2h_fl_05x05x05_commodity_metal_agricium_a
# Captures: category (metal/mineral/nonmetal/...) and name (with underscores).
# The optional trailing _a/_b/_c is a sub-variant suffix (different mesh).
_CARRYABLE_FILENAME_RE = re.compile(
    r"^carryable_[^_]+_fl_[^_]+_commodity_(?P<category>[^_]+)_(?P<name>.+?)(_[abc])?$"
)

_RESOURCE_ENTRY_RE = re.compile(
    rb'<ResourceContainerDefaultCompositionEntry\s+entry="([^"]+)"')
_SCU_RE = re.compile(rb'standardCargoUnits="([0-9.]+)"')
# Find the first <Reference value="..."> immediately inside <inclusiveGroups>.
_INCLUSIVE_GROUP_RE = re.compile(
    rb'<inclusiveGroups>\s*<Reference\s+value="([^"]+)"')


def _parse_carryable_name(filename_stem):
    """Extract (category, name_raw, is_ore) from a carryable filename stem.

    Returns (None, None, False) when the pattern doesn't match. `is_ore`
    is True when the filename contains `_ore` (the unrefined form, e.g.
    `commodity_metal_ore_agricium`).
    """
    m = _CARRYABLE_FILENAME_RE.match(filename_stem.lower())
    if not m:
        return None, None, False
    category = m.group("category")
    raw = m.group("name")
    tokens = raw.split("_")
    is_ore = "ore" in tokens
    if is_ore:
        tokens = [t for t in tokens if t != "ore"]
    return category, "_".join(tokens), is_ore


def _resolve_localized(translations, name_raw, is_ore):
    """Resolve `@items_commodities_{name}[_ore]` localization key.

    Falls back to title-cased raw name when the key is missing or returns
    an unresolved `@LOC_*` marker.
    """
    if not name_raw:
        return ""
    key = f"items_commodities_{name_raw}" + ("_ore" if is_ore else "")
    val = translations.get(key)
    if val and not val.startswith("@"):
        return val
    title = " ".join(t.capitalize() for t in name_raw.split("_"))
    if is_ore:
        title += " (Ore)"
    return title


def _collect_resource_carryables(cache_dir):
    """Walk `entities/scitem/carryables/`; return
    {resource_guid: [(filename_stem, scu, group_guid), ...]}.

    Each carryable XML declares one resource (via ResourceContainer) and
    one SCU capacity. Multiple carryables share the same resource GUID
    (size variants 0.125 / 1 / 2 / 4 / ... SCU of the same material).
    """
    base = os.path.join(cache_dir, "Data", "Libs", "Foundry", "Records",
                          "entities", "scitem", "carryables")
    out = {}
    if not os.path.isdir(base):
        return out
    for root, _dirs, files in os.walk(base):
        for f in files:
            if not f.endswith(".xml"):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            m = _RESOURCE_ENTRY_RE.search(data)
            if not m:
                continue
            guid = m.group(1).decode("ascii", errors="ignore").lower()
            scu_match = _SCU_RE.search(data)
            scu = float(scu_match.group(1)) if scu_match else None
            grp_match = _INCLUSIVE_GROUP_RE.search(data)
            group_guid = grp_match.group(1).decode("ascii", errors="ignore").lower() \
                if grp_match else ""
            stem = os.path.splitext(f)[0]
            out.setdefault(guid, []).append((stem, scu, group_guid))
    return out


def build_resources(ctx):
    """Build the resources.json output.

    Walks crafting blueprints for unique cost GUIDs, then resolves
    Resource-type via carryable entity scan and Item-type via items_db.
    """
    # Collect unique cost GUIDs by type from blueprints.
    resource_guids = set()
    item_guids = set()
    for bp in ctx.crafting_blueprints.values():
        for tier in bp.get("tiers", []):
            for slot in tier.get("slots", []):
                for cost in slot.get("costs", []):
                    g = (cost.get("guid") or "").lower()
                    if not g:
                        continue
                    t = cost.get("type")
                    if t == "Resource":
                        resource_guids.add(g)
                    elif t == "Item":
                        item_guids.add(g)

    out = []

    # Resource-type (SCU) — scan carryables once, resolve per GUID.
    carryables = _collect_resource_carryables(ctx.cache_dir)
    for guid in sorted(resource_guids):
        carryable_list = carryables.get(guid, [])
        if not carryable_list:
            out.append({
                "GUID": guid,
                "Name": guid,
                "UnitType": "SCU",
                "Category": "",
                "GroupGUID": "",
                "AvailableSCUSizes": [],
            })
            continue
        # Try each carryable's stem for a parseable name; first hit wins.
        category, name_raw, is_ore = None, None, False
        for stem, _scu, _grp in carryable_list:
            category, name_raw, is_ore = _parse_carryable_name(stem)
            if name_raw:
                break
        display = _resolve_localized(ctx.translations, name_raw or guid, is_ore)
        scu_sizes = sorted({s for _, s, _ in carryable_list if s is not None})
        group_guid = next((g for _, _, g in carryable_list if g), "")
        out.append({
            "GUID": guid,
            "Name": display,
            "UnitType": "SCU",
            "Category": category or "",
            "GroupGUID": group_guid,
            "AvailableSCUSizes": scu_sizes,
        })

    # Item-type (Units) — resolve via items_db's guid index.
    items_by_guid = {rec["guid"].lower(): cn
                     for cn, rec in ctx.items.items() if rec.get("guid")}
    for guid in sorted(item_guids):
        cn = items_by_guid.get(guid)
        if not cn:
            out.append({
                "GUID": guid,
                "Name": guid,
                "UnitType": "Units",
                "ClassName": "",
                "Category": "",
            })
            continue
        rec = ctx.items[cn]
        ad = rec.get("attachDef") or {}
        # attachDef.name is a translation key like @harvestable_aphorite.
        name_key = ad.get("name", "")
        display = cn
        if name_key.startswith("@"):
            t = ctx.translations.get(name_key[1:])
            if t and not t.startswith("@"):
                display = t
        out.append({
            "GUID": guid,
            "Name": display,
            "UnitType": "Units",
            "ClassName": cn,
            "Category": ad.get("subType", "") or ad.get("type", ""),
        })

    return out
