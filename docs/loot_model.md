# Loot model: how "where can I loot X" is derived

Measured against LIVE `4.9.188.23497`.

Loot generation never names an item. Every pool is a **tag query**, so
reachability has to be computed. This document records the chain, the
semantics questions that had to be settled before the model could be trusted,
and the evidence for each answer.

Code: `nova/loot_parser.py` (extract), `nova/loot_match.py` (evaluate),
`nova/builders/loot.py` (emit), `nova/loot_query.py` (look up).

## The chain

```
item entityTagGuids
   |  matched by tag selectors
LootArchetype (V2)  /  LootArchetypeV3 (V3)
   |  weighted into
LootTable (V2)      /  LootTableV3Record (V3)
   |  referenced by a named config in
SubHarvestableMultiConfigRecord     "slot preset", 103 records, 45 in use
   |  bound by multiConfigRef in *.entxml
socpak                              304 of 9,614 place a loot container
   |  module -> set -> system container
PU/system/<system>/<body>.socpak
```

Two generations run side by side and both are live. V3 gates event and faction
content with a `poolFilter` on the container's `lootConstraints`. V2 has no
pool filters at all and gates with per-archetype `excludedTags`, so a
`poolFilter=` sweep silently misses half the graph.

## Settled semantics

### 1. Tag matching is descendant-inclusive

A selector asking for `Weapon > FPS > Attachment` matches an item carrying only
the child `... > Attachment > Barrel`. Three independent arguments:

- Six items in the entire game carry that parent tag directly (the GRIN
  multitools); 174 carry a descendant. Exact matching would make every
  attachment archetype yield multitools only.
- `LootArchetype_Container_Small_Weapons_*` lists the parent tag in
  `excludedTags` to keep attachments out of weapon containers. Under exact
  matching that exclusion would do nothing.
- Selectors routinely pair a parent positive with a child negative
  (`+Attachment`, `-Attachment > Magazine`). The pairing is only meaningful
  when the positive already covers the child.

### 2. `positiveTags` is AND, not any-of

Every multi-tag selector in the game is a semantic conjunction: "Optic + S1",
"Pistol + Magazine", "Healing + InjectionPen", "Heavy + Backpack". The decisive
counter-test: `LootArchetype_Ammo_Pistol_Common` requires Magazine + Pistol +
Common and yields the 17 common pistol magazines it is named after. Under
any-of it would yield 4,015 unrelated items.

A handful of entries evaluate to nothing under AND. Those are simply dead
entries, and the data has several independently of this question, e.g.
`LootArchetypes_Large_Armour_Legendary_Orbageddon` asking for Antium + Pistol,
and "S2 Underbarrel attachments", for which no item exists.

### 3a. The event gate is designed but not enforced

CIG's description on the `LootGeneration > Event` tag states the intent
verbatim:

> Tag for events or other special situations which need to protect items
> against appearing in generic loot so they only appear in specifically tagged
> loot boxes

The model below implements exactly that. **Observed play contradicts it.**
Confirmed on build 4.9.188.23497, the same build this data comes from: a
Torrent Compensator (StormBreaker-tagged) looted loose from a container in a
Stanton drug lab, and video evidence of a Quell Suppressor 1
(Orbageddon-tagged) likewise. Drug labs run `V3SlotPreset_Loot_Military`,
whose 97 configs all use `V3PoolFilter_Generic`, which by the data cannot
admit an event-tagged item.

Everything else was ruled out before reaching this conclusion: the installed
build matches the cache, placed containers carry no per-instance pool filter
override, the preset has no config shape the parser skips, making negative
tags exact-match breaks the faction gate (1092 faction items carry only
descendant tags), and SpawnWith is not the path because the item was looted
loose rather than mounted on a weapon.

So the divergence is in the engine, not the data. `loot_locations.json`
therefore carries both answers: `sourceSet` is reachability by design, and
`observedSourceSet` (present when `eventGated` is true) is what the pools
match when the event gate is ignored. The second one is what players see.
289 items carry the distinction.

### 3. Pool filters are a sequence, and Additive bypasses Cumulative

`PoolFilterInstance` comes in two modes. Cumulative instances restrict the pool
and must all pass. Additive instances union items back in on their own. The
resulting rule is `all(cumulative) or any(additive)`.

This single mechanism is the whole event system. `V3PoolFilter_Generic` =
NoFactions + NoSpecialEvents, both Cumulative, and it is used by 1,240 of the
1,252 container configs that carry a filter. `V3PoolFilter_NoSpecialEvents`
negates the entire `LootGeneration > Event` branch, so event-tagged items are
invisible to ordinary loot. A location-specific filter then adds exactly one
event branch back:

