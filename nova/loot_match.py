"""Evaluate the loot graph: which items can drop from which containers.

The datacore never links a loot pool to an item. Pools are tag queries, so
reachability is computed here. Three rules govern the evaluation, each one
established against the data rather than assumed (see docs/loot_model.md):

1. **Tag matching is descendant-inclusive.** A selector asking for
   `Weapon > FPS > Attachment` matches an item tagged only with the child
   `... > Attachment > Barrel`. Six items in the whole game carry that parent
   tag directly while 174 carry a descendant, and selectors routinely pair a
   parent positive with a child negative ("+Attachment, -Attachment>Magazine"),
   which is only meaningful under descendant matching.

2. **positiveTags is AND, not any-of.** Every multi-tag selector in the game
   is a semantic conjunction: "Optic + S1", "Pistol + Magazine",
   "Healing + InjectionPen". Under any-of, `LootArchetype_Ammo_Pistol_Common`
   would yield 4015 items instead of the 17 common pistol magazines it names.
   A few entries evaluate to nothing under AND; those are simply dead entries
   and the data has several (e.g. "Antium Armour" asking for Antium + Pistol).

3. **Pool filters are a sequence.** Cumulative instances restrict the pool;
   Additive instances union items back in, bypassing the cumulative ones.
   That is exactly how event loot works: every generic container chains
   NoFactions + NoSpecialEvents cumulatively, so anything tagged under
   `LootGeneration > Event` is invisible, and a location-specific filter adds
   one event branch back.
"""

import collections

_EVENT_TAG_PATH = "LootGeneration > Event"


class TagIndex:
    """Tag hierarchy with descendant closure, built from parsed_tags.json."""

    def __init__(self, tags):
        self._path = {g: (v.get("Path") or "") for g, v in tags.items()}
        by_path = collections.defaultdict(list)
        for g, p in self._path.items():
            if p:
                by_path[p].append(g)
        self._sorted = sorted(by_path)
        self._by_path = by_path
        self._family_cache = {}

    def path(self, guid):
        return self._path.get(guid, "")

    def family(self, guid):
        """{guid} plus every descendant tag GUID."""
        cached = self._family_cache.get(guid)
        if cached is not None:
            return cached
        p = self._path.get(guid)
        fam = {guid}
        if p:
            import bisect
            prefix = p + " > "
            i = bisect.bisect_left(self._sorted, prefix)
            while i < len(self._sorted) and self._sorted[i].startswith(prefix):
                fam.update(self._by_path[self._sorted[i]])
                i += 1
            fam.update(self._by_path.get(p, ()))
        self._family_cache[guid] = fam
        return fam


