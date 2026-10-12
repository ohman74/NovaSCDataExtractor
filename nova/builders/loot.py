"""Build loot_locations.json - where in the universe an item can be looted.

Purchasing is deliberately out of scope; shop availability comes from the UEX
pipeline (see TODO_SHOP_INFORMATION.md) and is a separate join key.

The file has three sections so it stays navigable and doesn't blow up
combinatorially. A common attachment matches ~250 container configs and a
preset is placed in many socpaks, so writing the full cross product per item
would multiply into hundreds of thousands of rows:

  presets   slot preset -> where it is physically placed (socpak, body, system)
  items     item -> which presets/configs can roll it, grouped per preset
  actors    NPC/corpse loot tables -> items, for lootable bodies

An item's answer is `items[uuid].sources` joined against `presets`. `reachable`
and `blockedBy` are carried explicitly: an empty source list is otherwise
ambiguous between "not loot" and "gated behind something", and the difference
matters - see the Stoic Suppressor case, which is tagged for the Storm Breaker
locations but which no attachment pool there re-admits.
"""

import collections
import os
import re

from ..loot_match import TagIndex, LootModel
from ..socpak_parser import build_socpak_loot_index, resolve_placements
from ..utils import resolve_name

# `LootGeneration > CanGenerateAsLoot` - the flag CIG sets on anything the
# loot generator is allowed to produce. Used to bound the item sweep.
_CAN_LOOT_PATH = "LootGeneration > CanGenerateAsLoot"
_LOOT_TAG_PREFIX = "LootGeneration"
_EVENT_PATH = "LootGeneration > Event"

# Placement containers are `pu/system/<system>/...`, but the depth varies: a
# body sits directly under the system (`pyro/pyro4.socpak`) while placed
# instances nest below it with a GUID suffix
# (`stanton/stanton1/ugf/sand_drug_001_{...}.socpak`).
_SYSTEM_SOCPAK_RE = re.compile(r"^pu/system/([a-z0-9_]+)/(.+)\.socpak$")
_INSTANCE_SUFFIX_RE = re.compile(r"_\{[0-9a-f-]+\}$")


def _body_name(body_key, translations):
    """Resolve a system-container path segment to its in-game name.

    CIG keys bodies directly: `Pyro1=Pyro I`, `Pyro4=Pyro IV`,
    `Stanton1=Hurston`. Returns None when the segment isn't a known body, so
    the caller can try the next one up the path.
    """
    for candidate in (body_key.capitalize(), body_key.title(), body_key):
        got = translations.get(candidate)
        if got:
            return got
    return None


def _location(system_socpak, translations):
    """Map a system-container path to (system, body).

    Walks from the most specific path segment outwards and takes the first one
    the localisation knows as a body. That turns
    `pu/system/stanton/stanton1/ugf/sand_drug_001_{guid}.socpak` into Hurston,
    while leaving genuinely body-less containers (asteroid rings, Lagrange
    clouds) flagged unresolved instead of mislabelled.
    """
    m = _SYSTEM_SOCPAK_RE.match(system_socpak)
    if not m:
        return {"system": "", "body": "", "container": system_socpak, "resolved": False}
    system, rest = m.group(1), m.group(2).split("/")
    candidates = [_INSTANCE_SUFFIX_RE.sub("", rest[-1])] + list(reversed(rest[:-1]))
    for candidate in candidates:
        name = _body_name(candidate, translations)
        if name:
            return {"system": system.capitalize(), "body": name,
                    "container": system_socpak, "resolved": True}
    return {"system": system.capitalize(), "body": candidates[0],
            "container": system_socpak, "resolved": False}


