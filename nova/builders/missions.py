"""missions.json — contract & scenario-tier catalog (blueprint-granting only).

One entry per CareerContract / Contract that carries <BlueprintRewards>,
plus one synthetic entry per ScenarioProgress tier that grants pools.
Tier entries use the synthetic ClassName
    "<ScenarioClassName>.Tier_<minPoints>"
so consumers iterate `missions.json` uniformly.

References to factions / standings / localities / tags / pools / target
blueprints are by ClassName (resolved against the sibling output files);
GUIDs are exposed as a secondary key on tags only since TagName is not
unique.
"""

# Mission-result-mask index → human-readable enum string (matches
# nova/__main__._MISSION_RESULT_NAMES so RewardSources and missions stay
# in sync).
_MISSION_RESULT_NAMES = ["Success", "FailedTimeout", "FailedDeath", "Aborted", "Failed"]


def _loc(ctx, raw):
    if not raw:
        return ""
    if not raw.startswith("@"):
        return raw
    val = ctx.resolve_name(raw)
    if val and not val.startswith("@"):
        return val
    return ""


def _decode_results(mask):
    return [
        _MISSION_RESULT_NAMES[i]
        for i, b in enumerate(mask)
        if b and i < len(_MISSION_RESULT_NAMES)
    ]


def _build_indices(ctx):
    """Cache lookups: GUID → ClassName for pools/factions/standings/localities
    and BP-GUID → target item ClassName. Also produces template_to_type
    (template GUID → MissionType ClassName) used to resolve a contract's
    @template → MissionType in one hop."""
    pool_cn = {g: r.get("className", "") for g, r in ctx.blueprint_pools.items()}
    fac_cn = {g: r.get("className", "") for g, r in ctx.faction_reputation.items()}
    std_cn = {g: r.get("className", "") for g, r in ctx.standings.items()}
    loc_cn = {g: r.get("className", "") for g, r in ctx.localities.items()}

    # template_guid → mission_type_classname. Two-step join: template
    # carries the MissionType GUID, MissionType carries the ClassName.
    type_cn = {g: r.get("className", "") for g, r in ctx.mission_types.items()}
    template_to_type = {}
    for tpl_guid, tpl in ctx.contract_templates.items():
        mt_guid = tpl.get("missionTypeGuid", "")
        mt_cn = type_cn.get(mt_guid, "")
        if mt_cn:
            template_to_type[tpl_guid] = mt_cn

    # bp_guid → target classname. Walk crafting_blueprints (keyed by target
    # GUID) and pivot. items_by_class[target_cn].guid gives us target GUID;
    # bp.blueprintGuid (added by the parser) gives us the bp record GUID.
    items_by_guid = {
        rec["guid"].lower(): cn
        for cn, rec in ctx.items.items()
        if rec.get("guid")
    }
    bp_to_target = {}
    for target_guid, bp in ctx.crafting_blueprints.items():
        bp_guid = bp.get("blueprintGuid", "").lower()
        if not bp_guid:
            continue
        target_cn = items_by_guid.get(target_guid.lower(), "")
        if target_cn:
            bp_to_target[bp_guid] = target_cn
    return pool_cn, fac_cn, std_cn, loc_cn, bp_to_target, template_to_type


def _resolve_tags(ctx, guids):
    """Project a list of tag GUIDs to [{GUID, TagName}] tuples.
    Missing GUIDs are still emitted (with empty TagName) so consumers
    can flag unresolved tags."""
    out = []
    for g in guids:
        entry = ctx.tags.get(g) or {}
        out.append({
            "GUID": g,
            "TagName": entry.get("TagName", ""),
        })
    return out


def _pool_target_classnames(pool_rec, bp_to_target):
    out = []
    for r in pool_rec.get("rewards", []):
        cn = bp_to_target.get(r.get("bpGuid", "").lower(), "")
        if cn:
            out.append(cn)
    # Deduplicate while preserving order
    seen, dedup = set(), []
    for cn in out:
        if cn not in seen:
            seen.add(cn)
            dedup.append(cn)
    return dedup


