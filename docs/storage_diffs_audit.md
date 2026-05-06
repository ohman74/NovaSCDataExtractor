# Storage / Cargo diff audit

Snapshot of `Hardpoints.Components.{Storage,CargoGrids}` derivation
work against the local baseline `entry_2.json` reference.

## Headline (2026-05-05)

**Our XML extraction now produces correct storage counts. The reference
file is the incomplete side wherever counts disagree.** Validated
against in-game observation by the project owner across multiple
ships:

| Ship | OUT | REF | In-game (confirmed) |
|---|---:|---:|---:|
| DRAK_Cutlass_Black | 2 | 0 | 2 ✓ |
| ESPR_Prowler_Utility | 5 | 0 | 5 ✓ |
| DRAK_Corsair | 4 | 0 | 4 ✓ |
| ANVL_Terrapin_Medic | 2 | 0 | 2 ✓ |
| ANVL_Asgard | 2 | 0 | 2 ✓ |
| RSI_Zeus_CL | 3 | 3 | 3 ✓ |

Each one OUT matches the in-game placement; REF either matches us or
reports zero. None of the spot-checked ships had REF correct and OUT
wrong. The 49 "REF=0, OUT≥1" rows in the count comparison are
treated as REF undercounts (the REF tool didn't walk the relevant
data), not as our emission errors.