| Pool filter | Additive branch | Excludes |
|---|---|---|
| `V3PoolFilter_ASDDelving` | ASDDelving | Part2 |
| `V3PoolFilter_ASDDelving_ScienceWing` | ASDDelving | Part1 |
| `V3PoolFilter_DCDelving` | DCDelving | |
| `V3PoolFilter_Orbageddon` | Orbageddon | |
| `V3PoolFilter_RockCracker` | RockCracker | |
| `V3PoolFilter_SOO` | SoO | |
| `V3PoolFilter_StormBreaker_Data` | StormBreaker | StormBreaker > Lab |
| `V3PoolFilter_StormBreaker_Lab` | StormBreaker | StormBreaker > DataCentre |
| `V3PoolFilter_TSG` | TSG | |
| `V3PoolFilter_WelcomeToNyx` | WelcomeToNyx, faction ShatteredBlade | |

### 4. Items can spawn attached to other items

`EntryOptionalData_SpawnWith` / `ArchetypeOptionalDataV3_SpawnWith` attach ammo
and, in nine archetypes, a random attachment to a rolled weapon
(`+Weapon > FPS > Attachment`, `-Magazine`, `-Multitool`). These use
`mode="MostSimilar"`, i.e. a similarity ranking rather than a hard filter, so
they are parsed and stored but not treated as a reachability path. Anything
reachable only through SpawnWith will read as unreachable.

### 5. Actors carry loot too

132 entity records (NPC archetypes, corpses, one Vanduul pilot) hold their own
`LootConfig`. They are emitted in the `actors` section rather than tied to a
socpak, because an NPC's location is a spawn-system question, not a placement.

## The `LootGeneration > Event` branch

17 tags, with the number of items carrying each. Sub-branches matter: searching
only the parent GUID undercounts badly, which is how the Storm Breaker set was
initially read as 8 items instead of 50.

| Tag | Items |
|---|---|
| ASDDelving | 7 |
| ASDDelving > Part1 | 34 |
| ASDDelving > Part2 | 21 |
| ContestedZone | 27 |
| DCDelving | 37 |
| GoblinGathering | 4 |
| Orbageddon | 38 |
| RockCracker | 28 |
| SoO | 20 |
| StormBreaker | 8 |
| StormBreaker > DataCentre | 15 |
| StormBreaker > Lab | 27 |
| TSG | 23 |
| TheCollector | 7 |
| WelcomeToNyx | 35 |
| BennyHenge | 0 |

## Output

`output/<channel>/loot_locations.json`, four sections:

- `presets` - slot preset to physical placements (socpak, body, system)
- `sourceSets` - deduplicated source lists. 3,715 lootable items collapse to
  ~174 distinct sets, which is what keeps the file around 5 MB instead of 83
- `items` - item to `sourceSet` index, plus `reachable` and `blockedBy`
- `actors` - NPC/corpse loot tables

`reachable` and `blockedBy` are carried explicitly because an empty source list
is otherwise ambiguous between "not loot" and "gated behind something". The
Stoic Suppressor is the worked example: tagged for Storm Breaker, but every
attachment pool at those locations runs the generic filter, so it resolves to
`reachable: false` with the two rejecting filters named.

Query it with:

```
py -m nova.loot_query "Stoic Suppressor"
py -m nova.loot_query arma_barrel_supp_s2_03 --verbose
```

## Known limitations

- **SpawnWith is not a reachability path** (see 4 above).
- **Body naming is localisation-driven.** A placement resolves to a body by
  walking the system-container path outwards and taking the first segment the
  localisation knows (`Stanton1=Hurston`, `Pyro4=Pyro IV`). Containers with no
  body segment (asteroid rings, Lagrange clouds, `pyro1_ptn`) stay flagged
  `resolved: false` rather than being guessed at.
- **Container counts are per world instance, not per module.** A facility
  module is defined once and instantiated many times: Pyro IV places the Farro
  data-centre module 10 times, Pyro I places the Lazarus research module 6
  times. `resolve_placements` multiplies along the chain, validated against the
  `Outpost_ASD_DF_Pyro4_FarroDataCenter_*` and `..._LazarusComplex_*` mission
  templates, whose counts match exactly. Counting module definitions instead
  understates the world by 8x overall (497 versus 6,779 containers) and
  reorders every location ranking, so it is worth re-checking after a patch.
- **Rarity is a gate, not a probability.** Secondary rarity groups are applied
  as a filter; the emitted weights are not turned into drop chances, because
  container fullness, `chanceToGenerate` and result limits all compound and the
  model has not been validated against observed drop rates.
- **No shop data.** Buying is a separate question with a separate source; see
  `TODO_SHOP_INFORMATION.md`.
