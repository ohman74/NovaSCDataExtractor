"""Build FPS weapon data JSON with full stdItem.

Emits ALL player-equippable FPS weapons including cosmetic variants.
Items that are pure skin/color/tint variants of a base weapon are
emitted with `CosmeticVariant: true` and `CosmeticVariantOf: <base>`
flags so consumers can hide or aggregate them as desired.

Filter chain:
1. Structural: must have a player-weapon component (SMeleeWeapon...,
   SWeapon..., weapon, SPrimeable... for grenades).
2. Path: drops dev/test items in `/dev/` directory.
3. Editorial name fallbacks: vlk_ (Vanduul NPC), salvage_repair (routed
   to fps_attachments.py), _template suffix, Yormandi_Weapon (dev).
"""

from .stditem import build_std_item
from .cosmetic import detect_cosmetic_variants


FPS_WEAPON_TYPES = {"WeaponPersonal", "Knife", "Grenade"}


_PLAYER_WEAPON_COMPONENTS = (
    "SMeleeWeaponComponentParams",
    "SWeaponModifierComponentParams",
    "weapon",
    "SPrimeableComponentParams",
)


def _is_non_player_fps(class_name, record):
    """Filter out non-player FPS items.

    Primary filter is structural: an item is only player-equippable if it
    carries a functional weapon component (`SMeleeWeaponComponentParams`,
    `SWeaponModifierComponentParams`, `weapon`, or `SPrimeableComponentParams`
    for grenades). This catches Carryable_*/EntitySpawner_*, most templates,
    test gadgets, and placeable mines without enumerating their names.

    Path-based: items under `/dev/` directory are CIG's internal test
    weapons (e.g. *_test_inf_ammo) — never player-facing.

    The remaining name fallbacks (audited 2026-05-06) handle items that
    DO carry weapon components but are not player equipment for editorial
    reasons:
    - vlk_ (Vanduul NPC weapons): real SMeleeWeaponComponentParams, not
      obtainable by players. No tag/structural marker distinguishes them.
    - salvage_repair: real weapon attachments routed to fps_attachments.py.
    - _template suffix: template skeletons that happen to have weapon comp
      (FPS_Throwable_TEMPLATE).
    - Yormandi_Weapon: dev placeholder with weapon component.
    """
    comps = record.get("components", {}) or {}
    if not any(c in comps for c in _PLAYER_WEAPON_COMPONENTS):
        return True

    path = (record.get("path", "") or "").lower()
    if "/dev/" in path or "\\dev\\" in path:
        return True

    cn = class_name.lower()

    if cn.endswith("_template") or "_template_" in cn:
        return True
    if cn.startswith("vlk_"):
        return True
    # Multitool sub-attachments (`grin_multitool_01_salvage_repair`) are
    # WeaponAttachment.Utility and routed to fps_attachments.py. The
    # standalone Cambio SRT salvage tool (`grin_salvage_repair_01`) is
    # WeaponPersonal.Gadget and belongs here. Discriminate by type so the
    # standalone gadget isn't dropped along with sub-attachments.
    attach_def = record.get("attachDef") or {}
    if "salvage_repair" in cn and attach_def.get("type") == "WeaponAttachment":
        return True
    if cn == "yormandi_weapon":
        return True

    return False


def build_fps_weapons(ctx):
    """Build the FPS weapons output dataset.

    Emits all player-equippable FPS weapons. Items that are cosmetic
    variants of a base weapon (same gameplay signature, classname is a
    suffix-extension of the base) get `CosmeticVariant: true` +
    `CosmeticVariantOf: <base_classname>` flags.
    """
    all_weapons = {}

    for class_name, record in ctx.items.items():
        attach_def = record.get("attachDef")
        if not attach_def:
            continue

        item_type = attach_def.get("type", "")
        components = record.get("components", {})

        base_type = item_type.split(".")[0] if "." in item_type else item_type
        is_fps = base_type in FPS_WEAPON_TYPES or "fpsWeapon" in components

        if not is_fps:
            continue

        if _is_non_player_fps(class_name, record):
            continue

        sub_type = attach_def.get("subType", "")
        mfr_guid = attach_def.get("manufacturerGuid", "")
        mfr = ctx.get_manufacturer(mfr_guid)

        weapon = {
            "className": class_name,
            "reference": record.get("guid", ""),
            "itemName": class_name.lower(),
            "type": item_type,
            "subType": sub_type,
            "tags": attach_def.get("tags", ""),
            "requiredTags": attach_def.get("requiredTags", ""),
            "size": attach_def.get("size", 0),
            "grade": attach_def.get("grade", 0),
            "name": attach_def.get("name", ""),
            "manufacturer": (mfr or {}).get("Code", ""),
            "classification": "",
            "stdItem": build_std_item(record, ctx),
        }

        all_weapons[class_name] = weapon

    # Tag cosmetic variants. Two signals (union):
    #   1. SCItemWeaponComponentParams.geometryTags — CIG's explicit skin
    #      identifier (e.g. "Black02", "Tint01", "Collector01"). Catches
    #      275/378 items including ones whose signatures differ for
    #      incidental reasons (separate Crafting blueprint, Class label
    #      inconsistencies between base and variants).
    #   2. Gameplay-signature equivalence with a prefix-base. Catches
    #      melee weapons (which use SCItemMeleeWeaponParams instead) and
    #      numbered duplicates (banu_melee_02/03/04 sharing stats with _01).
    def _skin_tag(weapon):
        comps = ctx.items[weapon["className"]].get("components", {})
        wcomp = comps.get("weapon", {}) if isinstance(comps, dict) else {}
        return wcomp.get("geometryTags", "") if isinstance(wcomp, dict) else ""

    cosmetic_map = detect_cosmetic_variants(
        all_weapons, lambda w: w["stdItem"], get_skin_tag=_skin_tag
    )
    for cn, base_cn in cosmetic_map.items():
        all_weapons[cn]["cosmeticVariant"] = True
        all_weapons[cn]["cosmeticVariantOf"] = base_cn
        std = all_weapons[cn]["stdItem"]
        if std:
            std["CosmeticVariant"] = True
            std["CosmeticVariantOf"] = base_cn

    weapons = list(all_weapons.values())
    weapons.sort(key=lambda w: (w.get("type", ""), w.get("className", "")))
    cosmetic_count = sum(1 for w in weapons if w.get("cosmeticVariant"))
    print(f"  Built {len(weapons)} FPS weapons "
          f"({cosmetic_count} cosmetic variants tagged)")
    return weapons
