# Heuristics audit — name/substring matches across the extractor

A survey of every place where the extractor matches by **name pattern**
(substring, prefix, suffix) instead of by an XML-authoritative identifier
(GUID, `attachDef.type`, `port_def.types`). Following the policy in
`feedback_identifier_hierarchy.md`, every entry here is technical debt
to retire when a GUID/type-based replacement is clear.

This is the master tracking list — review entries one at a time and fix
where a clean substitute exists.

## Status legend

- **A**: Item filtering (exclude debug/test/template items from output) — 10 entries
- **B**: Port-name routing in `_classify_port` — **was 81, now 35** after the 2026-05-02 refactor (see B-status below)
- **C**: Other className matching (special-case identification) — 29 entries
- **D**: Specific className suffix marker (variant detection) — 5 entries

## Updates after 2026-05-04 / 2026-05-05 work

- **Turret routing (G4)** — fully structural, see `turret_classification.md`.
  PW/RT/MT/Slaved classification has 0 mismatches against REF. The
  remaining className fallbacks (`_remote+_turret`, `_ai_turret`,
  decorative `camera_turret`/`bomb_turret`/`door_*`/`turret_cap`) are
  documented edge cases — kept because no clean structural distinction
  exists (G2 / C.1 entries below).
- **Storage** (`_compute_storage`, `_build_hardpoints`) — refactored to:
  - emit Mass from `physics.mass` instead of hardcoded `0.0`;
  - filter by positive type list `{SeatAccess, Cargo}` instead of negative
    `{CargoGrid, Container, Module}`;
  - suppress SeatAccess GenericExterior fallback by attachDef.name token
    (`@item_Name_SeatAccess_GenericExterior`) instead of resolved Name
    string ("Access" / "Personal Storage").
  Storage diffs **119 → 64**. Remaining diffs documented in
  `storage_diffs_audit.md` (capital-ship interior parsing, REF-suspect
  ItemsQuantity / Mass / Uneditable).
- **Line-number references below are stale** — the file structure shifted
  during the turret + storage work. Use the heuristic descriptions and
  search by code pattern instead. Scheduled for re-numbering once the
  next round of refactors lands.

## B refactor outcome (2026-05-02)

### Phase 1 — Dead-code removal
The entire 35-branch `types_are_meaningless` port-name fallback block
was **removed** as confirmed dead code. A 262-ship, 5313-entry audit
showed every port previously routed by name-fallback contributed zero
entries to the final output — they were filtered downstream as
Misc.UNDEFINED placeholders/covers. Aligned 16 ships' output more
closely with REF (zero regressions, several improvements).

### Phase 2 — Per-group structural replacement

**G1 (Weapon racks) — REPLACED structurally** ✓
Old: `"weapon_rack" in pn` + `item_cn.startswith("weapon_rack_")`.
New: check installed item's sub-ports for `WeaponPersonal` type
(excluding `.Gadget` subtype which is for fire-extinguisher cabinets).
1 ship better against REF (Pisces no longer falsely flagged extinguisher
cabinet as rack). Empty rack ports keep port-name fallback as last
resort (CIG provides no structural signal for unfilled rack mounts).

**G2 (Decorative item exclusion: door_/turret_cap/camera_turret/bomb_turret) — kept**
7 specific items, no clean structural distinction (typed Turret.GunTurret
or Misc.UNDEFINED with placeholder names; same as legitimate items).
Kept className matching as documented edge case.

**G3 (Misc.UNDEFINED placeholder + @LOC_PLACEHOLDER name) — kept**
Already mostly structural (`attachDef.type` + `attachDef.name`); only
port-name is heuristic, used as one of three discriminators.

**G4 (Remote turret detection) — deep analysis 2026-05-03**

Exhaustive structural-signal audit against all 358 turret ports +
50 RT entries / 193 PW entries / 48 MT entries in REF:

| Signal | Coverage | Failure mode |
|--------|----------|--------------|
| `type == TurretBase.MannedTurret` | 48/48 MT (100%) ✓ | Specific to manned only |
| `defaultWeaponGroup` on port | ~189/193 PW (95%) ✓ | Misses 13 RT entries with dwg=True (Ballista/Centurion/etc.) |
| `attachDef.name == "@item_Name_Turret_Remote"` | Tested, **rejected** | Hull_C nose turret has this name but REF=PilotWeapons |
| `port_def.controllableTags` presence | Useful but ambiguous | Manned turrets also have ControllerDef |
| `controllableTags` substring "remote" | 38/50 RT but 96 port-name disagreements | Many remote ports use seat tags (RearLeftBackSeat, gunnerSeat) instead of "remote" |
| `controllableTags` "copilot" substring | **Conflict** | `weaponCopilot` → REF.PilotWeapons; `coPilotSeat` → REF.RemoteTurrets |
| `className` contains `_remote+_turret` | ~80% of RT items | Misses AI_Turret variants |
| Combined: `_remote+_turret` OR `_ai_turret` className OR `remote_turret` portname | ~100% RT, 0 regressions | Current implementation |

**Conclusion**: no single XML field cleanly replaces the heuristic. The
structural signal "ControllerDef without defaultWeaponGroup, type≠MannedTurret"
gets 76% of RT cases right but conflicts on 24% (RT-with-dwg + PW-with-ctrl).
Item-className + port-name combined hits 100%. Kept current implementation;
it's already the smallest possible heuristic given REF's editorial choices.

**Counts:**
- _classify_port heuristics: 110 (original) → 62 (post fallback removal) → 65 (current; G4 added ai_turret variant)
- Net effect: same heuristic count post-G1-G4, but **dead code removed** and **more structural where possible**.

For each entry: file, line, current code, **why it exists**, and the
**proposed XML-driven replacement** (if any). Lines marked ✓ have been
audited and confirmed unfixable from XML (genuine name-only signal).

---

## Category A — Item filtering

These exclude items from output catalogues. The signals are debug/test/
template suffixes that don't have a single-type marker — they're
explicitly *non-gameplay* items that CIG ships in the data dump but
which never appear in the game.

### A.1 — fps_weapons.py

| Line | Code | Why | Proposed fix |
|------|------|-----|--------------|
| 29 | `if cn.startswith("carryable_") or cn.startswith("entityspawner_"):` | Both prefixes mark generic entity-spawner placeholders, not actual weapons | Could check `attachDef.type == "WeaponPersonal"` (presence) instead of excluding by name. Audit needed. |
| 33 | `if cn.endswith("_template") or cn.startswith("test_") or "_template_" in cn:` | Template/test items are non-shippable | No type signal — these literally exist in data but aren't real items. **Likely unfixable.** |
| 41 | `if cn.startswith("vlk_"):` | Vanduul faction prefix; faction-only items excluded | Could match by manufacturer GUID instead of `vlk_` prefix. Worth verifying. |
| 45 | `if "salvage_repair" in cn:` | Salvage-repair fps items not part of the standard catalogue | Audit if these have a distinct attachDef subtype. |
| 49 | `if any(p in cn for p in ["mine", "_ltp_", "_prx_", "lasertrip", "proximity"]):` | Trap/mine items excluded from FPS weapon catalogue | Likely have specific subtypes — audit. |

### A.2 — ship_equipment.py

| Line | Code | Why | Proposed fix |
|------|------|-----|--------------|
| 29 | `if cn.endswith("_template") or "_template_" in cn:` | Template items | Same as A.1 — likely unfixable |
| 33 | `if cn.startswith("test_") or "_test_" in cn or cn.startswith("master_"):` | Test/master items | Same |
| 37 | `if "lowpoly" in cn or "fakehologram" in cn or "_dummy" in cn:` | Visual placeholder items (LOD models, holograms, dummies) | Audit attachDef.type — many are likely Misc.UNDEFINED |
| 41 | `if "pudefenseturret" in cn:` | PU AI-controlled defense turrets | Should be `Turret.*` typed; check what makes them excluded specifically |
| 43 | `if "destructible_pu" in cn or "_ground_destructible" in cn:` | World-prop destructibles | Likely Misc/Door/etc — type-based skip should work |
| 47 | `if "_pu_ai_van" in cn:` | PU AI variant prefix | Could check tags/manufacturer |

