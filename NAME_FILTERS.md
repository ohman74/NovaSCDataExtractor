# Name-based filter backlog

Audit of every place the code classifies or excludes an entity by matching on
`ClassName`, `Name`, `DisplayName`, or file path rather than on structural
fields (`Type`, `SubType`, `Tags`, `Components[*]`, `itemPortTags`,
`vehicleDefinition`, etc.).

## Current state (session pause)

HIGH #15 (`_classify_port` in ships.py) — **resolved 2026-04-21**. Hardpoint
category is now derived from the port's `types` (vehicle-impl XML), with
the installed item's `attachDef.type` as a secondary allow-list and name-
based patterns only as last-resort when the impl XML carries no useful
type (`Misc`, `Usable`, `Useable`, or no port_def at all). Structural type
allow-list covers 22 categories directly; only WeaponsRacks / Mining /
Salvage keep a name-based check (documented in-line — the structural
corpus has no single type that discriminates them). `_SKIP_PORT_TYPES`
lists 30+ non-gameplay types (SeatAccess, Door, *Controller, Ping,
Scanner, Display, Room, AIModule, WeaponRegenPool, LandingSystem, etc.).
Net output effect: 776 port-level reclassifications across 7 ships, all
structural improvements — e.g. gimballed guns now correctly land in
PilotWeapons (shifting DPS in `vehicle_stats.json` for 56 ships);
hovercraft gravlev fans are picked up as thrusters; SeatAccess ports
named `hardpoint_turret_*` no longer show up as turrets. Matrix baseline
unchanged (262 ships, 209 matched, 0 gaps). Also closes entry #22
(`classify_port` in entity_parser.py) if that helper is retired.

CRITICAL #1 (vehicle filter stack) — **resolved**. The extractor now runs
five sequential filters on every vehicle record:

1. `_is_salvageable_debris` — path/className fallback (entry #6 below, still
   name-based; lowest priority to refactor since the records are obviously
   not vehicles).
2. `_is_placeholder_record` — **structural**. Catches records with
   `vehicleName == "@LOC_UNINITIALIZED"` or empty `vehicleDefinition`.
3. `_is_not_included` — **structural**. Catches records where CIG's own
   `StaticEntityClassData/EAEntityDataParams.inclusionMode == "DoNotInclude"`.
   Replaced the hardcoded `AEGS_Javelin` exclusion and three CRUS_Starlifter_A2
   entries. Also caught the 4 ground-vehicle DoNotInclude records previously
   missed because `get_entity_files` looked in `ground/` but the folder is
   `groundvehicles/` — fix shipped.
4. `_is_ai_or_excluded_variant` — name-based `_AI_MISSION_PATTERNS` list.
   Necessary fallback per the 2026-04-20 investigation (AI variants are
   structurally identical to player ships in Game2.xml). Documented in
   entry #1 below.
5. `_is_cosmetic_variant` — **algorithmic**. Uses `nova/cosmetic_classifier.py`
   to compare each ship against siblings sharing the same
   `vehicleDefinition`. Pairs that differ only in palette / material /
   localization / interior art / paint ports / rename-only modification
   blocks / item-level cosmetic twins get filtered. Currently catches 34
   variants per build.

Remaining manual entries in `_NOT_PLAYER_OWNABLE`: 2 only
(`ANVL_Lightning_F8` — F8A military spec with no cosmetic sibling on the
same impl; `ORIG_600i_Executive_Edition` — classifier flags as FUNCTIONAL
because of real landingSystem / inventoryContainer / Exec turret
differences, retained per product decision).

Audit harnesses in place:
- `py compare_matrix.py` — diffs `output/vehicle_metadata.json` against
  RSI ship-matrix flight-ready set. 0 gaps / 0 anomalies at time of save.
- `py find_cosmetic_dupes.py` — CLI over `nova/cosmetic_classifier.py`.
  Thin wrapper around the build-integrated logic.
- Algorithmic cosmetic-variant exchange: extractor writes
  `cache/cosmetic_variants.json`; `compare_matrix.py` reads it and
  auto-excludes matrix SKUs covered by filtered cosmetic variants (so no
  hardcoded cosmetic-SKU ignore list needed).

Stditem backlog #25–#33 — **mostly resolved 2026-04-21**:
- #25 Container.Cargo mass skip: structural (ResourceContainer / tags /
  name+inventory+volume).
