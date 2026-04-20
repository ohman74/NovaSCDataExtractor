# Nova Star Citizen Data Extractor

A Python tool that extracts ship, vehicle, equipment, and weapon data from a local Star Citizen install (`Data.p4k`) and produces JSON output matching the SPViewer / NovaTools reference format.

**Current match rate: 99.9%** (2884/2888 items for `ship_equipment`).

**For the full field-by-field data-source map** (XML path → parser → builder), see [`DATA_SOURCES.md`](./DATA_SOURCES.md).

## Quick start

```bat
run.bat
```

Or manually:

```bat
py -m pip install -r requirements.txt
py -m nova
```

Output lands in `./output/`.

## Configuration

Edit `nova_config.json`:

```json
{
  "sc_live_path": "D:/Games/Roberts Space Industries/StarCitizen/Live",
  "tools_dir": "./tools",
  "cache_dir": "./cache",
  "output_dir": "./output"
}
```

## CLI flags

```
py -m nova                          # Extract everything
py -m nova --only ship_equipment    # Extract one dataset
py -m nova --channel PTU            # Use a different channel
py -m nova --force                  # Clear cache and re-extract from Data.p4k
py -m nova --config path.json       # Use a different config file
```

Datasets: `ships`, `vehicles`, `ship_equipment`, `vehicle_equipment`, `fps_weapons`, `fps_attachments`.

## Pipeline

1. **Extract** — `unp4k` unpacks `Data.p4k` into `./cache/`.
2. **Convert DCB** — `Game2.dcb` → `Game2.xml` (~2.4 GB of readable XML).
3. **Collect entity files + scan for CryXML binaries** — curated ship/ground entity lists plus an automatic scan of known CryXML-binary directories (see note below).
4. **Convert CryXML → text XML** — every collected binary file is run through `unforge.exe`. Idempotent: a magic-byte header check skips files that are already text.
5. **Stream-parse `Game2.xml`** — single-pass `ET.iterparse` collects items, vehicles, GUIDs, manufacturers, ammo, inventory containers, gimbal modifiers.
6. **Build datasets** — per-category builders map parsed records to SPViewer `stdItem` format.
7. **Write JSON** to `./output/`.

> **Note on CryXML-binary `.xml` files:** Several directories under `cache/Data/` contain files with `.xml` extension that are actually CryXML binary (magic bytes `CryXmlB`) and must be converted via `unforge.exe` before any XML parser can read them. Current known directories:
> - `Libs/Foundry/Records/entities/spaceships/`
> - `Libs/Foundry/Records/entities/ground/`
> - `Scripts/Entities/Vehicles/Implementations/Xml/` (hull mass, structural HP, thruster HP, port definitions)
>
> The extractor (`nova/extractor.py::CRYXML_BINARY_DIRS`) scans these automatically. If a new binary-XML directory is discovered, add it to that list. See `DATA_SOURCES.md` → "CryXML-binary files" for details.

Fresh extraction from a 154 GB `Data.p4k` takes ~5–7 minutes. Cached reruns (after parser changes) take ~20–45 seconds.

## Project layout

```
nova/
├── __main__.py              CLI entry point, orchestration
├── config.py                Config loader
├── tool_downloader.py       Fetches unp4k/unforge on first run
├── extractor.py             unp4k + entity-file extraction
├── converter.py             DCB → XML, CryXML → XML
├── dataforge_parser.py      Stream parse of Game2.xml
├── entity_parser.py         Per-entity XML parsing
├── vehicle_impl_parser.py   Vehicle loadout implementations
├── utils.py                 Shared helpers (safe_float, parse_localization, ...)
└── builders/
    ├── stditem.py           The 2000-line heart: builds the stdItem block for every record
    ├── ships.py             Ship dataset builder
    ├── vehicles.py          Vehicle dataset builder
    ├── ship_equipment.py    Ship equipment dataset builder
    ├── vehicle_equipment.py Vehicle equipment dataset builder
    ├── fps_weapons.py       FPS weapon builder
    └── fps_attachments.py   FPS attachment builder
```

## Reference-format compatibility (`ship_equipment.json`)

Every field of every item is compared against the SPViewer reference at `temp/reference_data_new/entry_3.json`. **2884 of 2888 items match exactly**, modulo leading/trailing whitespace.

Per-field match rates (100% except where noted):

