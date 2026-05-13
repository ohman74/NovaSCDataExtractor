"""standings.json — SReputationStandingParams catalog.

One entry per rank step (Neutral, Friendly, Elite Contractor, …). The
contract entries in missions.json reference these by ClassName via
StandingMinClassName / StandingMaxClassName.

We attach the parent scope's ClassName (FactionReputationScope, etc.)
when we can find the rank in a scope's standingGuids list — useful for
grouping ranks by ladder in the UI.
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


def _scope_index(ctx):
    """guid → scope_className for every standing referenced by any scope."""
    idx = {}
    for scope in ctx.reputation_scopes.values():
        scope_cn = scope.get("className", "")
        for std_guid in scope.get("standingGuids", []):
            idx[std_guid] = scope_cn
    return idx


def build_standings(ctx) -> list[dict]:
    scope_idx = _scope_index(ctx)
    out = []
    for guid, rec in ctx.standings.items():
        entry = {
            "ClassName": rec.get("className", ""),
            "GUID": guid,
            "Name": rec.get("name", ""),
            "DisplayName": _loc(ctx, rec.get("displayName", "")),
            "MinReputation": rec.get("minReputation", 0),
            "Gated": bool(rec.get("gated", False)),
        }
        scope = scope_idx.get(guid)
        if scope:
            entry["ScopeClassName"] = scope
        out.append(entry)

    out.sort(key=lambda x: (x.get("ScopeClassName", ""), x["MinReputation"], x["ClassName"]))
    return out
