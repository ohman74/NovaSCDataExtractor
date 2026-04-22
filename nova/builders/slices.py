"""Project full vehicle records into the reference's three slice shapes.

The reference data (SPViewer/NovaTools) splits vehicles across three files:
- entry_0: catalog metadata (scalar Cargo, Type, external-web placeholders)
- entry_1: detailed stats (object Cargo, full spec)
- entry_2: hardpoints/structural (PortTags, Hull, Hardpoints)

We build one rich record per vehicle then project it into each slice so the
output files line up with the reference's structure.
"""

from .fps_attachments import build_fps_attachments
from .fps_weapons import build_fps_weapons
from .ship_equipment import build_ship_equipment
from .ships import build_ships
from .vehicles import build_vehicles


# Fields that belong in each slice, in the order reference emits them.
_METADATA_FIELDS = ["ClassName", "Name", "Manufacturer", "Career", "Role", "Size", "Cargo", "Type"]
_STATS_FIELDS = [
    "ClassName", "Name", "Description", "Career", "Role", "Size", "Cargo",
    "Crew", "WeaponCrew", "OperationsCrew",
    "Mass", "ComponentsMass", "Dimensions",
    "IsSpaceship", "IsVehicle", "IsGravlev",
    "Armor", "Hull", "Emissions", "ResourceNetwork", "BaseLoadout",
    "Insurance", "FlightCharacteristics", "FuelManagement",
]
_HARDPOINTS_FIELDS = ["ClassName", "Name", "IsSpaceship", "IsVehicle", "IsGravlev", "PortTags", "Hull", "Hardpoints"]


def _empty_commlink():
    return {"HasCommLink": False, "Date": None, "Url": None}


def _empty_progress_tracker():
    return {"Status": None, "IsOnPT": False, "ID": None}


def _empty_store():
    return {"Url": None, "IsPromotionOnly": False, "IsLimitedSale": False, "Buy": None}


def _empty_pu():
    return {"Patch": None, "HasPerf": False, "IsPTUOnly": False, "Buy": None}


def _derive_is_vehicle(record):
    """Ground non-gravlev vehicle → IsVehicle=True. Ships and gravlevs → absent."""
    if record.get("IsSpaceship"):
        return None
    if record.get("IsGravlev"):
        return None
    if record.get("MovementClass", "").lower() in {"arcadewheeled", "wheeled", "tracked"}:
        return True
    return None


def _project(record, fields):
    out = {}
    for f in fields:
        if f not in record:
            continue
        v = record[f]
        # Reference emits IsGravlev only when true (absent otherwise).
        if f == "IsGravlev" and not v:
            continue
        out[f] = v
    return out


def to_metadata(record):
    """Entry_0 shape: catalog metadata with scalar Cargo and external-web placeholders."""
    out = _project(record, _METADATA_FIELDS)
    cargo = record.get("Cargo")
    if isinstance(cargo, dict):
        out["Cargo"] = int(round(cargo.get("CargoGrid", 0)))
    elif isinstance(cargo, (int, float)):
        out["Cargo"] = int(round(cargo))
    else:
        out["Cargo"] = 0
    out["CommLink"] = _empty_commlink()
    out["ProgressTracker"] = _empty_progress_tracker()
    out["Store"] = _empty_store()
    out["PU"] = _empty_pu()
    out["New Ship"] = None
    out["New Vehicle"] = None
    return out


def to_stats(record):
    """Entry_1 shape: full spec with object Cargo and per-store Buy placeholder."""
    out = _project(record, _STATS_FIELDS)
    iv = _derive_is_vehicle(record)
    if iv:
        out["IsVehicle"] = True
    out["Buy"] = {}
    out["New Ship"] = None
    out["New Vehicle"] = None
    return out


def to_hardpoints(record):
    """Entry_2 shape: ports, hull structure, and hardpoints."""
    out = _project(record, _HARDPOINTS_FIELDS)
    iv = _derive_is_vehicle(record)
    if iv:
        out["IsVehicle"] = True
    return out


def _merge_ships_and_vehicles(ctx):
    """Build ships + vehicles separately then merge. Cached per-ctx: the three
    slice builders (metadata/stats/hardpoints) all need the same merged list.

    Overlaps: ship fields win; vehicle-only fields (IsGravlev, MovementClass)
    fill missing slots. Matches the merge logic in compare_vehicles.py.
    """
    cached = getattr(ctx, "_merged_vehicles", None)
    if cached is not None:
        return cached

    ships = build_ships(ctx)
    vehicles = build_vehicles(ctx)

    merged = {r["ClassName"]: dict(r) for r in vehicles}
    for r in ships:
        cn = r["ClassName"]
        if cn in merged:
            combined = dict(merged[cn])
            combined.update(r)
            merged[cn] = combined
        else:
            merged[cn] = dict(r)

    result = sorted(merged.values(), key=lambda r: r.get("Name", "") or r.get("ClassName", ""))
    ctx._merged_vehicles = result
    return result


def build_vehicle_metadata(ctx):
    records = _merge_ships_and_vehicles(ctx)
    return [to_metadata(r) for r in records]


def build_vehicle_stats(ctx):
    records = _merge_ships_and_vehicles(ctx)
    return [to_stats(r) for r in records]


def build_vehicle_hardpoints(ctx):
    records = _merge_ships_and_vehicles(ctx)
    return [to_hardpoints(r) for r in records]


def build_vehicle_equipment(ctx):
    """Entry_3 equivalent: ship/vehicle equipment stdItem records."""
    return build_ship_equipment(ctx)


def build_fps_equipment(ctx):
    """Entry_4 equivalent: FPS weapons + attachments merged."""
    return build_fps_weapons(ctx) + build_fps_attachments(ctx)
