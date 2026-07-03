# Code review 2026-07 — refactor / perf / tech-debt / untapped data

Five-agent review of the full codebase (~17k lines) plus the cached XML corpus
(cache/LIVE, 6.5 GB). Findings verified against file:line at review time.
Ordered by priority within each section.

## A. Likely correctness bugs (fix first, diff output after each)

1. **GUID-form loadouts not resolved in three ships.py helpers** —
   `_build_base_loadout_summary` (ships.py:1481), `_compute_hardpoint_dps`
   (:1525), `_compute_missile_damage` (:1557) call `ctx.get_item(loadout)`
   directly; GUID-referenced items silently contribute 0 to TotalShieldHP /
   PilotBurstDPS / TotalMissilesDmg. `_enrich_radar_detection` (:3805) already
   does it right (`_GUID_RE` + `ctx.resolve_guid`). Fix: shared
   `_resolve_loadout_token(ctx, s)`. Small/low.

2. **`_build_hull_stats` resolves by `entityClassName` only** (ships.py:1085) —
   the one loadout walk not using `_resolve_entry`; GUID-only entries skipped →
   Hull HP undercount. Small/low-med.

3. **`in_record` never reset for two record types in dataforge_parser** —
   `SReputationStandingParams` (:549) and `MissionType` (:726) are in the
   start-set but their end handlers don't reset `in_record`, so iterparse
   element clearing stops after the first such record (memory bloat on the
   2.4 GB Game2.xml). Fix centrally: reset at top of end-branch for all
   record types. Small/low.

4. **Two divergent pilot-ctrl-tag sets** — local `PILOT_CTRL_TAGS`
   (ships.py:1715) vs module `_PILOT_CTRL_TAGS` (:3045); one has
   `mainweaponscontrol`, the other `weapon_controller_pilot`. Unify or
   document the delta. Small/med (diff vs REF).

5. **Four contradictory thruster classifiers** — `_build_hull_stats` inline
   (ships.py:1102) trusts `thrusterType` first, directly contradicting the
   audit note at :1127-1133 ("thrusterType unreliable, verified 2026-05-05");
   `_classify_thruster_role` (:1134), `_classify_port` main (:2160) and
   fallback (:2427) all differ. Make `_classify_thruster_role` the single
   classifier (add onlyActiveInVTOL signal). Medium/med.

6. **Grenade explosion walk: key-casing mismatch** — stditem.py:404 reads
   `explosionParams`, stditem.py:1104 reads `ExplosionParams` and only handles
   timer triggers; one path may silently never match → grenades with Class but
   no Explosive block. Extract one `_walk_grenade_explosion`. Small/med
   (verify against grenade corpus, currently 2 items).

7. **Port defaultLoadout misattribution risk** — dataforge_parser.py:2672 uses
   `elem.iter()` over the whole SItemPortDef subtree and takes the first
   loadout entry; a nested sub-port's item can be attributed to the parent
   port. Scope the search to the port's own loadout container. Small/low-med.

8. **Cosmetic classifier port-name collisions** — cosmetic_classifier.py:208
   flattens all loadout entries by bare port name (first wins); identically
   named ports under different turrets can hide a functional swap → wrong
   cosmetic-twin verdict. Key by hierarchical path. Medium/med.

9. **`vehicle_impl_parser.py:66` swallows ALL exceptions** as `failed += 1`
   with no logging — real bugs become silently missing vehicles. Narrow to
   `ET.ParseError`/`OSError`, log the rest. Small/low.

10. **Stale-cache hazard** — dataforge_parser.py:167 trusts parsed_*.json on
    existence only; no mtime check vs Game2.xml. One getmtime comparison
    removes the "forgot to delete cache" failure class. Small/low.

## B. Performance

Hot-path (~4-min code-only rebuild):

