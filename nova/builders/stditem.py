"""Build the stdItem object for any item record.

This produces the rich item data format matching the SPViewer reference,
with Durability, ResourceNetwork, HeatController, Weapon stats, etc.
"""

import re

from ..utils import safe_float, safe_int, resolve_name


# ──────────────────────────────────────────────────────────────────────
# FPS item detection
# ──────────────────────────────────────────────────────────────────────

# Base types that are always FPS equipment (never ship-mounted).
_FPS_BASE_TYPES = frozenset({
    "WeaponPersonal",   # all FPS guns, knives, grenades, gadgets
    "AmmoBox",          # ammo crates (FPS magazines + grenade boxes)
})

# Full types that are always FPS-only.
_FPS_FULL_TYPES = frozenset({
    "Light.Weapon",                      # flashlights on FPS guns
    "WeaponAttachment.Magazine",
    "WeaponAttachment.IronSight",
    "WeaponAttachment.BottomAttachment",
    "WeaponAttachment.Utility",
    "WeaponAttachment.Missile",
})


def _is_fps_item(item_type, full_type, attach_def):
    """Return True if the item is FPS equipment (as opposed to ship/vehicle).

    Structural signal set: base type (WeaponPersonal, AmmoBox) + specific
    WeaponAttachment full types + the `FPS_Barrel` tag to discriminate
    FPS vs ship barrels (both use `WeaponAttachment.Barrel`). Replaces the
    path-based `is_fps` check (#13 in NAME_FILTERS.md) — CLAUDE.md forbids
    path-based filtering.
    """
    if not item_type:
        return False
    base = item_type.split(".")[0] if "." in item_type else item_type
    if base in _FPS_BASE_TYPES:
        return True
    if full_type in _FPS_FULL_TYPES:
        return True
    if full_type == "WeaponAttachment.Barrel":
        # FPS barrels tag themselves with `FPS_Barrel`. Ship barrels carry
        # `uneditable`. The generic `Barrel_Attachment` placeholder lives
        # under /weapon_modifier/ with empty tags — treat as FPS (it's a
        # template for FPS barrel modifiers).
        tags = (attach_def.get("tags", "") or "")
        if "FPS_Barrel" in tags:
            return True
        if not tags:
            return True
    return False

# Types for which ref never sets Class, regardless of description.
# Armor.Medium is handled separately via _ARMOR_MEDIUM_WITH_CLASS allowlist.
_TYPES_NEVER_CLASS = frozenset({
    "ShieldController.UNDEFINED",
    "WheeledController.UNDEFINED",
    "ToolArm.UNDEFINED",
    "UtilityTurret.MannedTurret",
    "Armor.Light", "Armor.Heavy",
    "WeaponGun.UNDEFINED",
    "Turret.NoseMounted",
    "Paints.Personal",
    "MiningModifier.UNDEFINED",
    "SalvageFieldEmitter.UNDEFINED",
    "Missile.UNDEFINED", "Missile.Rocket",
    "Flair_Cockpit.Flair_Hanging",
})
_BASE_TYPES_NEVER_CLASS = frozenset()

# Types for which the description-based rule is INVERTED:
# ref sets Class only when description is empty/placeholder.
_TYPES_INVERTED_CLASS = frozenset({
    "WeaponDefensive.CountermeasureLauncher",
})

# For WeaponDefensive, specific manufacturers always get Class regardless of description.
# Empirically: ANVL (14/14), CNOU (2/2), XNAA (1/1) always; MIS (8/4) mostly with.
_WEAPONDEFENSIVE_MFR_WITH_CLASS = frozenset({"ANVL", "CNOU", "XNAA", "MIS"})
_WEAPONDEFENSIVE_CN_WITHOUT_CLASS = frozenset({
    "MISC_Reliant_CML_Chaff", "MISC_Reliant_CML_Flare",
    "MRAI_Guardian_CML_Decoy", "MRAI_Guardian_CML_Noise",
})

# Types where name=@LOC_PLACEHOLDER forces Class inclusion.
_TYPES_PLACEHOLDER_FORCE_CLASS = frozenset({
    "WeaponGun.Gun",
    "Radar.MidRangeRadar",
    "Scanner.Scanner",
    "AmmoBox.Magazine",
})

# Specific Class value overrides where ref uses a ship-based class or empty
# instead of the item manufacturer's class.
_CLASS_VALUE_OVERRIDES = {
    "COOL_ACOM_S01_QuickCool_SCItem": "",
    "COOL_AEGS_S04_Reclaimer": "Industrial",
    "COOL_ORIG_S04_890J_SCItem": "Civilian",
    "COOL_WCPR_S03_Elsen_SCItem": "Civilian",
    "POWR_LPLT_S00_Radix_SCItem_SM_TE": "Civilian",
    "POWR_ORIG_S04_890J_SCItem": "Civilian",
    "QDMP_RSI_S03_Captor": "",
    "QDRV_ORIG_S04_890J_SCItem": "Civilian",
    "QED_RSI_S03_Scorpius": "",
    "SHLD_AEGS_S04_Reclaimer_SCItem": "Industrial",
    "SHLD_GODI_S04_Idris_Pirate_SCItem": "",
    "SHLD_GODI_S04_Idris_SCItem": "",
    "SHLD_RSI_S04_Polaris_SCItem": "Industrial",
    # Specific items where ref uses special Class values.
    "Paint_325a_microTech_Security": "@LOC_PLACEHOLDER",
    "RADR_S02_Fake": "@LOC_PLACEHOLDER",
    "RADR_Default": "@item_Desc_RADR_Default",
}

# ToolArm.UNDEFINED items that ref does expose Turret for (large salvage arms).
_TOOLARM_WITH_TURRET = frozenset({
    "MISC_Fortune_Salvage_Arm",
    "RSI_Salvation_Salvage_Arm_Left",
    "RSI_Salvation_Salvage_Arm_Right",
})

# Per-item Class omissions where ref has no Class field but our generic rules
# would otherwise add one (items that fall outside the type-level patterns).
_CLASS_OMIT_CLASSNAMES = frozenset({
    "ANVL_Terrapin_Nose_Turret_S3",
    "BEHR_LaserCannon_S2_CleanAir",
    "CNOU_Mustang_Nose_Turret_S3",
    "Flair_Dashboard_Bobblehead_01", "Flair_Dashboard_Bobblehead_02",
    "MISL_S09_CS_TALN_Argos_2",
    "Mining_Laser_SHIN_Hofstede_S0",
    "Mining_Laser_THCN_Helix_S0",
    "POWR_AEGS_S04_Idris_SCItem",
    "POWR_AEGS_S04_Reclaimer_SCItem",
    "POWR_RSI_S04_Bengal_SCItem",
    "RADR_GNRP_S03_Idris_TEMP",
    "RADR_RSI_S04_Polaris",
    "RADR_WLOP_S03_Lephari",
    "UMNT_ANVL_S5_Rotodome_Mk2",
})

# Turret.GunTurret items ref omits Class for (ship-integrated / fixed mounts).
_TURRETS_WITHOUT_CLASS = frozenset({
    "ANVL_Asgard_Nose_Turret_S4",
    "ANVL_Valkyrie_Nose_Turret_S3",
    "BEHR_PC2_Dual_S1",
    "DRAK_Dual_S1", "DRAK_Dual_S3",
    "Default_Fixed_Mount_S3", "Default_Fixed_Mount_S4",
    "MISC_Starlancer_TAC_Missile_Gimbal",
    "MISC_Starlancer_TAC_Missile_Gimbal_R",
    "ORIG_85X_Turret",
})

# Specific Paints items that ref omits Class for (ship-variant paints with opaque rule).
_PAINTS_WITHOUT_CLASS = frozenset({
    "Paint_Cutter_Black_Silver_Stripe",
    "Paint_Perseus_Beige_Beige_Beige",
    "Paint_Perseus_Beige_Blue_Brown",
    "Paint_Perseus_Beige_Green_Red",
    "Paint_Perseus_Black_Grey_Grey",
    "Paint_Perseus_Blue_Blue_Black",
    "Paint_Perseus_Green_Green_Black",
    "Paint_Perseus_Grey_Grey_Orange",
    "Paint_Perseus_Red_White_Black",
    "Paint_Starlifter_Pink_Pink_White",
})

# Specific MissileLauncher.MissileRack items ref omits Mass for
# (ship-integrated rackracks like Aurora Mk2, BEHR_S02).
_MISSILERACK_WITHOUT_MASS = frozenset({
    "MRCK_S01_RSI_Aurora_Mk2_Combat_Module_Rack",
    "GMRCK_S02_BEHR_Single_S02",
})

# Per-item Mass override: these items SHOULD have Mass despite matching
# generic skip rules (volume=1 Turret, Remote turret, TurretBase, etc.).
_MASS_FORCE_INCLUDE = frozenset({
    "Mount_Gimbal_S1", "Mount_Gimbal_S1_NoSafety", "Mount_Gimbal_S1_Tractor",
    "ANVL_Hornet_F7A_Mk1_Ball_Turret", "ANVL_Hornet_F7C_Ball_Turret",
    "CNOU_Mustang_Gamma_Scoop_Front",
    "DRAK_Cutlass_Steel_Rear_Remote_Dual_Turret_S4",
    "DRAK_Fixed_Mount_S4",
    "MISC_Hull_C_Nose_Turret_S5",
    "ANVL_Hornet_F7C_Mk2_Cargo_Mod",
})

# Ship-integrated MissileLauncher.MissileRack items that ref omits Class for.
# These are purpose-built for specific capital/large ships and aren't purchasable
# standalone, so ref treats them like ship-integrated hardware.
_MISSILERACK_WITHOUT_CLASS = frozenset({
    "MRCK_S01_TMBL_Storm_AA_Custom",
    "MRCK_S02_ORIG_100i_Dual_S02",
    "MRCK_S02_ORIG_125a_Quad_S02",
    "MRCK_S02_TMBL_Storm_AA_Custom",
    "MRCK_S03_VNCL_Quad_S01",
    "MRCK_S03_VNCL_Quad_S01_Blade",
    "MRCK_S04_RSI_Constellation",
    "MRCK_S04_RSI_Scorpius",
    "MRCK_S04_RSI_Scorpius_bottom_right",
    "MRCK_S04_RSI_Scorpius_top_left",
    "MRCK_S04_RSI_Scorpius_top_right",
    "MRCK_S04_VNCL_Quad_S02",
    "MRCK_S05_CRUS_Starfighter_Left",
    "MRCK_S05_CRUS_Starfighter_Right",
    "MRCK_S05_MISC_Freelancer_MIS_Left",
    "MRCK_S05_MISC_Freelancer_MIS_Right",
    "MRCK_S05_RSI_Constellation",
    "MRCK_S06_MISC_Gemini",
    "MRCK_S06_MISC_Gemini_Derelict",
    "MRCK_S09_AEGS_Eclipse",
    "MRCK_S09_AEGS_Retaliator_Fore",
    "MRCK_S09_AEGS_Retaliator_Rear",
    "MRCK_S12_AEGS_Javelin",
})

# Armor.Medium follows an opaque rule: only specific ship variants have Class.
# Empirically derived from entry_3.
_ARMOR_MEDIUM_WITH_CLASS = frozenset({
    "ARMR_AEGS_SabreRaven",
    "ARMR_AEGS_Sabre_Firebird", "ARMR_AEGS_Sabre_Peregrine",
    "ARMR_ANVL_C8_Pisces", "ARMR_ANVL_C8R_Pisces", "ARMR_ANVL_C8X_Pisces_Expedition",
    "ARMR_ANVL_Gladiator",
    "ARMR_ANVL_Hornet_F7A", "ARMR_ANVL_Hornet_F7C",
    "ARMR_ANVL_Hornet_F7CM", "ARMR_ANVL_Hornet_F7CM_Mk2",
    "ARMR_ANVL_Hornet_F7CR", "ARMR_ANVL_Hornet_F7CR_Mk2",
    "ARMR_ANVL_Hornet_F7CS", "ARMR_ANVL_Hornet_F7CS_Mk2",
    "ARMR_ORIG_100i", "ARMR_ORIG_125a", "ARMR_ORIG_135c",
})

# Types for which ref never includes Mass (empirically)
_TYPES_NO_MASS = frozenset({
    "FlightController.UNDEFINED",
    "Armor.Medium", "Armor.Light", "Armor.Heavy",
    "ShieldController.UNDEFINED",
    "WheeledController.UNDEFINED",
    "Turret.PDCTurret", "Turret.Utility",
    "SelfDestruct.UNDEFINED",
    "UtilityTurret.MannedTurret",
    "SalvageModifier.UNDEFINED",
    "TurretBase.MannedTurret",
    "Paints.Personal",
    "Door.UNDEFINED",
    "Flair_Cockpit.Flair_Static",
    "WeaponGun.UNDEFINED",
})
_BASE_TYPES_NO_MASS = frozenset({
    "Paints",
})

# Types where ref omits Mass only when volume == 1 (placeholder/ship-integrated items).
_BASE_TYPES_NO_MASS_IF_V1 = frozenset({
    "Turret",
})
_TYPES_NO_MASS_IF_V1 = frozenset({
    "Flair_Cockpit.Flair_Static",
    "ToolArm.UNDEFINED",
})

# Base types for which Class takes an actual manufacturer-class value (not "")
_COMPONENT_TYPES_CLASSED = frozenset({
    "Shield", "Cooler", "PowerPlant", "QuantumDrive", "Radar",
    "LifeSupportGenerator", "JumpDrive", "QuantumInterdictionGenerator",
})

# FPS weapon Class overrides by className. Empty string means "include as empty".
# Missing entries fall through to default FPS Class derivation (by classname pattern).
# Presence of className in _FPS_CLASS_OMIT means "omit Class field entirely".
_FPS_CLASS_OMIT = frozenset({
    "gmni_optics_tsco_x4_s2",
    "grin_cutter_01",
    "Multitool_Attachment",
})

# Specific FPS items where the default pattern-derived Class is wrong (ref uses empty).
_FPS_CLASS_EMPTY = frozenset({
    "none_pistol_ballistic_01",
    "none_special_ballistic_01",
    "volt_shotgun_energy_01",
    "volt_sniper_energy_01",
    "behr_binoculars_01",
    "behr_gren_frag_01",
    "crlf_medgun_01",
})

# Explicit FPS Class values by className — overrides all pattern-based rules.
_FPS_CLASS_BY_CLASSNAME = {
    # Multitool attachments
    "grin_multitool_01_cutter": "Cutter",
    "grin_multitool_01_healing": "Medical",
    "grin_multitool_01_mining": "Mining",
    "grin_multitool_01_salvage_repair": "Salvage and Repair",
    "grin_multitool_01_tractorbeam": "Tractor Beam",
    # Gadgets
    "grin_multitool_01": "Gadget",
    "grin_tractor_01": "Gadget",
    "kegr_fire_extinguisher_01": "Gadget",
    # Specific energy weapons (exceptions to manufacturer-based pattern)
    "klwe_smg_energy_01": "Laser",
    "ksar_smg_energy_01": "Energy\u00a0(Laser)",  # non-breaking space (matches ref)
    "ksar_rifle_energy_01": "Energy (Plasma)",
    "ksar_shotgun_energy_01": "Energy (Plasma)",
    "volt_pistol_energy_01": "Energy (Laser)",
    "none_smg_energy_01": "Energy (Laser)",
    "sasu_pistol_toy_01": "Foam Dart",
}

# className-prefix → FPS Class for *_energy_* weapons (fallback for non-specific items).
# Keyed on lowercase classname prefix since manufacturer GUIDs resolve differently
# for some FPS items (LBCO/VOLT have @LOC_PLACEHOLDER manufacturer).
_FPS_ENERGY_CLASS_BY_PREFIX = {
    "klwe": "Energy (Laser)",
    "ksar": "Energy (Plasma)",
    "lbco": "Electron",
    "volt": "Energy (Electron)",
    "none": "Energy (Laser)",
}


