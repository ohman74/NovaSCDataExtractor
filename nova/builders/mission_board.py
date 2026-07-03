"""mission_board.json — MissionBrokerEntry catalog (job-board / mission-giver
offers players actually see and accept in the PU).

Source: Libs/Foundry/Records/missionbroker/**/*.xml (2,584 files across four
subdirs: jobboard, pu_missioninvites, pu_missions, testmissions). Each file is
a single self-closing-or-nested MissionBrokerEntry.<ClassName> record — read
directly as plain-text XML (same pattern as mineables.py), not via the DCB
parser. `Source` is the first path segment under missionbroker/, i.e. the
subdir the file lives in.

A small side-catalog is also read directly by this module (not exposed on
ctx): Libs/Foundry/Records/reputation/rewards/**/*.xml — ~50
SReputationRewardAmount records (editorName + reputationAmount). Each
mission's per-result reputation reward (missionResultReputationRewards/
.../SReputationAmountParams@reward) is a GUID into *this* catalog, not a raw
number, so it has to be resolved the same way factions/standings/scopes are.

Deliberate simplifications / TODOs for a future pass (all confirmed via a
full 2,584-file scan, not guessed):

- Properties: MissionProperty's nested <value> child is one of 15 distinct
  MissionPropertyValue_* types. Only the 4 "scalar" types are expanded here:
  StringHash / Integer / Float (weighted option lists — Options: [{TextKey,
  Text, Value, Variation, Weight}]) and Boolean (Value). The other 11 types
  (Location, Organization, MissionItem, Tags, AIName, EntitySpawnDescriptions,
  ShipSpawnDescriptions, NPCSpawnDescriptions, CombinedDataSetEntries, Reward,
  TimeTrialRace) carry match-condition / spawn-description subtrees that are
  each their own recursive structure — reduced here to just {"ValueType":
  <type>} as a discriminator. Property dict key is extendedTextToken (falls
  back to missionVariableName, then "Property_N"); 19/2,584 files have a
  colliding key within one entry, where the later MissionProperty wins.
- ReputationRewards: missionResultReputationRewards holds 1, 2, or 3 sibling
  SReputationAmountListParams blocks per entry (966 / 161 / 674 files
  respectively) with *no* attribute anywhere identifying which mission
  result (Success/Failed/Aborted/...) each sibling corresponds to — the scan
  confirmed SReputationAmountListParams carries zero attributes. Emitted as
  an ordered list with a positional "Index" only; mapping that ordinal to a
  named mission result is a game-logic fact this data doesn't encode.
- WantedLevelMin is only emitted when reputationPrerequisites/wantedLevel's
  minValue is nonzero (2,568/2,584 files have minValue=0 — the default).
- AbandonedCooldownTime is present as an attribute on every record (like
  InstanceLifeTime) but only takes effect when canReacceptAfterAbandoning is
  set, so — mirroring the InstanceLifeTime/instanceHasLifeTime gate — it's
  only emitted when that flag is true (304/2,584 files).
- Not surfaced at all this pass: objectiveTokens (854 files), missionFlow
  (849), partialRewardPayout (849), requiredMissions (425), missionTags
  (368), modifiers (309), completionTags (177), requiredCompletedMissionTags
  (153), associatedMissions (29), journalEntriesToAdd/RemoveOnComplete
  (8/5), availableDateSchedule (5), onlyAvailableIfAllMissionsNotAvailable /
  requiredAreaTags / excludedAreaTags (<=3 each) — none were requested for
  this pass. Root scalar attrs outside the requested field list (owner,
  commsChannelName, titleHUD, scheduling/variation knobs, prison/criminal
  gates, personal-cooldown knobs, localityAvailable, invitationMission,
  missionGiverFragmentTags, playerFacingDebugName, linkedMission) are
  likewise omitted.
"""

import os
import xml.etree.ElementTree as ET

from ..utils import safe_bool, safe_float, safe_int

_SOURCE_SUBDIRS = ("jobboard", "pu_missioninvites", "pu_missions", "testmissions")