1. **iterparse dispatch** (dataforge_parser.py:255-857) — per-event ~25-branch
   elif chain + linear tuple scan over ~100M events. Fix: frozenset for the
   start check, early-continue for non-record end events, dict dispatch,
   depth tracking. Est. 15-30 % off streaming parse. Small-medium/low.

2. **cosmetic_classifier re-parses the same entity XML O(group²) times**
   (:199-242, :544-568) — 4 ET.parse per pair + re-parse in
   `_armor_classname_for_ship`. Memoize per path (files immutable within a
   run). Tens of seconds. Small/low.

3. **~15 redundant full-loadout walks per ship** in ships.py (14 local `_walk`
   defs, 20 `_resolve_entry` sites). Fix: shared `iter_loadout()` generator +
   per-ship resolution memo. Medium/low — biggest combined perf+readability
   win in ships.py.

4. **Ground vehicles run `_build_ship` twice** (vehicles.py:37 + ships.py:245,
   merged in slices.py:145). Cache per className; preserve merge semantics
   exactly (Type from ships, MovementClass/IsGravlev from vehicles).
   Medium/med.

5. **`_build_cargo_grid_items_by_name` scans all ctx.items per ship**
   (ships.py:657). Precompute prefix map once on ctx. Small/low.

6. **Entity XML consumed ~5-10× per run** (cross-cutting): parse_entity_file,
   full text re-read for regex pool scan (__main__.py:599-629), 4× per
   cosmetic pair, socpak double-parse (socpak_parser.py:89 + :35). Shared
   `{path: parsed_root}` cache; move the regex extraction into entity_parser
   (single read). Medium/low.

7. **Four builders rebuild `{guid.lower(): className}`** (blueprints.py:124,
   missions.py:74, resources.py:172, cosmetic_classifier.py:187). One cached
   `ctx.items_by_guid`. Small/low.

Fresh-extract path (~25 min):

8. **`_assemble_game2_xml` parses every record file twice** (converter.py:107)
   — validation fromstring + real parse. Lazy/heuristic validation, or skip
   assembly and feed records straight to handlers (large). Minutes.

9. **`extract_files` os.walks the whole cache tree just to print a count**
   (extractor.py:55); return value unused by all callers. Delete. ~10-30 s ×
   up to 3 passes.

10. Minor: metadata counts re-read every output JSON (__main__.py:788);
    compact JSON separators for parsed_*.json (5-8 % smaller); per-call
    imports in hot paths (ships.py:298, :4293).

## C. Refactoring / simplification

1. **24-element positional tuple** from `stream_parse_dataforge`, mirrored in
   3 hand-maintained lists + the unpack in __main__.py:570. → dict/dataclass
   keyed like the cache files. Medium/med (mechanical, wide).

2. **BuildContext**: ~30-param `__init__` + ad-hoc bolt-ons (`ctx.matrix`,
   `ctx.cache_dir`, `ctx._merged_vehicles`). → dataclass with all fields
   declared. Medium/low.

3. **~170 lines duplicated ammo-block logic** — stditem.py:1927-2013 (ship)
   vs :2168-2266 (FPS); already drifting (DamageDrop, float vs safe_float).
   → `_build_ammunition_block(ammo, capacity, *, is_fps)`. Medium/low-med
   (key order matters vs REF).

4. **DPS computed three ways** — stditem.py:2015, :2273, :2735 with different
   key sets/rounding/skip-lists. → one `_compute_firing_dps(..., is_fps)`;
   verify REF match rate. Medium/med.

5. **`_classify_port` ~770 lines** (ships.py:1673) — extract decorative-cap,
   turret-routing (primary/secondary tables at :2119/:2375 are
   near-duplicates), item-type tier. Large/med — byte-diff output.

6. **`_build_hardpoints` ~580 lines** — extract `_compute_control_claims`
   (:2510-2630) as NamedTuple; share with `_enrich_remote_controllers`.
   Medium/low.