This is a deliberate consequence of the project rule **"XML is the
single point of truth for values; REF can be wrong; park
divergences"**. Our pipeline now reads the same `Data/ObjectContainers/
Ships/.../*.socpak` archives the running game loads, so the storage
counts we emit are the actual ship configurations.

## Refactor summary (2026-05-05)

Three structural fixes landed:

1. **Mass from `physics.mass`** (`_compute_storage`).
   `Storage.InstalledItems[*].Mass` was hardcoded `0.0`; now reads
   `components.physics.mass` from the inventory item. Removes 65 Mass
   value diffs across SeatAccess "Access" entries.

2. **Type-based filter** (`_compute_storage`).
   Replaced "skip CargoGrid/Container/Module" with positive filter
   `attachDef.type ∈ {SeatAccess, Cargo}`. Excludes incidental-inventory
   types (Usable chairs, Char_* gear) and includes Cargo personal-storage
   items routed through inventory-container component (Mustang, Scorpius,
   Pisces, etc.).

3. **Token-based suppression** (`_build_hardpoints` post-walk).
   The "drop Access when Personal Storage present" rule was a Name-string
   match; now driven by attachDef.name token: drop entries with
   `name == "@item_Name_SeatAccess_GenericExterior"` whenever the ship has
   any port-routed Container.Cargo storage **or** any computed
   `@ui_PersonalStorage` entry. Symmetrical to the previous rule but
   localization-independent.

Storage diffs went **119 → 64**.

## Remaining diff buckets

### Bucket A — Interior-placed storage items — RESOLVED via socpak walk (2026-05-05)

REF emits `Crew_Locker`, `Bunk_Storage`, `Wing_Storage`, `Captain_Locker`,
`Storage`, `Bunk`, `Locker`, `PersonalStorage_400i`,
`CRUS_Starlifter_CargoGrid_Personal_*` etc. for the interior of mid- to
capital-class ships.

Affected ships: AEGS_Reclaimer, AEGS_Retaliator, ANVL_Valkyrie,
CRUS_Intrepid, CRUS_Starlifter_A2/C2/M2, MISC_Fortune, MISC_Starlancer_Max,
ORIG_400i, RSI_Constellation_Andromeda/Aquila/Phoenix/Taurus, RSI_Polaris,
RSI_Zeus_CL, RSI_Zeus_ES, MRAI_Guardian (Bunk_Storage/Wing_Storage split).

**Discovery (2026-05-05):** the data IS in `Data.p4k` — under
`Data/ObjectContainers/Ships/{MFR}/{Ship}/*.socpak`. The original
extraction skipped these because the `unp4k "xml"` filter only pulls
`.xml` and `.dcb`; `.socpak` archives are separate ZIP files.

The structural chain is:

1. Ship entity XML (e.g. `entities/spaceships/rsi_zeus_cl.xml`) lists
   `<SVehicleObjectContainerParams fileName=".../X.socpak" boneName="..." />`
   for every interior ObjectContainer pack the ship uses.
2. Each `.socpak` is a ZIP archive containing `X.xml`, `X_editor.xml`,
   `X.soc`, plus VFX/lighting assets.
3. The `X_editor.xml` member contains `<Object type="PersonalStorage_*"/>`
   placement records — one per locker physically placed in the room.

`probe_ship_lockers.py` walks this chain and counts placements per ship.
Result against REF (2026-05-05):

| Ship | Derived | REF | Status |
|---|---:|---:|---|
| AEGS_Reclaimer | 5 | 5 | match |
| AEGS_Retaliator | 10 | 10 | match |
| ANVL_Valkyrie | 6 | 6 | match |
| CRUS_Intrepid | 1 | 1 | match |
| CRUS_Starlifter_A2 | 6 | 9 | base 6 ok; 3 module-bay slots not yet walked |
| CRUS_Starlifter_C2 | 6 | 6 | match |
| CRUS_Starlifter_M2 | 6 | 9 | same module-bay shortfall as A2 |
| MISC_Fortune | 1 | 1 | match |
| MISC_Starlancer_Max | 4 | 4 | match |
| ORIG_400i | 3 | 3 | match |
| RSI_Constellation_Andromeda/Aquila/Phoenix/Taurus | 5 each | 5 each | match (all 4) |
| RSI_Polaris | 27 | 13 | over-counts; 10 `_Com_Suit_Locker_Overhead` are visual-only, REF excludes them; remaining 17 vs REF 13 still off |
| RSI_Zeus_CL | 3 | 3 | match |
| RSI_Zeus_ES | 3 | 3 | match |
| MRAI_Guardian / Guardian_QI | 1 | 2 | undercount; REF additionally counts the loadout-attached `PersonalStorage_MRAI_Guardian` (already emitted via `_compute_storage`) |

**Status: 14/19 ships match REF on COUNT.** Needs:

- Item-className → display-name mapping (REF emits `Crew_Locker`,
  `Captain_Locker`, `Locker`, `Storage`, `Bunk`, etc. — these are
  derived from the placement's `<Object name="X">` attribute or from
  the item's localization in some non-obvious way).
- Capacity field per locker (item's inventory container vs REF value
  often disagree — Zeus item template = 0.39 SCU but REF reports 1.2;
  in-game UI shows 1M/1.2M ambiguous from rounding).
- Polaris `_Com_Suit_Locker_Overhead` exclusion rule (visual-only
  suit lockers REF skips).
- Module-bay walk for Starlifter A2/M2 swappable cargo modules.
- Power/Heat zero-blocks REF emits on these entries.

`nova/extractor.py::_ensure_ship_socpaks` now runs a second unp4k pass
after the main `xml` extraction so future cache rebuilds include the
ship socpaks automatically.

**Wired in (commit `6db73a0`):** `nova/socpak_parser.py::build_ship_storage_index`
walks every spaceship entity's socpak chain and tallies placements
into `cache/parsed_ship_storage.json`, exposed via
`BuildContext.ship_storage_index`. `nova/builders/ships.py::_compute_interior_storage`
emits one Storage entry per placement.

**Coverage vs REF (post-wiring, 2026-05-05):**

- 140 / 194 ships match REF on Storage list length.
- 49 ships emit storage entries REF reports as empty. **REF is
  incorrect for these.** Confirmed by in-game inspection:
  DRAK_Cutlass_Black (2 ✓), ESPR_Prowler_Utility (5 ✓), DRAK_Corsair
  (4 ✓), ANVL_Terrapin_Medic (2 ✓), ANVL_Asgard (2 ✓). Other
  REF-zero ships in the same bucket: Hammerhead (10), Idris (44 each
  variant), Carrack (6), Star_Runner (6), Perseus (7), Starlancer_TAC
  (18), Prowler (6), Cutlass family Red/Blue/Steel (2 each),
  Vanguard family (1 each), MOLE/MOTH (4 each), Spirit_A1/C1 (2),
  Caterpillar (2), Cutter family (1 each), Apollo Medivac/Triage (2),
  Hermes (2), Mantis (2), Meteor (2), Hull_A/B/C (1/2/4),
  300i/315p/325a/350r (1/1/2/1), Aurora variants (1), Herald (1),
  Defender (1), Nomad (1), SRV (1), RAFT (2), Shiv (2). Every one of
  these has `<Object type="PersonalStorage_*"/>` placements in its
  `.socpak` archives — the same data the live game loads. Our
  emission stays.
- 5 ships have non-empty REF but a different count (Polaris 13 vs 17,
  Paladin 2 vs 6, Vulture 1 vs 2, Syulen 1 vs 2, Guardian_MX 1 vs 2).
  Polaris extra 4 are `_Polaris_Medical` items REF appears to skip;
  Paladin extra 4 are socpak placements REF excludes; the three
  +1-extras are loadout-attached + socpak combinations.

**Per-ship count list with mismatches** (as of 2026-05-05):

```
ClassName                              REF    OUT    Diff
AEGS_Idris_M                             0     44    +44
AEGS_Idris_P                             0     44    +44
MISC_Starlancer_TAC                      0     18    +18
AEGS_Hammerhead                          0     10    +10
RSI_Perseus                              0      7     +7
ANVL_Carrack                             0      6     +6
CRUS_Star_Runner                         0      6     +6
ESPR_Prowler                             0      6     +6
ESPR_Prowler_Utility                     0      5     +5
ARGO_MOLE                                0      4     +4
ARGO_MOTH                                0      4     +4
DRAK_Corsair                             0      4     +4
DRAK_Cutlass_Blue                        0      4     +4
MISC_Hull_C                              0      4     +4
ANVL_Asgard                              0      2     +2
ANVL_Terrapin                            0      2     +2
ANVL_Terrapin_Medic                      0      2     +2
ARGO_RAFT                                0      2     +2
CRUS_Spirit_A1                           0      2     +2
CRUS_Spirit_C1                           0      2     +2
DRAK_Caterpillar                         0      2     +2
DRAK_Clipper                             0      2     +2
DRAK_Cutlass_Black                       0      2     +2
DRAK_Cutlass_Red                         0      2     +2
DRAK_Cutlass_Steel                       0      2     +2
GLSN_Shiv                                0      2     +2
MISC_Hull_B                              0      2     +2
ORIG_325a                                0      2     +2
RSI_Apollo_Medivac                       0      2     +2
RSI_Apollo_Triage                        0      2     +2
RSI_Hermes                               0      2     +2
RSI_Mantis                               0      2     +2
RSI_Meteor                               0      2     +2
AEGS_Vanguard                            0      1     +1
AEGS_Vanguard_Harbinger                  0      1     +1
AEGS_Vanguard_Sentinel                   0      1     +1
ARGO_SRV                                 0      1     +1
BANU_Defender                            0      1     +1
CNOU_Nomad                               0      1     +1
DRAK_Cutter                              0      1     +1
DRAK_Cutter_Rambler                      0      1     +1
DRAK_Cutter_Scout                        0      1     +1
DRAK_Herald                              0      1     +1
MISC_Hull_A                              0      1     +1
ORIG_300i                                0      1     +1
ORIG_315p                                0      1     +1
ORIG_350r                                0      1     +1
RSI_Aurora_GS_SE                         0      1     +1
RSI_Aurora_Mk2                           0      1     +1
ANVL_Paladin                             2      6     +4
RSI_Polaris                             13     17     +4
DRAK_Vulture                             1      2     +1
GAMA_Syulen                              1      2     +1
MRAI_Guardian_MX                         1      2     +1
```

**Remaining REF divergences on the 140 matched ships** (XML truth vs
REF curation):

- **Names**: REF curates per-ship display names (`Crew_Locker`,
  `Captain_Locker`, `Locker`, `Storage`, `Bunk`, `PersonalStorage_400i`).
  Placement-type `attachDef.name` resolves to `@ui_PersonalStorage` →
  "Personal Storage" for all. No structural signal maps placement →
  REF display name.
- **Capacities**: REF capacities (Zeus 1.2, Reclaimer 1.35,
  Constellation 1.05, Valkyrie 0.75) match orphan
  `personalstorage_locker_*.xml` containers not linked to those ships
  in any XML chain. Each placement's actual item has its own container
  capacity (Template = 0.39 SCU). Both interpretations are present in
  the data; REF picks a different one with no derivable rule.
- **Power/Heat**: REF emits zero-blocks on these entries. We don't.
- **Uneditable**: REF marks these `Uneditable=true`. We don't.

### Bucket A2 — Module-nested CargoGrids — RESOLVED (2026-05-05)

`_build_cargo_grid_items_from_loadout` (ships.py:656) now recurses
into the installed item's `components.defaultLoadout` to surface
CargoGrid items nested inside Module-style wrapper items — the same
chain `_compute_storage_scu` already follows for capacity totals.

**Trigger case:** base TMBL_Cyclone has cargo space behind
driver/passenger (project-owner-confirmed in-game), structured as:

```
TMBL_Cyclone (vehicle)
  └─ hardpoint_module_attach -> TMBL_Cyclone_Module_Cargo
                                 └─ hardpoint_cargo_grid -> TMBL_Cyclone_CargoGrid_Main (1 SCU)
```

The cargo grid is two levels deep, not on a separate vehicle port.
REF reports 0 cargo for Cyclone — incorrect, the same incompleteness
pattern as Bucket A. Our recursion now surfaces it.

**Cargo diffs went 78 → 49** (-29 total). Other modular ships also
benefited (CCs nested inside cargo-bay wrappers).

**Remaining 4 cargo count mismatches** (all REF=0 / OUT=1, treated
as REF undercounts):

| Ship | XML cargo | REF |
|---|---:|---:|
| TMBL_Cyclone | 1 | 0 |
| RSI_Ursa_Medivac | 1 | 0 |
| RSI_Ursa_Rover | 1 | 0 |
| GRIN_MTC | 1 | 0 |

All four are ground/light vehicles with module-nested cargo. REF's
tool doesn't walk into module items' own loadouts.

## Cargo diff breakdown (post Bucket A2 — 49 cargo diffs across 11 ships)

| Cat | Diffs | Ships | Pattern |
|---|---:|---|---|
| **CA — Power/Heat blocks on Hull_C CargoGrids** | 32 | MISC_Hull_C only (16 cargo struts × Power + Heat) | **Deep-dived 2026-05-05: REF-specific, not derivable from XML.** See investigation below. **Parked.** |
| **CB — Mining ore-pod walk** | 0 (was 5) | RESOLVED 2026-05-05 | Stored_pod port skip moved BEFORE the item-className catch in `_classify_port`. Collapsed-spare items match `shipmining_pod` in their className and were routing to CargoContainers via the wrong branch. |
| **CC — ROC capacity** | 0 (was 1) | RESOLVED 2026-05-05 | `_build_cargo_container_entry` now reads `ResourceContainer.capacity.SStandardCargoUnit` (gameplay ore-SCU) instead of `attachDef.volume` (physical fitment volume). Mole pod is 8 SCU physically but holds 12 SCU; ROC is 2.5 SCU physically but 1.2 SCU. |
| **CD — REF-only items** | 2 | ANVL_Hornet_F7C / F7C_Wildfire | **Investigated 2026-05-05: REF wrong, OUT correct.** Project owner confirmed in-game: F7C base ships with a cargo pod as standard equipment. The XML matches that — `hardpoint_class_4_center` defaultLoadout points to `ANVL_Hornet_F7C_Cargo_Mod` (Module type) which contains a CargoGrid_F7C. We emit the structural truth. REF (1) hides the actual Cargo_Mod loadout (showing the slot empty in PilotWeapons) and (2) emits a fictional `Cargo_Pod_F7C_TEMP` className that has 0 hits in Game2.xml. Wildfire variant has a real weapon at the slot but REF still emits `Cargo_Pod_F7C_TEMP` — confirming REF's CargoContainers entry is ship-level hardcoded stale data, not loadout-derived. **OUT is correct, REF is incorrect. Parked.** |
| **CE — REF undercounts (XML truth, REF wrong)** | 4 | TMBL_Cyclone, GRIN_MTC, RSI_Ursa_Medivac, RSI_Ursa_Rover | All REF=0 / OUT=1, same pattern as Storage Bucket A |
| **CF — Other CargoContainer** | 5 | GRIN_ROC_DS (1) + spillover from MOLE/Prospector pod issues | Mostly subsumed into CB |

**Power/Heat shape (CA):** identical across all 16 Hull_C struts —
```
Power: {PowerBase: 0.0, PowerDraw: 2.0, IdlePowerEmission: 0.0, ActivePowerEmission: 6.0}
Heat:  {StartComponentTemperature: 300.0, StartIRTemperature: 250.0, StartIREmission: 264.0, ThermalEnergyBase: 20.0, ThermalEnergyDraw: 40.0}
```

**Reframing (2026-05-05, project owner):** these "Power/Heat" blocks
in REF can be read as **EM signature** (Power*) and **IR signature**
(Heat*) data — the structural source we use elsewhere is
`ItemResourceComponentParams.states.signatureParams.{EMSignature,IRSignature}`
with `nominalSignature` + `decayRate`, plus `powerRanges`
{low,medium,high}. The components-derived Power/Heat model.

**CA deep-dive (2026-05-05):**

1. Compared component sets: `MISC_Hull_C_CargoGrid` and
   `RSI_Apollo_CargoGrid_Main` have **identical** polymorphicTypes
   (SAttachableComponentParams, SEntityPhysicsControllerParams,
   SEntityRigidPhysicsControllerParams, SEntityInteractableParams,
   SCItemInventoryContainerComponentParams, SMicroCargoUnit,
   CoolingEqualizationMultiplier, GlobalResourceAudio). Yet only
   Hull_C gets Power/Heat blocks in REF.
2. Searched `MISC_Hull_C_CargoGrid` and `MISC_Hull_C_FoldingStrut`
   item XMLs for the values 264, 20, 40, 2, 6: only
   `temperatureToIR=6` matches (one of REF's `StartIRTemperature` /
   ThermalEnergyDraw aren't in the data).
3. Searched all of Game2.xml for the field names REF emits
   (`PowerDraw`, `ActivePowerEmission`, `ThermalEnergyBase`,
   `ThermalEnergyDraw`, `StartIREmission`):
   - `EntityComponentHeatConnection`: **1 occurrence** total in
     Game2.xml — on `BaseBuilding_FPSCraftingBench_CargoGridEntity`
     (TempToIR=2.64 → 264, ThermalEnergyBase=10, ThermalEnergyDraw=20,
     StartCool=300). Not on any Hull_C entity.
   - `PowerConnection`: 2 occurrences total. Sparse usage.
   - `StartIREmission`, `ActivePowerEmission`: 0 occurrences.
4. Hull_C struts (16 of them) all share IDENTICAL Power/Heat blocks
   in REF. F7C cargo pod has DIFFERENT but similarly hardcoded values.

5. Following the EM/IR-signature reframing (project owner hint):
   `MISC_Hull_C_FoldingStrut` and `_Cargo_Mod` items both have
   `signatureParams enable="0"` (disabled) inside their
   `SEntityRigidPhysicsControllerParams.PhysType.temperature.signatureParams`,
   with only `minimumTemperatureForIR=250` and `temperatureToIR=6`
   populated — no `nominalSignature` / `decayRate` /
   `EMSignature` / `IRSignature` / `powerRanges`. Neither item has
   `ItemResourceComponentParams` (the structural source where
   `nominalSignature`/`decayRate` per state lives). So the
   structural signature path that we already parse for
   ResourceNetwork doesn't apply here.

The REF values are not in our XML and not computable from any field
we extract. Most likely **stale REF data** — folding struts and
cargo modules shouldn't have separate EM/IR signatures (passive
items, not active power consumers); the baseline probably carries
these values from a previous patch where the items had
ItemResourceComponentParams with signature data, since removed by
CIG. Project owner agreed 2026-05-05 that these signatures aren't
gameplay-important.

We follow XML truth and don't emit these blocks. **Parked as
REF-stale.** Revisit if a fresh source surfaces, or if CIG
re-adds signature data to these items.

**Attack order:** CA first (likely simplest structural lift), then CB + CC (mining pods need a walk-rule fix), then CD (one specific item), then CE parks as REF undercount.

### Bucket B — REF inconsistencies (suspected)

REF reports `ItemsQuantity` higher than the visible `InstalledItems` list.
Verified XML-correct count = `len(InstalledItems)`.

| Ship | REF ItemsQuantity | REF list len | Inventories in XML |
|------|------------------:|-------------:|-------------------:|
| CNOU_Mustang_Alpha/Beta/Delta/Gamma/Omega | 2 | 1 | 2 (SeatAccess + Personal Storage) |
| RSI_Scorpius / RSI_Scorpius_Antares | 3 | 1 | 3 (SeatAccess + 2× Personal Storage) |

REF's count appears to match the underlying inventory count, but its
displayed list is filtered. We emit list+count consistently, so REF
flags ItemsQuantity as a value mismatch. Not derivable from XML
without intentionally desyncing list length and count to mirror REF.

### Bucket C — Cargo-item Mass mismatch (4 diffs)

`CRUS_Starlifter_CargoGrid_Personal_Armory_Large/Small` items have
`physics.mass = 1.0`, but REF reports `Mass = 0.0`. Cabinet items with
SCItemDoorParams + Cargo type. No structural rule explains REF's `0.0`
— their mass is genuinely 1.0 in source XML. Suspected REF normalization
(zeroing physical mass for "container" gameplay items).

### Bucket D — Cargo-item Power/Heat blocks (8 diffs)

REF emits `Power`/`Heat` sub-blocks (all-zero) for Cargo storage items
emitted via `_compute_storage`. We currently omit these. Easy structural
fix: when emitting Cargo type entries, attach the same Power/Heat zero
blocks REF produces. Defer until interior-walker lands so the affected
items (Starlifter et al.) actually appear in OUT.

### Bucket E — Uneditable=true on Cargo @ui_PersonalStorage (3 diffs)

GRIN_MDC, GRIN_MTC, ANVL_Paladin: REF flags Storage entries
`Uneditable=true`; we don't emit it. The entries' impl-XML ports either
don't exist (loadout-only) or carry empty flags. No structural signal
distinguishes these from Mustang/Pisces (where REF *omits* Uneditable).
Suspected REF inconsistency.