---

## Category B — Port-name routing

`_classify_port` (ships.py:1499) decides which output slice (PilotWeapons,
PowerPlant, FuelTank, etc.) a loadout entry belongs to. Already uses
`port_def.types` as primary discriminator with name-based fallback for
ports without a single-type signal. The 81 entries here are the
documented fallback branches.

### B.1 — Confirmed-needed name fallbacks (port has no/ambiguous type signal)

These are documented in code comments as needed. ✓ marker means audited
and confirmed irreducible.

- **Weapon racks** (lines 1529-1535): `weapon_rack`/`weaponlocker`/`weapon_cabinet` port names; item className `weapon_rack_*`. Port type is `Door` (rack opens via door mechanism), so type alone can't classify. ✓
- **Mining/Salvage on UtilityTurret** (lines 1746, 1833-1835): `utilityturret + mining` / `toolarm + salvage|mining` — same type, different role. Port-name disambiguates Mining vs Salvage. ✓
- **Storage / personal_storage** (line 2016): port-name match for storage ports.
- **Modules** (line 2018): generic `Module` ports (Mustang Beta cover-back, etc.).

### B.2 — Fallback when impl-XML port-def is absent

The block at ships.py:1947-2018 is gated on:

```python
types_are_meaningless = not types or all(
    t in ("misc", "misc.misc", "usable", "useable") for t in types
)
if types_are_meaningless:
    # ~70 port-name substring branches
```

This fires when `port_def.types` is missing OR contains only generic
markers (`Misc`, `Usable`). It's **graceful degradation for ports the
vehicle-impl XML didn't fully define** — the loadout references a
hardpoint name that exists but lacks structural type info.

**Improvement opportunity**: when the port has no impl-XML types but
DOES have an installed item with a known `attachDef.type`, route by
that instead of port name. The `item_type` parameter is already passed
to `_classify_port` but currently unused in this fallback block.

Proposed: before the port-name branches, add an item-type-driven block:

```python
# Item-type fallback: when the port lacks impl-XML type info but the
# installed item has an attachDef.type, route by it.
TYPE_TO_SLICE = {
    "PowerPlant.Power": "PowerPlants",
    "QuantumDrive.UNDEFINED": "QuantumDrives",
    "QuantumFuelTank.UNDEFINED": "QuantumFuelTanks",
    "FuelTank.UNDEFINED": "HydrogenFuelTanks",
    "FuelIntake.Fuel": "FuelIntakes",
    "Shield.UNDEFINED": "Shields",
    "Cooler.UNDEFINED": "Coolers",
    "LifeSupportGenerator.UNDEFINED": "LifeSupport",
    "SelfDestruct.UNDEFINED": "SelfDestruct",
    "Radar.MidRangeRadar": "Radars",
    "Paints.UNDEFINED": "Paints",
    "Paints.Personal": "Paints",
    "CargoGrid.UNDEFINED": "CargoGrids",
    "WeaponDefensive.CountermeasureLauncher": "Countermeasures",
    "MissileLauncher.MissileRack": "MissileRacks",
    "BombLauncher.BombRack": "BombRacks",
    # Armor.{Light,Medium,Heavy} → "Armor"
    "Armor.Light": "Armor", "Armor.Medium": "Armor", "Armor.Heavy": "Armor",
    "Flair_Cockpit.Flair_Static": "Flairs",
    "Flair_Cockpit.Flair_Hanging": "Flairs",
    # … etc
}
if item_type:
    full_type = item_type if "." in item_type else f"{item_type}.UNDEFINED"
    if full_type in TYPE_TO_SLICE:
        return TYPE_TO_SLICE[full_type]
```

Risk: needs careful regression-test against existing matches.
Sub-classification (Retro/VTOL/Manneuver thrusters) still needs name
fallback because all live under one parent type — see B.3.

### B.2-extra — Genuinely irreducible in fallback

