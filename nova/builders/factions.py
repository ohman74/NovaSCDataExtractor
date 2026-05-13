"""factions.json — FactionReputation catalog.

One entry per FactionReputation record. Carries the localized name plus
the propertiesBB metadata (Headquarters / Leadership / Area / Focus / …)
exposed as flat top-level fields. ClassName is the stable joinkey from
missions.json (FactionClassName).
"""


def _loc(ctx, raw):
    """Resolve @LOC keys, return empty string for unresolved/missing."""
    if not raw:
        return ""
    if not raw.startswith("@"):
        return raw
    val = ctx.resolve_name(raw)
    if val and not val.startswith("@"):
        return val
    return ""


def build_factions(ctx) -> list[dict]:
    out = []
    for guid, rec in ctx.faction_reputation.items():
        entry = {
            "ClassName": rec.get("className", ""),
            "GUID": guid,
            "DisplayName": _loc(ctx, rec.get("displayName", "")),
            "IsNPC": bool(rec.get("isNPC", False)),
            "Lawful": bool(rec.get("lawful", False)),
        }
        logo = rec.get("logo", "")
        if logo:
            entry["Logo"] = logo
        # Optional loc fields — emit only when resolved to a non-empty string.
        for raw_key, out_key in (
            ("description",  "Description"),
            ("headquarters", "Headquarters"),
            ("founded",      "Founded"),
            ("leadership",   "Leadership"),
            ("area",         "Area"),
            ("focus",        "Focus"),
        ):
            val = _loc(ctx, rec.get(raw_key, ""))
            if val:
                entry[out_key] = val
        out.append(entry)

    out.sort(key=lambda x: x["ClassName"])
    return out
