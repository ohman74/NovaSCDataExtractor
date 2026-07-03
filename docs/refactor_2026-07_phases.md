# Refactor 2026-07 — phases B–E: before/after verification vs live.zip

Continuation of `docs/code_review_2026-07.md` after the section A bugfixes
(whose value diffs are in `docs/section_a_value_diffs.md`). Each phase was
rebuilt and diffed against the previous output with the same recursive
JSON differ used for section A.

## Headline for double-checking against live.zip

**Phases B, C and D changed NOTHING in the emitted data.** Every rebuild
diffed byte-identical to the previous LIVE output except
`metadata.extractionTimestamp`. There are no new ship/weapon deviations to
verify beyond the section A list — the cumulative content difference vs the
pre-review live.zip is exactly:

1. the section A corrections (documented per-ship/per-item in
   `docs/section_a_value_diffs.md`), and
2. two brand-new files added in phase E (below) — no existing file changed.

## Phase B — performance (commit "perf: section B hot-path optimizations")

Full LIVE rebuild: **195 s → 154 s** (−21 %); streaming DataForge parse
50 s. Changes: iterparse fast path + root cleanup (memory), cosmetic
classifier memoization (was O(group²) re-parses), _build_ship memoized
(ground vehicles were built twice), cargo-grid prefix index, entity XMLs
read once instead of twice, shared items_by_guid index, metadata counts
without re-reading outputs, extractor os.walk removed, compact parsed_*.json.
Verified: diff = extractionTimestamp only (full reparse from Game2.xml).

## Phase C — dead code (commit "cleanup: section C dead code removal")

−239 lines: unused entity_parser port functions, unreachable
ship_equipment filter, empty hook tables + shadowed set in stditem,
zero-caller helpers, unused BUILDERS slot, empty MFR_ALIASES, unforge
download asset, NULL_GUID/_CARGO_CELL constants, hoisted imports.
The lowercase `splineJump` parser block was deleted after confirming zero
occurrences in the current Game2.xml.
Verified: diff = extractionTimestamp only.

## Phase D — heuristic → structural identification (commit "debt: replace
three name heuristics with structural identification")

These COULD have changed output; on the current corpus they did not
(diff = extractionTimestamp only), which is the intended outcome — same
answer, patch-rename-proof derivation:

- LBCO "Electron" class: manufacturer GUID `98bb2e9e-…` instead of
  className prefix (the mfr record's code/name are placeholders in CIG
  data, so the GUID is the only structural key).
- FPS magazine resolution: loadout items typed `WeaponAttachment.Magazine`
  (surveyed: 363/363 resolvable magazine-port items have exactly this
  type; no other port carries it) instead of portName substrings.
- `has_modules` (cargo-grid fallback exclusion): impl port-def types
  containing `Module` (verified on Retaliator) instead of "module" in
  portName.

## Phase E — new datasets (additive only)

### mineables.json (46 entries) — NEW FILE
From `Libs/Foundry/Records/mining/mineableelements/*.xml`
(`MineableElement` records; the extractor never read this subtree).
Per ore/raw material: `Instability`, `Resistance`, `OptimalWindow`
{Midpoint, MidpointRandomness, Thinness}, `ExplosionMultiplier`,
`ClusterFactor`, plus `ResourceGUID` (joins the crafting/commodity
resource GUID space — only Aluminium + Copper currently appear in
resources.json, hence a separate file), `ClassName`, record `GUID`, and
localized `Name` (`items_commodities_<className>` keys; title-case
fallback). Note: some entries carry negative Resistance /
ExplosionMultiplier values (e.g. Aluminium Ore −0.4 / −36) — that is
what the XML says, emitted as-is.

### mission_board.json (2 584 entries) — NEW FILE
From `Libs/Foundry/Records/missionbroker/**` (`MissionBrokerEntry`
records; never previously read). This is the job-board/subsumption
mission system — a different system from the ContractGenerator-based
missions.json, so it is a separate dataset rather than an enrichment.
Per entry: identity (ClassName, GUID, Source subdir, NotForRelease),
localized Title/Description (+raw keys; 96.1 % of pu_missions titles
resolve — the rest are missing from CIG's localization file), mission
Type (GUID + resolved via mission_types), giver, location GUID,
missionModule path, Difficulty, Lawful, BuyIn, instance limits/sharing,
lifetimes/cooldowns, Reward {Amount, Max, Currency, ReputationBonus},
Deadline, wanted-level gate, reputation requirements and rewards
(reputation reward amounts resolve through the previously-unhandled
`Records/reputation/rewards/**` SReputationRewardAmount catalog — 100 %
resolution), and scalar mission Properties.
Documented omissions (TODO in module docstring): objectiveTokens,
missionFlow, partialRewardPayout, non-scalar property types
(Location/Organization/MissionItem/…), scheduling knobs.

## Deferred (tracked in docs/code_review_2026-07.md)

- B3: consolidation of the ~15 per-ship loadout walks in ships.py
  (biggest remaining perf+readability item; needs byte-diff discipline).
- C1/C2: 24-tuple → dataclass for stream_parse_dataforge, BuildContext
  → declared-field dataclass.
- C3/C4: ammo-block and DPS-computation unification in stditem.
- C5–C7: monster-function extraction (_classify_port, _build_hardpoints,
  _build_weapon_data).
- D remaining: tractor verdict pass-through, crew counting via Seat port
  types + controllableTags, ship_equipment NPC filter via GUID exclusion.
- E remaining: starmap (2 058 records — new locations dataset), lawsystem,
  lootgeneration, cargomanifest/loadoutkits, hangars/landing pads,
  ObjectContainers/PU socpak walk for station interiors,
  ContractDifficultyProfile + ItemAwardWeightingsRecord (same dir as
  already-parsed contract records but not whitelisted).
- Open verification item from section A: aux thrusters
  (`thruster_aux_*`, thrusterType="main") currently in Maneuvering —
  check against erkul whether they should be Main.
