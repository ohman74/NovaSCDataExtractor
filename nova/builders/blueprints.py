"""Crafting blueprints catalog — full coverage of all 1500+ recipes.

`stdItem.Crafting` is embedded only in items that survive the
ship/FPS-equipment emission filters — magazines, char armor, and items
otherwise filtered out are absent from the equipment JSONs but DO have
recipes in `parsed_crafting.json`. This builder surfaces every parsed
blueprint, keyed by target item, with localized names and resolved
modifier/cost references so the UI gets one self-contained crafting
table.

Each entry:
- Target item metadata (GUID, ClassName, Name, Type, Size)
- Tiered recipe (slots, costs, quality-modifiers, total craft seconds)
- Modifiers expose the GPP class name (e.g. `GPP_Weapon_FireRate`) so
  consumers don't need a separate gpp lookup.
- Resource/Item cost GUIDs match the entries in `resources.json`.
"""

from typing import Any


def _craft_seconds(craft_time: dict) -> int:
    """Total craft time as integer seconds. CIG splits across
    days/hours/minutes/seconds fields; the UI almost always wants the
    sum rather than reconstructing it."""
    if not isinstance(craft_time, dict):
        return 0
    return (int(craft_time.get("days", 0)) * 86400
            + int(craft_time.get("hours", 0)) * 3600
            + int(craft_time.get("minutes", 0)) * 60
            + int(craft_time.get("seconds", 0)))


def _resolve_target_name(rec: dict, ctx) -> str:
    """Best-effort localized item name; fall back to className."""
    ad = rec.get("attachDef") or {}
    for key_field in ("name", "displayName", "shortName"):
        raw = ad.get(key_field, "")
        if raw.startswith("@"):
            val = ctx.resolve_name(raw)
            if val and not val.startswith("@"):
                return val
    return rec.get("className", "")


def _resolve_modifier(modifier: dict, ctx) -> dict:
    """Resolve a slot-modifier entry, replacing gppGuid with the GPP
    record's className + localized propertyName."""
    gpp_guid = modifier.get("gppGuid", "")
    gpp_rec = ctx.gpp_records.get(gpp_guid) or {}
    gpp_class = gpp_rec.get("className", "")
    prop_key = gpp_rec.get("propertyName", "")
    prop_name = ""
    if prop_key.startswith("@"):
        val = ctx.resolve_name(prop_key)
        if val and not val.startswith("@"):
            prop_name = val
    return {
        "GPP": gpp_class,
        "PropertyName": prop_name,
        # "multiplier" — value is a float multiplier on the base property
        # (e.g. Integrity 0.8x → 1.2x). "additive" — value is an integer
        # delta added to the base property (e.g. Power Pips +2).
        "Kind": modifier.get("kind", "multiplier"),
        "QualityRange": [modifier.get("startQuality", 0),
                         modifier.get("endQuality", 0)],
        "ModifierRange": [modifier.get("modifierAtStart", 0),
                          modifier.get("modifierAtEnd", 0)],
    }


def _shape_slot(slot: dict, ctx) -> dict:
    """Project a raw parsed slot into the output shape."""
    display_key = slot.get("displayName", "")
    display = display_key
    if display_key.startswith("@"):
        val = ctx.resolve_name(display_key)
        if val and not val.startswith("@"):
            display = val
    return {
        "Name": slot.get("name", ""),
        "DisplayName": display,
        "Costs": [
            {
                "Type": c.get("type", ""),       # "Resource" | "Item"
                "GUID": c.get("guid", ""),
                "Quantity": c.get("quantity", 0),
            }
            for c in slot.get("costs", [])
        ],
        "Modifiers": [
            _resolve_modifier(m, ctx)
            for m in slot.get("modifiers", [])
        ],
    }


def build_blueprints(ctx) -> list[dict]:
    """Build the blueprints.json output — all parsed crafting recipes,
    sorted by target ClassName for stable diffs."""
    items_by_guid = {rec["guid"].lower(): cn
                     for cn, rec in ctx.items.items() if rec.get("guid")}

    out: list[dict] = []
    for bp_guid, bp in ctx.crafting_blueprints.items():
        target_cn = items_by_guid.get(bp_guid.lower(), "")
        target_rec = ctx.items.get(target_cn) if target_cn else None
        if target_rec:
            ad = target_rec.get("attachDef") or {}
            target_name = _resolve_target_name(target_rec, ctx)
            target_type = ad.get("type", "")
            target_subtype = ad.get("subType", "")
            target_size = ad.get("size", 0)
        else:
            target_name = ""
            target_type = ""
            target_subtype = ""
            target_size = 0

        tiers_out: list[dict] = []
        for tier in bp.get("tiers", []):
            tiers_out.append({
                "Slots": [
                    _shape_slot(s, ctx) for s in tier.get("slots", [])
                ],
                "CraftTimeSeconds": _craft_seconds(tier.get("craftTime", {})),
            })

        out.append({
            "TargetGUID": bp_guid,
            "TargetClassName": target_cn,
            "TargetName": target_name,
            "TargetType": target_type,
            "TargetSubType": target_subtype,
            "TargetSize": target_size,
            "Tiers": tiers_out,
        })

    out.sort(key=lambda e: (e["TargetClassName"], e["TargetGUID"]))
    return out
