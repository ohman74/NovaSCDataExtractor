"""Build ship equipment JSON with full stdItem data."""

from .stditem import build_std_item


def _is_non_equippable(class_name):
    """Filter out items that can't be equipped on player ships/vehicles.

    Name-based by necessity (#7 in NAME_FILTERS.md, investigated 2026-04-21):
    - Templates (133 caught): share `name == @LOC_PLACEHOLDER` + no
      manufacturer with 60+ legitimate items (Locker_PH,
      GRIN_ROC_CargoGrid_Main, Colonialism_Outpost_*, bay doors, RN_*
      resource nodes, etc.) that SPViewer's reference catalogue keeps.
      No tighter structural filter exists.
    - LowPoly duplicates (27 caught): byte-for-byte identical to the real
      item — same components, same attachDef. The `_LowPoly` suffix is
      CIG's only discriminator.
    - Test/Master (8), PUDefenseTurret (3), Ground_Destructible (29),
      PU_AI_VAN (4): editorial NPC flags. Tag/manufacturer profiles
      overlap with real equipment.

    Kept narrower than "truly non-equippable" because the reference
    catalogue includes some static-scene items (RADR_*_Fake,
    Colonialism_Outpost_*, Orbital_Sentry_*, GATS_*_fps_balance).
    """
    cn = class_name.lower()

    # Templates
    if cn.endswith("_template") or "_template_" in cn:
        return True

    # Test/debug items
    if cn.startswith("test_") or "_test_" in cn or cn.startswith("master_"):
        return True

    # Low-poly / hologram / dummy (but NOT _fake — SPViewer includes RADR_*_Fake)
    if "lowpoly" in cn or "fakehologram" in cn or "_dummy" in cn:
        return True

    # NPC-only PU defense installations (but allow Colonialism_ and Orbital_Sentry_ — in ref)
    if "pudefenseturret" in cn:
        return True
    if "destructible_pu" in cn or "_ground_destructible" in cn:
        return True

    # NPC Vanduul AI flight controllers
    if "_pu_ai_van" in cn:
        return True

    return False


# Item types to INCLUDE (meaningful ship/vehicle equipment)
_INCLUDED_TYPES = {
    # Weapons
    "WeaponGun", "WeaponDefensive", "WeaponMining", "WeaponSalvage",
    # Launchers
    "MissileLauncher", "BombLauncher", "GroundVehicleMissileLauncher",
    # Ordnance
    "Missile", "Bomb",
    # Turrets
    "Turret", "TurretBase", "UtilityTurret",
    # Defense
    "Shield", "Armor",
    # Power & Cooling
    "PowerPlant", "Cooler",
    # Drives
    "QuantumDrive", "JumpDrive",
    # Avionics
    "Radar", "Scanner",
    # Controllers
    "FlightController", "ShieldController", "WheeledController",
    # Modules
    "Module", "Container",
    # Utility
    "LifeSupportGenerator", "EMP", "SelfDestruct",
    "QuantumInterdictionGenerator", "TractorBeam", "TowingBeam",
    "MiningModifier", "SalvageModifier", "SalvageHead", "SalvageFieldEmitter",
    "ToolArm", "Gadget",
    # Paints & Flairs
    "Paints", "Flair_Cockpit",
}


def build_ship_equipment(ctx):
    """Build the ship equipment output dataset with full stdItem.

    Args:
        ctx: BuildContext

    Returns:
        List of equipment item dicts
    """
    equipment = []

    for class_name, record in ctx.items.items():
        attach_def = record.get("attachDef")
        if not attach_def:
            continue

        item_type = attach_def.get("type", "")
        if not item_type:
            continue

        base_type = item_type.split(".")[0] if "." in item_type else item_type
        if base_type not in _INCLUDED_TYPES:
            continue

        # Skip FPS items (handled by fps_weapons/fps_attachments).
        # Use path only for personal/FPS item types so that ship weapons with
        # "_fps_balance" suffixes (like GATS_BallisticGatling_Mounted_S1) stay.
        path = record.get("path", "").lower()
        if "personal" in item_type.lower():
            continue
        if "fps" in path and base_type in {"WeaponPersonal", "FPS_Deployable",
                                             "FPS_Consumable", "FPS_Radar",
                                             "RemovableChip"}:
            continue

        # Skip non-equippable items: templates, test items, NPC-only, low-poly, dummies
        if _is_non_equippable(class_name):
            continue

        sub_type = attach_def.get("subType", "")
        full_type = f"{item_type}.{sub_type}" if sub_type and sub_type != "UNDEFINED" else item_type

        mfr_guid = attach_def.get("manufacturerGuid", "")
        mfr = ctx.get_manufacturer(mfr_guid)

        equip = {
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

        equipment.append(equip)

    equipment.sort(key=lambda e: (e.get("type", ""), e.get("size", 0), e.get("className", "")))
    print(f"  Built {len(equipment)} ship equipment items")
    return equipment
