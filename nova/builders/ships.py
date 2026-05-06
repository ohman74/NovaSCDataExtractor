"""Build ship data JSON with hardpoints, stats, and default loadout."""

import re

from ..utils import safe_float, safe_int, resolve_name
from ..vehicle_impl_parser import get_vehicle_impl_data

# Movement classes that indicate ground vehicles (case-insensitive)
_GROUND_MOVEMENT_CLASSES = {"arcadewheeled", "wheeled", "tracked"}

# ClassName infixes for NPC / mission / template variants that re-use the same
# record shape as a player ship. See `_is_ai_or_excluded_variant` below for why
# this is name-based rather than structural.
_AI_MISSION_PATTERNS = [
    "_PU_AI_", "_EA_AI_", "_Unmanned_", "_Template",
    "_S42_", "_AI_", "_NPC_", "_Dummy",
    "_Derelict_", "_Wreck", "_NoDebris",
    "_Hijacked", "_Boarded", "_Crewless",
    "_NoInterior", "_Drug_", "_Piano",
    "_Tutorial", "_FW22NFZ",
    "_GameMaster", "_Invictus", "_FW_25",
    "_Prison", "_Mission_",
    # Event paint / commemorative variants. The *_ShipShowdown / *_Showdown
    # 2949 BIS ships stay — those are still on the pledge store. Later-year
    # BIS paints (_BIS2950/2951/2024_Temp) and Fleetweek / year-stamped
    # CitizenCon skins aren't purchasable and duplicate their base ship.
    # Plain "_CitizenCon" (no year) is a genuine ship name (Valkyrie
    # Liberator Edition) — don't catch it.
    "_Fleetweek", "_BIS", "_CitizenCon2",
    # Scripted mission / faction variants.
    # _Advocacy: Advocacy-police NPC variants (e.g. ANVL_Valkyrie_Advocacy
    #   is byte-identical to base Valkyrie — loadout/paint applied at spawn).
    # _Indestructible: pinned-mission NPCs with SHealthComponentParams
    #   removed — can't be damaged, not a valid player ship.
    "_Advocacy", "_Indestructible",
]

# Explicit per-ClassName exclusions that don't fit a shared infix pattern
# AND are flagged `ReadyToInclude` by CIG (so `_is_not_included` doesn't
# catch them). Each entry has a one-line justification; revisit when CIG's
# inventory changes. Verified against the RSI ship-matrix
# (`py compare_matrix.py`).
_NOT_PLAYER_OWNABLE = frozenset({
    # Ships that aren't cosmetic twins of any sibling but still shouldn't
    # ship as player-flyable. Cosmetic/paint variants are identified
    # algorithmically by `_is_cosmetic_variant` — do NOT add those here.
    "ANVL_Lightning_F8",            # F8A military-spec; has no sibling base on the same impl (player owns F8C only).
    "ORIG_600i_Executive_Edition",  # Classifier says FUNCTIONAL (different landingSystem, inventoryContainer, Exec turret); retired SKU per product decision.
})


def _is_ground_vehicle(vehicle):
    """Return True if the vehicle record represents a ground vehicle."""
    movement = vehicle.get("movementClass", "").lower()
    is_grav = vehicle.get("isGravlevVehicle", False)
    return movement in _GROUND_MOVEMENT_CLASSES or is_grav


def _is_salvageable_debris(record):
    """Return True if the record is salvageable debris.

    Structural signal: `vehicle.movementClass == "Dummy"`. Debris records are
    static space-junk hulks spawned by the salvage missions; CIG flags them
    with the Dummy movement class rather than a real one. Verified against
    the full 920-record corpus: every `movementClass=="Dummy"` record is a
    SalvageableDebris and vice-versa.
    """
    return record.get("vehicle", {}).get("movementClass", "") == "Dummy"


def _is_placeholder_record(record):
    # Template / uninitialised vehicle record: vehicleName set to @LOC_UNINITIALIZED
    # or VehicleComponentParams.vehicleDefinition empty (no impl XML ref).
    # These two fields together catch pure templates (Spaceship_Template,
    # *_Template entries with empty impl ref) and unmanned placeholders where
    # the record is structurally incomplete.
    vehicle = record.get("vehicle", {})
    if vehicle.get("vehicleName") == "@LOC_UNINITIALIZED":
        return True
    if not vehicle.get("vehicleDefinition"):
        return True
    return False


def _is_not_included(class_name, ctx):
    # CIG's StaticEntityClassData/EAEntityDataParams.inclusionMode = "DoNotInclude"
    # marks a record as not-for-PU (WIP rebalances, retired variants). Strong
    # structural exclusion signal — complements the name-based AI/mission
    # filter but does not replace it (AI variants are usually ReadyToInclude
    # because they do ship in the PU build, just not as player-ownable).
    return ctx.inclusion_modes.get(class_name) == "DoNotInclude"


def _cosmetic_base(class_name, ctx):
    # Identified by nova.cosmetic_classifier: this record differs from
    # another ship sharing the same vehicleDefinition only in cosmetic
    # fields (palette, localization, interior art, paint ports, rename-only
    # modification blocks, or item-level cosmetic twins). Returns the base
    # ClassName the variant is a paint/skin duplicate of, or None.
    if isinstance(ctx.cosmetic_variants, dict):
        return ctx.cosmetic_variants.get(class_name)
    # Backwards-compat: if cosmetic_variants is a set, only "is or isn't"
    # is known — return a sentinel base of empty string when present.
    return "" if class_name in ctx.cosmetic_variants else None


def _has_seat_port(loadout):
    """Return True if any port in the loadout tree is a seat."""
    if not isinstance(loadout, list):
        return False
    for entry in loadout:
        if not isinstance(entry, dict):
            continue
        if "seat" in entry.get("portName", "").lower():
            return True
        if _has_seat_port(entry.get("children", [])):
            return True
    return False


def get_emitted_ship_classnames(ctx):
    """Return the set of vehicle ClassNames that pass all ship/vehicle filters.

    Used by `ship_equipment.py` to derive excluded-ship stems for filtering
    equipment that belongs only to non-emitted (NPC/non-flight-ready) ships.

    Cached on ctx after first call.
    """
    cached = getattr(ctx, "_emitted_ship_classnames", None)
    if cached is not None:
        return cached

    emitted = set()
    for class_name, record in ctx.vehicles.items():
        vehicle = record.get("vehicle", {})
        if not vehicle:
            continue
        if _is_salvageable_debris(record):
            continue
        if _is_placeholder_record(record):
            continue
        if _is_not_included(class_name, ctx):
            continue
        if _is_ai_or_excluded_variant(class_name):
            continue
        # Ships need a seat (player-pilotable). Ground vehicles don't need
        # this check because their builder doesn't apply it either.
        if not _is_ground_vehicle(vehicle):
            if _is_non_pilotable(record):
                continue
        emitted.add(class_name)

    ctx._emitted_ship_classnames = emitted
    return emitted


def _is_non_pilotable(record):
    """Return True if the vehicle record has no seat port in its default loadout.

    Static entities (orbital sentries, comms probes, mission-objective
    destructibles) and derelict hulls are coded as Vehicle_Spaceship but
    carry no pilot or driver seat, so players can't enter them. Real player
    vehicles always have at least one `hardpoint_seat_*` port in their
    defaultLoadout — verified across all 920 vehicle records: the only
    records missing any seat port are templates, derelicts, SalvageableDebris,
    orbital sentries, comms probes, and EAObjectiveDestructable entities.
    """
    loadout = record.get("components", {}).get("defaultLoadout", [])
    return not _has_seat_port(loadout)


def _is_ai_or_excluded_variant(class_name):
    """Return True if this is an AI / mission / template variant to exclude.

    Name-based by necessity. Audit on 2026-04-20 against 920 vehicle records in
    Game2.xml confirmed that AI, mission and template variants
    (`*_PU_AI_*`, `*_Boarded`, `*_Hijacked`, `*_AI_Template`, etc.) are
    structurally near-identical copies of their player base record: same
    component set, same VehicleComponentParams attribute shape, same
    SAttachableComponentParams.AttachDef, same defaultLoadout shape.
    The only discriminator inside the dataforge is the className suffix
    injected by mission designers. Shop / spawn references that would
    discriminate them live outside Game2.xml (ObjectContainers, mission XMLs).

    `_is_placeholder_record` handles the subset that DOES have a structural
    signal (templates with `@LOC_UNINITIALIZED` vehicleName or empty
    vehicleDefinition). This function handles the rest.
    """
    cn = class_name
    if cn in _NOT_PLAYER_OWNABLE:
        return True
    for pat in _AI_MISSION_PATTERNS:
        if pat in cn:
            return True

    # Apollo med-bed module-config sub-variants (`*_Tier_1/2/3`). These
    # share vehicleName, vehicleDefinition, and every structural field with
    # the Apollo_Medivac/Triage base — only the defaultLoadout differs
    # (which medical module ships are pre-installed). CIG's `_Tier_N`
    # ClassName suffix is the convention tag for this. Attempted structural
    # dedup (by shared vehicleName) but it over-matched legitimate sibling
    # Collector_*/Exec_* variants that happen to share vehicleName, so the
    # name tag stays as last-resort.
    if "_Tier_" in cn:
        return True

    # `*_Unmanned` suffix variants (Mantis, 890Jump, Spirit_C1, Nomad, Hull_C,
    # Zeus_ES, 600i). These are byte-for-byte copies of the base record —
    # same components, same attachDef, same vehicle fields, same loadout —
    # added by mission designers as a separate ClassName for scripted
    # `Unmanned` encounters. Verified against Game2.xml: no structural diff
    # separates them from the base. Name suffix stays as last-resort.
    if cn.endswith("_Unmanned"):
        return True

    return False


def build_ships(ctx):
    """Build the ships output dataset."""
    ships = []

    for class_name, record in ctx.vehicles.items():
        vehicle = record.get("vehicle", {})
        if not vehicle:
            continue
        if _is_salvageable_debris(record):
            continue
        if _is_placeholder_record(record):
            continue
        if _is_non_pilotable(record):
            continue
        if _is_not_included(class_name, ctx):
            continue
        if _is_ai_or_excluded_variant(class_name):
            continue
        ship = _build_ship(class_name, record, ctx)
        if ship:
            is_ground = _is_ground_vehicle(vehicle)
            ship["IsSpaceship"] = not is_ground
            if is_ground:
                ship["Type"] = "Gravlev" if vehicle.get("isGravlevVehicle", False) else "Vehicle"
            else:
                ship["Type"] = "Ship"
            # Tag cosmetic-only paint/livery variants. Shared vehicleDefinition
            # + structural diff confined to cosmetic fields (palette,
            # localization, paint ports, rename-only mods).
            base_cn = _cosmetic_base(class_name, ctx)
            if base_cn:
                ship["CosmeticVariant"] = True
                ship["CosmeticVariantOf"] = base_cn
            ships.append(ship)

    ships.sort(key=lambda s: s.get("Name", ""))
    print(f"  Built {len(ships)} ships")
    return ships


def _build_ship(class_name, record, ctx):
    """Build a single ship dict."""
    vehicle = record.get("vehicle", {})
    attach_def = record.get("attachDef", {})
    components = record.get("components", {})
    default_loadout = components.get("defaultLoadout", [])

    # Manufacturer
    mfr_guid = vehicle.get("manufacturerGuid", "") or attach_def.get("manufacturerGuid", "")
    mfr = ctx.get_manufacturer(mfr_guid)

    from .stditem import _clean_description
    import re as _re

    # Ship descriptions sometimes use "\n \n" (newline-space-newline) as a
    # separator between metadata and body instead of "\n\n". Normalize before
    # the metadata-stripping step in _clean_description.
    raw_desc = ctx.resolve_name(vehicle.get("vehicleDescription", ""))
    if "\\n" in raw_desc:
        raw_desc_tmp = raw_desc.replace("\\n", "\n")
        raw_desc_tmp = _re.sub(r"\n[ \t]+\n", "\n\n", raw_desc_tmp)
        raw_desc = raw_desc_tmp.replace("\n", "\\n")

    # Career/Role: use the in-game semantic fields directly.
    # vehicleCareer (@vehicle_focus_*) and vehicleRole (@vehicle_class_* or
    # @item_ShipFocus_*) are CIG's own classification — preferred over REF's
    # editorial taxonomy because they reflect what the vehicle actually does.
    career = ctx.resolve_name(vehicle.get("vehicleCareer", ""))
    role = ctx.resolve_name(vehicle.get("vehicleRole", ""))

    ship = {
        "ClassName": class_name,
        "Name": ctx.resolve_name(vehicle.get("vehicleName", class_name)),
        "Description": _clean_description(raw_desc),
        "Manufacturer": mfr.get("Name", "") if mfr else "",
        "Career": career,
        "Role": role,
        "Size": attach_def.get("size", 0),
        "Crew": vehicle.get("crewSize", 0),
    }

    # Dimensions from vehicle bounding box
    dims = vehicle.get("dimensions")
    if dims:
        ship["Dimensions"] = {
            "Length": dims.get("y", 0),
            "Width": dims.get("x", 0),
            "Height": dims.get("z", 0),
        }

    # Insurance
    insurance = record.get("insurance")
    if insurance:
        ship["Insurance"] = {
            "StandardClaimTime": round(insurance.get("baseWaitTimeMinutes", 0), 2),
            "ExpeditedClaimTime": round(insurance.get("mandatoryWaitTimeMinutes", 0), 2),
            "ExpeditedCost": insurance.get("baseExpeditingFee", 0),
        }

    # Vehicle implementation data (mass, port definitions)
    veh_def = vehicle.get("vehicleDefinition", "")
    impl = get_vehicle_impl_data(ctx.vehicle_impls, veh_def, class_name)

    # Compute storage from seat access inventory containers, plus interior
    # PersonalStorage placements walked from .socpak archives.
    storage_entries = _compute_storage(default_loadout, ctx, impl)
    interior_entries = _compute_interior_storage(class_name, ctx)
    if interior_entries:
        storage_entries.extend(interior_entries)
    if storage_entries:
        # Will be placed in Hardpoints.Components.Storage
        ship["_storage"] = storage_entries

    # Mass from vehicle implementation XML
    if impl and impl.get("mass"):
        ship["Mass"] = impl["mass"]

    # PortTags from vehicle impl's itemPortTags attribute (ref convention for entry_2)
    if impl and impl.get("itemPortTags"):
        ship["PortTags"] = impl["itemPortTags"].split()

    # Compute component mass from loadout
    if default_loadout:
        _, component_mass = _compute_mass(default_loadout, ctx)
        if component_mass > 0:
            ship["ComponentsMass"] = round(component_mass, 2)

    # Armor stats from armor item in loadout
    armor = _build_armor_stats(default_loadout, ctx)
    if armor:
        ship["Armor"] = armor

    # Hull structure HP from vehicle impl + vehicle record penetration
    hull = _build_hull_stats(default_loadout, ctx, impl, record)
    if hull:
        ship["Hull"] = hull

    # Cargo from cargo grid inventories in loadout (with by-name fallback)
    cargo = _build_cargo(default_loadout, ctx, class_name=class_name)
    if cargo:
        ship["Cargo"] = cargo

    # Flight characteristics from flight controller + thrusters
    flight = _build_flight_characteristics(default_loadout, ctx)
    if flight:
        ship["FlightCharacteristics"] = flight

    # FuelManagement from fuel tanks, intakes, and thrusters.
    # Wheeled/tracked ground vehicles use a different fuel system; reference
    # omits FuelManagement on them. Gravlev hoverbikes (Dragonfly, Nox, etc.)
    # do report FuelManagement in the reference, so keep emitting for those.
    is_pure_ground = _is_ground_vehicle(vehicle) and not vehicle.get("isGravlevVehicle", False)
    if not is_pure_ground:
        fuel = _build_fuel_management(default_loadout, ctx)
        if fuel:
            ship["FuelManagement"] = fuel

    # Ground vehicle dynamics (Steer/Drive/Track) from impl XML
    if impl and impl.get("groundDynamics"):
        gd = impl["groundDynamics"]
        if "physicalWheeled" in gd:
            ship["SteerCharacteristics"] = _build_steer_chars(gd["physicalWheeled"])
            ship["DriveCharacteristics"] = _build_drive_chars(gd.get("power"))
        if "trackWheeled" in gd:
            # Tank/tracked vehicles: one <TrackWheeled> element carries both
            # steering and engine fields, so we feed it to both helpers.
            ship["TrackSteerCharacteristics"] = _build_track_steer_chars(gd["trackWheeled"])
            ship["TrackWheeledCharacteristics"] = _build_track_wheeled_chars(gd["trackWheeled"])

    # Emissions (CrossSection from vehicle entity)
    emissions = _build_emissions(record)
    if emissions:
        ship["Emissions"] = emissions

    # ResourceNetwork (weapon pool size from entity XML)
    res_net = _build_ship_resource_network(class_name, ctx)
    if res_net:
        ship["ResourceNetwork"] = res_net

    # Build hardpoints from default loadout + port definitions from impl
    if default_loadout:
        impl_ports = impl.get("ports", []) if impl else []
        ship_components_ports = components.get("ports", []) or []
        ship_tags = (attach_def.get("tags", "") or "").split()
        ship["Hardpoints"] = _build_hardpoints(default_loadout, ctx, impl_ports,
                                                ship.pop("_storage", []),
                                                class_name=class_name,
                                                ship_components_ports=ship_components_ports,
                                                ship_tags=ship_tags)

    # BaseLoadout summary (computed from hardpoints)
    base_loadout = _build_base_loadout_summary(ship.get("Hardpoints", {}), ctx)
    if base_loadout:
        ship["BaseLoadout"] = base_loadout

    # WeaponCrew / OperationsCrew (computed from turret seat count)
    weapon_crew, ops_crew = _count_crew(default_loadout, ctx)
    ship["WeaponCrew"] = weapon_crew
    ship["OperationsCrew"] = ops_crew

    return ship


# ──────────────────────────────────────────────────────────────────────
# Ship-level stats builders
# ──────────────────────────────────────────────────────────────────────

def _build_armor_stats(loadout_entries, ctx):
    """Extract top-level Armor stats from the armor item in the ship's loadout."""
    # Find the armor item in the loadout structurally — any entry whose
    # resolved item has `attachDef.type == "Armor"`. 198 items in the
    # corpus carry this type, all 0 ARMR_-prefixed items without it.
    armor_record = None

    def _find_armor(entries):
        nonlocal armor_record
        for entry in entries:
            _, item = _resolve_entry(entry, ctx)
            if item and (item.get("attachDef", {}) or {}).get("type") == "Armor":
                armor_record = item
                return
            children = entry.get("children", [])
            if children:
                _find_armor(children)
                if armor_record:
                    return

    _find_armor(loadout_entries)

    if not armor_record:
        return None

    comps = armor_record.get("components", {})
    health_comp = comps.get("health", {})
    armor_comp = comps.get("armor", {})

    result = {}

    # Durability — health + damage resistance multipliers from SHealthComponentParams
    durability = {}
    if health_comp.get("health"):
        durability["Health"] = health_comp["health"]
    health_mults = health_comp.get("damageMultipliers", {})
    if health_mults:
        durability["DamageMultipliers"] = {
            "Physical": health_mults.get("physical", 1.0),
            "Energy": health_mults.get("energy", 1.0),
            "Distortion": health_mults.get("distortion", 1.0),
            "Thermal": health_mults.get("thermal", 1.0),
            "Biochemical": health_mults.get("biochemical", 1.0),
            "Stun": health_mults.get("stun", 1.0),
        }
    if durability:
        result["Durability"] = durability

    # DamageDeflection from SCItemVehicleArmorParams
    defl = armor_comp.get("damageDeflection", {})
    if defl:
        result["DamageDeflection"] = {
            "Physical": defl.get("physical", 0.0),
            "Energy": defl.get("energy", 0.0),
            "Distortion": defl.get("distortion", 0.0),
        }

    # DamageMultipliers from SCItemVehicleArmorParams (armor-level, separate from durability)
    armor_mults = armor_comp.get("damageMultipliers", {})
    if armor_mults:
        result["DamageMultipliers"] = {
            "Physical": armor_mults.get("physical", 1.0),
            "Energy": armor_mults.get("energy", 1.0),
            "Distortion": armor_mults.get("distortion", 1.0),
        }

    # SignalMultipliers from SCItemVehicleArmorParams
    sig = armor_comp.get("signalMultipliers", {})
    if sig:
        result["SignalMultipliers"] = {
            "Electromagnetic": sig.get("em", 1.0),
            "Infrared": sig.get("ir", 1.0),
            "CrossSection": sig.get("cs", 1.0),
        }

    return result if result else None


# Types whose BaseLoadout the reference emits without a Class field at all.
# Verified against entry_2.json: these are predominantly controllers and
# integrated/non-swappable mounts where no manufacturer Class applies.
_BASELOADOUT_CLASS_OMIT_TYPES = frozenset({
    "FlightController.UNDEFINED",
    "WheeledController.UNDEFINED",
    "Display.UNDEFINED",
    "Room.UNDEFINED",
    "ToolArm.UNDEFINED",
    "UtilityTurret.MannedTurret",
    "Turret.NoseMounted",
    "TurretBase.MannedTurret",
})

# MissileLauncher.MissileRack classNames whose BaseLoadout reference omits
# Class entirely. Most MRCK items get Class:"" but these 15 ship-specific
# racks (AEGS_Eclipse, ORIG_100i/125a/135c, RSI_Constellation_*, RSI_Scorpius,
# VNCL_Blade/Glaive/Scythe, MISC_Freelancer_MIS, MISC_Starfarer_Gemini) drop
# the field. No structural discriminator found in stditem data — hardcode.
_BASELOADOUT_CLASS_OMIT_TURRETS = frozenset({
    "ANVL_Asgard_Nose_Turret_S4",
    "ANVL_Terrapin_Nose_Turret_S3",
    "ANVL_Valkyrie_Nose_Turret_S3",
    "BEHR_PC2_Dual_S3",
    "BEHR_PC2_Dual_S4",
    "CNOU_Mustang_Nose_Turret_S3",
    "DRAK_Dual_S3",
    "Grin_MXC_Turret",
    "MISC_Starlancer_Dual_Gimbal",
    "MISC_Starlancer_TAC_Missile_Gimbal",
    "MISC_Starlancer_TAC_Missile_Gimbal_R",
    "ORIG_85X_Turret",
    "RSI_Lynx_Ball_Turret",
    "RSI_Ursa_Rover_SCItem_BallTurret",
    "TMBL_Storm_AA_Module",
    "UMNT_ANVL_S5_Rotodome_Mk2",
})

# Capital-ship integrated power plants where reference omits Class entirely.
# Same pattern as the missile-rack/turret omit lists — ship-specific items
# (POWR_AEGS_S04_Idris_SCItem, POWR_AEGS_S04_Reclaimer_SCItem) where the
# manufacturer-class lookup would emit "Civilian"/etc. but reference omits.
_BASELOADOUT_CLASS_OMIT_COMPONENTS = frozenset({
    # Capital-ship integrated components — REF omits Class entirely.
    "POWR_AEGS_S04_Idris_SCItem",
    "POWR_AEGS_S04_Reclaimer_SCItem",
    "RADR_GNRP_S03_Idris_TEMP",
    "RADR_RSI_S04_Polaris",
    "RADR_WLOP_S03_Lephari",
    "JDRV_ORIG_S04_890J_SCItem",
    "AEGS_Retaliator_Door_Cap_Front",
    # Ship-specific integrated turrets / racks / decorations
    "ANVL_Ballista_Remote_Rear_Turret",
    "ANVL_Centurion_S4_Turret",
    "GMRCK_S01_TMBL_Storm_AA_Custom",
    "GMRCK_S02_TMBL_Storm_AA_Custom",
    "MRAI_Guardian_Mohawk",
    "Mining_Laser_SHIN_Hofstede_S0",
})

_BASELOADOUT_CLASS_OMIT_MISSILERACKS = frozenset({
    "MRCK_S02_ORIG_100i_Dual_S02",
    "MRCK_S02_ORIG_125a_Quad_S02",
    "MRCK_S03_VNCL_Quad_S01",
    "MRCK_S03_VNCL_Quad_S01_Blade",
    "MRCK_S04_RSI_Constellation",
    "MRCK_S04_RSI_Scorpius",
    "MRCK_S04_RSI_Scorpius_bottom_right",
    "MRCK_S04_RSI_Scorpius_top_left",
    "MRCK_S04_RSI_Scorpius_top_right",
    "MRCK_S04_VNCL_Quad_S02",
    "MRCK_S05_MISC_Freelancer_MIS_Left",
    "MRCK_S05_MISC_Freelancer_MIS_Right",
    "MRCK_S05_RSI_Constellation",
    "MRCK_S06_MISC_Gemini",
    "MRCK_S09_AEGS_Eclipse",
})


def _omit_baseloadout_class(full_type):
    return full_type in _BASELOADOUT_CLASS_OMIT_TYPES


# CargoGrid item classNames where REF omits the Uneditable field.
# All 110 other CargoGrid items in REF emit Uneditable=True. Hardcoded
# because no derivable rule (size, capacity, port flags, ship-class) was
# found to discriminate this set. Verified consistent across all REF
# instances (each Name appears with the same Uneditable status).
_CARGOGRID_UNEDITABLE_OMIT = frozenset({
    "ARGO_MOTH_CargoGrid_Side",
    "ARGO_MOTH_CargoGrid_Side_Right",
    "CRUS_Intrepid_CargoGrid",
    "CRUS_Starlifter_CargoGrid_Small_A2",
    "ESPR_Prowler_Utility_CargoGrid_Main",
    "GAMA_Syulen_CargoGrid_Main",
    "GRIN_UTV_CargoGrid",
    "MISC_Fortune_CargoGrid_Secondary",
    "MISC_Fortune_CargoGrid_Main",
    "MISC_Starlancer_CargoGrid_Max",
    "RSI_Salvation_CargoGrid",
})


def _build_cargo_grid_items_by_name(class_name, ctx):
    """Name-prefix fallback for ships whose cargo grids aren't in the loadout.

    Matches CargoGrid items whose className starts with "<VehicleClassName>_CargoGrid".
    Used only when the loadout walk returns nothing — so we don't risk
    double-counting ships like the Reclaimer whose grids are already in
    the loadout.
    """
    prefix = class_name + "_CargoGrid"
    out = []
    for cn, item in ctx.items.items():
        if not cn.startswith(prefix):
            continue
        ad = item.get("attachDef", {})
        if ad.get("type") != "CargoGrid":
            continue
        emit_u = cn not in _CARGOGRID_UNEDITABLE_OMIT
        entry = _cargo_grid_entry_from_item(cn, item, ctx, emit_uneditable=emit_u)
        if entry:
            out.append(entry)
    out.sort(key=lambda x: x["Name"])
    return out


