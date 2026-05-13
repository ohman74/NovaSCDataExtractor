"""localities.json — MissionLocality catalog (Nyx, Pyro, Pyro_RegionA, …).

The locality ClassName IS the region name; CIG does not @LOC it. Each
record exposes its availableLocations GUID list for later resolution
against a (potentially separate) place-name dataset.
"""


def build_localities(ctx) -> list[dict]:
    out = []
    for guid, rec in ctx.localities.items():
        out.append({
            "ClassName": rec.get("className", ""),
            "GUID": guid,
            "AvailableLocations": list(rec.get("availableLocations", [])),
        })
    out.sort(key=lambda x: x["ClassName"])
    return out