- #26 Storm missile rack: structural (`SCItemPurchasableParams.displayName`
  placeholder check).
- #27 Remote turret mass: `attachDef.name` localization-key check.
- #28 Salvage head mass: `SDistortionParams` component absence.
- #29 LifeSupport class: `attachDef.size == 4` (also updated in
  `ships.py:1486` BaseLoadout duplicate).
- #30 Blade HND/SPD: DEFERRED — requires SIFCSModifiersLegacy record
  parsing (multi-file). Commented in-line.
- #31 Cargo-pod ship/ground split: component-set check.
- #32 Cyclone CargoGrid: kept as single-className exception (no generic
  structural rule separates it from sibling 1x1x1 placeholders); in-line
  comment documents the trade-off.
- #33 FPS class: melee → `WeaponPersonal.Knife` structural; energy vs
  ballistic retained as ClassName-suffix check because the data lacks a
  structural damage-class signal for personal weapons. In-line comment.

All resolved changes: zero output diff vs pre-refactor baseline.

**CRITICAL-tier entries resolved 2026-04-21:**
- #2 orbital/probe/securitynetwork → `_is_non_pilotable` (no seat port
  anywhere in the defaultLoadout tree).
- #6 `_is_salvageable_debris` → `vehicle.movementClass == "Dummy"` (7/7
  exact match).
- #4 `AEGS_Javelin` was already removed earlier (handled by
  inclusionMode).

**CRITICAL-tier entries investigated and kept as last-resort:**
- #3 `_Tier_` (Apollo module-config variants) — structural dedup by
  vehicleName would also drop Exec/Collector siblings. Kept as
  documented CIG convention tag.
- #5 `_Unmanned` suffix — variants are byte-for-byte copies of the base
  record. No structural discriminator exists.
- #7 `_is_non_equippable` in ship_equipment.py — 6 sub-categories
  investigated individually. LowPoly duplicates are byte-identical;
  templates/tests share signals with 60+ legitimate reference items;
  PUDefense/Destructible/AI-Van have overlapping manufacturer/tag
  profiles with real equipment. Kept with detailed in-line per-category
  docs.
- #8 `_is_non_player_fps` — "no manufacturer" would over-filter
  `none_melee_01` + `kegr_fire_extinguisher_01`; mines have real
  manufacturers. Kept with in-line docs.

**CRITICAL-tier FPS entries resolved 2026-04-21:**
- #11 `_is_fps_attachment` uppercase-first-letter check → `FPS_Barrel`
  tag discrimination + placeholder-name+no-mfr template skip (scoped
  to WeaponAttachment).
- #13 FPS path detection → `_is_fps_item()` structural helper (base
  type + full type + Barrel tag).
- #14 FPS classification fallback → folded into #13's helper.

**CRITICAL-tier FPS entries investigated and kept as last-resort:**
- #9 `_01_<suffix>` orphan drop — signature dedup alone leaks 3 items
  through. Editorial CIG convention, retained.
- #10 `_find_base_weapon`, #12 `_find_base_attachment` — segment-
  stripping for base lookup (not a filter). No structural parent-ref
  signal in parsed records.

Remaining open items:
- #16–#24 HIGH port-classification details (armor, cargo/storage,
  thruster sub-classification, pool-size lookups, impl-XML segment-
  stripping).
- #30 blade modifier record parsing.
- #33 energy/ballistic FPS split (pending ammo parse).
- LOW-tier allowlists (stditem.py:38 et al — accepted as last-resort
  exceptions).

## Audit harness — latest baseline

Run `py compare_matrix.py` to diff `output/vehicle_metadata.json` against the
RSI pledge-store's flight-ready set (cached in `cache/rsi_flight_ready.json`).
At session pause:

- 262 vehicles in our output (was 312 at session start)
- 209 matrix-matched (196 exact + 13 mapped), 0 matrix-only, 0 ours-only
- 2 dupe groups (Polaris + Zeus Mk II CL with Wikelo Collector variants, both
  genuine functional differences — not cosmetic)

Subcommands: `--matched`, `--ours-only`, `--matrix-only`, `--dupes`.

