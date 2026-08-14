"""Parse the loot-generation graph out of the converted Game2.xml.

Loot never names an item. Every pool is expressed as a *tag query*, so which
item can drop where has to be computed rather than looked up. This module
extracts the records that make up that graph; `loot_match` evaluates it.

Two generations coexist in the datacore and both are live:

  V3  LootTableV3Record -> LootArchetypeV3 entries with tag selectors.
      Event/faction gating happens outside the archetype, in the
      `poolFilter` on the container's lootConstraints.

  V2  LootTable -> WeightedLootArchetype -> LootArchetype, where the
      archetype itself carries `excludedTags` and each primary entry carries
      `tag` + `additionalTags`. V2 uses no pool filters at all, so a
      `poolFilter=` sweep misses this half of the graph entirely.

Both are reached the same way: a SubHarvestableMultiConfigRecord ("slot
preset") maps container tags to a LootConfig, and placed containers in the
socpaks point at a preset by GUID (see socpak_parser.build_socpak_loot_index).

Record counts on LIVE 4.9.188.23497, as a smoke-test baseline:
  PoolFilterRecord 15, LootArchetype 230, LootArchetypeV3Record 34,
  LootTable 155, LootTableV3Record 59, SubHarvestableMultiConfigRecord 103,
  SubHarvestableConfigRecord (shared sub-configs) and HarvestablePreset 571.
"""

import json
import os
import time
import xml.etree.ElementTree as ET

# Top-level record types this pass keeps. Anything else is discarded as soon
# as its end event fires, which is what keeps a 1.9 GB parse in bounds.
_RECORD_TYPES = frozenset({
    "PoolFilterRecord",
    "LootArchetype",
    "LootArchetypeV3Record",
    "LootTable",
    "LootTableV3Record",
    "SubHarvestableMultiConfigRecord",
    "SubHarvestableConfigRecord",
    "HarvestablePreset",
    "LootV3SecondaryChoicesSingleLayerRecord",
    # Entity records are scanned only for the handful of NPCs and creatures
    # that carry their own LootConfig (lootable corpses).
    "EntityClassDefinition",
})

_CACHE_NAME = "parsed_loot.json"


def _refs(elem, *names):
    """Collect `<Reference value="GUID"/>` children under the named subpaths."""
    out = []
    for name in names:
        for sub in elem.iter(name):
            for ref in sub.findall("Reference"):
                v = ref.get("value", "")
                if v:
                    out.append(v)
    return out


def _tag_filter(elem):
    """Return (positive, negative) tag GUIDs for a selector-ish element."""
    pos, neg = [], []
    for block in elem.iter("positiveTags"):
        pos += [r.get("value", "") for r in block.findall("Reference") if r.get("value")]
    for block in elem.iter("negativeTags"):
        neg += [r.get("value", "") for r in block.findall("Reference") if r.get("value")]
    return pos, neg


def _spawn_with(entry):
    """Extract SpawnWith riders (ammo/attachments that come with an item).

    Both generations spell this differently but carry the same fields, so we
    normalise. `mode` is usually "MostSimilar", i.e. the engine ranks
    candidates by tag overlap rather than filtering hard; we record it so
    consumers can label these sources as approximate.
    """
    out = []
    for kind in ("EntryOptionalData_SpawnWith", "ArchetypeOptionalDataV3_SpawnWith"):
        for sw in entry.iter(kind):
            pos, neg = _tag_filter(sw)
            rng = sw.find(".//QuantityRange_Linear")
            out.append({
                "name": sw.get("name", ""),
                "mode": sw.get("mode", ""),
                "chance": sw.get("chanceToSpawnWith", ""),
                "min": sw.get("min", rng.get("min", "") if rng is not None else ""),
                "max": sw.get("max", rng.get("max", "") if rng is not None else ""),
                "positiveTags": pos,
                "negativeTags": neg,
            })
    return out


def _parse_pool_filter(elem):
    """PoolFilterRecord -> ordered filter instances.

    A record is either a bare `PoolFilter_Tags` or a `PoolFilter_Sequence` of
    named instances. Modes seen in the data: Cumulative (intersect, i.e.
    restrict the pool) and Additive (union, i.e. re-admit items the cumulative
    filters removed). Event gating is entirely this mechanism: every generic
    container chains NoFactions + NoSpecialEvents cumulatively, and a
    location-specific filter adds back one `LootGeneration > Event > X` branch.
    """
    instances = []
    seq = elem.find(".//PoolFilter_Sequence")
    if seq is not None:
        for inst in seq.iter("PoolFilterInstance"):
            pos, neg = _tag_filter(inst)
            ref = inst.find(".//PoolFilter_RecordRef")
            instances.append({
                "name": inst.get("name", ""),
                "mode": inst.get("mode", ""),
                "positiveTags": pos,
                "negativeTags": neg,
                "filterRecord": ref.get("filterRecord", "") if ref is not None else "",
            })
    else:
        tags = elem.find(".//PoolFilter_Tags")
        if tags is not None:
            pos, neg = _tag_filter(tags)
            instances.append({
                "name": "", "mode": "Cumulative",
                "positiveTags": pos, "negativeTags": neg, "filterRecord": "",
            })
    return {"filters": instances}


