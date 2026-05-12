"""Build ship equipment JSON with full stdItem data.

Cosmetic variants (LowPoly duplicates, color/skin variants with identical
gameplay stats) are emitted with `CosmeticVariantOf: <base>` tags rather
than filtered out — see `cosmetic.py`.

Editorial filters that REMAIN (these are not cosmetic; they have real
gameplay differences or are non-player templates):
- Templates (skeleton entities)
- Test/Master (dev placeholders)
- PUDefenseTurret / ground destructibles (NPC-only)
- PU_AI_VAN (Vanduul AI flight controllers)

Path-based NPC-installation filters:
- `/weapons/turret_unmanned/` (NPC ground turrets — Unmanned, Automated, AntiPersonnel)
- `/locations/` (Colonialism outposts and similar static installations)

Ship-bound NPC equipment (Bengal, Orbital_Sentry): items whose className
contains a ship-name stem belonging to a non-emitted vehicle. Derived
structurally from `ctx.vehicles` minus the emitted-ship set.
"""

from .stditem import build_std_item
from .cosmetic import detect_cosmetic_variants
from .ships import get_emitted_ship_classnames


# Single-token variant markers used to derive a stripped family key. When
# the first of these tokens is encountered while walking the className
# parts, the remainder is treated as a per-variant suffix.
_VARIANT_TOKENS = frozenset({
    "PU", "AI", "EA", "NPC", "Pirate", "Boarded", "Hijacked", "Crewless",
    "FleetWeek", "Fleetweek", "BIS", "CitizenCon2", "Showdown", "ShipShowdown",
    "Tutorial", "Mission", "Indestructible", "Advocacy", "Drug", "Piano",
    "Prison", "Template", "Dummy", "Wreck", "Derelict", "NoDebris",
    "NoInterior", "GameMaster", "Invictus", "FW22NFZ", "FW", "S42",
})

# Manufacturer prefixes seen in vehicle ClassNames. Stripped before
# computing the stripped family key.
_MFR_CODES = frozenset({
    "AEGS", "ANVL", "RSI", "DRAK", "CRUS", "CNOU", "MISC", "ORIG",
    "KRGR", "ESPR", "XNAA", "BANU", "GAMA", "GRIN", "TMBL", "GREY",
    "XIAN", "VNCL", "RKHM", "ARGO", "TUMB", "APAR", "BEHR", "GMNI",
    "HDGW", "KSAR", "KLWE", "LBCO", "SASU", "UTFL", "VOLT", "VANDUUL",
})


def _longest_common_prefix(strings):
    """Longest common underscore-token prefix shared by all input strings."""
    if not strings:
        return ""
    parts_lists = [s.split("_") for s in strings]
    common = []
    for tokens in zip(*parts_lists):
        if all(t == tokens[0] for t in tokens):
            common.append(tokens[0])
        else:
            break
    return "_".join(common)


def _strip_mfr_and_variant(prefix):
    """Strip manufacturer + trailing variant tokens from a className prefix."""
    parts = prefix.split("_")
    if parts and parts[0] in _MFR_CODES:
        parts = parts[1:]
    for i, p in enumerate(parts):
        if p in _VARIANT_TOKENS:
            parts = parts[:i]
            break
    return "_".join(parts)


def _build_family_keys(ctx):
    """Build family-key → is_excluded map for ship-bound equipment filtering.

    Each ship family (group sharing a `vehicleDefinition`) contributes
    two key forms — the longest common className prefix (e.g.
    `RSI_Aurora_Mk2`) and the mfr/variant-stripped short form (e.g.
    `Aurora_Mk2`). Both map to `is_excluded` (no emitted variants).

    Lookup uses longest-substring-match: when an item's className
    matches multiple keys, the longest wins. This discriminates between
    Aurora Mk1 (excluded, key `Aurora`) and Aurora Mk2 (kept, key
    `Aurora_Mk2`) for items like `RSI_Aurora_Mk2_Module_Cargo` that
    contain both as substrings — without this, "any excluded match
    wins" caused Mk2 modules to be dropped because of Mk1's status.
    """
    cached = getattr(ctx, "_family_keys", None)
    if cached is not None:
        return cached

    emitted = get_emitted_ship_classnames(ctx)
    by_def = {}
    for cn, rec in ctx.vehicles.items():
        vd = ((rec.get("vehicle") or {}).get("vehicleDefinition", "") or "").lower()
        if vd:
            by_def.setdefault(vd, []).append(cn)

    family_keys = {}
    for vd, members in by_def.items():
        excluded = not any(cn in emitted for cn in members)
        common = _longest_common_prefix(members)
        if common:
            # When two families produce the same key, prefer included (any
            # non-excluded family wins) — favor emission when ambiguous.
            family_keys[common] = family_keys.get(common, excluded) and excluded
        stripped = _strip_mfr_and_variant(common)
        if stripped and stripped != common:
            family_keys[stripped] = family_keys.get(stripped, excluded) and excluded

    ctx._family_keys = family_keys
    return family_keys


