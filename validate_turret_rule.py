"""Validate the structural turret-classification rule against REF (entry_2.json).

Rule under test:
  REF=PW iff non-pilot WC has default="no_control" AND pilot WC has a tag claim
           (specialist takeover pattern)
  REF=RT iff pilot has no claim, OR non-pilot WC has numeric default (broad gunner),
           OR a seat directly owns the port via UserDef.
"""
import xml.etree.ElementTree as ET
import os
import glob
import json

XML_DIR = "cache/Data/Scripts/Entities/Vehicles/Implementations/Xml"
PILOT_CTRL_TAGS = {
    "pilotseat", "pilot_seat", "weaponpilot", "pilotseat_weapons",
    "weapon_controller_pilot", "gunnose",
}
# User-flagged ground vehicles to skip
GROUND_SKIP = {"ANVL_Ballista", "ANVL_Centurion", "ANVL_Spartan", "TMBL_Nova"}


def parse_impl(path):
    tree = ET.parse(path)
    root = tree.getroot()
    turret_ports = []
    weapon_controllers = []
    seats = []
    for part in root.iter("Part"):
        pname = part.get("name", "")
        for itemport in part.iter("ItemPort"):
            for ctrldef in itemport.iter("ControllerDef"):
                ctrl = ctrldef.get("controllableTags", "") or ""
                types = []
                for t in itemport.iter("Type"):
                    base = t.get("type", "")
                    subs = t.get("subtypes", "")
                    if subs:
                        for s in subs.split(","):
                            types.append(f"{base}.{s.strip()}")
                    elif base:
                        types.append(base)
                dwg = itemport.get("defaultWeaponGroup")
                u_pgs = []
                ud = ctrldef.find("UsableDef")
                if ud is not None:
                    for pg in ud.iter("PriorityGroup"):
                        it = pg.get("itemType", "")
                        dp = pg.get("defaultPriority", "")
                        tag_overrides = {}
                        for tag_el in pg.iter("tags"):
                            tag_v = tag_el.get("tag", "")
                            for prio in tag_el.iter("Priority"):
                                tag_overrides[tag_v] = prio.get("value", "")
                        u_pgs.append({"itemType": it, "default": dp, "tags": tag_overrides})
                user_pgs = []
                userdef = ctrldef.find("UserDef")
                if userdef is not None:
                    for pg in userdef.iter("PriorityGroup"):
                        it = pg.get("itemType", "")
                        dp = pg.get("defaultPriority", "")
                        tag_overrides = {}
                        for tag_el in pg.iter("tags"):
                            tag_v = tag_el.get("tag", "")
                            for prio in tag_el.iter("Priority"):
                                tag_overrides[tag_v] = prio.get("value", "")
                        user_pgs.append({"itemType": it, "default": dp, "tags": tag_overrides})
                is_turret = (
                    any("Turret" in t or "WeaponGun" in t or "MissileLauncher" in t for t in types)
                    and not any("Controller" in t for t in types)
                )
                if is_turret:
                    turret_ports.append({"name": pname, "ctrl": ctrl, "types": types, "dwg": dwg})
                if any("WeaponController" in t for t in types):
                    weapon_controllers.append({"name": pname, "ctrl": ctrl, "pgs": u_pgs})
                if "Seat" in types:
                    seats.append({"name": pname, "ctrl": ctrl, "user_pgs": user_pgs})
    return turret_ports, weapon_controllers, seats


