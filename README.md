# Nova Star Citizen Data Extractor

A Python tool that extracts ship, vehicle, equipment, and weapon data from a local Star Citizen install (`Data.p4k`) and produces JSON output in a documented downstream format (see `DATA_SOURCES.md`).

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

Output lands in `./output/<channel>/`. With no `--channel` flag, the run extracts Live and then auto-runs PTU if a sibling PTU install has a newer build; each channel is also packaged as `output/<channel>.zip`.

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
py -m nova                              # Extract Live, then PTU if newer; package each channel as <channel>.zip
py -m nova --only vehicle_equipment     # Extract one dataset
py -m nova --channel PTU                # Pin to one channel (skips PTU auto-detection)
py -m nova --no-package                 # Skip the per-channel .zip step
py -m nova --force                      # Clear cache and re-extract from Data.p4k
py -m nova --config path.json           # Use a different config file
```

Datasets (valid `--only` values): `vehicle_metadata`, `vehicle_stats`, `vehicle_hardpoints`, `vehicle_equipment`, `fps_equipment`.

## Pipeline

1. **Fetch RSI ship-matrix** — `nova/matrix.py` GETs the public `https://robertsspaceindustries.com/ship-matrix/index` once at the start and caches it to `cache/rsi_flight_ready.json`. The matrix is channel-agnostic — Live and PTU runs share the same file. Falls back to existing cache on network failure; build continues without tags if neither works.
2. **Extract** — `unp4k` unpacks `Data.p4k` into `./cache/<channel>/`.
3. **Convert DCB** — `Game2.dcb` → per-record XML files under `Libs/Foundry/Records/`; the converter assembles them into `Game2.xml` (~2.4 GB) for the streaming parser. Both legacy single-XML output and the v4.0.83+ folder layout are supported.
4. **Collect entity files + scan for CryXML binaries** — curated ship/ground entity lists plus an automatic scan of known CryXML-binary directories (see note below).
5. **Convert CryXML → text XML** — every collected binary file is run through `unforge.exe`. Idempotent: a magic-byte header check skips files that are already text.
6. **Stream-parse `Game2.xml`** — single-pass `ET.iterparse` collects items, vehicles, GUIDs, manufacturers, ammo, inventory containers, gimbal modifiers, IFCS modifier records, crafting blueprints, GPP records, procedural recoil configs/modifiers, and weapon misfire defs.
7. **Parse per-vehicle entity XML** — extracts `weaponPoolSize`, `shieldMaxItemCount`, and `inclusionMode` per ship.
8. **Parse vehicle implementation XMLs** — extracts ports, hull HP, mass, and inline `<Modifications>` blocks. `get_vehicle_impl_data` applies the entity's `VehicleComponentParams.modification` (e.g. `Zeus_CL`, `F7C_Mk2`) on top of the base impl, toggling `skipPart` and renaming variant-specific ports.
9. **Classify cosmetic ship variants** — `nova/cosmetic_classifier.py` groups ships by `vehicleDefinition` and identifies cosmetic-only siblings; emits `cache/cosmetic_variants.json`.
10. **Walk ship-interior socpaks** — `nova/socpak_parser.py` follows each ship entity's `SVehicleObjectContainerParams.fileName` references into `.socpak` archives and counts `PersonalStorage_*` placements (used by the Storage builder for crew-locker entries not reachable through the loadout port chain).
11. **Build datasets** — five builders project records into the reference output shapes via `nova/builders/slices.py`. The slice merger tags each ship with `FlightReady` (matrix flight-ready / in-game earnable) and `Thumbnail` (matrix `store_thumb_listing_small` URL) when matched.
12. **Write JSON** to `./output/<channel>/`, plus per-channel `output/<channel>.zip` unless `--no-package`.

> **Note on CryXML-binary `.xml` files:** Several directories under `cache/Data/` contain files with `.xml` extension that are actually CryXML binary (magic bytes `CryXmlB`) and must be converted via `unforge.exe` before any XML parser can read them. Current known directories (see `nova/extractor.py::CRYXML_BINARY_DIRS`):
> - `Libs/Foundry/Records/entities/spaceships/`
> - `Libs/Foundry/Records/entities/groundvehicles/`
> - `Scripts/Entities/Vehicles/Implementations/Xml/` (hull mass, structural HP, thruster HP, port definitions)
> - `Scripts/Loadouts/` (external loadout files referenced by `SItemPortLoadoutXMLParams.loadoutPath`)
>
> The extractor scans these automatically. If a new binary-XML directory is discovered, add it to `CRYXML_BINARY_DIRS`. See `DATA_SOURCES.md` → "CryXML-binary files" for details.

