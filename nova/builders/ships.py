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


def _is_cosmetic_variant(class_name, ctx):
    # Identified by nova.cosmetic_classifier: this record differs from
    # another ship sharing the same vehicleDefinition only in cosmetic
    # fields (palette, localization, interior art, paint ports, rename-only
    # modification blocks, or item-level cosmetic twins). Keep the base
    # ClassName only; variant is a paint/skin duplicate.
    return class_name in ctx.cosmetic_variants


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
        if _is_cosmetic_variant(class_name, ctx):
            continue

        ship = _build_ship(class_name, record, ctx)
        if ship:
            is_ground = _is_ground_vehicle(vehicle)
            ship["IsSpaceship"] = not is_ground
            if is_ground:
                ship["Type"] = "Gravlev" if vehicle.get("isGravlevVehicle", False) else "Vehicle"
            else:
                ship["Type"] = "Ship"
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

    ship = {
        "ClassName": class_name,
        "Name": ctx.resolve_name(vehicle.get("vehicleName", class_name)),
        "Description": _clean_description(raw_desc),
        "Manufacturer": mfr.get("Name", "") if mfr else "",
        "Career": ctx.resolve_name(vehicle.get("vehicleCareer", "")),
        "Role": ctx.resolve_name(vehicle.get("vehicleRole", "")),
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

    # Compute storage from seat access inventory containers
    storage_entries = _compute_storage(default_loadout, ctx)
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

    # Cargo from cargo grid inventories in loadout
    cargo = _build_cargo(default_loadout, ctx)
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
    # Find the armor item in the loadout (port name contains "armor"/"armour",
    # or entity class starts with ARMR_). Search recursively through children.
    armor_record = None

    def _find_armor(entries):
        nonlocal armor_record
        for entry in entries:
            pn = entry.get("portName", "").lower()
            entity_class, item = _resolve_entry(entry, ctx)
            if item and ("armor" in pn or "armour" in pn
                         or (entity_class and entity_class.startswith("ARMR_"))):
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


def _omit_baseloadout_class(full_type):
    return full_type in _BASELOADOUT_CLASS_OMIT_TYPES


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
        entry = _cargo_grid_entry_from_item(cn, item, ctx)
        if entry:
            out.append(entry)
    out.sort(key=lambda x: x["Name"])
    return out


def _cargo_grid_entry_from_item(class_name, item, ctx, port_name=None):
    """Render a single CargoGrid InstalledItems entry from a resolved item record.

    Name: uses the item className when it contains "_CargoGrid_" (e.g.
    AEGS_Reclaimer_CargoGrid_Small). Falls back to the port name when the
    item is a generic plate (MISC_Hull_A_CargoPlate → hardpoint_cargoplate_*).
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

    return {
        "Name": name,
        "Mass": float((comps.get("physics") or {}).get("mass", 0)),
        "Size": ad.get("size", 0),
        "Grade": ad.get("grade", 0),
        "Capacity": float(inv.get("capacity", 0)),
        "GridProperties": grid_props,
        "Uneditable": True,
    }


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
                rec = _cargo_grid_entry_from_item(
                    entity_class, item, ctx, port_name=pn
                )
                if rec:
                    out.append(rec)
                    # If this entry produced a grid, its children are the
                    # grid sub-ports — skip them (ref doesn't double-emit).
                    continue
            is_plate = item and "cargoplate" in (entity_class or "").lower()
            child_inherit = entry.get("portName") if is_plate else None
            for child in entry.get("children", []) or []:
                _walk([child], inherited_port=child_inherit)

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
            for p in sub_ports
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


def _build_cargo(loadout_entries, ctx):
    """Compute Cargo SCU from cargo grid and storage inventories in the loadout."""
    cargo_grid_scu = 0.0
    storage_scu = 0.0

    def _walk(entries):
        nonlocal cargo_grid_scu, storage_scu
        for entry in entries:
            pn = entry.get("portName", "").lower()
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {})
                inv_comp = comps.get("SCItemInventoryContainerComponentParams", {})
                if isinstance(inv_comp, dict):
                    container_guid = inv_comp.get("containerParams", "")
                    capacity = ctx.get_inventory_capacity(container_guid)
                    if capacity > 0:
                        if "cargogrid" in pn or "cargo_grid" in pn or "cargo" in pn:
                            cargo_grid_scu += capacity
                        else:
                            storage_scu += capacity
            children = entry.get("children", [])
            if children:
                _walk(children)

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


def _build_flight_characteristics(loadout_entries, ctx):
    """Extract FlightCharacteristics from flight controller (IFCSParams) and thrusters."""
    ifcs = None
    qd_spool = 0.0
    thrust_by_type = {}  # Main/Retro/VTOL/Maneuvering -> total capacity
    has_vtol = False

    def _classify_thruster(port_name, class_name):
        """Classify thruster by port name and class name (thrusterType is unreliable)."""
        pn = port_name.lower()
        cn = class_name.lower()
        if "vtol" in pn or "_vtol" in cn:
            return "VTOL"
        if "retro" in pn or "_retro" in cn:
            return "Retro"
        if any(x in pn for x in ["main_thruster", "thruster_main", "mainthruster", "engine"]):
            return "Main"
        if "_main" in cn and "thruster" in cn:
            return "Main"
        return "Maneuvering"

    def _walk_loadout(entries):
        nonlocal ifcs, qd_spool, has_vtol
        for entry in entries:
            pn = entry.get("portName", "").lower()
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {})

                # Flight controller — IFCSParams
                if ("controller_flight" in pn or "flight_blade" in pn) and "IFCSParams" in comps:
                    ifcs = comps["IFCSParams"]

                # Thrusters — aggregate by classified type
                if "SCItemThrusterParams" in comps:
                    tp = comps["SCItemThrusterParams"]
                    tc = safe_float(tp.get("thrustCapacity", "0"))
                    if tc:
                        tt = _classify_thruster(entry.get("portName", ""), entity_class)
                        thrust_by_type[tt] = thrust_by_type.get(tt, 0.0) + tc
                        if tt == "VTOL":
                            has_vtol = True

                # Quantum drive — spool time comes from StandardJump.SpoolUpTime
                if ("quantum_drive" in pn or "quantumdrive" in pn) and "quantumDrive" in comps:
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

    # MasterModes — BaseSpoolTime defaults to 1.0 (SPViewer convention).
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

    # Boost — from afterburner (old) block, matching SPViewer reference
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
        pn = port_name.lower()
        cn = class_name.lower()
        if "vtol" in pn or "_vtol" in cn:
            return "Vtol"
        if "retro" in pn or "_retro" in cn:
            return "Retro"
        if any(x in pn for x in ["main_thruster", "thruster_main", "mainthruster", "engine"]):
            return "Main"
        if "_main" in cn and "thruster" in cn:
            return "Main"
        return "Maneuvering"

    def _walk(entries):
        nonlocal fuel_capacity, quantum_fuel_capacity, fuel_intake_rate
        for entry in entries:
            pn = entry.get("portName", "").lower()
            entity_class, item_record = _resolve_entry(entry, ctx)
            if item_record:
                comps = item_record.get("components", {})
                ad = item_record.get("attachDef", {})
                item_type = ad.get("type", "")

                # Hydrogen fuel tanks
                if "fuel_tank" in pn and "quantum" not in pn:
                    rc = comps.get("ResourceContainer", {})
                    if isinstance(rc, dict):
                        cap = rc.get("capacity", {})
                        if isinstance(cap, dict):
                            scu = cap.get("SStandardCargoUnit", {})
                            if isinstance(scu, dict):
                                fuel_capacity += safe_float(scu.get("standardCargoUnits", "0"))

                # Quantum fuel tanks
                if "quantum_fuel" in pn:
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


def _classify_port(port_name, item_type="", port_def=None, item_record=None):
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
    """
    pn = port_name.lower()
    it = (item_type or "").lower()
    port_def = port_def or {}
    types = [t.lower() for t in port_def.get("types", []) or []]
    port_tags = (port_def.get("portTags", "") or "").lower()

    # Weapon-rack ports use a Door mechanism (opens to reveal the rack), so
    # the port's type is Door even though the hardpoint is a rack. Check the
    # port name first so these don't get skipped by the Door rule below.
    # Also match by installed item className (ANVL_Valkyrie uses ports named
    # hardpoint_Weapon_Cabinet_* with Weapon_Rack_ANVL_Valkyrie_1Slot items).
    if "weapon_rack" in pn or "weaponlocker" in pn or "weapon_locker" in pn \
            or "weapon_cabinet" in pn:
        return "WeaponsRacks"
    if item_record:
        item_cn = (item_record.get("className", "") or "").lower()
        if item_cn.startswith("weapon_rack_") or "_weapon_rack_" in item_cn:
            return "WeaponsRacks"

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
    if port_def.get("defaultWeaponGroup") is not None \
            and "remote_turret" not in pn and "remoteturret" not in pn \
            and "_remote_" not in pn:
        it_lower = (item_type or "").lower()
        if it_lower.startswith("turret.") or it_lower.startswith("weapongun."):
            return "PilotWeapons"

    # Weapons and weapon-like mounts. Missile/bomb racks that also carry a
    # WeaponGun.Rocket type must be matched BEFORE the WeaponGun branch
    # (bomb racks list both).
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
        return "PilotWeapons"
    if has_type("weapondefensive"):
        return "Countermeasures"
    if has_type("quantuminterdictiongenerator") or has_type("emp"):
        return "InterdictionHardpoints"

    # Turrets — after weapons so gimballed guns (Turret.GunTurret + WeaponGun)
    # are classified as PilotWeapons, not Turrets.
    if has_type("turret"):
        # Tractor-beam turrets carry Turret.GunTurret but belong under
        # UtilityHardpoints. Structural signal: port name ends in
        # `_tractor_turret` / contains tractor_beam; no cleaner type signal
        # exists in the corpus.
        if "tractor" in pn:
            return "UtilityHardpoints"
        # Remote-operated turrets (no occupant; pilot or remote crew member
        # fires from a console). Port name or installed item className is
        # the cleanest discriminator.
        item_cn_lower = ""
        if item_record:
            item_cn_lower = (item_record.get("className", "") or "").lower()
        if ("remote_turret" in pn or "_remote_" in pn or "remoteturret" in pn
                or "_remote_turret" in item_cn_lower or "remote_turret" in item_cn_lower):
            return "RemoteTurrets"
        # Point Defense (PDC) turrets — small autonomous turrets on capitals.
        if "pdc" in pn or "point_defense" in pn:
            return "PDCTurrets"
        # Pilot-controlled mounts carry defaultWeaponGroup on the impl port
        # (assigns the mount to a fire group). Hornet's class-4 center/nose
        # and Mustang's weapon_nose are typed Turret.BallTurret but have a
        # defaultWeaponGroup, so reference classes them as PilotWeapons.
        if port_def.get("defaultWeaponGroup") is not None:
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
        if ift in ("turret.canardturret", "turret.nosemounted"):
            return "PilotWeapons"
        return "Turrets"
    # UtilityTurret (e.g. Cyclone mining cab). Falls after Turret since it
    # currently lands in MiningHardpoints by port name convention.
    if has_type("utilityturret") and "mining" in pn:
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
        if thruster_type_attr == "vtol" or "vtol" in pn or "_vtol" in item_cls_lower:
            return "VtolThrusters"
        if thruster_type_attr == "retro" or "retro" in pn or "_retro" in item_cls_lower or item_cls_lower.endswith("_retro"):
            return "RetroThrusters"
        if has_type("mainthruster") or thruster_type_attr == "main":
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
    if has_type("flair_cockpit"):
        return "Flairs"

    # Salvage family — structural types are several variants.
    # (SalvageController is already in _SKIP_PORT_TYPES.)
    if (has_type("salvagefieldsupporter") or has_type("salvagefillerstation")
            or "salvagemount" in port_tags):
        return "SalvageHardpoints"
    if has_type("toolarm") and ("salvage" in pn or "salvagemount" in port_tags):
        return "SalvageHardpoints"
    if has_type("toolarm") and "mining" in pn:
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
        # Mining-ship ore pods (MOLE mining_pod_*, Prospector, ROC, Golem,
        # Hornet F7C cargo pod) → CargoContainers in reference.
        if "mining_pod" in pn or "ore_pod" in pn or ("pod" in pn and "cargo" in pn):
            return "CargoContainers"
        # "stored_pod" ports on the MOLE are empty spare slots — reference
        # omits them entirely.
        if "stored_pod" in pn:
            return None
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
    # Fires when the port_def has no types entry (e.g. port not in the impl
    # XML, or sub-ports discovered only through the loadout tree).
    if "weapongun" in it:
        return "PilotWeapons"
    if "missilelauncher" in it:
        return "MissileRacks"
    if "weapondefensive" in it:
        return "Countermeasures"
    if "turret" in it:
        # Route by item's full type when port_def is unavailable (port not in
        # impl XML, e.g. Hornet F7CM variant guns). Same heuristic as the
        # has_type("turret") branch: non-manned turret subtypes route by
        # their reference distribution rather than defaulting to MannedTurrets.
        ift = it  # already lowercased
        item_cn_lower = ""
        if item_record:
            item_cn_lower = (item_record.get("className", "") or "").lower()
        if ("remote_turret" in pn or "_remote_" in pn or "remoteturret" in pn
                or "_remote_turret" in item_cn_lower or "remote_turret" in item_cn_lower):
            return "RemoteTurrets"
        if "pdc" in pn or "point_defense" in pn:
            return "PDCTurrets"
        if ift.startswith("turretbase.manned"):
            return "Turrets"
        if ift in ("turretbase.unmanned", "turret.bottomturret",
                   "turret.missileturret", "turret.topturret"):
            return "RemoteTurrets"
        if ift in ("turret.canardturret", "turret.nosemounted",
                   "turret.ballturret", "turret.gunturret"):
            return "PilotWeapons"
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

    # ── Name-based last-resort (documented cases with no single structural
    # signal in the corpus, plus graceful degradation when port_def is empty
    # because the loadout references a port not in the impl XML). ──
    # (weapon_rack is handled at the very top — its Door-typed ports would
    # otherwise be skipped.)

    # Mining/salvage: no single structural type — both mix Container.Cargo,
    # UtilityTurret, ToolArm, SeatAccess etc. depending on ship.
    if "mining" in pn and "controller" not in pn:
        return "MiningHardpoints"
    if "salvage" in pn and "controller" not in pn:
        return "SalvageHardpoints"

    # The following branches fire when port_def lacks structural types (the
    # loadout references a port the vehicle-impl XML did not define) OR
    # when the only types are semantically empty (`Misc`, `Misc.Misc`,
    # `Usable`). Without them the classifier would drop legitimate entries.
    types_are_meaningless = not types or all(
        t in ("misc", "misc.misc", "usable", "useable") for t in types
    )
    if types_are_meaningless:
        if "powerplant" in pn or "power_plant" in pn:
            return "PowerPlants"
        if "quantum_drive" in pn or "quantumdrive" in pn:
            return "QuantumDrives"
        if "quantum_fuel" in pn:
            return "QuantumFuelTanks"
        if "fuel_tank" in pn:
            return "HydrogenFuelTanks"
        if "fuel_intake" in pn:
            return "FuelIntakes"
        if ("engine" in pn or "thruster_main" in pn or "main_thruster" in pn) and "engineering" not in pn:
            return "MainThrusters"
        if "retro" in pn:
            return "RetroThrusters"
        if "thruster_vtol" in pn:
            return "VtolThrusters"
        if "thruster" in pn and "vtol" not in pn:
            return "ManeuveringThrusters"
        if "controller_shield" in pn:
            return None
        if "controller_flight" in pn or "flight_blade" in pn:
            return "FlightBlade"
        if "shield" in pn and "controller" not in pn:
            return "Shields"
        if "cooler" in pn and "controller" not in pn:
            return "Coolers"
        if "lifesupport" in pn or "life_support" in pn:
            return "LifeSupport"
        if "selfdestruct" in pn or "self_destruct" in pn:
            return "SelfDestruct"
        if "radar" in pn and "controller" not in pn:
            return "Radars"
        if "armor" in pn or "armour" in pn:
            return "Armor"
        if "paint" in pn:
            return "Paints"
        if "flair" in pn:
            return "Flairs"
        if "cargogrid" in pn or "cargo_grid" in pn:
            return "CargoGrids"
        if "cm_launcher" in pn or "countermeasure" in pn:
            return "Countermeasures"
        if "missilerack" in pn or "missile_rack" in pn:
            return "MissileRacks"
        if "bomb" in pn:
            return "BombRacks"
        if ("interdiction" in pn or "quantum_enforcement" in pn or "interdiction_device" in pn) and "controller" not in pn:
            return "InterdictionHardpoints"
        if "utility" in pn:
            return "UtilityHardpoints"
        if "tractor" in pn and "turret" in pn:
            return "UtilityHardpoints"
        if "turret_base" in pn or "turret_upper" in pn or "turret_lower" in pn:
            return "Turrets"
        if "turret" in pn and "seataccess" not in pn and "controller" not in pn:
            return "Turrets"
        if (any(p in pn for p in ["gun_", "weapon_pilot", "hardpoint_weapon_"]) or pn.endswith("_weapon")) and "turret" not in pn and "rack" not in pn and "controller" not in pn:
            return "PilotWeapons"
        if "storage" in pn or "personal_storage" in pn:
            return "Storage"
        if "module" in pn:
            return "Modules"
        # Skip-name patterns (seat/display/door/controller) for ports with
        # no types entry.
        if any(skip in pn for skip in [
            "seat_access", "seat_pilot", "seat_copilot", "seat_passenger",
            "escape_pod", "display_hud", "screen_", "cockpit_radar",
            "dashboard", "door_", "relay_", "engineeringscreen",
            "lightgroup", "light_", "controller_door", "controller_light",
            "controller_comms", "controller_energy", "controller_capacitor",
            "controller_fuel", "controller_missile", "controller_weapon",
            "controller_cooler",
            "docking_collar", "fuel_port", "air_traffic",
            "bed_", "battery", "avionics",
        ]):
            return None

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

    for entry in loadout_entries:
        port_name = entry.get("portName", "")
        if not port_name:
            continue

        entity_class, item_record = _resolve_entry(entry, ctx)

        # Skip entries with no resolved entity and no installable children,
        # UNLESS the impl XML defines a weapon-typed port at this location
        # (Hornet F7C_*/Mk2 class_4_nose, Mustang wing_*, Terrapin weapon_nose).
        # Reference emits empty mount slots with MinSize/MaxSize/Types/Flags
        # for pilot-weapon ports that have no loadout item.
        raw_children = entry.get("children", [])
        if not entity_class and not any(
            c.get("entityClassName") or c.get("entityClassReference")
            for c in raw_children
        ):
            # Check if impl declares this as a weapon port that reference
            # emits even when empty.
            _pd = port_defs.get(port_name) or port_defs_lower.get(port_name.lower()) or {}
            _pd_types = [t.lower() for t in _pd.get("types", []) or []]
            is_weapon_slot = any(
                t.startswith("weapongun") or t.startswith("turret") or
                t.startswith("turretbase") or t.startswith("missilelauncher") or
                t.startswith("bomblauncher")
                for t in _pd_types
            )
            if not is_weapon_slot:
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

        category = _classify_port(port_name, item_type, port_def, item_record)
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

    # Add computed storage entries
    if storage_entries:
        for se in storage_entries:
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
        category = _classify_port(port_name, item_type, port_def)
        if category and category in ("Paints", "Flairs"):
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
            _place(tree, category, hp)

    # Radar DetectionCapability
    _enrich_radar_detection(tree, ctx)

    # Shield FaceType + MaxItem
    _enrich_shield_info(tree, loadout_entries, ctx, class_name)

    # Enrich Controllers sub-blocks (Missiles, Weapons, Wheeled)
    _enrich_controllers(tree, loadout_entries, ctx, class_name)

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
            pn = e.get("portName", "").lower()
            if "controller_missile" in pn:
                cn = e.get("entityClassName", "")
                if cn:
                    item = ctx.get_item(cn)
                    if item:
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
    if pool:
        weapons_block["PoolSize"] = float(pool)

    # Look up the ship's engineering buff. Variants like AEGS_Idris_M share
    # a base AEGS_Idris buff, so strip trailing _X / _XX suffixes on miss.
    buff_candidates = [f"Engineering_Buff_Modifier_{class_name}"]
    # Strip final underscore-separated suffix to try the base class.
    parts = class_name.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) <= 4:
        buff_candidates.append(f"Engineering_Buff_Modifier_{parts[0]}")
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
            pn = e.get("portName", "").lower()
            if "controller_flight" in pn or "flight_blade" in pn:
                _, item = _resolve_entry(e, ctx)
                if item:
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
        entry = {
            "Name": ctx.resolve_name(ad.get("name", "")),
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

    # FaceType from shield controller item (hardpoint_controller_shield)
    def _find_shield_controller(entries):
        for entry in entries:
            pn = entry.get("portName", "").lower()
            if "controller_shield" in pn:
                entity_class, item_record = _resolve_entry(entry, ctx)
                if item_record:
                    se = item_record.get("components", {}).get("SCItemShieldEmitterParams", {})
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


def _compute_storage(loadout_entries, ctx):
    """Find storage/inventory entries by checking seat access entities.

    Reference omits storage entries whose item name doesn't resolve (the
    @LOC_PLACEHOLDER fallback) — those represent internal inventory blocks
    not surfaced as cargo.
    """
    storage = []

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
                        name = ctx.resolve_name(ad.get("name", "Access"))
                        if "PLACEHOLDER" in name:
                            children = entry.get("children", [])
                            if children:
                                _walk(children)
                            continue
                        storage.append({
                            "Name": name,
                            "Mass": 0.0,
                            "Size": ad.get("size", 1),
                            "Grade": ad.get("grade", 1),
                            "Capacity": capacity,
                            "Uneditable": True,
                        })
            children = entry.get("children", [])
            if children:
                _walk(children)

    _walk(loadout_entries)
    return storage


def _add_impl_only_ports(tree, impl_ports, loadout_port_names):
    """Add ports from vehicle impl that aren't in the loadout (paints, etc.).

    Storage slots with no loadout entry are unequipped mount points rather
    than real cargo; reference omits them. Only Paints carry through.
    """
    for port in impl_ports:
        pname = port.get("name", "")
        if pname and pname not in loadout_port_names:
            item_type = port["types"][0] if port.get("types") else ""
            category = _classify_port(pname, item_type, port)
            if category == "Paints":
                hp = {"PortName": pname, "Uneditable": port.get("uneditable", False),
                      "MinSize": port.get("minSize", 0), "MaxSize": port.get("maxSize", 0),
                      "Types": port.get("types", [])}
                _place(tree, category, hp)
        # Recurse into sub-ports
        for sub in port.get("subPorts", []):
            sub_name = sub.get("name", "")
            if sub_name and sub_name not in loadout_port_names:
                item_type = sub["types"][0] if sub.get("types") else ""
                category = _classify_port(sub_name, item_type, sub)
                if category == "Paints":
                    hp = {"PortName": sub_name, "Uneditable": sub.get("uneditable", False),
                          "MinSize": sub.get("minSize", 0), "MaxSize": sub.get("maxSize", 0),
                          "Types": sub.get("types", [])}
                    _place(tree, category, hp)


def _index_ports(impl_ports, port_defs, order_index=None, _depth=0):
    """Build a flat lookup of port name -> port definition from vehicle impl ports.

    If `order_index` is provided, also records each port's discovery order so
    callers can sort loadout entries to match the impl XML's structural order
    (which is what the SPViewer reference uses).
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

        # Use port definition from vehicle impl for size/types if available
        if port_def:
            entry["MinSize"] = port_def.get("minSize", size)
            entry["MaxSize"] = port_def.get("maxSize", size)
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
        from .stditem import MANUFACTURER_CLASS, _COMPONENT_TYPES_CLASSED
        base_type = full_type.split(".")[0] if full_type else ""
        mfr_code = (mfr or {}).get("Code", "") if mfr else ""
        bl_class = ""
        if base_type in _COMPONENT_TYPES_CLASSED and mfr_code:
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
        bl = {
            "ClassName": entity_class,
            "Name": ctx.resolve_name(ad.get("name", "")),
            "Type": full_type,
            "Size": size,
            "Grade": ad.get("grade", 0),
        }
        if not _omit_baseloadout_class(full_type):
            bl["Class"] = bl_class
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
            entry["Types"] = [full_type.split(".UNDEFINED")[0] if full_type.endswith(".UNDEFINED") else full_type]

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
        if "gimbal" in entity_class.lower() or full_type == "Turret.GunTurret":
            entry["Gimballed"] = True
        elif full_type.startswith("Turret.") or full_type.startswith("TurretBase."):
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
        if not children and not is_sub_port and (
            full_type.startswith("Turret.") or full_type.startswith("TurretBase.")
        ):
            item_default = item_record.get("components", {}).get("defaultLoadout", [])
            if item_default:
                children = item_default

        # When the parent item is a turret, reference only emits weapon-like
        # sub-ports (the guns mounted inside). Ship loadouts often enumerate
        # cockpit displays, seat-access panels, a Room OC port, etc. — ref
        # filters those out. Scope the filter to turret parents so non-turret
        # items (e.g. CrewControlled salvage mounts that DO include Display
        # children in ref) keep their full sub-port list.
        is_turret_parent = (
            full_type.startswith("Turret.") or full_type.startswith("TurretBase.")
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
                # Turret filter: drop this child if none of its port types
                # match a weapon-sub prefix. Uses the port def's declared
                # types first; falls back to the installed item's type.
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
    Capacity comes from attachDef.volume (microSCU) / 1e6.
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
    physics = item_record.get("components", {}).get("physics", {})
    entry = {
        "Name": name,
        "Mass": float(physics.get("mass", 0) or 0),
        "Size": ad.get("size", 1),
        "Grade": ad.get("grade", 1),
    }
    if ad.get("volume"):
        entry["Capacity"] = round(ad["volume"] / 1000000.0, 2)
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


# Categories whose Hardpoints/ItemsQuantity count includes nested Ports
# (e.g. PilotWeapons Hardpoints = mount count + weapon-slot count).
# MissileRacks/BombRacks intentionally excluded — reference counts only
# the racks themselves, not the missile/bomb slots inside them.
_WEAPON_CATEGORIES_RECURSIVE_COUNT = {
    "PilotWeapons", "MannedTurrets", "RemoteTurrets", "PDCTurrets",
    "UtilityHardpoints", "UtilityTurrets",
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
                if key in _WEAPON_CATEGORIES_RECURSIVE_COUNT:
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