def _fps_class_value(class_name, full_type, mfr_code):
    """Return (has_class, class_value) for an FPS item.

    has_class=False: omit Class field entirely.
    has_class=True, value="": include Class = "".
    has_class=True, value=<str>: include Class = value.
    """
    # Light.Weapon and other opaque types → always omit
    if full_type == "Light.Weapon":
        return (False, None)
    if class_name in _FPS_CLASS_OMIT:
        return (False, None)
    # Explicit per-item overrides
    if class_name in _FPS_CLASS_BY_CLASSNAME:
        return (True, _FPS_CLASS_BY_CLASSNAME[class_name])
    # Items forced to empty Class
    if class_name in _FPS_CLASS_EMPTY:
        return (True, "")
    # All WeaponAttachment.* except Utility → empty Class
    if full_type in ("WeaponAttachment.Barrel", "WeaponAttachment.IronSight",
                      "WeaponAttachment.BottomAttachment", "WeaponAttachment.Missile"):
        return (True, "")
    # Melee weapons are structurally `WeaponPersonal.Knife` (verified against
    # the full corpus: every _melee_ ClassName has this full_type).
    if full_type == "WeaponPersonal.Knife":
        return (True, "Melee")
    # Energy vs Ballistic classification is editorial — CIG encodes it in
    # the FPS weapon's ClassName (*_energy_* / *_ballistic_* / *_multi_*)
    # rather than in a structural field. The weapon component's fireType
    # (rapid/sequence/charged/burst) cuts across both classes, and the ammo
    # record damage-type isn't populated for personal weapons. Keep as a
    # last-resort name check until CIG exposes a damage-class enum.
    cn_lower = class_name.lower()
    if "_energy_" in cn_lower:
        prefix = cn_lower.split("_", 1)[0]
        if prefix in _FPS_ENERGY_CLASS_BY_PREFIX:
            return (True, _FPS_ENERGY_CLASS_BY_PREFIX[prefix])
    if "_ballistic_" in cn_lower or "_multi_" in cn_lower:
        return (True, "Ballistic")
    return (True, "")


# Manufacturer code -> equipment class mapping
MANUFACTURER_CLASS = {
    "ACAS": "Competition", "ACOM": "Competition",
    "AEG": "Military", "AMRS": "Military",
    "ARCC": "Civilian", "ASAS": "Stealth",
    "BANU": "Military", "BASL": "Industrial",
    "BEH": "Civilian", "BLTR": "Stealth",
    "CHCO": "Industrial", "GODI": "Military",
    "GRNP": "Military", "JSPN": "Civilian",
    "JUST": "Industrial", "LPLT": "Civilian",
    "NAVE": "Competition", "ORIG": "Industrial",
    "RACO": "Stealth", "RSI": "Civilian",
    "SASU": "Civilian", "SECO": "Civilian",
    "TARS": "Civilian", "TYDT": "Stealth",
    "WCPR": "Civilian", "WETK": "Military",
    "WLOP": "Civilian", "YORM": "Competition",
}


def build_std_item(record, ctx, external_loadout=None, nested=False):
    """Build a full stdItem dict from a parsed entity record."""
    attach_def = record.get("attachDef", {})
    components = record.get("components", {})

    item_type = attach_def.get("type", "")
    sub_type = attach_def.get("subType", "")
    # Keep .UNDEFINED for types like Shield.UNDEFINED to match reference
    full_type = f"{item_type}.{sub_type}" if sub_type else item_type

    # Detect FPS items (used by several downstream blocks)
    is_fps = _is_fps_item(item_type, full_type, attach_def)

    description = _clean_description(
        ctx.resolve_name(attach_def.get("description", "")), is_fps=is_fps
    )

    si = {
        "ClassName": record.get("className", ""),
        "Size": attach_def.get("size", 0),
        "Grade": attach_def.get("grade", 0),
        "Type": full_type,
        "Name": _resolve_item_name(attach_def.get("name", ""), record.get("className", ""), ctx),
    }

    # Description: include only if resolved text, or if it's literally @LOC_PLACEHOLDER.
    # Exclude @LOC_EMPTY and any other unresolved @ keys.
    if description and not description.startswith("@") and description != "<= PLACEHOLDER =>":
        si["Description"] = description
    elif description == "@LOC_PLACEHOLDER":
        si["Description"] = description
    elif record.get("className") == "RADR_Default" and description:
        # RADR_Default is the one item where ref includes the raw @-key Description.
        si["Description"] = description
    tags = [t for t in attach_def.get("tags", "").split() if t]
    if tags:
        si["Tags"] = tags

    # RequiredTags from attachDef
    req_tags_str = attach_def.get("requiredTags", "")
    if req_tags_str:
        si["RequiredTags"] = req_tags_str.split()

    # Classification (excluded for nested/InstalledItem)
    if not nested:
        classification = _build_classification(full_type, attach_def)
        if classification:
            si["Classification"] = classification

    # Mass from physics (ref omits Mass for certain types, and for specific types when volume=1 is a placeholder)
    raw_volume = attach_def.get("volume", 0)
    try:
        volume_is_one = int(raw_volume) == 1
    except (TypeError, ValueError):
        volume_is_one = False
    base = full_type.split(".")[0] if full_type else ""
    cn = record.get("className", "")
    skip_mass = (
        full_type in _TYPES_NO_MASS
        or base in _BASE_TYPES_NO_MASS
        or (volume_is_one and (base in _BASE_TYPES_NO_MASS_IF_V1 or full_type in _TYPES_NO_MASS_IF_V1))
    )
    # Container.Cargo: three classes of ship-integrated items whose mass
    # isn't meaningful in the standalone record. Matched structurally:
    # - Mining pods carry a `ResourceContainer` component (dynamic cargo).
    # - Cyclone swap modules are tagged `TMBL_Cyclone_Module` by CIG.
    # - Ship-integrated CargoGrid_Main placeholders have a @LOC_PLACEHOLDER
    #   name + inventory container + volume=1 stub geometry.
    if full_type == "Container.Cargo":
        raw_name = attach_def.get("name", "")
        if "ResourceContainer" in components:
            skip_mass = True
        elif attach_def.get("tags") == "TMBL_Cyclone_Module":
            skip_mass = True
        elif (raw_name == "@LOC_PLACEHOLDER"
              and "SCItemInventoryContainerComponentParams" in components
              and volume_is_one):
            skip_mass = True
    # GroundVehicleMissileLauncher: vehicle-integrated rack variants (Nova,
    # Ballista, Cyclone_MT/AA) point at an existing standard rack by name
    # (`SCItemPurchasableParams.displayName` references e.g.
    # `@item_NameMRCK_S03_BEHR_Dual_S02`). Only genuinely standalone racks
    # (Storm) carry a placeholder displayName. Skip mass on the aliases so
    # the catalogue doesn't double-count.
    if full_type == "GroundVehicleMissileLauncher.GroundVehicleMissileRack":
        purch = components.get("SCItemPurchasableParams", {})
        display = purch.get("displayName", "") if isinstance(purch, dict) else ""
        if display and display != "@LOC_PLACEHOLDER":
            skip_mass = True
    # Turret.TopTurret/BottomTurret: remote-turret variants have no Mass. The
    # item's `attachDef.name` is a localization key that identifies the
    # turret class (`@item_Name_Turret_Manned` vs `@item_Name_Turret_Remote`
    # vs ship-specific like `@item_NameDRAK_Cutlass_Steel_RemoteTurret`).
    # Match "Remote" in the name key rather than the ClassName.
    if full_type in ("Turret.TopTurret", "Turret.BottomTurret"):
        if "Remote" in attach_def.get("name", ""):
            skip_mass = True
    # Module.UNDEFINED: ship-integrated modules (placeholder volume) have no Mass.
    if full_type == "Module.UNDEFINED" and (volume_is_one or raw_volume in (0, None, "")):
        skip_mass = True
    # Ship-integrated MissileRack exceptions where ref omits Mass
    if full_type == "MissileLauncher.MissileRack" and cn in _MISSILERACK_WITHOUT_MASS:
        skip_mass = True
    # SalvageHead.UNDEFINED covers both salvage heads and tractor beams.
    # Tractor beams carry SDistortionParams (the beam rendering); salvage
    # heads never do. Skip mass on salvage heads only.
    if full_type == "SalvageHead.UNDEFINED" and "SDistortionParams" not in components:
        skip_mass = True
    # Per-item allowlist: items that should have Mass despite generic skip rules.
    if cn in _MASS_FORCE_INCLUDE:
        skip_mass = False
    if not skip_mass:
        physics = components.get("physics", {})
        if physics.get("mass"):
            si["Mass"] = physics["mass"]

    # Volume from attachDef
    if attach_def.get("volume"):
        si["Volume"] = float(attach_def["volume"])

    # Manufacturer
    mfr_guid = attach_def.get("manufacturerGuid", "")
    mfr = ctx.get_manufacturer(mfr_guid)
    if mfr:
        si["Manufacturer"] = mfr

    # Class presence is determined by whether the item has a real (non-placeholder) description.
    # For most types, ref sets Class iff description is a real localization key.
    # WeaponDefensive.CountermeasureLauncher has the INVERTED rule.
    raw_desc = attach_def.get("description", "")
    desc_is_empty = raw_desc in ("", "@LOC_EMPTY", "@LOC_PLACEHOLDER")
    base_type = full_type.split(".")[0] if full_type else ""

    class_name = record.get("className", "")
    # Items with name=@LOC_PLACEHOLDER always carry Class (set to @LOC_PLACEHOLDER below),
    # but only for types that normally have Class (components, weapons, radar, scanner).
    name_is_placeholder = attach_def.get("name", "") == "@LOC_PLACEHOLDER"
    placeholder_class_types = full_type in _TYPES_PLACEHOLDER_FORCE_CLASS

    if is_fps and not nested:
        mfr_code = (mfr or {}).get("Code", "") if mfr else ""
        has_cls, cls_val = _fps_class_value(class_name, full_type, mfr_code)
        if has_cls:
            si["Class"] = cls_val
        should_have_class = False  # FPS path already set (or omitted) Class.
    elif class_name in _CLASS_OMIT_CLASSNAMES:
        should_have_class = False
    elif class_name in _CLASS_VALUE_OVERRIDES:
        should_have_class = True
    elif name_is_placeholder and placeholder_class_types:
        should_have_class = True
    elif full_type == "Armor.Medium":
        should_have_class = class_name in _ARMOR_MEDIUM_WITH_CLASS
    elif full_type == "MissileLauncher.MissileRack" and class_name in _MISSILERACK_WITHOUT_CLASS:
        should_have_class = False
    elif full_type == "Paints.UNDEFINED" and class_name in _PAINTS_WITHOUT_CLASS:
        should_have_class = False
    elif full_type == "Turret.GunTurret" and class_name in _TURRETS_WITHOUT_CLASS:
        should_have_class = False
    elif full_type in _TYPES_NEVER_CLASS or base_type in _BASE_TYPES_NEVER_CLASS:
        should_have_class = False
    elif full_type in _TYPES_INVERTED_CLASS:
        # WeaponDefensive: inverted rule (empty desc → has Class), plus specific
        # manufacturer allowlist that always gets Class regardless of description.
        # Specific item exceptions (Reliant, MRAI_Guardian) override the allowlist.
        mfr_code = (mfr or {}).get("Code", "") if mfr else ""
        if class_name in _WEAPONDEFENSIVE_CN_WITHOUT_CLASS:
            should_have_class = False
        elif mfr_code in _WEAPONDEFENSIVE_MFR_WITH_CLASS:
            should_have_class = True
        else:
            should_have_class = desc_is_empty
    else:
        should_have_class = not desc_is_empty

    if should_have_class:
        raw_name = attach_def.get("name", "")
        if raw_name == "@LOC_PLACEHOLDER":
            si["Class"] = "@LOC_PLACEHOLDER"
        elif class_name in _CLASS_VALUE_OVERRIDES:
            si["Class"] = _CLASS_VALUE_OVERRIDES[class_name]
        elif base_type in _COMPONENT_TYPES_CLASSED and mfr:
            # LifeSupport: capital-class (size 4) units are ship-integrated
            # for Idris/Polaris/890 and carry empty Class; smaller sizes
            # (S00–S03) are player-purchasable civilian grade.
            if full_type == "LifeSupportGenerator.UNDEFINED":
                if attach_def.get("size") == 4:
                    si["Class"] = ""
                else:
                    si["Class"] = "Civilian"
            else:
                si["Class"] = MANUFACTURER_CLASS.get(mfr["Code"], "")
        else:
            si["Class"] = ""

    # Durability (from SHealthComponentParams + SDistortionParams + misfire + ItemResourceComponentParams.selfRepair)
    health = components.get("health", {})
    irp = components.get("ItemResourceComponentParams", {})
    distortion = components.get("SDistortionParams", {})
    # Misfire data from EntityComponentMisfireParams (generically captured)
    misfire_comp = components.get("EntityComponentMisfireParams", {})
    misfire_effect = {}
    if isinstance(misfire_comp, dict):
        misfires = misfire_comp.get("misfires", {})
        if isinstance(misfires, dict):
            she = misfires.get("SHostExplosionEffect", {})
            if isinstance(she, dict) and she.get("explosionChance"):
                misfire_effect = {
                    "chance": safe_float(she.get("explosionChance")),
                    "countdown": safe_float(she.get("explosionCountdown")),
                    "healthCancelRatio": safe_float(she.get("healthCancelRatio")),
                }
    # Lifetime from SDegradationParams
    deg = components.get("SDegradationParams", {})
    has_degradation = False
    lifetime = 0.0
    if isinstance(deg, dict):
        accum = deg.get("accumulators", {})
        wear = accum.get("SWearAccumulatorParams", {})
        if isinstance(wear, dict) and wear:
            has_degradation = True
            lifetime = safe_float(wear.get("MaxLifetimeHours", "0"))

    if health:
        si["Durability"] = _build_durability(health, irp, distortion, misfire_effect,
                                              lifetime, has_degradation)
    elif has_degradation:
        # Item has degradation but no health component — still include Durability with Lifetime
        si["Durability"] = {"Lifetime": lifetime}

    # ResourceNetwork (from ItemResourceComponentParams)
    if irp:
        resource_net = _build_resource_network_from_irp(irp)
        # Include even if empty list (ref includes [] for items with IRP but no states)
        if resource_net is not None:
            si["ResourceNetwork"] = resource_net

    # HeatController (from physics temperature element or EntityComponentHeatConnection)
    hc = components.get("heatController", {})
    heat = components.get("heat", {})
    if hc:
        si["HeatController"] = _build_heat_controller_from_hc(hc)
    elif heat:
        si["HeatController"] = _build_heat_controller_from_heat(heat)

    # Magazine block for WeaponAttachment.Magazine items (ammo capacity + repool flag)
    if full_type == "WeaponAttachment.Magazine":
        ammo_comp = components.get("ammo", {})
        if ammo_comp:
            si["Magazine"] = {
                "Capacity": float(ammo_comp.get("maxAmmoCount", 0)),
                "AllowRepool": bool(ammo_comp.get("allowAmmoRepool", False)),
            }

    # Type-specific data
    if "weapon" in components:
        weapon_data = _build_weapon_data(components, ctx, item_type, is_fps=is_fps) or {}
        # For FPS weapons, ammo lives in the magazine — resolve it even when the
        # weapon has no firing modes (crlf_medgun, none_pistol_ballistic).
        if (is_fps and "defaultLoadout" in components
                and not weapon_data.get("Ammunition")):
            _resolve_fps_ammo(weapon_data, components["defaultLoadout"], ctx)
        if weapon_data:
            # Repool block (FPS weapons only — SWeaponAmmoRepoolParams)
            if is_fps:
                weapon_comp = components.get("weapon", {})
                repool = weapon_comp.get("ammoRepool")
                if repool:
                    weapon_data["Repool"] = {
                        "AmmoPerSecond": float(repool.get("bulletsPerSecond", 0)),
                        "UnstowMagDuration": float(repool.get("unstowMagDuration", 0)),
                        "MagMergeDuration": float(repool.get("fullMagMergeDuration", 0)),
                    }
            # Reorder keys to match reference format
            ordered = {}
            if "Modifiers" in weapon_data:
                ordered["Modifiers"] = weapon_data["Modifiers"]
            if "Ammunition" in weapon_data:
                ordered["Ammunition"] = weapon_data["Ammunition"]
            # Emit Firing (empty list is valid: ref-convention for medgun, etc.)
            if is_fps and "Ammunition" in weapon_data and "Firing" not in weapon_data:
                ordered["Firing"] = []
            elif "Firing" in weapon_data:
                ordered["Firing"] = weapon_data["Firing"]
            if "Repool" in weapon_data:
                ordered["Repool"] = weapon_data["Repool"]
            if "Consumption" in weapon_data:
                ordered["Consumption"] = weapon_data["Consumption"]
            if "HeatParameters" in weapon_data:
                ordered["HeatParameters"] = weapon_data["HeatParameters"]
            si["Weapon"] = ordered

    if "shield" in components:
        si["Shield"] = _build_shield_data(components["shield"])

    if "cooler" in components:
        si["Cooler"] = components["cooler"]

    if "powerPlant" in components:
        si["PowerPlant"] = components["powerPlant"]

    if "quantumDrive" in components:
        si["QuantumDrive"] = _build_quantum_drive(components["quantumDrive"])

    if "missile" in components:
        missile = _build_missile(components["missile"])
        if missile:
            si["Missile"] = missile

    if "armor" in components:
        si["Armour"] = _build_armour(components["armor"])

    # MissileRack — count and size from missile ports
    ports = components.get("ports", [])
    missile_rack = _build_missile_rack(ports, item_type)
    if missile_rack:
        si["MissileRack"] = missile_rack

    # Turret — yaw/pitch axis data.
    # ToolArm items (salvage arms) use SCItemTurretParams internally but ref
    # omits Turret for most — only a few large salvage arms expose it.
    turret_params = components.get("SCItemTurretParams")
    skip_turret = (full_type == "ToolArm.UNDEFINED"
                   and record.get("className") not in _TOOLARM_WITH_TURRET)
    if turret_params and not skip_turret:
        turret = _build_turret(turret_params)
        if turret:
            si["Turret"] = turret

    # ShieldEmitter
    shield_emitter = components.get("SCItemShieldEmitterParams")
    if shield_emitter:
        si["ShieldEmitter"] = _build_shield_emitter(shield_emitter)

    # CounterMeasure from ammo's counterMeasure params
    if "WeaponDefensive" in item_type:
        ammo_comp = components.get("ammo", {})
        ammo_guid = ammo_comp.get("ammoParamsRecord", "")
        ammo_data = ctx.get_ammo(ammo_guid)
        if ammo_data and ammo_data.get("counterMeasure"):
            cm = ammo_data["counterMeasure"]
            cm_type = ammo_data.get("counterMeasureType", "Chaff")
            si["CounterMeasure"] = {cm_type: cm}

    # Ifcs from IFCSParams
    ifcs_params = components.get("IFCSParams")
    if ifcs_params:
        ifcs = _build_ifcs(ifcs_params, components)
        if ifcs:
            _apply_blade_modifier(ifcs, record.get("className", ""))
        si["Ifcs"] = ifcs

    # Radar from SCItemRadarComponentParams
    radar_params = components.get("SCItemRadarComponentParams")
    if radar_params:
        si["Radar"] = _build_radar(radar_params)

    # JumpDrive from SCItemJumpDriveParams
    jd_params = components.get("SCItemJumpDriveParams")
    if jd_params:
        si["JumpDrive"] = _build_jump_drive(jd_params)

    # EMP from SCItemEMPParams
    emp_params = components.get("SCItemEMPParams")
    if emp_params:
        si["Emp"] = _build_emp(emp_params)

    # SelfDestruct from SSCItemSelfDestructComponentParams
    sd_params = components.get("SSCItemSelfDestructComponentParams")
    if sd_params:
        si["SelfDestruct"] = _build_self_destruct(sd_params)

    # QuantumInterdiction from SCItemQuantumInterdictionGeneratorParams
    qi_params = components.get("SCItemQuantumInterdictionGeneratorParams")
    if qi_params:
        si["QuantumInterdiction"] = _build_quantum_interdiction(qi_params)

    # MiningLaser from SEntityComponentMiningLaserParams
    mining_params = components.get("SEntityComponentMiningLaserParams")
    if mining_params:
        si["MiningLaser"] = _build_mining_laser(mining_params, components)

    # Module/SalvageModifier from EntityComponentAttachableModifierParams
    modifier_params = components.get("EntityComponentAttachableModifierParams")
    if modifier_params:
        _build_modifier(si, modifier_params, full_type)

    # TractorBeam - from weapon firing modes for tractor/salvage items
    if "TractorBeam" in item_type or "TowingBeam" in item_type or "SalvageHead" in item_type:
        tractor = _build_tractor_beam(components)
        if tractor:
            si["TractorBeam"] = tractor

    # FPS weapon-shape items with empty firingModes get an empty TractorBeam placeholder
    # (ref convention for medgun, fire extinguisher, rocketless pistol).
    weapon_comp_for_tb = components.get("weapon") or {}
    if (is_fps and weapon_comp_for_tb and not weapon_comp_for_tb.get("firingModes")
            and full_type.startswith("WeaponPersonal.")):
        si["TractorBeam"] = {"Tractor": [], "Towing": []}

    # Bomb from SCItemBombParams
    bomb_params = components.get("SCItemBombParams")
    if bomb_params:
        si["Bomb"] = _build_bomb(bomb_params)

    # Explosive for FPS grenades — from EntityComponentTriggerableDevicesParams
    td = components.get("EntityComponentTriggerableDevicesParams")
    if td and isinstance(td, dict):
        triggers = td.get("triggers", {})
        timer = triggers.get("STriggerableDevicesTriggerTimerParams") if isinstance(triggers, dict) else None
        if isinstance(timer, dict):
            behavior = timer.get("behavior", {})
            explosion = behavior.get("STriggerableDevicesBehaviorExplosionParams") if isinstance(behavior, dict) else None
            exp_params = explosion.get("ExplosionParams") if isinstance(explosion, dict) else None
            if isinstance(exp_params, dict):
                dmg_info = ((exp_params.get("damage") or {}).get("DamageInfo") or {})
                damage = {}
                for key in ["Physical", "Energy", "Distortion", "Thermal", "Biochemical", "Stun"]:
                    v = safe_float(dmg_info.get(f"Damage{key}", 0))
                    if v:
                        damage[key] = v
                si["Explosive"] = {
                    "DetonationDelay": safe_float(timer.get("duration", 0)),
                    "RadiusMin": safe_float(exp_params.get("minRadius", 0)),
                    "RadiusMax": safe_float(exp_params.get("maxRadius", 0)),
                    "Pressure": safe_float(exp_params.get("pressure", 0)),
                    "Damage": damage,
                }

    # MissilesController from SCItemMissileControllerParams
    mc_params = components.get("SCItemMissileControllerParams")
    if mc_params:
        si["MissilesController"] = _build_missiles_controller(mc_params)

    # CargoGrid/CargoContainers
    rc = components.get("ResourceContainer")
    inv_comp = components.get("SCItemInventoryContainerComponentParams")
    if ("Container" in item_type or "Cargo" in item_type):
        _build_cargo_fields(si, rc, inv_comp, record.get("className", ""), full_type, ctx)

    # Ports
    if ports:
        default_loadout = components.get("defaultLoadout", []) or external_loadout or []
        si["Ports"] = _build_ports(ports, si.get("Tags", []), ctx, default_loadout,
                                    parent_type=full_type)

    # Weapon modifier (FPS attachments only — recoil, spread, zoom modifiers).
    # Ship weapon attachments have SWeaponModifierComponentParams too but ref
    # omits the block for those.
    if is_fps:
        weapon_mod = components.get("SWeaponModifierComponentParams", {})
        if weapon_mod:
            wm = _build_weapon_modifier(weapon_mod)
            if wm:
                si["WeaponModifier"] = wm

    return si