| Field | Match | Notes |
|-------|-------|-------|
| ClassName, Size, Grade, Type, Classification, Name, Volume, Manufacturer, Tags, RequiredTags, Class, Description | 100% | — |
| Durability, HeatController, ResourceNetwork, Mass, Armour, CounterMeasure, MissileRack, ShieldEmitter, Shield, Missile, Radar, QuantumDrive, Module, MiningLaser, TractorBeam, JumpDrive, Emp, SelfDestruct, SalvageModifier, QuantumInterdiction, Bomb, MissilesController, Ifcs, Turret | 100% | — |
| CargoContainers, CargoGrid | 100% | — |
| **Ports** | **831/832** (99.9%) | 1 nested `ControlPanel` loadout resolves to a different class than ref. |
| **Weapon** | **373/376** (99.2%) | 3 items differ by 0.01 DPS due to Python's round-half-to-even on boundary values (819.725, 149.625). |

### Remaining gaps (known edge cases)

1. **DPS rounding** — `AMRS_LaserCannon_S4`, `APAR_MassDriver_S2`, `KLWE_MassDriver_S2` each differ by ±0.01 on one DPS value. Python's `round()` uses banker's rounding; matching the reference would require IEEE 754 float-aware rounding that breaks other weapons.
2. **Nested Loadout GUID** — `AEGS_Retaliator_Module_Rear_Cargo` has one deeply nested `ControlPanel` port whose `Loadout` GUID resolves to `RearCargo_Lift_exterior` for us vs `FrontCargo_Lift_Exterior` in ref (likely a data-version difference).

## How the `stdItem` format is built

The builders translate the game's component-based entity data into SPViewer's flatter format. Key conventions:

### Class presence
1. **`_TYPES_NEVER_CLASS`** (ShieldController, WheeledController, ToolArm, Armor.Light/Heavy, WeaponGun.UNDEFINED, Turret.NoseMounted, Paints.Personal, MiningModifier.UNDEFINED, SalvageFieldEmitter.UNDEFINED, Missile.UNDEFINED/Rocket, Flair_Cockpit.Flair_Hanging) → never.
2. **`name == "@LOC_PLACEHOLDER"`** + type in `_TYPES_PLACEHOLDER_FORCE_CLASS` (WeaponGun.Gun, Radar.MidRangeRadar, Scanner.Scanner, AmmoBox.Magazine) → Class = `"@LOC_PLACEHOLDER"`.
3. **Armor.Medium** → only items in `_ARMOR_MEDIUM_WITH_CLASS` allowlist (18 specific ship variants).
4. **Specific blocklists**: `_MISSILERACK_WITHOUT_CLASS`, `_PAINTS_WITHOUT_CLASS`, `_TURRETS_WITHOUT_CLASS`, `_CLASS_OMIT_CLASSNAMES` → never.
5. **WeaponDefensive.CountermeasureLauncher** uses inverted rule (empty desc → Class), except the `_WEAPONDEFENSIVE_MFR_WITH_CLASS` allowlist (ANVL/CNOU/XNAA/MIS) always includes, and `_WEAPONDEFENSIVE_CN_WITHOUT_CLASS` always excludes.
6. **Default** — include Class iff description is non-empty (not `@LOC_EMPTY`/`@LOC_PLACEHOLDER`/empty).

### Class values
- `_CLASS_VALUE_OVERRIDES` dict wins first (ship-integrated components like `COOL_AEGS_S04_Reclaimer` → `Industrial`).
- `name == "@LOC_PLACEHOLDER"` → Class = `"@LOC_PLACEHOLDER"`.
- For component types (Shield/Cooler/PowerPlant/QuantumDrive/Radar/LifeSupportGenerator/JumpDrive/QuantumInterdictionGenerator) with a manufacturer → `MANUFACTURER_CLASS[code]`.
- LifeSupport: `LFSP_S04_*` → `""`; others → `"Civilian"`.
- Otherwise `""`.

### Mass exclusions
- Type in `_TYPES_NO_MASS` (FlightController, Armor.*, ShieldController, WheeledController, Turret.PDCTurret, SelfDestruct, UtilityTurret.MannedTurret, SalvageModifier, TurretBase.MannedTurret, Door.UNDEFINED, Flair_Cockpit.Flair_Static, WeaponGun.UNDEFINED, Paints.Personal) → skip.
- Base in `_BASE_TYPES_NO_MASS` (Paints) → skip.
- Volume=1 placeholder for Turret.* / Flair_Cockpit.Flair_Static / ToolArm.UNDEFINED → skip.
- Container.Cargo mining pods / TMBL_Cyclone_Module_* / *_CargoGrid_Main → skip.
- GroundVehicleMissileLauncher non-Storm → skip.
- Turret.TopTurret/BottomTurret remote variants → skip.
- Module.UNDEFINED placeholder-volume → skip.
- `Salvage_Head_*` → skip.
- `_MISSILERACK_WITHOUT_MASS` blocklist (2 items).
- `_MASS_FORCE_INCLUDE` allowlist wins (10 items).

