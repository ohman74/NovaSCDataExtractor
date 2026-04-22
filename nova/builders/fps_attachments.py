"""Build FPS attachment data JSON with full stdItem.

Filters to weapon-mountable FPS attachments only (sights, barrels, underbarrel, lights).
Excludes ship weapon barrels and templates.
"""

from .stditem import build_std_item

# SubTypes that are FPS weapon attachments
_FPS_SUBTYPES = {
    "IronSight", "Barrel", "BottomAttachment", "Utility",
    "Missile",
}


def _is_fps_attachment(item_type, sub_type, class_name, attach_def=None):
    """Check if this is an FPS weapon attachment (not a ship weapon barrel).

    Structural discriminators for the WeaponAttachment.Barrel case (both
    FPS and ship barrels share this type):
    - FPS barrels carry the `FPS_Barrel` tag (CIG's own marker).
    - Ship barrels carry the `uneditable` tag and no `FPS_Barrel`.
    Templates lack either tag; handled by the placeholder-name check
    below.
    """
    cn_lower = class_name.lower()
    ad = attach_def or {}
    tags = (ad.get("tags", "") or "")

    # WeaponAttachment.Barrel is shared by FPS and ship barrels. Use the
    # `FPS_Barrel` structural tag to discriminate (replaces the old
    # uppercase-first-letter name check — #11 in NAME_FILTERS.md).
    if item_type == "WeaponAttachment" and sub_type == "Barrel":
        if "FPS_Barrel" in tags:
            pass  # fall through to the FPS allow-list below
        else:
            # Ship barrel (uneditable) or generic template (empty tags).
            return False

    # Skip generic WeaponAttachment templates — placeholder name + no
    # manufacturer. Light.Weapon items with the same shape are NOT
    # templates (e.g. weapon_underbarrel_light variants), so scope this
    # check to WeaponAttachment only.
    if (item_type == "WeaponAttachment"
            and ad.get("name", "") == "@LOC_PLACEHOLDER"
            and not ad.get("manufacturerGuid", "")):
        return False

    if item_type == "WeaponAttachment" and sub_type in _FPS_SUBTYPES:
        return True
    if item_type == "Light" and sub_type == "Weapon":
        return True
    if "weapon_underbarrel_light" in cn_lower:
        return True

    return False


def _modifier_signature(record):
    """Extract the weapon modifier stats for variant comparison.

    Uses SWeaponModifierComponentParams which contains recoil, spread,
    aim/zoom, and damage modifiers — the actual gameplay-affecting data.
    """
    comps = record.get("components", {})
    mod = comps.get("SWeaponModifierComponentParams", {})
    return str(mod.get("modifier", {}))


def _find_base_attachment(class_name, all_records):
    """Find base attachment by progressively stripping name segments.

    Same rationale as `_find_base_weapon` (#10 in NAME_FILTERS.md):
    no parent-ref signal exists in the parsed item records, so we fall
    back to CIG's ClassName-prefix convention. Used only for signature
    comparison — not a filter.
    """
    parts = class_name.split("_")
    for i in range(len(parts) - 1, 1, -1):
        candidate = "_".join(parts[:i])
        if candidate != class_name and candidate in all_records:
            return candidate
    return None


def build_fps_attachments(ctx):
    """Build the FPS attachments output dataset."""
    # First pass: collect all valid attachments with their raw records
    all_attachments = {}

    for class_name, record in ctx.items.items():
        attach_def = record.get("attachDef")
        if not attach_def:
            continue

        item_type = attach_def.get("type", "")
        sub_type = attach_def.get("subType", "")

        if not _is_fps_attachment(item_type, sub_type, class_name, attach_def):
            continue

        all_attachments[class_name] = record

    # Second pass: build all attachments (ref includes color/tint variants)
    attachments = []
    for class_name, record in all_attachments.items():
        attach_def = record.get("attachDef", {})
        mfr_guid = attach_def.get("manufacturerGuid", "")
        mfr = ctx.get_manufacturer(mfr_guid)

        attach = {
            "className": class_name,
            "reference": record.get("guid", ""),
            "itemName": class_name.lower(),
            "type": attach_def.get("type", ""),
            "subType": attach_def.get("subType", ""),
            "tags": attach_def.get("tags", ""),
            "requiredTags": attach_def.get("requiredTags", ""),
            "size": attach_def.get("size", 0),
            "grade": attach_def.get("grade", 0),
            "name": attach_def.get("name", ""),
            "manufacturer": mfr["Code"] if mfr else "",
            "classification": "",
            "stdItem": build_std_item(record, ctx),
        }

        attachments.append(attach)

    attachments.sort(key=lambda a: (a.get("type", ""), a.get("className", "")))
    print(f"  Built {len(attachments)} FPS attachments")
    return attachments