Fresh extraction from a 154 GB `Data.p4k` takes ~5–7 minutes. Cached reruns (after parser changes) take ~20–45 seconds.

## Project layout

```
nova/
├── __main__.py              CLI entry point + orchestration (Live + auto-PTU)
├── config.py                Config loader
├── tool_downloader.py       Fetches unp4k/unforge on first run
├── extractor.py             unp4k + entity-file extraction + CRYXML_BINARY_DIRS scan
├── converter.py             DCB → XML, CryXML → XML
├── dataforge_parser.py      Single-pass stream parse of Game2.xml
├── entity_parser.py         Per-entity XML parsing
├── vehicle_impl_parser.py   Vehicle loadout implementations
├── cosmetic_classifier.py   Ship-level cosmetic-variant detection (XML-diff over siblings)
├── socpak_parser.py         Ship-interior PersonalStorage walk via .socpak archives
├── utils.py                 Shared helpers (safe_float, parse_localization, ...)
├── matrix.py               RSI ship-matrix fetcher + matcher (FlightReady / Thumbnail tags)
└── builders/
    ├── slices.py            Projects merged ship+vehicle records into the 5 output shapes
    ├── stditem.py           The 3300-line heart: builds the stdItem block for every record
    ├── ships.py             Ship dataset builder + filter stack
    ├── vehicles.py          Ground-vehicle dataset builder
    ├── ship_equipment.py    Ship/vehicle stdItem records
    ├── fps_weapons.py       FPS weapon stdItem records
    ├── fps_attachments.py   FPS attachment stdItem records
    └── cosmetic.py          Item-level cosmetic-variant detection (gameplay-signature)
```

## Output files

Five JSON files in `output/<channel>/`, matching the documented reference shapes:

| File | Reference | Content |
|------|-----------|---------|
| `vehicle_metadata.json` | entry_0 | Catalog metadata (scalar Cargo, Type, store/PU placeholders, FlightReady, Thumbnail) |
| `vehicle_stats.json` | entry_1 | Detailed spec (object Cargo, FlightCharacteristics, FuelManagement, FlightReady, …) |
| `vehicle_hardpoints.json` | entry_2 | PortTags (from `SItemPortContainerComponentParams.PortTags`), Hull.Structure, Hardpoints with per-port `RequiredTags`, FlightReady |
| `vehicle_equipment.json` | entry_3 | Ship/vehicle equipment stdItem records (~2868 items on current Live) |
| `fps_equipment.json` | entry_4 | FPS weapons + attachments stdItem records (~496 items on current Live, includes cosmetic skin variants tagged inline) |