def build_missions(ctx) -> list[dict]:
    pool_cn_idx, fac_cn_idx, std_cn_idx, loc_cn_idx, bp_to_target, \
        template_to_type = _build_indices(ctx)

    out = []

    # --- Mekanism A: Contract-bound BlueprintRewards ---
    for c in ctx.contract_rewards:
        title = _loc(ctx, c.get("titleKey", ""))
        desc = _loc(ctx, c.get("descriptionKey", ""))

        bp_rewards_out = []
        for br in c.get("blueprintRewards", []):
            pool_guid = br.get("poolGuid", "").lower()
            pool_rec = ctx.blueprint_pools.get(pool_guid) \
                or ctx.blueprint_pools.get(br.get("poolGuid", ""))
            entry = {
                "PoolClassName": pool_cn_idx.get(pool_guid, "")
                    or pool_cn_idx.get(br.get("poolGuid", ""), ""),
                "PoolChance": br.get("chance", 1.0),
                "OnMissionResults": _decode_results(
                    br.get("missionResultsMask", [])
                ),
            }
            if pool_rec:
                entry["TargetClassNames"] = _pool_target_classnames(
                    pool_rec, bp_to_target,
                )
            bp_rewards_out.append(entry)

        # Class name fallback chain: contract debugName → handler debugName.
        cn = c.get("debugName") or c.get("handlerDebugName") or ""

        entry = {
            "Kind": "Contract",
            "ClassName": cn,
            "Id": c.get("id", ""),
            "Title": title,
            "Description": desc,
            "WorkInProgress": bool(c.get("workInProgress", False)),
            "NotForRelease": bool(c.get("notForRelease", False)),
            "MissionTypeClassName":
                template_to_type.get(c.get("templateGuid", ""), ""),
            "FactionClassName":
                fac_cn_idx.get(c.get("factionReputationGuid", ""), ""),
            "StandingMinClassName":
                std_cn_idx.get(c.get("minStandingGuid", ""), ""),
            "StandingMaxClassName":
                std_cn_idx.get(c.get("maxStandingGuid", ""), ""),
            "LocalityClassName":
                loc_cn_idx.get(c.get("localityGuid", ""), ""),
            "TagFilter": {
                "PositiveTags": _resolve_tags(ctx, c.get("positiveTagGuids", [])),
                "NegativeTags": _resolve_tags(ctx, c.get("negativeTagGuids", [])),
            },
            "BlueprintRewards": bp_rewards_out,
        }
        out.append(entry)

    # --- Mekanism B: ScenarioProgress tiers ---
    for s in ctx.scenario_rewards:
        scen_cn = s.get("scenarioClassName", "")
        prog_text = _loc(ctx, s.get("progressionTextKey", ""))
        faction_cn = fac_cn_idx.get(s.get("factionReputationGuid", ""), "")
        for tier in s.get("tiers", []):
            min_pts = tier.get("minPoints", 0)
            bp_rewards_out = []
            for pool_guid_raw in tier.get("poolGuids", []):
                pool_guid = pool_guid_raw.lower()
                pool_rec = ctx.blueprint_pools.get(pool_guid) \
                    or ctx.blueprint_pools.get(pool_guid_raw)
                pool_cn = pool_cn_idx.get(pool_guid, "") \
                    or pool_cn_idx.get(pool_guid_raw, "")
                entry = {"PoolClassName": pool_cn}
                if pool_rec:
                    entry["TargetClassNames"] = _pool_target_classnames(
                        pool_rec, bp_to_target,
                    )
                bp_rewards_out.append(entry)

            out.append({
                "Kind": "ScenarioTier",
                "ClassName": f"{scen_cn}.Tier_{min_pts}",
                "ScenarioClassName": scen_cn,
                "Title": prog_text,
                "FactionClassName": faction_cn,
                "MinPoints": min_pts,
                "BadgeToAward": tier.get("badgeToAward", "None"),
                "BlueprintRewards": bp_rewards_out,
            })

    out.sort(key=lambda x: (x["Kind"], x["ClassName"]))
    return out