class LootModel:
    """Resolved loot graph with reverse indexes for item -> container lookups."""

    def __init__(self, loot, tag_index, item_tags):
        """
        loot:       parse_loot_records() output
        tag_index:  TagIndex
        item_tags:  {item_guid: set(tag_guids)} for every candidate item
        """
        self.loot = loot
        self.tags = tag_index
        self.item_tags = item_tags
        self._carriers = {}
        # The `LootGeneration > Event` marker, needed to model the difference
        # between designed and observed reachability (see pool_allows).
        self.event_tag = next(
            (g for g in tag_index._path if tag_index.path(g) == _EVENT_TAG_PATH), "")
        self._build_entry_index()
        self._build_reverse_indexes()

    # -- tag matching ----------------------------------------------------

    def carriers(self, tag_guid):
        """Items carrying this tag or any descendant of it."""
        got = self._carriers.get(tag_guid)
        if got is None:
            fam = self.tags.family(tag_guid)
            got = {i for i, t in self.item_tags.items() if t & fam}
            self._carriers[tag_guid] = got
        return got

    def select(self, positive, negative):
        """Item set matching AND(positive) minus ANY(negative)."""
        positive = [p for p in positive if p]
        if not positive:
            return set()
        out = self.carriers(positive[0])
        for p in positive[1:]:
            out = out & self.carriers(p)
            if not out:
                return set()
        for n in negative:
            if n:
                out = out - self.carriers(n)
        return out

    def item_matches(self, item_guid, positive, negative):
        tags = self.item_tags.get(item_guid, set())
        for p in positive:
            if p and not (tags & self.tags.family(p)):
                return False
        for n in negative:
            if n and (tags & self.tags.family(n)):
                return False
        return True

    # -- pool filters ----------------------------------------------------

    def pool_allows(self, item_guid, filter_guid, _depth=0, ignore_event_gate=False):
        """Evaluate a PoolFilterRecord against one item.

        No filter means no restriction. Cumulative instances must all pass;
        any Additive instance that matches admits the item on its own.

        `ignore_event_gate` drops the `LootGeneration > Event` exclusion. CIG's
        own description of that tag is "protect items against appearing in
        generic loot so they only appear in specifically tagged loot boxes",
        and this model implements exactly that. Observed play contradicts it:
        event-tagged barrel attachments (Quell, Torrent) do drop loose from
        generic containers such as Stanton drug labs. The engine evidently
        does not enforce the gate on that path, so the flag lets callers
        compute the pools an item reaches in practice as opposed to by design.
        """
        if not filter_guid:
            return True
        rec = self.loot["poolFilters"].get(filter_guid)
        if rec is None or _depth > 8:
            return True
        cumulative_ok = True   # vacuously true when the record has no Cumulative
        additive_hit = False   # stays false when it has no Additive
        for inst in rec["filters"]:
            if inst["filterRecord"]:
                ok = self.pool_allows(item_guid, inst["filterRecord"], _depth + 1,
                                      ignore_event_gate)
            else:
                negative = inst["negativeTags"]
                if ignore_event_gate and self.event_tag:
                    negative = [n for n in negative if n != self.event_tag]
                ok = self.item_matches(item_guid, inst["positiveTags"], negative)
            if inst["mode"] == "Additive":
                additive_hit = additive_hit or ok
            else:
                cumulative_ok = cumulative_ok and ok
        return cumulative_ok or additive_hit

    # -- graph indexes ---------------------------------------------------

    def _build_entry_index(self):
        """Flatten every archetype entry into a uniform, addressable form.

        Inline V3 archetypes (a table holding its own entries rather than
        referencing a record) get a synthetic key `<table_guid>#<n>` so both
        shapes index identically.
        """
        self.entries = {}          # entry_key -> dict
        self.archetype_entries = collections.defaultdict(list)  # archetype_guid -> [entry_key]

        for guid, rec in self.loot["archetypesV3"].items():
            for i, e in enumerate(rec["entries"]):
                key = f"{guid}#{i}"
                self.entries[key] = {
                    "archetype": guid, "archetypeName": rec["className"],
                    "generation": "V3", "entry": e,
                }
                self.archetype_entries[guid].append(key)

        for guid, rec in self.loot["archetypesV2"].items():
            for i, e in enumerate(rec["entries"]):
                key = f"{guid}#{i}"
                self.entries[key] = {
                    "archetype": guid, "archetypeName": rec["className"],
                    "generation": "V2", "entry": e,
                    "excludedTags": rec["excludedTags"],
                    "secondaryGroups": rec["secondaryGroups"],
                }
                self.archetype_entries[guid].append(key)

        for guid, rec in self.loot["tablesV3"].items():
            for i, te in enumerate(rec["entries"]):
                for j, e in enumerate(te["inlineEntries"]):
                    key = f"{guid}#inline{i}.{j}"
                    self.entries[key] = {
                        "archetype": f"{guid}#inline{i}", "archetypeName": rec["className"],
                        "generation": "V3", "entry": e,
                    }
                    self.archetype_entries[f"{guid}#inline{i}"].append(key)

    def _build_reverse_indexes(self):
        # archetype -> [(table_guid, generation, weight)]
        self.archetype_tables = collections.defaultdict(list)
        for guid, rec in self.loot["tablesV2"].items():
            for a in rec["archetypes"]:
                if a["archetype"]:
                    self.archetype_tables[a["archetype"]].append((guid, "V2", a["weight"]))
        for guid, rec in self.loot["tablesV3"].items():
            for i, e in enumerate(rec["entries"]):
                target = e["archetype"] or (f"{guid}#inline{i}" if e["inlineEntries"] else "")
                if target:
                    self.archetype_tables[target].append((guid, "V3", e["weight"]))

        # table -> [(preset_guid, config_name, loot_config)]
        self.table_configs = collections.defaultdict(list)
        sub = self.loot["subConfigs"]
        for guid, rec in self.loot["slotPresets"].items():
            for cfg in rec["configs"]:
                configs = list(cfg["lootConfigs"])
                for ref in cfg["subConfigRefs"]:
                    shared = sub.get(ref)
                    if shared:
                        configs += shared["lootConfigs"]
                for lc in configs:
                    for table in (lc["lootTable"], lc["lootTableV3"]):
                        if table:
                            self.table_configs[table].append((guid, cfg["name"], lc))

        # table -> [(entity_class, loot_config)] for lootable NPCs and corpses
        self.table_entities = collections.defaultdict(list)
        for guid, rec in self.loot["entityLoot"].items():
            for lc in rec["lootConfigs"]:
                for table in (lc["lootTable"], lc["lootTableV3"]):
                    if table:
                        self.table_entities[table].append((rec["className"], lc))

    # -- resolution ------------------------------------------------------

    def entry_matches(self, entry_key, item_guid):
        info = self.entries[entry_key]
        e = info["entry"]
        if e.get("unsupportedSelector"):
            return False
        if info["generation"] == "V2":
            tags = self.item_tags.get(item_guid, set())
            for x in info["excludedTags"]:
                if tags & self.tags.family(x):
                    return False
            # Each secondary group (rarity) must be satisfied by one of its
            # entries, otherwise the roll can never land on this item.
            for group in info["secondaryGroups"]:
                if group["entries"] and not any(
                        self.item_matches(item_guid, [s["tag"]], []) for s in group["entries"]):
                    return False
        return self.item_matches(item_guid, e["positiveTags"], e["negativeTags"])

    def sources_for(self, item_guid, ignore_event_gate=False):
        """All container configs that can produce this item.

        Returns a list of dicts describing the full chain. Sources blocked by
        the container's pool filter are dropped here, which is what makes an
        event-gated item come back empty outside its event locations.
        """
        out = []
        for key, info in self.entries.items():
            if not self.entry_matches(key, item_guid):
                continue
            for table_guid, gen, weight in self.archetype_tables.get(info["archetype"], ()):
                table = (self.loot["tablesV3"].get(table_guid)
                         or self.loot["tablesV2"].get(table_guid) or {})
                for preset_guid, cfg_name, lc in self.table_configs.get(table_guid, ()):
                    if not self.pool_allows(item_guid, lc["poolFilter"],
                                            ignore_event_gate=ignore_event_gate):
                        continue
                    preset = self.loot["slotPresets"][preset_guid]
                    out.append({
                        "kind": "container",
                        "preset": preset["className"], "presetGuid": preset_guid,
                        "config": cfg_name,
                        "lootTable": table.get("className", table_guid),
                        "archetype": info["archetypeName"],
                        "entry": info["entry"]["name"],
                        "generation": gen,
                        "tableWeight": weight,
                        "entryWeight": info["entry"].get("weight", ""),
                        "chanceToGenerate": lc.get("chanceToGenerate", ""),
                        "poolFilter": self.loot["poolFilters"].get(
                            lc["poolFilter"], {}).get("className", ""),
                    })
                for entity_class, lc in self.table_entities.get(table_guid, ()):
                    if not self.pool_allows(item_guid, lc["poolFilter"],
                                            ignore_event_gate=ignore_event_gate):
                        continue
                    out.append({
                        "kind": "actor",
                        "actor": entity_class,
                        "lootTable": table.get("className", table_guid),
                        "archetype": info["archetypeName"],
                        "entry": info["entry"]["name"],
                        "generation": gen,
                        "tableWeight": weight,
                        "entryWeight": info["entry"].get("weight", ""),
                    })
        return out

    def blocked_reason(self, item_guid):
        """Explain an empty result: matched a pool but every filter rejected it.

        An empty `sources_for` is ambiguous on its own - it can mean the item
        is not loot at all, or that a gate removed it. Callers surface this so
        a legitimately unreachable item never reads as a parser failure.
        """
        matched_any = False
        blockers = set()
        for key, info in self.entries.items():
            if not self.entry_matches(key, item_guid):
                continue
            for table_guid, _gen, _w in self.archetype_tables.get(info["archetype"], ()):
                for _preset, _cfg, lc in self.table_configs.get(table_guid, ()):
                    matched_any = True
                    if not self.pool_allows(item_guid, lc["poolFilter"]):
                        blockers.add(self.loot["poolFilters"].get(
                            lc["poolFilter"], {}).get("className", lc["poolFilter"]))
        if not matched_any:
            return "no loot archetype selects this item"
        if blockers:
            return "every container pool filter rejects it: " + ", ".join(sorted(blockers))
        return ""
