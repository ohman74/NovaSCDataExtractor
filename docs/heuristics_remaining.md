# Heuristics — what's left after the 2026-05-04..2026-05-05 work

Snapshot of remaining name-pattern matches across the extractor, after
the turret + storage refactors. Each entry is grouped by whether a
clean structural replacement exists.

## Inventory (post-2026-05-06 structural sweep)

- **`ships.py`**: 38 name-string matches (was ~110 originally; ~62
  after 2026-05-02 fallback removal; ~40 after 2026-05-05 P1/P2/PDC/
  RT/decorative work; **38 after controller-component refactors**).
- **`stditem.py`**: 0 substring filters (FlightBlade HND/SPD resolved
  2026-05-06 via SIFCSModifiersLegacy record parsing; FPS Class
  `_energy_`/`_ballistic_`/`_multi_` substring matching replaced
  2026-05-06 with structural ammo-damage-profile derivation).
- **`ship_equipment.py`**: 6 (already-audited item filters; re-confirmed
  2026-05-06 — no structural alternative without over-filtering).
- **`fps_weapons.py`**: 4 (down from 6 after 2026-05-06 structural sweep
  — replaced `carryable_/entityspawner_`, most templates, dev gadgets,
  and mines with single component-presence check).

Total ≈ **48 lines** matching by name. Most remaining are confirmed
fallbacks for empty/unfilled ports where no item exists to inspect
structurally. Detailed status below.

---

## Retirable (best ROI)

### R1 — Item-filter A.1 / A.2 audit — **partially refactored 2026-05-06**