7. **`_build_weapon_data` ~490 lines** (stditem.py:1582) — extract
   sequence-RPM, charged-RPM, per-mode body shared with
   `_build_single_firing_mode` (Beam/Spread/AimModifier blocks duplicated).
   Medium-large/med.

8. **Shared builder boilerplate** — identical `_loc()` in 4 builders (+2
   near-clones) → `ctx.loc()`; identical 13-field entry dict + tag/sort/print
   epilogue in fps_weapons/fps_attachments/ship_equipment →
   `make_catalog_entry` helper. Small/low.

9. **Duplicated code registry (mechanical dedup)**: placeholder-name fallback
   ×6 (ships.py:3430 etc.), Flags normalization ×5, ResourceContainer→SCU ×5,
   modifier-chain lookup ×2, damage-dict capitalize idiom ×4 (stditem),
   NULL_GUID literal ×13 across 3 files, cargo 1.25 constant ×10
   (stditem.py:3402ff), `ordered` re-key block (stditem.py:959) → key-order
   tuple. All small/low.

10. **Dead code**: entity_parser.py:26-114 (extract_ports & friends, ~90
    lines); ship_equipment.py:242-249 (unreachable filter); stditem.py empty
    hook-tables (:77,:232,:254,:257) + shadowed `_TYPES_NO_MASS_IF_V1`
    (:233) + unused `import re`; `_parse_simple_dict`, `_sum_mass_recursive`;
    `uses_vehicles` in BUILDERS registry; `config.get_game_version`;
    matrix.py `MFR_ALIASES={}`; tool_downloader unforge asset; duplicate
    spline-jump block (dataforge_parser.py:2390, + `State2AccelerationRate`
    typo); always-true guard ships.py:399; `mfr_code` param unused in
    `_fps_class_value`.

11. **Misc structure**: mission-result names duplicated (__main__.py:396 vs
    missions.py:18); `_build_reward_sources_index` is domain logic living in
    __main__; vehicle_impl dunder-sentinel keys (`__variant_overrides__` etc.)
    → return object; Config path poking (`config._config_path`); duplicated
    `_elem_to_dict` (dataforge_parser:2845 vs entity_parser:117); ship-filter
    chain triplicated (ships.py:148/:245/vehicles.py:22) with undocumented
    deltas; Swedish/English comment mix; scattered inline imports.

## D. Name-heuristic debt (GUID > className > name)

Structural replacement identified — do these:

- stditem.py:627 `prefix == "lbco"` → use the already-passed-but-unused
  `mfr_code == "LBCO"` (finding sat in the signature). Small/low.
- stditem.py:449/:2148 portName contains "magazine"/"ammo" → discriminate by
  installed item type (WeaponAttachment.Magazine / AmmoBox). Small-med.
- ships.py:3014 `"module" in portName` → port `types` already in port_defs.
- ships.py:4383 tractor via substring → `_classify_port` already derives it
  structurally; pass verdict through.
- ships.py:1443 `_count_crew` seat substrings → Seat port types +
  controllableTags (same data the claims precompute parses).
- ships.py:3697 Engineering_Buff `Engineering_Buff_Modifier_{cn}` suffix
  stripping → audit for GUID reference; at least key by vehicleDefinition
  family.
- ships.py:657 cargo-grid className-prefix fallback → grid ref exists in ship
  entity XML by GUID (worth an audit).
- ship_equipment.py:117-137 family-substring NPC filter (~90 lines) →
  build exclusion set by GUID from non-emitted vehicles' default loadouts.
  Medium-large, diff-validate.
- fps_weapons.py:63 `salvage_repair` name check → test whether
  `attachDef.type == "WeaponAttachment"` alone suffices.
- missions contract identity = debugName (missions.py:194, __main__.py:342)
  → check for record GUID in DCB, emit alongside.
- blueprint_pools GUID case fallback ×4 call sites → normalize to lowercase
  at parse time.

