"""Build FPS attachment data JSON with full stdItem.

Filters to weapon-mountable FPS attachments only (sights, barrels, underbarrel, lights).
Excludes ship weapon barrels and templates. Cosmetic variants (color/tint
duplicates with identical gameplay-modifier signatures) are emitted with
`CosmeticVariantOf: <base>` tags rather than filtered out.
"""

from .stditem import build_std_item
from .cosmetic import detect_cosmetic_variants

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

    return False


def build_fps_attachments(ctx):
    """Build the FPS attachments output dataset.

    Cosmetic variants (color/tint/skin duplicates with identical
    gameplay-modifier signatures) are emitted with `CosmeticVariantOf: <base>`
    via the shared cosmetic-detection helper.
    """
    attachments_by_cn = {}

    for class_name, record in ctx.items.items():
        attach_def = record.get("attachDef")
        if not attach_def:
            continue

        item_type = attach_def.get("type", "")
        sub_type = attach_def.get("subType", "")

        if not _is_fps_attachment(item_type, sub_type, class_name, attach_def):
            continue

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
            "manufacturer": (mfr or {}).get("Code", ""),
            "classification": "",
            "stdItem": build_std_item(record, ctx),
        }

        attachments_by_cn[class_name] = attach

    # Tag cosmetic variants — same gameplay signature as a prefix-base item.
    cosmetic_map = detect_cosmetic_variants(
        attachments_by_cn, lambda a: a["stdItem"]
    )
    for cn, base_cn in cosmetic_map.items():
        attachments_by_cn[cn]["cosmeticVariantOf"] = base_cn
        std = attachments_by_cn[cn]["stdItem"]
        if std:
            std["CosmeticVariantOf"] = base_cn

    attachments = list(attachments_by_cn.values())
    attachments.sort(key=lambda a: (a.get("type", ""), a.get("className", "")))
    cosmetic_count = sum(1 for a in attachments if a.get("cosmeticVariantOf"))
    print(f"  Built {len(attachments)} FPS attachments "
          f"({cosmetic_count} cosmetic variants tagged)")
    return attachments