def build_loot_locations(ctx) -> dict:
    """Resolve every lootable item to the container configs that can roll it."""
    loot = ctx.loot
    items_by_class = ctx.items
    tags = ctx.tags
    translations = ctx.translations
    cache_dir = ctx.cache_dir

    tag_index = TagIndex(tags)
    tag_path = {g: (v.get("Path") or "") for g, v in tags.items()}
    can_loot = next((g for g, p in tag_path.items() if p == _CAN_LOOT_PATH), "")

    item_tags, item_meta = {}, {}
    for entry in items_by_class.values():
        guid = entry.get("guid")
        if not guid:
            continue
        item_tags[guid] = set(entry.get("entityTagGuids") or [])
        item_meta[guid] = entry

    model = LootModel(loot, tag_index, item_tags)

    print("  Indexing socpak loot placements...")
    socpak_index = build_socpak_loot_index(cache_dir)
    placements = resolve_placements(socpak_index)

    # preset guid -> placements. A preset placed in no system container is
    # unplaced dev content; it is kept with an empty location list so the
    # distinction stays visible instead of looking like a lookup miss.
    preset_placements = collections.defaultdict(list)
    for socpak, info in socpak_index.get("containers", {}).items():
        systems = placements.get(socpak, {})
        for preset_guid, count in info["presets"].items():
            # `count` is per module definition; a module is instantiated
            # `instances` times in a given system, so the containers a player
            # can actually open is the product.
            locations = [dict(_location(system, translations),
                              instances=instances,
                              containers=count * instances)
                         for system, instances in systems.items()]
            preset_placements[preset_guid].append({
                "socpak": socpak,
                "containersPerModule": count,
                "containers": sum(loc["containers"] for loc in locations),
                "locations": locations,
            })

    presets_out = {}
    for guid, rec in loot["slotPresets"].items():
        places = preset_placements.get(guid, [])
        presets_out[rec["className"]] = {
            "guid": guid,
            "totalContainers": sum(p["containers"] for p in places),
            "placements": sorted(places, key=lambda p: p["socpak"]),
        }

    # Only items CIG marked lootable are swept; everything else can only ever
    # come back empty and would bloat the file with negative results.
    candidates = [g for g, t in item_tags.items() if not can_loot or can_loot in t]
    print(f"  Resolving loot sources for {len(candidates)} lootable items...")

    def group_sources(raw):
        """Collapse raw sources into per-preset and per-actor groups."""
        by_preset, by_actor = collections.OrderedDict(), collections.OrderedDict()
        for s in raw:
            if s["kind"] != "container":
                slot = by_actor.setdefault(s["actor"], {
                    "kind": "actor", "actor": s["actor"], "lootTables": [],
                })
                if s["lootTable"] not in slot["lootTables"]:
                    slot["lootTables"].append(s["lootTable"])
                continue
            slot = by_preset.setdefault(s["preset"], {
                "preset": s["preset"], "configs": [], "lootTables": [],
                "archetypes": [], "generation": s["generation"],
                "poolFilter": s["poolFilter"],
            })
            for key, value in (("configs", s["config"]), ("lootTables", s["lootTable"]),
                               ("archetypes", s["archetype"])):
                if value and value not in slot[key]:
                    slot[key].append(value)
        out = sorted(by_preset.values(), key=lambda g: g["preset"])
        for g in out:
            for key in ("configs", "lootTables", "archetypes"):
                g[key].sort()
        actors = sorted(by_actor.values(), key=lambda g: g["actor"])
        for g in actors:
            g["lootTables"].sort()
        return out + actors

    items_out = {}
    actors_out = collections.defaultdict(list)
    # Reachability is a property of an item's tags, and tags repeat heavily:
    # 3715 lootable items resolve to ~155 distinct source sets. Storing each
    # set once and referencing it by index keeps the file ~2% of the size it
    # would be inlined, with no loss of detail.
    source_sets = []
    source_set_ids = {}

    def intern_sources(groups):
        signature = repr(groups)
        set_id = source_set_ids.get(signature)
        if set_id is None:
            set_id = len(source_sets)
            source_set_ids[signature] = set_id
            source_sets.append(groups)
        return set_id
    for guid in candidates:
        meta = item_meta[guid]
        sources = model.sources_for(guid)

        for s_ in sources:
            if s_["kind"] != "container":
                actors_out[s_["actor"]].append({
                    "item": meta["className"],
                    "lootTable": s_["lootTable"],
                    "entry": s_["entry"],
                })
        grouped = group_sources(sources)
        # An item is reachable if a placed container can roll it, or if a
        # lootable NPC carries it. Actors have no socpak placement of their
        # own, so they must be counted separately or corpse-only loot reads
        # as unobtainable.
        placed = [g for g in grouped
                  if g.get("kind") == "actor"
                  or presets_out.get(g["preset"], {}).get("totalContainers")]

        set_id = intern_sources(grouped)

        record = {
            "className": meta["className"],
            "name": resolve_name((meta.get("attachDef") or {}).get("name", ""),
                                 translations) or meta["className"],
            "lootTags": sorted(tag_path.get(t, t) for t in item_tags[guid]
                               if tag_path.get(t, "").startswith(_LOOT_TAG_PREFIX)),
            "reachable": bool(placed),
            "sourceSet": set_id,
        }
        if not grouped:
            record["blockedBy"] = model.blocked_reason(guid)
        elif not placed:
            record["blockedBy"] = "matching presets are not placed in any system container"

        # Event-gated items are, by CIG's own description of the tag, kept out
        # of generic loot. Observed play contradicts that for at least the
        # barrel attachments, so record the pools the item would reach if the
        # gate were not enforced. That set is what players actually see.
        if any(tag_path.get(t, "").startswith(_EVENT_PATH) for t in item_tags[guid]):
            observed = group_sources(model.sources_for(guid, ignore_event_gate=True))
            if observed != grouped:
                record["eventGated"] = True
                record["observedSourceSet"] = intern_sources(observed)
        items_out[guid] = record

    reachable = sum(1 for v in items_out.values() if v["reachable"])
    print(f"  Loot locations: {reachable}/{len(items_out)} lootable items reachable, "
          f"{len(presets_out)} presets, "
          f"{sum(p['totalContainers'] for p in presets_out.values())} placed containers, "
          f"{len(source_sets)} distinct source sets")

    return {
        "presets": presets_out,
        "sourceSets": source_sets,
        "items": items_out,
        "actors": {k: v for k, v in sorted(actors_out.items())},
    }