def _build_weapon_modifier(weapon_mod):
    """Build the WeaponModifier block for FPS attachments from SWeaponModifierComponentParams.

    Maps XML `modifier.weaponStats` tree to the SPViewer-format output:
    - RecoilModifier (AimRecoilModifier.CurveRecoil, RecoilMultiplier, DecayMultiplier)
    - SpreadModifier (Min/Max/FirstAttack/PerAttack/Decay)
    - AimModifier (ZoomScale/SecondZoomScale/ZoomTimeScale)
    - Top-level multipliers for damage/fire rate/projectile speed/etc.
    """
    modifier = weapon_mod.get("modifier", {}) or {}
    ws = modifier.get("weaponStats", {}) or {}
    if not ws:
        return None

    recoil = ws.get("recoilModifier", {}) or {}
    aim_recoil = recoil.get("aimRecoilModifier", {}) or {}
    curve = aim_recoil.get("curveRecoil", {}) or {}
    spread = ws.get("spreadModifier", {}) or {}
    aim = ws.get("aimModifier", {}) or {}

    return {
        "RecoilModifier": {
            "AimRecoilModifier": {
                "CurveRecoil": {
                    "YawMaxDegrees": safe_float(curve.get("yawMaxDegreesModifier", 1)),
                    "PitchMaxDegrees": safe_float(curve.get("pitchMaxDegreesModifier", 1)),
                    "RollMaxDegrees": safe_float(curve.get("rollMaxDegreesModifier", 1)),
                },
                "RandomPitchMultiplier": safe_float(aim_recoil.get("randomPitchMultiplier", 1)),
                "RandomYawMultiplier": safe_float(aim_recoil.get("randomYawMultiplier", 1)),
                "DecayMultiplier": safe_float(aim_recoil.get("decayMultiplier", 1)),
            },
            "RecoilMultiplier": safe_float(recoil.get("animatedRecoilMultiplier", 1)),
            "DecayMultiplier": safe_float(recoil.get("decayMultiplier", 1)),
        },
        "SpreadModifier": {
            "Min": safe_float(spread.get("minMultiplier", 1)),
            "Max": safe_float(spread.get("maxMultiplier", 1)),
            "FirstAttack": safe_float(spread.get("firstAttackMultiplier", 1)),
            "PerAttack": safe_float(spread.get("attackMultiplier", 1)),
            "Decay": safe_float(spread.get("decayMultiplier", 1)),
        },
        "AimModifier": {
            "ZoomScale": safe_float(aim.get("zoomScale", 1)),
            "SecondZoomScale": safe_float(aim.get("secondZoomScale", 1)),
            "ZoomTimeScale": safe_float(aim.get("zoomTimeScale", 1)),
        },
        "DamageMultiplier": safe_float(ws.get("damageMultiplier", 1)),
        "DamageOverTimeMultiplier": safe_float(ws.get("damageOverTimeMultiplier", 1)),
        "FireRateMultiplier": safe_float(ws.get("fireRateMultiplier", 1)),
        "ProjectileSpeedMultiplier": safe_float(ws.get("projectileSpeedMultiplier", 1)),
        "AmmoCostMultiplier": safe_float(ws.get("ammoCostMultiplier", 1)),
        "ChargeTimeMultiplier": safe_float(ws.get("chargeTimeMultiplier", 1)),
        "HeatGenerationMultiplier": safe_float(ws.get("heatGenerationMultiplier", 1)),
        "BarrelEffectsStrength": safe_float(weapon_mod.get("barrelEffectsStrength", 1)),
        "SoundRadiusMultiplier": safe_float(ws.get("soundRadiusMultiplier", 1)),
    }


def _resolve_item_name(raw_name, class_name, ctx):
    """Resolve item name, falling back to className for placeholders/unresolved."""
    resolved = ctx.resolve_name(raw_name)
    if not resolved or resolved == "<= PLACEHOLDER =>" or resolved == "@LOC_PLACEHOLDER":
        return class_name or raw_name
    # If still unresolved (@key), fall back to className
    if resolved.startswith("@"):
        return class_name or raw_name
    return resolved


def _clean_description(desc, is_fps=False):
    """Strip metadata prefix from descriptions (Manufacturer:, Item Type:, etc.)."""
    if not desc:
        return desc
    # Keep unresolved localization keys as-is
    if desc.startswith("@"):
        return desc
    # Restore placeholder markers
    if desc == "<= PLACEHOLDER =>":
        return "@LOC_PLACEHOLDER"
    # Localization files use literal \n — convert to real newlines
    if "\\n" in desc:
        desc = desc.replace("\\n", "\n")
    # Strip the first \n\n-separated section (whether it's a "warning" line
    # like "ATTACHMENTS SOLD SEPARATELY!" or a metadata block of Key:Value lines).
    # Ship items: only strip metadata blocks (colons everywhere).
    # FPS items: always strip the first section (warning OR metadata).
    if "\n\n" in desc:
        parts = desc.split("\n\n", 1)
        prefix = parts[0]
        lines = [l for l in prefix.split("\n") if l.strip()]
        is_metadata = lines and all(":" in l for l in lines)
        is_warning = lines and not any(":" in l for l in lines)
        if is_metadata or (is_fps and is_warning):
            desc = parts[1] if len(parts) > 1 else desc
    # Reference removes newlines from descriptions (but preserves trailing whitespace)
    return desc.replace("\n", "")


_CLASSIFICATION_TYPE_MAP = {
    "TurretBase": "Turret",
    "WeaponGun": "Weapon",
    "WeaponMining": "Mining",
    "ToolArm": "Turret",
    "UtilityTurret": "Turret",
    "WeaponPersonal": "Weapon",
}

# FPS-specific sub-type transformations (applied only when prefix == "FPS").
_FPS_SUBTYPE_MAP = {
    ("WeaponAttachment", "Barrel"): ("WeaponAttachment", "BarrelAttachment"),
    ("Light", "Weapon"): ("WeaponAttachment", "Light"),
}

def _build_classification(full_type, attach_def):
    """Build classification string like 'Ship.WeaponDefensive.CountermeasureLauncher'."""
    if not full_type:
        return ""
    # FPS prefix set via structural FPS-type check. `attach_def` is used for
    # the Barrel tag disambiguation path inside `_is_fps_item`.
    prefix = "FPS" if _is_fps_item(
        full_type.split(".")[0], full_type, attach_def or {}
    ) else "Ship"

    # Split type parts and clean up
    parts = full_type.split(".")
    # Apply FPS sub-type remap first (Barrel→BarrelAttachment, Light.Weapon→WeaponAttachment.Light)
    if prefix == "FPS" and len(parts) == 2:
        key = (parts[0], parts[1])
        if key in _FPS_SUBTYPE_MAP:
            parts = list(_FPS_SUBTYPE_MAP[key])
    # Map base type (e.g. TurretBase -> Turret, WeaponPersonal -> Weapon)
    if parts[0] in _CLASSIFICATION_TYPE_MAP:
        parts[0] = _CLASSIFICATION_TYPE_MAP[parts[0]]
    # Remove UNDEFINED suffix
    parts = [p for p in parts if p != "UNDEFINED"]

    return f"{prefix}.{'.'.join(parts)}"


def _build_durability(health_data, irp=None, distortion_data=None, misfire_data=None,
                      lifetime=0.0, has_degradation=False):
    """Build Durability object from health component, distortion, misfire, and ItemResourceComponentParams."""
    result = {"Health": health_data.get("health", 0)}
    if has_degradation:
        result["Lifetime"] = lifetime

    # Distortion from SDistortionParams
    if distortion_data:
        max_dmg = safe_float(distortion_data.get("Maximum", "0"))
        decay_delay = safe_float(distortion_data.get("DecayDelay", "0"))
        decay_rate = safe_float(distortion_data.get("DecayRate", "0"))
        # RecoveryTime = DecayDelay + Maximum * (1 - RecoveryRatio) / DecayRate
        recovery_ratio = safe_float(distortion_data.get("RecoveryRatio", "0"))
        effective_dmg = max_dmg * (1 - recovery_ratio) if recovery_ratio else max_dmg
        recovery = round(decay_delay + effective_dmg / decay_rate, 2) if decay_rate else 0.0
        result["Distortion"] = {
            "MaximumDamage": max_dmg,
            "DecayDelay": decay_delay,
            "DecayRate": round(decay_rate, 7),
            "RecoveryTime": recovery,
        }

    dm = health_data.get("damageMultipliers", {})
    if dm:
        mults = {}
        for key, field in [("physical", "Physical"), ("energy", "Energy"),
                           ("distortion", "Distortion"), ("thermal", "Thermal"),
                           ("biochemical", "Biochemical"), ("stun", "Stun")]:
            val = dm.get(key)
            if val is not None and val != 0.0:
                mults[field] = val
        result["DamageMultipliers"] = mults

    # Misfire (power plants — from SHostExplosionEffect)
    if misfire_data and misfire_data.get("chance"):
        result["Misfire"] = {
            "Explosion": {
                "Chance": misfire_data.get("chance", 0),
                "Countdown": misfire_data.get("countdown", 0),
                "HealthCancelRatio": misfire_data.get("healthCancelRatio", 0),
            }
        }

    # SelfRepair from ItemResourceComponentParams
    if irp:
        self_repair = irp.get("selfRepair", {})
        if self_repair:
            result["SelfRepair"] = {
                "MaxRepair": safe_float(self_repair.get("maxRepairCount")),
                "TimeToRepair": safe_float(self_repair.get("timeToRepair")),
                "HealthRatio": safe_float(self_repair.get("healthRatio")),
            }

    return result


