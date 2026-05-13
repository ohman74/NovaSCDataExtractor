"""mission_types.json — MissionType catalog (BountyHunter, Collection, …).

Mission categorization carrier. Contract entries in missions.json link
to this catalog via MissionTypeClassName. ScenarioTier entries have no
MissionType (dynamic events use a separate progression model).

Source: Records/missiontype/**/*.xml — each file is a self-closing
MissionType record. Class-name suffix is the canonical type ID;
LocalisedTypeName is the @LOC display key.
"""


def _loc(ctx, raw):
    if not raw:
        return ""
    if not raw.startswith("@"):
        return raw
    val = ctx.resolve_name(raw)
    if val and not val.startswith("@"):
        return val
    return ""


def build_mission_types(ctx) -> list[dict]:
    out = []
    for guid, rec in ctx.mission_types.items():
        entry = {
            "ClassName": rec.get("className", ""),
            "GUID": guid,
            "DisplayName": _loc(ctx, rec.get("localisedTypeName", "")),
        }
        icon = rec.get("svgIconPath", "")
        if icon:
            entry["IconPath"] = icon
        icon_name = rec.get("iconName", "")
        if icon_name:
            entry["IconName"] = icon_name
        out.append(entry)

    out.sort(key=lambda x: x["ClassName"])
    return out