def classify(port, wcs, seats):
    ctrl = (port.get("ctrl") or "").strip()
    types = port.get("types", [])
    if "TurretBase.MannedTurret" in types:
        return "MT", "TurretBase.MannedTurret type"
    if not ctrl:
        return ("PW", "no ctrl, dwg") if port.get("dwg") else ("PW?", "no ctrl, no dwg")
    if ctrl.lower() in PILOT_CTRL_TAGS:
        return "PW", "pilot ctrl_tag"

    # Pilot WC heuristic: ctrl in pilot tags
    pilot_wc = None
    nonpilot_wcs = []
    for wc in wcs:
        wc_ctrl = (wc.get("ctrl") or "").lower()
        if wc_ctrl in {"weapon_controller_pilot", "pilotseat", "pilot_seat", "pilotseat_weapons", "weaponpilot"}:
            pilot_wc = wc
        else:
            nonpilot_wcs.append(wc)

    pilot_claims = False
    if pilot_wc:
        for pg in pilot_wc["pgs"]:
            if pg["itemType"] not in ("Turret", "WeaponGun"):
                continue
            # Only a TAG-SPECIFIC override on the port's ctrl_tag counts as a
            # claim. An empty default ("" with no tags) does NOT grant claim
            # to all ports — verified against Cutlass_Red/Redeemer/Valkyrie
            # /Scorpius which all have empty pilot default but REF=RT.
            if ctrl in pg["tags"] and pg["tags"][ctrl] != "no_control":
                pilot_claims = True
                break
            # A numeric default ALSO counts as a broad pilot claim
            # (Prowler pilot default=100 covers ports without tag override).
            if pg["default"] not in ("no_control", "", None):
                pilot_claims = True
                break

    nonpilot_specialist = False
    nonpilot_broad = False
    for wc in nonpilot_wcs:
        for pg in wc["pgs"]:
            if pg["itemType"] not in ("Turret", "WeaponGun"):
                continue
            tag_claim = ctrl in pg["tags"] and pg["tags"][ctrl] != "no_control"
            if pg["default"] == "no_control" and tag_claim:
                nonpilot_specialist = True
            elif pg["default"] not in ("no_control", "", None):
                nonpilot_broad = True

    seat_owns = False
    for seat in seats:
        sctrl = (seat.get("ctrl") or "").lower()
        if sctrl in PILOT_CTRL_TAGS:
            continue
        for pg in seat["user_pgs"]:
            if pg["itemType"] in ("Turret", "WeaponGun") and ctrl in pg["tags"]:
                if pg["tags"][ctrl] != "no_control":
                    seat_owns = True

    if not pilot_claims and (nonpilot_specialist or nonpilot_broad or seat_owns):
        return "RT", "pilot has no claim"
    if nonpilot_broad:
        return "RT", "non-pilot WC has numeric default (broad gunner)"
    if seat_owns and not pilot_claims:
        return "RT", "seat directly owns port"
    if pilot_claims and nonpilot_specialist:
        return "PW", "pilot slaved fallback + specialist takeover"
    if pilot_claims and not nonpilot_specialist and not nonpilot_broad and not seat_owns:
        return "PW", "pilot has claim, no non-pilot competitor"
    return "?", f"pc={pilot_claims} sp={nonpilot_specialist} br={nonpilot_broad} so={seat_owns}"


def ref_cat(cn, port, ref_by):
    r = ref_by.get(cn)
    if not r:
        return None
    hp = r.get("Hardpoints", {}).get("Weapons", {})
    for cat in ("PilotWeapons", "RemoteTurrets", "MannedTurrets", "PDCTurrets"):
        items = hp.get(cat, {}).get("InstalledItems", []) or []
        if any(isinstance(x, dict) and x.get("PortName") == port for x in items):
            return {"PilotWeapons": "PW", "RemoteTurrets": "RT", "MannedTurrets": "MT", "PDCTurrets": "PDC"}[cat]
    return None


def main():
    with open("temp/reference/entry_2.json", encoding="utf-8-sig") as f:
        ref_list = json.load(f)
    ref_by = {r["ClassName"]: r for r in ref_list}

    matches = 0
    mismatches = []
    for path in glob.glob(os.path.join(XML_DIR, "*.xml")):
        cn = os.path.splitext(os.path.basename(path))[0]
        if cn in GROUND_SKIP:
            continue
        try:
            tps, wcs, seats = parse_impl(path)
        except Exception:
            continue
        for p in tps:
            if not p.get("ctrl"):
                continue
            ref = ref_cat(cn, p["name"], ref_by)
            if ref is None:
                continue
            pred, reason = classify(p, wcs, seats)
            if pred == ref:
                matches += 1
            else:
                mismatches.append((cn, p["name"], p.get("ctrl"), p.get("dwg"), pred, ref, reason, p.get("types")))

    print(f"Matches: {matches}")
    print(f"Mismatches: {len(mismatches)}")
    print()
    for r in mismatches[:60]:
        cn, pn, ctrl, dwg, pred, ref, reason, types = r
        print(f"  {cn:28s} {pn:42s} ctrl={ctrl!r:28s} dwg={dwg!s:5s} pred={pred:3s} REF={ref:3s}  ({reason})")


if __name__ == "__main__":
    main()