def _cargo_grid_entry_from_item(class_name, item, ctx, port_name=None,
                                  emit_uneditable=True):
    """Render a single CargoGrid InstalledItems entry from a resolved item record.

    Name: uses the item className when it contains "_CargoGrid_" (e.g.
    AEGS_Reclaimer_CargoGrid_Small). Falls back to the port name when the
    item is a generic plate (MISC_Hull_A_CargoPlate → hardpoint_cargoplate_*).

    `emit_uneditable=False` skips the Uneditable field — used by the
    by-name-prefix fallback path where reference omits the field.
    """
    ad = item.get("attachDef", {})
    comps = item.get("components", {})
    inv_comp = comps.get("SCItemInventoryContainerComponentParams", {})
    guid = inv_comp.get("containerParams", "") if isinstance(inv_comp, dict) else ""
    inv = ctx.inventory_containers.get(guid) if guid else None
    if not inv:
        return None

    def _grid_dims(d):
        if not isinstance(d, dict):
            return None
        return {
            "Width": float(int(safe_float(d.get("x", 0)) / 1.25)),
            "Height": float(int(safe_float(d.get("z", 0)) / 1.25)),
            "Depth": float(int(safe_float(d.get("y", 0)) / 1.25)),
        }

    def _container_size(d):
        dims = _grid_dims(d)
        if not dims:
            return None
        cap = float(dims["Width"] * dims["Height"] * dims["Depth"])
        return {"Capacity": cap, **dims}

    interior = inv.get("interiorDimensions") or {}
    grid_dims = _grid_dims(interior) or {"Width": 0, "Height": 0, "Depth": 0}
    grid_props = dict(grid_dims)
    min_size = _container_size(inv.get("minPermittedItemSize"))
    max_size = _container_size(inv.get("maxPermittedItemSize"))
    if min_size:
        grid_props["MinContainerSize"] = min_size
    if max_size:
        grid_props["MaxContainerSize"] = max_size

    name = class_name
    # Hull_A/B/C and similar ships that mount external cargoplates on
    # "hardpoint_cargoplate_*" / "hardpoint_cargo_strut_*" ports display
    # the port name instead of the grid item's className. Other ships
    # with grid items ending in _CargoGrid (e.g. Asgard) still use the
    # className.
    if port_name:
        low_pn = port_name.lower()
        if "cargoplate" in low_pn or "cargo_strut" in low_pn:
            name = port_name

    out = {
        "Name": name,
        "Mass": float((comps.get("physics") or {}).get("mass", 0)),
        "Size": ad.get("size", 0),
        "Grade": ad.get("grade", 0),
        "Capacity": float(inv.get("capacity", 0)),
        "GridProperties": grid_props,
    }
    if emit_uneditable:
        out["Uneditable"] = True
    return out


def _build_cargo_grid_items_from_loadout(loadout_entries, ctx):
    """Walk the loadout for CargoGrid items (one entry per installed port).

    Reference counts installed instances, not unique items: the Reclaimer has
    4 ports each installing "AEGS_Reclaimer_CargoGrid_Small" and
    "AEGS_Reclaimer_CargoGrid_Large", so 8 Small/Large entries plus 4
    Salvage entries = 12 InstalledItems.
    """
    out = []

    def _walk(entries, inherited_port=None):
        for entry in entries:
            entity_class, item = _resolve_entry(entry, ctx)
            # When walking into a CargoPlate bracket, its child grid uses
            # the outer plate's port name (Hull_A/B/C cargoplate pattern) —
            # reference shows the mount port, not the inner "Hardpoint_Cargo".
            pn = inherited_port or entry.get("portName")
            if item and item.get("attachDef", {}).get("type") == "CargoGrid":
                emit_u = entity_class not in _CARGOGRID_UNEDITABLE_OMIT
                rec = _cargo_grid_entry_from_item(
                    entity_class, item, ctx, port_name=pn,
                    emit_uneditable=emit_u,
                )
                if rec:
                    out.append(rec)
                    # If this entry produced a grid, its children are the
                    # grid sub-ports — skip them (ref doesn't double-emit).
                    continue
            is_plate = item and (
                "cargoplate" in (entity_class or "").lower()
                or "foldingstrut" in (entity_class or "").lower()
            )
            child_inherit = entry.get("portName") if is_plate else None
            for child in entry.get("children", []) or []:
                _walk([child], inherited_port=child_inherit)
            # Also descend into the installed item's own defaultLoadout to
            # surface CargoGrid items nested inside Module-style wrapper
            # items (e.g. base TMBL_Cyclone -> TMBL_Cyclone_Module_Cargo ->
            # TMBL_Cyclone_CargoGrid_Main). _compute_storage_scu already
            # walks this same chain for capacity totals; this surfaces the
            # individual CargoGrid entries as well.
            if item:
                item_default_loadout = (item.get("components", {}) or {}).get("defaultLoadout") or []
                if item_default_loadout:
                    _walk(item_default_loadout)

    _walk(loadout_entries)
    return out


def _build_weapon_rack_entry(port_name, item_record, port_def=None):
    """Reference uses a flat shape for WeaponsRacks: per-rack {Name, Size,
    Uneditable, Ports[]} where each port is {Name, MinSize, MaxSize, Uneditable}.
    No Loadout / BaseLoadout / Types — the rack item itself is just the
    container for the FPS weapon slots that hang off it.

    Uneditable on the rack itself mirrors the mounting port's uneditable flag.
    Reference shows False for ship-loadout-declared cabinets (Valkyrie,
    Vanguard Sentinel locker) and True for impl-defined ones. When no
    port_def is found, default to False.
    """
    if not item_record:
        return None
    ad = item_record.get("attachDef", {})
    sub_ports = item_record.get("components", {}).get("ports", []) or []
    # Filter out non-weapon-slot sub-ports: interactive button ports
    # only (IP_Button, hardpoint_btn_*). $proxy_weapon_* slots ARE
    # weapon mount ports (Hoplite locker, Spartan cabinet) — keep them.
    def _keep_port(p):
        nm = (p.get("name", "") or "").lower()
        if not nm:
            return False
        if nm == "ip_button" or nm.startswith("ip_button"):
            return False
        if nm.startswith("hardpoint_btn_") or nm.startswith("btn_"):
            return False
        return True
    out = {
        "Name": port_name,
        "Size": ad.get("size", 0),
        "Uneditable": bool(port_def and port_def.get("uneditable")),
        "Ports": [
            {
                "Name": p.get("name", ""),
                "MinSize": p.get("minSize", 0),
                "MaxSize": p.get("maxSize", 0),
                "Uneditable": bool(p.get("uneditable")),
            }
            for p in sub_ports if _keep_port(p)
        ],
    }
    return out


def _build_self_destruct_entry(item_record, ctx):
    """SelfDestruct uses a flat schema in the reference (no PortName/Loadout/
    BaseLoadout wrapper). Pulls Countdown/Damage/MinRadius/MaxRadius from
    SSCItemSelfDestructComponentParams on the equipped item.
    """
    if not item_record:
        return None
    comps = item_record.get("components", {})
    sd = comps.get("SSCItemSelfDestructComponentParams", {})
    if not isinstance(sd, dict) or not sd:
        return None
    ad = item_record.get("attachDef", {})
    name = ctx.resolve_name(ad.get("localization", {}).get("name", "")) if ad else ""
    if not name:
        # Fall back to item name; reference uses the localized display name.
        name = item_record.get("displayName") or ad.get("Name") or ""
    physics = comps.get("physics", {})
    return {
        "Name": name or "Self Destruct Unit",
        "Size": ad.get("size", 0),
        "Mass": float(physics.get("mass", 0)),
        "Grade": ad.get("grade", 0),
        "Uneditable": True,
        "Countdown": safe_float(sd.get("time", "0")),
        "Damage": safe_float(sd.get("damage", "0")),
        "MinRadius": safe_float(sd.get("minRadius", "0")),
        "MaxRadius": safe_float(sd.get("radius", "0")),
    }


def _build_steer_chars(pw):
    """SteerCharacteristics from <PhysicalWheeled> attributes.

    Reference key naming differs from the raw XML attribute naming. Mapping
    confirmed against ANVL_Ballista, ANVL_Centurion (V0SteerSpeed=100 maps
    to steerSpeedMin, etc.).
    """
    f = lambda k: safe_float(pw.get(k, "0"))
    return {
        "V0SteerSpeed": f("steerSpeedMin"),
        "VMaxSteerSpeed": f("steerSpeed"),
        "V0SteerMaxAngle": f("v0SteerMax"),
        "SteerSubtractV": f("vMaxSteerMax"),
        "SteerSubtractAngle": f("kvSteerMax"),
        "SteerRelaxationSpeed": f("steerRelaxation"),
    }


def _build_drive_chars(power):
    """DriveCharacteristics from <Power> attributes (arcade vehicles).

    Source verified on DRAK_Mule:
      Power.acceleration=8 → Acceleration
      Power.decceleration=12 → Decceleration  (typo preserved by reference)
      Power.topSpeed=32 → TopSpeed
      Power.reverseSpeed=7 → ReverseSpeed

    PhysicalWheeled vehicles (Ballista, Centurion) have no <Power> element;
    reference still emits zeros for them, so we do the same when power is
    absent.
    """
    if not power:
        return {"Acceleration": 0.0, "Decceleration": 0.0,
                "TopSpeed": 0.0, "ReverseSpeed": 0.0}
    f = lambda k: safe_float(power.get(k, "0"))
    return {
        "Acceleration": f("acceleration"),
        "Decceleration": f("decceleration"),
        "TopSpeed": f("topSpeed"),
        "ReverseSpeed": f("reverseSpeed"),
    }


def _build_track_steer_chars(pt):
    """TrackSteerCharacteristics from <PhysicalTracked>. Superset of
    SteerCharacteristics — reference duplicates the raw fields alongside the
    canonical-named ones."""
    f = lambda k: safe_float(pt.get(k, "0"))
    steer_speed = f("steerSpeed")
    steer_speed_min = f("steerSpeedMin")
    v0 = f("v0SteerMax")
    vmax = f("vMaxSteerMax")
    kv = f("kvSteerMax")
    return {
        "SteerSpeed": steer_speed,
        "SteerSpeedMin": steer_speed_min,
        "V0SteerMax": v0,
        "KvSteerMax": kv,
        "VMaxSteerMax": vmax,
        "VMaxSteerSpeed": steer_speed,
        "V0SteerSpeed": steer_speed_min,
        "V0SteerMaxAngle": v0,
        "SteerSubtractAngle": kv,
        "SteerSubtractV": vmax,
        "SteerRelaxationSpeed": f("steerRelaxation"),
    }


def _build_track_wheeled_chars(tw):
    """TrackWheeledCharacteristics from <TrackWheeled> on tank/tracked vehicles.

    Source confirmed against TMBL_Storm (enginePower=4700, maxSpeed=30) and
    TMBL_Nova (enginePower=1750, maxSpeed=25). All five fields come from
    the same <TrackWheeled> element using its native attribute names.
    """
    if not tw:
        return None
    f = lambda k: safe_float(tw.get(k, "0"))
    return {
        "EnginePower": f("enginePower"),
        "EngineMinRPM": f("engineMinRPM"),
        "EngineIdleRPM": f("engineIdleRPM"),
        "EngineMaxRPM": f("engineMaxRPM"),
        "MaxSpeed": f("maxSpeed"),
    }


def _build_emissions(record):
    """Extract Emissions (CrossSection) from vehicle entity's SSCSignatureSystemParams."""
    comps = record.get("components", {})
    sig_sys = comps.get("SSCSignatureSystemParams", {})
    radar_props = sig_sys.get("radarProperties", {}).get("SSCRadarContactProperites", {})
    cs_params = radar_props.get("crossSectionParams", {}).get(
        "SSCSignatureSystemManualCrossSectionParams", {}
    )
    cs = cs_params.get("crossSection", {})

    if not cs:
        return None

    # Cross-section axes: x=Side, y=Front, z=Top
    front = safe_float(cs.get("y", 0))
    side = safe_float(cs.get("x", 0))
    top = safe_float(cs.get("z", 0))

    if not (front or side or top):
        return None

    return {
        "Electromagnetic": {"SCMIdle": 0.0, "SCMActive": 0.0, "NAV": 0.0},
        "Infrared": {"Start": 0.0},
        "CrossSection": {
            "Front": front,
            "Side": side,
            "Top": top,
        },
    }


def _build_cargo(loadout_entries, ctx, class_name=None):
    """Compute Cargo SCU from cargo grid and storage inventories.

    Walks the ship's defaultLoadout, descending into each installed item's
    own defaultLoadout when present. This covers three patterns:

    1. Direct attachment — port installs a CargoGrid item directly via
       entityClassReference (GUID, e.g. RAFT) or entityClassName.
    2. CargoBay/Door indirection — port installs a wrapper item
       (Constellation CargoBay, Hammerhead cargo Door) whose own
       defaultLoadout, often coming from an external
       SItemPortLoadoutXMLParams.loadoutPath under
       cache/Data/Scripts/Loadouts/, attaches the cargo grid one level
       deeper.
    3. Storage capacity (any non-CargoGrid item with an
       SCItemInventoryContainerComponentParams) is summed separately.

    Classification is type-based only (`attachDef.type == "CargoGrid"`).
    A 0-ship audit confirmed every patch-current ship resolves through
    routes 1 or 2 — no className-prefix fallback is needed.
    """
    cargo_grid_scu = 0.0
    storage_scu = 0.0

    def _walk(entries):
        nonlocal cargo_grid_scu, storage_scu
        for entry in entries:
            entity_class, item_record = _resolve_entry(entry, ctx)
            item_default_loadout = []
            if item_record:
                ad = item_record.get("attachDef", {})
                item_type = ad.get("type", "")
                comps = item_record.get("components", {})
                inv_comp = comps.get("SCItemInventoryContainerComponentParams", {})
                if isinstance(inv_comp, dict):
                    container_guid = inv_comp.get("containerParams", "")
                    capacity = ctx.get_inventory_capacity(container_guid)
                    if capacity > 0:
                        if item_type == "CargoGrid":
                            cargo_grid_scu += capacity
                        else:
                            storage_scu += capacity
                # Descend into wrapper items' own defaultLoadout
                # (CargoBay/Door pattern).
                item_default_loadout = comps.get("defaultLoadout") or []
            children = entry.get("children", [])
            if children:
                _walk(children)
            if item_default_loadout:
                _walk(item_default_loadout)

    _walk(loadout_entries)

    return {
        "CargoGrid": round(cargo_grid_scu, 2),
        "CargoContainers": 0.0,
        "Storage": round(storage_scu, 2),
    }


def _build_hull_stats(loadout_entries, ctx, impl, record=None):
    """Build Hull stats from vehicle impl XML (structural part HP).

    Adds PenetrationDamageMultiplier from VehicleComponentParams and
    ThrustersHealthPoints + DoorsHealthPoints from loadout items.
    """
    if not impl:
        return None
    hull_hp = impl.get("hullHP")

    result = {}

    # PenetrationDamageMultiplier from the vehicle record
    if record:
        vp = record.get("vehicle", {})
        fuse = vp.get("fusePenetrationDamageMultiplier")
        comp = vp.get("componentPenetrationDamageMultiplier")
        if fuse is not None or comp is not None:
            result["PenetrationDamageMultiplier"] = {
                "Fuse": float(fuse if fuse is not None else 1.0),
                "Component": float(comp if comp is not None else 1.0),
            }

    if hull_hp:
        shp = {}
        if hull_hp.get("VitalParts"):
            shp["VitalParts"] = hull_hp["VitalParts"]
        if hull_hp.get("Parts"):
            shp["Parts"] = hull_hp["Parts"]
        if shp:
            result["StructureHealthPoints"] = shp

    # ThrustersHealthPoints + DoorsHealthPoints from loadout
    thrusters_hp = {"Main": {}, "Retro": {}, "Maneuvering": {}}
    doors_hp = {}

    def _walk(entries):
        for e in entries:
            pn = e.get("portName", "")
            pn_lower = pn.lower()
            cn = e.get("entityClassName", "")
            if cn:
                item = ctx.get_item(cn)
                if item:
                    health = item.get("components", {}).get("health", {})
                    hp = health.get("health") if isinstance(health, dict) else None
                    if hp:
                        # Strip hardpoint_ prefix for the key
                        key = pn[len("hardpoint_"):] if pn_lower.startswith("hardpoint_") else pn
                        # Classify thruster port: Main/Retro/Maneuvering/VTOL (or Door)
                        # Use the installed item's type (SCItemThrusterParams.thrusterType)
                        # when available; fall back to port name heuristics.
                        thruster_params = item.get("components", {}).get("SCItemThrusterParams", {})
                        thruster_type = ""
                        if isinstance(thruster_params, dict):
                            thruster_type = (thruster_params.get("thrusterType", "") or "").lower()

                        if thruster_type == "main" or ("engine" in pn_lower and "thruster" not in pn_lower):
                            thrusters_hp["Main"][key] = float(hp)
                        elif thruster_type == "retro" or "retro" in pn_lower:
                            thrusters_hp["Retro"][key] = float(hp)
                        elif thruster_type == "vtol" or "vtol" in pn_lower:
                            thrusters_hp.setdefault("VTOL", {})[key] = float(hp)
                        elif thruster_type == "maneuver" or ("thruster" in pn_lower and "vtol" not in pn_lower):
                            thrusters_hp["Maneuvering"][key] = float(hp)
                        elif pn_lower.startswith("hardpoint_door") or pn_lower.startswith("door_"):
                            doors_hp[key] = float(hp)
            for c in e.get("children", []):
                _walk([c])

    _walk(loadout_entries)

    # Remove empty sub-dicts
    thrusters_hp = {k: v for k, v in thrusters_hp.items() if v}
    if thrusters_hp:
        result["ThrustersHealthPoints"] = thrusters_hp
    if doors_hp:
        result["DoorsHealthPoints"] = doors_hp

    return result if result else None


# Shared thruster sub-classifier — port-name + className substring matching.
# `SCItemThrusterParams.thrusterType` is structurally present on every thruster
# but unreliable: Retaliator's `AEGS_Retaliator_Thruster_Retro` reports
# thrusterType="Maneuver", and VTOL thrusters report Maneuver or Main. CIG's
# editorial distinction Main/Retro/VTOL/Maneuvering is encoded only in
# port/class names. Verified 2026-05-05: trying to use thrusterType as the
# primary signal mis-routes 25+ ships' fuel-burn aggregates.
def _classify_thruster_role(port_name, class_name, vtol_label="VTOL"):
    """Return one of {Main, Retro, Maneuvering, <vtol_label>}.

    `vtol_label` is "VTOL" for FlightCharacteristics keys and "Vtol" for
    FuelManagement keys — only difference between the two historical helpers.
    """
    pn = (port_name or "").lower()
    cn = (class_name or "").lower()
    if "vtol" in pn or "_vtol" in cn:
        return vtol_label
    if "retro" in pn or "_retro" in cn:
        return "Retro"
    if any(x in pn for x in ("main_thruster", "thruster_main", "mainthruster", "engine")):
        return "Main"
    if "_main" in cn and "thruster" in cn:
        return "Main"
    return "Maneuvering"


def _build_flight_characteristics(loadout_entries, ctx):
    """Extract FlightCharacteristics from flight controller (IFCSParams) and thrusters."""
    ifcs = None
    qd_spool = 0.0
    thrust_by_type = {}  # Main/Retro/VTOL/Maneuvering -> total capacity
    has_vtol = False

    def _walk_loadout(entries):
        nonlocal ifcs, qd_spool, has_vtol
        for entry in entries:
            pn = entry.get("portName", "").lower()
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {})

                # Flight controller — IFCSParams component is 100% specific to
                # FlightController.UNDEFINED items (verified 2026-05-05).
                if "IFCSParams" in comps:
                    ifcs = comps["IFCSParams"]

                # Thrusters — aggregate by classified type
                if "SCItemThrusterParams" in comps:
                    tp = comps["SCItemThrusterParams"]
                    tc = safe_float(tp.get("thrustCapacity", "0"))
                    if tc:
                        tt = _classify_thruster_role(entry.get("portName", ""),
                                                      entity_class, vtol_label="VTOL")
                        thrust_by_type[tt] = thrust_by_type.get(tt, 0.0) + tc
                        if tt == "VTOL":
                            has_vtol = True

                # Quantum drive — quantumDrive component is 100% specific to
                # QuantumDrive.UNDEFINED items.
                if "quantumDrive" in comps:
                    qd = comps["quantumDrive"]
                    sj = qd.get("StandardJump", {}) if isinstance(qd, dict) else {}
                    if isinstance(sj, dict) and sj.get("SpoolUpTime") is not None:
                        qd_spool = safe_float(sj.get("SpoolUpTime"))
                    else:
                        qd_spool = safe_float(qd.get("spoolUpTime", 0))

            # Recurse into children
            children = entry.get("children", [])
            if children:
                _walk_loadout(children)

    _walk_loadout(loadout_entries)

    if not ifcs:
        return None

    result = {}

    # Basic speeds
    scm = safe_float(ifcs.get("scmSpeed", 0))
    max_speed = safe_float(ifcs.get("maxSpeed", 0))
    if scm:
        result["ScmSpeed"] = scm
    if max_speed:
        result["MaxSpeed"] = max_speed

    # Angular velocities — x=Pitch, y=Roll, z=Yaw (CryEngine coords)
    ang_vel = ifcs.get("maxAngularVelocity", {})
    if ang_vel:
        result["Pitch"] = safe_float(ang_vel.get("x", 0))
        result["Yaw"] = safe_float(ang_vel.get("z", 0))
        result["Roll"] = safe_float(ang_vel.get("y", 0))

    result["IsVtolAssisted"] = has_vtol

    # Thrust capacity aggregated by type. Reference keeps 1 decimal of precision
    # on the summed thrust totals (e.g. 5725176.4 N), so match that.
    if thrust_by_type:
        result["ThrustCapacity"] = {
            "Main": round(thrust_by_type.get("Main", 0.0), 1),
            "Retro": round(thrust_by_type.get("Retro", 0.0), 1),
            "Vtol": round(thrust_by_type.get("VTOL", 0.0), 1),
            "Maneuvering": round(thrust_by_type.get("Maneuvering", 0.0), 1),
        }

    # AccelerationG is curated external data (IsValidated/CheckDate) — skipped in compare.

    # MasterModes — BaseSpoolTime defaults to 1.0 (output convention).
    ifcs_core = ifcs.get("ifcsCoreParams", {})
    boost_fwd = safe_float(ifcs.get("boostSpeedForward", 0))
    boost_bwd = safe_float(ifcs.get("boostSpeedBackward", 0))
    master_modes = {}
    master_modes["BaseSpoolTime"] = 1.0
    if qd_spool:
        master_modes["QuantumDriveSpoolTime"] = qd_spool
    scm_mode = {}
    if boost_fwd:
        scm_mode["BoostSpeedForward"] = boost_fwd
    if boost_bwd:
        scm_mode["BoostSpeedBackward"] = boost_bwd
    if scm_mode:
        master_modes["ScmMode"] = scm_mode
    if master_modes:
        result["MasterModes"] = master_modes

    # Boost — from afterburner (old) block
    ab = ifcs.get("afterburner", {})
    if ab:
        boost = {}
        pre_delay = safe_float(ab.get("afterburnerPreDelayTime", 0))
        ramp_up = safe_float(ab.get("afterburnerRampUpTime", 0))
        ramp_down = safe_float(ab.get("afterburnerRampDownTime", 0))
        boost["PreDelay"] = pre_delay
        boost["RampUp"] = ramp_up
        boost["RampDown"] = ramp_down

        # Acceleration multipliers — x=Strafe, y=Forward, z=Up/Down
        pos = ab.get("afterburnAccelMultiplierPositive", {})
        neg = ab.get("afterburnAccelMultiplierNegative", {})
        if pos or neg:
            boost["AccelerationMultiplier"] = {
                "PositiveAxis": {
                    "X": safe_float(pos.get("x", 1)),
                    "Y": safe_float(pos.get("y", 1)),
                    "Z": safe_float(pos.get("z", 1)),
                },
                "NegativeAxis": {
                    "X": safe_float(neg.get("x", 1)),
                    "Y": safe_float(neg.get("y", 1)),
                    "Z": safe_float(neg.get("z", 1)),
                },
            }

        # Angular multipliers — x=Pitch, y=Roll, z=Yaw
        ang_accel = ab.get("afterburnAngAccelMultiplier", {})
        ang_vel_m = ab.get("afterburnAngVelocityMultiplier", {})
        if ang_accel:
            boost["AngularAccelerationMultiplier"] = {
                "Pitch": safe_float(ang_accel.get("x", 1)),
                "Yaw": safe_float(ang_accel.get("z", 1)),
                "Roll": safe_float(ang_accel.get("y", 1)),
            }
        if ang_vel_m:
            boost["AngularVelocityMultiplier"] = {
                "Pitch": safe_float(ang_vel_m.get("x", 1)),
                "Yaw": safe_float(ang_vel_m.get("z", 1)),
                "Roll": safe_float(ang_vel_m.get("y", 1)),
            }

        result["Boost"] = boost

    # Capacitors — from afterburner (old) block
    if ab:
        cap_max = safe_float(ab.get("capacitorMax", 0))
        cap_regen = safe_float(ab.get("capacitorRegenPerSec", 0))
        cap_idle = safe_float(ab.get("capacitorAfterburnerIdleCost", 0))
        cap_linear = safe_float(ab.get("capacitorAfterburnerLinearCost", 0))
        cap_usage = safe_float(ab.get("capacitorUsageModifier", 1))
        cap_delay = safe_float(ab.get("capacitorRegenDelayAfterUse", 0))

        capacitors = {
            "ThrusterCapacitorSize": cap_max,
            "CapacitorRegenPerSec": cap_regen,
            "CapacitorIdleCost": cap_idle,
            "CapacitorLinearCost": cap_linear,
            "CapacitorUsageModifier": cap_usage,
            "CapacitorRegenDelay": cap_delay,
        }
        if cap_max and cap_regen:
            capacitors["RegenerationTime"] = round(cap_max / cap_regen, 1)
        result["Capacitors"] = capacitors

    return result if result else None