def _build_resource_network_from_irp(irp):
    """Build ResourceNetwork array from ItemResourceComponentParams."""
    states_data = irp.get("states", {})
    if not states_data:
        return []

    # states can be a single dict or a list of dicts
    state_list = states_data
    if isinstance(states_data, dict):
        # Check if it has a single state or multiple
        if "ItemResourceState" in states_data:
            state_obj = states_data["ItemResourceState"]
            if isinstance(state_obj, list):
                state_list = state_obj
            else:
                state_list = [state_obj]
        else:
            state_list = [states_data]

    result = []
    for state in state_list:
        if not isinstance(state, dict):
            continue

        entry = {}
        state_name = state.get("name", "Online")

        # Consumption
        deltas = state.get("deltas", {})
        consumption_list = []
        generation_list = []

        # Handle deltas that can be dict or list
        if isinstance(deltas, dict):
            for dk, dv in deltas.items():
                # dv can be a single dict or a list of dicts
                items_list = dv if isinstance(dv, list) else [dv]
                for delta_item in items_list:
                    if not isinstance(delta_item, dict):
                        continue
                    if "Consumption" in dk:
                        c = _extract_consumption(delta_item)
                        if c:
                            consumption_list.append(c)
                    elif "Generation" in dk:
                        g = _extract_generation(delta_item)
                        if g:
                            generation_list.append(g)
                    elif "Conversion" in dk:
                        conv = _extract_conversion(delta_item)
                        if conv:
                            entry["Conversion"] = [conv]

        if consumption_list:
            entry["Consumption"] = consumption_list
        if generation_list:
            entry["Generation"] = generation_list

        # Signatures
        sig_params = state.get("signatureParams", {})
        signatures = {}
        for sig_key, sig_name in [("EMSignature", "Electromagnetic"), ("IRSignature", "Infrared")]:
            sig = sig_params.get(sig_key, {})
            if sig:
                nominal = safe_float(sig.get("nominalSignature"))
                decay = safe_float(sig.get("decayRate", "0.15"))
                signatures[sig_name] = {"Nominal": nominal, "DecayRate": decay}
        if signatures:
            entry["Signatures"] = signatures

        # Power ranges
        power_ranges = state.get("powerRanges", {})
        if power_ranges:
            pr = {}
            for level in ["low", "medium", "high"]:
                pr_data = power_ranges.get(level, {})
                if pr_data:
                    pr[level.capitalize()] = {
                        "Start": safe_float(pr_data.get("start")),
                        "Modifier": safe_float(pr_data.get("modifier")),
                        "RegisterRange": pr_data.get("registerRange") in ("1", "true", True),
                    }
            if pr:
                entry["PowerRanges"] = pr

        # State goes last (after Consumption, Signatures, PowerRanges)
        entry["State"] = state_name

        if entry:
            result.append(entry)

    return result if result else None


def _extract_resource_amount(amount_data):
    """Extract resource amount and field name from resourceAmountPerSecond dict.

    Returns (field_name, value) where field_name is UnitPerSec, Segment, or MicroUnitPerSec.
    """
    if not amount_data:
        return "UnitPerSec", 0
    for k, v in amount_data.items():
        if isinstance(v, dict):
            if "standardResourceUnits" in v:
                return "UnitPerSec", safe_float(v["standardResourceUnits"])
            elif "units" in v and "Segment" in k:
                return "Segment", safe_float(v["units"])
            elif "microResourceUnits" in v:
                return "MicroUnitPerSec", safe_float(v["microResourceUnits"])
            # Fallback: try first numeric value
            for vk, vv in v.items():
                val = safe_float(vv)
                if val:
                    return "UnitPerSec", val
        else:
            return "UnitPerSec", safe_float(v)
    return "UnitPerSec", 0


def _extract_consumption(delta):
    """Extract consumption data from a delta entry."""
    consumption = delta.get("consumption", {})
    if not consumption:
        return None
    resource = consumption.get("resource", "")
    amount_data = consumption.get("resourceAmountPerSecond", {})
    field_name, value = _extract_resource_amount(amount_data)
    min_frac = safe_float(delta.get("minimumConsumptionFraction"))
    result = {
        "Resource": resource,
        "MinConsumptionFraction": min_frac,
        field_name: value,
    }
    return result


def _extract_generation(delta):
    """Extract generation data from a delta entry."""
    generation = delta.get("generation", {})
    if not generation:
        return None
    resource = generation.get("resource", "")
    amount_data = generation.get("resourceAmountPerSecond", {})
    field_name, value = _extract_resource_amount(amount_data)
    min_frac = safe_float(delta.get("minimumConsumptionFraction", "0"))
    result = {
        "Resource": resource,
        "MinConsumptionFraction": min_frac,
        field_name: value,
    }
    return result


def _extract_conversion(delta):
    """Extract conversion data from a delta entry."""
    gen = delta.get("generation", {})
    cons = delta.get("consumption", {})
    result = {}
    if gen:
        gen_res = gen.get("resource", "")
        gen_amount = gen.get("resourceAmountPerSecond", {})
        field_name, value = _extract_resource_amount(gen_amount)
        result["Generation"] = {"Resource": gen_res, field_name: value}
    if cons:
        cons_res = cons.get("resource", "")
        cons_amount = cons.get("resourceAmountPerSecond", {})
        cons_entry = {"Resource": cons_res}
        if cons_amount:
            field_name, value = _extract_resource_amount(cons_amount)
            cons_entry[field_name] = value
        result["Consumption"] = cons_entry
    min_frac = safe_float(delta.get("minimumConsumptionFraction"))
    result["MinConsumptionFraction"] = min_frac
    return result if result else None


def _build_heat_controller_from_hc(hc):
    """Build HeatController from parsed heatController component data."""
    result = {
        "EnableHeat": hc.get("enableHeat", False),
        "InitialTemperature": hc.get("initialTemperature", -1),
        "PoweredAmbientCoolingMultiplier": hc.get("poweredAmbientCoolingMultiplier", 1),
        "MinOperatingTemperature": hc.get("minOperatingTemperature", 0),
        "MinCoolingTemperature": hc.get("minCoolingTemperature", 300),
    }
    ceq = hc.get("coolingEqualization", {})
    if ceq:
        result["CoolingEqualization"] = {
            "EqualizationRate": ceq.get("equalizationRate", 0),
            "TemperatureDifference": ceq.get("temperatureDifference", 0),
        }

    sig = hc.get("signature", {})
    result["Signature"] = {
        "EnableSignature": sig.get("enableSignature", False),
        "MinTemperatureForIR": sig.get("minTemperatureForIR", 250),
        "TemperatureToIR": sig.get("temperatureToIR", 0),
        "StartIREmission": 0.0,
    }

    overheat = hc.get("overheat", {})
    result["Overheat"] = {
        "EnableOverheat": overheat.get("enableOverheat", False),
        "MaxTemperature": overheat.get("maxTemperature", 0),
        "WarningTemperature": overheat.get("warningTemperature", 0),
        "RecoveryTemperature": overheat.get("recoveryTemperature", 0),
    }

    return result


def _build_heat_controller_from_heat(heat):
    """Build HeatController from EntityComponentHeatConnection."""
    return {
        "MinOperatingTemperature": heat.get("minTemperature", 0),
        "MinCoolingTemperature": heat.get("startCoolingTemperature", 300),
        "Signature": {
            "MinTemperatureForIR": heat.get("startIRTemperature", 250),
            "TemperatureToIR": heat.get("temperatureToIR", 0),
        },
        "Overheat": {
            "MaxTemperature": heat.get("maxTemperature", 0),
            "WarningTemperature": heat.get("overheatTemperature", 0),
            "RecoveryTemperature": heat.get("recoveryTemperature", 0),
        },
    }


def _build_weapon_data(components, ctx, item_type="", is_fps=False):
    """Build Weapon object with Ammunition, Firing modes, Consumption."""
    weapon = components.get("weapon", {})
    ammo_comp = components.get("ammo", {})

    result = {}

    # Firing modes
    firing_modes = weapon.get("firingModes", [])
    if firing_modes:
        firing = []
        for mode in firing_modes:
            fire_type = mode.get("fireType", "single")

            # rapidBeam (SWeaponActionDynamicConditionParams wrapper):
            # emit minimal Name/LocalisedName/FireType + DefaultWeaponAction/ConditionalWeaponActions
            # sub-dicts, built by recursively invoking the firing-mode builder.
            # Exception: inner sequence types are NOT emitted (ref convention).
            if fire_type == "rapidBeam":
                ln = ctx.resolve_name(mode.get("localisedName", ""))
                if ln == "<= PLACEHOLDER =>":
                    ln = "@LOC_PLACEHOLDER"
                rb = {
                    "Name": mode.get("name", ""),
                    "LocalisedName": ln,
                    "FireType": "rapidBeam",
                }
                for src_key, dst_key in [("defaultWeaponAction", "DefaultWeaponAction"),
                                          ("conditionalWeaponActions", "ConditionalWeaponActions")]:
                    inner = mode.get(src_key)
                    if not inner or inner.get("fireType") == "sequence":
                        continue
                    # Conditional actions: only include when it's a beam variant
                    # (single/rapid/burst conditional duplicates are omitted by ref).
                    if dst_key == "ConditionalWeaponActions" and inner.get("fireType") != "beam":
                        continue
                    inner_built = _build_single_firing_mode(inner, ctx, weapon)
                    if inner_built:
                        rb[dst_key] = inner_built
                rb["DamagePerShot"] = {}
                rb["DamagePerSecond"] = {}
                firing.append(rb)
                continue

            shot_count = mode.get("shotCount", 0)
            # Burst type includes shot count: "burst 1", "burst 3"
            if fire_type == "burst" and shot_count:
                fire_type = f"burst {shot_count}"

            # Tractor fireType is "tractorbeam" in ref (one word)
            is_beam_like = fire_type in ("beam", "tractor")
            if fire_type == "tractor":
                fire_type = "tractorbeam"

            # Compute effective RPM for charged weapons.
            # Default: cycle = chargeTime + max(cooldown, 60/inner_fireRate)
            # Shotgun-pistol (charge adds pellets): cycle = ct + 1/(pellets × overchargedTime)
            # (the pellet salvo recovery is governed by overchargedTime × pellet count).
            rpm = float(mode.get("fireRate", 0))
            if fire_type == "charged" and rpm > 0:
                charge_time = mode.get("chargeTime", 0)
                cooldown_time = mode.get("cooldownTime", 0)
                cm = mode.get("chargeModifiers") or {}
                cm_pellets = cm.get("pellets", 0) or 0
                overcharged_time = mode.get("overchargedTime", 0) or 0
                if charge_time:
                    if (cm_pellets > 0 and overcharged_time > 0 and is_fps):
                        total_pellets = (mode.get("pelletCount", 0) or 0) + cm_pellets
                        cycle_time = charge_time + 1.0 / (total_pellets * overcharged_time)
                    else:
                        fire_interval = 60.0 / rpm
                        cycle_time = charge_time + max(cooldown_time, fire_interval)
                    rpm = round(60.0 / cycle_time, 1) if cycle_time > 0 else rpm

            # Sequence weapons: effective RPM derives from sequence entry timing.
            # Per-entry time differs between ship and FPS weapons:
            # - Ship: unit="Seconds" → entry_time = 60/inner + delay
            # - FPS:  unit="Seconds" → entry_time = delay (as-is)
            # - Both: unit="RPM" → entry_time = max(60/delay, 60/inner)
            # FPS burst-inner sequences also add:
            #   (shotCount-1)*60/inner  (burst duration, between first and last shot)
            #   + innerCooldownTime     (post-burst recovery)
            if fire_type == "sequence" and rpm > 0:
                seq_entries = mode.get("sequenceEntries") or []
                if seq_entries:
                    shots_per_entry = max(mode.get("shotCount", 0) or 1, 1)
                    inner_interval = 60.0 / rpm
                    inner_cd = mode.get("innerCooldownTime", 0) or 0
                    total_cycle = 0.0
                    total_shots = 0
                    has_mixed_units = len(set(e.get("unit", "") for e in seq_entries)) > 1
                    has_seconds = any(e.get("unit") == "Seconds" for e in seq_entries)
                    for e in seq_entries:
                        delay = e.get("delay", 0) or 0
                        unit = e.get("unit", "")
                        reps = max(e.get("repetitions", 1) or 1, 1)
                        if unit == "RPM" and delay > 0:
                            if is_fps:
                                entry_time = max(60.0 / delay, inner_interval)
                            else:
                                entry_time = 60.0 / delay
                        elif unit == "Seconds":
                            entry_time = delay if is_fps else (inner_interval + delay)
                        else:
                            entry_time = inner_interval
                        total_cycle += entry_time * reps
                        total_shots += shots_per_entry * reps
                    # FPS burst-inner sequences: add burst duration + inner cooldown
                    # (shotCount-1 intervals at inner rate, plus post-burst cooldown).
                    if is_fps and shots_per_entry > 1:
                        total_cycle += (shots_per_entry - 1) * inner_interval + inner_cd
                    if total_cycle > 0:
                        effective_rpm = total_shots * 60.0 / total_cycle
                        # Ship convention: uniform-RPM sequence caps at inner fireRate
                        rpm_units = [e for e in seq_entries if e.get("unit") == "RPM"]
                        uniform_rpm = (len(rpm_units) == len(seq_entries)
                                       and len(set(e.get("delay") for e in rpm_units)) == 1)
                        if not is_fps and uniform_rpm and effective_rpm > rpm:
                            effective_rpm = rpm
                        rpm = round(effective_rpm, 2)
                    # ShotPerAction / ShotPerSequence patterns:
                    # - Ship + mixed RPM rates → ShotPerAction (Meteor pattern)
                    # - FPS: already handled below based on unit mix / inner name
                    rpm_units = [e for e in seq_entries if e.get("unit") == "RPM"]
                    mixed_rates = (len(rpm_units) > 1
                                   and len(set(e.get("delay") for e in rpm_units)) > 1)
                    if not is_fps and len(seq_entries) > 1 and not shot_count and mixed_rates:
                        shot_count = total_shots
                    elif is_fps and len(seq_entries) > 1 and not shot_count and total_shots > 1:
                        shot_count = total_shots

            # Default AmmoPerShot / PelletsPerShot: 0 for beam/tractor, 1 for single/rapid/burst
            default_shots = 0 if is_beam_like else 1
            ln = ctx.resolve_name(mode.get("localisedName", ""))
            if ln == "<= PLACEHOLDER =>":
                ln = "@LOC_PLACEHOLDER"
            pellets_per_shot = mode.get("pelletCount", default_shots) or default_shots
            # Charged mode adds charge's pellets bonus to the base pelletCount
            if fire_type == "charged":
                charge_pellets = (mode.get("chargeModifiers") or {}).get("pellets", 0)
                if charge_pellets:
                    pellets_per_shot = pellets_per_shot + charge_pellets

            fm = {
                "Name": mode.get("name", ""),
                "LocalisedName": ln,
                "RoundsPerMinute": rpm,
                "FireType": fire_type,
                "AmmoPerShot": float(mode.get("ammoCost", default_shots)),
                "PelletsPerShot": float(pellets_per_shot),
                "HeatPerShot": float(mode.get("heatPerShot", 0)),
                "WearPerShot": float(mode.get("wearPerShot", 0)),
            }
            # ShotPerAction (burst count) / ShotPerSequence for sequence types.
            # Ship sequence w/ mixed RPM rates → ShotPerAction.
            # FPS sequence: uses inner-action name + unit mix to decide which.
            # Charged modes never emit ShotPerAction (ref convention).
            if shot_count and fire_type != "charged":
                if fire_type == "sequence" and is_fps:
                    seq_entries = mode.get("sequenceEntries") or []
                    units = set(e.get("unit", "") for e in seq_entries)
                    is_mixed = len(units) > 1
                    inner_name = mode.get("name", "")
                    pellets_count = mode.get("pelletCount", 1) or 1
                    all_seconds = units == {"Seconds"}
                    if inner_name == "Burst" or is_mixed:
                        fm["ShotPerAction"] = float(shot_count)
                    elif pellets_count > 1 or all_seconds:
                        fm["ShotPerSequence"] = float(shot_count)
                else:
                    fm["ShotPerAction"] = float(shot_count)

            # SpinUp/SpinDown for rapid fire (gatling). Always emit for rapid type.
            if fire_type == "rapid":
                fm["SpinUpTime"] = float(mode.get("spinUpTime") or 0.0)
                fm["SpinDownTime"] = float(mode.get("spinDownTime") or 0.0)
            else:
                if mode.get("spinUpTime"):
                    fm["SpinUpTime"] = float(mode["spinUpTime"])
                if mode.get("spinDownTime"):
                    fm["SpinDownTime"] = float(mode["spinDownTime"])

            # FireChargedParameters for charged weapons
            if fire_type == "charged" and mode.get("chargeTime"):
                fcp = {
                    "ChargeTime": float(mode.get("chargeTime", 0)),
                    "OverchargeTime": float(mode.get("overchargeTime", 0)),
                    "OverchargedTime": float(mode.get("overchargedTime", 0)),
                    "Cooldown": float(mode.get("cooldownTime", 0)),
                    "FireOnFullCharge": mode.get("fireOnFullCharge", False),
                    "FireOnlyOnFullCharge": mode.get("fireOnlyOnFullCharge", False),
                }
                cm = mode.get("chargeModifiers")
                if cm:
                    fcp["Modifiers"] = {
                        "FireRateMultiplier": cm.get("fireRateMultiplier", 1.0),
                        "ProjectileSpeedMultiplier": cm.get("projectileSpeedMultiplier", 1.0),
                        "DamageMultiplier": cm.get("damageMultiplier", 1.0),
                        "DamageOverTimeMultiplier": cm.get("damageOverTimeMultiplier", 1.0),
                    }
                fm["FireChargedParameters"] = fcp

            spread = mode.get("spread")
            if spread:
                fm["Spread"] = {
                    "Min": spread.get("min", 0),
                    "Max": spread.get("max", 0),
                    "FirstAttack": spread.get("firstAttack", 0),
                    "PerAttack": spread.get("attack", 0),
                    "Decay": spread.get("decay", 0),
                }
            elif is_fps and fire_type == "sequence":
                # FPS sequence weapons lacking spread params get a default all-1.0 block
                # (ref convention — e.g. apar_special_ballistic_02).
                fm["Spread"] = {
                    "Min": 1.0, "Max": 1.0,
                    "FirstAttack": 1.0, "PerAttack": 1.0, "Decay": 1.0,
                }

            # AimModifier.SpreadModifier — only emit when weapon's aimAction has
            # a spreadModifier sub-element (ship weapons lack this; FPS-specific).
            if ((fire_type in ("single", "rapid", "charged", "sequence")
                             or fire_type.startswith("burst"))
                    and "aimSpreadModifier" in weapon):
                aim_sp = weapon["aimSpreadModifier"]
                fm["AimModifier"] = {
                    "SpreadModifier": {
                        "Min": float(aim_sp.get("min", 0.0)),
                        "Max": float(aim_sp.get("max", 0.0)),
                        "FirstAttack": float(aim_sp.get("firstAttack", 0.0)),
                        "PerAttack": float(aim_sp.get("attack", 0.0)),
                        "Decay": float(aim_sp.get("decay", 0.0)),
                    }
                }

            # Beam mode: add Spread/Beam/DamagePerSecond blocks
            if fire_type == "beam":
                if "Spread" not in fm:
                    fm["Spread"] = {
                        "Min": 0.0, "Max": 0.0,
                        "FirstAttack": 0.0, "PerAttack": 0.0, "Decay": 0.0,
                    }
                fm["Beam"] = {
                    "HitType": mode.get("hitType", ""),
                    "HitRadius": float(mode.get("hitRadius", 0)),
                    "MinEnergyDraw": float(mode.get("minEnergyDraw", 0)),
                    "MaxEnergyDraw": float(mode.get("maxEnergyDraw", 0)),
                    "FullDamageRange": float(mode.get("fullDamageRange", 0)),
                    "ZeroDamageRange": float(mode.get("zeroDamageRange", 0)),
                    "HeatPerSecond": float(mode.get("heatPerSecond", 0)),
                    "WearPerSecond": float(mode.get("wearPerSecond", 0)),
                    "ChargeUpTime": float(mode.get("chargeUpTime", 0)),
                    "ChargeDownTime": float(mode.get("chargeDownTime", 0)),
                }
                dps_dmg = mode.get("damagePerSecondBreakdown") or {}
                fm["DamagePerSecond"] = {k: float(v) for k, v in dps_dmg.items()}
            firing.append(fm)
        result["Firing"] = firing

    # Ammunition (from AmmoParams cross-reference)
    ammo_guid = ammo_comp.get("ammoParamsRecord", "")
    ammo_data = ctx.get_ammo(ammo_guid)
    if ammo_data:
        ammo = {
            "Speed": float(ammo_data.get("speed", 0)),
            "LifeTime": float(ammo_data.get("lifetime", 0)),
            "Range": float(round(ammo_data.get("speed", 0) * ammo_data.get("lifetime", 0))),
            "Size": float(ammo_data.get("size", 0)),
        }
        # Explosion radius
        exp_min = ammo_data.get("explosionRadiusMin")
        exp_max = ammo_data.get("explosionRadiusMax")
        if exp_min:
            ammo["ExplosionRadiusMin"] = float(exp_min)
        if exp_max:
            ammo["ExplosionRadiusMax"] = float(exp_max)

        ammo["Capacity"] = float(ammo_comp.get("maxAmmoCount", 0))

        pen = ammo_data.get("penetration", {})
        if pen:
            ammo["Penetration"] = {
                "BasePenetrationDistance": float(pen.get("basePenetrationDistance", 0)),
                "NearRadius": float(pen.get("nearRadius", 0)),
                "FarRadius": float(pen.get("farRadius", 0)),
            }
        dmg = ammo_data.get("damage", {})
        impact = {}
        if dmg:
            for key in ["physical", "energy", "distortion", "thermal", "biochemical", "stun"]:
                val = dmg.get(key, 0)
                if val:
                    impact[key.capitalize()] = float(val)
        ammo["ImpactDamage"] = impact

        det_dmg = ammo_data.get("detonationDamage", {})
        if det_dmg:
            det = {}
            for key in ["physical", "energy", "distortion"]:
                val = det_dmg.get(key, 0)
                if val:
                    det[key.capitalize()] = val
            if det:
                ammo["DetonationDamage"] = det

        # SalvageHead items include an empty DamageDrop block in ref, but only
        # when the weapon has actual impact damage (Salvage_Head_standard/Salvation).
        # Pure tractor-beam salvage heads without damage omit DamageDrop.
        if "SalvageHead" in item_type and impact:
            ammo["DamageDrop"] = {"MinDistance": {}, "DropPerMeter": {}, "MinDamage": {}}

        result["Ammunition"] = ammo

        # Compute DPS for each firing mode (always include DamagePerShot/DamagePerSecond).
        # Ref sums impact + detonation damage per type.
        dps_source = {}
        for key in ["physical", "energy", "distortion", "thermal"]:
            total = (dmg or {}).get(key, 0) + (det_dmg or {}).get(key, 0)
            if total:
                dps_source[key] = total

        _populate_firing_dps(result.get("Firing", []), dps_source)
    else:
        _populate_firing_dps(result.get("Firing", []), {})

    # Modifiers from gimbal mode modifier record
    gimbal_guid = weapon.get("gimbalModeModifierRecord")
    if gimbal_guid:
        gm = ctx.get_gimbal_modifier(gimbal_guid)
        frm = gm["fireRateMultiplier"] if gm and gm.get("fireRateMultiplier") else 1.0
        result["Modifiers"] = {
            "FireRateMultiplier": {
                "Precision": frm,
                "Target": frm,
                "Gimbal": frm,
            },
        }

    # Consumption from weapon regen consumer params.
    # For FPS weapons ref emits all 6 fields even when zero; for ship weapons
    # only emit fields that are non-zero (to preserve existing behaviour).
    regen = weapon.get("regenConsumer")
    consumption = {}
    if regen:
        # Detect FPS context via maxAmmoLoad presence as heuristic — FPS regen
        # consumers always have a magazine load while ship weapons may not.
        any_set = any(regen.get(k) for k in ("requestedRegenPerSec", "regenerationCooldown",
                                              "regenerationCostPerBullet", "requestedAmmoLoad",
                                              "maxAmmoLoad", "maxRegenPerSec"))
        if any_set:
            consumption["RequestedRegenPerSec"] = safe_float(regen.get("requestedRegenPerSec", 0))
            consumption["Cooldown"] = safe_float(regen.get("regenerationCooldown", 0))
            consumption["CostPerBullet"] = safe_float(regen.get("regenerationCostPerBullet", 0))
            consumption["RequestedAmmoLoad"] = safe_float(regen.get("requestedAmmoLoad", 0))
            consumption["MaxAmmo"] = safe_float(regen.get("maxAmmoLoad", 0))
            consumption["MaxRegenPerSec"] = safe_float(regen.get("maxRegenPerSec", 0))
    if consumption:
        result["Consumption"] = consumption

    # HeatParameters from SWeaponSimplifiedHeatParams
    shp = weapon.get("simplifiedHeat")
    if shp:
        result["HeatParameters"] = {
            "MinTemp": shp.get("minTemperature", 0.0),
            "OverheatTemp": shp.get("overheatTemperature", 100.0),
            "CoolingPerSecond": shp.get("coolingPerSecond", 0.0),
            "TimeTillCoolingStarts": shp.get("timeTillCoolingStarts", 0.0),
            "OverheatFixTime": shp.get("overheatFixTime", 0.0),
            "TempAfterOverheatFix": shp.get("temperatureAfterOverheatFix", 0.0),
        }

    return result if result else None


