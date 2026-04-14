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


def _is_fps_attachment(item_type, sub_type, class_name):
    """Check if this is an FPS weapon attachment (not a ship weapon barrel)."""
    cn_lower = class_name.lower()

    # Skip ship weapon barrels (uppercase manufacturer prefix + weapon type + Barrel)
    # e.g. BEHR_LaserCannon_Barrel_S1, GATS_BallisticGatling_Barrel_S3
    if item_type == "WeaponAttachment" and sub_type == "Barrel":
        # FPS barrels use lowercase: arma_barrel_comp_s1
        # Ship barrels use uppercase: BEHR_LaserCannon_Barrel_S1
        if class_name[0].isupper() and "_Barrel_" in class_name:
            return False

    # Skip generic templates
    if cn_lower.endswith("_template") or cn_lower.startswith("wep_") and "template" in cn_lower:
        return False
    if class_name in ("Barrel_Attachment", "Optics_TEMPLATE", "Underbarrel_TEMPLATE",
                       "WEP_Barrel_Template", "WEP_CannonBarrel_Template",
                       "WEP_GatlingBarrel_Template", "WEP_RepeaterBarrel_Template"):
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
    """Find base attachment by progressively stripping name segments."""
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

        if not _is_fps_attachment(item_type, sub_type, class_name):
            continue

        all_attachments[class_name] = record

    # Second pass: filter skin variants with identical modifier stats
    attachments = []
    for class_name, record in all_attachments.items():
        base_cn = _find_base_attachment(class_name, all_attachments)
        if base_cn:
            base_sig = _modifier_signature(all_attachments[base_cn])
            var_sig = _modifier_signature(record)
            if base_sig == var_sig:
                continue  # Same modifiers, skin-only variant

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