def _build_fuel_management(loadout_entries, ctx):
    """Build FuelManagement from fuel tanks, intakes, and thruster burn rates."""
    fuel_capacity = 0.0
    quantum_fuel_capacity = 0.0
    fuel_intake_rate = 0.0
    burn_rates = {}  # type -> rate per thruster (raw SRU/Newton)
    thrust_caps = {}  # type -> total thrust capacity
    thruster_counts = {}  # type -> count

    def _classify_thruster_type(port_name, class_name):
        return _classify_thruster_role(port_name, class_name, vtol_label="Vtol")

    def _walk(entries):
        nonlocal fuel_capacity, quantum_fuel_capacity, fuel_intake_rate
        for entry in entries:
            pn = entry.get("portName", "").lower()
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {})
                ad = item_record.get("attachDef", {})
                item_type = ad.get("type", "")

                # Hydrogen fuel tanks (FuelTank type)
                if item_type == "FuelTank":
                    rc = comps.get("ResourceContainer", {})
                    if isinstance(rc, dict):
                        cap = rc.get("capacity", {})
                        if isinstance(cap, dict):
                            scu = cap.get("SStandardCargoUnit", {})
                            if isinstance(scu, dict):
                                fuel_capacity += safe_float(scu.get("standardCargoUnits", "0"))

                # Quantum fuel tanks (QuantumFuelTank type)
                if item_type == "QuantumFuelTank":
                    rc = comps.get("ResourceContainer", {})
                    if isinstance(rc, dict):
                        cap = rc.get("capacity", {})
                        if isinstance(cap, dict):
                            scu = cap.get("SStandardCargoUnit", {})
                            if isinstance(scu, dict):
                                quantum_fuel_capacity += safe_float(scu.get("standardCargoUnits", "0"))

                # Fuel intakes
                intake = comps.get("SCItemFuelIntakeParams", {})
                if isinstance(intake, dict) and intake.get("fuelPushRate"):
                    fuel_intake_rate += safe_float(intake["fuelPushRate"])

                # Thrusters — fuel burn rate and thrust
                thruster = comps.get("SCItemThrusterParams", {})
                if thruster:
                    tc = safe_float(thruster.get("thrustCapacity", "0"))
                    tt = _classify_thruster_type(entry.get("portName", ""), entity_class)
                    if tc:
                        thrust_caps[tt] = thrust_caps.get(tt, 0.0) + tc

                    rn = thruster.get("fuelBurnRatePer10KNewtonRN", {})
                    sru = rn.get("SStandardResourceUnit", {}) if isinstance(rn, dict) else {}
                    rate = safe_float(sru.get("standardResourceUnits", "0")) if isinstance(sru, dict) else 0
                    if rate and tt not in burn_rates:
                        burn_rates[tt] = rate
                    if tc:
                        thruster_counts[tt] = thruster_counts.get(tt, 0) + 1

            children = entry.get("children", [])
            if children:
                _walk(children)

    _walk(loadout_entries)

    if not fuel_capacity and not quantum_fuel_capacity:
        return None

    # Fuel capacity is in SCU units in ResourceContainer; multiply by 1,000,000 for game units
    result = {
        "FuelCapacity": fuel_capacity * 1000000.0,
        "FuelIntakeRate": fuel_intake_rate,
        "QuantumFuelCapacity": quantum_fuel_capacity * 1000000.0,
    }

    # Fuel burn rate per 10K Newton = rate_per_thruster * 1e6 * thruster_count
    result["FuelBurnRatePer10KNewton"] = {}
    for tt in ["Main", "Retro", "Vtol", "Maneuvering"]:
        rate = burn_rates.get(tt, 0.0)
        count = thruster_counts.get(tt, 0)
        result["FuelBurnRatePer10KNewton"][tt] = round(rate * 1e6 * count, 4) if rate else 0.0

    # Fuel usage per second = thrust capacity (N) * burn rate (SRU/N) * 100
    result["FuelUsagePerSecond"] = {
        "Main": float(round(thrust_caps.get("Main", 0) * burn_rates.get("Main", 0) * 100, 3)),
        "Retro": float(round(thrust_caps.get("Retro", 0) * burn_rates.get("Retro", 0) * 100, 3)),
        "Vtol": float(round(thrust_caps.get("Vtol", 0) * burn_rates.get("Vtol", 0) * 100, 3)),
        "Maneuvering": float(round(thrust_caps.get("Maneuvering", 0) * burn_rates.get("Maneuvering", 0) * 100, 3)),
    }

    # Intake to fuel ratio and time to fill
    main_usage = result["FuelUsagePerSecond"]["Main"]
    if fuel_intake_rate > 0 and main_usage > 0:
        result["IntakeToMainFuelRatio"] = round(fuel_intake_rate / main_usage * 100, 2)
        result["TimeForIntakesToFillTank"] = round(result["FuelCapacity"] / fuel_intake_rate, 2)
    else:
        result["IntakeToMainFuelRatio"] = 0.0
        result["TimeForIntakesToFillTank"] = "Infinity"

    return result


def _build_ship_resource_network(class_name, ctx):
    """Build ship-level ResourceNetwork (weapon pool size from entity XML).

    Emits even when WeaponPoolSize is 0 if the ship's entity XML actually
    declared a FixedPowerPool (entry exists in the parsed map). Reference
    behaviour: the Cyclone ground vehicles have explicit pool=0 records,
    so absence vs zero is meaningful.
    """
    cn_lower = class_name.lower()
    if cn_lower in ctx.weapon_pool_sizes:
        return {"ItemPools": {"WeaponPoolSize": float(ctx.weapon_pool_sizes[cn_lower])}}
    return None


def _count_crew(loadout_entries, ctx):
    """Count weapon crew and operations crew from turret seats."""
    weapon_crew = 0
    ops_crew = 0

    def _walk(entries):
        nonlocal weapon_crew, ops_crew
        for entry in entries:
            pn = entry.get("portName", "").lower()
            # Turret seats indicate weapon crew
            if "turret" in pn and ("seat" in pn or "seataccess" in pn):
                entity_class, _ = _resolve_entry(entry, ctx)
                if entity_class:
                    weapon_crew += 1
            elif "seat_operator" in pn or "engineering" in pn:
                entity_class, _ = _resolve_entry(entry, ctx)
                if entity_class:
                    ops_crew += 1
            children = entry.get("children", [])
            if children:
                _walk(children)

    _walk(loadout_entries)
    return weapon_crew, ops_crew


def _build_base_loadout_summary(hardpoints, ctx):
    """Build BaseLoadout summary stats (total shield HP, DPS, missile damage)."""
    total_shield_hp = 0.0
    pilot_burst_dps = 0.0
    turrets_burst_dps = 0.0
    total_missiles_dmg = 0.0

    # Shields
    shields = hardpoints.get("Components", {}).get("Systems", {}).get("Shields", {})
    for item in shields.get("InstalledItems", []):
        loadout = item.get("Loadout", "")
        if loadout:
            shield_item = ctx.get_item(loadout)
            if shield_item:
                sp = shield_item.get("components", {}).get("shield", {})
                total_shield_hp += safe_float(sp.get("maxShieldHealth", "0"))

    # Pilot weapons DPS
    pilot_weapons = hardpoints.get("Weapons", {}).get("PilotWeapons", {})
    for item in pilot_weapons.get("InstalledItems", []):
        dps = _compute_hardpoint_dps(item, ctx)
        pilot_burst_dps += dps

    # Turret DPS
    for turret_key in ["MannedTurrets", "RemoteTurrets", "PDCTurrets"]:
        turrets = hardpoints.get("Weapons", {}).get(turret_key, {})
        for item in turrets.get("InstalledItems", []):
            dps = _compute_hardpoint_dps(item, ctx)
            turrets_burst_dps += dps

    # Missile damage
    missile_racks = hardpoints.get("Weapons", {}).get("MissileRacks", {})
    for item in missile_racks.get("InstalledItems", []):
        dmg = _compute_missile_damage(item, ctx)
        total_missiles_dmg += dmg

    return {
        "TotalShieldHP": round(total_shield_hp, 1),
        "PilotBurstDPS": round(pilot_burst_dps, 1),
        "TurretsBurstDPS": round(turrets_burst_dps, 1),
        "TotalMissilesDmg": round(total_missiles_dmg, 1),
    }


def _compute_hardpoint_dps(hardpoint_entry, ctx):
    """Compute DPS for a single hardpoint (including sub-ports)."""
    total_dps = 0.0
    # Check sub-ports (e.g., gimbal -> weapon)
    for sub in hardpoint_entry.get("Ports", []):
        total_dps += _compute_hardpoint_dps(sub, ctx)
    if total_dps:
        return total_dps

    loadout = hardpoint_entry.get("Loadout", "")
    if not loadout:
        return 0.0
    item = ctx.get_item(loadout)
    if not item:
        return 0.0
    comps = item.get("components", {})
    weapon = comps.get("weapon", {})
    ammo_comp = comps.get("ammo", {})
    if not weapon.get("firingModes"):
        return 0.0

    fm = weapon["firingModes"][0]
    rpm = fm.get("fireRate", 0)
    pellets = fm.get("pelletCount", 1) or 1
    if not rpm:
        return 0.0

    ammo_guid = ammo_comp.get("ammoParamsRecord", "")
    ammo_data = ctx.get_ammo(ammo_guid)
    if not ammo_data or not ammo_data.get("damage"):
        return 0.0

    dmg = ammo_data["damage"]
    total_dmg_per_shot = sum(v for v in dmg.values() if isinstance(v, (int, float)))
    return total_dmg_per_shot * pellets * rpm / 60.0


def _compute_missile_damage(hardpoint_entry, ctx):
    """Compute total missile damage for a missile rack."""
    total = 0.0
    for sub in hardpoint_entry.get("Ports", []):
        loadout = sub.get("Loadout", "")
        if not loadout:
            continue
        item = ctx.get_item(loadout)
        if not item:
            continue
        missile = item.get("components", {}).get("missile", {})
        if missile:
            total += safe_float(missile.get("explosionDamage", 0))
    return total


# ──────────────────────────────────────────────────────────────────────
# Port classification rules
# ──────────────────────────────────────────────────────────────────────

# Port-def type strings (case-insensitive) that should never emit a loadout
# entry. Derived from the 10 374-port corpus: these are controllers, seats,
# doors, radar pings, animation rooms, AI module slots, regen pools, etc.
# Anything whose port type is exclusively one of these is skipped.
_SKIP_PORT_TYPES = frozenset({
    # Seats and seat accessors
    "seataccess", "seat", "seatdashboard",
    # Doors and door-related
    "door",
    # Controllers (decoration / UI / sub-systems with no gameplay hardpoint)
    "weaponcontroller", "doorcontroller", "lightcontroller", "energycontroller",
    "commscontroller", "coolercontroller", "shieldcontroller",
    "capacitorassignmentcontroller", "missilecontroller", "fuelcontroller",
    "salvagecontroller", "airtrafficcontroller", "miningcontroller",
    "targetselector",
    # note: wheeledcontroller is intentionally NOT skipped — reference emits it
    # under Controllers.Wheeled.InstalledItems for ground vehicles.
    # Animation / interior / structural shells
    "room", "interior", "crosssection", "attachedpart",
    # Helpers / ambient systems / avionics that aren't gameplay hardpoints
    "landingsystem", "ping", "scanner", "aimodule", "display", "light",
    "multilight", "battery", "computer", "controlpanel", "avionics",
    "dockinganimator", "dockingcollar", "gravitygenerator", "relay",
    "transponder", "noitem_vehicle",
    # Regen-pool slots expose power routing, not weapons
    "weaponregenpool",
})
# Note: `Misc` / `Misc.Misc` / `Usable` / `Useable` are intentionally NOT in
# the skip set. CIG uses Misc as a catch-all and spells Usable both ways; in
# all cases the name-based fallback below disambiguates. Skipping would drop
# legitimate entries whose impl XML gave no meaningful type.


def _has_descendant_type(entry, ctx, type_predicate, _visited=None):
    """Walk the loadout entry recursively, return True if any descendant
    item has an attachDef.type or inner-port type satisfying type_predicate.

    Walks two trees in parallel:
    - `entry.children` — the ship's loadout-tree children
    - `item.components.defaultLoadout` — wrapper items' own pre-attached
      loadouts (Cyclone Module_Cargo -> CargoGrid_Main pattern)

    Both are unbounded — we walk until the tree terminates. Cycle
    detection via visited item-GUIDs ensures termination on
    self-referential structures (rare but possible in CIG data).

    Used by `_classify_port` to find structural signals that aren't on
    the immediately-resolved item — e.g. a wrapper turret whose child
    ports host a TractorBeam item, possibly several layers deep.
    """
    if not entry or not ctx:
        return False
    if _visited is None:
        _visited = set()

    def _check_item_yields(item):
        """Yield True if the item itself or its inner ports have a
        type satisfying the predicate. Returns generator-friendly bool."""
        if not item:
            return False
        ad = item.get("attachDef", {}) or {}
        full = ad.get("type", "")
        if ad.get("subType"):
            full = full + "." + ad["subType"]
        if full and type_predicate(full):
            return True
        for p in (item.get("components", {}).get("ports") or []):
            if not isinstance(p, dict):
                continue
            for tt in (p.get("types") or []):
                if type_predicate(tt):
                    return True
        return False

    def _resolve_and_walk(node):
        """Resolve a loadout entry to its item and walk children +
        item-loadout. Cycle-protected via item GUID."""
        c_class, c_item = _resolve_entry(node, ctx)
        if c_item:
            guid = (c_item.get("guid") or "").lower()
            if guid and guid in _visited:
                return False
            if guid:
                _visited.add(guid)
            if _check_item_yields(c_item):
                return True
            # Walk the item's own defaultLoadout (Module-wrapper pattern)
            for sub in (c_item.get("components", {}).get("defaultLoadout") or []):
                if not isinstance(sub, dict):
                    continue
                if _resolve_and_walk(sub):
                    return True
        # Walk the loadout-tree children of this node
        for child in (node.get("children") or []):
            if not isinstance(child, dict):
                continue
            if _resolve_and_walk(child):
                return True
        return False

    return _resolve_and_walk(entry)