Per `.claude/CLAUDE.md`, name-based matching is only acceptable as a last
resort, in a clearly-commented block, after verifying no structural field
distinguishes the cases. It is **never acceptable** for
availability/flight-readiness. Several entries below violate that rule.

Risk tiers:

- **CRITICAL** — violates the "never acceptable" rule (availability /
  flight-readiness / is-this-a-player-entity) or silently drops records.
- **HIGH** — routine classification where structural fields almost certainly
  exist but haven't been investigated.
- **MEDIUM** — contextual overrides where a structural signal may exist but
  the data must be checked before refactoring.
- **LOW** — curated per-item allowlists keyed by `ClassName`. Acceptable as
  last-resort exceptions but should shrink as upstream rules are discovered.

---

## CRITICAL — availability / exclusion filters

These decide whether an entity appears in output at all. CLAUDE.md forbids
name-based logic here.

### 1. `nova/builders/ships.py:10` — `_AI_MISSION_PATTERNS` *(investigated 2026-04-20)*
```python
_AI_MISSION_PATTERNS = [
    "_PU_AI_", "_EA_AI_", "_Unmanned_", "_Template",
    "_S42_", "_AI_", "_NPC_", "_Dummy",
    "_Derelict_", "_Wreck", "_NoDebris",
    "_Hijacked", "_Boarded", "_Crewless",
    "_NoInterior", "_Drug_", "_Piano",
    "_Tutorial", "_FW22NFZ",
    "_GameMaster", "_Invictus", "_FW_25",
    "_Prison",
]
```
**Status:** name-based by necessity. Structural filtering verified
**impossible** against 920 vehicle records. AI, mission and template
variants (`*_PU_AI_*`, `*_Boarded`, `*_Hijacked`, `*_AI_Template`, …)
are structurally near-identical copies of their player base record —
same component set, same `VehicleComponentParams`, same
`SAttachableComponentParams.AttachDef`, same `defaultLoadout`. The
only discriminator inside the Game2.xml dataforge is the className
suffix injected by mission designers; shop and AI-spawn references
that would discriminate them live outside Game2.xml.

Candidates tried and rejected:
- `DefaultEntitlementEntityParams.canEntitleThroughWebsite` — actually
  means "sold for cash on RSI website", not "player flyable".
  Concept ships (Asgard, Perseus, Scorpius, Zeus Mk II …) are in-game
  earnable but lack this flag.
- Component-set diff (PU_AI_CIV vs player) — identical.
- Cross-reference scan for GUID mentions in Game2.xml — only 5
  `AIWaveMember` references for one AI variant; most AI variants
  carry zero external references in the dataforge.

**Partial structural rescue applied:** two structural checks run before
the name-based filter:
- `_is_placeholder_record` — catches records where
  `VehicleComponentParams.vehicleName == "@LOC_UNINITIALIZED"` OR
  `vehicleDefinition == ""`. Handles pure templates and some unmanned
  placeholders.
- `_is_not_included` — catches records where CIG's own
  `StaticEntityClassData/EAEntityDataParams.inclusionMode ==
  "DoNotInclude"`. This is a marketing/build flag meaning "not in the
  current PU build" — WIP rebalances (e.g. `AEGS_Idris_M_PU`), retired
  loadout presets (e.g. the Hercules bomb-config variants), faction
  paint drafts (`ANVL_Ballista_EA_UEE`), and scripted-mission variants
  (`*_Indestructible`, `*_NoCrimesAgainst`). This is the single
  strongest structural exclusion signal found; it eliminated three
  explicit per-ClassName entries from `_NOT_PLAYER_OWNABLE` and
  cleaned up several dupe groups automatically.

  Caveat: `inclusionMode=ReadyToInclude` does NOT mean "player-ownable"
  — AI variants, mission NPCs, and templates are also marked
  `ReadyToInclude` because they spawn in the PU. So this signal is
  additive with name-based patterns, not a replacement.