def _build_single_firing_mode(mode, ctx, weapon):
    """Build a single firing-mode dict (used for nested DefaultWeaponAction /
    ConditionalWeaponActions inside rapidBeam modes)."""
    fire_type = mode.get("fireType", "single")
    is_beam_like = fire_type in ("beam", "tractor")
    default_shots = 0 if is_beam_like else 1
    ln = ctx.resolve_name(mode.get("localisedName", ""))
    if ln == "<= PLACEHOLDER =>":
        ln = "@LOC_PLACEHOLDER"

    fm = {
        "Name": mode.get("name", ""),
        "LocalisedName": ln,
    }
    if fire_type == "rapid":
        fm["SpinUpTime"] = float(mode.get("spinUpTime") or 0.0)
        fm["SpinDownTime"] = float(mode.get("spinDownTime") or 0.0)
    fm["RoundsPerMinute"] = float(mode.get("fireRate", 0))
    fm["FireType"] = fire_type
    fm["AmmoPerShot"] = float(mode.get("ammoCost", default_shots))
    fm["PelletsPerShot"] = float(mode.get("pelletCount", default_shots))
    fm["HeatPerShot"] = float(mode.get("heatPerShot", 0))
    fm["WearPerShot"] = float(mode.get("wearPerShot", 0))

    spread = mode.get("spread")
    if spread:
        fm["Spread"] = {
            "Min": spread.get("min", 0),
            "Max": spread.get("max", 0),
            "FirstAttack": spread.get("firstAttack", 0),
            "PerAttack": spread.get("attack", 0),
            "Decay": spread.get("decay", 0),
        }

    if fire_type in ("single", "rapid", "charged", "sequence") or fire_type.startswith("burst"):
        aim_sp = weapon.get("aimSpreadModifier") or {}
        fm["AimModifier"] = {
            "SpreadModifier": {
                "Min": float(aim_sp.get("min", 0.0)),
                "Max": float(aim_sp.get("max", 0.0)),
                "FirstAttack": float(aim_sp.get("firstAttack", 0.0)),
                "PerAttack": float(aim_sp.get("attack", 0.0)),
                "Decay": float(aim_sp.get("decay", 0.0)),
            }
        }

    if fire_type == "beam":
        fm["RoundsPerMinute"] = 0.0
        fm["AmmoPerShot"] = 0.0
        fm["PelletsPerShot"] = 0.0
        fm["Beam"] = {
            "HitType": mode.get("hitType", ""),
            "HitRadius": float(mode.get("hitRadius", 0)),
            "MinEnergyDraw": float(mode.get("minEnergyDraw", 0)),
            "MaxEnergyDraw": float(mode.get("maxEnergyDraw", 0)),
            "FullDamageRange": float(mode.get("fullDamageRange", 0)),
            "ZeroDamageRange": float(mode.get("zeroDamageRange", 0)),
            "HeatPerSecond": float(mode.get("heatPerSecond", 0)),
            "WearPerSecond": float(mode.get("wearPerSecond", 0)),
            "ChargeUpTime": float(mode.get("chargeUpTime", 0)),
            "ChargeDownTime": float(mode.get("chargeDownTime", 0)),
        }
        dps_dmg = mode.get("damagePerSecondBreakdown") or {}
        fm["DamagePerSecond"] = {k: float(v) for k, v in dps_dmg.items()}
    return fm


def _resolve_fps_ammo(weapon_data, default_loadout, ctx):
    """Resolve FPS weapon ammo from the magazine in the default loadout."""
    for entry in default_loadout:
        pn = entry.get("portName", "").lower()
        if "magazine" not in pn and "ammo" not in pn:
            continue

        cn = entry.get("entityClassName", "")
        ref = entry.get("entityClassReference", "")

        resolved = cn
        if not cn and ref:
            resolved = ctx.resolve_guid(ref)
        if not resolved:
            continue

        mag_item = ctx.get_item(resolved)
        if not mag_item:
            continue

        mag_ammo = mag_item.get("components", {}).get("ammo", {})
        ammo_guid = mag_ammo.get("ammoParamsRecord", "")
        ammo_data = ctx.get_ammo(ammo_guid)

        if ammo_data:
            speed = safe_float(ammo_data.get("speed", 0))
            lifetime = safe_float(ammo_data.get("lifetime", 0))
            ammo = {
                "Speed": speed,
                "LifeTime": lifetime,
                "Range": float(round(speed * lifetime)),
                "Size": safe_float(ammo_data.get("size", 0)),
            }
            exp_min = ammo_data.get("explosionRadiusMin")
            exp_max = ammo_data.get("explosionRadiusMax")
            # If either is set, emit both (0.0 is a valid min value — behr_glauncher).
            if exp_max:
                ammo["ExplosionRadiusMin"] = safe_float(exp_min or 0)
                ammo["ExplosionRadiusMax"] = safe_float(exp_max)
            elif exp_min:
                ammo["ExplosionRadiusMin"] = safe_float(exp_min)
            pen = ammo_data.get("penetration", {})
            if pen:
                ammo["Penetration"] = {
                    "BasePenetrationDistance": safe_float(pen.get("basePenetrationDistance", 0)),
                    "NearRadius": safe_float(pen.get("nearRadius", 0)),
                    "FarRadius": safe_float(pen.get("farRadius", 0)),
                }
            drop = ammo_data.get("damageDrop", {})
            if drop:
                def _cap_damage_keys(d):
                    if not isinstance(d, dict):
                        return {}
                    return {k.capitalize() if isinstance(k, str) else k: v for k, v in d.items()}
                ammo["DamageDrop"] = {
                    "MinDistance": _cap_damage_keys(drop.get("minDistance", {})),
                    "DropPerMeter": _cap_damage_keys(drop.get("dropPerMeter", {})),
                    "MinDamage": _cap_damage_keys(drop.get("minDamage", {})),
                }
            dmg = ammo_data.get("damage", {})
            impact = {}
            if dmg:
                for key in ["physical", "energy", "distortion", "thermal", "biochemical", "stun"]:
                    val = dmg.get(key, 0)
                    if val:
                        impact[key.capitalize()] = safe_float(val)
            # Always include ImpactDamage for FPS (empty when all-zero, e.g. toy pistol)
            ammo["ImpactDamage"] = impact
            # Emit empty DamageDrop block only when ImpactDamage is non-empty OR
            # when there's literally no damage at all (toy pistol case).
            det_dmg_nonempty = ammo_data.get("detonationDamage") and any(
                v for v in ammo_data["detonationDamage"].values() if isinstance(v, (int, float))
            )
            if "DamageDrop" not in ammo:
                if not det_dmg_nonempty or impact:
                    ammo["DamageDrop"] = {"MinDistance": {}, "DropPerMeter": {}, "MinDamage": {}}

            det_dmg = ammo_data.get("detonationDamage", {})
            if det_dmg:
                det = {}
                for key in ["physical", "energy", "distortion"]:
                    val = det_dmg.get(key, 0)
                    if val:
                        det[key.capitalize()] = safe_float(val)
                if det:
                    ammo["DetonationDamage"] = det

            weapon_data["Ammunition"] = ammo

            # Compute DPS for firing modes. For charged modes, also emit AmmoSpeed/AmmoRange
            # (base values scaled by chargeModifiers.projectileSpeedMultiplier).
            base_speed = speed
            base_lifetime = lifetime
            if dmg and weapon_data.get("Firing"):
                # Combine impact + detonation damage for DPS source
                dps_source = {}
                for key in ["physical", "energy", "distortion", "thermal", "biochemical", "stun"]:
                    total = (dmg or {}).get(key, 0) + (det_dmg or {}).get(key, 0)
                    if total:
                        dps_source[key] = total

                for fm in weapon_data["Firing"]:
                    # Beam/rapidBeam/tractor modes carry their own DPS — don't overwrite
                    if fm.get("FireType") in ("rapidBeam", "beam", "tractorbeam", "tractor"):
                        continue
                    rpm = fm.get("RoundsPerMinute", 0)
                    pellets = fm.get("PelletsPerShot", 1)
                    # Charged-mode multipliers
                    dmg_mult = 1.0
                    if fm.get("FireType") == "charged":
                        fcp_mods = fm.get("FireChargedParameters", {}).get("Modifiers", {})
                        dmg_mult = float(fcp_mods.get("DamageMultiplier", 1.0))
                        speed_mult = float(fcp_mods.get("ProjectileSpeedMultiplier", 1.0))
                        if speed_mult and speed_mult != 1.0:
                            charged_speed = base_speed * speed_mult
                            fm["AmmoSpeed"] = float(charged_speed)
                            fm["AmmoRange"] = float(round(charged_speed * base_lifetime))
                    fm["DamagePerShot"] = {}
                    fm["DamagePerSecond"] = {}
                    for key, val in dps_source.items():
                        k = key.capitalize()
                        shot = val * pellets * dmg_mult
                        fm["DamagePerShot"][k] = shot
                        fm["DamagePerSecond"][k] = round(shot * (rpm / 60.0), 2) if rpm else 0

        break  # Only process first magazine