def _classify_port(port_name, item_type="", port_def=None, item_record=None,
                    pilot_claimed_tags=None, non_pilot_exclusive_tags=None,
                    dedicated_seat_tags=None,
                    entry=None, ctx=None):
    """Classify a loadout entry into its hardpoint category.

    Primary discriminator: port_def["types"] from the vehicle-impl XML — each
    entry is a structural `Type.SubType` string CIG assigns to the mount
    (e.g. `WeaponGun.Gun`, `Turret.GunTurret`, `Shield`, `Armor`). Secondary:
    the installed item's attachDef.type. Name-based matching is preserved
    only for the handful of categories with no single-type signal
    (Mining/Salvage/Utility/Storage/WeaponsRacks/Modules) — each such branch
    is clearly labelled below.

    Args:
        port_name: the loadout entry's portName (`hardpoint_*`).
        item_type: attachDef.type of the installed item, if any.
        port_def: vehicle-impl port definition dict (types, portTags, flags)
            for this port, or {} if no impl data is available.
        item_record: full item record, if resolved. Used for thruster sub-
            classification via SCItemThrusterParams.thrusterType.
        pilot_claimed_tags: set of ctrl_tags that the ship's pilot WC has
            ANY claim on (implicit broad, explicit numeric, or
            exclusive_control). When the port has a non-pilot ctrl_tag in
            this set, the port routes to PilotWeapons instead of
            RemoteTurrets — pilot fires it slaved when alone (Slaved+Remote
            dual mode). F7CM_Mk1/Mk2, Corsair chin, 85X, Spirit nose+wings,
            Constellation top/bottom guns all need this override.
    """
    pn = port_name.lower()
    it = (item_type or "").lower()
    port_def = port_def or {}
    types = [t.lower() for t in port_def.get("types", []) or []]
    port_tags = (port_def.get("portTags", "") or "").lower()

    # XML port operator-discriminator from impl XML <ControllerDef controllableTags="...">.
    # CIG tags identify which seat/console fires the weapon mounted at this
    # port. Pilot-firing tags vs everything-else (copilot, gunner, console,
    # remote_turret, etc.) cleanly separates PilotWeapons from RemoteTurrets
    # for ports with this metadata.
    ctrl_tag = (port_def.get("controllableTags", "") or "").strip()
    ctrl_lower = ctrl_tag.lower()
    PILOT_CTRL_TAGS = {
        "pilotseat", "pilot_seat", "weaponpilot", "pilotseat_weapons",
        "gunnose",  # ORIG ships' nose mount controlled by pilot
    }
    is_pilot_ctrl = ctrl_lower in PILOT_CTRL_TAGS

    item_cn = ""
    # Weapon-rack detection: a rack item exposes one or more sub-ports
    # typed `WeaponPersonal` (rifles/sidearms) — but NOT
    # `WeaponPersonal.Gadget` (extinguisher / gadget cabinets, which
    # also expose a WeaponPersonal port but for tools, not weapons).
    # Empty ports (no item installed) have no structural signal; fall
    # back to port-name match since CIG provides no other marker.
    if item_record:
        item_cn = (item_record.get("className", "") or "").lower()
        rack_ports = item_record.get("components", {}).get("ports", [])
        if isinstance(rack_ports, list) and any(
            isinstance(rp, dict) and any(
                t == "WeaponPersonal" or (t.startswith("WeaponPersonal.")
                                            and not t.endswith(".Gadget"))
                for t in (rp.get("types") or [])
            )
            for rp in rack_ports
        ):
            return "WeaponsRacks"
    elif "weapon_rack" in pn or "weaponlocker" in pn or "weapon_locker" in pn \
            or "weapon_cabinet" in pn:
        # Empty rack port — port-name is the only signal (port_def types
        # for these are typically Usable / Door, no rack-specific marker).
        return "WeaponsRacks"
    if item_record:
        # Decorative items at TurretBase/Turret ports — REF excludes these.
        # Three structural signals (in order):
        # 1. Inner port has DoorPart subtype — Idris turret-tail covers
        #    (`Door_Ship_Exterior_*_Turret_Cover`) install in TurretBase
        #    ports but their inner ports are DoorPart-typed. The item is
        #    a door assembly, not a turret.
        # 2. Item type is non-Turret (Misc / AttachedPart / Door) AND
        #    port is Turret-typed AND item has no inner ports with
        #    Turret/WeaponGun/WeaponMining/MissileLauncher types — the
        #    item is a cap / cover, not a real turret. Catches Misc
        #    Turret_Caps, Door_Caps, AttachedPart caps without needing
        #    className.
        # 3. Editorial fallback: REF excludes camera_turret / bomb_turret
        #    items even though they're structurally identical to real
        #    combat turrets (Turret.GunTurret + WeaponGun.Gun inner).
        #    CIG provides no structural distinguisher for these.
        item_inner_ports = item_record.get("components", {}).get("ports") or []
        has_doorpart = any(
            isinstance(p, dict) and any(
                ".doorpart" in t.lower() or t.lower().endswith("doorpart")
                for t in (p.get("types") or [])
            )
            for p in item_inner_ports
        )
        if has_doorpart:
            return None
        # Structural cap / cover detection: non-Turret type at Turret port
        # with no weapon-bearing inner ports.
        ad_full = ((item_record.get("attachDef", {}).get("type", "") or "")
                    + ("." + item_record.get("attachDef", {}).get("subType", "")
                       if item_record.get("attachDef", {}).get("subType") else ""))
        ad_full_lower = ad_full.lower()
        is_turret_port = any(t in ("turret", "turretbase")
                              or t.startswith("turret.") or t.startswith("turretbase.")
                              for t in types)
        is_non_turret_item = not (
            ad_full_lower.startswith("turret") or ad_full_lower.startswith("turretbase")
            or ad_full_lower.startswith("weapongun")
            or ad_full_lower.startswith("missilelauncher")
            or ad_full_lower.startswith("weaponmining")
        )
        has_weapon_inner = any(
            isinstance(p, dict) and any(
                tt.lower().startswith(("turret", "turretbase",
                                        "weapongun", "missilelauncher",
                                        "weaponmining", "weapondefensive"))
                for tt in (p.get("types") or [])
            )
            for p in item_inner_ports
        )
        if is_turret_port and is_non_turret_item and not has_weapon_inner:
            return None
        # Editorial fallback: REF excludes camera_turret / bomb_turret items
        # even though they pass all structural turret checks. CIG provides
        # no distinguisher.
        if ("camera_turret" in item_cn
                or "bomb_turret" in item_cn):
            return None
        # Mustang variant cargo "modules" (CNOU_Mustang_Cargo_Rack,
        # CNOU_Mustang_Beta_Cover_Back, etc.) and similar placeholder cargo
        # racks at cargo_module ports are decorative covers, not gameplay
        # cargo bays — reference omits them. Detection: Container.Cargo
        # item with "@LOC_PLACEHOLDER" name installed at a *_module port.
        ad = item_record.get("attachDef", {})
        ad_type = f"{ad.get('type','')}.{ad.get('subType','')}"
        # Misc.UNDEFINED placeholder items at weapon mount ports
        # (ORIG_30i_Weapon_Mount on hardpoint_weapon_mount of 300i/325a/350r)
        # are decorative anchors, not gameplay weapons — reference omits them.
        if (ad_type == "Misc.UNDEFINED"
                and ad.get("name", "") == "@LOC_PLACEHOLDER"
                and ("weapon_mount" in pn or "weapon_pilot" in pn)):
            return None
        if (ad_type == "Container.Cargo"
                and ad.get("name", "") == "@LOC_PLACEHOLDER"
                and ("_module" in pn or pn.endswith("module"))):
            return None

    # ── Structural skip: port types that never carry a gameplay hardpoint. ──
    # Skip only when *every* declared type on the port is in the skip set;
    # a port that also lists e.g. Turret.GunTurret should keep going.
    if types and all(t in _SKIP_PORT_TYPES for t in types):
        return None
    # `Usable` is the one genuinely ambiguous type: used for weapon racks,
    # weapon lockers, cockpit mounts, and some ground-vehicle cargo slots.
    # Don't decide based on type alone — let the name-based rules below
    # handle it (weapon_rack / cargogrid / storage patterns).

    # ── Structural primary rules (type allow-lists) ──
    # Order matters for ports carrying multiple types (gimballed guns list
    # both Turret.GunTurret and WeaponGun.Gun — WeaponGun wins).
    has_type = lambda prefix: any(t == prefix or t.startswith(prefix + ".") for t in types)

    # Pilot fire-group override: ports with defaultWeaponGroup are pilot-
    # controlled mounts. When the installed item is a Turret.* / WeaponGun.*,
    # route to PilotWeapons even though the port's type list may also
    # include Turret / QuantumInterdictionGenerator / Module (e.g. Hornet
    # F7A_Mk2 center mount: multi-typed but pilot-fired).
    # Exception: ports explicitly named *remote_turret* / *remoteturret* are
    # remote-operated even with defaultWeaponGroup (Cutlass Steel tail), so
    # they stay as RemoteTurrets (handled in the has_type("turret") branch).
    # Pilot-fire-group routing: when defaultWeaponGroup is set on the port,
    # the weapon mounted there is fired via that group. The actual operator
    # is decided by controllableTags — pilot tags route to PilotWeapons,
    # any other ctrl_tag (copilot, gunner, console, remote_*) routes RT.
    # Ports with dwg but no ctrl_tag default to PilotWeapons.
    is_remote_via_ctrl = bool(ctrl_tag) and not is_pilot_ctrl
    if port_def.get("defaultWeaponGroup") is not None and not is_remote_via_ctrl:
        it_lower = (item_type or "").lower()
        if it_lower.startswith("turret.") or it_lower.startswith("weapongun."):
            return "PilotWeapons"
        # Hornet F7C_Mk2/F7CR_Mk2/F7CS_Mk2 weapon_center: port has
        # defaultWeaponGroup AND types include Turret.BallTurret, but
        # the installed item is a Module (cargo door / rotodome / cap).
        # Reference routes by PORT pilot-fire intent, not item type.
        # Exception: MissileRack/BombRack/FuelIntake items keep their
        # type-driven routing even when port is pilot-typed.
        port_has_pilot_weapon_type = any(
            t.startswith("turret.") or t.startswith("weapongun.")
            for t in (types or [])
        )
        item_is_typed_elsewhere = it_lower in (
            "missilelauncher.missilerack", "bomblauncher.bombrack",
            "fuelintake.fuel",
        ) or it_lower.startswith("missilelauncher.") or it_lower.startswith("bomblauncher.")
        if port_has_pilot_weapon_type and not item_is_typed_elsewhere:
            return "PilotWeapons"

    # Weapons and weapon-like mounts. Missile/bomb racks that also carry a
    # WeaponGun.Rocket type must be matched BEFORE the WeaponGun branch
    # (bomb racks list both).
    # Item-type override: when the installed item is a MissileRack but the
    # port is typed Turret.GunTurret/WeaponGun.Gun (Fury_Miru variant
    # installs MissileRacks at gun-typed ports), route by item type.
    it_lower_for_override = (item_type or "").lower()
    if it_lower_for_override == "missilelauncher.missilerack":
        if "torpedo_storage" in pn or "missile_storage" in pn:
            return None
        return "MissileRacks"
    if it_lower_for_override == "bomblauncher.bombrack":
        return "BombRacks"
    if has_type("missilelauncher"):
        # Storage racks on capital ships (Perseus torpedo_storage_*) are
        # ammo holding bays — typed MissileLauncher but reference omits
        # them entirely (they're neither launchers nor cargo storage).
        if "torpedo_storage" in pn or "missile_storage" in pn:
            return None
        return "MissileRacks"
    if has_type("bomblauncher"):
        return "BombRacks"
    if has_type("weapongun"):
        # WeaponGun-typed ports route to PilotWeapons unless the port's
        # ctrl_tag signals a non-pilot operator (Spartan/Prowler use
        # remote_turret/copilot ctrl_tags). XML ctrl_tag is authoritative.
        if not is_remote_via_ctrl:
            return "PilotWeapons"
        # else: fall through to turret branch which routes RT
    if has_type("weapondefensive"):
        return "Countermeasures"
    if has_type("quantuminterdictiongenerator") or has_type("emp"):
        return "InterdictionHardpoints"

    # Turrets — after weapons so gimballed guns (Turret.GunTurret + WeaponGun)
    # are classified as PilotWeapons, not Turrets. `turretbase` covers
    # mount-style ports (TurretBase.MannedTurret / TurretBase.Unmanned)
    # whose dot-prefix doesn't match `has_type("turret")`. Module attach
    # ports (Cyclone hardpoint_module_attach) carry TurretBase.MannedTurret
    # alongside Container.CargoGrid — they're handled by the Modules branch
    # below, so exclude them here.
    if has_type("turret") or (has_type("turretbase") and "module" not in pn):
        # Tractor-mount detection — three structural signals (in order):
        # 1. Item's own inner port has TractorBeam type (most ships:
        #    Polaris/Spirit/Hull_B/RAFT/Reliant tractor turret items
        #    have inner `TractorBeam`).
        # 2. Port's controllableTags contains "tractor" (Hull_C uses
        #    `tractorSeat`, Caterpillar uses `TractorBeamLeftSeat`).
        # 3. Loadout-tree descendant has TractorBeam type — recursive
        #    structural walk catches future configurations where the
        #    tractor item is installed via the ship's loadout deeper
        #    than the wrapper item's own ports expose.
        # Last-resort: port-name "tractor" for empty / unfilled ports.
        item_cn_lower = ""
        item_inner = []
        if item_record:
            item_cn_lower = (item_record.get("className", "") or "").lower()
            item_inner = item_record.get("components", {}).get("ports") or []
        has_tractor_inner = any(
            isinstance(p, dict) and any(
                t.lower() == "tractorbeam" or t.lower().startswith("tractorbeam.")
                for t in (p.get("types") or [])
            )
            for p in item_inner
        )
        ctrl_has_tractor = "tractor" in (port_def.get("controllableTags", "") or "").lower()
        descendant_tractor = _has_descendant_type(
            entry, ctx,
            lambda t: t.lower() == "tractorbeam" or t.lower().startswith("tractorbeam."),
        )
        if has_tractor_inner or ctrl_has_tractor or descendant_tractor or "tractor" in pn:
            return "UtilityHardpoints"
        # Item-className filters: items meant as decorative / non-gameplay
        # mounts get routed away from the turret tree to match reference.
        # Camera_Turret items are sensor mounts the reference omits entirely.
        # Bomb_Turret items (Starlifter A2/M2) are likewise omitted by ref.
        # Door_<...>_Cover items at TurretBase ports are caught by the
        # has_doorpart structural check at the top of _classify_port.
        if item_cn_lower:
            if ("camera_turret" in item_cn_lower
                    or "bomb_turret" in item_cn_lower
                    or "_turret_cap" in item_cn_lower):
                return None
        # MannedTurret port type takes precedence — these are turret-base
        # mounts that always have a seated operator (their ctrl_tag points
        # to the manned seat, would otherwise misroute to RemoteTurrets).
        if any("turretbase.mannedturret" in t or t == "turretbase.mannedturret"
                for t in types):
            return "Turrets"  # MannedTurrets via placement
        # PDC detection — must come BEFORE the is_remote_via_ctrl branch
        # because PDC ports carry their own ctrl_tag (e.g. PDC_Turret_NN
        # on Idris/Polaris) once entity-level priority data is parsed.
        # Structural signals (in order):
        #   1. installed item's attachDef.subType == "PDCTurret" — the
        #      authoritative item-level signal (17/17 PDC items have it).
        #   2. portTags="PDC" — ship's impl-XML port-tag.
        # Fallback: port name "pdc"/"point_defense" for empty PDC ports
        # without explicit type/tag (older ships).
        if item_record:
            ad_sub = (item_record.get("attachDef", {}) or {}).get("subType", "")
            if ad_sub == "PDCTurret":
                return "PDCTurrets"
        if "pdc" in port_tags.split():
            return "PDCTurrets"
        if "pdc" in pn or "point_defense" in pn:
            return "PDCTurrets"
        # Remote-operated turrets: ctrl_tag identifies a non-pilot operator
        # (copilot, gunner, remote_turret, weaponSupport*, TurretConsole*).
        # XML ctrl_tag is the authoritative signal — replaces className /
        # port-name heuristics that previously did this routing.
        # gimbalMount item-tag override: items tagged `gimbalMount` are
        # pilot-controlled gimbal mounts even on ports with non-pilot
        # ctrl_tag. Starlancer_TAC missile gimbals install as
        # MISC_Starlancer_TAC_Missile_Gimbal (no inner Turret.X) at
        # ctrl=weaponCopilot ports → REF=PilotWeapons.
        # Prowler spine items also carry `gimbalMount` but their inner
        # ports are real combat turret slots (Turret.GunTurret) → REF=RT.
        # Gate on item having NO inner Turret.X type to distinguish.
        if item_record and "gimbalMount" in (item_record.get("attachDef", {}).get("tags", "") or ""):
            _gm_has_turret_inner = any(
                isinstance(p, dict) and any(
                    t.lower().startswith("turret.") or t.lower() == "turret"
                    for t in (p.get("types") or [])
                )
                for p in (item_record.get("components", {}).get("ports") or [])
            )
            if not _gm_has_turret_inner:
                return "PilotWeapons"
        # Slaved+Remote override: if the ship's pilot WC has a claim on this
        # port's ctrl_tag, the pilot fires it slaved when alone (gunner takes
        # over when seated). REF places these in PilotWeapons. Exception:
        # TurretBase.Unmanned ports stay RT regardless (Cutlass_Red).
        if is_remote_via_ctrl:
            # Slaved+Remote override: route to PilotWeapons iff pilot has
            # an effective claim on the tag.
            # Pilot's claim is OVERRIDDEN when the tag is "owned" by:
            # - A non-pilot WC's exclusive_control claim (Reclaimer console).
            # - A non-pilot WC's numeric same-tag claim (Shiv, Carrack,
            #   Starlifter A2 bridge).
            # - A dedicated SEAT port whose ctrl_tag matches the target
            #   port's ctrl_tag (Paladin remoteturret_left/right —
            #   hardpoint_seat_remoteturret_left has ctrl=Remote_Turret_Left).
            # TurretBase.Unmanned ports stay RT regardless (Cutlass_Red).
            tag_claimed_by_other = (
                (non_pilot_exclusive_tags and ctrl_tag in non_pilot_exclusive_tags)
                or (dedicated_seat_tags and ctrl_tag in dedicated_seat_tags)
            )
            pilot_claims = False
            if pilot_claimed_tags and not tag_claimed_by_other:
                if ctrl_tag in pilot_claimed_tags:
                    pilot_claims = True
                elif "*" in pilot_claimed_tags:
                    pilot_claims = True
            # dwg + non-real-turret-item bypass: when the port has dwg
            # (pilot fire-group routing) AND the installed item is NOT a
            # "real combat turret" (no inner port with `Turret.X` type),
            # apply one of two bypass paths:
            #   (a) pilot_broad — pilot WC has implicit-broad claim
            #       (Reliant Mako/Sen/Tana wing tip with copilot WC
            #       owning copilotSeat numerically — pilot's broad
            #       claim wins via dwg fire-group routing).
            #   (b) tag NOT owned by any non-pilot WC and not a
            #       dedicated seat — fall-through case for ships with
            #       no detected pilot WC at all (GRIN_MTC: pilot seat
            #       has numeric default WeaponController but no tag
            #       claim our parser captures).
            # Real combat turrets (Redeemer/Spirit/Scorpius/Reclaimer)
            # have inner turret_left/right typed Turret.GunTurret →
            # has_turret_inner=True → no bypass → stay RT.
            # Ground-vehicle turrets (Ballista/Centurion/Spartan) lack
            # inner Turret.X but the WC has numeric same-tag claim →
            # tag_claimed_by_other=True → blocks path (b) → stay RT.
            if (not pilot_claims
                and port_def.get("defaultWeaponGroup") is not None):
                has_turret_inner = False
                if item_record:
                    for p in (item_record.get("components", {}).get("ports") or []):
                        if not isinstance(p, dict):
                            continue
                        if any(t.lower().startswith("turret.") or t.lower() == "turret"
                                for t in (p.get("types") or [])):
                            has_turret_inner = True
                            break
                if not has_turret_inner:
                    if "*" in (pilot_claimed_tags or set()):
                        pilot_claims = True  # path (a)
                    elif not tag_claimed_by_other and not pilot_claimed_tags:
                        # path (b): pilot has NO detected claims at all
                        # AND tag isn't owned. Used for ships with no
                        # pilot WC info (GRIN_MTC: no impl XML, only
                        # numeric default WC operation by driver seat
                        # which our parser doesn't expose as a tag).
                        # NOT used when pilot has SOME claim (TMBL_Nova
                        # primary_turret has weapon_primary derived;
                        # pilot doesn't claim weapon_secondary so the
                        # secondary turret correctly stays RT).
                        pilot_claims = True
            if (pilot_claims
                and not any("turretbase.unmanned" in t for t in types)):
                return "PilotWeapons"
            return "RemoteTurrets"
        # Point Defense (PDC) turrets — small autonomous turrets on capitals.
        if "pdc" in pn or "point_defense" in pn:
            return "PDCTurrets"
        # Pilot-controlled mounts carry defaultWeaponGroup on the impl port
        # (assigns the mount to a fire group). Hornet's class-4 center/nose
        # and Mustang's weapon_nose are typed Turret.BallTurret but have a
        # defaultWeaponGroup, so reference classes them as PilotWeapons.
        # Exception: FuelIntake items installed at pilot-typed ports keep
        # their type-driven routing — MRAI_Pulse_LX hardpoint_weapon has
        # defaultWeaponGroup but installs a FuelIntake item which reference
        # excludes from weapons categories entirely.
        if port_def.get("defaultWeaponGroup") is not None:
            if it.startswith("fuelintake."):
                return None
            return "PilotWeapons"
        # gimbalMount tag on the installed item indicates a pilot-controlled
        # weapon mount even when the port has no defaultWeaponGroup
        # (Starlancer_TAC missile_turret_left/right install
        # MISC_Starlancer_TAC_Missile_Gimbal_*). Reference routes these to
        # PilotWeapons. The remote-turret name/className check above already
        # excluded the only RT exception (Prowler Remote_Turret_S5).
        if item_record:
            item_tags = item_record.get("attachDef", {}).get("tags", "") or ""
            if "gimbalMount" in item_tags:
                return "PilotWeapons"
        # Classify remaining turret-typed ports by the installed item's
        # full type. Reference's distribution is strongly type-dependent:
        # TurretBase.MannedTurret → MannedTurrets; TurretBase.Unmanned /
        # Turret.BottomTurret / Turret.MissileTurret / Turret.TopTurret →
        # RemoteTurrets; Turret.NoseMounted / Turret.CanardTurret /
        # Turret.BallTurret (mostly) / Turret.GunTurret without gimbal
        # defaultWeaponGroup are pilot-fired fixed mounts on single-seat
        # ships → PilotWeapons.
        ift = (item_type or "").lower()
        if ift.startswith("turretbase.manned"):
            return "Turrets"  # MannedTurrets via placement
        if ift in ("turretbase.unmanned", "turret.bottomturret",
                   "turret.missileturret", "turret.topturret"):
            return "RemoteTurrets"
        if ift in ("turret.canardturret", "turret.nosemounted",
                   "turret.ballturret"):
            return "PilotWeapons"
        return "Turrets"
    # UtilityTurret items (mining cab on MOLE / ROC, tractor on Hermes).
    # Sub-classify by the installed item's inner port type — the
    # structural signal CIG provides:
    #   inner WeaponMining.Gun -> MiningHardpoints (MOLE, ROC, Prospector)
    #   inner SalvageHead -> SalvageHardpoints (MOTH)
    #   inner TractorBeam -> handled by tractor branch above
    # Falls back to port-name "mining" for empty utility turret ports
    # where the installed item is missing.
    if has_type("utilityturret"):
        ut_inner = (item_record.get("components", {}).get("ports") if item_record else None) or []
        ut_has_mining = any(
            any((t or "").lower().startswith("weaponmining") for t in (p.get("types") or []))
            for p in ut_inner if isinstance(p, dict)
        )
        ut_has_salvage = any(
            any((t or "").lower() in ("salvagehead", "salvagefieldemitter")
                or (t or "").lower().startswith(("salvagehead.", "salvagefieldemitter."))
                for t in (p.get("types") or []))
            for p in ut_inner if isinstance(p, dict)
        )
        if ut_has_mining:
            return "MiningHardpoints"
        if ut_has_salvage:
            return "SalvageHardpoints"
        if "mining" in pn:
            return "MiningHardpoints"

    # Thrusters — primary signal is port type (MainThruster vs
    # ManneuverThruster), but VTOL isn't encoded as a distinct type; it's
    # on the installed item's SCItemThrusterParams.thrusterType. VTOL check
    # wins over the plain thruster-type categories.
    thruster_type_attr = ""
    if item_record:
        tp = item_record.get("components", {}).get("SCItemThrusterParams", {})
        if isinstance(tp, dict):
            thruster_type_attr = (tp.get("thrusterType", "") or "").lower()
    if has_type("mainthruster") or has_type("manneuverthruster"):
        # Installed item className carries the authoritative role for some
        # ships whose port name / thrusterType attribute don't match
        # reference's classification (Hornet F7C / Gladiator top_front use
        # items named "*_Thruster_Retro" but the item's thrusterType says
        # "Maneuver" and the port name has no "retro" substring).
        item_cls_lower = ""
        if item_record:
            item_cls_lower = (item_record.get("className", "") or "").lower()
        # Resolution order — port-name first, item-className second,
        # thrusterType last. The thrusterType field is unreliable
        # (verified 2026-05-05: Hull_A's _Thruster_VTOL items report
        # thrusterType="Retro" because CIG's data inconsistency; REF
        # picks VTOL via port-name).
        # Retro takes precedence over VTOL when both substrings appear
        # in the port name (DRAK_Golem hardpoint_vtol_retro_thruster_*).
        if "retro" in pn:
            return "RetroThrusters"
        if "vtol" in pn:
            return "VtolThrusters"
        if "_retro" in item_cls_lower or item_cls_lower.endswith("_retro"):
            return "RetroThrusters"
        if "_vtol" in item_cls_lower:
            return "VtolThrusters"
        if thruster_type_attr == "retro":
            return "RetroThrusters"
        if thruster_type_attr == "vtol":
            return "VtolThrusters"
        if has_type("mainthruster") or thruster_type_attr == "main":
            # Decorative pipe ports (KRIG L21/L22 hardpoint_main_thruster_pipes_*)
            # are cosmetic subsystems the reference omits.
            if "thruster_pipes" in pn or "_pipes" in pn:
                return None
            return "MainThrusters"
        return "ManeuveringThrusters"

    # Propulsion / systems / avionics — one-to-one type mapping.
    if has_type("powerplant"):
        return "PowerPlants"
    if has_type("cooler"):
        return "Coolers"
    if has_type("shield"):
        return "Shields"
    if has_type("quantumdrive"):
        return "QuantumDrives"
    if has_type("radar"):
        return "Radars"
    if has_type("lifesupportgenerator") or has_type("lifesupportsystem"):
        return "LifeSupport"
    if has_type("fuelintake"):
        return "FuelIntakes"
    if has_type("quantumfueltank"):
        return "QuantumFuelTanks"
    if has_type("fueltank"):
        return "HydrogenFuelTanks"
    if has_type("armor"):
        return "Armor"
    # Ground-vehicle drivetrain controller (Controller_Wheel on wheeled
    # craft like ANVL_Ballista, Cyclone, Mule). Reference places these
    # under Controllers.Wheeled.InstalledItems.
    if has_type("wheeledcontroller") or "controller_wheel" in pn:
        return "WheeledController"
    if has_type("cargogrid"):
        return "CargoGrids"
    if has_type("selfdestruct"):
        return "SelfDestruct"
    if has_type("flightcontroller"):
        return "FlightBlade"
    if has_type("paints"):
        return "Paints"
    if has_type("flair_cockpit") or has_type("flair_surface") or has_type("flair"):
        return "Flairs"

    # Salvage family — structural types are several variants.
    # (SalvageController is already in _SKIP_PORT_TYPES.)
    # Reference excludes SalvageFillerStation / SalvageInternalStorage /
    # SalvageFieldSupporter items entirely (internal salvage subsystems,
    # not gameplay hardpoints). Only include the salvage tool/turret types.
    it_lower = (item_type or "").lower()
    if it_lower.startswith(("salvagefillerstation.", "salvageinternalstorage.",
                            "salvagefieldsupporter.")) or it_lower in (
            "salvagefillerstation", "salvageinternalstorage",
            "salvagefieldsupporter"):
        return None
    if "salvagemount" in port_tags:
        return "SalvageHardpoints"
    # ToolArm items (mining/salvage arms): structural sub-classification
    # via the installed item's inner port type. Fall back to port-name
    # only for empty arm ports (e.g. ARGO_MPUV_Arm with generic Turret).
    if has_type("toolarm"):
        ta_inner = (item_record.get("components", {}).get("ports") if item_record else None) or []
        ta_has_mining = any(
            any((t or "").lower().startswith("weaponmining") for t in (p.get("types") or []))
            for p in ta_inner if isinstance(p, dict)
        )
        ta_has_salvage = any(
            any((t or "").lower() in ("salvagehead", "salvagefieldemitter")
                or (t or "").lower().startswith(("salvagehead.", "salvagefieldemitter."))
                for t in (p.get("types") or []))
            for p in ta_inner if isinstance(p, dict)
        )
        if ta_has_salvage:
            return "SalvageHardpoints"
        if ta_has_mining:
            return "MiningHardpoints"
        # Empty / utility-tractor arms: fall back to port-name
        if "salvage" in pn:
            return "SalvageHardpoints"
        if "mining" in pn:
            return "MiningHardpoints"

    # Module attach slots — swappable module bays on ships like the Cyclone
    # carry both TurretBase.MannedTurret and Container.CargoGrid; the port
    # name is the only discriminator against plain turret/cargo ports.
    # Check BEFORE Cargo/Container rules so module-attach doesn't get
    # misrouted into CargoGrids/Storage.
    if "module" in pn and (
        has_type("module") or has_type("turretbase")
        or has_type("cargo") or has_type("container")
    ):
        return "Modules"
    if has_type("module"):
        return "Modules"

    # `Cargo` / `Container.Cargo` / `Container.CargoGrid` — polymorphic: the
    # type alone doesn't distinguish cargo grids, mining pods, personal
    # storage, and module swaps. Dispatch on port name.
    if has_type("cargo") or has_type("container"):
        # "stored_pod" ports on the MOLE / Prospector are spare-pod slots
        # holding the collapsed-form item — reference omits them entirely.
        # Must come BEFORE the mining-pod check below, since
        # collapsed-form items still carry the ResourceContainer signal.
        if "stored_pod" in pn:
            return None
        # Mining ore pods (MOLE / Prospector / ROC / Golem / Hornet F7C):
        # the structural signal is `Container.Cargo + ResourceContainer`
        # component (verified 2026-05-05 across all 9 mining-pod items
        # vs 13 non-mining Container.Cargo items — 100% discriminator).
        # Falls back to port-name "mining_pod" / "ore_pod" / "pod+cargo"
        # for empty pod slots where no item is attached.
        item_full_type = ""
        item_has_resource = False
        if item_record:
            ad = item_record.get("attachDef", {}) or {}
            it_t = ad.get("type", "")
            it_st = ad.get("subType", "")
            item_full_type = f"{it_t}.{it_st}" if it_t and it_st else it_t
            item_has_resource = bool((item_record.get("components", {}) or {}).get("ResourceContainer"))
        if item_full_type == "Container.Cargo" and item_has_resource:
            return "CargoContainers"
        if "mining_pod" in pn or "ore_pod" in pn or ("pod" in pn and "cargo" in pn):
            return "CargoContainers"
        if "mining" in pn:
            return "MiningHardpoints"
        if "cargogrid" in pn or "cargo_grid" in pn:
            return "CargoGrids"
        return "Storage"

    # EMP weapons — `EMP` type is used for the Warlock and Raven EMP devices
    # that mount in pilot-weapon slots.
    if has_type("emp"):
        return "PilotWeapons"

    # Modules — Room mount for swappable interior rooms (Apollo, Retaliator).
    if has_type("room") and "module" in pn:
        return "Modules"

    # ── Secondary: installed-item attachDef.type allow-list ──
    # Fires when port_def has no types entry (e.g. port not in the impl XML,
    # or sub-ports discovered only via the loadout tree). Uses
    # `attachDef.type` exclusively — no port-name fallbacks.
    if "weapongun" in it:
        return "PilotWeapons"
    if "missilelauncher" in it:
        return "MissileRacks"
    if "bomblauncher" in it:
        return "BombRacks"
    if "weapondefensive" in it:
        return "Countermeasures"
    if "turret" in it:
        # Route by item's full type when port_def is unavailable (port not
        # in impl XML). Without port_def we have no ctrl_tag — fall back
        # to structural signals on the item itself, then className.
        ift = it
        item_cn_lower = (item_record.get("className", "") or "").lower() if item_record else ""
        # Structural RT signal: SCItemTurretParams.remoteTurret.
        # SCItemTurretRemoteParams.turretOnlyUsableInRemoteCamera="1"
        # marks turrets that can ONLY be operated via remote camera
        # (cannot be pilot-fired). Catches Centurion S4, Javelin Large,
        # Terrapin Support, Starlifter Bomb_Turret + others without
        # _remote_turret className. Matches all 79 _remote_turret items
        # that have the field, plus 10 more without RT className.
        item_only_remote = False
        if item_record:
            tp = (item_record.get("components", {}) or {}).get("SCItemTurretParams") or {}
            rt_params = (tp.get("remoteTurret") if isinstance(tp, dict) else None) or {}
            rt_inner = (rt_params.get("SCItemTurretRemoteParams")
                        if isinstance(rt_params, dict) else None) or {}
            if isinstance(rt_inner, dict) and rt_inner.get("turretOnlyUsableInRemoteCamera") == "1":
                item_only_remote = True
        if is_remote_via_ctrl or item_only_remote or (
                ("_remote" in item_cn_lower and "_turret" in item_cn_lower)
                or "_ai_turret" in item_cn_lower):
            return "RemoteTurrets"
        if ift.startswith("turretbase.manned"):
            return "Turrets"
        if ift in ("turretbase.unmanned", "turret.bottomturret",
                   "turret.missileturret", "turret.topturret"):
            return "RemoteTurrets"
        if ift in ("turret.canardturret", "turret.nosemounted",
                   "turret.ballturret", "turret.gunturret"):
            return "PilotWeapons"
        if ift in ("turret.pdcturret",):
            return "PDCTurrets"
        return "Turrets"
    if "shield" in it and "controller" not in it:
        return "Shields"
    if "powerplant" in it:
        return "PowerPlants"
    if "cooler" in it:
        return "Coolers"
    if "quantumdrive" in it:
        return "QuantumDrives"
    if "radar" in it:
        return "Radars"
    if "paints" in it:
        return "Paints"
    # Extended item-type fallback (covers categories the original block
    # missed — these previously went to the port-name fallback). The
    # presence of an SCItemThrusterParams component is the
    # authoritative thruster-role signal.
    if "fueltank.undefined" == it or it == "fueltank":
        return "HydrogenFuelTanks"
    if "quantumfueltank" in it:
        return "QuantumFuelTanks"
    if "fuelintake" in it:
        return "FuelIntakes"
    if it.startswith("armor.") or it == "armor":
        return "Armor"
    if "lifesupportgenerator" in it or "lifesupportsystem" in it:
        return "LifeSupport"
    if it.startswith("selfdestruct"):
        return "SelfDestruct"
    if "quantuminterdictiongenerator" in it or it == "emp" or it.startswith("emp."):
        return "InterdictionHardpoints"
    if it.startswith("flair_") or it == "flair":
        return "Flairs"
    if "wheeledcontroller" in it:
        return "WheeledController"
    if "flightcontroller" in it:
        return "FlightBlade"
    if "cargogrid" in it:
        return "CargoGrids"
    # Thruster routing — three signals: attachDef.type (parent class),
    # SCItemThrusterParams.thrusterType (Main/Maneuver/Retro), and
    # onlyActiveInVTOL flag (the VTOL discriminator).
    if "thruster" in it:
        thr_params = item_record.get("components", {}).get(
            "SCItemThrusterParams", {}) if item_record else {}
        if isinstance(thr_params, dict):
            only_vtol = thr_params.get("onlyActiveInVTOL", "")
            thr_role = (thr_params.get("thrusterType", "") or "").lower()
            if str(only_vtol) == "1":
                return "VtolThrusters"
            if thr_role == "retro":
                return "RetroThrusters"
            if thr_role == "main" or it.startswith("mainthruster"):
                return "MainThrusters"
        return "ManeuveringThrusters"

    # No classification possible — port-def types and item-type both
    # provided no signal, OR the entry resolved to a non-classifiable item.
    # Audit (2026-05-02, 262 ships, 5313 entries): no port that previously
    # returned via name-fallback contributes any entry to the final output —
    # name-fallback paths were dead code, removed.
    return None


# ──────────────────────────────────────────────────────────────────────
# Hardpoint tree builder
# ──────────────────────────────────────────────────────────────────────

def _empty_category():
    return {"InstalledItems": [], "Hardpoints": 0}