The name list still drives the rest (AI/mission/NPC variants that CIG
legitimately includes in the build but that aren't player-flyable).

**Revisit when:** CIG adds a dedicated `aiOnly` / `playerOwnable` flag
to `VehicleComponentParams`, or when the project starts parsing shop /
mission / encounter records from ObjectContainers.

Hard-coded exclusions alongside the pattern list, with their reasons:
- `AEGS_Javelin` — "In Concept" on the pledge store, not yet
  implemented. Flight-readiness is a business rule not encoded
  structurally anywhere.
- `_Tier_` — Apollo med-bed module-config sub-variants of the same
  ship. Both `RSI_Apollo_Triage` and `RSI_Apollo_Medivac` base
  records exist separately; `_Tier_1/2/3` share the same vehicleName
  and vehicleDefinition, so no structural field separates them.

### 2. `nova/builders/ships.py` — orbital/probe/securitynetwork drop *(resolved 2026-04-21)*
Replaced 4-substring ClassName match with structural
`_is_non_pilotable(record)`: true when the defaultLoadout tree contains
no seat port at all. Catches exactly the 16 static entities (orbital
sentries, comms probes, EAObjectiveDestructable, satellites) plus
templates, derelicts, and SalvageableDebris that lack seats — these are
redundantly filtered by other stages but the cross-cutting structural
check is the cleaner primary filter. Zero output diff.

### 3. `nova/builders/ships.py` — `_Tier_` drop *(investigated, kept)*
Attempted structural replacement: group accepted records by `vehicleName`
and drop non-shortest ClassNames. Catches Apollo_Medivac_Tier_1/2/3
correctly, but also drops 7 legitimate sibling variants — Executive
Editions (Exec_Military + Exec_Stealth share a PYAM_Exec vehicleName
between them) and Collector variants that share the base's vehicleName
(e.g. RSI_Polaris / RSI_Polaris_Collector_Military). Reverted; `_Tier_`
ClassName infix retained as documented convention tag (no legitimate
ship uses `_Tier_` in its name).

### 4. `nova/builders/ships.py` — `AEGS_Javelin` hard-coded *(resolved earlier)*
No longer hard-coded. Handled by `_is_not_included`: CIG's own
`EAEntityDataParams.inclusionMode == "DoNotInclude"` on the Javelin's
entity XML. The Javelin-specific className check was removed when the
inclusionMode signal was wired in.

### 5. `nova/builders/ships.py` — `_Unmanned` suffix *(investigated, kept 2026-04-21)*
Verified byte-for-byte: the 7 `*_Unmanned` variants (Mantis, 890Jump,
Spirit_C1, Nomad, Hull_C, Zeus_ES, 600i) are structurally identical to
their base records — same components, same attachDef, same
defaultLoadout, same vehicle fields. Mission-designer ClassName
aliases with no structural discriminator. Name-suffix check retained as
last-resort with documentation.

### 6. `nova/builders/ships.py` — `_is_salvageable_debris` *(resolved 2026-04-21)*
Replaced path + ClassName-prefix checks with
`vehicle.movementClass == "Dummy"`. Exact match: every Dummy-movement
record is a SalvageableDebris and vice-versa (7/7 across the corpus).
Zero output diff.

### 7. `nova/builders/ship_equipment.py:6` — `_is_non_equippable`
```python
if cn.endswith("_template") or "_template_" in cn: return True
if cn.startswith("test_") or "_test_" in cn or cn.startswith("master_"): return True
if "lowpoly" in cn or "fakehologram" in cn or "_dummy" in cn: return True
if "pudefenseturret" in cn: return True
if "destructible_pu" in cn or "_ground_destructible" in cn: return True
if "_pu_ai_van" in cn: return True
```
Drops ship/vehicle equipment entirely. **Proposed:** templates and test
items generally lack a manufacturer reference, have
placeholder names (`@LOC_PLACEHOLDER`), or live under a specific
`Tags`/`itemType` signal. NPC-only (`pudefenseturret`, `_pu_ai_van`)
should be detectable from a tag or loadout reference, not the name.

### 8. `nova/builders/fps_weapons.py:13` — `_is_non_player_fps`
```python
if cn.startswith("carryable_") or cn.startswith("entityspawner_"): return True
if cn.endswith("_template") or cn.startswith("test_") or "_template_" in cn: return True
if cn in ("janitormob", "tablet_small", "yormandi_weapon"): return True
if cn.startswith("vlk_"): return True
if "salvage_repair" in cn: return True
if any(p in cn for p in ["mine", "_ltp_", "_prx_", "lasertrip", "proximity"]): return True
```
**Proposed:** Vanduul (`vlk_`) items likely have a faction/NPC tag.
Mines probably have a `SCItemExplosiveParams` + non-weapon component
profile. `carryable_` items lack a `WeaponPersonal`/`Knife`/`Grenade`
type — could be filtered on `Type` alone rather than name.

### 9. `nova/builders/fps_weapons.py` — FPS orphan-variant drop *(investigated, kept 2026-04-21)*
`_01_<suffix>` ClassName pattern marks CIG dev/event/skin variants.
Tried removing it in favour of the existing signature-based dedup in
the second pass — 3 items with genuinely-different signatures leaked
through (sasu_pistol_toy_01_ea_elim, grin_multitool_01_default_grapple,
kegr_fire_extinguisher_01_Igniter). Signature dedup alone is
insufficient; the name check is editorial (ref-catalogue convention).
Retained with experiment-based documentation.

### 10. `nova/builders/fps_weapons.py` — `_find_base_weapon` *(documented 2026-04-21)*
Segment-stripping is used to find a base for signature comparison (not
as a filter, so a miss is non-fatal). No structural parent/inherit
reference exists in parsed item records. `SCItemPurchasableParams.
displayName` clusters variants together but doesn't identify the base
within a cluster. Kept with rationale in-line.

### 11. `nova/builders/fps_attachments.py` — `_is_fps_attachment` *(resolved 2026-04-21)*
Replaced uppercase-first-letter ship vs FPS barrel rule with the
structural `FPS_Barrel` tag (CIG's own marker on FPS barrels; ship
barrels carry `uneditable` instead). Template-skip also moved to
structural `name==@LOC_PLACEHOLDER + no manufacturer`, scoped to
`WeaponAttachment` to avoid dropping valid `Light.Weapon`
underbarrel-light items (verified). Zero output diff.

### 12. `nova/builders/fps_attachments.py` — `_find_base_attachment` *(documented 2026-04-21)*
Same rationale as #10.

### 13. `nova/builders/stditem.py` — FPS path detection *(resolved 2026-04-21)*
Replaced path-substring check with structural `_is_fps_item(item_type,
full_type, attach_def)` helper — allow-list of base types
(`WeaponPersonal`, `AmmoBox`), specific WeaponAttachment.* full types
(`Light.Weapon`, `Magazine`, `IronSight`, `BottomAttachment`,
`Utility`, `Missile`), plus FPS_Barrel tag discrimination for the
shared `WeaponAttachment.Barrel` type. Both use sites updated
(`is_fps` flag in build_std_item + `_build_classification` prefix).
Zero output diff.

### 14. `nova/builders/stditem.py` — FPS classification fallback *(resolved as part of #13)*
`"personal" in type_lower` substring check replaced by the structural
`_is_fps_item` helper (WeaponPersonal base type is in the allow-list;
`Paints.Personal` is correctly excluded because `Paints` isn't a FPS
base type).

---

## HIGH — entity-category classification by port / class name

These map a port or item to a category (weapon, turret, thruster, shield,
…). Port data in the vehicle-impl XML carries `types` and `portTags` which
are the intended structural classifier.

### 15. `nova/builders/ships.py` — `_classify_port` *(resolved 2026-04-21)*
Was ~100 lines of substring matches against `port_name.lower()`.
Now driven by:
1. `_SKIP_PORT_TYPES` frozenset of non-gameplay types (Seat*, Door,
   *Controller, Ping, Scanner, Display, Room, AIModule,
   WeaponRegenPool, LandingSystem, Light, Battery, Computer, etc.) —
   skip when every declared type is in this set.
2. Structural allow-list: `WeaponGun.*` → PilotWeapons,
   `MissileLauncher.*` → MissileRacks, `BombLauncher.*` → BombRacks,
   `WeaponDefensive.*` → Countermeasures,
   `QuantumInterdictionGenerator` → InterdictionHardpoints,
   `Turret.*` → Turrets (unless `tractor` in pn → UtilityHardpoints),
   `UtilityTurret.*` + mining → MiningHardpoints, plus 1:1 mappings
   for PowerPlant / Cooler / Shield / QuantumDrive / Radar.* /
   LifeSupportGenerator|System / FuelIntake / FuelTank /
   QuantumFuelTank.* / Armor / CargoGrid / SelfDestruct /
   FlightController / Paints / Flair_Cockpit.*.
3. Thrusters: `MainThruster` | `ManneuverThruster` port type, split
   Main/Retro/VTOL/Maneuvering via the installed item's
   `SCItemThrusterParams.thrusterType`.
4. Last-resort name-based branch: fires only when `types_are_meaningless`
   (no types, or only `Misc` / `Usable` / `Useable`) OR for the
   genuinely-ambiguous categories (WeaponsRacks where the port type is a
   Door mechanism; Mining/Salvage where types mix Container.Cargo /
   UtilityTurret / ToolArm / SeatAccess depending on ship).

Net effect vs pre-refactor baseline: 776 port-level reclassifications
across 7 ships, all structurally defensible (e.g. gimballed guns with
both `Turret.GunTurret` and `WeaponGun.Gun` now correctly land in
PilotWeapons; hovercraft fans are picked up as thrusters; SeatAccess
ports named `hardpoint_turret_*` no longer surface as turrets). Matrix
compare unchanged (262 ships / 209 matched / 0 gaps).

### 16. `nova/builders/ships.py:238` — armor detection
```python
if item and ("armor" in pn or "armour" in pn
             or (entity_class and entity_class.startswith("ARMR_"))):
```
**Proposed:** `item_type == "Armor"` (allow-list of subtypes if needed).

### 17. `nova/builders/ships.py:357` — cargo/storage split
```python
if "cargogrid" in pn or "cargo_grid" in pn or "cargo" in pn:
    cargo_grid_scu += capacity
else:
    storage_scu += capacity
```
**Proposed:** the installed item's type
(`Container.Cargo` vs. inventory-container storage) distinguishes cargo
grid from personal storage structurally.

### 18. `nova/builders/ships.py:422..439` — thruster classification
Mixed: starts with `SCItemThrusterParams.thrusterType` (structural) but
falls back to substring checks on port name and entity class. Door
detection at line 439 is entirely name-based.
**Proposed:** always use `thrusterType`; for doors use item
`Type == "Door"` rather than `hardpoint_door`/`door_` prefix.

### 19. `nova/builders/ships.py:463` + `:645` — duplicate thruster classifier
Two copies of `_classify_thruster` / `_classify_thruster_type` fall
back to `vtol`/`retro`/`main`/`thruster` substring checks on port name
and class name. **Proposed:** use `SCItemThrusterParams.thrusterType`
exclusively; deduplicate the two helpers.

### 20. `nova/builders/ships.py:1519` — gimbal/turret flag
```python
if "gimbal" in entity_class.lower() or "turret" in full_type.lower():
    entry["Gimballed"] = True
```
**Proposed:** check for a `SCItemTurretParams` / `gimballedMount`
component rather than substring-matching the class name.

### 21. `nova/builders/ships.py:1643` — Noise vs Decoy countermeasure
```python
if "noise" in entity_class.lower() or "chaff" in entity_class.lower():
    entry["Type"] = "Noise"
elif "flare" in entity_class.lower() or "decoy" in entity_class.lower():
    entry["Type"] = "Decoy"
```
**Proposed:** countermeasure ammo has a structural type
(`SCItemCountermeasureAmmoParams.countermeasureType` or similar).
Confirm and use it.

### 22. `nova/entity_parser.py:117` — `classify_port` *(resolved 2026-04-21)*
Dead code — no callers anywhere in the project. Deleted.

### 23. `nova/builders/ships.py:754`, `:1240`, `:1346` — pool-size lookups
```python
ctx.weapon_pool_sizes.get(class_name.lower(), 0)
```
The indices (`weapon_pool_sizes`, `shield_pool_sizes`) are keyed by
lowercased class name. Name-based by construction.
**Proposed:** store the pool map keyed by a GUID / structural reference
if one is available in the source XML.

### 24. `nova/vehicle_impl_parser.py:274` — segment-stripping lookup
```python
base = class_name.split("_")
for i in range(len(base), 1, -1):
    candidate = "_".join(base[:i])
```
Fallback to find a vehicle-impl XML by progressively stripping
className segments. Same pattern as the removed paint filter.
**Proposed:** look up by `vehicle.vehicleDefinition` path (which is
already a structural reference into the XML) rather than by class-name
shape.

---

## MEDIUM — className-driven overrides inside stditem

These are per-type exceptions inside `build_std_item`. Each one needs a
short investigation of the underlying record to find the structural
signal.

### 25. `nova/builders/stditem.py` — `Container.Cargo` mass skip *(resolved 2026-04-21)*
Replaced three ClassName rules with three structural checks:
- Mining pods → `ResourceContainer` component present.
- Cyclone swap modules → `attachDef.tags == "TMBL_Cyclone_Module"` (CIG's
  own tag, already applied to all 6 sub-module variants).
- CargoGrid_Main placeholders → `attachDef.name == "@LOC_PLACEHOLDER"` +
  `SCItemInventoryContainerComponentParams` + volume==1.
Verified against all 22 Container.Cargo items in the corpus; zero output
diff.

### 26. `nova/builders/stditem.py` — Storm missile rack exception *(resolved 2026-04-21)*
Replaced the `"Storm" not in cn` check with
`SCItemPurchasableParams.displayName != "@LOC_PLACEHOLDER"`. Vehicle-
integrated rack variants (Nova / Ballista / Cyclone MT/AA) alias an
existing standard rack via `displayName`, while truly standalone racks
(Storm) carry a placeholder displayName. Verified across all 8 rack
items; zero output diff.

### 27. `nova/builders/stditem.py` — Remote turret mass skip *(resolved 2026-04-21)*
Replaced `"Remote" in cn` with `"Remote" in attachDef.name`. The
`attachDef.name` is CIG's localization key identifying turret class
(`@item_Name_Turret_Manned` vs `@item_Name_Turret_Remote` vs
ship-specific `@item_NameDRAK_Cutlass_Steel_RemoteTurret`). Zero output
diff. (Note: `SCItemTurretParams.remoteTurret` is present on every
turret — even manned ones — so that field couldn't discriminate.)

### 28. `nova/builders/stditem.py` — Salvage head mass skip *(resolved 2026-04-21)*
Replaced `cn.startswith("Salvage_Head_")` with `"SDistortionParams" not
in components`. Tractor beams carry `SDistortionParams` (beam rendering);
salvage heads never do. Zero output diff.

### 29. `nova/builders/stditem.py` — LifeSupport class *(resolved 2026-04-21)*
Replaced `class_name.startswith("LFSP_S04_")` with
`attachDef.size == 4` in both `stditem.py` and the
`ships.py:1486` BaseLoadout duplicate. Size-4 LifeSupport is the capital
tier (Idris / Polaris / 890) and is ship-integrated; smaller sizes are
player-purchasable civilian grade. Zero output diff.

### 30. `nova/builders/stditem.py` — Blade modifier *(deferred)*
`_apply_blade_modifier` still uses ClassName suffix (`_Blade_HND` /
`_Blade_SPD`) plus hardcoded delta values. The proper structural fix
requires parsing `SIFCSModifiersLegacy` records into the build context
and applying their actual `numbers` / `vectors` deltas — a multi-file
refactor touching `dataforge_parser.py` + `BuildContext` + this helper.
Verified the ClassName suffix is a 1:1 proxy for the referenced record
name (all HND blades point to the same `FlightBlade_HND` GUID; same for
SPD) and that the hardcoded deltas match the record values. Comment in-
line explains the trade-off. Revisit if deltas need tuning or new blade
variants appear.

### 31. `nova/builders/stditem.py` — Cargo-pod classification *(resolved 2026-04-21)*
Replaced the two ClassName prefixes with component-set + type checks:
- `is_ship_mining`: `full_type == "Container.Cargo"` + `ResourceContainer`
  present + no `SCItemInventoryContainerComponentParams`.
- `is_ground_mining`: `full_type == "Container.Cargo"` + both
  `ResourceContainer` AND `SCItemInventoryContainerComponentParams`.
The `Container.Cargo` full-type gate prevents non-mining ResourceContainer
items (e.g. `Container.Medical` healing canisters) from hitting the
mining branches. Zero output diff. (`is_cargo_grid_main` still uses the
`_CargoGrid_Main` suffix — see #32.)

### 32. `nova/builders/stditem.py` — Cyclone cargo-grid drop *(investigated, kept)*
Single-className match retained as documented last-resort. Verified that
`TMBL_Cyclone_CargoGrid_Main` is structurally identical to
`ARGO_CSV_CargoGrid_Rear` and `ExternalInventory_BoxCrate_*_1SCU_a` (all
three: capacity=1 with 1.25^3 interior dimensions). A generic
`capacity==1 + minimal dims → skip` rule would drop those two sibling
items too, diverging from the reference catalogue. Comment in-line
explains why className-exact-match is the correct scope here.

### 33. `nova/builders/stditem.py` — FPS class by prefix *(partially resolved 2026-04-21)*
- Melee now structural: `full_type == "WeaponPersonal.Knife"` (every
  `*_melee_*` ClassName has this type — verified in the corpus).
- Energy / Ballistic classification remains ClassName-suffix based. CIG
  encodes this as an editorial label; the weapon component's `fireType`
  (rapid / sequence / charged / burst) cuts across both classes, and the
  ammo record damage-type isn't populated for personal weapons in the
  current parse. Comment in-line explains the limitation. Revisit if
  the ammo-record parse is extended.

### 34. `nova/builders/stditem.py:1519` — turret-in-type flag (also listed
under 20, but leaves a cross-check here)
See entry 20.

---

## LOW — curated allowlists keyed by className

These are explicit per-item exception sets used to match a reference
dataset. They are name-based by construction but at least audited. They
should shrink over time as the structural rules behind each exception are
identified.

| File | Set | Purpose |
|---|---|---|
| `stditem.py:38` | `_WEAPONDEFENSIVE_CN_WITHOUT_CLASS` | Reliant/Guardian CM exceptions |
| `stditem.py:53` | `_CLASS_VALUE_OVERRIDES` | Hand-picked Class values |
| `stditem.py:74` | `_TOOLARM_WITH_TURRET` | Salvage arms that expose Turret |
| `stditem.py:82` | `_CLASS_OMIT_CLASSNAMES` | Items where Class must be dropped |
| `stditem.py:100` | `_TURRETS_WITHOUT_CLASS` | Integrated/fixed turret mounts |
| `stditem.py:112` | `_PAINTS_WITHOUT_CLASS` | Ship-variant paint exceptions |
| `stditem.py:127` | `_MISSILERACK_WITHOUT_MASS` | Aurora/BEHR S02 mass exceptions |
| `stditem.py:134` | `_MASS_FORCE_INCLUDE` | Override skip-mass rule |
| `stditem.py:147` | `_MISSILERACK_WITHOUT_CLASS` | Ship-integrated missile racks |
| `stditem.py:175` | `_ARMOR_MEDIUM_WITH_CLASS` | Armor.Medium Class allowlist |
| `stditem.py:68` (inside `_CLASS_VALUE_OVERRIDES`) | specific Paints | ship-variant rules |
| `stditem.py:*` (FPS) | `_FPS_CLASS_OMIT`, `_FPS_CLASS_BY_CLASSNAME`, `_FPS_CLASS_EMPTY` | FPS class exceptions |

Each row is a candidate for collapsing into a structural rule. When doing
that, the rule in CLAUDE.md applies: open one member of the set, inventory
the structural fields, look for the one that actually distinguishes the
set from non-members, and verify against a few known-good / known-bad
cases before removing the allowlist.

---

## Notes on false positives

The following hits look name-based but are **not**; leave them alone:

- `description.startswith("@")`, `raw_name.startswith("@")`,
  `desc.startswith("@")` — localization-key detection; `@` is the
  structural prefix for unresolved keys.
- `flags_str.lower()` / `"uneditable" in flags_lower` — parsing a
  structural `flags` string from the port definition.
- `movementClass.lower() in {"arcadewheeled", "wheeled", "tracked"}`
  (`ships.py:24`, `slices.py:54`) — `movementClass` is a structural
  field; the lowercase comparison just normalizes its value.
- `fire_type.startswith("burst")` (`stditem.py:1433`, `:1619`) —
  `fireType` is a structural enum on the firing-mode component.
- `"fpsWeapon" in components` (`fps_weapons.py:98`) — component-key
  membership, which is the structural signal CLAUDE.md recommends.
- `item_type.startswith("EMP" / "ToolArm")` and
  `"MannedTurret" in item_type` / `item_type.startswith("Turret.Utility")`
  (`ships.py:1770..1780`) — `item_type` is the structural `Type` field,
  not `ClassName`.
