"""Build ground vehicle data JSON."""

from .ships import (
    _build_ship,
    _is_ai_or_excluded_variant,
    _is_cosmetic_variant,
    _is_ground_vehicle,
    _is_not_included,
    _is_placeholder_record,
    _is_salvageable_debris,
)


def build_vehicles(ctx):
    """Build the vehicles output dataset (ground vehicles only)."""
    vehicles = []

    for class_name, record in ctx.vehicles.items():
        vehicle = record.get("vehicle", {})
        if not vehicle:
            continue
        if not _is_ground_vehicle(vehicle):
            continue
        if _is_salvageable_debris(record):
            continue
        if _is_placeholder_record(record):
            continue
        if _is_not_included(class_name, ctx):
            continue
        if _is_ai_or_excluded_variant(class_name):
            continue
        if _is_cosmetic_variant(class_name, ctx):
            continue

        veh = _build_ship(class_name, record, ctx)
        if veh:
            veh["IsSpaceship"] = False
            veh["IsGravlev"] = vehicle.get("isGravlevVehicle", False)
            veh["MovementClass"] = vehicle.get("movementClass", "")
            vehicles.append(veh)

    vehicles.sort(key=lambda v: v.get("Name", ""))
    print(f"  Built {len(vehicles)} ground vehicles")
    return vehicles