**ship_equipment.py (6 filters)**: Investigated 2026-04-21 (#7), re-audited
2026-05-06 against the 2888-item baseline reference. Confirmed irreducible:
- Templates (133), test/master (8), LowPoly (27), PUDefenseTurret (3),
  ground destructibles (30), PU_AI_VAN (4) — all share component
  signatures with legitimate items. `health=0` only catches 1/133
  templates; "no manufacturer + LOC_PLACEHOLDER" over-filters 76 items
  the baseline keeps (Locker_PH, GRIN_ROC_CargoGrid_Main, RN_*, etc).
  "Twin-existence" (LowPoly/PU_AI_VAN have non-suffixed siblings) is
  technically structural but still keys on suffix-stripping.

**fps_weapons.py (was 6 filters → now 4)**: 2026-05-06 sweep replaced
4 name patterns with one structural test. New rule: an item is
player-equippable only if it carries a functional weapon component
(`SMeleeWeaponComponentParams`, `SWeaponModifierComponentParams`,
`weapon`, or `SPrimeableComponentParams`). Verified against ref4 (174
items) — 0 false drops, 0 false keeps.

Eliminated by structural rule:
- `carryable_*` / `entityspawner_*` (22 items) — glowsticks, utensils
- Most `_template` / `test_*` (4 of 5) — skeleton entities
- Most dev placeholders (`JanitorMob`, `Tablet_Small`)
- All currently-filtered mines (`behr_prx_*`, ProximityMine_Template,
  LaserTripMine_static_Template, etc.)

Surviving name fallbacks (4):
- `_template` suffix: `FPS_Throwable_TEMPLATE` carries weapon comp
- `vlk_` prefix: 11 Vanduul NPC weapons carry real `SMeleeWeapon...`
- `salvage_repair`: 3 attachments routed to fps_attachments.py
- `Yormandi_Weapon`: dev placeholder with weapon comp

### R2 — `_CargoGrid_Main` override — **fully resolved (2026-05-05)**

Two pieces:
- `is_cargo_grid_main = class_name.endswith("_CargoGrid_Main")` (dead
  variable, never read). **Removed.**
- `if class_name == "TMBL_Cyclone_CargoGrid_Main": return` exception
  at line ~2893. **Removed** after the project owner confirmed the
  base TMBL_Cyclone in-game has a 1 SCU cargo box behind driver +
  passenger — REF was wrong to omit it. The 2026-04-21 NAME_FILTERS
  #32 entry was REF-driven; it's now obsolete because we follow XML
  truth, not REF. Net visible-output change: zero (the item is
  filtered upstream by ship_equipment's `_INCLUDED_TYPES` which
  excludes standalone `CargoGrid` items, and it appears in
  vehicle_hardpoints.Modules via the proper module-attach chain
  TMBL_Cyclone -> TMBL_Cyclone_Module_Cargo -> TMBL_Cyclone_CargoGrid_Main).

### R3 — Armor detection in `_build_armor_stats` — **resolved (2026-05-05)**

Replaced `("armor" in pn or "armour" in pn or className.startswith("ARMR_"))`
with `attachDef.type == "Armor"`. Verified 198 items carry the type
and 0 ARMR_-prefixed items lack it. Zero output diff.

### R4 — Thruster classifier deduplication — **resolved (2026-05-05)**

`_classify_thruster` (FlightCharacteristics) and
`_classify_thruster_type` (FuelManagement) were near-identical. Merged
into one helper `_classify_thruster_role(port_name, class_name,
vtol_label)`. The substring matching itself is **kept**: tested using
`SCItemThrusterParams.thrusterType` as the primary signal, but it's
unreliable — Retaliator's `AEGS_Retaliator_Thruster_Retro` reports
thrusterType=Maneuver, and VTOL thrusters report Maneuver or Main.
Documented inline.

### R5 — TYPE_TO_SLICE for ports with missing impl-types — **RESOLVED**

Already implemented in `_classify_port` lines 2112-2198 (the
"Secondary: installed-item attachDef.type allow-list" block,
introduced in the 2026-05-02 fallback-removal refactor). Covers
~22 item types including weapongun, missilelauncher, bomblauncher,
weapondefensive, turret (full-type routing), shield, powerplant,
cooler, quantumdrive, radar, paints, fueltank, quantumfueltank,
fuelintake, armor, lifesupport, selfdestruct, emp,
quantuminterdictiongenerator, flair, wheeledcontroller,
flightcontroller, cargogrid, and thruster (with
SCItemThrusterParams sub-routing). Falls back to None (no
classification) when both port-types and item-type are absent.

---

## Possibly retirable (unclear payoff)

### P1 — Mining/Salvage on UtilityTurret + ToolArm — **RESOLVED 2026-05-05**

Replaced port-name `"mining"`/`"salvage"` heuristic with installed
item's inner port type:
- inner WeaponMining.Gun → MiningHardpoints
- inner SalvageHead / SalvageFieldEmitter → SalvageHardpoints

Verified across all ToolArm + UtilityTurret items in parsed_items —
clean structural signal. Port-name fallback retained only for empty
arm/turret ports where the installed item is missing.

### P2 — Cargo ore-pod routing — **RESOLVED 2026-05-05**

Replaced 4 className-substring checks
(`mining_pod`/`_ore_pod`/`groundvehiclemining_pod`/`shipmining_pod` in
className) with single structural rule: `Container.Cargo` +
`ResourceContainer` component → CargoContainers. Verified 100%
discriminator across 22 Container.Cargo items (9 mining-named all have
ResourceContainer, 13 non-mining all lack it). Port-name fallback for
empty pod slots retained. Zero output diff.

### P3 — Module-port detection (lines ~2061, ~2100)

```
if "module" in pn and (has_type("module") or has_type("turretbase") ...):
if has_type("room") and "module" in pn:
```

Module ports are gated on type AND name. The name fallback handles
modular ships (Cyclone) where same type is used for swappable bays.
Likely irreducible — types aren't enough.

---

## Structurally irreducible (CIG provides no clean signal)

Marked ✓ in `heuristics_audit.md`. Don't try to refactor these —
audited.

### I1 — Decorative items — **PARTIALLY STRUCTURAL (2026-05-05)**

```
camera_turret / bomb_turret in item_cn  (editorial-only fallback)
```

Restructured 2026-05-05:
1. `has_doorpart` — inner port has DoorPart subtype (catches genuine
   door assemblies at any port).
2. **Structural cap/cover detection**: at Turret/TurretBase port, item
   has non-Turret type (Misc/AttachedPart/Door/etc.) AND no
   weapon-bearing inner ports → decorative. Catches Misc.UNDEFINED
   Turret_Caps, AttachedPart caps, door_* without DoorPart inner.
3. **Editorial fallback (irreducible)**: `camera_turret` /
   `bomb_turret` in className. These items are structurally identical
   to real combat turrets (Turret.GunTurret + WeaponGun.Gun inner +
   `turretOnlyUsableInRemoteCamera=1`) — REF excludes them by editorial
   choice only. CIG provides no structural distinguisher.

### I2 — Remote-turret className (G4) — **PARTIALLY STRUCTURAL (2026-05-05)**

```
"_remote" in item_cn_lower and "_turret" in item_cn_lower
"_ai_turret" in item_cn_lower
```

RT items live under same `Turret.*` types as MT. Added structural
signal: `SCItemTurretParams.remoteTurret.SCItemTurretRemoteParams.
turretOnlyUsableInRemoteCamera == "1"` catches 79+10 items
including some without _remote_turret className (Centurion S4,
Javelin Large, Terrapin Support, Starlifter Bomb_Turret).
className fallback still needed for ~6 RSI_Bengal items where the
remote_params field is absent.

Primary RT detection (controllableTags ctrl_tag) remains the
authoritative signal; className + structural item flag are
fallbacks for the secondary block when port_def is missing.

### I3 — Thruster sub-classification (B.3) — confirmed irreducible 2026-05-05

```
"retro" in pn        / "_retro" in item_cls
"vtol" in pn         / "_vtol" in item_cls
"thruster_pipes"     / "_pipes" in pn
```

Retro/VTOL/Maneuvering all share `MainThruster` or `ManeuverThruster`
parent type. Sub-type isn't in any structural field.

Audited 2026-05-05:
- `SCItemThrusterParams.thrusterType` is **unreliable** — Hull_A's
  `_Thruster_VTOL` items report thrusterType=Retro; Retaliator's
  `_Thruster_Retro` reports thrusterType=Maneuver. CIG data
  inconsistency.
- `SCItemThrusterParams.onlyActiveInVTOL=1` covers only **19/52**
  VTOL items (37%). The rest are multi-mode swiveling thrusters
  (Asgard 4-motor, Cutlass 2-motor — they pivot down for VTOL,
  back for normal flight) where `onlyActiveInVTOL=0` but the
  thruster IS used for VTOL.
- REF's VTOL category is editorial; CIG's actual data has the
  more nuanced "VTOL-only vs multi-mode" distinction.

Conclusion: className/port-name fallback is the only way to match
REF's binary VTOL classification. Confirmed irreducible.

### I4 — Weapon racks (G1)

```
elif "weapon_rack" in pn or "weaponlocker" in pn ...
```

The structural replacement (check installed item's sub-ports for
`WeaponPersonal` type) ALREADY runs first; this `elif` only fires
for empty rack ports (no installed item). No structural signal for
unfilled mounts.

### I5 — PDC discrimination — **STRUCTURAL (2026-05-05)**

```
attachDef.subType == "PDCTurret"  (item-level, structural)
"pdc" in port_tags.split()        (impl-XML port tag)
"pdc" in pn / "point_defense" in pn  (last-resort fallback)
```

Item-level structural signal added 2026-05-05: 17/17 PDC items
have `attachDef.subType == "PDCTurret"`. Port-tag and port-name
fallbacks retained for empty PDC ports without installed item.

### I6 — Tractor disambiguation — **STRUCTURAL (2026-05-05)**

Three structural signals (in priority order):
1. `has_tractor_inner` — installed item's own inner port has
   `TractorBeam` type (Polaris/Spirit/Hull_B/RAFT/Reliant/Cutlass).
2. `ctrl_has_tractor` — port_def.controllableTags contains "tractor"
   (Hull_C `tractorSeat`, Caterpillar `TractorBeamLeftSeat`).
3. `_has_descendant_type` — recursive walk through loadout-entry
   children at any depth (catches future configs where tractor
   items are installed via the ship's loadout below the wrapper).

className-substring fallback REMOVED. Port-name "tractor" remains
only as ultimate fallback for empty / decorative ports with no
loadout content and no impl-XML controllableTags.

### I7 — Variant-suffix markers (D)

```
"_Tier_" in cn       (AI tier variant exclusion)
cn.endswith("_Unmanned")
"_Flight_Blade_HND/SPD"
```

Variants of an item that share the type with the base. CIG provides
no enable/version flag. Irreducible.

### I8 — Countermeasure type (C.1) — confirmed irreducible 2026-05-05

```
"noise" in entity_class.lower()
"flare" in entity_class.lower()
```

Chaff/Flare/Decoy distinction not exposed in attachDef. Verified
2026-05-05: ALL 60+ chaff/flare AMBX_* items have
`type=UNDEFINED.UNDEFINED`, `tags=''`, and only `SAttachableComponentParams`
+ `GlobalResourceAudio` + `SMicroCargoUnit` components. CIG provides
ZERO structural distinction between Noise (chaff) and Decoy (flare).
The className suffix is the ONLY signal. ✓

### I9 — Capital storage racks (lines 1675, 1684)

```
"torpedo_storage" / "missile_storage" in pn
```

Perseus torpedo storage racks — emit nothing (REF excludes). Port
name is the only signal. Confirmed.

---

## Confirmed-needed name fallbacks (kept on purpose)

These are documented in code comments as gracefully-degrading port-name
fallbacks for ports with missing/generic `port_def.types`. They route
to specific output slices when the structural type signal is absent:

- `weapon_mount` / `weapon_pilot` (line 1610) — empty pilot weapon ports
- `_module` / `pn.endswith("module")` (line 1614) — module ports
- `controller_wheel` (line 1960) — wheeled drivetrain controller
- `cargogrid` / `cargo_grid` (line 2025) — cargo grid ports
- `mining` (line 2023) — generic mining ports
- `stored_pod` (line 2021) — empty pod slots (drop)

Removing these would lose data for ships where the impl XML is
incomplete. The 2026-05-02 fallback-block removal already pruned the
unreachable branches; what's left is reachable.

---

## Priority order

After 2026-05-06 work, no more known structural improvements are
pending. All remaining name-string matches fall into one of:

1. **Empty/unfilled port fallbacks** — no item exists to inspect
   structurally. Examples: empty weapon-rack ports, empty PDC ports,
   empty tractor ports, empty pilot-weapon-mount ports, empty pod
   slots, decorative pipe ports.
2. **Editorial-only distinctions where CIG provides no structural
   field** — camera_turret/bomb_turret (structurally identical to
   real combat turrets), countermeasure noise/flare (all UNDEFINED),
   variant suffixes (`_Tier_`, `_Unmanned`, `_HND/SPD` —
   byte-identical with their bases), thruster sub-class fallback
   (CIG's thrusterType is unreliable; multi-mode thrusters have
   onlyActiveInVTOL=0 even when they're VTOL).
3. **Item-filter exclusions audited 2026-04-21** — debug/test/
   template items, faction (vlk_) items, etc. Detailed in NAME_FILTERS.md.
4. **Sub-classification within identical types** — turret seat vs
   engineering seat (both Seat.UNDEFINED); B.3 confirmed irreducible.

Each remaining heuristic has been verified as either fallback for
genuinely missing structural info OR exists where CIG provides zero
structural distinction.

Resolved 2026-05-05:
- R1 (item-filter audit) — already-audited 2026-04-21.
- R2 (`_CargoGrid_Main`) — dead variable removed; TMBL_Cyclone
  exception removed after project owner confirmed XML truth.
- R3 (armor) — structural via `attachDef.type == "Armor"`.
- R4 (thruster dedup) — consolidated; substring-matching kept
  because `thrusterType` is unreliable.
- **Thruster routing reorder** — port-name priority over
  thrusterType (Hull_A `_Thruster_VTOL` reports thrusterType=Retro,
  CIG inconsistency).
- **P1** (Mining/Salvage routing) — installed item's inner port
  type (WeaponMining.Gun / SalvageHead / SalvageFieldEmitter)
  replaces port-name `mining`/`salvage` heuristic.
- **P2** (Mining ore-pod routing) — `Container.Cargo + ResourceContainer`
  component replaces 4 className substring checks. 100% discriminator
  across 22 Container.Cargo items.

I1–I9 — leave alone, confirmed irreducible.