# MissionPropertyValue_* tag -> (option child tag, value converter). Covers
# the 3 option-list-bearing scalar types; Boolean is handled separately
# since it carries its value directly on the node, not via <options>.
_OPTION_VALUE_TYPES = {
    "MissionPropertyValue_StringHash": ("MissionPropertyValueOption_StringHash", lambda v: v),
    "MissionPropertyValue_Integer": ("MissionPropertyValueOption_Integer", safe_int),
    "MissionPropertyValue_Float": ("MissionPropertyValueOption_Float", safe_float),
}


def _cn(rec_map, guid):
    """Resolve a GUID to its record's className in one of the ctx GUID-keyed
    catalogs (standings / faction_reputation / reputation_scopes / mission_types).
    Tries the lowercase form first (the catalogs' normal key casing), then the
    raw attribute value, mirroring the dual-lookup pattern used elsewhere
    (e.g. missions.py's bp_to_target)."""
    if not guid:
        return ""
    rec = rec_map.get(guid.lower()) or rec_map.get(guid)
    return rec.get("className", "") if rec else ""


def _load_reputation_reward_amounts(ctx):
    """guid -> {className, amount} for SReputationRewardAmount records under
    Records/reputation/rewards/**. Not part of BuildContext — read locally
    since only this builder needs to resolve mission reputation-reward GUIDs
    to their actual point values."""
    base = os.path.join(ctx.cache_dir, "Data", "Libs", "Foundry", "Records",
                         "reputation", "rewards")
    out = {}
    if not os.path.isdir(base):
        return out
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if not fn.endswith(".xml"):
                continue
            try:
                root = ET.parse(os.path.join(dirpath, fn)).getroot()
            except ET.ParseError:
                continue
            if root.get("__type") != "SReputationRewardAmount":
                continue
            guid = (root.get("__ref") or "").lower()
            if not guid:
                continue
            tag = root.tag
            class_name = tag.split(".", 1)[1] if "." in tag else tag
            out[guid] = {
                "className": class_name,
                "amount": safe_int(root.get("reputationAmount", "0")),
            }
    return out


def _property_value(vnode, ctx):
    """Project one MissionProperty's typed <value> child. See module
    docstring for which types are expanded vs. reduced to a discriminator."""
    tag = vnode.tag
    value_type = tag[len("MissionPropertyValue_"):] if tag.startswith("MissionPropertyValue_") else tag
    result = {"ValueType": value_type}

    option_info = _OPTION_VALUE_TYPES.get(tag)
    if option_info:
        option_tag, convert = option_info
        opts = vnode.find("options")
        if opts is not None:
            options_out = []
            for opt in opts.findall(option_tag):
                opt_entry = {}
                text_id = opt.get("textId", "")
                if text_id:
                    opt_entry["TextKey"] = text_id
                    if text_id.startswith("@"):
                        resolved = ctx.resolve_name(text_id)
                        if resolved and resolved != text_id:
                            opt_entry["Text"] = resolved
                raw_value = opt.get("value")
                if raw_value is not None:
                    opt_entry["Value"] = convert(raw_value)
                variation = opt.get("variation")
                if variation is not None:
                    opt_entry["Variation"] = safe_float(variation)
                weighting = opt.get("weighting")
                if weighting is not None:
                    opt_entry["Weight"] = safe_float(weighting)
                options_out.append(opt_entry)
            result["Options"] = options_out
    elif tag == "MissionPropertyValue_Boolean":
        val = vnode.get("value")
        if val is not None:
            result["Value"] = safe_bool(val)

    return result


def _properties(ctx, root):
    out = {}
    props = root.find("properties")
    if props is None:
        return out
    for i, mp in enumerate(props.findall("MissionProperty")):
        key = mp.get("extendedTextToken") or mp.get("missionVariableName") or f"Property_{i}"
        value_parent = mp.find("value")
        if value_parent is None or len(value_parent) == 0:
            continue
        out[key] = _property_value(value_parent[0], ctx)
    return out