def _parse_archetype_v2(elem):
    """LootArchetype (V2).

    `excludedTags` rejects an item outright. Each primary entry then requires
    its `tag` plus every tag in `additionalTags/positiveTags` (verified AND,
    not any-of: e.g. LootArchetype_Ammo_Pistol_Common = Magazine + Pistol +
    Common yields the 17 common pistol magazines, whereas any-of would yield
    4015 unrelated items). Secondary groups carry the rarity weighting.
    """
    excluded = _refs(elem.find("excludedTags"), "tags") if elem.find("excludedTags") is not None else []
    entries = []
    primary = elem.find("primaryOrGroup")
    if primary is not None:
        for e in primary.iter("LootArchetypeEntry_Primary"):
            add = e.find("additionalTags")
            pos, neg = _tag_filter(add) if add is not None else ([], [])
            entries.append({
                "name": e.get("name", ""),
                "weight": e.get("weight", ""),
                "positiveTags": [e.get("tag", "")] + pos,
                "negativeTags": neg,
                "spawnWith": _spawn_with(e),
            })
    secondary = []
    for group in elem.iter("LootArchetypeOrGroup_Secondary"):
        secondary.append({
            "group": group.get("groupName", ""),
            "entries": [{"tag": s.get("tag", ""), "weight": s.get("weight", "")}
                        for s in group.iter("LootArchetypeEntry_Secondary")],
        })
    return {"excludedTags": excluded, "entries": entries, "secondaryGroups": secondary}


def _parse_archetype_v3_body(elem):
    """Entries of a LootArchetypeV3 (either a record or inlined in a table)."""
    entries = []
    for e in elem.iter("LootArchetypeV3Entry"):
        sel = e.find(".//LootArchetypeV3Selector_Tags")
        if sel is None:
            # Non-tag selectors exist (direct record refs); keep the entry so
            # the count stays honest, but mark it unevaluable.
            entries.append({"name": e.get("name", ""), "weight": e.get("weight", ""),
                            "positiveTags": [], "negativeTags": [],
                            "unsupportedSelector": True, "spawnWith": _spawn_with(e)})
            continue
        pos, neg = _tag_filter(sel)
        entries.append({
            "name": e.get("name", ""),
            "weight": e.get("weight", ""),
            "positiveTags": pos,
            "negativeTags": neg,
            "spawnWith": _spawn_with(e),
        })
    return entries


def _parse_table_v2(elem):
    """LootTable (V2) -> weighted archetype references."""
    out = []
    for w in elem.iter("WeightedLootArchetype"):
        c = w.find("numberOfResultsConstraints")
        out.append({
            "archetype": w.get("archetype", ""),
            "weight": w.get("weight", ""),
            "minResults": c.get("minResults", "") if c is not None else "",
            "maxResults": c.get("maxResults", "") if c is not None else "",
        })
    return {"archetypes": out}


def _parse_table_v3(elem):
    """LootTableV3Record -> entries, each an archetype ref or an inline archetype."""
    out = []
    for e in elem.iter("LootTableV3Entry"):
        ref = e.find(".//LootArchetypeV3_RecordRef")
        limit = e.find(".//LootTableOptionalDataV3_ChoiceLimit")
        inline = e.find(".//LootArchetypeV3")
        out.append({
            "name": e.get("name", ""),
            "weight": e.get("weight", ""),
            "archetype": ref.get("lootArchetypeRecord", "") if ref is not None else "",
            "inlineEntries": _parse_archetype_v3_body(inline) if (ref is None and inline is not None) else [],
            "choiceLimit": limit.get("choiceLimit", "") if limit is not None else "",
        })
    return {"entries": out}


def _loot_configs(elem):
    """Every loot config under an element, flattened with its constraints.

    Slot presets spell it `<lootConfig><LootConfig lootTableV3=...>` - an
    unattributed wrapper around the real element - while entity records put the
    attributes straight on a lowercase `<lootConfig lootTableV3=...>` under
    LootGenerationComponentParams. Keying on the attribute rather than the tag
    name catches both and skips the wrapper.
    """
    out = []
    for lc in elem.iter():
        if not (lc.get("lootTable") or lc.get("lootTableV3")):
            continue
        con = lc.find("lootConstraints")
        rng = lc.find(".//fullnessFactorRange")
        out.append({
            "lootTable": lc.get("lootTable", ""),
            "lootTableV3": lc.get("lootTableV3", ""),
            "poolFilter": con.get("poolFilter", "") if con is not None else "",
            "totalResultsLimit": con.get("totalResultsLimit", "") if con is not None else "",
            "chanceToGenerate": con.get("chanceToGenerate", "") if con is not None else "",
            "fullnessMin": rng.get("min", "") if rng is not None else "",
            "fullnessMax": rng.get("max", "") if rng is not None else "",
        })
    return out


