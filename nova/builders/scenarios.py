"""scenarios.json — MissionScenario records (content blockers + dynamic events).

ContractGeneratorHandler_* references these by GUID in
`<required_active_scenarios>`. The handler only spawns its contracts when
every referenced scenario is active; `ContentBlocker_Scenario` in
particular ships with `ScheduleEnabled=false` to keep unreleased contract
families gated until CIG flips the switch.

Surfacing this as its own output lets missions.json reference scenarios
by ClassName (the canonical join key used throughout the catalog) and
lets consumers tell "blocked in build" from "blocked by player progress"
without re-reading the source XML.
"""


def build_scenarios(ctx) -> list[dict]:
    out = []
    for rec in ctx.mission_scenarios.values():
        out.append({
            "ClassName": rec.get("className", ""),
            "Name": rec.get("name", ""),
            "Description": rec.get("description", ""),
            "AutoCreate": bool(rec.get("autoCreate", False)),
            "TrackProgress": bool(rec.get("trackProgress", False)),
            "ScheduleEnabled": bool(rec.get("scheduleEnabled", True)),
        })
    out.sort(key=lambda e: e["ClassName"])
    return out
