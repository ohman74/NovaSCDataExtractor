"""Build FPS weapon data JSON with full stdItem.

Filters out:
- Skin variants with identical stats to their base weapon
- Carryable/spawner items (glowsticks, utensils, etc.)
"""

from .stditem import build_std_item

FPS_WEAPON_TYPES = {"WeaponPersonal", "Knife", "Grenade"}


def _is_non_player_fps(class_name, attach_def):
    """Filter out non-player FPS items."""
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

    # Multitools, fire extinguishers (utility, not weapons)
    if "multitool" in cn or "fire_extinguisher" in cn or "salvage_repair" in cn:
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
    """Find the base weapon by progressively stripping name segments."""
    parts = class_name.split("_")
    for i in range(len(parts) - 1, 1, -1):
        candidate = "_".join(parts[:i])
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
        base_cn = _find_base_weapon(class_name, all_weapons)
        if base_cn:
            base_sig = _weapon_signature(all_weapons[base_cn]["stdItem"])
            var_sig = _weapon_signature(weapon["stdItem"])
            if base_sig == var_sig:
                continue  # Skin-only variant, skip

        weapons.append(weapon)

    weapons.sort(key=lambda w: (w.get("type", ""), w.get("className", "")))
    print(f"  Built {len(weapons)} FPS weapons")
    return weapons