def _is_npc_only_equipment(class_name, record, family_keys):
    """Return True if the item belongs to a non-emitted ship or NPC installation."""
    path = (record.get("path", "") or "").lower()
    # Path-based NPC installations (not ship-bound).
    if "/weapons/turret_unmanned/" in path:
        return True
    if "/locations/" in path:
        return True
    # Bare `AI_Module_*` / `AIModule_*` items live at the root of /ships/
    # rather than under a per-ship subdir; catch them by className prefix.
    if class_name.startswith("AI_Module_") or class_name.startswith("AIModule_"):
        return True
    # Ship-bound equipment: longest-matching family key wins. Filter only
    # if the most-specific matching family is excluded (no emitted variants).
    best_len = 0
    best_excluded = False
    for key, excluded in family_keys.items():
        if len(key) > best_len and key in class_name:
            best_len = len(key)
            best_excluded = excluded
    return best_excluded


def _is_non_equippable(class_name):
    """Filter out items that can't be equipped on player ships/vehicles.

    Name-based by necessity (#7 in NAME_FILTERS.md, investigated 2026-04-21,
    re-audited 2026-05-06): every category here has been tested against
    structural alternatives that all over-filter legitimate items.

    What was REMOVED 2026-05-06 (now handled by CosmeticVariantOf tagging):
    - `_LowPoly` suffix items: byte-for-byte identical to base items, now
      emitted with `CosmeticVariantOf: <base>`. Detection is via signature
      comparison + className-prefix match.
    """
    cn = class_name.lower()

    # Templates
    if cn.endswith("_template") or "_template_" in cn:
        return True

    # Test/debug items
    if cn.startswith("test_") or "_test_" in cn or cn.startswith("master_"):
        return True

    # Holograms / dummies (visual placeholders, NOT cosmetic variants of
    # any base item — they have different geometry/components).
    if "fakehologram" in cn or "_dummy" in cn:
        return True

    # NPC-only PU defense installations (different gameplay tuning, not cosmetic)
    if "pudefenseturret" in cn:
        return True
    if "destructible_pu" in cn or "_ground_destructible" in cn:
        return True

    # NPC Vanduul AI flight controllers (AI-specific tuning)
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

    Cosmetic variants (LowPoly + color/skin/tint duplicates with identical
    gameplay signatures) are emitted with `CosmeticVariantOf: <base>` tags.

    Args:
        ctx: BuildContext

    Returns:
        List of equipment item dicts
    """
    equipment_by_cn = {}
    family_keys = _build_family_keys(ctx)

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

        # Skip non-equippable items: templates, test items, NPC-only.
        # Cosmetic variants (LowPoly, color skins) are NOT filtered here —
        # they're tagged below.
        if _is_non_equippable(class_name):
            continue

        # Skip equipment that belongs to non-emitted ships (Bengal,
        # Orbital_Sentry) or NPC-only installations (ground turrets,
        # outposts, AI_Module items).
        if _is_npc_only_equipment(class_name, record, family_keys):
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
            "manufacturer": (mfr or {}).get("Code", ""),
            "classification": "",
            "stdItem": build_std_item(record, ctx),
        }

        equipment_by_cn[class_name] = equip

    # Tag cosmetic variants — same gameplay signature as a prefix-base item.
    cosmetic_map = detect_cosmetic_variants(
        equipment_by_cn, lambda e: e["stdItem"]
    )
    for cn, base_cn in cosmetic_map.items():
        equipment_by_cn[cn]["cosmeticVariantOf"] = base_cn
        std = equipment_by_cn[cn]["stdItem"]
        if std:
            std["CosmeticVariantOf"] = base_cn

    equipment = list(equipment_by_cn.values())
    equipment.sort(key=lambda e: (e.get("type", ""), e.get("size", 0), e.get("className", "")))
    cosmetic_count = sum(1 for e in equipment if e.get("cosmeticVariantOf"))
    print(f"  Built {len(equipment)} ship equipment items "
          f"({cosmetic_count} cosmetic variants tagged)")
    return equipment