def _build_shield_data(shield):
    """Build Shield object with full resistance/absorption data."""
    result = {
        "Health": shield.get("maxShieldHealth", 0),
        "RegenRate": shield.get("maxShieldRegen", 0),
        "DownedDelay": shield.get("downedRegenDelay", 0),
        "DamagedDelay": shield.get("damagedRegenDelay", 0),
    }

    if "reservePool" in shield:
        rp = shield["reservePool"]
        result["ReservePool"] = {
            "InitialHealthRatio": rp.get("initialHealthRatio", rp.get("InitialHealthRatio", 0)),
            "MaxHealthRatio": rp.get("maxHealthRatio", rp.get("MaxHealthRatio", 0)),
            "RegenRateRatio": rp.get("regenRateRatio", rp.get("RegenRateRatio", 0)),
            "DrainRateRatio": rp.get("drainRateRatio", rp.get("DrainRateRatio", 0)),
        }

    if "resistance" in shield:
        result["Resistance"] = _capitalize_damage_ranges(shield["resistance"])

    if "absorption" in shield:
        result["Absorption"] = _capitalize_damage_ranges(shield["absorption"])

    return result


def _capitalize_damage_ranges(data):
    """Capitalize damage type keys in min/max range dicts."""
    result = {}
    for key, val in data.items():
        cap_key = key.capitalize() if key[0].islower() else key
        if isinstance(val, dict):
            result[cap_key] = {
                "Minimum": val.get("min", 0),
                "Maximum": val.get("max", 0),
            }
        else:
            result[cap_key] = val
    return result


def _build_ports(ports, parent_tags=None, ctx=None, default_loadout=None, parent_type=""):
    """Build Ports array for items."""
    # Build lookup from defaultLoadout entries by portName.
    # When the same portName has multiple entries (e.g. the Retaliator Rear Cargo
    # module's lift door declares both Front- and Rear-cargo control panels),
    # ref uses the first occurrence, not the last.
    dl_by_port = {}
    if default_loadout:
        for dl_entry in default_loadout:
            pn = dl_entry.get("portName", "")
            if pn and pn not in dl_by_port:
                dl_by_port[pn] = dl_entry

    result = []
    for port in ports:
        port_name = port.get("name", "")
        p = {
            "PortName": port_name,
            "MinSize": port.get("minSize", 0),
            "MaxSize": port.get("maxSize", 0),
        }
        if port.get("types"):
            p["Types"] = port["types"]

        # Loadout and InstalledItem — first from port's own defaultLoadout/Ref,
        # then from the item's SEntityComponentDefaultLoadoutParams
        loadout_class = port.get("defaultLoadout", "")
        loadout_ref = port.get("defaultLoadoutRef", "")

        # If not in port def, check defaultLoadout component
        if not loadout_class and not loadout_ref and port_name in dl_by_port:
            dl_entry = dl_by_port[port_name]
            loadout_class = dl_entry.get("entityClassName", "")
            loadout_ref = dl_entry.get("entityClassReference", "")

        # For WeaponPersonal.Large magazine_attach ports, ref uses the raw GUID
        # as Loadout (not the resolved className) — e.g. none_special_ballistic_01.
        if (parent_type == "WeaponPersonal.Large"
                and port_name == "magazine_attach"
                and loadout_class and loadout_ref):
            loadout_class = ""

        # Get children from defaultLoadout for passing to InstalledItem
        dl_children = dl_by_port.get(port_name, {}).get("children", []) if dl_by_port else []

        # LifeSupport filter slots ($slot_*) keep the Loadout GUID but skip InstalledItem expansion.
        skip_installed = (parent_type == "LifeSupportGenerator.UNDEFINED"
                          and port_name.startswith("$slot_"))

        if loadout_class and ctx:
            p["Loadout"] = loadout_class
            if not skip_installed:
                installed_record = ctx.get_item(loadout_class)
                if installed_record:
                    p["InstalledItem"] = build_std_item(installed_record, ctx, dl_children, nested=True)
        elif loadout_ref and loadout_ref != "00000000-0000-0000-0000-000000000000" and ctx:
            p["Loadout"] = loadout_ref
            if not skip_installed:
                resolved_class = ctx.resolve_guid(loadout_ref)
                if resolved_class:
                    installed_record = ctx.get_item(resolved_class)
                    if installed_record:
                        p["InstalledItem"] = build_std_item(installed_record, ctx, dl_children, nested=True)

        flags_str = port.get("flags", "")
        flags_lower = flags_str.lower() if isinstance(flags_str, str) else ""
        # Ref emits Uneditable=True when flag is $uneditable (preferred marker) OR
        # plain "uneditable". BUT when the literal flag string is "Uneditable"
        # (capitalized, single-word), ref treats it only as a Flags entry, not top-level.
        if flags_str == "Uneditable":
            is_uneditable = False
        else:
            is_uneditable = "uneditable" in flags_lower
        # Only include Flags if non-empty
        if flags_str:
            flags = flags_str.split() if isinstance(flags_str, str) else flags_str
            p["Flags"] = flags
        if parent_tags:
            p["Tags"] = parent_tags

        # RequiredTags from port definition
        req_tags = port.get("requiredPortTags", "")
        if req_tags:
            p["RequiredTags"] = req_tags.split() if isinstance(req_tags, str) else req_tags

        # PortTags from port definition
        port_tags = port.get("portTags", "")
        if port_tags:
            p["PortTags"] = port_tags.split() if isinstance(port_tags, str) else port_tags

        # Only include Uneditable if true
        if is_uneditable:
            p["Uneditable"] = True
        if port.get("subPorts"):
            # Pass children from defaultLoadout for sub-ports
            dl_entry = dl_by_port.get(port_name, {})
            sub_dl = dl_entry.get("children", []) if dl_entry else []
            p["Ports"] = _build_ports(port["subPorts"], parent_tags, ctx, sub_dl)
        result.append(p)
    return result


def _build_armour(armor_data):
    """Build Armour object with proper casing matching the reference format."""
    result = {}

    defl = armor_data.get("damageDeflection", {})
    if defl:
        result["DamageDeflection"] = {
            "Physical": safe_float(defl.get("physical", 0)),
            "Energy": safe_float(defl.get("energy", 0)),
            "Distortion": safe_float(defl.get("distortion", 0)),
            "Thermal": safe_float(defl.get("thermal", 0)),
            "Biochemical": safe_float(defl.get("biochemical", 0)),
            "Stun": safe_float(defl.get("stun", 0)),
        }

    pen_red = armor_data.get("penetrationReduction")
    if pen_red is not None:
        result["PenetrationReduction"] = safe_float(pen_red)

    pen_abs = armor_data.get("penetrationAbsorption", {})
    if pen_abs:
        result["PenetrationAbsorption"] = {
            "Physical": safe_float(pen_abs.get("physical", 0)),
            "Energy": safe_float(pen_abs.get("energy", 0)),
            "Distortion": safe_float(pen_abs.get("distortion", 0)),
            "Thermal": safe_float(pen_abs.get("thermal", 0)),
            "Biochemical": safe_float(pen_abs.get("biochemical", 0)),
            "Stun": safe_float(pen_abs.get("stun", 0)),
        }

    mults = armor_data.get("damageMultipliers", {})
    if mults:
        result["DamageMultipliers"] = {
            "Physical": safe_float(mults.get("physical", 1.0)),
            "Energy": safe_float(mults.get("energy", 1.0)),
            "Distortion": safe_float(mults.get("distortion", 1.0)),
            "Thermal": safe_float(mults.get("thermal", 1.0)),
            "Biochemical": safe_float(mults.get("biochemical", 1.0)),
            "Stun": safe_float(mults.get("stun", 1.0)),
        }

    sig = armor_data.get("signalMultipliers", {})
    if sig:
        result["SignalMultipliers"] = {
            "Electromagnetic": safe_float(sig.get("em", 1.0)),
            "Infrared": safe_float(sig.get("ir", 1.0)),
            "CrossSection": safe_float(sig.get("cs", 1.0)),
        }

    return result if result else None


def _build_missile_rack(ports, item_type):
    """Build MissileRack {Count, Size} from missile/bomb ports."""
    if not ports:
        return None
    base = item_type.split(".")[0] if item_type else ""
    if base not in ("MissileLauncher", "BombLauncher", "GroundVehicleMissileLauncher"):
        return None

    # Count = total number of ports on the launcher item
    count = len(ports)

    # Size from the first port with a missile/bomb type
    size = 0
    for p in ports:
        types = p.get("types", [])
        if any(t.startswith(("Missile", "Bomb")) for t in types):
            size = p.get("maxSize", 0)
            break
    if not size and ports:
        size = ports[0].get("maxSize", 0)

    return {"Count": count, "Size": size}


def _extract_angle_limits(limits):
    """Extract angle limits from standard angle limit params."""
    std = limits.get("SCItemTurretStandardAngleLimitParams", {})
    if std:
        return safe_float(std.get("LowestAngle", -180)), safe_float(std.get("HighestAngle", 180))
    return -180.0, 180.0


def _build_turret(turret_params):
    """Build Turret object with yaw/pitch axis rotation data.

    Ref convention: pitchAxis uses its OWN Speed/TimeToFullSpeed/AccelerationDecay
    but inherits LowestAngle/HighestAngle from the yaw axis.
    """
    ml = turret_params.get("movementList", {})
    joints = ml.get("SCItemTurretJointMovementParams", [])
    if isinstance(joints, dict):
        joints = [joints]

    yaw_params = None
    pitch_params = None

    for joint in joints:
        yaw = joint.get("yawAxis", {})
        if yaw and not yaw_params:
            params = yaw.get("SCItemTurretJointMovementAxisParams", {})
            if params:
                yaw_params = params

        pitch = joint.get("pitchAxis", {})
        if pitch and not pitch_params:
            params = pitch.get("SCItemTurretJointMovementAxisParams", {})
            if params:
                pitch_params = params

    yaw_low = yaw_high = None
    result = {}

    if yaw_params:
        limits = yaw_params.get("angleLimits", {})
        yaw_low, yaw_high = _extract_angle_limits(limits)
        result["yawAxis"] = {
            "Speed": safe_float(yaw_params.get("speed", 0)),
            "TimeToFullSpeed": safe_float(yaw_params.get("acceleration_timeToFullSpeed", 0)),
            "AccelerationDecay": safe_float(yaw_params.get("accelerationDecay", 0)),
            "LowestAngle": yaw_low,
            "HighestAngle": yaw_high,
        }
    elif pitch_params:
        # No yaw data: emit zero-filled yawAxis and reset angle limits to 0,0 for pitch.
        yaw_low, yaw_high = 0.0, 0.0
        result["yawAxis"] = {
            "Speed": 0.0, "TimeToFullSpeed": 0.0, "AccelerationDecay": 0.0,
            "LowestAngle": 0.0, "HighestAngle": 0.0,
        }

    if pitch_params:
        # Inherit angle limits from yaw (ref convention)
        if yaw_low is None:
            limits = pitch_params.get("angleLimits", {})
            yaw_low, yaw_high = _extract_angle_limits(limits)
        result["pitchAxis"] = {
            "Speed": safe_float(pitch_params.get("speed", 0)),
            "TimeToFullSpeed": safe_float(pitch_params.get("acceleration_timeToFullSpeed", 0)),
            "AccelerationDecay": safe_float(pitch_params.get("accelerationDecay", 0)),
            "LowestAngle": yaw_low,
            "HighestAngle": yaw_high,
        }

    # OnlyUsableInRemoteCamera from remoteTurret params
    remote = turret_params.get("remoteTurret", {})
    remote_params = remote.get("SCItemTurretRemoteParams", {})
    if isinstance(remote_params, dict) and remote_params.get("turretOnlyUsableInRemoteCamera") == "1":
        result["OnlyUsableInRemoteCamera"] = True

    return result if result else None


def _build_shield_emitter(params):
    """Build ShieldEmitter from SCItemShieldEmitterParams."""
    result = {}
    ft = params.get("FaceType", "")
    if ft:
        result["FaceType"] = ft
    max_realloc = params.get("MaxReallocation")
    if max_realloc is not None:
        result["MaxReallocation"] = safe_float(max_realloc)
    reconfig = params.get("ReconfigurationCooldown")
    if reconfig is not None:
        result["ReconfigurationCooldown"] = safe_float(reconfig)
    max_elec = params.get("MaxElectricalChargeDamageRate")
    if max_elec is not None:
        result["MaxElectricalChargeDamageRate"] = safe_float(max_elec)
    result["Curves"] = {}
    return result


def _build_quantum_drive(qd):
    """Build QuantumDrive matching reference format.

    Ref format: {FuelRate, JumpRange, DisconnectRange, InterdictionEffectTime,
                 StandardJump: {Speed, Cooldown, Stage1AccelerationRate,
                                State2AccelerationRate, SpoolUpTime}, SplineJump: {...}}
    FuelRate is in raw data as units/sec; ref divides by 1e6.
    """
    if not isinstance(qd, dict):
        return None

    result = {}

    fuel_rate = qd.get("FuelRate")
    if fuel_rate is not None:
        result["FuelRate"] = safe_float(fuel_rate) / 1_000_000.0

    for src in ["JumpRange", "DisconnectRange", "InterdictionEffectTime"]:
        val = qd.get(src)
        if val is not None:
            result[src] = safe_float(val)

    # StandardJump / SplineJump are already in the right format
    for key in ["StandardJump", "SplineJump"]:
        j = qd.get(key)
        if isinstance(j, dict) and j:
            result[key] = {
                "Speed": safe_float(j.get("Speed", 0)),
                "Cooldown": safe_float(j.get("Cooldown", 0)),
                "Stage1AccelerationRate": safe_float(j.get("Stage1AccelerationRate", 0)),
                "State2AccelerationRate": safe_float(j.get("State2AccelerationRate", 0)),
                "SpoolUpTime": safe_float(j.get("SpoolUpTime", 0)),
            }

    return result if result else None


def _build_ifcs(ifcs, components=None):
    """Build Ifcs from IFCSParams. Ref format: {MaxSpeed, SCMSpeed, TorqueImbalanceMultiplier, ...}"""
    result = {}
    for src, dst in [("maxSpeed", "MaxSpeed"), ("scmSpeed", "SCMSpeed")]:
        val = ifcs.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    # Direct float fields
    for src, dst in [("torqueImbalanceMultiplier", "TorqueImbalanceMultiplier"),
                     ("liftMultiplier", "LiftMultiplier"),
                     ("dragMultiplier", "DragMultiplier"),
                     ("precisionMinDistance", "PrecisionMinDistance"),
                     ("precisionMaxDistance", "PrecisionMaxDistance"),
                     ("precisionLandingMultiplier", "PrecisionLandingMultiplier"),
                     ("linearAccelDecay", "LinearAccelDecay"),
                     ("angularAccelDecay", "AngularAccelDecay"),
                     ("scmMaxDragMultiplier", "ScmMaxDragMultiplier")]:
        val = ifcs.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    # MasterModes: only BoostSpeedForward and BoostSpeedBackward
    mm = {}
    boost_fwd = ifcs.get("boostSpeedForward")
    boost_bwd = ifcs.get("boostSpeedBackward")
    if boost_fwd is not None:
        mm["BoostSpeedForward"] = safe_float(boost_fwd)
    if boost_bwd is not None:
        mm["BoostSpeedBackward"] = safe_float(boost_bwd)
    if mm:
        result["MasterModes"] = mm

    # Gravlev (for hover vehicles) from GravlevParams.handling
    if components:
        gp = components.get("GravlevParams", {})
        if isinstance(gp, dict):
            handling = gp.get("handling", {})
            if isinstance(handling, dict) and handling:
                gravlev = {}
                for src, dst in [("turnFriction", "TurnFriction"),
                                 ("selfRightingAccelBoost", "SelfRightingAccelBoost"),
                                 ("hoverMaxSpeed", "HoverMaxSpeed"),
                                 ("airControlMultiplier", "AirControlMultiplier"),
                                 ("antiFallMultiplier", "AntiFallMultiplier"),
                                 ("lateralStrafeMultiplier", "LateralStrafeMultiplier")]:
                    val = handling.get(src)
                    if val is not None:
                        gravlev[dst] = safe_float(val)
                if gravlev:
                    result["Gravlev"] = gravlev

    # AngularVelocity from maxAngularVelocity: x→Pitch, y→Roll, z→Yaw
    mav = ifcs.get("maxAngularVelocity")
    if isinstance(mav, dict) and mav:
        av = {}
        if "x" in mav:
            av["Pitch"] = safe_float(mav["x"])
        if "z" in mav:
            av["Yaw"] = safe_float(mav["z"])
        if "y" in mav:
            av["Roll"] = safe_float(mav["y"])
        if av:
            result["AngularVelocity"] = av

    # AfterBurner from afterburner component
    ab_raw = ifcs.get("afterburner")
    if isinstance(ab_raw, dict) and ab_raw:
        result["AfterBurner"] = _build_afterburner(ab_raw)

    return result if result else None