### Key formulas
- **CargoGrid** Width/Depth/Height = `floor(interiorDimensions.{x,y,z} / 1.25)` (SC grid slot = 1.25 m).
- **Ifcs Blade HND** modifier: `MaxSpeed-25, SCM-8, Boost±10, Pitch+1, Yaw+1, Roll+2`. Blade SPD is the inverse.
- **AfterBurner.Capacitor.RegenerationTime** = `round(Size / RegenPerSec, 1)`.
- **Radar GroundSensitivity** = `max(0, IR_sensitivity + ground_add)` applied uniformly to all signals.
- **Radar signal index map**: `0=EM, 1=IR, 2=CS, 3=DB, 4=RS, 5=ID, 6=Scan1, 7=Scan2`.
- **Missile.MaxDistance** = `round(linearSpeed × maxLifetime)`.
- **QuantumDrive.FuelRate** = `raw_quantumFuelRequirement / 1e6`.
- **JumpDrive.TuningDecayRate** = `alignmentDecayRate` (ref convention; raw `tuningDecayRate` differs).
- **Turret pitchAxis** inherits `LowestAngle`/`HighestAngle` from `yawAxis` (speed/decay from pitch's own data).
- **Sequence weapon RPM**: `effective = total_shots × 60 / sum(entry_times)`. Cap by inner fireRate when all entries share the same RPM rate.
- **Weapon DPS** = `(impact + detonation) × pellets × chargeDmgMult × RPM / 60`.
- **VehicleMod mining buffs** (type `UNDEFINED.Gun`): 4-entry zero-filled `RegenBuffModifier` + `SalvageBuffModifier`.

## Comparing against the reference

`compare.py` is the regression harness used during development:

```bat
py compare.py                       REM summary of per-field match rates
py compare.py --field Weapon        REM show mismatching items for one field
py compare.py ITEM_CLASS_NAME       REM deep diff on a single item
py compare.py --missing             REM list all items with any mismatch
```

String comparisons are whitespace-insensitive (leading/trailing only) via the `eq()` helper.

Reference files live in `temp/reference_data_new/`:

| File | Content |
|------|---------|
| `entry_0.json` | Ship metadata (store, progress tracker, PU info) |
| `entry_1.json` | Ship stats (201 ships: FuelManagement, FlightCharacteristics, Armor, ...) |
| `entry_2.json` | Ship hardpoints (201 ships: port tree with Types, Hull.Structure) |
| `entry_3.json` | **Ship equipment stdItem (2888 items)** — primary match target |
| `entry_4.json` | FPS equipment stdItem (174 items) |

## Caching

First run takes ~5–7 min to unpack and convert the DataForge. Parser cache files land in `./cache/`:

- `parsed_items.json` — all entity records
- `parsed_vehicles.json` — vehicle records
- `parsed_ammo.json` — AmmoParams by GUID
- `parsed_inventory.json` — InventoryContainer by GUID
- `parsed_manufacturers.json` — manufacturer records
- `parsed_guids.json` — GUID → className map
- `parsed_gimbal_modifiers.json` — weapon gimbal modifier records

Delete `parsed_items.json` + `parsed_ammo.json` after changes to `dataforge_parser.py` to force re-parse. `--force` wipes the entire cache and re-unpacks.

## Development notes

- Both `fireActions` scope and nested `elem.iter()` matter: the parser restricts fire-action iteration to `<fireActions>` so a reference `SWeaponActionFireSingleParams` inside `<aimAction>` isn't double-counted.
- `ET.iterparse` with stream-clear is used for `Game2.xml` to stay within memory. Elements inside recognized record types (AmmoParams, EntityClassDefinition, etc.) are preserved via an `in_record` flag; anything else is cleared immediately.
- CryXML binary entity files are converted to text XML in `extractor.py` before parsing.
- The reference format uses several ref-specific conventions that aren't derivable from raw data (e.g. pitchAxis angle-limit inheritance, Blade modifier deltas, specific className allow/block lists). These are captured as constants at the top of `builders/stditem.py`.