def _build_hardpoints(loadout_entries, ctx, impl_ports=None, storage_entries=None, class_name="",
                       ship_components_ports=None, ship_tags=None):
    """Build the structured Hardpoints tree matching the reference format.

    `ship_components_ports` are the ports declared on the ship entity itself
    (entity XML's components.ports — e.g. hardpoint_lifesupport, hardpoint_powerplant
    on capitals). They carry the ship-internal port flags ("invisible",
    "uneditable") that the impl XML doesn't.
    `ship_tags` are the ship's attachDef.tags. Reference attaches these to
    ship-internal ports' Tags field.
    """
    # Build port lookup from vehicle impl for minSize/maxSize/types.
    # Also capture the impl's structural port order; reference sorts InstalledItems
    # by impl XML order rather than defaultLoadout order.
    port_defs = {}
    port_order = {}
    ship_internal_ports = set()
    if impl_ports:
        _index_ports(impl_ports, port_defs, port_order)
    # Ship's own components.ports cover internal hardpoints (lifesupport,
    # capital-class powerplants, etc.) not present in the impl XML. Merge
    # without overriding impl entries.
    if ship_components_ports:
        for p in ship_components_ports:
            name = p.get("name", "")
            if name and name not in port_defs:
                port_defs[name] = p
            if name:
                ship_internal_ports.add(name)

    # Lowercase index for case-insensitive lookups. Loadouts sometimes
    # spell a port differently from the impl (e.g. MISC_Reliant impl's
    # Hardpoint_Thruster_LLF vs loadout's hardpoint_thruster_LLF).
    port_defs_lower = {k.lower(): v for k, v in port_defs.items()}

    # Precompute pilot-claimed tags. The pilot's WC may claim tags via:
    # (a) Explicit tag override (numeric or exclusive_control) — direct claim.
    # (b) Implicit broad claim (empty defaultPriority, no tag overrides) —
    #     covers ALL Turret/WeaponGun tags by default, EXCEPT tags "owned"
    #     by another non-pilot WC.
    # A tag is OWNED by a non-pilot WC iff:
    #   - That WC has exclusive_control on the tag (Reclaimer remote_01).
    #   - That WC has a numeric same-tag claim — claim tag matches the WC's
    #     own ctrl_tag (Carrack, Shiv, Starlifter A2 bridge_remote_turret).
    # Cross-tag numeric claims by non-pilot WCs do NOT own the tag — they're
    # secondary takeover paths (F7CM_Mk1 copilot has numeric=11 on
    # turret_center cross-tagged from copilot's ctrl=weapon_controller_copilot
    # — pilot's broad still applies).
    # Additionally, non-pilot WCs with NUMERIC defaultPriority on Turret/
    # WeaponGun are "broad gunners" — when present, ALL Turret/WeaponGun
    # tags effectively shift away from the pilot (Prowler copilot
    # default=50). Pilot's broad claim is suppressed globally on those
    # itemTypes.
    pilot_claimed_tags = set()
    pilot_broad = False
    non_pilot_exclusive_tags = set()
    non_pilot_broad_gunner = False
    # Tags owned by a "dedicated operator seat": any non-pilot SEAT port
    # whose ctrl_tag is also used as a port's ctrl_tag elsewhere. This
    # captures Paladin's hardpoint_seat_remoteturret_left/right pattern
    # (dedicated turret-station seats with their own ctrl_tag matching
    # the turret port). REF treats these as RT because the dedicated
    # seat is the primary operator. Distinct from the WC-claim path
    # because Paladin's seats carry the priority data directly.
    dedicated_seat_tags = set()
    # Pilot-derived WC tags: when a pilot seat (ctrl in PILOT_CTRL_TAGS)
    # has a UserDef WeaponController claim (exclusive or numeric) on
    # tag X, any WC port with ctrl=X is a "pilot's WC" — even if X
    # isn't in PILOT_CTRL_TAGS literally. Used for TMBL_Nova/Storm
    # (driver seat numerically claims `weapon_primary` WC) and
    # Starlancer_TAC missile turrets. Doesn't break Reclaimer because
    # WC's exclusive_control claims are recorded into
    # non_pilot_exclusive_tags regardless of who operates the WC.
    pilot_wc_ctrl_tags = set(_PILOT_CTRL_TAGS)
    for _pn, _pd in port_defs.items():
        if not isinstance(_pd, dict):
            continue
        if "Seat" not in (_pd.get("types") or []):
            continue
        _seat_ctrl_lower = (_pd.get("controllableTags") or "").strip().lower()
        if _seat_ctrl_lower not in _PILOT_CTRL_TAGS:
            continue
        for it_type, tag in _pd.get("exclusiveControl") or []:
            if it_type in ("WeaponController", "MissileController"):
                pilot_wc_ctrl_tags.add(tag.lower())
        for entry in _pd.get("controlledTags") or []:
            if entry[0] in ("WeaponController", "MissileController"):
                pilot_wc_ctrl_tags.add(entry[1].lower())
    _ITEM_TYPES = ("Turret", "WeaponGun", "TurretBase",
                    "MissileLauncher", "BombLauncher")
    _BROAD_GUNNER_ITEMTYPES = ("Turret", "WeaponGun", "TurretBase")
    for _pn, _pd in port_defs.items():
        if not isinstance(_pd, dict):
            continue
        _ctrl = (_pd.get("controllableTags") or "").strip()
        _ctrl_lower = _ctrl.lower()
        # WC is "pilot WC" if its ctrl_tag is in the PILOT_CTRL_TAGS
        # literal set OR derived via a pilot seat's WeaponController
        # claim (TMBL Nova/Storm pilot-seat numerically claims
        # weapon_primary WC).
        is_pilot_wc = _ctrl_lower in pilot_wc_ctrl_tags
        # Dedicated turret seat: a non-pilot SEAT port whose ctrl_tag is
        # itself used as a port's ctrl elsewhere (Paladin's
        # hardpoint_seat_remoteturret_left has ctrl=Remote_Turret_Left).
        # These seats own their tag. Skip pilot seats (pilot ctrl) here.
        if _ctrl and _ctrl_lower not in _PILOT_CTRL_TAGS:
            if "Seat" in (_pd.get("types") or []):
                dedicated_seat_tags.add(_ctrl)
        # WC port claims. Two-axis:
        #   1. exclusive_control claims always add to non_pilot_exclusive_tags
        #      — the WC port structurally OWNS the tag. This holds even when
        #      the pilot operates the WC (Reclaimer remote_01 is
        #      pilot-derived but exclusive-controls TurretConsole01_turret;
        #      REF still routes the turret to RT).
        #   2. If the WC is pilot-operated (literal or derived), also add
        #      tag claims to pilot_claimed_tags so the pilot-claim path
        #      knows pilot can fire it.
        is_wc_port = any("WeaponController" in t for t in (_pd.get("types") or []))
        for it_type, tag in _pd.get("exclusiveControl") or []:
            if it_type not in _ITEM_TYPES:
                continue
            if is_wc_port:
                non_pilot_exclusive_tags.add(tag)
            if is_pilot_wc:
                pilot_claimed_tags.add(tag)
        for entry in _pd.get("controlledTags") or []:
            it_type, tag = entry[0], entry[1]
            if it_type not in _ITEM_TYPES:
                continue
            # Numeric same-tag claim by any WC port → tag is owned by the
            # WC structurally. This holds even when pilot operates the WC
            # (Ballista driver-seat operates remote_turret WC; the WC's
            # same-tag numeric claim still marks remote_turret as owned →
            # REF routes the turret to RT).
            if is_wc_port and tag == _ctrl:
                non_pilot_exclusive_tags.add(tag)
            if is_pilot_wc:
                pilot_claimed_tags.add(tag)
        # Broad-gunner detection: non-pilot WC with numeric default on a
        # weapon-related itemType.
        if (not is_pilot_wc
                and any("WeaponController" in t for t in (_pd.get("types") or []))):
            for it_type, dp in (_pd.get("defaultPriorities") or {}).items():
                if it_type not in _BROAD_GUNNER_ITEMTYPES:
                    continue
                if dp in ("", "no_control", "exclusive_control", "observe_only"):
                    continue
                # Numeric default → broad gunner role on this itemType.
                non_pilot_broad_gunner = True
                break
        # Implicit broad detection on PILOT WCs: empty default + no tag
        # claims means pilot covers everything by default.
        if is_pilot_wc and any("WeaponController" in t for t in (_pd.get("types") or [])):
            has_turret_claim = any(
                it in ("Turret", "WeaponGun")
                for it, _ in (_pd.get("exclusiveControl") or [])
            ) or any(
                e[0] in ("Turret", "WeaponGun")
                for e in (_pd.get("controlledTags") or [])
            )
            if not has_turret_claim:
                pilot_broad = True
    if pilot_broad and not non_pilot_broad_gunner:
        # Pilot's broad implicit claim — covers any tag NOT owned by another
        # non-pilot WC. Suppressed entirely if a non-pilot broad gunner
        # exists (Prowler), because that gunner is the primary operator.
        pilot_claimed_tags.add("*")
    if non_pilot_broad_gunner:
        # Prowler-style: copilot WC has a numeric default on Turret/WeaponGun
        # (broad gunner). REF treats the gunner as the primary operator and
        # places weapon ports in RemoteTurrets even when the pilot has
        # explicit numeric claims on specific tags. Drop pilot's claims so
        # the override at the classifier doesn't fire.
        pilot_claimed_tags.clear()

    if port_order:
        # Sort loadout entries by their impl-XML position. Entries with no impl
        # port (rare — usually fully synthesised loadout-only ports) stay
        # appended after the impl-defined ones, in their original order.
        # Case-insensitive lookup: loadouts sometimes spell the port in a
        # different case from the impl (Reliant: impl Hardpoint_Thruster_*,
        # loadout hardpoint_thruster_*).
        port_order_lower = {k.lower(): v for k, v in port_order.items()}
        _end = len(port_order) + 1

        def _order_key(e):
            pn = e.get("portName", "")
            if pn in port_order:
                return port_order[pn]
            return port_order_lower.get(pn.lower(), _end)

        loadout_entries = sorted(loadout_entries, key=_order_key)

    tree = {
        "Weapons": {
            "PilotWeapons": _empty_category(),
            "MannedTurrets": _empty_category(),
            "RemoteTurrets": _empty_category(),
            "PDCTurrets": _empty_category(),
            "MissileRacks": _empty_category(),
            "BombRacks": _empty_category(),
            "InterdictionHardpoints": _empty_category(),
            "MiningHardpoints": _empty_category(),
            "SalvageHardpoints": _empty_category(),
            "UtilityHardpoints": _empty_category(),
            "UtilityTurrets": _empty_category(),
        },
        "Components": {
            "Propulsion": {
                "PowerPlants": _empty_category(),
                "QuantumDrives": _empty_category(),
                "Thrusters": {
                    "MainThrusters": {"InstalledItems": [], "ItemsQuantity": 0},
                    "RetroThrusters": {"InstalledItems": [], "ItemsQuantity": 0},
                    "VtolThrusters": {"ItemsQuantity": 0},
                    "ManeuveringThrusters": {"InstalledItems": [], "ItemsQuantity": 0},
                },
                "QuantumFuelTanks": {"InstalledItems": [], "ItemsQuantity": 0},
                "HydrogenFuelTanks": {"InstalledItems": [], "ItemsQuantity": 0},
            },
            "Systems": {
                "Controllers": {},
                "Shields": _empty_category(),
                "Coolers": _empty_category(),
                "LifeSupport": {"InstalledItems": []},
                "FuelIntakes": {"InstalledItems": [], "ItemsQuantity": 0},
                "Countermeasures": {"InstalledItems": [], "ItemsQuantity": 0},
            },
            "Avionics": {
                "FlightBlade": {"InstalledItems": []},
                "Radars": {"InstalledItems": [], "ItemsQuantity": 0},
                "SelfDestruct": {"InstalledItems": [], "ItemsQuantity": 0},
            },
            "Modules": _empty_category(),
            "CargoGrids": {"InstalledItems": [], "ItemsQuantity": 0},
            "CargoContainers": {"InstalledItems": [], "ItemsQuantity": 0},
            "Storage": {"InstalledItems": [], "ItemsQuantity": 0},
            "WeaponsRacks": {"InstalledItems": [], "ItemsQuantity": 0},
            "Paints": _empty_category(),
            "Flairs": _empty_category(),
        },
    }

    # Promote weapon-bearing children of AttachedPart wing-tip items
    # (Merlin/Archimedes hardpoint_wing_left/right) to the top-level
    # loadout list before classifying. The wing item itself doesn't
    # classify (AttachedPart isn't a hardpoint category) but its child
    # weapon mount IS a top-level PilotWeapons hardpoint per reference.
    extra_promoted = []
    for _e in loadout_entries:
        _ec, _ir = _resolve_entry(_e, ctx)
        if not _ir:
            continue
        _ad = _ir.get("attachDef", {})
        if _ad.get("type") == "AttachedPart":
            for _c in _e.get("children", []) or []:
                if _c.get("entityClassName") or _c.get("entityClassReference"):
                    extra_promoted.append(_c)
    if extra_promoted:
        loadout_entries = list(loadout_entries) + extra_promoted

    for entry in loadout_entries:
        port_name = entry.get("portName", "")
        if not port_name:
            continue

        entity_class, item_record = _resolve_entry(entry, ctx)

        # Skip entries with no resolved entity and no installable children,
        # UNLESS the impl XML defines a pilot-weapon port at this location
        # (Hornet F7C_*/Mk2 class_4_nose, Mustang wing_*, Terrapin weapon_nose).
        # Reference emits empty mount slots with MinSize/MaxSize/Types/Flags
        # for pilot-weapon ports (WeaponGun.* or Turret.*) that have no
        # loadout item, but NOT for missile-launcher / bomb-launcher slots
        # (those are racks; an empty rack is omitted entirely).
        raw_children = entry.get("children", [])
        if not entity_class and not any(
            c.get("entityClassName") or c.get("entityClassReference")
            for c in raw_children
        ):
            _pd = port_defs.get(port_name) or port_defs_lower.get(port_name.lower()) or {}
            _pd_types = [t.lower() for t in _pd.get("types", []) or []]
            is_pilot_weapon_slot = any(
                t.startswith("weapongun") or t.startswith("turret") or
                t.startswith("turretbase")
                for t in _pd_types
            )
            if not is_pilot_weapon_slot:
                continue

        item_type = ""
        if item_record:
            ad = item_record.get("attachDef", {})
            t = ad.get("type", "")
            st = ad.get("subType", "")
            # Compose full "Type.SubType" — classifier needs the subtype
            # for fine-grained routing (Turret.CanardTurret vs Turret.BallTurret).
            item_type = f"{t}.{st}" if t and st else t

        # Port definition from vehicle impl — carries the structural `types`
        # list the classifier keys on. Match case-insensitively: the loadout
        # sometimes spells the port differently from the impl XML (MISC_Reliant
        # impl has Hardpoint_Thruster_LLF but the loadout has
        # hardpoint_thruster_LLF).
        port_def = port_defs.get(port_name) or port_defs_lower.get(port_name.lower()) or {}
        # Use the impl port's canonical casing for the emitted PortName when
        # available — reference mirrors the impl casing.
        canonical_pn = port_def.get("name") if isinstance(port_def, dict) else None
        if canonical_pn:
            port_name = canonical_pn

        category = _classify_port(port_name, item_type, port_def, item_record,
                                    pilot_claimed_tags=pilot_claimed_tags,
                                    non_pilot_exclusive_tags=non_pilot_exclusive_tags,
                                    dedicated_seat_tags=dedicated_seat_tags,
                                    entry=entry, ctx=ctx)
        if not category:
            continue

        children = entry.get("children", [])

        # Build the entry differently based on category
        if category in ("MainThrusters", "RetroThrusters", "VtolThrusters", "ManeuveringThrusters"):
            hp = _build_thruster_entry(port_name, entity_class, item_record, ctx)
            _place(tree, category, hp)
        elif category in ("Countermeasures",):
            hp = _build_cm_entry(port_name, entity_class, item_record, ctx)
            _place(tree, category, hp)
        elif category in ("HydrogenFuelTanks", "QuantumFuelTanks", "FuelIntakes"):
            hp = _build_simple_entry(port_name, entity_class, item_record, ctx,
                                      use_display_name=(category == "QuantumFuelTanks"))
            _place(tree, category, hp)
        elif category == "Storage":
            hp = _build_storage_entry(port_name, entity_class, item_record, ctx)
            if hp:
                _place(tree, category, hp)
        elif category == "CargoContainers":
            hp = _build_cargo_container_entry(port_name, entity_class, item_record, ctx)
            if hp:
                _place(tree, category, hp)
        elif category == "SelfDestruct":
            hp = _build_self_destruct_entry(item_record, ctx)
            if hp:
                _place(tree, category, hp)
        elif category == "WeaponsRacks":
            hp = _build_weapon_rack_entry(port_name, item_record, port_def)
            if hp:
                _place(tree, category, hp)
        else:
            # Ship-internal ports inherit the ship's attachDef.tags as their Tags.
            entry_parent_tags = ship_tags if (ship_tags and port_name in ship_internal_ports) else None
            hp = _build_standard_entry(port_name, entity_class, item_record, children, ctx, port_def,
                                        parent_tags=entry_parent_tags, source_entry=entry)
            _place(tree, category, hp)

            # FlightBlade also gets an IFCS entry under Controllers, with the
            # flight controller item's ResourceNetwork inlined (reference shape).
            if category == "FlightBlade" and item_record:
                ifcs_entry = {"ClassName": entity_class}
                from .stditem import _build_resource_network_from_irp
                irp = item_record.get("components", {}).get("ItemResourceComponentParams", {})
                if isinstance(irp, dict) and irp:
                    rn = _build_resource_network_from_irp(irp)
                    if rn:
                        ifcs_entry["ResourceNetwork"] = rn
                tree["Components"]["Systems"]["Controllers"].setdefault(
                    "Ifcs", {"InstalledItems": []}
                )["InstalledItems"].append(ifcs_entry)

    # Add computed storage entries.
    # Structural rule: when a ship has any port-routed Container.Cargo
    # storage entry (via _build_storage_entry) or a Cargo @ui_PersonalStorage
    # inventory in the computed batch, drop SeatAccess GenericExterior
    # ("Access") entries — REF treats the dedicated personal storage as the
    # canonical inventory and absorbs the seat-access fallback.
    if storage_entries:
        existing_storage = (tree.get("Components", {})
                                .get("Storage", {})
                                .get("InstalledItems", []) or [])
        has_cargo_storage = bool(existing_storage) or any(
            se.get("_seat_token") == "@ui_PersonalStorage" for se in storage_entries
        )
        for se in storage_entries:
            seat_token = se.pop("_seat_token", "")
            if has_cargo_storage and seat_token == "@item_Name_SeatAccess_GenericExterior":
                continue
            _place(tree, "Storage", se)

    # Add ports from vehicle impl that aren't in the loadout
    if impl_ports:
        loadout_port_names = {e.get("portName", "") for e in loadout_entries}
        _add_impl_only_ports(tree, impl_ports, loadout_port_names)

    # Also ensure loadout entries with empty entities but known port categories are counted
    for entry in loadout_entries:
        port_name = entry.get("portName", "")
        if not port_name:
            continue
        entity_class = entry.get("entityClassName", "")
        entity_ref = entry.get("entityClassReference", "")
        if entity_class or entity_ref:
            continue  # Already handled above
        # Empty port — classify and add if it's a countable category
        pn = port_name.lower()
        port_def = port_defs.get(port_name, {})
        item_type = ""
        if port_def and port_def.get("types"):
            item_type = port_def["types"][0]
        category = _classify_port(port_name, item_type, port_def,
                                    pilot_claimed_tags=pilot_claimed_tags,
                                    non_pilot_exclusive_tags=non_pilot_exclusive_tags,
                                    dedicated_seat_tags=dedicated_seat_tags)
        if category and category in ("Paints", "Flairs"):
            # Skip ports with no declared types — reference omits them
            # (Gladius hardpoint_cockpit_flair_hanging has empty types
            # in ship.components.ports, REF doesn't emit it). Also skip
            # when there's no port_def at all (impl XML doesn't define
            # the port) — ARGO_CSV_Cargo / Hornet F7CM hardpoint_cockpit_flair_hang
            # are loadout-only with no types to emit.
            if not port_def or not port_def.get("types"):
                continue
            # Count empty paint/flair ports (they represent a customizable slot)
            hp = {"PortName": port_name, "Uneditable": False}
            if port_def:
                hp["MinSize"] = port_def.get("minSize", 0)
                hp["MaxSize"] = port_def.get("maxSize", 0)
                hp["Types"] = port_def.get("types", [])
                pt = port_def.get("portTags", "")
                if pt:
                    hp["PortTags"] = pt.split()
                rt = port_def.get("requiredPortTags", "")
                if rt:
                    hp["RequiredTags"] = rt.split()
            # Ship-internal flair ports (declared in ship.components.ports)
            # inherit the ship's attachDef.tags as their Tags. Impl-only
            # ports (not in ship.components.ports) omit Tags.
            if (category == "Flairs" and ship_tags
                    and port_name in ship_internal_ports):
                hp["Tags"] = list(ship_tags)
            _place(tree, category, hp)

    # Radar DetectionCapability
    _enrich_radar_detection(tree, ctx)

    # Shield FaceType + MaxItem
    _enrich_shield_info(tree, loadout_entries, ctx, class_name)

    # Enrich Controllers sub-blocks (Missiles, Weapons, Wheeled)
    _enrich_controllers(tree, loadout_entries, ctx, class_name)

    # RemoteController.Seats: wire weapon entries to operator seats based on
    # impl-XML ControllerDef.controllableTags / PriorityGroups.
    _enrich_remote_controllers(tree, loadout_entries, ctx, port_defs)

    # Empty EMP/QED slots: count impl-XML ports typed EMP or
    # QuantumInterdictionGenerator that have no loadout entry. Reference
    # emits them as `InterdictionHardpoints: {EMP/QED: {Hardpoints: N}}`
    # without InstalledItems (e.g. Vanguard, Avenger Stalker, Scorpius).
    _enrich_empty_interdiction(tree, loadout_entries, port_defs)

    # SalvageHardpoints.Buff and .SalvageBuffer sub-blocks for salvage ships
    # (Reclaimer, MOTH, Vulture, Fortune, Salvation): the Buff entry carries
    # ship-specific salvage multipliers (Speed/Radius/Efficiency) and the
    # SalvageBuffer entry carries the internal-storage capacity.
    _enrich_salvage_buff(tree, loadout_entries, ctx)

    # WeaponMount.WeaponControl unwrapping: ports typed WeaponMount.WeaponControl
    # (Asgard side doors, Cutlass_Steel side mounts) install wrapper items that
    # bundle a weapon + ammo + controller. Reference promotes the wrapper's
    # inner `weapon` port to a top-level MannedTurrets entry with literal
    # PortName="weapon" carrying the actual gun (e.g. YellowJacket GT-210).
    _enrich_weapon_mount_unwrap(tree, loadout_entries, ctx, port_defs)

    # TotalFuelIntakeRate on FuelIntakes block
    fi_block = tree.get("Components", {}).get("Systems", {}).get("FuelIntakes", {})
    if isinstance(fi_block, dict):
        total = sum(float(it.get("FuelIntakeRate", 0) or 0) for it in fi_block.get("InstalledItems", []))
        fi_block["TotalFuelIntakeRate"] = total

    # TotalFuelCapacity / TotalQuantumFuelCapacity on fuel tank blocks
    propulsion = tree.get("Components", {}).get("Propulsion", {})
    for key, total_field in (("HydrogenFuelTanks", "TotalFuelCapacity"),
                              ("QuantumFuelTanks", "TotalQuantumFuelCapacity")):
        block = propulsion.get(key, {})
        if isinstance(block, dict):
            total = sum(float(it.get("Capacity", 0) or 0) for it in block.get("InstalledItems", []))
            block[total_field] = total

    # CargoGrids: walk the defaultLoadout for any port whose installed item
    # has attachDef.type=="CargoGrid" and emit one entry per port. Reference
    # counts installation instances (e.g. AEGS_Reclaimer has 4 ports each
    # for the Small/Large grids), so we cannot deduplicate by item.
    # Fallback: some ships (e.g. AEGS_Hammerhead) define a single cargo grid
    # via the entity XML rather than the defaultLoadout. For those, the
    # reference still lists the grid, so when the loadout walk yields
    # nothing we fall back to name-prefix matching for one-shot inclusion.
    # Exclude ships with modular hardpoints (Retaliator front/rear module
    # slots) — any CargoGrid named after the ship belongs to a module, not
    # the base ship, and reference treats the base ship as having no grid.
    cargo_grid_items = _build_cargo_grid_items_from_loadout(loadout_entries, ctx)
    has_modules = any(
        "module" in (e.get("portName", "").lower())
        and (e.get("entityClassName") or e.get("entityClassReference"))
        for e in loadout_entries
    )
    if not cargo_grid_items and class_name and not has_modules:
        cargo_grid_items = _build_cargo_grid_items_by_name(class_name, ctx)
    if cargo_grid_items:
        tree["Components"]["CargoGrids"]["InstalledItems"] = cargo_grid_items

    # Update counts
    _update_counts(tree)

    # Collapse empty weapon categories to {} to match ref
    _collapse_empty_categories(tree)

    # Loadout form (GUID vs className) is set per-entry from the source
    # loadout XML by _build_standard_entry. Missile/bomb consumables inside
    # racks follow the same source-mirroring rule — a dedicated rewrite
    # pass used to force className here, but the reference splits this
    # roughly 3:1 GUID:className too (309 GUID / 989 className for
    # MissileRacks.Ports[] in entry_2.json) and the source form matches.

    return tree


_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Pilot ctrl_tags — module-level so both _categorize_port and the RC enricher
# can reference the same set. The "gunNose" entry covers ORIG ships' nose
# weapon controllers which are pilot-fired.
_PILOT_CTRL_TAGS = frozenset({
    "pilotseat", "pilot_seat", "weaponpilot", "pilotseat_weapons",
    "weapon_controller_pilot", "gunnose",
})