Audited-irreducible (keep, ensure documented in docs/heuristics_audit.md):
_AI_MISSION_PATTERNS, thruster port-name matching (given classifier
unification above), camera/bomb-turret editorial, empty weapon-rack ports,
pdc port-name last resort, cosmetic _POSITIONAL_TOKENS, description
colon-metadata, resources.py carryable filename regex (add `(_[a-z])?$` and
log unmatched stems), matrix.py name tables (add drift logging: unmatched
flight-ready entries).

## E. Untapped XML data (cache/LIVE/Data)

DCB whitelist covers 21 of ~200 record types under
Libs/Foundry/Records/. Highest-value unread subtrees:

1. **starmap/** (2,058 files, StarMapObject) — POI names/descriptions, QT
   arrivalRadius/obstructionRadius, isScannable, respawn type. Whole new
   locations dataset.
2. **lawsystem/** (220, InfractionDefinition) — felony flags, merits, fines,
   grace periods. Crime table.
3. **lootgeneration/** (495, LootArchetype) — tag-weighted loot pools,
   rarity tags, SpawnWith rules; cross-links to tag DB we already parse.
4. **mining/mineableelements/** (307, MineableElement) — instability,
   resistance, optimal window, explosion multiplier; `resourceType` GUID
   joins resources.json directly. Cheap win.
5. **missionbroker/** (2,584, MissionBrokerEntry) — buy-in, maxInstances,
   difficulty, missionGiver, location GUID, shareability. Enriches existing
   missions.json.
6. **franchises/ + globalshopparams/** — sell matchPercentage, wear curve,
   supply/demand thresholds. NOTE: no per-item price records exist in the
   corpus (RetailProduct absent — prices are server-side now).
7. Entity components parsed but never surfaced: SVehicleArmourModifier
   (per-ship armor multipliers), SMasterModeParams (SCM/NAV),
   EMPoolParams, CargoControllerParams, SCItemPurchasableParams,
   LegalRegistration/Hostility/AITargetable, Thermal/StunResistance.
8. Encounter data: cargomanifest/ (82, NPC cargo fills), crewmanifest/ (56),
   loadoutkits/ (386, pledge/customizer kits).
9. World: ssolarsystem (galactic coords), jumppoints (4), hangars
   instancedinterior/ (85) + landingpadsize/ (6), transitsystem/ (124),
   harvestable/ (892, respawn timers), refiningprocess/ (9),
   ObjectContainers/PU/loc/ (111 socpaks — extend the proven ship-storage
   socpak walk to stations/outposts).
10. Libs/Subsumption/ (4,074 files) — mission-flow ground truth
    (MissionBrokerEntry.missionModule points here). Hard to parse; long-term.

Same-dir gaps in already-whitelisted types: ContractDifficultyProfile (7),
ItemAwardWeightingsRecord (5) under contracts/ are NOT in the whitelist.

Confirmed fully exploited: Scripts/Loadouts, ObjectContainers/Ships socpaks,
Localization, TagDatabase, and all 21 whitelisted record types; no orphan
parsed_*.json caches.

Caveat: new readers for Prefabs/, Scripts/Entities etc. need the CryXmlB
binary check.

## Suggested attack order

1. Section A items 1-5 + 9-10 (correctness, mostly small) — validate each
   with the ~4-min cache-preserving rebuild + output diff.
2. B1, B2, B9, B5 (cheap perf), then B3/B6 (walk + parse-cache
   consolidation), then B4.
3. C10 dead code + C9 mechanical dedup in one cleanup pass; then C3/C4
   (ammo/DPS unification), C8; then C1/C2 (tuple→dataclass, BuildContext).
4. D quick wins (lbco, magazine-type, module/tractor/crew structural).
5. E4 (mining) and E5 (missionbroker) as first new-data additions — both
   join existing outputs by GUID; then E1 starmap as a new dataset.
6. C5/C6/C7 monster-function extractions last, byte-diff verified.