def _populate_firing_dps(firing_modes, dps_source):
    """Fill in DamagePerShot/DamagePerSecond for each firing mode.

    Beam fire types already carry DamagePerSecond from their own data; leave them alone.
    For other fire types, use the weapon's impact damage × pellet count × RPM.
    Charged weapons with chargeModifiers.damageMultiplier scale damage per shot.
    """
    for fm in firing_modes:
        if fm.get("FireType") == "beam":
            continue
        rpm = fm.get("RoundsPerMinute", 0)
        pellets = fm.get("PelletsPerShot", 1)
        # Apply charged damage multiplier (e.g., MassDriver S10 fires at 2x damage)
        fcp = fm.get("FireChargedParameters") or {}
        mods = fcp.get("Modifiers") or {} if isinstance(fcp, dict) else {}
        damage_mult = float(mods.get("DamageMultiplier", 1.0)) if isinstance(mods, dict) else 1.0
        fm["DamagePerShot"] = {}
        fm["DamagePerSecond"] = {}
        if dps_source:
            for key in ["physical", "energy", "distortion", "thermal"]:
                val = dps_source.get(key, 0)
                if val:
                    k = key.capitalize()
                    dps_val = round(val * pellets * damage_mult, 2)
                    if dps_val:
                        fm["DamagePerShot"][k] = dps_val
                        fm["DamagePerSecond"][k] = round(dps_val * (rpm / 60.0), 2) if rpm else 0.0


def _apply_blade_modifier(ifcs, class_name):
    """Apply BRRA Blade modifier deltas to a base Ifcs.

    Flight_Blade_HND (Handling): trades speed for agility.
      MaxSpeed -25, SCMSpeed -8, BoostFwd -10, BoostBack -10,
      Pitch +1, Yaw +1, Roll +2.
    Flight_Blade_SPD (Speed): trades agility for speed.
      MaxSpeed +25, SCMSpeed +8, BoostFwd +10, BoostBack +10,
      Pitch -1, Yaw -1, Roll -2.
    The deltas come from SIFCSModifiersLegacy records (FlightBlade_HND/SPD).
    """
    if not class_name:
        return
    # NOTE (#30 in NAME_FILTERS.md): the classification uses the ClassName
    # suffix, which mirrors the `SIFCSModifiersLegacy.FlightBlade_HND/SPD`
    # record the item references via `IFCSParams.modifiersLegacy`. The
    # proper structural fix would parse those records into ctx and apply
    # their actual delta values (numbers + vectors) instead of the
    # hardcoded `sign * 25 / 8 / 10 / 1 / 2` below, which happen to match
    # the record values in current data. Deferred as a multi-file refactor.
    if class_name.endswith("_Flight_Blade_HND") or class_name.endswith("_Blade_HND"):
        sign = -1
    elif class_name.endswith("_Flight_Blade_SPD") or class_name.endswith("_Blade_SPD"):
        sign = 1
    else:
        return

    if "MaxSpeed" in ifcs:
        ifcs["MaxSpeed"] = ifcs["MaxSpeed"] + sign * 25
    if "SCMSpeed" in ifcs:
        ifcs["SCMSpeed"] = ifcs["SCMSpeed"] + sign * 8

    mm = ifcs.get("MasterModes")
    if isinstance(mm, dict):
        if "BoostSpeedForward" in mm:
            mm["BoostSpeedForward"] = mm["BoostSpeedForward"] + sign * 10
        if "BoostSpeedBackward" in mm:
            mm["BoostSpeedBackward"] = mm["BoostSpeedBackward"] + sign * 10

    av = ifcs.get("AngularVelocity")
    if isinstance(av, dict):
        if "Pitch" in av:
            av["Pitch"] = av["Pitch"] + (-sign) * 1
        if "Yaw" in av:
            av["Yaw"] = av["Yaw"] + (-sign) * 1
        if "Roll" in av:
            av["Roll"] = av["Roll"] + (-sign) * 2


def _build_afterburner(ab):
    """Build AfterBurner object from IFCS afterburner params."""
    def vec3(key):
        v = ab.get(key, {})
        if isinstance(v, dict) and v:
            return {
                "x": safe_float(v.get("x", 0)),
                "y": safe_float(v.get("y", 0)),
                "z": safe_float(v.get("z", 0)),
            }
        return {}

    result = {
        "AfterburnerAngCapacitorScaling": safe_float(ab.get("afterburnerAngCapacitorScaling", 0)),
        "PreDelayTime": safe_float(ab.get("afterburnerPreDelayTime", 0)),
        "RampUpTime": safe_float(ab.get("afterburnerRampUpTime", 0)),
        "RampDownTime": safe_float(ab.get("afterburnerRampDownTime", 0)),
        "AccelMultiplierPositive": vec3("afterburnAccelMultiplierPositive"),
        "AccelMultiplierNegative": vec3("afterburnAccelMultiplierNegative"),
        "LinTimeToFullAccelerationMultiplier": vec3("afterburnLinTimeToFullAccelerationMultiplier"),
        "AngAccelMultiplier": vec3("afterburnAngAccelMultiplier"),
        "AngVelocityMultiplier": vec3("afterburnAngVelocityMultiplier"),
        "AngTimeToFullAccelerationMultiplier": vec3("afterburnAngTimeToFullAccelerationMultiplier"),
    }

    # Capacitor
    size = safe_float(ab.get("capacitorMax", 0))
    regen_per_sec = safe_float(ab.get("capacitorRegenPerSec", 0))
    regen_time = round(size / regen_per_sec, 1) if regen_per_sec else 0.0

    # Curves.AngVelocity from afterburnerAngCapacitorScalingCurve.points.Vec2
    curve = ab.get("afterburnerAngCapacitorScalingCurve", {})
    ang_velocity_points = []
    if isinstance(curve, dict):
        points = curve.get("points", {})
        if isinstance(points, dict):
            vec2 = points.get("Vec2", [])
            if isinstance(vec2, dict):
                vec2 = [vec2]
            for pt in vec2:
                if isinstance(pt, dict):
                    ang_velocity_points.append({
                        "x": safe_float(pt.get("x", 0)),
                        "y": safe_float(pt.get("y", 0)),
                    })

    capacitor = {
        "Size": size,
        "ThresholdRatio": safe_float(ab.get("afterburnerCapacitorThresholdRatio", 0)),
        "IdleCost": safe_float(ab.get("capacitorAfterburnerIdleCost", 0)),
        "LinearCost": safe_float(ab.get("capacitorAfterburnerLinearCost", 0)),
        "AngularCost": safe_float(ab.get("capacitorAfterburnerAngularCost", 0)),
        "RegenDelay": safe_float(ab.get("capacitorRegenDelayAfterUse", 0)),
        "RegenPerSec": regen_per_sec,
        "RegenerationTime": regen_time,
        "Curves": {
            "Regen": ab.get("capacitorAssignmentInputOutputRegen", ""),
            "RegenNavMode": ab.get("capacitorAssignmentInputOutputRegenNavMode", ""),
            "Usage": ab.get("capacitorAssignmentInputOutputUsage", ""),
            "AngVelocity": ang_velocity_points,
        },
    }
    result["Capacitor"] = capacitor
    return result


def _build_radar(radar):
    """Build Radar from SCItemRadarComponentParams."""
    result = {}

    # AimAssist
    aa = radar.get("aimAssist", {})
    if isinstance(aa, dict) and aa:
        result["AimAssist"] = {
            "DistanceMin": safe_float(aa.get("distanceMinAssignment", aa.get("distanceMin", 0))),
            "DistanceMax": safe_float(aa.get("distanceMaxAssignment", aa.get("distanceMax", 0))),
            "OutsideRangeBufferDistance": safe_float(aa.get("outsideRangeBufferDistance", 0)),
        }

    # Signal detection types
    sd = radar.get("signatureDetection", {})
    sd_list = sd.get("SCItemRadarSignatureDetection", [])
    if isinstance(sd_list, dict):
        sd_list = [sd_list]

    # Sensitivity modifiers for ground
    sm = radar.get("sensitivityModifiers", {})
    ground_add = 0.0
    if isinstance(sm, dict):
        mod = sm.get("SCItemRadarSensitivityModifier", {})
        if isinstance(mod, dict):
            ground_add = safe_float(mod.get("sensitivityAddition", "0"))

    # Signal index -> signal name mapping (determined from reference data)
    # 0=EM, 1=IR, 2=CS, 3=DB, 4=RS, 5=ID, 6=Scan1, 7=Scan2
    idx_to_name = {0: "EM", 1: "IR", 2: "CS", 3: "DB", 4: "RS", 5: "ID", 6: "Scan1", 7: "Scan2"}
    # Output order (as in reference): IR, EM, CS, DB, RS, ID, Scan1, Scan2
    output_order = ["IR", "EM", "CS", "DB", "RS", "ID", "Scan1", "Scan2"]

    # GroundSensitivity is a single scalar per item = max(0, IR_sensitivity + ground_add),
    # applied uniformly to ALL signals.
    ir_idx = 1  # IR
    ir_sens = 0.0
    if ir_idx < len(sd_list):
        ir_sens = safe_float(sd_list[ir_idx].get("sensitivity", "0"))
    ground_sens = round(max(0.0, ir_sens + ground_add), 4)

    name_to_entry = {}
    for idx, name in idx_to_name.items():
        if idx < len(sd_list):
            entry = sd_list[idx]
            sens = safe_float(entry.get("sensitivity", "0"))
            piercing = safe_float(entry.get("piercing", "0"))
            passive = entry.get("permitPassiveDetection", "1") == "1"
            active = entry.get("permitActiveDetection", "1") == "1"
            name_to_entry[name] = {
                "Sensitivity": sens,
                "GroundSensitivity": ground_sens,
                "Piercing": piercing,
                "PermitPassiveDetection": passive,
                "PermitActiveDetection": active,
            }
    for name in output_order:
        if name in name_to_entry:
            result[name] = name_to_entry[name]

    return result if result else None


def _build_jump_drive(jd):
    """Build JumpDrive from SCItemJumpDriveParams."""
    result = {}
    for src, dst in [("alignmentRate", "AlignmentRate"),
                     ("alignmentDecayRate", "AlignmentDecayRate"),
                     ("tuningRate", "TuningRate"),
                     ("fuelUsageEfficiencyMultiplier", "FuelUsageEfficiencyMultiplier")]:
        val = jd.get(src)
        if val is not None:
            # insert in correct order: AlignmentRate, AlignmentDecayRate, TuningRate, TuningDecayRate, FuelUsage
            result[dst] = safe_float(val)
            if dst == "TuningRate":
                # TuningDecayRate mirrors AlignmentDecayRate (ref convention)
                adr = jd.get("alignmentDecayRate")
                if adr is not None:
                    result["TuningDecayRate"] = safe_float(adr)
    return result if result else None


def _build_emp(emp):
    """Build Emp from SCItemEMPParams."""
    return {
        "ChargeTime": safe_float(emp.get("chargeTime", 0)),
        "UnleashTime": safe_float(emp.get("unleashTime", 0)),
        "Damage": safe_float(emp.get("distortionDamage", 0)),
        "MinRadius": safe_float(emp.get("minEmpRadius", 0)),
        "MaxRadius": safe_float(emp.get("empRadius", 0)),
        "CooldownTime": safe_float(emp.get("cooldownTime", 0)),
    }


def _build_self_destruct(sd):
    """Build SelfDestruct from SSCItemSelfDestructComponentParams."""
    return {
        "Countdown": safe_float(sd.get("time", 0)),
        "Damage": safe_float(sd.get("damage", 0)),
        "MinRadius": safe_float(sd.get("minRadius", 0)),
        "MaxRadius": safe_float(sd.get("radius", 0)),
    }


def _build_quantum_interdiction(qi):
    """Build QuantumInterdiction from SCItemQuantumInterdictionGeneratorParams."""
    jammer = qi.get("jammerSettings", {})
    if isinstance(jammer, dict):
        jammer = jammer.get("SCItemQuantumJammerParams", jammer)
    pulse = qi.get("quantumInterdictionPulseSettings", {})
    if isinstance(pulse, dict):
        pulse = pulse.get("SCItemQuantumInterdictionPulseParams", pulse)
    result = {}
    if isinstance(jammer, dict):
        result["JammingRange"] = safe_float(jammer.get("jammerRange", 0))
        result["InterdictionRange"] = safe_float(pulse.get("radiusMeters", 0)) if isinstance(pulse, dict) else 0.0
    if isinstance(pulse, dict):
        result["ChargeTime"] = safe_float(pulse.get("chargeTimeSecs", 0))
        result["ActivationTime"] = safe_float(pulse.get("activationPhaseDuration_seconds", 0))
        result["DisperseChargeTime"] = safe_float(pulse.get("disperseChargeTimeSeconds", 0))
        result["DischargeTime"] = safe_float(pulse.get("dischargeTimeSecs", 0))
        result["CooldownTime"] = safe_float(pulse.get("cooldownTimeSecs", 0))
    return result if result else None


def _build_mining_laser(mining, components):
    """Build MiningLaser from SEntityComponentMiningLaserParams + weapon firing modes."""
    result = {}
    result["ThrottleLerpSpeed"] = safe_float(mining.get("throttleLerpSpeed", 0))
    result["ThrottleMinimum"] = safe_float(mining.get("throttleMinimum", 0))

    def _mod_value(container, key):
        v = container.get(key, {}) if isinstance(container, dict) else {}
        if isinstance(v, dict):
            inner = v.get("FloatModifierMultiplicative")
            if isinstance(inner, dict):
                return safe_float(inner.get("value", 0))
        return None

    mods = mining.get("miningLaserModifiers", {})
    # Only include modifiers that have a value (ref omits unset ones)
    for src, dst in [("resistanceModifier", "ResistanceModifier"),
                     ("laserInstability", "LaserInstability"),
                     ("optimalChargeWindowRateModifier", "OptimalWindowRateModifier"),
                     ("optimalChargeWindowSizeModifier", "OptimalChargeWindowModifier")]:
        val = _mod_value(mods, src)
        if val is not None:
            result[dst] = val

    # InertMaterialsFilter from filterParams.filterModifier
    filter_params = mining.get("filterParams", {})
    val = _mod_value(filter_params, "filterModifier")
    if val is not None:
        result["InertMaterialsFilter"] = val

    # Firing modes from weapon (SWeaponActionFireBeamParams)
    weapon = components.get("weapon", {})
    firing_modes = weapon.get("firingModes", [])
    firing = []
    if firing_modes:
        for mode in firing_modes:
            if mode.get("fireType") != "beam":
                continue
            fm = {
                "Mode": mode.get("mode", ""),
                "FireType": "beam",
                "LaserPower": safe_float(mode.get("damageEnergy", 0)),
                "FullDamageDistance": safe_float(mode.get("fullDamageRange", 0)),
                "MinDamageDistance": safe_float(mode.get("zeroDamageRange", 0)),
            }
            firing.append(fm)
    if firing:
        result["Firing"] = firing
    else:
        # Placeholder Firing block when no beam modes (binoculars, multitool)
        result["Firing"] = [{
            "LaserPower": 0.0,
            "FullDamageDistance": 0.0,
            "MinDamageDistance": 0.0,
        }]

    return result if result else None


