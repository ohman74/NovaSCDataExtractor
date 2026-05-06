# Cargo SCU Algorithm

How `entry_0.Cargo` (top-level number) and `entry_1.Cargo` (per-grid breakdown)
are computed from game data.

## Core formula

A Star Citizen cargo grid is a 3D rectangular volume that holds 1.25 m × 1.25 m × 1.25 m boxes (1 SCU = 1 standard cargo unit). The total SCU capacity of a single grid is:

```
Width  = floor(interiorDimensions.x / 1.25)
Depth  = floor(interiorDimensions.y / 1.25)
Height = floor(interiorDimensions.z / 1.25)
SCU    = Width × Depth × Height
```

The per-grid `interiorDimensions` lives on the `SCItemInventoryContainerComponentParams` of the grid item, resolved via its `containerParams` GUID (mapped in `cache/parsed_inventory.json`).

The DataForge already exposes this product as the integer `capacity` field on the inventory container, so for most ships we can read `capacity` directly instead of recomputing — both are valid sources, the formula is the canonical definition.

## Multiple grids per ship

Every cargo-carrying ship has **one or more** CargoGrid items. The total ship cargo is the **sum of capacity over all grids** that belong to that ship.

```
ship.entry_0.Cargo = sum(capacity of every cargo grid attached to ship)
ship.entry_1.Cargo.CargoGrid = same sum (as float)
```

A grid is "attached to" a ship if either of:

1. It appears in the ship's `defaultLoadout` (under `<EntityComponentDefaultLoadoutParams>`), as a port whose installed item has `attachDef.type == "CargoGrid"`. The wiring is GUID-based via `entityClassReference` (preferred) or className via `entityClassName`. Example: ARGO_RAFT's `hardpoint_cargo_grid` carries `entityClassReference="90b012ac-..."` which the GUID index resolves to `ARGO_RAFT_CargoGrid_192` (192 SCU).

2. It appears in the `defaultLoadout` of a wrapper item that the ship itself references — Constellation CargoBay, Hammerhead cargo Door, etc. We recursively descend into that wrapper item's own `defaultLoadout`, which often comes from an external `SItemPortLoadoutXMLParams.loadoutPath` file under `cache/Data/Scripts/Loadouts/`.

A 262-ship audit confirmed every cargo-bearing ship resolves via 1 or 2. **No className-prefix fallback is used in the cargo path** — the previously-present by-name lookup was confirmed dead and removed. Orphan items like `ARGO_RAFT_CargoGrid_Main` (32 SCU, zero references in Game2.xml) are correctly ignored because they have no loadout attachment.

## XML data sources

The authoritative source is the unpacked Star Citizen game data under `cache/Data/`. Everything we read derives from XML files originally packed in `Data.p4k`:

1. **`cache/Data/Game2.xml`** (~2.4 GB DataForge dump) — the master record. Contains every `EntityClassDefinition` (items, ships, manufacturers, ammo, inventory containers). All `parsed_*.json` files in `cache/` are stream-parsed indexes built from this single file by `nova/dataforge_parser.py`. They are **caches for fast lookup, not independent sources** — every value is round-trippable to a Game2.xml record via the entity's `__ref` GUID.

2. **`cache/Data/Libs/Foundry/Records/entities/spaceships/<ship>.xml`** — per-ship Foundry entity (also dumped into Game2.xml). Contains `SEntityComponentDefaultLoadoutParams.loadout` with port → item wiring.

3. **`cache/Data/Scripts/Loadouts/Objects/Doors/<...>.xml`** — external loadout files referenced via `SItemPortLoadoutXMLParams.loadoutPath` from CargoBay-style items. These are CryXML-binary, converted to text in the extraction step. Their entries use `<Item portName="X" itemName="Y">`.

4. **`cache/Data/Scripts/Entities/Vehicles/Implementations/Xml/<ship>.xml`** — vehicle implementation (port-tree, hull HP, modifications). Cargo grids attach via item-port hierarchy here when the loadout doesn't list them explicitly.

The walk needs all of (1)–(4) for full coverage. The cached JSONs (`parsed_items.json`, `parsed_inventory.json`) are just GUID-indexed views over (1) — never the authority.

## Identifier-resolution order

When following references between records we prefer the strongest identifier first:

1. **GUID (`__ref` / `entityClassReference` / `containerParams`)** — globally unique, stable across patches. Always preferred.
2. **`className`** (e.g. `entityClassName`, `itemName`) — unique within an entity-type, stable but renameable.
3. **String name patterns / className prefixes** — last resort; heuristic and brittle. Every use is technical debt and should be tracked.

### Name-matching in the cargo path

**None remaining.** Every match in the cargo computation goes through GUID or className (both authoritative source-fields in the XML). The two heuristics that previously existed have been removed after audits showed they were unused:

| Removed heuristic | Audit | Replacement |
|------|-------|-------------|
| Port-name substring (`"cargogrid"`/`"cargo"` in port name) used to classify an entry as CargoGrid | 0/262 ships needed the fallback | Type-based: `attachDef.type == "CargoGrid"` only |
| By-name prefix lookup `<ShipClass>_CargoGrid_<single-word>` to find free-standing grids | 0/262 ships needed it after the wrapper-item descent (CargoBay/Door pattern) was added | Routes 1+2 above cover everything; orphan items ignored automatically |

## Module-defined grids (modular ships)

Modular ships (Retaliator, Caterpillar, etc.) have multiple loadout configurations swappable at the hangar. REF reports the **default-config** cargo:

- Retaliator default = `Module_Front_Base` + `Module_Rear_Base` = 0 SCU (no cargo bays installed)
- Cargo-module config = `Module_Front_Cargo` + `Module_Rear_Cargo` = full cargo (when player swaps modules at hangar)

The default loadout's installed module determines what cargo is available. Free-standing `<class>_CargoGrid_*` items often belong to swappable cargo modules that aren't installed by default — counting them by prefix would over-report.

**Detection rule**: if any item in the ship's loadout walk has `attachDef.type == "Module"`, the ship is treated as modular and the **by-name fallback is skipped**. Cargo SCU then comes only from grids actually attached via the default loadout's module entries.

## Family-shared grids (Constellation)

The Constellation family illustrates a case the by-name fallback does **not** cover today:

- `RSI_Constellation_CargoGrid_Main` (96 SCU) is shared between Andromeda, Aquila and (partially) Phoenix.
- Andromeda/Aquila have **no** ship-specific grid item — the by-name prefix `RSI_Constellation_Andromeda_CargoGrid` finds nothing, so we report 0.
- Phoenix has its own `RSI_Constellation_Phoenix_CargoGrid_Main` (80 SCU), but REF reports 96 (base + Phoenix-specific).

To handle this generally we'd need a "family prefix" rule: if no per-class grid is found, fall back to the family root (`RSI_Constellation` for any ship whose className starts with `RSI_Constellation_*`). Not currently implemented because identifying the family root reliably needs additional metadata.

## Storage vs CargoGrid

`entry_1.Cargo` separates `CargoGrid` (the user-fillable bay) from `Storage` (fixed crew/personal lockers, weapon racks). The walk classifies a port as cargo-grid if any of:

- The port name contains `cargogrid`, `cargo_grid` or `cargo`.
- The installed item's `attachDef.type == "CargoGrid"`.

Otherwise the inventory capacity flows into `Storage`. This split matters for the per-slice JSON structure but not for the `entry_0.Cargo` summary, which only uses `CargoGrid`.

## Where the algorithm lives

| Step | Function | File |
|------|----------|------|
| Per-grid SCU + dimensions | `_cargo_grid_entry_from_item` | `nova/builders/ships.py:584` |
| Loadout walk (entry_1 grid listing) | `_build_cargo_grid_items_from_loadout` | `nova/builders/ships.py:653` |
| Total SCU computation | `_build_cargo` | `nova/builders/ships.py:886` |
| External loadout file resolution | `_resolve_external_loadouts` | `nova/dataforge_parser.py` |
| `entry_0.Cargo` int projection | `to_metadata` | `nova/builders/slices.py:75` |

## Status

After GUID-priority loadout resolution, external loadout file resolution
(SItemPortLoadoutXMLParams), CargoBay-descent, modular-ship detection,
and type-based classification, our cargo grid output matches the
patch-current ShipValues reference for **193/193** comparable ships.

The only difference originally seen against the third-party spreadsheet
(Tumbril Cyclone, 1 SCU vs 0) was confirmed by the user to be correct on
our side — XML defines a 1.25×1.25×1.25 m grid (= 1 SCU) which the
spreadsheet had rounded down. XML is source of truth.

## Previously-known gaps (all resolved)

| Gap | Affected ships | Resolution |
|-----|---------------|------------|
| Loadout walk silent on free-standing grids | Hammerhead | By-name fallback when loadout walk returns 0 cargo SCU |
| Modular ship overcounting | Retaliator | Detected via any loadout item having `attachDef.type == "Module"`; by-name fallback skipped |
| External loadout file references | Constellation Andromeda/Aquila/Phoenix/Taurus | `SItemPortLoadoutXMLParams.loadoutPath` resolved post-parse from `cache/Data/Scripts/Loadouts/` |
| Orphan items double-counted | RAFT (`_CargoGrid_Main`), Starlancer Max | By-name fallback gated to "only when loadout walk found nothing" |
| Personal locker classified as cargo grid | Starlifter A2/M2 | Type-based classification — `attachDef.type == "CargoGrid"` only; substring port-name match removed |