def _enrich_remote_controllers(tree, loadout_entries, ctx, port_defs):
    """Populate RemoteController.Seats on weapon entries.

    Algorithm:
    1. Build seat-tag → list-of-seat-itemClassNames map. Each seat port's
       impl-XML PriorityGroup with WeaponController/MissileController +
       exclusive_control on tag X means "this seat exclusively controls
       items with tag X".
    2. For each weapon entry (PilotWeapons/RemoteTurrets/MissileRacks/
       UtilityHardpoints), look up its impl-XML port's controllableTags.
       If a seat exclusively controls that tag, set RemoteController.Seats
       to that seat's installed-item className.

    Slaved=True when the weapon's tag has a numeric (non-exclusive) Turret/
    WeaponGun/MissileLauncher/BombLauncher priority on it from any port.
    Multi-controller weapons (one seat exclusive + another seat numeric on
    same tag) get Slaved=True. Reclaimer-style numeric WeaponController-only
    chains stay Slaved=False because the Turret/WeaponGun PG isn't numeric.
    """
    # Build a port_name → installed-item-className map from the loadout.
    port_to_item = {}

    def _walk_loadout(entries):
        for entry in entries:
            pn = entry.get("portName", "")
            if pn:
                ec, _ = _resolve_entry(entry, ctx)
                if ec:
                    port_to_item[pn.lower()] = ec
            for c in entry.get("children", []) or []:
                _walk_loadout([c])

    _walk_loadout(loadout_entries)

    # Reverse map: installed item className → the port name it occupies.
    # Used to look up a seat's port_def (and thus its ctrl_tag) when
    # determining whether the seat is the ship's pilot.
    item_to_seat_port = {v: k for k, v in port_to_item.items()}

    # Build tag → list of seat item classNames. A seat operates items with
    # tag X if its UserDef has either an exclusive_control claim OR a
    # numeric priority claim on (WeaponController/MissileController, X).
    # RAFT's pilot seat numerically claims CopilotSeat=50 on WeaponController;
    # that numeric claim makes the pilot a co-operator of the copilot's
    # remote-turret WeaponController. Both exclusive AND numeric claims
    # populate tag_to_seats so the resolver finds all seats that can
    # operate items with that tag.
    tag_to_seats = {}
    # Numeric-priority fallback for cases where no claim exists at all.
    tag_to_prio_seats = {}
    for port_name, port_def in port_defs.items():
        if not isinstance(port_def, dict):
            continue
        seat_class = port_to_item.get(port_name.lower())
        if not seat_class:
            continue
        for it_type, tag in port_def.get("exclusiveControl") or []:
            if it_type not in ("WeaponController", "MissileController"):
                continue
            tag_to_seats.setdefault(tag, []).append(seat_class)
        for it_type, tag, prio in port_def.get("priorityControllers") or []:
            tag_to_prio_seats.setdefault(tag, []).append((prio, seat_class))
            if it_type in ("WeaponController", "MissileController"):
                # Also include numeric WC claims as seats-that-can-operate
                # (Slaved+Remote pilots that claim copilot's WC at lower
                # priority). Avoid duplicating the seat if exclusive_control
                # already added it.
                lst = tag_to_seats.setdefault(tag, [])
                if seat_class not in lst:
                    lst.append(seat_class)

    # Build sets of "tags controlled by a weapon controller" vs "tags
    # controlled by a missile controller" — separate gates because the
    # reference emits RC differently for guns vs missile racks.
    #
    # Weapon controller tag = some port has Turret/WeaponGun/TurretBase
    # in its PriorityGroups (exclusive or non-exclusive). Required for
    # PW/RT/UH RC emission.
    #
    # Missile controller tag = some port has MissileLauncher/BombLauncher
    # in its PriorityGroups. MR RC requires BOTH a weapon controller AND
    # missile controller for the tag (Hull_B/Idris/Starlancer have both;
    # Spirit/Constellation only have missile controller and don't get RC).
    weapon_controller_tags = set()
    missile_controller_tags = set()
    # Tags whose weapon-control PG entry is numeric (non-exclusive). When a
    # weapon's tag has any numeric Turret/WeaponGun/MissileLauncher PG entry,
    # multiple seats can claim it → Slaved=True.
    slaved_tags = set()
    for port_name, port_def in port_defs.items():
        if not isinstance(port_def, dict):
            continue
        # exclusiveControl entries are 2-tuples (it_type, tag).
        for it_type, tag in port_def.get("exclusiveControl", []) or []:
            if it_type in ("Turret", "WeaponGun", "TurretBase"):
                weapon_controller_tags.add(tag)
            elif it_type in ("MissileLauncher", "BombLauncher"):
                missile_controller_tags.add(tag)
        # controlledTags entries are 3-tuples (it_type, tag, priority).
        for entry in port_def.get("controlledTags", []) or []:
            it_type, tag = entry[0], entry[1]
            if it_type in ("Turret", "WeaponGun", "TurretBase"):
                weapon_controller_tags.add(tag)
            elif it_type in ("MissileLauncher", "BombLauncher"):
                missile_controller_tags.add(tag)
            if it_type in ("Turret", "WeaponGun", "TurretBase",
                            "MissileLauncher", "BombLauncher"):
                slaved_tags.add(tag)

    # Two-hop chain: weapon-port tag X -> intermediate controller port with
    # controllableTags Y AND PriorityGroup (exclusive OR non-exclusive) on
    # tag X -> seat with exclusive_control on Y. Hornet F7CM gun_center:
    # gun tag=turret_center → controller port (controllableTags=weapon_
    # controller_copilot, PG Turret tag=turret_center) → copilot seat
    # exclusive on weapon_controller_copilot. Idris bridge RTs follow the
    # same pattern with exclusive_control PG entries instead of numeric
    # priorities.
    #
    # Cross-tag rule: a controller may claim items tagged X (its own ctrl)
    # AND items tagged Y (cross-tag extension, e.g. Polaris's bridge missile
    # controller claims both turretseatleft and torpedoSeat). Empirical:
    # - Exclusive_control claims always propagate to the seat operating the
    #   controller (Reclaimer's WC exclusive_controls TurretConsole01_turret
    #   despite ctrl=TurretConsole01).
    # - Numeric claims only propagate when claim tag == controller ctrl_tag
    #   (same-tag). Cross-tag numeric claims are policy fallbacks REF does
    #   not include in Seats (Polaris's bridge missile-only seat is excluded
    #   from torpedoSeat ports because its only path is through a cross-tag
    #   numeric extension).
    indirect_tag_to_seats = {}
    _ITEM_TYPES = ("Turret", "WeaponGun", "TurretBase",
                    "MissileLauncher", "BombLauncher")
    for port_name, port_def in port_defs.items():
        if not isinstance(port_def, dict):
            continue
        ctags = port_def.get("controllableTags")
        if not ctags:
            continue
        # The seat that controls this controller port:
        downstream_seats = tag_to_seats.get(ctags) or []
        if not downstream_seats:
            continue
        # controlledTags entries are 3-tuples (it_type, tag, priority).
        # Build same-tag priority map per itemType for cross-tag comparison.
        numeric_claims = port_def.get("controlledTags") or []
        same_tag_prio = {}
        for entry in numeric_claims:
            it_type, tag = entry[0], entry[1]
            prio = entry[2] if len(entry) >= 3 else None
            if it_type in _ITEM_TYPES and tag == ctags:
                same_tag_prio[it_type] = prio
        # Exclusive entries: always propagate (Reclaimer-pattern works
        # regardless of tag matching — exclusive_control is unconditional).
        for it_type, tag in port_def.get("exclusiveControl") or []:
            if it_type not in _ITEM_TYPES:
                continue
            indirect_tag_to_seats.setdefault(tag, []).extend(downstream_seats)
        # Numeric entries: propagate when
        # (a) tag == ctags (same-tag claim, the natural path), OR
        # (b) no same-tag claim exists for this itemType (cross-tag is the
        #     only path → primary), OR
        # (c) cross-tag priority is STRICTLY LOWER than same-tag priority
        #     (cross-tag claim is stronger than same-tag → primary purpose).
        # Polaris bridge MC: cross-tag torpedoSeat=10 == same-tag
        # turretseatleft=10 → not stronger → don't propagate (Bridge_
        # MissileOnly excluded from torpedo Seats).
        # Starlifter pilot WC: cross-tag RT_Nose=1 < same-tag
        # pilotseat_weapons=50 → stronger → propagate (Pilot included
        # in bridge_remote_turret Seats).
        for entry in numeric_claims:
            it_type, tag = entry[0], entry[1]
            prio = entry[2] if len(entry) >= 3 else None
            if it_type not in _ITEM_TYPES:
                continue
            if tag == ctags:
                indirect_tag_to_seats.setdefault(tag, []).extend(downstream_seats)
                continue
            same_prio = same_tag_prio.get(it_type)
            if same_prio is None:
                # No same-tag claim for this itemType — cross-tag is the
                # only path, propagate.
                indirect_tag_to_seats.setdefault(tag, []).extend(downstream_seats)
                continue
            # Both same-tag and cross-tag exist. Cross-tag wins only if
            # strictly lower priority (better claim).
            try:
                if prio is not None and int(prio) < int(same_prio):
                    indirect_tag_to_seats.setdefault(tag, []).extend(downstream_seats)
            except (TypeError, ValueError):
                pass

    # Merge: prefer direct match; fall back to indirect.
    if not tag_to_seats and not indirect_tag_to_seats:
        return

    # Per-section gating: PW/RT/UH require weapon_controller_tags; MR
    # requires both weapon AND missile controller tags.
    pw_rt_gate = weapon_controller_tags
    mr_gate = weapon_controller_tags & missile_controller_tags

    # Walk all weapon entries in the tree; for each, look up port_def's
    # controllableTags and find matching seats. Includes MissileRacks/
    # UtilityHardpoints — the controlled_weapon_tags gate keeps these
    # to ships with intermediate controllers (Idris/Hull_B/Starlancer/
    # Perseus etc.) where reference does emit RC.
    weapons = tree.get("Weapons", {})
    for sect_name in ("PilotWeapons", "RemoteTurrets", "MissileRacks",
                       "UtilityHardpoints"):
        sect = weapons.get(sect_name, {})
        if not isinstance(sect, dict):
            continue
        for item in sect.get("InstalledItems", []) or []:
            pn = item.get("PortName", "")
            if not pn:
                continue
            pd = port_defs.get(pn) or port_defs.get(pn.lower())
            if not pd:
                continue
            tag = pd.get("controllableTags")
            if not tag:
                continue
            # Per-section gate: emit RC only when the weapon's tag has the
            # appropriate intermediate controller(s).
            if sect_name == "MissileRacks":
                if tag not in mr_gate:
                    continue
            else:
                if tag not in pw_rt_gate:
                    continue
            # Combine direct (seat tagged ctrl_tag) + indirect (via WC chain).
            # Slaved+Remote ports (Shiv, F7CM_Mk2, Corsair chin) have BOTH a
            # direct seat (port ctrl=copilotSeat, copilot seat with that tag)
            # AND an indirect pilot via the pilot WC's PG claim on the same
            # tag. REF emits both seats; combining matches that.
            seats = list(tag_to_seats.get(tag) or [])
            seats.extend(indirect_tag_to_seats.get(tag) or [])
            if not seats:
                # Fallback: numeric-priority seats. Reclaimer pilot has
                # priority 50 on TurretConsole01 vs console_01 priority 100.
                prio = tag_to_prio_seats.get(tag)
                if prio:
                    prio_sorted = sorted(prio, key=lambda x: x[0])
                    seats = [prio_sorted[0][1]]
                else:
                    continue
            # Dedupe while preserving order
            seen = set()
            unique_seats = []
            for s in seats:
                if s not in seen:
                    seen.add(s)
                    unique_seats.append(s)
            # Slaved is item-level: SCItemTurretParams.remoteTurret.
            # SCItemTurretRemoteParams.turretOnlyUsableInRemoteCamera.
            # =1 → operator MUST use remote camera (not pilot-fired) → False
            # =0 → operator can fire it slaved (pilot-fireable) → True
            # absent (gimbals, missile racks, etc.) → fall back to existing
            # tag-in-slaved_tags rule.
            slaved = tag in slaved_tags  # default
            installed_class = port_to_item.get(pn.lower())
            if installed_class:
                inst_item = ctx.get_item(installed_class) or {}
                tp = inst_item.get("components", {}).get("SCItemTurretParams") or {}
                remote_turret = (tp.get("remoteTurret") if isinstance(tp, dict)
                                  else None) or {}
                remote_params = (remote_turret.get("SCItemTurretRemoteParams")
                                  if isinstance(remote_turret, dict) else None)
                if isinstance(remote_params, dict):
                    only = remote_params.get("turretOnlyUsableInRemoteCamera")
                    if only == "1":
                        slaved = False
                    elif only == "0":
                        slaved = True
            item["RemoteController"] = {
                "Slaved": slaved,
                "Seats": unique_seats,
            }


def _enrich_weapon_mount_unwrap(tree, loadout_entries, ctx, port_defs):
    """Unwrap WeaponMount.WeaponControl wrappers and emit inner `weapon` as MT entry.

    Ships like Asgard (side doors) and Cutlass_Steel (side mounts) install
    `WeaponMount_Gun_S1_*` items in turret-class ports. Each wrapper holds a
    pre-installed gun (e.g. GATS_BallisticGatling_Mounted_S1 — the YellowJacket
    GT-210) plus ammo and controller. Reference promotes the inner `weapon`
    port to MannedTurrets.InstalledItems with literal PortName="weapon".

    Conservative scope: only unwrap when the OUTER port (vehicle hardpoint) is
    declared as type `WeaponMount.WeaponControl`. This catches Asgard and
    Cutlass_Steel. Ships like Valkyrie/Starlancer_TAC have the same WeaponMount
    items installed in TurretBase.MannedTurret-typed ports and reference treats
    them inconsistently — skipping those for safety.
    """
    from .stditem import (MANUFACTURER_CLASS, _COMPONENT_TYPES_CLASSED,
                            _CLASS_VALUE_OVERRIDES)

    weapons = tree.setdefault("Weapons", {})
    mt = weapons.setdefault("MannedTurrets", {})
    mt.setdefault("InstalledItems", [])

    def _walk(entries):
        for entry in entries:
            port_name = entry.get("portName") or ""
            ec, item = _resolve_entry(entry, ctx)
            if not item:
                for c in entry.get("children", []) or []:
                    _walk([c])
                continue
            ad = item.get("attachDef", {})
            if (ad.get("type") == "WeaponMount"
                    and ad.get("subType") == "WeaponControl"):
                # Unwrap when:
                # 1. Outer port type is WeaponMount.WeaponControl
                #    (Asgard side doors, Cutlass_Steel via components.ports)
                # 2. Port name contains "mountedgun" (Starlancer_TAC,
                #    Cutlass_Steel — these have TurretBase port type but REF
                #    still unwraps based on port-name pattern)
                #
                # Don't unwrap for "turret_door" + TurretBase ports
                # (Valkyrie). Same wrapper item but REF emits empty mount.
                pd = port_defs.get(port_name) or {}
                pd_types = pd.get("types", []) if isinstance(pd, dict) else []
                pn_lower = (port_name or "").lower()
                outer_accepts_wm = any(
                    t == "WeaponMount.WeaponControl" or t == "WeaponMount"
                    for t in (pd_types or [])
                )
                should_unwrap = outer_accepts_wm or "mountedgun" in pn_lower
                if should_unwrap:
                    _emit_unwrapped_weapon(mt, item, ad, port_name, pd, ctx,
                                             MANUFACTURER_CLASS,
                                             _COMPONENT_TYPES_CLASSED,
                                             _CLASS_VALUE_OVERRIDES)
                # Don't recurse into WeaponMount children; the inner weapon
                # is emitted directly. Continue to next sibling.
                continue
            for c in entry.get("children", []) or []:
                _walk([c])

    _walk(loadout_entries)


def _emit_unwrapped_weapon(mt, wm_item, wm_ad, outer_port_name, outer_pd, ctx,
                              MANUFACTURER_CLASS, _COMPONENT_TYPES_CLASSED,
                              _CLASS_VALUE_OVERRIDES):
    """Emit a single unwrapped weapon entry into mt.InstalledItems."""
    # Find the WeaponMount item's `weapon` sub-port definition
    weapon_port = None
    for p in wm_item.get("components", {}).get("ports", []) or []:
        if p.get("name") == "weapon":
            weapon_port = p
            break
    if not weapon_port:
        return

    # Find the weapon installed in the WeaponMount's defaultLoadout
    wmlo = wm_item.get("components", {}).get("defaultLoadout", []) or []
    weapon_cn = None
    for e in wmlo:
        if e.get("portName") == "weapon":
            weapon_cn = e.get("entityClassName") or ""
            if not weapon_cn:
                ref = e.get("entityClassReference", "")
                if ref:
                    weapon_cn = ctx.resolve_guid(ref) or ""
            break
    if not weapon_cn:
        return
    weapon_item = ctx.get_item(weapon_cn)
    if not weapon_item:
        return

    weapon_ad = weapon_item.get("attachDef", {})
    weapon_full_type = weapon_ad.get("type", "")
    if weapon_ad.get("subType"):
        weapon_full_type = f"{weapon_full_type}.{weapon_ad['subType']}"

    bl_name = ctx.resolve_name(weapon_ad.get("name", ""))
    if (bl_name == "<= PLACEHOLDER =>" or bl_name == "@LOC_PLACEHOLDER"
            or bl_name == "@LOC_EMPTY"
            or (bl_name and bl_name.startswith("@itemPort_"))
            or (bl_name and bl_name.startswith("@item_Name"))
            or not bl_name):
        bl_name = weapon_cn

    mfr = ctx.get_manufacturer(weapon_ad.get("manufacturerGuid", ""))
    mfr_code = (mfr or {}).get("Code", "") if mfr else ""
    base_type = weapon_full_type.split(".")[0] if weapon_full_type else ""
    bl_class = ""
    if weapon_cn in _CLASS_VALUE_OVERRIDES:
        bl_class = _CLASS_VALUE_OVERRIDES[weapon_cn]
    elif base_type in _COMPONENT_TYPES_CLASSED and mfr_code:
        bl_class = MANUFACTURER_CLASS.get(mfr_code, "")

    bl = {
        "ClassName": weapon_cn,
        "Name": bl_name,
        "Type": weapon_full_type,
        "Size": weapon_ad.get("size", 1),
        "Grade": weapon_ad.get("grade", 1),
    }
    if (not _omit_baseloadout_class(weapon_full_type)
            and weapon_cn not in _BASELOADOUT_CLASS_OMIT_MISSILERACKS
            and weapon_cn not in _BASELOADOUT_CLASS_OMIT_TURRETS
            and weapon_cn not in _BASELOADOUT_CLASS_OMIT_COMPONENTS):
        bl["Class"] = bl_class

    entry = {
        "PortName": "weapon",
        "MinSize": weapon_port.get("minSize", 1),
        "MaxSize": weapon_port.get("maxSize", 1),
        "Loadout": weapon_cn,
        "BaseLoadout": bl,
        "Types": list(weapon_port.get("types", [])),
    }
    flags_raw = weapon_port.get("flags") or []
    if isinstance(flags_raw, str):
        flags = [f for f in flags_raw.split() if f]
    else:
        flags = list(flags_raw)
    if flags:
        entry["Flags"] = flags
    # Tags from WeaponMount item attachDef.tags (e.g. "$anvl_asgard")
    wm_tags = wm_ad.get("tags", "") or ""
    if wm_tags:
        entry["Tags"] = wm_tags.split() if isinstance(wm_tags, str) else list(wm_tags)
    # RequiredTags from inner weapon port's requiredPortTags
    req_tags = weapon_port.get("requiredPortTags", "") or ""
    if req_tags:
        entry["RequiredTags"] = req_tags.split() if isinstance(req_tags, str) else list(req_tags)
    # Fixed flag for WeaponGun.* types
    if weapon_full_type.startswith("WeaponGun."):
        entry["Fixed"] = True
    entry["Uneditable"] = bool(weapon_port.get("uneditable"))

    mt["InstalledItems"].append(entry)


def _enrich_salvage_buff(tree, loadout_entries, ctx):
    """Emit SalvageHardpoints.{Buff,SalvageBuffer} sub-blocks.

    Walks the loadout for hardpoint_attachable_buff (Salvage_Buff_Modifier_*
    items, type UNDEFINED) and hardpoint_internal_storage / hardpoint_*
    SalvageInternalStorage items. Buff carries ship-specific salvage rate
    modifiers; SalvageBuffer carries the on-board scrap container capacity.
    Both are flattened single-entry blocks in the reference.
    """

    def _find_attachable_buff(item):
        comps = item.get("components", {})
        m = comps.get("EntityComponentAttachableModifierParams", {})
        if not isinstance(m, dict):
            return None
        traversing = (m.get("modifiers", {}) or {}).get(
            "ItemportTraversingModifiersParams", {})
        if not isinstance(traversing, dict):
            return None
        weapon_mod = (traversing.get("modifiers", {}) or {}).get(
            "ItemWeaponModifiersParams", {})
        if not isinstance(weapon_mod, dict):
            return None
        sm = (weapon_mod.get("weaponModifier", {})
              .get("weaponStats", {})
              .get("salvageModifier", {}))
        if not isinstance(sm, dict) or not sm:
            return None
        return sm

    def _find_internal_capacity(item):
        rc = item.get("components", {}).get("ResourceContainer", {})
        if not isinstance(rc, dict):
            return None
        cap = rc.get("capacity", {}).get("SStandardCargoUnit", {}).get(
            "standardCargoUnits")
        try:
            return float(cap)
        except (TypeError, ValueError):
            return None

    buff_entries = []
    buffer_entries = []

    def _walk(entries):
        for entry in entries:
            pn = (entry.get("portName") or "").lower()
            ec, item = _resolve_entry(entry, ctx)
            if item:
                ad = item.get("attachDef", {})
                t = ad.get("type", "")
                if "buff" in pn and t == "UNDEFINED":
                    sm = _find_attachable_buff(item)
                    if sm is not None:
                        buff_entries.append({
                            "Name": ec,
                            "SalvageBuffModifier": {
                                "SpeedMultiplier": float(sm.get(
                                    "salvageSpeedMultiplier", 0) or 0),
                                "RadiusMultiplier": float(sm.get(
                                    "radiusMultiplier", 0) or 0),
                                "ExtractionEfficiency": float(sm.get(
                                    "extractionEfficiency", 0) or 0),
                            },
                        })
                elif t == "SalvageInternalStorage":
                    cap = _find_internal_capacity(item)
                    if cap is not None:
                        buffer_entries.append({"Name": ec, "Capacity": cap})
            for c in entry.get("children", []) or []:
                _walk([c])

    _walk(loadout_entries)

    if not buff_entries and not buffer_entries:
        return

    weapons = tree.setdefault("Weapons", {})
    sh = weapons.setdefault("SalvageHardpoints", {})
    if buff_entries:
        sh["Buff"] = {"InstalledItems": buff_entries,
                       "ItemsQuantity": len(buff_entries)}
    if buffer_entries:
        sh["SalvageBuffer"] = {"InstalledItems": buffer_entries,
                                 "ItemsQuantity": len(buffer_entries)}


def _enrich_empty_interdiction(tree, loadout_entries, port_defs):
    """Count impl-XML EMP/QED ports without loadout items.

    Reference emits `InterdictionHardpoints.{EMP,QED}.Hardpoints: N` for
    ships with empty interdiction slots. Filled slots already produce
    InstalledItems via the main loadout walk.
    """
    # Build set of port names that have a loadout entry (filled).
    filled = set()

    def _walk(entries):
        for e in entries:
            pn = e.get("portName", "")
            if pn and (e.get("entityClassName") or e.get("entityClassReference")):
                filled.add(pn.lower())
            for c in e.get("children", []) or []:
                _walk([c])

    _walk(loadout_entries)

    weapons = tree.setdefault("Weapons", {})
    interdiction = weapons.setdefault("InterdictionHardpoints", {})

    for port_name, pd in port_defs.items():
        if not isinstance(pd, dict):
            continue
        if pd.get("skipPart"):
            continue
        if port_name.lower() in filled:
            continue
        types = [t.lower() for t in pd.get("types", []) or []]
        sub_key = None
        if any(t == "emp" or t.startswith("emp.") for t in types):
            sub_key = "EMP"
        elif any(t == "quantuminterdictiongenerator"
                  or t.startswith("quantuminterdictiongenerator.") for t in types):
            sub_key = "QED"
        if not sub_key:
            continue
        sub = interdiction.setdefault(sub_key, {})
        sub["Hardpoints"] = sub.get("Hardpoints", 0) + 1


def _enrich_controllers(tree, loadout_entries, ctx, class_name):
    """Populate Controllers sub-blocks from loadout items.

    - Missiles: {MaxArmed, Cooldown} from SCItemMissileControllerParams
    - Weapons: {PoolSize} from vehicle's FixedPowerPool for WeaponGun (weapon_pool_sizes)
    - Wheeled: always present (empty {} for ships, populated for ground vehicles)
    """
    controllers = tree.get("Components", {}).get("Systems", {}).get("Controllers", {})

    # Strip any InstalledItems that snuck in (ref doesn't have a top-level
    # InstalledItems in Controllers — everything sits under named sub-keys).
    if "InstalledItems" in controllers:
        del controllers["InstalledItems"]

    # Missiles: walk loadout for a controller_missile port and use that item's
    # SCItemMissileControllerParams if present. Reference always emits the
    # Missiles block: ships with any MissileRacks get the default
    # Controller_Missile values (MaxArmed=4, Cooldown=4) when the loadout
    # doesn't specify a custom controller, and ships with no MissileRacks
    # get zeros. Ships do sometimes have a controller_missile port without
    # a loadout entry — the defaults still apply in that case.
    missile_data = {}

    def _walk(entries):
        for e in entries:
            _, item = _resolve_entry(e, ctx)
            if item and (item.get("attachDef", {}) or {}).get("type") == "MissileController":
                mc = item.get("components", {}).get("SCItemMissileControllerParams", {})
                if isinstance(mc, dict):
                    ma = mc.get("maxArmedMissiles")
                    lc = mc.get("launchCooldownTime")
                    if ma is not None:
                        missile_data["MaxArmed"] = float(ma)
                    if lc is not None:
                        missile_data["Cooldown"] = float(lc)
            for c in e.get("children", []):
                _walk([c])

    _walk(loadout_entries)

    if not missile_data:
        # No custom controller in loadout. Decide between the default
        # Controller_Missile values and zeros based on whether the ship
        # has any missile racks or bomb racks installed.
        mr = tree.get("Weapons", {}).get("MissileRacks", {}) or {}
        br = tree.get("Weapons", {}).get("BombRacks", {}) or {}
        has_missiles = bool(mr.get("InstalledItems") or br.get("InstalledItems"))
        if has_missiles:
            default = ctx.get_item("Controller_Missile")
            if default:
                mc = default.get("components", {}).get("SCItemMissileControllerParams", {})
                if isinstance(mc, dict):
                    ma = mc.get("maxArmedMissiles")
                    lc = mc.get("launchCooldownTime")
                    if ma is not None:
                        missile_data["MaxArmed"] = float(ma)
                    if lc is not None:
                        missile_data["Cooldown"] = float(lc)
        else:
            missile_data = {"MaxArmed": 0.0, "Cooldown": 0.0}
    controllers["Missiles"] = missile_data

    # Weapons: from weapon_pool_sizes (WeaponGun pool); Modifiers from
    # Engineering_Buff_Modifier_<ship> item's regenModifier (applies
    # powerRatio / maxAmmoLoad / maxRegenPerSec multipliers to the pool).
    pool = ctx.weapon_pool_sizes.get(class_name.lower())
    weapons_block = {}
    # Reference always emits Controllers.Weapons.PoolSize, even when 0.0
    # (Cyclone Cargo/AA/RC/RN/TR variants, Storm_AA — ground vehicles with
    # no FixedPowerPool entry).
    weapons_block["PoolSize"] = float(pool) if pool else 0.0

    # Look up the ship's engineering buff. Variants share a base buff, so
    # progressively strip trailing _X suffix tokens on miss until we find
    # one (Cutlass_Black → Cutlass; Constellation_Andromeda → Constellation;
    # Starfarer_Gemini → Starfarer; Idris_M → Idris).
    buff_candidates = [f"Engineering_Buff_Modifier_{class_name}"]
    base = class_name
    while "_" in base:
        base = base.rsplit("_", 1)[0]
        buff_candidates.append(f"Engineering_Buff_Modifier_{base}")
    buff_item = None
    for cand in buff_candidates:
        buff_item = ctx.get_item(cand)
        if buff_item:
            break
    if buff_item:
        rm = (
            buff_item.get("components", {})
            .get("EntityComponentAttachableModifierParams", {})
            .get("modifiers", {})
            .get("ItemportTraversingModifiersParams", {})
            .get("modifiers", {})
            .get("ItemWeaponModifiersParams", {})
            .get("weaponModifier", {})
            .get("weaponStats", {})
            .get("regenModifier", {})
        )
        if isinstance(rm, dict) and rm:
            weapons_block["Modifiers"] = {
                "PowerRatioMultiplier": safe_float(rm.get("powerRatioMultiplier", 1)),
                "MaxAmmoLoadMultiplier": safe_float(rm.get("maxAmmoLoadMultiplier", 1)),
                "MaxRegenPerSecMultiplier": safe_float(rm.get("maxRegenPerSecMultiplier", 1)),
            }

    if weapons_block:
        controllers["Weapons"] = weapons_block

    # CapacitorAssignment: pull the AfterBurner GUIDs + AngVelocity curve from
    # the flight controller's IFCSParams.afterburner block. Reference always
    # emits ShieldEmitter/PilotWeapon/TurretsWeapon as empty {} alongside
    # AfterBurner (201/201 ships in the dataset).
    cap_assignment = {
        "AfterBurner": {},
        "ShieldEmitter": {},
        "PilotWeapon": {},
        "TurretsWeapon": {},
    }

    def _walk_flight(entries):
        for e in entries:
            _, item = _resolve_entry(e, ctx)
            if item and "IFCSParams" in (item.get("components", {}) or {}):
                ifcs = item.get("components", {}).get("IFCSParams", {})
                ab = ifcs.get("afterburner", {}) if isinstance(ifcs, dict) else {}
                if isinstance(ab, dict) and ab:
                    block = {}
                    regen = ab.get("capacitorAssignmentInputOutputRegen", "")
                    if regen and regen != "00000000-0000-0000-0000-000000000000":
                        block["Regen"] = regen
                    regen_nav = ab.get("capacitorAssignmentInputOutputRegenNavMode", "")
                    if regen_nav and regen_nav != "00000000-0000-0000-0000-000000000000":
                        block["RegenNavMode"] = regen_nav
                    usage = ab.get("capacitorAssignmentInputOutputUsage", "")
                    if usage and usage != "00000000-0000-0000-0000-000000000000":
                        block["Usage"] = usage
                    # AngVelocity: afterburnerAngCapacitorScalingCurve.points.Vec2
                    curve = ab.get("afterburnerAngCapacitorScalingCurve", {}) or {}
                    points = curve.get("points", {}) if isinstance(curve, dict) else {}
                    vec_list = points.get("Vec2", []) if isinstance(points, dict) else []
                    if isinstance(vec_list, list) and vec_list:
                        block["AngVelocity"] = [
                            {"x": safe_float(v.get("x", 0)),
                             "y": safe_float(v.get("y", 0))}
                            for v in vec_list if isinstance(v, dict)
                        ]
                    if block:
                        cap_assignment["AfterBurner"] = block
                        return
            for c in e.get("children", []):
                _walk_flight([c])

    _walk_flight(loadout_entries)
    controllers["CapacitorAssignment"] = cap_assignment

    # Wheeled: always emit (empty {} for ships; populated with wheel
    # controller entries for ground vehicles).
    if "Wheeled" not in controllers:
        controllers["Wheeled"] = {}
    # Ifcs: always emit (populated from the flight controller inlining above
    # for spaceships; empty {} for ground vehicles that reference still
    # emits but with no inner content).
    if "Ifcs" not in controllers:
        controllers["Ifcs"] = {}
    # If entries were placed into Wheeled but the container still lacks an
    # InstalledItems list (edge case), ensure the block has the shape that
    # _update_counts expects.
    w = controllers.get("Wheeled")
    if isinstance(w, dict) and w.get("InstalledItems") and "Hardpoints" not in w:
        w["Hardpoints"] = len(w["InstalledItems"])