def _reputation_requirements(ctx, root):
    out = []
    reqs = root.find("reputationRequirements")
    if reqs is None:
        return out
    for block in reqs.findall("SReputationMissionRequirementsParams"):
        expr = block.find("expression")
        if expr is None:
            continue
        for req in expr.findall("SReputationMissionGiverRequirementParams"):
            faction_guid = req.get("factionReputation", "")
            scope_guid = req.get("reputationScope", "")
            standing_guid = req.get("standing", "")
            out.append({
                "Comparison": req.get("comparison", ""),
                "FactionGUID": faction_guid,
                "FactionClassName": _cn(ctx.faction_reputation, faction_guid),
                "ScopeGUID": scope_guid,
                "ScopeClassName": _cn(ctx.reputation_scopes, scope_guid),
                "StandingGUID": standing_guid,
                "StandingClassName": _cn(ctx.standings, standing_guid),
            })
    return out


def _reputation_rewards(ctx, root, reward_amounts):
    out = []
    block = root.find("missionResultReputationRewards")
    if block is None:
        return out
    for i, lst in enumerate(block.findall("SReputationAmountListParams")):
        amounts_out = []
        amounts = lst.find("reputationAmounts")
        if amounts is not None:
            for amt in amounts.findall("SReputationAmountParams"):
                faction_guid = amt.get("factionReputation", "")
                scope_guid = amt.get("reputationScope", "")
                reward_guid = amt.get("reward", "")
                amt_entry = {
                    "FactionGUID": faction_guid,
                    "FactionClassName": _cn(ctx.faction_reputation, faction_guid),
                    "ScopeGUID": scope_guid,
                    "ScopeClassName": _cn(ctx.reputation_scopes, scope_guid),
                    "RewardGUID": reward_guid,
                }
                reward_rec = reward_amounts.get(reward_guid.lower()) if reward_guid else None
                if reward_rec:
                    amt_entry["RewardClassName"] = reward_rec["className"]
                    amt_entry["RewardAmount"] = reward_rec["amount"]
                amounts_out.append(amt_entry)
        out.append({"Index": i, "Amounts": amounts_out})
    return out