def _parse_slot_preset(elem):
    """SubHarvestableMultiConfigRecord -> named configs with their loot configs.

    A config's subConfig is either inline (`SubHarvestableConfigSingleManual`,
    holding LootConfigs directly) or a reference to a shared
    SubHarvestableConfigRecord, which has to be resolved afterwards.
    """
    configs = []
    for cfg in elem.iter("TaggedSubHarvestableConfig"):
        tag_list = cfg.find("tagList")
        configs.append({
            "name": cfg.get("name", ""),
            "tags": _refs(tag_list, "tags") if tag_list is not None else [],
            "subConfigRefs": [r.get("subConfigRef", "") for r in cfg.iter("SubHarvestableConfigSingleRef")
                              if r.get("subConfigRef")],
            "lootConfigs": _loot_configs(cfg),
        })
    return {"configs": configs}


def parse_loot_records(xml_path, cache_dir=None):
    """Stream Game2.xml once and return the loot graph.

    Cached to `parsed_loot.json`; the cache is invalidated when it predates
    Game2.xml, matching the staleness rule the DataForge parser uses.
    """
    cache_file = os.path.join(cache_dir, _CACHE_NAME) if cache_dir else None
    if cache_file and os.path.isfile(cache_file):
        if os.path.getmtime(cache_file) >= os.path.getmtime(xml_path):
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"  Loaded cached loot graph "
                  f"({len(data['slotPresets'])} slot presets, "
                  f"{len(data['tablesV2']) + len(data['tablesV3'])} loot tables)")
            return data
        print("  Cached loot graph is older than Game2.xml - reparsing.")

    print("  Parsing loot graph...")
    start = time.time()
    out = {
        "poolFilters": {}, "archetypesV2": {}, "archetypesV3": {},
        "tablesV2": {}, "tablesV3": {}, "slotPresets": {}, "subConfigs": {},
        "harvestablePresets": {}, "secondaryChoices": {}, "entityLoot": {},
    }
    parsers = {
        "PoolFilterRecord": ("poolFilters", _parse_pool_filter),
        "LootArchetype": ("archetypesV2", _parse_archetype_v2),
        "LootTable": ("tablesV2", _parse_table_v2),
        "LootTableV3Record": ("tablesV3", _parse_table_v3),
        "SubHarvestableMultiConfigRecord": ("slotPresets", _parse_slot_preset),
    }

    depth = 0
    root = None
    record = None   # record type currently being read, or None to skip
    for event, elem in ET.iterparse(xml_path, events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 1:
                root = elem
            elif depth == 2:
                rtype = elem.tag.split(".", 1)[0]
                record = rtype if rtype in _RECORD_TYPES else None
            continue

        depth -= 1
        if depth != 1:
            continue
        if record is None:
            # Top-level record we don't want. Drop it and detach it from the
            # root, or 1.36M empty shells accumulate over the parse.
            elem.clear()
            if root is not None:
                root.clear()
            continue

        rtype = record
        record = None
        guid = elem.get("__ref", "")
        class_name = elem.tag.split(".", 1)[1] if "." in elem.tag else elem.tag
        if guid:
            if rtype in parsers:
                bucket, fn = parsers[rtype]
                rec = fn(elem)
                rec["className"] = class_name
                out[bucket][guid] = rec
            elif rtype == "LootArchetypeV3Record":
                body = elem.find(".//LootArchetypeV3")
                out["archetypesV3"][guid] = {
                    "className": class_name,
                    "entries": _parse_archetype_v3_body(body) if body is not None else [],
                }
            elif rtype == "SubHarvestableConfigRecord":
                out["subConfigs"][guid] = {"className": class_name,
                                           "lootConfigs": _loot_configs(elem)}
            elif rtype == "HarvestablePreset":
                out["harvestablePresets"][guid] = {"className": class_name,
                                                   "entityClass": elem.get("entityClass", "")}
            elif rtype == "LootV3SecondaryChoicesSingleLayerRecord":
                out["secondaryChoices"][guid] = {
                    "className": class_name,
                    "choices": [{"name": c.get("name", ""), "weight": c.get("weight", ""),
                                 "positiveTags": _tag_filter(c)[0]}
                                for c in elem.iter("LootV3SecondaryChoiceEntry")],
                }
            elif rtype == "EntityClassDefinition":
                configs = _loot_configs(elem)
                if configs:
                    out["entityLoot"][guid] = {"className": class_name, "lootConfigs": configs}
        elem.clear()
        if root is not None:
            root.clear()

    print(f"  Loot graph: {len(out['poolFilters'])} pool filters, "
          f"{len(out['archetypesV2'])} V2 / {len(out['archetypesV3'])} V3 archetypes, "
          f"{len(out['tablesV2'])} V2 / {len(out['tablesV3'])} V3 tables, "
          f"{len(out['slotPresets'])} slot presets, {len(out['subConfigs'])} sub-configs, "
          f"{len(out['entityLoot'])} entities with loot ({time.time() - start:.0f}s)")

    if cache_file:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(out, f)
    return out