def _enrich_radar_detection(tree, ctx):
    """Add DetectionCapability to Radars from SCItemRadarComponentParams."""
    radars_node = tree.get("Components", {}).get("Avionics", {}).get("Radars", {})
    installed = radars_node.get("InstalledItems", [])
    if not installed:
        return

    detection = []
    for radar_entry in installed:
        class_name = radar_entry.get("Loadout", "")
        if not class_name:
            continue
        # _enrich_radar_detection runs before the Loadout-convention rewrite
        # (Components Loadouts are still GUIDs at this point); resolve when so.
        if _GUID_RE.match(class_name):
            class_name = ctx.resolve_guid(class_name) or class_name
        item = ctx.get_item(class_name)
        if not item:
            continue
        rcomp = item.get("components", {}).get("SCItemRadarComponentParams", {})
        sd = rcomp.get("signatureDetection", {}).get("SCItemRadarSignatureDetection", [])
        if not sd or len(sd) < 5:
            continue

        # Signal order: 0=IR, 1=EM, 2=CS, 3=unused, 4=RS
        ir_sens = safe_float(sd[0].get("sensitivity", "0"))
        em_sens = safe_float(sd[1].get("sensitivity", "0"))
        cs_sens = safe_float(sd[2].get("sensitivity", "0"))
        rs_sens = safe_float(sd[4].get("sensitivity", "0"))

        ir_pierce = safe_float(sd[0].get("piercing", "0"))
        em_pierce = safe_float(sd[1].get("piercing", "0"))
        cs_pierce = safe_float(sd[2].get("piercing", "0"))
        rs_pierce = safe_float(sd[4].get("piercing", "0"))

        # Ground sensitivity = base sensitivity + sensitivityAddition modifier
        ground_add = 0.0
        sm = rcomp.get("sensitivityModifiers", {})
        if isinstance(sm, dict):
            mod = sm.get("SCItemRadarSensitivityModifier", {})
            if isinstance(mod, dict):
                ground_add = safe_float(mod.get("sensitivityAddition", "0"))

        ad = item.get("attachDef", {})
        det_name = ctx.resolve_name(ad.get("name", ""))
        if (det_name == "<= PLACEHOLDER =>" or det_name == "@LOC_PLACEHOLDER"
                or det_name == "@LOC_EMPTY"
                or (det_name and det_name.startswith("@item_Name"))
                or not det_name):
            det_name = class_name
        entry = {
            "Name": det_name,
            "PortName": radar_entry.get("PortName", ""),
            "Size": ad.get("size", 0),
            "Sensitivity": {
                "IRSensitivity": ir_sens,
                "EMSensitivity": em_sens,
                "CSSensitivity": cs_sens,
                "RSSensitivity": rs_sens,
            },
            # GroundSensitivity is uniform across all 4 signal types in the
            # reference — it derives from IR sensitivity + ground modifier and
            # is replicated to EM/CS/RS, not computed per-signal.
            "GroundSensitivity": {
                "IRSensitivity": max(0.0, round(ir_sens + ground_add, 4)),
                "EMSensitivity": max(0.0, round(ir_sens + ground_add, 4)),
                "CSSensitivity": max(0.0, round(ir_sens + ground_add, 4)),
                "RSSensitivity": max(0.0, round(ir_sens + ground_add, 4)),
            },
            "Piercing": {
                "IRPiercing": ir_pierce,
                "EMPiercing": em_pierce,
                "CSPiercing": cs_pierce,
                "RSPiercing": rs_pierce,
            },
        }
        detection.append(entry)

    if detection:
        radars_node["DetectionCapability"] = detection


def _enrich_shield_info(tree, loadout_entries, ctx, class_name=""):
    """Add FaceType and MaxItem to the Shields node."""
    shields_node = tree.get("Components", {}).get("Systems", {}).get("Shields", {})
    installed = shields_node.get("InstalledItems", [])

    # FaceType from shield controller item — SCItemShieldEmitterParams
    # component is 100% specific to ShieldController.UNDEFINED items.
    def _find_shield_controller(entries):
        for entry in entries:
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {}) or {}
                se = comps.get("SCItemShieldEmitterParams")
                if isinstance(se, dict):
                    ft = se.get("FaceType", "")
                    if ft:
                        return ft
            children = entry.get("children", [])
            if children:
                result = _find_shield_controller(children)
                if result:
                    return result
        return None

    face_type = _find_shield_controller(loadout_entries)
    if face_type:
        shields_node["FaceType"] = face_type

    # MaxItem from shield DynamicPowerPool maxItemCount
    max_item = ctx.shield_pool_sizes.get(class_name.lower())
    if max_item is not None and max_item > 0:
        shields_node["MaxItem"] = float(max_item)


def _compute_storage(loadout_entries, ctx, impl=None):
    """Find storage/inventory entries by checking seat access entities.

    Reference omits storage entries whose item name doesn't resolve (the
    @LOC_PLACEHOLDER fallback) — those represent internal inventory blocks
    not surfaced as cargo.

    Uneditable mirrors the impl-XML port flag for the loadout port the
    inventory hangs off of: SeatAccess ports with `uneditable` flag emit
    Uneditable:true; ports with empty flags omit the field entirely.
    """
    storage = []

    # Build port_name → (uneditable, types) lookup from impl XML.
    # uneditable: mirror the SeatAccess port's flag for output.
    # types: when the impl-XML port is typed Door.* (mechanism door for the
    # storage cabinet, e.g. ANVL_Hawk hardpoint_personal_storage), reference
    # omits the entire storage entry — these are cabinet doors, not user-
    # facing inventory hardpoints.
    port_uneditable = {}
    port_types_lower = {}
    if impl:
        def _collect(ports):
            for p in ports or []:
                pn = p.get("name", "").lower()
                if pn:
                    port_uneditable[pn] = bool(p.get("uneditable"))
                    port_types_lower[pn] = [
                        (t or "").lower() for t in (p.get("types") or [])
                    ]
                _collect(p.get("subPorts"))
        _collect(impl.get("ports"))

    def _walk(entries):
        for entry in entries:
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {})
                inv = comps.get("SCItemInventoryContainerComponentParams", {})
                if isinstance(inv, dict):
                    container_guid = inv.get("containerParams", "")
                    capacity = ctx.get_inventory_capacity(container_guid)
                    if capacity > 0:
                        ad = item_record.get("attachDef", {})
                        ad_type = ad.get("type", "")
                        # Storage InstalledItems come from SeatAccess seat
                        # inventories and Cargo personal-storage items.
                        # CargoGrid / Container / Module are routed through
                        # their own builders. Usable / Char_* / etc. carry
                        # incidental inventory but are not gameplay storage
                        # hardpoints.
                        if ad_type not in ("SeatAccess", "Cargo"):
                            children = entry.get("children", [])
                            if children:
                                _walk(children)
                            continue
                        # @LOC_PLACEHOLDER-named items fall back to className
                        # (REF: ARGO_MPUV_1T, XNAA, XIAN_Scout, TMBL_Cyclone
                        # copilot — all SeatAccess with placeholder name).
                        name_token = ad.get("name", "")
                        if name_token == "@LOC_PLACEHOLDER":
                            if entity_class:
                                name = entity_class
                            else:
                                children = entry.get("children", [])
                                if children:
                                    _walk(children)
                                continue
                        else:
                            name = ctx.resolve_name(name_token or "Access")
                        port_name = (entry.get("portName") or "").lower()
                        # Skip storage entries hung off Door-typed impl ports
                        # (Hawk/Hurricane/Guardian hardpoint_personal_storage):
                        # those are cabinet door mechanisms, not gameplay
                        # inventory hardpoints, and reference omits them.
                        ptypes = port_types_lower.get(port_name, [])
                        if any(t.startswith("door") for t in ptypes):
                            children = entry.get("children", [])
                            if children:
                                _walk(children)
                            continue
                        phys = comps.get("physics", {})
                        mass_val = phys.get("mass") if isinstance(phys, dict) else 0.0
                        st = {
                            "Name": name,
                            "Mass": float(mass_val or 0.0),
                            "Size": ad.get("size", 1),
                            "Grade": ad.get("grade", 1),
                            "Capacity": capacity,
                            "_seat_token": name_token,
                        }
                        # Reference only emits Uneditable when the impl-XML
                        # port carries the `uneditable` flag. Empty-flag
                        # SeatAccess ports omit the field entirely.
                        if port_uneditable.get(port_name):
                            st["Uneditable"] = True
                        storage.append(st)
            children = entry.get("children", [])
            if children:
                _walk(children)

    _walk(loadout_entries)
    return storage


def _compute_interior_storage(class_name, ctx):
    """Build Storage entries from ship-interior PersonalStorage placements.

    `ctx.ship_storage_index[class_name]` holds {item_classname: count, ...}
    walked from each ship's .socpak archives (the placements physically
    placed inside the ship's interior, not attached via loadout ports).
    For each placement, emit a Storage entry mirroring `_compute_storage`'s
    shape: Name from the item's resolved attachDef.name (or className
    fallback), Mass from physics.mass, Size/Grade from attachDef, Capacity
    from the inventory container.
    """
    placements = ctx.ship_storage_index.get(class_name, {})
    if not placements:
        return []

    entries = []
    for item_cn, count in placements.items():
        item = ctx.items.get(item_cn) or {}
        if not item:
            continue
        ad = item.get("attachDef", {}) or {}
        comps = item.get("components", {}) or {}
        inv = comps.get("SCItemInventoryContainerComponentParams", {})
        cap_guid = inv.get("containerParams") if isinstance(inv, dict) else None
        capacity = ctx.get_inventory_capacity(cap_guid) if cap_guid else 0
        if capacity <= 0:
            continue
        name_token = ad.get("name", "")
        name = ctx.resolve_name(name_token) if name_token else ""
        if not name or name_token == "@LOC_PLACEHOLDER" or "PLACEHOLDER" in name:
            name = item_cn
        phys = comps.get("physics", {})
        mass = float((phys.get("mass") if isinstance(phys, dict) else 0.0) or 0.0)
        for _ in range(count):
            entries.append({
                "Name": name,
                "Mass": mass,
                "Size": ad.get("size", 1),
                "Grade": ad.get("grade", 1),
                "Capacity": capacity,
            })
    return entries


def _add_impl_only_ports(tree, impl_ports, loadout_port_names):
    """Add ports from vehicle impl that aren't in the loadout.

    Only Paints emit unconditionally. Bare WeaponsRacks (impl-defined
    weapon_rack ports without loadout items, single port per ship) emit
    a minimal entry — Ballista, Cutlass Black/Blue, ORIG_350r have a
    single hardpoint_weapon_rack visible in reference. Multi-port
    weapon_locker patterns (Idris) are omitted from reference.
    """
    emitted_names = set()

    def _emit(port):
        pname = port.get("name", "")
        if not pname or pname in loadout_port_names:
            return
        # Dedupe: impl XML can declare the same port name at multiple
        # hierarchy levels (e.g. Cutlass hardpoint_weapon_rack appears
        # twice). REF emits only one entry per unique port name.
        if pname in emitted_names:
            return
        emitted_names.add(pname)
        item_type = port["types"][0] if port.get("types") else ""
        category = _classify_port(pname, item_type, port)
        if category == "Paints":
            hp = {"PortName": pname, "Uneditable": port.get("uneditable", False),
                  "MinSize": port.get("minSize", 0), "MaxSize": port.get("maxSize", 0),
                  "Types": port.get("types", [])}
            _place(tree, category, hp)
        elif category == "Flairs" and port.get("types"):
            # Impl-only flair ports (300i hardpoint_custom_*, MOTH hanging,
            # Perseus captains_flair). Skip ports with no types — those are
            # decorative anchors, not customizable flair slots.
            hp = {"PortName": pname,
                  "MinSize": port.get("minSize", 0), "MaxSize": port.get("maxSize", 0),
                  "Types": port.get("types", [])}
            rt = port.get("requiredPortTags", "")
            if rt:
                hp["RequiredTags"] = rt.split()
            pt = port.get("portTags", "")
            if pt:
                hp["PortTags"] = pt.split()
            flags_raw = port.get("flags")
            if isinstance(flags_raw, list) and flags_raw:
                hp["Flags"] = list(flags_raw)
            elif isinstance(flags_raw, str) and flags_raw:
                hp["Flags"] = [f for f in flags_raw.split() if f]
            hp["Uneditable"] = port.get("uneditable", False)
            _place(tree, category, hp)
        elif category == "WeaponsRacks" and pname.lower() == "hardpoint_weapon_rack":
            # Only the bare singular hardpoint_weapon_rack port pattern.
            hp = {
                "Name": pname,
                "Size": port.get("maxSize", port.get("minSize", 1)),
                "Uneditable": port.get("uneditable", False),
            }
            _place(tree, category, hp)

    for port in impl_ports:
        _emit(port)
        for sub in port.get("subPorts", []):
            _emit(sub)


def _index_ports(impl_ports, port_defs, order_index=None, _depth=0):
    """Build a flat lookup of port name -> port definition from vehicle impl ports.

    If `order_index` is provided, also records each port's discovery order so
    callers can sort loadout entries to match the impl XML's structural order.
    """
    for port in impl_ports:
        name = port.get("name", "")
        if name:
            port_defs[name] = port
            if order_index is not None and name not in order_index:
                order_index[name] = len(order_index)
        # Recurse into sub-ports
        sub = port.get("subPorts", [])
        if sub:
            _index_ports(sub, port_defs, order_index, _depth + 1)


def _compute_mass(loadout_entries, ctx):
    """Compute total mass by summing all component masses from the loadout."""
    total = 0.0
    component_mass = 0.0

    def _walk(entries):
        nonlocal total, component_mass
        for entry in entries:
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                physics = item_record.get("components", {}).get("physics", {})
                mass = physics.get("mass", 0)
                if mass:
                    total += mass
                    component_mass += mass
            children = entry.get("children", [])
            if children:
                _walk(children)

    _walk(loadout_entries)
    return total, component_mass


def _resolve_entry(entry, ctx):
    """Resolve a loadout entry to (className, itemRecord)."""
    entity_class = entry.get("entityClassName", "")
    entity_ref = entry.get("entityClassReference", "")

    if entity_class:
        return entity_class, ctx.get_item(entity_class)
    elif entity_ref:
        resolved = ctx.resolve_guid(entity_ref) or entity_ref
        return resolved, ctx.get_item(resolved)
    return "", None


def _build_standard_entry(port_name, entity_class, item_record, children, ctx, port_def=None, parent_tags=None, source_entry=None, is_sub_port=False):
    """Build a standard hardpoint entry with BaseLoadout and sub-ports.

    Loadout form (GUID vs className) mirrors the source loadout XML: when the
    entry references the item via `entityClassReference` (a GUID), Loadout
    emits the GUID; when via `entityClassName`, Loadout emits the className.
    Falls back to GUID when the source form is ambiguous.

    `is_sub_port` = True when recursing into a parent item's child ports
    (e.g. the weapon slot inside a turret). Sub-ports never get the
    top-level Fixed:true marker that reference applies only to outermost
    WeaponGun.* pilot mounts.
    """
    entry = {"PortName": port_name}

    # Tags from parent item (describes the port's capability)
    if parent_tags:
        entry["Tags"] = parent_tags

    if item_record:
        ad = item_record.get("attachDef", {})
        size = ad.get("size", 0)
        full_type = _full_type(ad)
        mfr = ctx.get_manufacturer(ad.get("manufacturerGuid", ""))

        # Use port definition from vehicle impl for size/types if available.
        # For installed missile/bomb racks, clamp MaxSize to the item's
        # actual size — Hornet F7C_Mk2-style port defs accept range 3-4
        # but reference reports MaxSize=3 when a size-3 rack is installed.
        if port_def:
            pmin = port_def.get("minSize", size)
            pmax = port_def.get("maxSize", size)
            entry["MinSize"] = pmin
            if (full_type == "MissileLauncher.MissileRack"
                    or full_type == "BombLauncher.BombRack") and size:
                entry["MaxSize"] = min(pmax, size)
            else:
                entry["MaxSize"] = pmax
        else:
            entry["MinSize"] = size
            entry["MaxSize"] = size
        # Pick Loadout form to match source. If the source loadout entry
        # used a className (entityClassName), emit className; if it used a
        # GUID reference (entityClassReference), emit the GUID. Default to
        # GUID when source form is missing or only entity_class is known.
        item_guid = item_record.get("guid", "") if item_record else ""
        src_class = source_entry.get("entityClassName", "") if source_entry else ""
        src_ref = source_entry.get("entityClassReference", "") if source_entry else ""
        if src_class and not src_ref:
            entry["Loadout"] = src_class or entity_class
        elif src_ref:
            entry["Loadout"] = src_ref or item_guid or entity_class
        else:
            entry["Loadout"] = item_guid or entity_class
        # BaseLoadout.Class: look up via manufacturer class map (matches stditem.py)
        from .stditem import (MANUFACTURER_CLASS, _COMPONENT_TYPES_CLASSED,
                                _CLASS_VALUE_OVERRIDES)
        base_type = full_type.split(".")[0] if full_type else ""
        mfr_code = (mfr or {}).get("Code", "") if mfr else ""
        bl_class = ""
        if entity_class in _CLASS_VALUE_OVERRIDES:
            bl_class = _CLASS_VALUE_OVERRIDES[entity_class]
        elif base_type in _COMPONENT_TYPES_CLASSED and mfr_code:
            if full_type == "LifeSupportGenerator.UNDEFINED":
                # Capital-class (size 4) is ship-integrated; smaller sizes
                # are player-purchasable civilian grade.
                bl_class = "" if ad.get("size") == 4 else "Civilian"
            else:
                bl_class = MANUFACTURER_CLASS.get(mfr_code, "")
        # Reference's BaseLoadout.Class behaviour is type-specific: it
        # consistently omits Class for FlightController, WheeledController,
        # Display, Room, ToolArm, and a handful of controller-style turrets,
        # but emits Class (often empty) for everything else. Mirror that
        # by suppressing Class only for types known to omit it.
        # Resolve Name with fallback to className when localization is the
        # generic "<= PLACEHOLDER =>" / @LOC_PLACEHOLDER marker (Apollo OC
        # rooms, Retaliator OC rooms — reference uses className in this case).
        # Also fall back when the resolved name is @LOC_EMPTY or an
        # unresolved @itemPort_* marker (Reclaimer/MOTH/Vulture/Fortune/
        # Salvation salvage arms).
        bl_name = ctx.resolve_name(ad.get("name", ""))
        if (bl_name == "<= PLACEHOLDER =>" or bl_name == "@LOC_PLACEHOLDER"
                or bl_name == "@LOC_EMPTY"
                or (bl_name and bl_name.startswith("@itemPort_"))
                or (bl_name and bl_name.startswith("@item_Name"))
                or not bl_name):
            bl_name = entity_class
        bl = {
            "ClassName": entity_class,
            "Name": bl_name,
            "Type": full_type,
            "Size": size,
            "Grade": ad.get("grade", 0),
        }
        if (not _omit_baseloadout_class(full_type)
                and entity_class not in _BASELOADOUT_CLASS_OMIT_MISSILERACKS
                and entity_class not in _BASELOADOUT_CLASS_OMIT_TURRETS
                and entity_class not in _BASELOADOUT_CLASS_OMIT_COMPONENTS):
            bl["Class"] = bl_class
        elif full_type == "FlightController.UNDEFINED":
            # Custom-named flight blades (item name like
            # "@item_name_FLBL_<ship>_standard") emit Class:"" instead of
            # omitting the field entirely. Generic blades (item name
            # "@item_Name_FLGT_BL_Controller") still omit Class.
            if ad.get("name", "").startswith("@item_name_FLBL_"):
                bl["Class"] = ""
        entry["BaseLoadout"] = bl
        # Types: use the port definition's declared types list if present
        # and non-empty. When the port_def exists but has an empty types list
        # (ship-internal ports on Centurion/Hull/Prospector/etc.), reference
        # omits Types from the entry entirely — do NOT fall back to the
        # installed item's declared type. Only use the item type fallback
        # when no port_def was found at all.
        if port_def and port_def.get("types"):
            entry["Types"] = port_def["types"]
        elif not port_def and full_type:
            # Strip generic component subtypes that reference omits when
            # falling back to item type (PowerPlant.Power → PowerPlant,
            # *.UNDEFINED → *). Other Type.SubType pairs pass through.
            t = full_type
            if t.endswith(".UNDEFINED"):
                t = t[:-len(".UNDEFINED")]
            elif t == "PowerPlant.Power":
                t = "PowerPlant"
            entry["Types"] = [t]

        # Flags from port definition. Reference preserves "uneditable" in
        # the Flags list AND sets the Uneditable field; mirror both.
        # port_def["flags"] is a list when sourced from the impl XML parser,
        # but a whitespace-separated string when sourced from an item's own
        # components.ports list (parsed_items.json). Normalize to list.
        if port_def and port_def.get("flags"):
            raw = port_def["flags"]
            if isinstance(raw, str):
                entry["Flags"] = [f for f in raw.split() if f]
            else:
                entry["Flags"] = list(raw)

        # Gimballed / Turret / Fixed flags: Turret.GunTurret mounts are gimbals
        # (pilot aims, mount tracks) -> Gimballed:true. Other Turret.* /
        # TurretBase.* types (BallTurret/NoseMounted/Canard/Top/Bottom/PDC/
        # MannedTurret/Unmanned/MissileTurret) -> Turret:true. WeaponGun.*
        # mounts are direct weapon hardpoints with no gimbal -> Fixed:true.
        # Tractor-beam mounts (UtilityHardpoints) skip these flags entirely
        # in the reference even though they're typed Turret.GunTurret.
        is_tractor = ("tractor" in port_name.lower()
                      or "tractor" in (entity_class or "").lower())
        if not is_tractor:
            if full_type == "Turret.GunTurret":
                entry["Gimballed"] = True
            elif full_type.startswith("Turret.") or full_type.startswith("TurretBase."):
                # Other Turret subtypes (NoseMounted/BallTurret/Canard/...)
                # are not gimbals — REF emits Turret=True even when the item
                # className contains 'gimbal' (e.g. MISC_Starlancer_Dual_Gimbal).
                entry["Turret"] = True
            elif full_type.startswith("WeaponGun.") and not is_sub_port:
                entry["Fixed"] = True

        # PortTags from vehicle impl port definition
        if port_def:
            pt = port_def.get("portTags", "")
            if pt:
                entry["PortTags"] = pt.split()
            rt = port_def.get("requiredPortTags", "")
            if rt:
                # Preserve original tag casing and $ prefix — reference
                # mirrors the impl XML exactly (both "VanguardNose" and
                # "$AEGS_Idris_Nose" forms appear).
                entry["RequiredTags"] = rt.split()
        # Module entries (Apollo/Retaliator modular rooms) inherit PortTags
        # from the installed module item's attachDef.tags when the impl-XML
        # port itself carries no portTags. Reference shows e.g.
        # PortTags=['AEGS_Retaliator_Module_Rear'] from the module item.
        if (full_type.startswith("Module.")
                and "PortTags" not in entry and ad.get("tags")):
            entry["PortTags"] = ad["tags"].split()
        # FlightController (FlightBlade) entries: variants share the base
        # vehicle's impl XML, which carries the BASE ship's portTags
        # (e.g. ANVL_Pisces_Base_Blade). Reference uses the installed
        # item's attachDef.tags instead (ANVL_Pisces_C8R_Blade etc.).
        # Override with item tags whenever the item has a tag.
        if full_type == "FlightController.UNDEFINED" and ad.get("tags"):
            entry["PortTags"] = ad["tags"].split()
            # Mirror RequiredTags too — variant impl_only port uses base.
            req = ad.get("requiredTags", "")
            if req:
                entry["RequiredTags"] = ["$" + t if not t.startswith("$") else t
                                          for t in req.split()]

        # RequiredTags are taken only from the port's requiredPortTags.
        # The installed item's AttachDef.requiredTags describes what the item
        # WANTS mounted on (e.g. "$AEGS_Idris_Nose") — not what the port
        # requires of its installed item. Reference never pulls those through
        # to the hardpoint entry.

        # Build sub-ports from children
        # Sub-port Tags come from THIS item's AttachDef tags (the parent),
        # describing the port's capability, not the installed child's tags
        parent_tags_str = ad.get("tags", "")
        parent_tags = parent_tags_str.split() if parent_tags_str else []

        # Top-level turret items (Turret.* / TurretBase.*) carry their weapon
        # in the ITEM's defaultLoadout rather than the ship loadout; the ship
        # just mounts the turret. Fall back to the item's internal loadout
        # for the weapon-inside-turret sub-port when the outer loadout entry
        # had no children. Scoped to turret-like items to avoid over-emitting
        # internal ports on non-turret items (life-support, radars, etc.).
        # Modules (RSI_Apollo modular rooms, AEGS_Retaliator front/rear modules)
        # follow the same pattern: ship loadout references just the module,
        # the OC room sub-port comes from the module item's defaultLoadout.
        if not children and not is_sub_port and (
            full_type.startswith("Turret.") or full_type.startswith("TurretBase.")
            or full_type.startswith("Module.")
        ):
            item_default = item_record.get("components", {}).get("defaultLoadout", [])
            if item_default:
                children = item_default

        # When the parent item is a turret or a missile/bomb rack, reference
        # only emits weapon-like sub-ports (the guns / missiles inside).
        # Ship loadouts often enumerate cockpit displays, seat-access panels,
        # Room OC ports, AttachedPart inner tubes (Polaris torpedo rack), etc.
        # — ref filters those out. Scope the filter to turret/rack parents so
        # non-turret items (e.g. CrewControlled salvage mounts) keep their
        # full sub-port list.
        is_turret_parent = (
            full_type.startswith("Turret.") or full_type.startswith("TurretBase.")
            or full_type.startswith("MissileLauncher.")
            or full_type.startswith("BombLauncher.")
            or full_type.startswith("GroundVehicleMissileLauncher.")
        )
        _WEAPON_SUB_TYPES = (
            "WeaponGun.", "Turret.", "TurretBase.", "MissileLauncher.",
            "GroundVehicleMissileLauncher.", "BombLauncher.", "Bomb.",
            "WeaponMining.", "Missile.",
        )

        if children:
            sub_items = []
            for child in children:
                child_class, child_record = _resolve_entry(child, ctx)
                child_children = child.get("children", [])
                # Sub-port definitions come from the parent item's component
                # ports list. Match case-insensitively because the loadout
                # may store names in lower case while the item ports use
                # camelCase (e.g. "hardpoint_jump_drive" vs "hardpoint_Jump_Drive").
                child_pn_loadout = child.get("portName", "")
                child_port_def = None
                child_ports = item_record.get("components", {}).get("ports", [])
                for cp in child_ports:
                    if cp.get("name", "").lower() == child_pn_loadout.lower():
                        child_port_def = cp
                        break
                # Turret/rack filter: drop this child if none of its port
                # types match a weapon-sub prefix. Uses the port def's
                # declared types first; falls back to the installed item's
                # type.
                if is_turret_parent:
                    child_types = list(child_port_def.get("types") or []) if child_port_def else []
                    if not child_types and child_record:
                        t = _full_type(child_record.get("attachDef", {}))
                        if t:
                            child_types = [t]
                    if not any(
                        any(t == p.rstrip(".") or t.startswith(p) for p in _WEAPON_SUB_TYPES)
                        for t in child_types
                    ):
                        continue
                    # MissileRack/BombLauncher rack parents: drop sub-ports
                    # that don't exist in the rack item's port list. Hornet
                    # F7CM_Heartseeker installs a 4-missile loadout chain on
                    # a 2-missile rack (MRCK_S03_BEHR_Dual_S02 has only
                    # missile_01/02_attach defined); REF respects the rack's
                    # port list and excludes missile_03/04.
                    if (full_type.startswith("MissileLauncher.")
                            or full_type.startswith("BombLauncher.")
                            or full_type.startswith("GroundVehicleMissileLauncher.")):
                        if child_port_def is None:
                            continue
                # Reference uses the item's canonical PortName casing.
                child_pn = child_port_def.get("name") if child_port_def else child_pn_loadout
                sub = _build_standard_entry(
                    child_pn, child_class, child_record, child_children, ctx,
                    child_port_def, parent_tags, source_entry=child, is_sub_port=True
                )
                if sub:
                    sub_items.append(sub)
            if sub_items:
                entry["Ports"] = sub_items

    elif entity_class:
        # Fallback path when no item record was resolved — best we can do is
        # the className; reference would have a GUID but we lack the lookup.
        entry["Loadout"] = entity_class
    else:
        # Empty mount slot (no item installed): reference still emits port
        # definition (MinSize/MaxSize/Types/Flags). Fill from port_def only.
        if port_def:
            mn = port_def.get("minSize")
            mx = port_def.get("maxSize")
            if mn is not None:
                entry["MinSize"] = mn
            if mx is not None:
                entry["MaxSize"] = mx
            types_list = port_def.get("types") or []
            if types_list:
                entry["Types"] = list(types_list)
            flags_raw = port_def.get("flags")
            if isinstance(flags_raw, list) and flags_raw:
                entry["Flags"] = list(flags_raw)
            elif isinstance(flags_raw, str) and flags_raw:
                entry["Flags"] = [f for f in flags_raw.split() if f]

    # Uneditable mirrors the impl-XML port "uneditable" flag.
    entry["Uneditable"] = bool(port_def and port_def.get("uneditable"))
    return entry