| Line | Code | Why irreducible |
|------|------|-----------------|
| 1963 | `if "retro" in pn:` | Retro is sub-class of MainThruster — same type as main |
| 1965-1968 | thruster vtol/maneuver | Sub-class of ManneuverThruster — same type as main |
| 1971 | `flight_blade` in pn | FlightController item but display field is "FlightBlade" only when port name signals blade vs. controller |
| 1987 | `flair` in pn | Cosmetic/Static distinction not always in subtype |
| 2016 | `storage` in pn | Storage port pulls from Container.Cargo items, but only when port-name signals storage (otherwise routes to CargoContainers) |
| 2018 | `module` in pn | Generic Modules slot |

### B.3 — Sub-classification (likely irreducible)

| Line | Code | Reason |
|------|------|--------|
| 1037-1041 | thruster type via `vtol`/`retro` in pn | All three sub-types share `MainThruster` / `ManneuverThruster` parent type — sub-classification needs port-name disambiguation |
| 1769-1778 | thruster_pipes filter | Same root cause |
| 1349-1353 | turret seat / engineering disambiguation | Both are `Seat.UNDEFINED` — port name is the distinguisher |

### B.4 — All other Category-B entries

See `temp/heuristics_audit.json` for full list. 71 more port-name
substring branches in ships.py — most are documented in code comments
as needed for specific edge cases (modular ships, variant ports).

---

## Category C — Other className matching

29 entries. Mixed bag of identification heuristics.

### C.1 — Confirmed needed (no type signal)

| Line | Code | Reason |
|------|------|--------|
| 390 | `entity_class.startswith("ARMR_")` | Armor manufacturer-prefix fallback when item type isn't loaded yet ✓ |
| 1534 | `item_cn.startswith("weapon_rack_")` | Weapon rack Door items — same Door type as exterior doors ✓ |
| 1539-1542 | `item_cn.startswith("door_")` etc — turret cap items | Decorative door covers; same type as gameplay doors ✓ |
| 1595-1596 | `_remote + _turret` in className | Remote-turret items live under the same `Turret.*` types as manned turrets — only naming distinguishes ✓ |
| 3803 | `"noise" in entity_class.lower()` (countermeasure type) | Chaff/Flare/Decoy distinction not exposed in attachDef ✓ |
| 3805 | `"flare" in entity_class.lower()` | Same |

### C.2 — Possibly substitutable

| Line | Code | Proposed |
|------|------|----------|
| 53 (fps_attachments.py) | `"weapon_underbarrel_light" in cn_lower` | Probably has a subtype — audit |
| 1045, 1227 | `_main + thruster` in cn | Used for main-thruster sub-classification — same as B.3 |

---

## Category D — Specific className suffix markers

5 entries. Variant identifiers via suffix.

| Line | Code | Reason |
|------|------|--------|
| ships.py:164 | `if "_Tier_" in cn:` | Tier-N AI vehicle variant exclusion. Has no type signal — manufacturer ships test variants under same items. Likely irreducible ✓ |
| ships.py:173 | `if cn.endswith("_Unmanned"):` | Unmanned AI variant exclusion — same as above ✓ |
| stditem.py:2263, 2265 | `_Flight_Blade_HND/SPD` | Two variants of FlightController: HND (handling-tuned) vs SPD (speed-tuned). Both are `FlightController.UNDEFINED` — only name distinguishes. Probably irreducible. |
| stditem.py:2857 | `_CargoGrid_Main` | Used for one specific override — likely retirable if we trust attachDef.type=CargoGrid alone |

---

## Recommended next steps

1. **Verify B.2 dead branches** — write an audit that reaches each line in `_classify_port`'s fallback block (1933-2018) on real data. Lines never reached = removable.
2. **Verify A.1/A.2 type-coverage** — for each filter pattern, check if `attachDef.type` already covers it (e.g. all `_dummy` items are `Misc.UNDEFINED`).
3. **stditem.py:2857** — single line, easy to retire if test passes.
4. Leave B.1, B.3, C.1 alone — confirmed needed.

## Tracking

Full machine-readable list at `temp/heuristics_audit.json` — re-run
the audit script in `temp/` to refresh.