def _build_modifier(si, modifier_params, item_type):
    """Build Module/SalvageModifier/BuffModifiers from EntityComponentAttachableModifierParams."""
    modifiers = modifier_params.get("modifiers", {})

    # VehicleMod mining modules (type "UNDEFINED.Gun") emit 4-entry buff modifier arrays
    # instead of a Module block. Ref convention uses zero-filled arrays.
    if item_type == "UNDEFINED.Gun":
        si["RegenBuffModifier"] = [
            {"PowerRatioMultiplier": 0.0, "MaxAmmoLoadMultiplier": 0.0, "MaxRegenPerSecMultiplier": 0.0}
            for _ in range(4)
        ]
        si["SalvageBuffModifier"] = [
            {"SpeedMultiplier": 0.0, "RadiusMultiplier": 0.0, "ExtractionEfficiency": 0.0}
            for _ in range(4)
        ]
        return

    if "Salvage" in item_type:
        # Salvage data lives at weaponStats.salvageModifier
        iwm = modifiers.get("ItemWeaponModifiersParams", {})
        stats = iwm.get("weaponModifier", {}).get("weaponStats", {}) if isinstance(iwm, dict) else {}
        sm = stats.get("salvageModifier", {}) if isinstance(stats, dict) else {}
        if isinstance(sm, dict) and sm:
            si["SalvageModifier"] = [{
                "SpeedMultiplier": safe_float(sm.get("salvageSpeedMultiplier", 0)),
                "RadiusMultiplier": safe_float(sm.get("radiusMultiplier", 0)),
                "ExtractionEfficiency": safe_float(sm.get("extractionEfficiency", 0)),
            }]
    else:
        # Module (mining consumable/gadget)
        charges = safe_int(modifier_params.get("charges", 0))
        modifiers_list = []

        # 1. LaserPowerModifier entries from ItemWeaponModifiersParams (damageMultiplier)
        iwm = modifiers.get("ItemWeaponModifiersParams", {})
        iwm_entries = iwm if isinstance(iwm, list) else ([iwm] if isinstance(iwm, dict) else [])
        for entry in iwm_entries:
            if not isinstance(entry, dict):
                continue
            stats = entry.get("weaponModifier", {}).get("weaponStats", {}) if isinstance(entry.get("weaponModifier"), dict) else {}
            dm = stats.get("damageMultiplier") if isinstance(stats, dict) else None
            if dm is not None:
                modifiers_list.append({"LaserPowerModifier": safe_float(dm)})

        # 2. Mining laser modifier entry from ItemMiningModifierParams or ItemMineableRockModifierParams
        def _get_mlm():
            for wrapper in ("ItemMiningModifierParams", "ItemMineableRockModifierParams"):
                w = modifiers.get(wrapper, {})
                if isinstance(w, dict):
                    candidate = w.get("MiningLaserModifier")
                    if isinstance(candidate, dict):
                        return candidate, w
            return None, None

        mlm, mlm_wrapper = _get_mlm()
        if mlm is not None:
            def _extract_mod(key):
                val = mlm.get(key)
                if isinstance(val, dict):
                    inner = val.get("FloatModifierMultiplicative")
                    if isinstance(inner, dict):
                        return safe_float(inner.get("value", 0))
                return 0.0

            mining_entry = {
                "LaserInstability": _extract_mod("laserInstability"),
                "ResistanceModifier": _extract_mod("resistanceModifier"),
                "OptimalChargeWindowSizeModifier": _extract_mod("optimalChargeWindowSizeModifier"),
                "OptimalChargeWindowRateModifier": _extract_mod("optimalChargeWindowRateModifier"),
                "ShatterDamageModifier": _extract_mod("shatterdamageModifier"),
                "ClusterFactorModifier": _extract_mod("clusterFactorModifier"),
                "CatastrophicChargeWindowRateModifier": _extract_mod("catastrophicChargeWindowRateModifier"),
            }
            # Duration from modifierLifetime.ItemModifierTimedLife.lifetime
            lifetime = None
            ml = mlm_wrapper.get("modifierLifetime", {}) if isinstance(mlm_wrapper, dict) else {}
            if isinstance(ml, dict):
                timed = ml.get("ItemModifierTimedLife")
                if isinstance(timed, dict):
                    lifetime = timed.get("lifetime")
            if lifetime is not None:
                mining_entry["Duration"] = safe_float(lifetime)
            modifiers_list.append(mining_entry)

        # 3. InertMaterialsFilter entry from MiningFilterItemModifierParams.filterParams.filterModifier
        mfip = modifiers.get("MiningFilterItemModifierParams", {})
        if isinstance(mfip, dict) and mfip:
            fp = mfip.get("filterParams", {})
            fm = fp.get("filterModifier", {}) if isinstance(fp, dict) else {}
            val = 0.0
            if isinstance(fm, dict):
                inner = fm.get("FloatModifierMultiplicative")
                if isinstance(inner, dict):
                    val = safe_float(inner.get("value", 0))
            modifiers_list.append({"InertMaterialsFilter": val})

        if modifiers_list:
            si["Module"] = {"Charges": charges, "Modifiers": modifiers_list}


def _build_tractor_beam(components):
    """Build TractorBeam from weapon firing modes (SWeaponActionFireTractorBeamParams)."""
    weapon = components.get("weapon", {})
    modes = weapon.get("firingModes", [])

    tractor_list = []
    towing_list = []

    for mode in modes:
        if mode.get("fireType") != "tractor":
            continue
        tractor_list.append({
            "Mode": mode.get("name", "TractorBeam"),
            "MinForce": safe_float(mode.get("minForce", 0)),
            "MaxForce": safe_float(mode.get("maxForce", 0)),
            "MinDistance": safe_float(mode.get("minDistance", 0)),
            "MaxDistance": safe_float(mode.get("maxDistance", 0)),
            "FullStrengthDistance": safe_float(mode.get("fullStrengthDistance", 0)),
            "MaxAngle": safe_float(mode.get("maxAngle", 0)),
            "MaxVolume": safe_float(mode.get("maxVolume", 0)),
        })
        # Towing params from the same fire-action's towingBeamParams (if present)
        towing = mode.get("towing") or {}
        if towing:
            towing_list.append({
                "TowingForce": safe_float(towing.get("towingForce", 0)),
                "TowingMaxAcceleration": safe_float(towing.get("towingMaxAcceleration", 0)),
                "TowingMaxDistance": safe_float(towing.get("towingMaxDistance", 0)),
                "QuantumTowMassLimit": safe_float(towing.get("quantumTowMassLimit", 0)),
            })

    # Even tractor items without towing data get a zero-filled Towing block
    if tractor_list and not towing_list:
        towing_list.append({
            "TowingForce": 0.0,
            "TowingMaxAcceleration": 0.0,
            "TowingMaxDistance": 0.0,
            "QuantumTowMassLimit": 0.0,
        })

    result = {}
    if tractor_list:
        result["Tractor"] = tractor_list
    if towing_list:
        result["Towing"] = towing_list

    return result if result else None


def _build_bomb(bomb):
    """Build Bomb from SCItemBombParams."""
    result = {}

    # Explosion damage — key may be PascalCase or camelCase
    exp = bomb.get("ExplosionParams", bomb.get("explosionParams", {}))
    if isinstance(exp, dict):
        damage = {}
        # Damage fields directly on ExplosionParams
        for src, dst in [("DamagePhysical", "Physical"), ("DamageEnergy", "Energy"),
                         ("DamageDistortion", "Distortion")]:
            val = safe_float(exp.get(src, 0))
            if val:
                damage[dst] = val
        # Fallback: nested damage/DamageInfo
        if not damage:
            di = exp.get("damage", {})
            if isinstance(di, dict):
                dinfo = di.get("DamageInfo", di)
                if isinstance(dinfo, dict):
                    for src, dst in [("DamagePhysical", "Physical"), ("DamageEnergy", "Energy")]:
                        val = safe_float(dinfo.get(src, 0))
                        if val:
                            damage[dst] = val

        explosion = {}
        if damage:
            explosion["Damage"] = damage
        radius = safe_float(exp.get("maxRadius", 0))
        if radius:
            explosion["Radius"] = radius
        proximity = safe_float(bomb.get("projectileProximity", 0))
        explosion["Proximity"] = proximity

        if explosion:
            result["Explosion"] = explosion

    arm = safe_float(bomb.get("armTime", 0))
    if arm:
        result["ArmTime"] = arm
    ignite = safe_float(bomb.get("igniteTime", 0))
    if ignite:
        result["IgniteTime"] = ignite

    return result if result else None


def _build_missile(m):
    """Build Missile from SCItemMissileParams data.

    Ref format: {Explosion: {Damage, MinRadius, MaxRadius, Proximity},
                 TrackingSignal, MinTrackingSignal, MinLockRatio, LockRate,
                 LockTime, LockAngle, LockRangeMin, LockRangeMax,
                 Speed, FuelTankSize, MaxLifeTime, MaxDistance,
                 ArmTime, IgniteTime, BoostPhaseDuration,
                 TerminalPhaseEngagementTime, TerminalPhaseEngagementAngle,
                 SafetyDistance}
    MaxDistance is computed as Speed * MaxLifeTime.
    """
    if not isinstance(m, dict):
        return None

    result = {}

    # Explosion
    dmg = m.get("explosionDamage")
    if isinstance(dmg, dict) and dmg:
        explosion = {"Damage": {k: safe_float(v) for k, v in dmg.items()}}
        explosion["MinRadius"] = safe_float(m.get("explosionMinRadius", 0))
        explosion["MaxRadius"] = safe_float(m.get("explosionMaxRadius", 0))
        explosion["Proximity"] = safe_float(m.get("projectileProximity", 0))
        result["Explosion"] = explosion

    signal = m.get("trackingSignalType", "")
    if signal:
        result["TrackingSignal"] = signal

    for src, dst in [("trackingSignalMin", "MinTrackingSignal"),
                     ("minRatioForLock", "MinLockRatio"),
                     ("lockIncreaseRate", "LockRate"),
                     ("lockTime", "LockTime"),
                     ("lockingAngle", "LockAngle"),
                     ("lockRangeMin", "LockRangeMin"),
                     ("lockRangeMax", "LockRangeMax")]:
        val = m.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    speed = safe_float(m.get("linearSpeed", 0))
    max_lifetime = safe_float(m.get("maxLifetime", 0))
    if speed:
        result["Speed"] = speed
    if m.get("fuelTankSize") is not None:
        result["FuelTankSize"] = safe_float(m.get("fuelTankSize"))
    if max_lifetime:
        result["MaxLifeTime"] = max_lifetime
    if speed and max_lifetime:
        result["MaxDistance"] = float(round(speed * max_lifetime))

    for src, dst in [("armTime", "ArmTime"),
                     ("igniteTime", "IgniteTime"),
                     ("boostPhaseDuration", "BoostPhaseDuration"),
                     ("terminalPhaseEngagementTime", "TerminalPhaseEngagementTime"),
                     ("terminalPhaseEngagementAngle", "TerminalPhaseEngagementAngle"),
                     ("explosionSafetyDistance", "SafetyDistance")]:
        val = m.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    return result if result else None


def _build_missiles_controller(mc):
    """Build MissilesController from SCItemMissileControllerParams."""
    return {
        "LockAngleAtMin": safe_float(mc.get("lockAngleAtMin", 0)),
        "LockAngleAtMax": safe_float(mc.get("lockAngleAtMax", 0)),
        "MaxArmedMissiles": safe_float(mc.get("maxArmedMissiles", 0)),
        "LaunchCooldownTime": safe_float(mc.get("launchCooldownTime", 0)),
    }


def _build_cargo_fields(si, rc, inv_comp, class_name, full_type, ctx):
    """Build CargoGrid and/or CargoContainers based on item type.

    - Ship mining pods (Container.Cargo + ResourceContainer, no inventory
      container): emit ONLY CargoContainers (including Collapsed at 0).
    - Ground mining pods (Container.Cargo + ResourceContainer + inventory
      container) and *_CargoGrid_Main: emit CargoGrid with Width derived
      from the InventoryContainer's interiorDimensions (x / 1.25).
    - Other Container/Cargo types with ResourceContainer: fall back to
      legacy CargoGrid+CargoContainers.
    """
    # Lookup inventory container dimensions via containerParams GUID
    container_guid = ""
    if isinstance(inv_comp, dict):
        container_guid = inv_comp.get("containerParams", "")
    container_data = ctx.inventory_containers.get(container_guid, {}) if ctx and container_guid else {}

    # Capacity can come from either ResourceContainer.SStandardCargoUnit or the inventory container
    capacity = 0.0
    if isinstance(rc, dict):
        cap = rc.get("capacity", {})
        scu = cap.get("SStandardCargoUnit", {}) if isinstance(cap, dict) else {}
        if isinstance(scu, dict):
            capacity = safe_float(scu.get("standardCargoUnits", 0))
    if not capacity and container_data:
        capacity = safe_float(container_data.get("capacity", 0))

    # Ship vs ground mining pods are distinguishable by component set.
    # Both are `Container.Cargo` + `ResourceContainer`; ground pods ALSO
    # carry `SCItemInventoryContainerComponentParams` so they dual-report
    # a grid shape for the player UI. The Container.Cargo gate keeps other
    # ResourceContainer items (e.g. Container.Medical healing canisters)
    # out of the mining-pod branches.
    is_cargo_type = full_type == "Container.Cargo"
    is_ship_mining = is_cargo_type and bool(rc) and not bool(inv_comp)
    is_ground_mining = is_cargo_type and bool(rc) and bool(inv_comp)
    is_cargo_grid_main = class_name.endswith("_CargoGrid_Main")

    if is_ship_mining:
        # Ship mining pods: only CargoContainers, include even when Capacity=0 (Collapsed).
        si["CargoContainers"] = {"Capacity": capacity}
        return

    if is_ground_mining:
        # Ground mining pods emit CargoGrid with Width only (Height/Depth = 0) plus CargoContainers.
        dim = container_data.get("interiorDimensions") if container_data else None
        width = 1.0
        if isinstance(dim, dict):
            dx = safe_float(dim.get("x", 0))
            if dx:
                width = float(int(dx / 1.25))
        if capacity:
            si["CargoGrid"] = {
                "Capacity": capacity,
                "Width": width,
                "Height": 0.0,
                "Depth": 0.0,
            }
            si["CargoContainers"] = {"Capacity": capacity}
        return

    # Other Container/Cargo items with inventory container data → full CargoGrid.
    if container_data:
        dim = container_data.get("interiorDimensions") or {}
        width = float(int(safe_float(dim.get("x", 0)) / 1.25)) if dim else 1.0
        depth = float(int(safe_float(dim.get("y", 0)) / 1.25)) if dim else 0.0
        height = float(int(safe_float(dim.get("z", 0)) / 1.25)) if dim else 0.0
        # TMBL_Cyclone_CargoGrid_Main is a 1x1x1 placeholder the ref catalogue
        # omits. Structurally it looks identical to `ARGO_CSV_CargoGrid_Rear`
        # and the destroyed-inventory box crates (all three are capacity=1
        # with 1.25^3 interior dimensions), so there's no generic structural
        # rule that catches exactly this one. Keep as last-resort className
        # exception — verify against ref if a similar placeholder surfaces.
        if class_name == "TMBL_Cyclone_CargoGrid_Main":
            return
        cargo_grid = {
            "Capacity": capacity,
            "Width": width,
            "Height": height,
            "Depth": depth,
        }
        min_size = container_data.get("minPermittedItemSize")
        max_size = container_data.get("maxPermittedItemSize")
        if isinstance(min_size, dict):
            mw = float(int(safe_float(min_size.get("x", 0)) / 1.25)) if min_size else 0.0
            md = float(int(safe_float(min_size.get("y", 0)) / 1.25)) if min_size else 0.0
            mh = float(int(safe_float(min_size.get("z", 0)) / 1.25)) if min_size else 0.0
            cargo_grid["MinContainerSize"] = {
                "Capacity": mw * md * mh or 1.0,
                "Width": mw, "Height": mh, "Depth": md,
            }
        if isinstance(max_size, dict):
            xw = float(int(safe_float(max_size.get("x", 0)) / 1.25)) if max_size else 0.0
            xd = float(int(safe_float(max_size.get("y", 0)) / 1.25)) if max_size else 0.0
            xh = float(int(safe_float(max_size.get("z", 0)) / 1.25)) if max_size else 0.0
            cargo_grid["MaxContainerSize"] = {
                "Capacity": xw * xd * xh or 1.0,
                "Width": xw, "Height": xh, "Depth": xd,
            }
        si["CargoGrid"] = cargo_grid
        return

    # Legacy fallback: ResourceContainer with no InventoryContainer data.
    if capacity:
        si["CargoGrid"] = {
            "Capacity": capacity,
            "Width": 1.0,
            "Height": 0.0,
            "Depth": 0.0,
        }
        si["CargoContainers"] = {"Capacity": capacity}