Plus `metadata.json` with `gameVersion` (public patch format `<patch>.<p4_changelist>` like `4.7.2.11715810` derived from the RSI launcher log; falls back to the build-manifest `Branch` when the log isn't available), `buildBranch`, `buildVersion`, `p4Change`, `buildDate`, `channel`, and per-dataset counts.

## Output format

The output format is stable across runs and documented field-by-field in
`DATA_SOURCES.md`. A few intentional design choices to be aware of:

1. **DPS rounding** — `AMRS_LaserCannon_S4`, `APAR_MassDriver_S2`, `KLWE_MassDriver_S2` each end up ±0.01 off some external sources for one DPS value. Python's `round()` uses banker's rounding; matching the other rounding mode would require IEEE 754 float-aware rounding that breaks other weapons.
2. **FPS catalogue includes cosmetic variants** — `fps_equipment.json` emits **all** player-equippable FPS items including skin variants (`apar_special_ballistic_01_black02`, etc.). Cosmetic variants are tagged inline with `CosmeticVariant: true` + `CosmeticVariantOf: <base_classname>` so consumers can hide, aggregate, or expose them as desired. See `nova/builders/cosmetic.py`.
3. **Extended equipment surface** — additional gameplay fields are surfaced on every ship/FPS item: per-firing-mode `Recoil`, `Crafting`, magazine `Capacity`, `Aim` block, `PowerModes`, `Durability.Wear`, ammunition `Projectile`/`Impulse`/`ArmorPenetration`. Additive only — existing fields preserved.

## How the `stdItem` format is built

The builders translate the game's component-based entity data into the flatter `stdItem` format. Key conventions:

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
- LifeSupport: `attachDef.size == 4` → `""`; others → `"Civilian"`.
- Otherwise `""`.

### Mass exclusions
- Type in `_TYPES_NO_MASS` (FlightController, Armor.*, ShieldController, WheeledController, Turret.PDCTurret, SelfDestruct, UtilityTurret.MannedTurret, SalvageModifier, TurretBase.MannedTurret, Door.UNDEFINED, Flair_Cockpit.Flair_Static, WeaponGun.UNDEFINED, Paints.Personal) → skip.
- Base in `_BASE_TYPES_NO_MASS` (Paints) → skip.
- Volume=1 placeholder for Turret.* / Flair_Cockpit.Flair_Static / ToolArm.UNDEFINED → skip.
- Container.Cargo mining pods (ResourceContainer-only, no inventory) / `attachDef.tags == "TMBL_Cyclone_Module"` / placeholder CargoGrid_Main → skip.
- GroundVehicleMissileLauncher with non-placeholder `displayName` (vehicle-integrated rack) → skip.
- Turret.TopTurret/BottomTurret with `"Remote"` in `attachDef.name` → skip.
- Module.UNDEFINED placeholder-volume → skip.
- Salvage heads (no `SDistortionParams` component) → skip.
- `_MISSILERACK_WITHOUT_MASS` blocklist (2 items).
- `_MASS_FORCE_INCLUDE` allowlist wins (10 items).

### Key formulas
- **CargoGrid** Width/Depth/Height = `floor(interiorDimensions.{x,y,z} / 1.25)` (SC grid slot = 1.25 m).
- **Ifcs Blade modifier** — applied from the referenced `SIFCSModifiersLegacy` record's `numbers`/`vectors` deltas (cached as `ctx.ifcs_modifiers`).
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

## Cosmetic-variant handling

Two distinct cosmetic systems run during build:

- **Ship-level** (`nova/cosmetic_classifier.py`) — XML-diffs ships sharing the same `vehicleDefinition`; cosmetic-only siblings are filtered from emit. Writes `cache/cosmetic_variants.json` for downstream tools.
- **Item-level** (`nova/builders/cosmetic.py`) — hashes a "gameplay signature" of each stdItem record (stripping cosmetic shell fields). Variants are *tagged* with `CosmeticVariant: true` + `CosmeticVariantOf: <base>` rather than dropped, so consumers can hide or aggregate them as desired.

## Caching

First run takes ~5–7 min to unpack and convert the DataForge. Cache files land per-channel in `./cache/<channel>/` plus one shared file at `./cache/`:

- `cache/rsi_flight_ready.json` — RSI ship-matrix snapshot (top-level, shared by Live + PTU; refetched at the start of every run)
- `cache/<channel>/parsed_items.json` — all entity records
- `cache/<channel>/parsed_vehicles.json` — vehicle records (includes `modification` for inline-mod resolution)
- `cache/<channel>/parsed_ammo.json` — AmmoParams by GUID
- `cache/<channel>/parsed_inventory.json` — InventoryContainer by GUID
- `cache/<channel>/parsed_manufacturers.json` — manufacturer records
- `cache/<channel>/parsed_guids.json` — GUID → className map
- `cache/<channel>/parsed_gimbal_modifiers.json` — weapon gimbal modifier records
- `cache/<channel>/parsed_ifcs_modifiers.json` — SIFCSModifiersLegacy records by GUID
- `cache/<channel>/parsed_crafting.json` — Crafting blueprints + GPP records
- `cache/<channel>/parsed_recoil.json` — procedural-recoil configs/modifiers + weapon recoil configs + misfire defs
- `cache/<channel>/cosmetic_variants.json` — ship ClassNames flagged by the cosmetic classifier
- `cache/<channel>/parsed_ship_storage.json` — per-ship interior PersonalStorage placement counts

Delete `parsed_items.json` + `parsed_vehicles.json` after changes to `dataforge_parser.py` to force re-parse. `--force` wipes the entire channel cache and re-unpacks.

## Development notes

- Both `fireActions` scope and nested `elem.iter()` matter: the parser restricts fire-action iteration to `<fireActions>` so a reference `SWeaponActionFireSingleParams` inside `<aimAction>` isn't double-counted.
- `ET.iterparse` with stream-clear is used for `Game2.xml` to stay within memory. Elements inside recognized record types (AmmoParams, EntityClassDefinition, etc.) are preserved via an `in_record` flag; anything else is cleared immediately.
- CryXML binary entity files are converted to text XML in `extractor.py` before parsing.
- The reference format uses several ref-specific conventions that aren't derivable from raw data (e.g. pitchAxis angle-limit inheritance, specific className allow/block lists). These are captured as constants at the top of `builders/stditem.py`.
- See `NAME_FILTERS.md` for the audit of remaining name-based filters and their refactor status — the project enforces structural classification per `.claude/CLAUDE.md`.