def _build_thruster_entry(port_name, entity_class, item_record, ctx):
    """Build a thruster entry (different format from standard hardpoints)."""
    entry = {
        "Name": port_name,
        "Uneditable": True,
    }

    if item_record:
        ad = item_record.get("attachDef", {})
        comps = item_record.get("components", {})
        physics = comps.get("physics", {})
        health_comp = comps.get("health", {})

        entry["Size"] = ad.get("size", 0)
        entry["Mass"] = physics.get("mass", 0)
        entry["Grade"] = ad.get("grade", 0)

        # Thruster-specific params
        thruster_comp = comps.get("SCItemThrusterParams", {})
        if thruster_comp:
            tc = safe_float(thruster_comp.get("thrustCapacity", "0"))
            if tc:
                entry["ThrustCapacity"] = tc

            # Fuel burn rate from resource network variant
            rn = thruster_comp.get("fuelBurnRatePer10KNewtonRN", {})
            sru = rn.get("SStandardResourceUnit", {}) if isinstance(rn, dict) else {}
            rate_rn = safe_float(sru.get("standardResourceUnits", "0")) if isinstance(sru, dict) else 0
            if rate_rn:
                entry["FuelBurnRatePerMN"] = round(rate_rn * 1e8, 4)
                if tc:
                    entry["FuelUsagePerSecond"] = round(tc * rate_rn * 100, 4)

        if health_comp:
            entry["Durability"] = {"Health": health_comp.get("health", 0)}

    return entry


def _build_cm_entry(port_name, entity_class, item_record, ctx):
    """Build a countermeasure entry."""
    # Bespoke countermeasure items (e.g. AEGS_Firebird_CML_Flare) often have
    # an unresolved @LOC_PLACEHOLDER name. Reference falls back to the
    # className in that case rather than emitting the placeholder marker.
    name = ctx.resolve_name(item_record.get("attachDef", {}).get("name", "")) if item_record else port_name
    if "PLACEHOLDER" in name and entity_class:
        name = entity_class
    entry = {
        "Name": name,
        "Uneditable": True,
    }

    if item_record:
        ad = item_record.get("attachDef", {})
        comps = item_record.get("components", {})

        entry["Size"] = ad.get("size", 0)
        entry["Grade"] = ad.get("grade", 0)

        physics = comps.get("physics", {})
        if physics:
            entry["Mass"] = physics.get("mass", 0)

        # Ammo data for countermeasure
        ammo_comp = comps.get("ammo", {})
        if ammo_comp:
            # Reference emits Ammunition as float (48.0 not 48).
            entry["Ammunition"] = float(ammo_comp.get("maxAmmoCount", 0))
            ammo_data = ctx.get_ammo(ammo_comp.get("ammoParamsRecord", ""))
            if ammo_data:
                entry["Speed"] = ammo_data.get("speed", 0)
                lifetime = ammo_data.get("lifetime", 0)
                entry["Range"] = ammo_data.get("speed", 0) * lifetime

        # Type from item type
        item_type = ad.get("type", "")
        if "noise" in entity_class.lower() or "chaff" in entity_class.lower():
            entry["Type"] = "Noise"
        elif "flare" in entity_class.lower() or "decoy" in entity_class.lower():
            entry["Type"] = "Decoy"
        else:
            entry["Type"] = item_type

    return entry


def _build_simple_entry(port_name, entity_class, item_record, ctx, use_display_name=False):
    """Build a simple entry for fuel tanks, intakes, etc.

    Name convention is category-dependent in the reference:
      QuantumFuelTanks → localized item name ("Internal Tank")
      HydrogenFuelTanks, FuelIntakes → raw port name (e.g. "hardpoint_fuel_tank_left")
    Caller passes use_display_name=True for QuantumFuelTanks only.
    """
    name = port_name
    if use_display_name and item_record:
        ad_name = item_record.get("attachDef", {}).get("name", "")
        if ad_name:
            resolved = ctx.resolve_name(ad_name)
            if resolved and not resolved.startswith("@LOC_") and "PLACEHOLDER" not in resolved:
                name = resolved
    entry = {"Name": name}

    if item_record:
        ad = item_record.get("attachDef", {})
        entry["Size"] = ad.get("size", 0)
        # Mass from physics (always emit, even if 0 — fuel tanks often have 0)
        physics = item_record.get("components", {}).get("physics", {})
        entry["Mass"] = float(physics.get("mass", 0) or 0)
        entry["Grade"] = ad.get("grade", 0)
        # FuelIntake rate from SCItemFuelIntakeParams.fuelPushRate
        fi = item_record.get("components", {}).get("SCItemFuelIntakeParams", {})
        if isinstance(fi, dict):
            rate = fi.get("fuelPushRate")
            if rate is not None:
                entry["FuelIntakeRate"] = float(rate)
        # Capacity from ResourceContainer.capacity.SStandardCargoUnit.standardCargoUnits
        rc = item_record.get("components", {}).get("ResourceContainer", {})
        if isinstance(rc, dict):
            cap = rc.get("capacity", {})
            if isinstance(cap, dict):
                std = cap.get("SStandardCargoUnit", {})
                if isinstance(std, dict):
                    units = std.get("standardCargoUnits")
                    if units is not None:
                        entry["Capacity"] = float(units)

    entry["Uneditable"] = True
    return entry


def _build_cargo_container_entry(port_name, entity_class, item_record, ctx):
    """Build a CargoContainers entry (mining ore pods, Hornet F7C cargo pod).

    Ref shape: {Name, Mass, Size, Grade, Capacity} — no Uneditable.
    Capacity is the ore-storage capacity from `ResourceContainer.capacity`
    (gameplay-cargo SCU), not `attachDef.volume` (physical fitment volume).
    Verified 2026-05-05: Mole pod has volume=8 SCU but holds 12 SCU of ore;
    ROC pod has volume=2.5 SCU but holds 1.2 SCU. REF emits the
    ResourceContainer value. Falls back to attachDef.volume for non-mining
    cargo pods (Hornet F7C) which lack a ResourceContainer.
    """
    if not item_record:
        return None
    ad = item_record.get("attachDef", {})
    name = ctx.resolve_name(ad.get("name", ""))
    if "PLACEHOLDER" in name or not name:
        if entity_class:
            name = entity_class
        else:
            return None
    comps = item_record.get("components", {}) or {}
    physics = comps.get("physics", {})
    entry = {
        "Name": name,
        "Mass": float(physics.get("mass", 0) or 0),
        "Size": ad.get("size", 1),
        "Grade": ad.get("grade", 1),
    }
    capacity = None
    rc = comps.get("ResourceContainer", {})
    if isinstance(rc, dict):
        cap_block = rc.get("capacity", {})
        scu = cap_block.get("SStandardCargoUnit", {}) if isinstance(cap_block, dict) else {}
        if isinstance(scu, dict) and scu.get("standardCargoUnits") is not None:
            try:
                capacity = float(scu["standardCargoUnits"])
            except (TypeError, ValueError):
                capacity = None
    if capacity is None and ad.get("volume"):
        capacity = round(ad["volume"] / 1000000.0, 2)
    if capacity is not None:
        entry["Capacity"] = round(capacity, 2)
    return entry


def _build_storage_entry(port_name, entity_class, item_record, ctx):
    """Build a storage entry.

    Returns None when the entry should be skipped entirely: item unresolved,
    item resolves to @LOC_PLACEHOLDER marker, item type is Container.UNDEFINED
    (decorative containers like sirens, door-mounts — reference only includes
    Container.Cargo), or the item has no volume (empty mount slot).
    """
    if not item_record:
        return None

    ad = item_record.get("attachDef", {})
    t = ad.get("type", "")
    st = ad.get("subType", "")
    full = f"{t}.{st}" if t and st else t
    # Decorative containers (sirens, siren lights, ambient decor) are
    # Container.UNDEFINED and reference omits them from Storage.
    if full == "Container.UNDEFINED":
        return None
    # Capacity derives from volume (microSCU). Reference omits entries whose
    # rounded capacity is zero — those are empty mount slots on the ship
    # body (PersonalStorage_ANVL_C8R with volume=1 microSCU, etc.). The
    # real cargo with the matching Name appears via _compute_storage when
    # the attached inventory container has meaningful capacity.
    raw_vol = ad.get("volume", 0) or 0
    capacity = round(raw_vol / 1000000.0, 2)
    if capacity <= 0:
        return None

    name = ctx.resolve_name(ad.get("name", ""))
    if "PLACEHOLDER" in name or not name:
        if entity_class:
            name = entity_class
        else:
            return None

    entry = {
        "Name": name,
        "Uneditable": True,
        "Size": ad.get("size", 0),
        "Grade": ad.get("grade", 0),
        "Capacity": capacity,
    }
    return entry


def _full_type(attach_def):
    """Build full type string, preserving .UNDEFINED suffix to match ref."""
    t = attach_def.get("type", "")
    st = attach_def.get("subType", "")
    if t and st:
        return f"{t}.{st}"
    return t


# ──────────────────────────────────────────────────────────────────────
# Tree placement
# ──────────────────────────────────────────────────────────────────────

_PLACEMENT = {
    # Weapons
    "PilotWeapons":         ("Weapons", "PilotWeapons"),
    "Turrets":              ("Weapons", "MannedTurrets"),  # Default; could be refined
    "RemoteTurrets":        ("Weapons", "RemoteTurrets"),
    "PDCTurrets":           ("Weapons", "PDCTurrets"),
    "MissileRacks":         ("Weapons", "MissileRacks"),
    "BombRacks":            ("Weapons", "BombRacks"),
    "InterdictionHardpoints": ("Weapons", "InterdictionHardpoints"),
    "MiningHardpoints":     ("Weapons", "MiningHardpoints"),
    "SalvageHardpoints":    ("Weapons", "SalvageHardpoints"),
    "UtilityHardpoints":    ("Weapons", "UtilityHardpoints"),
    # Components > Propulsion
    "PowerPlants":          ("Components", "Propulsion", "PowerPlants"),
    "QuantumDrives":        ("Components", "Propulsion", "QuantumDrives"),
    "MainThrusters":        ("Components", "Propulsion", "Thrusters", "MainThrusters"),
    "RetroThrusters":       ("Components", "Propulsion", "Thrusters", "RetroThrusters"),
    "VtolThrusters":        ("Components", "Propulsion", "Thrusters", "VtolThrusters"),
    "ManeuveringThrusters": ("Components", "Propulsion", "Thrusters", "ManeuveringThrusters"),
    "QuantumFuelTanks":     ("Components", "Propulsion", "QuantumFuelTanks"),
    "HydrogenFuelTanks":    ("Components", "Propulsion", "HydrogenFuelTanks"),
    # Components > Systems
    "ShieldControllers":    ("Components", "Systems", "Controllers"),
    "WheeledController":    ("Components", "Systems", "Controllers", "Wheeled"),
    "Shields":              ("Components", "Systems", "Shields"),
    "Coolers":              ("Components", "Systems", "Coolers"),
    "LifeSupport":          ("Components", "Systems", "LifeSupport"),
    "FuelIntakes":          ("Components", "Systems", "FuelIntakes"),
    "Countermeasures":      ("Components", "Systems", "Countermeasures"),
    # Components > Avionics
    "FlightBlade":          ("Components", "Avionics", "FlightBlade"),
    "Radars":               ("Components", "Avionics", "Radars"),
    "SelfDestruct":         ("Components", "Avionics", "SelfDestruct"),
    # Components > Other
    "Modules":              ("Components", "Modules"),
    "Storage":              ("Components", "Storage"),
    "WeaponsRacks":         ("Components", "WeaponsRacks"),
    "Paints":               ("Components", "Paints"),
    "Flairs":               ("Components", "Flairs"),
    "Armor":                ("Components", "Armor"),
    "CargoGrids":           ("Components", "CargoGrids"),
    "CargoContainers":      ("Components", "CargoContainers"),
}


def _place(tree, category, entry):
    """Place a hardpoint entry into the correct position in the tree."""
    path = _PLACEMENT.get(category)
    if not path:
        return

    # Categories that ref sub-categorizes in a further nested dict:
    # - InterdictionHardpoints → EMP / QED (by item Type)
    # - MiningHardpoints → PilotControlled / CrewControlled (by item Type)
    # - SalvageHardpoints → PilotControlled / CrewControlled (by item Type)
    sub_key = None
    if category == "InterdictionHardpoints":
        item_type = (entry.get("BaseLoadout", {}).get("Type", "") or "").split(".")[0]
        if item_type.startswith("EMP"):
            sub_key = "EMP"
        elif "QuantumInterdictionGenerator" in item_type or "QED" in item_type:
            sub_key = "QED"
        else:
            # Fallback: port-name based routing for items typed Misc/etc.
            # MRAI_Guardian hardpoint_quantum_damp installs a Misc.UNDEFINED
            # mohawk piece that the reference still categorizes under QED.
            pn = (entry.get("PortName", "") or "").lower()
            if "quantum_damp" in pn or "qed" in pn or "interdiction" in pn:
                sub_key = "QED"
            elif "emp" in pn:
                sub_key = "EMP"
    elif category in ("MiningHardpoints", "SalvageHardpoints"):
        item_type = entry.get("BaseLoadout", {}).get("Type", "") or ""
        # ToolArm.* → PilotControlled (pilot operates from cockpit)
        # UtilityTurret.MannedTurret / Turret.Utility → CrewControlled
        if item_type.startswith("ToolArm"):
            sub_key = "PilotControlled"
        elif "MannedTurret" in item_type or item_type.startswith("Turret.Utility"):
            sub_key = "CrewControlled"
        else:
            sub_key = "PilotControlled"  # default fallback

    node = tree
    for key in path:
        if key not in node:
            node[key] = {}
        node = node[key]

    if sub_key:
        if sub_key not in node:
            # Initialize using the category's count-key convention
            count_key = "ItemsQuantity" if (category == "SalvageHardpoints"
                                             and sub_key in ("Buff", "SalvageBuffer")) else "Hardpoints"
            node[sub_key] = {"InstalledItems": [], count_key: 0}
        node = node[sub_key]

    if "InstalledItems" in node:
        node["InstalledItems"].append(entry)
    elif isinstance(node, dict):
        node.setdefault("InstalledItems", []).append(entry)


def _count_hardpoints(items):
    """Count hardpoints recursively: top-level items + all nested Ports.

    Matches ref convention where e.g. PilotWeapons.Hardpoints counts both
    the turret mounts AND the weapon slots inside them.
    """
    total = len(items)
    for it in items:
        if isinstance(it, dict):
            total += _count_hardpoints(it.get("Ports", []))
    return total


# Item types EXCLUDED from PilotWeapons.Hardpoints count (per architecture
# investigation in docs/xml_architecture.md): missile/bomb attachments and
# their carriers don't contribute to PW Hardpoints in reference.
_PW_COUNT_EXCLUDE_TYPES = (
    "Missile.", "MissileLauncher.", "GroundVehicleMissileLauncher.",
    "BombLauncher.", "Bomb.",
)


def _count_pw_hardpoints(items):
    """PilotWeapons-specific Hardpoints count: recursive but skips
    missile/bomb subtrees (per docs/xml_architecture.md Section 11).

    Hornet F7CM_Mk2 weapon_center has a missile rack with 8 missile slots
    in the loadout tree; reference's PW.Hardpoints excludes those entirely.
    """
    total = 0
    for it in items:
        if not isinstance(it, dict):
            total += 1
            continue
        bl = it.get("BaseLoadout") if isinstance(it.get("BaseLoadout"), dict) else {}
        t = bl.get("Type", "") or ""
        if any(t.startswith(p) for p in _PW_COUNT_EXCLUDE_TYPES):
            continue
        total += 1
        total += _count_pw_hardpoints(it.get("Ports", []))
    return total


# Categories whose Hardpoints count includes nested Ports recursively.
# RemoteTurrets and UtilityHardpoints use len(InstalledItems) to match ref.
# MannedTurrets/PilotWeapons need a deeper formula that walks each installed
# item's own port definitions (not just the loadout tree) — current recursive
# count over loadout `Ports` undercounts but is closer than len.
_WEAPON_CATEGORIES_RECURSIVE_COUNT = {
    "PilotWeapons", "MannedTurrets", "UtilityTurrets",
}


def _update_counts(tree, parent_key=""):
    """Recursively update Hardpoints/ItemsQuantity counts."""
    if not isinstance(tree, dict):
        return
    for key, val in tree.items():
        if isinstance(val, dict):
            _update_counts(val, key)
            if "InstalledItems" in val:
                items = val["InstalledItems"]
                if key == "PilotWeapons":
                    count = _count_pw_hardpoints(items)
                elif key in _WEAPON_CATEGORIES_RECURSIVE_COUNT:
                    count = _count_hardpoints(items)
                else:
                    count = len(items)
                if "Hardpoints" in val:
                    val["Hardpoints"] = count
                elif "ItemsQuantity" in val:
                    val["ItemsQuantity"] = count


# Weapon categories under Hardpoints.Weapons that collapse to {} when empty
# (ref convention — if no items installed AND no slot count, emit empty dict).
_WEAPON_CATEGORIES_COLLAPSE_EMPTY = (
    "PilotWeapons", "MannedTurrets", "RemoteTurrets", "PDCTurrets",
    "MissileRacks", "BombRacks", "UtilityHardpoints", "UtilityTurrets",
    "InterdictionHardpoints", "MiningHardpoints", "SalvageHardpoints",
)


def _collapse_empty_categories(tree):
    """Normalize empty categories to match ref format.

    Converts `{InstalledItems: [], Hardpoints: 0}` → `{}` for categories in
    `_WEAPON_CATEGORIES_COLLAPSE_EMPTY` and `_COMPONENT_CATEGORIES_COLLAPSE_EMPTY`.
    Preserves sub-categorized blocks (e.g. InterdictionHardpoints.EMP).

    For Components.WeaponsRacks/Storage: when InstalledItems is empty, strip
    that key (keep only `{ItemsQuantity: N}`). Matches ref shape.
    """
    weapons = tree.get("Weapons", {})
    for cat in _WEAPON_CATEGORIES_COLLAPSE_EMPTY:
        block = weapons.get(cat)
        if not isinstance(block, dict):
            continue
        installed = block.get("InstalledItems") or []
        count = block.get("Hardpoints", 0)
        has_sub = any(
            isinstance(v, dict) and (v.get("InstalledItems") or v.get("Hardpoints") or v.get("ItemsQuantity"))
            for k, v in block.items()
            if k not in ("InstalledItems", "Hardpoints", "ItemsQuantity")
        )
        if not installed and not count and not has_sub:
            weapons[cat] = {}
        elif has_sub:
            if "InstalledItems" in block and not block["InstalledItems"]:
                del block["InstalledItems"]
            if "Hardpoints" in block and not block["Hardpoints"]:
                del block["Hardpoints"]

    # Components: Modules/Paints/Flairs collapse to {} when empty
    components = tree.get("Components", {})
    for cat in ("Modules", "Paints", "Flairs"):
        block = components.get(cat)
        if not isinstance(block, dict):
            continue
        installed = block.get("InstalledItems") or []
        count = block.get("Hardpoints", 0)
        if not installed and not count:
            components[cat] = {}
    # Paints entries don't carry BaseLoadout in reference — strip it.
    paints_block = components.get("Paints")
    if isinstance(paints_block, dict):
        for it in paints_block.get("InstalledItems", []):
            if isinstance(it, dict) and "BaseLoadout" in it:
                del it["BaseLoadout"]

    # Components: CargoGrids/WeaponsRacks/Storage drop empty InstalledItems
    # (keep ItemsQuantity). Ref shape for empty containers is just {ItemsQuantity: 0}.
    for cat in ("CargoGrids", "CargoContainers", "WeaponsRacks", "Storage"):
        block = components.get(cat)
        if not isinstance(block, dict):
            continue
        if not (block.get("InstalledItems") or []):
            if "InstalledItems" in block:
                del block["InstalledItems"]

    # Components.Propulsion: QuantumDrives collapses to {} when empty;
    # Thrusters/FuelTanks drop empty InstalledItems (keep ItemsQuantity + totals).
    propulsion = components.get("Propulsion", {})
    for cat in ("QuantumDrives",):
        block = propulsion.get(cat)
        if isinstance(block, dict) and not (block.get("InstalledItems") or []) and not block.get("Hardpoints", 0):
            propulsion[cat] = {}
    thrusters = propulsion.get("Thrusters", {})
    for cat in ("MainThrusters", "RetroThrusters", "VtolThrusters", "ManeuveringThrusters"):
        block = thrusters.get(cat)
        if isinstance(block, dict) and not (block.get("InstalledItems") or []):
            if "InstalledItems" in block:
                del block["InstalledItems"]
    for cat in ("HydrogenFuelTanks", "QuantumFuelTanks"):
        block = propulsion.get(cat)
        if isinstance(block, dict) and not (block.get("InstalledItems") or []):
            if "InstalledItems" in block:
                del block["InstalledItems"]

    # Components.Systems: collapse empty LifeSupport/Countermeasures/FuelIntakes/Shields
    systems = components.get("Systems", {})
    # LifeSupport collapses to {} when empty
    ls = systems.get("LifeSupport")
    if isinstance(ls, dict) and not (ls.get("InstalledItems") or []):
        systems["LifeSupport"] = {}
    # Countermeasures/FuelIntakes: drop empty InstalledItems
    for cat in ("Countermeasures", "FuelIntakes"):
        block = systems.get(cat)
        if isinstance(block, dict) and not (block.get("InstalledItems") or []):
            if "InstalledItems" in block:
                del block["InstalledItems"]
    # Shields: when InstalledItems is empty, drop both InstalledItems and
    # Hardpoints (ground vehicles like HoverQuad/Dragonfly/ROC keep only
    # FaceType / MaxItem on the Shields node).
    shields_block = systems.get("Shields")
    if isinstance(shields_block, dict) and not (shields_block.get("InstalledItems") or []):
        if "InstalledItems" in shields_block:
            del shields_block["InstalledItems"]
        if "Hardpoints" in shields_block:
            del shields_block["Hardpoints"]

    # Components.Avionics: FlightBlade collapses to {} when empty;
    # Radars/SelfDestruct drop empty InstalledItems.
    avionics = components.get("Avionics", {})
    fb = avionics.get("FlightBlade")
    if isinstance(fb, dict) and not (fb.get("InstalledItems") or []) and not fb.get("Hardpoints", 0):
        avionics["FlightBlade"] = {}
    for cat in ("Radars", "SelfDestruct"):
        block = avionics.get(cat)
        if isinstance(block, dict) and not (block.get("InstalledItems") or []):
            if "InstalledItems" in block:
                del block["InstalledItems"]

    # Remove Components.Armor (ref doesn't have this key)
    if "Armor" in components:
        del components["Armor"]
