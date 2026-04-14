"""Build vehicle equipment JSON."""

from .ship_equipment import build_ship_equipment


def build_vehicle_equipment(ctx):
    """Build vehicle equipment (same pool as ship equipment for now).

    The loadout system uses port tags and size constraints for compatibility.
    """
    # Vehicle equipment comes from the same item pool
    # Just re-run with same context — the output is identical
    # In the future we could filter by vehicle-specific tags
    return build_ship_equipment(ctx)
