# Name-based filter backlog

Audit of every place the code classifies or excludes an entity by matching
on `ClassName`, `Name`, `DisplayName`, or file path rather than on
structural fields (`Type`, `SubType`, `Tags`, `Components[*]`,
`itemPortTags`, `vehicleDefinition`, etc.).

Per `.claude/CLAUDE.md`, name-based matching is only acceptable as a last
resort, in a clearly-commented block, after verifying no structural field
distinguishes the cases. It is **never acceptable** for availability /
flight-readiness.

Investigated last-resort retentions (where a structural attempt was made
and rejected) carry their rationale in-line in the source — they are not
listed here. This file tracks only **outstanding** items where a
structural replacement is plausible but hasn't been attempted yet.

## Risk tiers

- **CRITICAL** — violates the "never acceptable" rule (availability /
  flight-readiness / is-this-a-player-entity) or silently drops records.
- **HIGH** — routine classification where structural fields almost
  certainly exist but haven't been investigated.
- **MEDIUM** — contextual overrides where a structural signal may exist
  but the data must be checked before refactoring.
- **LOW** — curated per-item allowlists keyed by `ClassName`. Acceptable
  as last-resort exceptions but should shrink as upstream rules are
  discovered.

---

## HIGH — open

### Pool-size lookups
Files: `nova/builders/stditem.py:1395-1397`, `:3568`, `:3786`
```python
ctx.weapon_pool_sizes.get(class_name.lower(), 0)
```
The maps (`weapon_pool_sizes`, `shield_pool_sizes`) are keyed by
lowercased class name. Name-based by construction. Candidate: store the
pool map keyed by a GUID or structural reference from the source XML if
one exists.

### Vehicle-impl segment-stripping
File: `nova/vehicle_impl_parser.py:496`
```python
base = class_name.split("_")
for i in range(len(base), 1, -1):
    candidate = "_".join(base[:i])
```
Fallback to find a vehicle-impl XML by progressively stripping
className segments. Candidate: look up by `vehicle.vehicleDefinition`
path (already a structural reference into the XML) rather than by
class-name shape.

---

## MEDIUM — open

### FPS energy/ballistic class split
File: `nova/builders/stditem.py:274, 285` (`_FPS_CLASS_EMPTY`,
`_FPS_CLASS_BY_CLASSNAME`)

Classification of FPS weapons as Energy / Ballistic / Laser / etc. is
currently ClassName-based. CIG encodes this as an editorial label; the
weapon component's `fireType` (rapid / sequence / charged / burst) cuts
across both classes, and the ammo record damage-type isn't populated for
personal weapons in the current parse. Candidate: extend the ammo parse
to capture damage-type on personal weapons and replace the
className-keyed dicts.

Melee classification is already structural
(`full_type == "WeaponPersonal.Knife"`).

---

## LOW — curated per-item allowlists

Explicit `ClassName` exception sets used to align certain edge-case
items with the documented output shape. Audited and kept; each is a
candidate for collapsing into a structural rule once the upstream
signal is identified.

| File | Set | Purpose |
|---|---|---|
| `stditem.py` | `_WEAPONDEFENSIVE_CN_WITHOUT_CLASS` | Reliant/Guardian CM exceptions |
| `stditem.py` | `_CLASS_VALUE_OVERRIDES` | Hand-picked Class values |
| `stditem.py` | `_TOOLARM_WITH_TURRET` | Salvage arms that expose Turret |
| `stditem.py` | `_CLASS_OMIT_CLASSNAMES` | Items where Class must be dropped |
| `stditem.py` | `_TURRETS_WITHOUT_CLASS` | Integrated/fixed turret mounts |
| `stditem.py` | `_PAINTS_WITHOUT_CLASS` | Ship-variant paint exceptions |
| `stditem.py` | `_MISSILERACK_WITHOUT_MASS` | Aurora/BEHR S02 mass exceptions |
| `stditem.py` | `_MASS_FORCE_INCLUDE` | Override skip-mass rule |
| `stditem.py` | `_MISSILERACK_WITHOUT_CLASS` | Ship-integrated missile racks |
| `stditem.py` | `_ARMOR_MEDIUM_WITH_CLASS` | Armor.Medium Class allowlist |
| `stditem.py` (FPS) | `_FPS_CLASS_OMIT`, `_FPS_CLASS_BY_CLASSNAME`, `_FPS_CLASS_EMPTY` | FPS class exceptions |

When refactoring one of these, follow the CLAUDE.md rule: open one
member, inventory the structural fields, find the one that actually
distinguishes the set from non-members, and verify against a few
known-good / known-bad cases before removing the allowlist.

---

## Notes on false positives

The following hits look name-based but are **not**; leave them alone:

- `description.startswith("@")`, `raw_name.startswith("@")`,
  `desc.startswith("@")` — localization-key detection; `@` is the
  structural prefix for unresolved keys.
- `flags_str.lower()` / `"uneditable" in flags_lower` — parsing a
  structural `flags` string from the port definition.
- `movementClass.lower() in {"arcadewheeled", "wheeled", "tracked"}` —
  `movementClass` is a structural field; the lowercase comparison just
  normalizes its value.
- `fire_type.startswith("burst")` — `fireType` is a structural enum on
  the firing-mode component.
- `"fpsWeapon" in components` — component-key membership, the structural
  signal CLAUDE.md recommends.
- `item_type.startswith("EMP" / "ToolArm")`,
  `"MannedTurret" in item_type`, `item_type.startswith("Turret.Utility")`
  — `item_type` is the structural `Type` field, not `ClassName`.

---

## Audit harness

The ship-matrix snapshot is fetched at the start of every run by
`nova/matrix.py` and cached at `cache/rsi_flight_ready.json`. The slice
builder tags each emitted ship with `FlightReady: true/false` based on
`match_ships(...)`, so a quick filter-regression check is just:

```python
import json
matrix = {e["name"]: e for e in json.load(open("cache/rsi_flight_ready.json"))}
meta   = json.load(open("output/Live/vehicle_metadata.json"))
flight_ready_in_meta  = {s["ClassName"] for s in meta if s.get("FlightReady")}
flight_ready_in_matrix = {e for e in matrix if matrix[e].get("production_status") == "flight-ready"}
```

Compare the two sets to surface missing tags or unexpected emissions.
