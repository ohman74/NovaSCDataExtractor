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
    """Cache lookups: GUID → ClassName for pools/factions/standings/localities/
    scopes/scenarios and BP-GUID → target item ClassName. Also produces
    template_to_type (template GUID → MissionType ClassName) used to resolve
    a contract's @template → MissionType in one hop."""
    pool_cn = {g: r.get("className", "") for g, r in ctx.blueprint_pools.items()}
    fac_cn = {g: r.get("className", "") for g, r in ctx.faction_reputation.items()}
    std_cn = {g: r.get("className", "") for g, r in ctx.standings.items()}
    loc_cn = {g: r.get("className", "") for g, r in ctx.localities.items()}
    scope_cn = {g: r.get("className", "") for g, r in ctx.reputation_scopes.items()}
    # Scenario lookup carries both ClassName and the scheduleEnabled flag so
    # the missions builder can inline `ScheduleEnabled` per required scenario
    # without consumers having to cross-reference scenarios.json.
    scenario_idx = {
        g: {
            "className": r.get("className", ""),
            "scheduleEnabled": bool(r.get("scheduleEnabled", True)),
        }
        for g, r in ctx.mission_scenarios.items()
    }

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
    items_by_guid = ctx.items_by_guid
    bp_to_target = {}
    for target_guid, bp in ctx.crafting_blueprints.items():
        bp_guid = bp.get("blueprintGuid", "").lower()
        if not bp_guid:
            continue
        target_cn = items_by_guid.get(target_guid.lower(), "")
        if target_cn:
            bp_to_target[bp_guid] = target_cn
    return (pool_cn, fac_cn, std_cn, loc_cn, scope_cn, scenario_idx,
            bp_to_target, template_to_type)


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


def _resolve_required_scenarios(scenario_idx, guids):
    """Project required_active_scenario GUIDs to {ClassName, ScheduleEnabled}
    tuples so consumers can tell "blocked in build" from "blocked by player
    progress" without a second join."""
    out = []
    for g in guids:
        rec = scenario_idx.get(g)
        if not rec:
            continue
        out.append({
            "ClassName": rec["className"],
            "ScheduleEnabled": rec["scheduleEnabled"],
        })
    return out


def _resolve_reputation_prereqs(fac_cn_idx, std_cn_idx, scope_cn_idx, reps):
    """Project each ContractPrerequisite_Reputation block to ClassName-keyed
    fields. Empty GUIDs collapse to empty strings — explicit null vs missing
    matters because some Reputation prereqs omit the scope reference."""
    out = []
    for r in reps:
        out.append({
            "FactionClassName": fac_cn_idx.get(r.get("factionReputationGuid", ""), ""),
            "ScopeClassName": scope_cn_idx.get(r.get("scopeGuid", ""), ""),
            "MinStandingClassName": std_cn_idx.get(r.get("minStandingGuid", ""), ""),
            "MaxStandingClassName": std_cn_idx.get(r.get("maxStandingGuid", ""), ""),
            "Exclude": bool(r.get("exclude", False)),
        })
    return out


def _resolve_completed_contract_tag_prereqs(ctx, blocks):
    out = []
    for b in blocks:
        out.append({
            "Tags": _resolve_tags(ctx, b.get("tagGuids", [])),
            "RequiredCount": int(b.get("requiredCount", 0)),
            "ExcludedCount": int(b.get("excludedCount", 0)),
        })
    return out


def build_missions(ctx) -> list[dict]:
    (pool_cn_idx, fac_cn_idx, std_cn_idx, loc_cn_idx, scope_cn_idx,
     scenario_idx, bp_to_target, template_to_type) = _build_indices(ctx)

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

        # Resolve all prereq blocks. Each is a list (possibly empty) — the
        # gating semantics across them is AND. RequiredActiveScenarios sits
        # alongside as the build-level gate; if any has ScheduleEnabled=false
        # the handler is content-blocked regardless of player state.
        prereq_localities = [
            loc_cn_idx.get(g, "") for g in c.get("prereqLocalityGuids", []) if g
        ]
        crime_prereqs = [
            {
                "MinCrimeStat": int(b.get("minCrimeStat", 0)),
                "MaxCrimeStat": int(b.get("maxCrimeStat", 0)),
            }
            for b in c.get("prereqCrimeStats", [])
        ]

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
            "RequiredActiveScenarios": _resolve_required_scenarios(
                scenario_idx, c.get("requiredActiveScenarioGuids", []),
            ),
            "PrereqLocalityClassNames": [n for n in prereq_localities if n],
            "PrereqReputations": _resolve_reputation_prereqs(
                fac_cn_idx, std_cn_idx, scope_cn_idx,
                c.get("prereqReputations", []),
            ),
            "PrereqCompletedContractTags": _resolve_completed_contract_tag_prereqs(
                ctx, c.get("prereqCompletedContractTags", []),
            ),
            "PrereqCrimeStats": crime_prereqs,
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