def _build_entry(ctx, root, source, reward_amounts):
    tag = root.tag
    class_name = tag.split(".", 1)[1] if "." in tag else tag

    entry = {
        "ClassName": class_name,
        "GUID": root.get("__ref", ""),
        "Source": source,
        "NotForRelease": safe_bool(root.get("notForRelease")),
    }

    title_key = root.get("title", "")
    if title_key:
        entry["Title"] = ctx.resolve_name(title_key)
        entry["TitleKey"] = title_key

    desc_key = root.get("description", "")
    if desc_key:
        entry["Description"] = ctx.resolve_name(desc_key)
        entry["DescriptionKey"] = desc_key

    giver_key = root.get("missionGiver", "")
    if giver_key:
        entry["MissionGiver"] = ctx.resolve_name(giver_key)

    giver_record = root.get("missionGiverRecord", "")
    if giver_record:
        entry["MissionGiverRecordGUID"] = giver_record

    type_guid = root.get("type", "")
    if type_guid:
        type_out = {"GUID": type_guid}
        type_rec = ctx.mission_types.get(type_guid.lower()) or ctx.mission_types.get(type_guid)
        if type_rec:
            cn = type_rec.get("className", "")
            if cn:
                type_out["Name"] = cn
            localised_key = type_rec.get("localisedTypeName", "")
            if localised_key:
                localised = ctx.resolve_name(localised_key)
                if localised:
                    type_out["LocalisedName"] = localised
        entry["Type"] = type_out

    location_guid = root.get("locationMissionAvailable", "")
    if location_guid:
        entry["LocationGUID"] = location_guid

    module = root.get("missionModule", "")
    if module:
        entry["MissionModule"] = module

    entry["Difficulty"] = safe_int(root.get("missionDifficulty", "0"))
    entry["Lawful"] = safe_bool(root.get("lawfulMission"))
    entry["BuyIn"] = safe_float(root.get("missionBuyInAmount", "0"))
    entry["RefundBuyInOnWithdraw"] = safe_bool(root.get("refundBuyInOnWithdraw"))
    entry["MaxInstances"] = safe_int(root.get("maxInstances", "0"))
    entry["MaxPlayersPerInstance"] = safe_int(root.get("maxPlayersPerInstance", "0"))
    entry["MaxInstancesPerPlayer"] = safe_int(root.get("maxInstancesPerPlayer", "0"))
    entry["CanBeShared"] = safe_bool(root.get("canBeShared"))
    entry["OnceOnly"] = safe_bool(root.get("onceOnly"))
    entry["RequestOnly"] = safe_bool(root.get("requestOnly"))
    entry["AvailableInPrison"] = safe_bool(root.get("availableInPrison"))
    entry["RespawnTime"] = safe_float(root.get("respawnTime", "0"))

    if safe_bool(root.get("instanceHasLifeTime")):
        entry["InstanceLifeTime"] = safe_float(root.get("instanceLifeTime", "0"))

    # See module docstring: gated on canReacceptAfterAbandoning the same way
    # InstanceLifeTime is gated on instanceHasLifeTime.
    if safe_bool(root.get("canReacceptAfterAbandoning")):
        entry["AbandonedCooldownTime"] = safe_float(root.get("abandonedCooldownTime", "0"))

    mission_reward = root.find("missionReward")
    if mission_reward is not None:
        reward = {
            "Amount": safe_float(mission_reward.get("reward", "0")),
            "Max": safe_float(mission_reward.get("max", "0")),
            "PlusBonuses": safe_bool(mission_reward.get("plusBonuses")),
            "Currency": mission_reward.get("currencyType", ""),
        }
        reputation_bonus = mission_reward.get("reputationBonus")
        if reputation_bonus is not None:
            reward["ReputationBonus"] = safe_float(reputation_bonus)
        entry["Reward"] = reward

    deadline = root.find("missionDeadline")
    if deadline is not None:
        entry["Deadline"] = {
            "CompletionTime": safe_float(deadline.get("missionCompletionTime", "0")),
            "AutoEnd": safe_bool(deadline.get("missionAutoEnd")),
            "ResultAfterTimerEnd": deadline.get("missionResultAfterTimerEnd", ""),
        }

    wanted_level = root.find("reputationPrerequisites/wantedLevel")
    if wanted_level is not None:
        entry["WantedLevelMax"] = safe_int(wanted_level.get("maxValue", "0"))
        wanted_min = safe_int(wanted_level.get("minValue", "0"))
        if wanted_min:
            entry["WantedLevelMin"] = wanted_min

    rep_requirements = _reputation_requirements(ctx, root)
    if rep_requirements:
        entry["ReputationRequirements"] = rep_requirements

    rep_rewards = _reputation_rewards(ctx, root, reward_amounts)
    if rep_rewards:
        entry["ReputationRewards"] = rep_rewards

    properties = _properties(ctx, root)
    if properties:
        entry["Properties"] = properties

    return entry


def build_mission_board(ctx):
    """Build mission_board.json from Libs/Foundry/Records/missionbroker."""
    base = os.path.join(ctx.cache_dir, "Data", "Libs", "Foundry", "Records", "missionbroker")
    if not os.path.isdir(base):
        print("  missionbroker records not found")
        return []

    reward_amounts = _load_reputation_reward_amounts(ctx)

    out = []
    for source in _SOURCE_SUBDIRS:
        source_dir = os.path.join(base, source)
        if not os.path.isdir(source_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(source_dir):
            for fn in sorted(filenames):
                if not fn.endswith(".xml"):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    root = ET.parse(full).getroot()
                except ET.ParseError:
                    print(f"  ! mission board parse failed: {full}")
                    continue
                if root.get("__type") != "MissionBrokerEntry":
                    continue
                out.append(_build_entry(ctx, root, source, reward_amounts))

    out.sort(key=lambda e: (e["Source"], e["ClassName"]))
    print(f"  Built {len(out)} mission board entries")
    return out
