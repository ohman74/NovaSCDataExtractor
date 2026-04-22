"""Build FPS weapon data JSON with full stdItem.

Filters out:
- Skin variants with identical stats to their base weapon
- Carryable/spawner items (glowsticks, utensils, etc.)
"""

from .stditem import build_std_item

FPS_WEAPON_TYPES = {"WeaponPersonal", "Knife", "Grenade"}


def _is_non_player_fps(class_name, attach_def):
    """Filter out non-player FPS items.

    Name-based by necessity (#8 in NAME_FILTERS.md, investigated
    2026-04-21): tested "no manufacturer" as a structural signal — would
    correctly flag vlk_ Vanduul weapons, EntitySpawner_*, and named dev
    items (JanitorMob, Tablet_Small, Yormandi_Weapon), but would also
    drop 2 legitimate items (none_melee_01, kegr_fire_extinguisher_01)
    that have empty manufacturer by design. Mines (_ltp_/_prx_) have
    real manufacturers but are excluded as "placed not equipped" per
    reference convention. Carryable_* glowsticks/utensils have proper
    manufacturers too. No clean structural signal across these classes.
    """
    cn = class_name.lower()

    # Carryable items (glowsticks, utensils, flares)
    if cn.startswith("carryable_") or cn.startswith("entityspawner_"):
        return True

    # Templates, test items
    if cn.endswith("_template") or cn.startswith("test_") or "_template_" in cn:
        return True

    # Placeholder / dev items
    if cn in ("janitormob", "tablet_small", "yormandi_weapon"):
        return True

    # Vanduul NPC weapons (not obtainable by players)
    if cn.startswith("vlk_"):
        return True

    # salvage_repair attachments are handled by fps_attachments.py, not here
    if "salvage_repair" in cn:
        return True

    # Mines (not available to players)
    if any(p in cn for p in ["mine", "_ltp_", "_prx_", "lasertrip", "proximity"]):
        return True

    return False


def _weapon_signature(std_item):
    """Extract combat-relevant stats for variant comparison."""
    weapon = std_item.get("Weapon", {})
    ammo = weapon.get("Ammunition", {})
    firing = weapon.get("Firing", [])

    sig = {
        "ammo_speed": ammo.get("Speed", 0),
        "ammo_range": ammo.get("Range", 0),
        "ammo_damage": str(ammo.get("ImpactDamage", {})),
        "ammo_detonation": str(ammo.get("DetonationDamage", {})),
        "firing": str([(
            f.get("RoundsPerMinute", 0),
            f.get("DamagePerShot", {}),
            f.get("PelletsPerShot", 0),
        ) for f in firing]),
    }
    return frozenset(sig.items())


def _find_base_weapon(class_name, all_weapons):
    """Find the base weapon by progressively stripping name segments.

    Handles both suffix-style (base → base_variant) and numbered variants
    (base_01 → base_02/03/04 by replacing the last numeric suffix with _01).

    Name-based by necessity (#10 in NAME_FILTERS.md): parsed item records
    carry no `parentRef` / `inheritsFrom` / base-item pointer, and the
    signature comparison below needs a specific base to diff against. The
    `SCItemPurchasableParams.displayName` clusters variants together but
    doesn't identify which cluster member is the base. Segment-stripping
    matches CIG's ClassName convention (base name is a prefix of variant
    names). Used only for signature-dedup lookup — not a filter — so a
    miss is non-fatal.
    """
    parts = class_name.split("_")
    # Try progressive suffix stripping first
    for i in range(len(parts) - 1, 1, -1):
        candidate = "_".join(parts[:i])
        if candidate != class_name and candidate in all_weapons:
            return candidate
    # Try replacing the last numeric suffix with _01 (banu_melee_02 → banu_melee_01)
    if parts and parts[-1].isdigit() and parts[-1] != "01":
        candidate = "_".join(parts[:-1] + ["01"])
        if candidate != class_name and candidate in all_weapons:
            return candidate
    return None


def build_fps_weapons(ctx):
    """Build the FPS weapons output dataset."""
    # First pass: collect all weapons
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

        # Skip non-equippable items
        if _is_non_player_fps(class_name, attach_def):
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
            "manufacturer": mfr["Code"] if mfr else "",
            "classification": "",
            "stdItem": build_std_item(record, ctx),
        }

        all_weapons[class_name] = weapon

    # Second pass: filter skin variants with identical stats
    weapons = []
    for class_name, weapon in all_weapons.items():
        # Name-based orphan check: CIG's `_01_<suffix>` pattern marks
        # dev/event variants (sasu_pistol_toy_01_ea_elim,
        # grin_multitool_01_default_grapple, kegr_fire_extinguisher_01_Igniter,
        # plus all *_01_brown01/red01/tint01 skin variants). The ref
        # catalogue drops these entirely. Confirmed via experiment: removing
        # this check lets 3 items through whose signatures legitimately
        # differ from their base — so signature-dedup alone can't replace
        # it. Retained as last-resort (#9 in NAME_FILTERS.md).
        parts = class_name.split("_")
        has_01_then_suffix = False
        for idx in range(len(parts) - 1):
            if parts[idx] == "01" and idx < len(parts) - 1:
                has_01_then_suffix = True
                break
        if has_01_then_suffix:
            continue

        base_cn = _find_base_weapon(class_name, all_weapons)
        if base_cn:
            base_sig = _weapon_signature(all_weapons[base_cn]["stdItem"])
            var_sig = _weapon_signature(weapon["stdItem"])
            if base_sig == var_sig:
                continue  # Skin-only variant, skip
        else:
            # No base found in our output. Check if this is an orphan variant:
            # - className has an "_01" segment followed by extra suffix segments
            #   (e.g. sasu_pistol_toy_01_ea_elim, grin_multitool_01_default_grapple)
            # - className ends with a short variant suffix like _cen01, _imp01
            # - className matches a variant of a base that doesn't exist in ctx.items
            #   (e.g. rrs_melee_01_fallout01, where rrs_melee_01 itself is absent)
            parts = class_name.split("_")
            is_orphan_variant = False
            # Pattern 1: has _01 at position i<last, followed by extra segments
            for idx in range(len(parts) - 1):
                if parts[idx] == "01" and idx < len(parts) - 1:
                    is_orphan_variant = True
                    break
            # Pattern 2: last segment ends with 2-digit-variant like _cen01, _imp01, _01_fallout01
            if not is_orphan_variant and len(parts) >= 3:
                last = parts[-1]
                if (len(last) > 2 and last[-2:].isdigit() and not last.isdigit()):
                    # e.g. "cen01", "imp01", "fallout01" — variant suffix
                    is_orphan_variant = True

            if is_orphan_variant:
                continue

        weapons.append(weapon)

    weapons.sort(key=lambda w: (w.get("type", ""), w.get("className", "")))
    print(f"  Built {len(weapons)} FPS weapons")
    return weapons
