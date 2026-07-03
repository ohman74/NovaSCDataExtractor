"""Stream-parse the converted Game2.xml (DataForge) to extract items, vehicles,
manufacturers, and ammo definitions.

The Game2.xml is ~2.4 GB with this structure:
<DataForge>
  <EntityClassDefinition.CLASSNAME __type="EntityClassDefinition" __ref="GUID" ...>
    <Components>...</Components>
  </EntityClassDefinition.CLASSNAME>
  <SCItemManufacturer.NAME __type="SCItemManufacturer" __ref="GUID" Code="XXX">
    <Localization Name="..." />
  </SCItemManufacturer.NAME>
  <AmmoParams.NAME __type="AmmoParams" __ref="GUID" speed="..." lifetime="...">
    <projectileParams><BulletProjectileParams>
      <damage><DamageInfo DamagePhysical="..." DamageEnergy="..." /></damage>
      <penetrationParams basePenetrationDistance="..." />
    </BulletProjectileParams></projectileParams>
  </AmmoParams.NAME>
</DataForge>

We use start+end events and only clear elements after processing to preserve
nested component data.
"""

import os
import json
import time
import xml.etree.ElementTree as ET

from .utils import safe_float, safe_int, safe_bool

# Top-level DataForge record types we extract. Used both to flag "inside a
# record" during the streaming parse (children must not be cleared until the
# record's end handler has run) and as the post-record root-cleanup trigger.
_RECORD_TYPES = frozenset({
    "EntityClassDefinition", "SCItemManufacturer", "AmmoParams",
    "InventoryContainer", "WeaponGimbalModeModifierDef",
    "SIFCSModifiersLegacy", "CraftingBlueprintRecord",
    "ActorProceduralRecoilConfig", "ActorProceduralRecoilModifiers",
    "WeaponProceduralRecoilConfigDef", "WeaponMisfireDef",
    "BlueprintPoolRecord", "FactionReputation",
    "SReputationStandingParams", "SReputationScopeParams",
    "MissionLocality", "ContractGenerator", "ScenarioProgress",
    "MissionType", "ContractTemplate", "MissionScenario",
})


def _extract_prereqs(root):
    """Walk a `<prerequisites>` or `<additionalPrerequisites>` element and
    project each ContractPrerequisite_* child into a typed dict.

    The five observed kinds (PTU 4.8) — every one matters as a gate:
      - Locality           localityAvailable GUID (region/sub-region scope)
      - Location           locationAvailable GUID (specific location entity)
      - LocationProperty   refers to a MissionProperty by name + level
      - Reputation         faction + scope + min/max standing range
      - CompletedContractTags  required completion-tag references + counts
      - CrimeStat          min/max crime stat range

    The caller can pass either a `<prerequisites>` (under
    `defaultAvailability`) or a `<additionalPrerequisites>` (under a contract
    or property override) — both share the same child schema. Returns a
    dict-of-lists shape so it can be merged across handler/contract layers
    without losing the per-kind boundaries.
    """
    out = {
        "localityGuids": [],
        "locationGuids": [],
        "locationProperties": [],
        "reputations": [],
        "completedContractTags": [],
        "crimeStats": [],
    }
    if root is None:
        return out
    for child in root:
        tag = child.tag
        if tag == "ContractPrerequisite_Locality":
            g = child.get("localityAvailable", "")
            if g:
                out["localityGuids"].append(g)
        elif tag == "ContractPrerequisite_Location":
            g = child.get("locationAvailable", "")
            if g:
                out["locationGuids"].append(g)
        elif tag == "ContractPrerequisite_LocationProperty":
            out["locationProperties"].append({
                "propertyVariableName": child.get("propertyVariableName", ""),
                "propertyExtendedTextToken": child.get(
                    "propertyExtendedTextToken", ""
                ),
                "locationLevelType": child.get("locationLevelType", ""),
            })
        elif tag == "ContractPrerequisite_Reputation":
            out["reputations"].append({
                "factionReputationGuid": child.get("factionReputation", ""),
                "scopeGuid": child.get("scope", ""),
                "minStandingGuid": child.get("minStanding", ""),
                "maxStandingGuid": child.get("maxStanding", ""),
                "exclude": safe_bool(child.get("exclude", "0")),
                "includeWhenSharing": safe_bool(
                    child.get("includePrerequisiteWhenSharing", "0")
                ),
            })
        elif tag == "ContractPrerequisite_CompletedContractTags":
            tag_guids = [
                r.get("value", "")
                for r in child.findall("requiredCompletedContractTags/tags/Reference")
            ]
            out["completedContractTags"].append({
                "tagGuids": tag_guids,
                "requiredCount": safe_int(child.get("requiredCountValue", "0")),
                "excludedCount": safe_int(child.get("excludedCountValue", "0")),
                "includeWhenSharing": safe_bool(
                    child.get("includePrerequisiteWhenSharing", "0")
                ),
            })
        elif tag == "ContractPrerequisite_CrimeStat":
            out["crimeStats"].append({
                "minCrimeStat": safe_int(child.get("minCrimeStat", "0")),
                "maxCrimeStat": safe_int(child.get("maxCrimeStat", "0")),
                "includeWhenSharing": safe_bool(
                    child.get("includePrerequisiteWhenSharing", "0")
                ),
            })
    return out


def _merge_prereqs(*sources):
    """Concatenate per-kind lists from multiple prereq buckets in order.
    Handler-level prereqs first, then contract-level additional prereqs."""
    merged = {
        "localityGuids": [],
        "locationGuids": [],
        "locationProperties": [],
        "reputations": [],
        "completedContractTags": [],
        "crimeStats": [],
    }
    for src in sources:
        if not src:
            continue
        for key in merged:
            merged[key].extend(src.get(key, []))
    return merged


def stream_parse_dataforge(xml_path, cache_dir=None):
    """Parse the Game2.xml DataForge file using streaming.

    Returns:
        (items_by_class, vehicles_by_class, guid_to_class, manufacturers, ammo_params)
    """
    # Check cache
    if cache_dir:
        cache_files = {
            "items": os.path.join(cache_dir, "parsed_items.json"),
            "vehicles": os.path.join(cache_dir, "parsed_vehicles.json"),
            "guids": os.path.join(cache_dir, "parsed_guids.json"),
            "manufacturers": os.path.join(cache_dir, "parsed_manufacturers.json"),
            "ammo": os.path.join(cache_dir, "parsed_ammo.json"),
            "inventory": os.path.join(cache_dir, "parsed_inventory.json"),
            "ifcs_modifiers": os.path.join(cache_dir, "parsed_ifcs_modifiers.json"),
            "gimbal_modifiers": os.path.join(cache_dir, "parsed_gimbal_modifiers.json"),
            "crafting": os.path.join(cache_dir, "parsed_crafting.json"),
            "gpp": os.path.join(cache_dir, "parsed_gpp.json"),
            "recoil_configs": os.path.join(cache_dir, "parsed_recoil_configs.json"),
            "recoil_modifiers": os.path.join(cache_dir, "parsed_recoil_modifiers.json"),
            "weapon_recoil_configs": os.path.join(cache_dir, "parsed_weapon_recoil_configs.json"),
            "misfire_defs": os.path.join(cache_dir, "parsed_misfire_defs.json"),
            "blueprint_pools": os.path.join(cache_dir, "parsed_blueprint_pools.json"),
            "faction_reputation": os.path.join(cache_dir, "parsed_faction_reputation.json"),
            "standings": os.path.join(cache_dir, "parsed_standings.json"),
            "reputation_scopes": os.path.join(cache_dir, "parsed_reputation_scopes.json"),
            "localities": os.path.join(cache_dir, "parsed_localities.json"),
            "contract_rewards": os.path.join(cache_dir, "parsed_contract_rewards.json"),
            "scenario_rewards": os.path.join(cache_dir, "parsed_scenario_rewards.json"),
            "mission_types": os.path.join(cache_dir, "parsed_mission_types.json"),
            "contract_templates": os.path.join(cache_dir, "parsed_contract_templates.json"),
            "mission_scenarios": os.path.join(cache_dir, "parsed_mission_scenarios.json"),
        }

        cache_fresh = all(os.path.isfile(f) for f in cache_files.values())
        # Guard against stale caches: a Game2.xml newer than any cache file
        # means a new patch was extracted without clearing parsed_*.json.
        if cache_fresh and xml_path and os.path.isfile(xml_path):
            xml_mtime = os.path.getmtime(xml_path)
            if any(os.path.getmtime(f) < xml_mtime for f in cache_files.values()):
                print("  Cached parse results are older than Game2.xml — reparsing.")
                cache_fresh = False
        if cache_fresh:
            print("  Loading cached parse results...")
            data = {}
            for key, path in cache_files.items():
                with open(path, "r", encoding="utf-8") as f:
                    data[key] = json.load(f)
            print(f"  Loaded {len(data['items'])} items, {len(data['vehicles'])} vehicles, "
                  f"{len(data['guids'])} GUIDs, {len(data['manufacturers'])} manufacturers, "
                  f"{len(data['ammo'])} ammo, {len(data['inventory'])} inventory, "
                  f"{len(data['gimbal_modifiers'])} gimbal modifiers, "
                  f"{len(data['ifcs_modifiers'])} ifcs modifiers, "
                  f"{len(data['crafting'])} crafting, {len(data['gpp'])} gpp, "
                  f"{len(data['recoil_configs'])} recoil configs, "
                  f"{len(data['recoil_modifiers'])} recoil modifiers, "
                  f"{len(data['weapon_recoil_configs'])} weapon recoil cfgs, "
                  f"{len(data['misfire_defs'])} misfire defs, "
                  f"{len(data['blueprint_pools'])} bp pools, "
                  f"{len(data['faction_reputation'])} factions, "
                  f"{len(data['standings'])} standings, "
                  f"{len(data['localities'])} localities, "
                  f"{len(data['contract_rewards'])} contract rewards, "
                  f"{len(data['scenario_rewards'])} scenario rewards, "
                  f"{len(data['mission_types'])} mission types, "
                  f"{len(data['contract_templates'])} contract templates, "
                  f"{len(data['mission_scenarios'])} mission scenarios")
            return (data["items"], data["vehicles"], data["guids"],
                    data["manufacturers"], data["ammo"], data["inventory"],
                    data["gimbal_modifiers"], data["ifcs_modifiers"],
                    data["crafting"], data["gpp"],
                    data["recoil_configs"], data["recoil_modifiers"],
                    data["weapon_recoil_configs"], data["misfire_defs"],
                    data["blueprint_pools"], data["faction_reputation"],
                    data["standings"], data["reputation_scopes"],
                    data["localities"], data["contract_rewards"],
                    data["scenario_rewards"],
                    data["mission_types"], data["contract_templates"],
                    data["mission_scenarios"])

    print(f"  Parsing {xml_path}...")
    size_mb = os.path.getsize(xml_path) / (1024 * 1024)
    print(f"  File size: {size_mb:.0f} MB")
    print("  This will take several minutes...")

    items_by_class = {}
    vehicles_by_class = {}
    guid_to_class = {}
    manufacturers = {}  # guid -> {code, name}
    ammo_params = {}    # guid -> {speed, lifetime, damage, penetration, ...}
    inventory_containers = {}  # guid -> {capacity, ...}
    gimbal_modifiers = {}  # guid -> {fireRateMultiplier: float}
    ifcs_modifiers = {}  # guid -> {numbers: [...], vectors: [...]} from SIFCSModifiersLegacy
    crafting_blueprints = {}  # target-entity-guid -> {tiers: [{craftTime, slots: [...]}]}
    raw_crafting_blueprints = []  # all parsed blueprints; target GUIDs resolved post-loop
                                  # (see _resolve_crafting_targets) once items_by_class is complete
    gpp_records = {}  # gpp-guid -> {propertyName, unitFormat, className}
    recoil_configs = {}  # config-guid -> {setups: [{filterByAimStanceState, modifiersGuid}, ...]}
    recoil_modifiers = {}  # modifiers-guid -> {hands: {...}, aim: {...}, body: {...}, head: {...}}
    weapon_recoil_configs = {}  # guid -> {hands, aim, body, head} per-firing-mode base curves
    misfire_defs = {}  # guid -> {minorDuration, minorCooldown, majorCooldown}
    # Blueprint reward catalog ------------------------------------------------
    # All keyed by record __ref (lowercased? No — keep raw and have consumers
    # normalize at lookup time; matches existing pattern for crafting_blueprints).
    blueprint_pools = {}      # guid -> {className, rewards: [{bp_guid, weight}]}
    faction_reputation = {}    # guid -> {className, displayName, …loc fields, logo, isNPC, lawful}
    standings = {}             # guid -> {className, name, displayName, minReputation, gated}
    reputation_scopes = {}     # guid -> {className, scopeName, displayName, standingGuids[]}
    localities = {}            # guid -> {className, availableLocations[]}
    contract_rewards = []       # flat list — see _parse_contract_generator
    scenario_rewards = []       # flat list — see _parse_scenario_progress
    mission_types = {}          # guid -> {className, localisedTypeName, svgIconPath, iconName}
    contract_templates = {}     # guid -> {className, missionTypeGuid}
    # MissionScenario records keyed by GUID. ContractGeneratorHandler_*
    # references these via <required_active_scenarios><Reference/>; when the
    # scenario's <MissionScenarioSchedule enabled="0" /> ships disabled, the
    # contract handler is content-blocked and its contracts never spawn.
    mission_scenarios = {}      # guid -> {className, name, description,
                                #          autoCreate, trackProgress, scheduleEnabled}

    start = time.time()
    entity_count = 0
    mfr_count = 0
    ammo_count = 0
    total_elements = 0
    inv_count = 0
    in_record = False  # Track if inside any top-level record that needs children preserved

    context = ET.iterparse(xml_path, events=("start", "end"))
    root = None  # DataForge root; records are its direct children

    for event, elem in context:
        total_elements += 1

        if event == "start":
            if root is None:
                root = elem
            if elem.get("__type") in _RECORD_TYPES:
                in_record = True
            continue

        # event == "end"
        if total_elements % 4000000 == 0:
            elapsed = time.time() - start
            print(f"  {total_elements:,} elements | {entity_count} entities | "
                  f"{len(items_by_class)} items | {len(vehicles_by_class)} vehicles | "
                  f"{mfr_count} mfrs | {ammo_count} ammo | {elapsed:.0f}s")

        elem_type = elem.get("__type")
        if elem_type is None:
            # Fast path — the overwhelming majority of end events are
            # non-record elements; skip the record-type dispatch chain.
            if not in_record:
                elem.clear()
            continue

        if elem_type == "EntityClassDefinition":
            entity_count += 1
            in_record = False

            tag = elem.tag
            class_name = tag.split(".", 1)[1] if "." in tag else ""
            if class_name:
                guid = elem.get("__ref", "")
                path = elem.get("__path", "")
                guid_to_class[guid] = class_name

                record = _parse_entity_record(elem, class_name, guid, path)
                if record:
                    if record.get("_is_vehicle"):
                        vehicles_by_class[class_name] = record
                    else:
                        items_by_class[class_name] = record

            elem.clear()

        elif elem_type == "SCItemManufacturer":
            mfr_count += 1
            in_record = False
            guid = elem.get("__ref", "")
            code = elem.get("Code", "")
            loc = elem.find("Localization")
            name = loc.get("Name", "") if loc is not None else ""
            if guid:
                guid_to_class[guid] = elem.tag.split(".", 1)[1] if "." in elem.tag else ""
                manufacturers[guid] = {"code": code, "name": name}
            elem.clear()

        elif elem_type == "AmmoParams":
            ammo_count += 1
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            ammo_class = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                guid_to_class[guid] = ammo_class
                ammo_params[guid] = _parse_ammo_params(elem)
            elem.clear()

        elif elem_type == "InventoryContainer":
            inv_count += 1
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                # Prefer SCentiCargoUnit (1/100 SCU) over others
                cap_elem = elem.find(".//SCentiCargoUnit")
                cap_scale = 0.01 if cap_elem is not None else 1.0
                if cap_elem is None:
                    cap_elem = elem.find(".//SStandardCargoUnit")
                    cap_scale = 1.0
                if cap_elem is None:
                    cap_elem = elem.find(".//SMicroCargoUnit")
                    cap_scale = 1e-6
                capacity = 0
                if cap_elem is not None:
                    raw = safe_float(cap_elem.get("standardCargoUnits",
                                     cap_elem.get("centiSCU",
                                     cap_elem.get("microSCU", "0"))))
                    capacity = raw * cap_scale

                # Capture interiorDimensions for CargoGrid Width/Height/Depth calc
                interior = None
                dim_elem = elem.find("interiorDimensions")
                if dim_elem is not None:
                    interior = {
                        "x": safe_float(dim_elem.get("x", "0")),
                        "y": safe_float(dim_elem.get("y", "0")),
                        "z": safe_float(dim_elem.get("z", "0")),
                    }

                # Fallback: compute SCU from dimensions grid-fit
                if not capacity and interior:
                    dx, dy, dz = interior["x"], interior["y"], interior["z"]
                    if dx and dy and dz:
                        capacity = int(dx / 1.25) * int(dy / 1.25) * int(dz / 1.25)

                # Capture min/max permitted item sizes (for CargoGrid MinContainerSize/MaxContainerSize)
                def _vec3(name):
                    e = elem.find(".//" + name)
                    if e is None:
                        return None
                    return {
                        "x": safe_float(e.get("x", "0")),
                        "y": safe_float(e.get("y", "0")),
                        "z": safe_float(e.get("z", "0")),
                    }
                min_size = _vec3("minPermittedItemSize")
                max_size = _vec3("maxPermittedItemSize")

                entry = {"capacity": capacity}
                if interior:
                    entry["interiorDimensions"] = interior
                if min_size:
                    entry["minPermittedItemSize"] = min_size
                if max_size:
                    entry["maxPermittedItemSize"] = max_size
                inventory_containers[guid] = entry
            elem.clear()

        elif elem_type == "WeaponGimbalModeModifierDef":
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                # Extract fireRateMultiplier from SWeaponModifierParams > weaponStats
                mod_elem = elem.find(".//SWeaponModifierParams/weaponStats")
                if mod_elem is not None:
                    frm = safe_float(mod_elem.get("fireRateMultiplier", "1"))
                    if frm != 1.0:
                        gimbal_modifiers[guid] = {"fireRateMultiplier": frm}
            elem.clear()

        elif elem_type == "CraftingBlueprintRecord":
            # Crafting recipes for FPS weapons, armour, ships. Structure:
            # CraftingBlueprintRecord -> blueprint/CraftingBlueprint
            #   -> processSpecificData/CraftingProcess_Creation entityClass=GUID
            #   -> tiers/CraftingBlueprintTier/recipe/CraftingRecipe/costs
            #     -> craftTime/TimeValue_Partitioned
            #     -> mandatoryCost/CraftingCost_Select/options/CraftingCost_Select
            #        (each is a slot with nameInfo + GPP modifiers + resource cost)
            in_record = False
            guid = elem.get("__ref", "")
            bp = _parse_crafting_blueprint(elem)
            if bp:
                # Collect every blueprint now; the target item GUID is resolved
                # after the parse completes (see _resolve_crafting_targets),
                # because detecting CIG's shared-entityClass copy-paste defect
                # needs the full set, and the className fallback needs the
                # fully-populated items_by_class. The blueprint record's own
                # GUID is preserved as bp["blueprintGuid"] so downstream code
                # can join pool references (which point at the *blueprint* GUID,
                # not the target item GUID) back to the target.
                bp["blueprintGuid"] = guid
                raw_crafting_blueprints.append(bp)
            elem.clear()

        elif elem_type == "CraftingGameplayPropertyDef":
            # Self-closing record: maps GUID -> human-readable property name
            # ("GPP_Weapon_Damage", "@StatName_GPP_Weapon_Damage", "@StatUnits_Percent")
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                gpp_records[guid] = {
                    "className": cls,
                    "propertyName": elem.get("propertyName", ""),
                    "unitFormat": elem.get("unitFormat", ""),
                }
            elem.clear()

        elif elem_type == "ActorProceduralRecoilConfig":
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                setups = []
                for setup in elem.findall(".//actorProceduralRecoilSetup/ActorProceduralRecoilSetup"):
                    setups.append({
                        "aimStance": setup.get("filterByAimStanceState", "Any"),
                        "stance": setup.get("filterByStanceState", "Any"),
                        "pose": setup.get("filterByPoseState", "Any"),
                        "motionSpeed": setup.get("filterByMotionSpeed", "Any"),
                        "modifiersGuid": setup.get("actorProceduralRecoilModifiers", ""),
                    })
                if setups:
                    recoil_configs[guid] = {"setups": setups}
            elem.clear()

        elif elem_type == "ActorProceduralRecoilModifiers":
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                rec = _parse_recoil_modifiers(elem)
                if rec:
                    recoil_modifiers[guid] = rec
            elem.clear()

        elif elem_type == "WeaponProceduralRecoilConfigDef":
            # Per-firing-mode base recoil curves (hands/aim/body/head). Reached
            # via fireActions[].@recoil GUID. ActorProceduralRecoilModifiers
            # multiply on top of these absolute values.
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                rec = _parse_weapon_recoil_config(elem)
                if rec:
                    weapon_recoil_configs[guid] = rec
            elem.clear()

        elif elem_type == "WeaponMisfireDef":
            # Per-fire-type jam mechanics. Shared across weapons with the same
            # fire type — only 5 records total (burst/rapid/single/charge/beam).
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                misfire_defs[guid] = {
                    "minorDuration": safe_float(elem.get("minorMisfireDuration", "0")),
                    "minorCooldown": safe_float(elem.get("minorMisfireCooldown", "0")),
                    "majorCooldown": safe_float(elem.get("majorMisfireCooldown", "0")),
                }
            elem.clear()

        elif elem_type == "BlueprintPoolRecord":
            # Pool of blueprint references with relative weights. Refed by
            # contracts (BlueprintRewards/@blueprintPool) and scenario tiers.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                rewards = []
                for r in elem.findall("blueprintRewards/BlueprintReward"):
                    rewards.append({
                        "bpGuid": r.get("blueprintRecord", ""),
                        "weight": safe_float(r.get("weight", "1")),
                    })
                blueprint_pools[guid] = {"className": cls, "rewards": rewards}
            elem.clear()

        elif elem_type == "FactionReputation":
            # Reputation-system faction (what contracts reference via
            # ContractGeneratorHandler_*/@factionReputation). Carries the
            # localized DisplayName plus rich metadata under propertiesBB
            # (Headquarters / Leadership / Area / Focus / …).
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                entry = {
                    "className": cls,
                    "displayName": elem.get("displayName", ""),
                    "logo": elem.get("logo", ""),
                    "isNPC": safe_bool(elem.get("isNPC", "0")),
                    # Lawful from className suffix — there is no factionType
                    # field on FactionReputation; CIG encodes it in the name.
                    "lawful": "_Lawful_" in cls,
                }
                # Extra metadata strings live under propertiesBB.
                for prop in elem.findall("propertiesBB/SReputationContextBBPropertyParams"):
                    pname = prop.get("name", "")
                    if not pname:
                        continue
                    val_elem = prop.find("dynamicProperty/SBBDynamicPropertyLocString")
                    if val_elem is None:
                        continue
                    raw = val_elem.get("value", "")
                    # Map CIG's property names → cleaner keys.
                    key_map = {
                        "entityDescription": "description",
                        "entityHeadquarters": "headquarters",
                        "entityFounded": "founded",
                        "entityLeadership": "leadership",
                        "entityArea": "area",
                        "entityFocus": "focus",
                    }
                    out_key = key_map.get(pname)
                    if out_key and raw:
                        entry[out_key] = raw
                faction_reputation[guid] = entry
            elem.clear()

        elif elem_type == "SReputationStandingParams":
            # One rank step within a reputation scope (e.g. "Neutral",
            # "Elite Contractor"). Referenced from contracts via
            # @minStanding / @maxStanding.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                standings[guid] = {
                    "className": cls,
                    "name": elem.get("name", ""),
                    "displayName": elem.get("displayName", ""),
                    "minReputation": safe_int(elem.get("minReputation", "0")),
                    "gated": safe_bool(elem.get("gated", "0")),
                }
            elem.clear()

        elif elem_type == "SReputationScopeParams":
            # Container for a list of standings (a "rep ladder"). Contract
            # generators reference it via @reputationScope.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                standing_refs = [
                    r.get("value", "")
                    for r in elem.findall("standingMap/standings/Reference")
                ]
                reputation_scopes[guid] = {
                    "className": cls,
                    "scopeName": elem.get("scopeName", ""),
                    "displayName": elem.get("displayName", ""),
                    "standingGuids": standing_refs,
                }
            elem.clear()

        elif elem_type == "MissionLocality":
            # Region/sub-region locality (Nyx, Pyro, Pyro_RegionA, …). The
            # className suffix IS the region name; CIG does not localize it.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                locs = [
                    r.get("value", "")
                    for r in elem.findall("availableLocations/Reference")
                ]
                localities[guid] = {
                    "className": cls,
                    "availableLocations": locs,
                }
            elem.clear()

        elif elem_type == "ContractGenerator":
            # Top-level contract definition file. Walk all handlers and the
            # contracts within, extracting only those that carry
            # <BlueprintRewards> entries (everything else is mission state
            # we don't need for the blueprint catalog).
            in_record = False
            tag = elem.tag
            gen_cls = tag.split(".", 1)[1] if "." in tag else ""
            for handler in elem.findall("generators/*"):
                handler_cls = handler.tag  # e.g. ContractGeneratorHandler_Career
                faction_rep_guid = handler.get("factionReputation", "")
                rep_scope_guid = handler.get("reputationScope", "")
                # Content-blocker / dynamic-event gate. Handler only spawns
                # contracts when ALL referenced MissionScenario records are
                # active. ContentBlocker_Scenario is the most common entry —
                # a kill-switch CIG ships with enabled="0" to keep unreleased
                # content out of the build until flipped on.
                required_scenario_guids = [
                    r.get("value", "")
                    for r in handler.findall(
                        "required_active_scenarios/Reference"
                    )
                ]
                handler_prereqs = _extract_prereqs(
                    handler.find("defaultAvailability/prerequisites")
                )
                # Legacy single-locality slot kept for backwards compat with
                # missions.json' `LocalityClassName` field. Pick the first
                # handler-level locality GUID, if any.
                locality_guid = (
                    handler_prereqs["localityGuids"][0]
                    if handler_prereqs["localityGuids"] else ""
                )

                for contract in handler.findall("contracts/*"):
                    rewards_nodes = contract.findall(
                        "contractResults/contractResults/BlueprintRewards"
                    )
                    if not rewards_nodes:
                        continue

                    contract_tag = contract.tag  # CareerContract / Contract
                    contract_cls = contract.get("debugName", "")
                    title_key = ""
                    desc_key = ""
                    for sp in contract.findall(
                        "paramOverrides/stringParamOverrides/ContractStringParam"
                    ):
                        if sp.get("param") == "Title":
                            title_key = sp.get("value", "")
                        elif sp.get("param") == "Description":
                            desc_key = sp.get("value", "")

                    # Tag-filter from MissionLocation_BP property override
                    pos_tags, neg_tags = [], []
                    for mp in contract.findall(
                        "paramOverrides/propertyOverrides/MissionProperty"
                    ):
                        if mp.get("missionVariableName") != "MissionLocation_BP":
                            continue
                        for term in mp.findall(
                            "value/MissionPropertyValue_Location/matchConditions/"
                            "DataSetMatchCondition_TagSearch/tagSearch/TagSearchTerm"
                        ):
                            for ref in term.findall("positiveTags/Reference"):
                                pos_tags.append(ref.get("value", ""))
                            for ref in term.findall("negativeTags/Reference"):
                                neg_tags.append(ref.get("value", ""))

                    # Contract-level additionalPrerequisites — direct children
                    # of the contract element only (the deeply nested
                    # location-conditional `additionalPrerequisites` inside
                    # propertyOverrides apply only when a location property
                    # resolves to a specific value and are out of scope for
                    # the top-level availability gate).
                    contract_prereqs = _extract_prereqs(
                        contract.find("additionalPrerequisites")
                    )
                    prereqs = _merge_prereqs(handler_prereqs, contract_prereqs)

                    bp_rewards = []
                    for br in rewards_nodes:
                        results_mask = [
                            safe_bool(b.get("value", "0"))
                            for b in br.findall("missionResults/Bool")
                        ]
                        bp_rewards.append({
                            "chance": safe_float(br.get("chance", "1")),
                            "poolGuid": br.get("blueprintPool", ""),
                            "missionResultsMask": results_mask,
                        })

                    contract_rewards.append({
                        "generatorClassName": gen_cls,
                        "handlerType": handler_cls,
                        "handlerDebugName": handler.get("debugName", ""),
                        "contractType": contract_tag,  # CareerContract / Contract
                        "id": contract.get("id", ""),
                        "debugName": contract_cls,
                        "templateGuid": contract.get("template", ""),
                        "minStandingGuid": contract.get("minStanding", ""),
                        "maxStandingGuid": contract.get("maxStanding", ""),
                        "notForRelease": safe_bool(contract.get("notForRelease", "0")),
                        "workInProgress": safe_bool(contract.get("workInProgress", "0")),
                        "titleKey": title_key,
                        "descriptionKey": desc_key,
                        "factionReputationGuid": faction_rep_guid,
                        "reputationScopeGuid": rep_scope_guid,
                        "localityGuid": locality_guid,
                        "positiveTagGuids": pos_tags,
                        "negativeTagGuids": neg_tags,
                        "requiredActiveScenarioGuids": required_scenario_guids,
                        "prereqLocalityGuids": prereqs["localityGuids"],
                        "prereqLocationGuids": prereqs["locationGuids"],
                        "prereqLocationProperties": prereqs["locationProperties"],
                        "prereqReputations": prereqs["reputations"],
                        "prereqCompletedContractTags": prereqs["completedContractTags"],
                        "prereqCrimeStats": prereqs["crimeStats"],
                        "blueprintRewards": bp_rewards,
                    })
            elem.clear()

        elif elem_type == "MissionType":
            # Self-closing record at Records/missiontype/**. The class-name
            # suffix is the canonical type ID (BountyHunter, Collection,
            # Hauling, …); LocalisedTypeName is the @LOC key.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            if guid:
                mission_types[guid] = {
                    "className": cls,
                    "localisedTypeName": elem.get("LocalisedTypeName", ""),
                    "svgIconPath": elem.get("svgIconPath", ""),
                    "iconName": elem.get("IconName", ""),
                }
            elem.clear()

        elif elem_type == "ContractTemplate":
            # Mission-type carrier — contracts reference a template by GUID
            # (CareerContract@template / Contract@template). The template's
            # contractDisplayInfo/ContractDisplayInfo@type points at a
            # MissionType record. Other ContractTemplate fields (display
            # strings, contractProperties) carry @LOC_UNINITIALIZED on most
            # records and are not surfaced.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            mission_type_guid = ""
            disp = elem.find("contractDisplayInfo/ContractDisplayInfo")
            if disp is not None:
                mission_type_guid = disp.get("type", "")
            if guid:
                contract_templates[guid] = {
                    "className": cls,
                    "missionTypeGuid": mission_type_guid,
                }
            elem.clear()

        elif elem_type == "ScenarioProgress":
            # Dynamic-event progression (e.g. RoX_ScenarioProgress for
            # Xenothreat 2). Pools are tier-gated by minPoints, no per-roll
            # chance — reaching the tier grants the pool.
            in_record = False
            tag = elem.tag
            scen_cls = tag.split(".", 1)[1] if "." in tag else ""
            for fac_tier in elem.findall(
                "factionRewardTiers/SScenarioProgressRewardsTiers"
            ):
                faction_rep_guid = fac_tier.get("faction", "")
                for prog in fac_tier.findall("tierProgressions/STierProgressions"):
                    progression_text = prog.get("progressionText", "")
                    tiers_out = []
                    for tier in prog.findall("tierRewards/STierReward"):
                        pool_guids = [
                            r.get("value", "")
                            for r in tier.findall("blueprintPool/Reference")
                        ]
                        if not pool_guids:
                            continue
                        tiers_out.append({
                            "minPoints": safe_int(tier.get("minPoints", "0")),
                            "badgeToAward": tier.get("badgeToAward", "None"),
                            "poolGuids": pool_guids,
                        })
                    if tiers_out:
                        scenario_rewards.append({
                            "scenarioClassName": scen_cls,
                            "factionReputationGuid": faction_rep_guid,
                            "progressionTextKey": progression_text,
                            "tiers": tiers_out,
                        })
            elem.clear()

        elif elem_type == "MissionScenario":
            # Build-gate / dynamic-event scenario. ContractGeneratorHandler_*
            # references these via <required_active_scenarios> — the handler
            # only spawns contracts when every referenced scenario is active.
            # The schedule's `enabled` flag is the on/off switch CIG ships;
            # ContentBlocker_Scenario in particular ships with enabled="0"
            # to keep unreleased contract families out of the live build.
            in_record = False
            guid = elem.get("__ref", "")
            tag = elem.tag
            cls = tag.split(".", 1)[1] if "." in tag else ""
            schedule_enabled = True
            sched_node = elem.find("schedule/MissionScenarioSchedule")
            if sched_node is not None:
                # `enabled` defaults to 1 when absent — only treat the
                # attribute as authoritative when present, matches CIG's
                # implicit "scheduled if not otherwise stated" behavior.
                schedule_enabled = safe_bool(sched_node.get("enabled", "1"))
            if guid:
                mission_scenarios[guid] = {
                    "className": cls,
                    "name": elem.get("name", ""),
                    "description": elem.get("description", ""),
                    "autoCreate": safe_bool(elem.get("auto_create", "0")),
                    "trackProgress": safe_bool(elem.get("track_progress", "0")),
                    "scheduleEnabled": schedule_enabled,
                }
            elem.clear()

        elif elem_type == "SIFCSModifiersLegacy":
            # Flight-blade modifier records (FlightBlade_HND/SPD): items
            # reference these via IFCSParams.modifiersLegacy GUID. The
            # record's positional `numbers` and `vectors` are the actual
            # delta values applied to the base IFCS stats — replaces
            # className-suffix + hardcoded constants.
            in_record = False
            guid = elem.get("__ref", "")
            if guid:
                nums = []
                for n in elem.findall("numbers/SIFCSModifierNumber"):
                    nums.append({
                        "value": safe_float(n.get("value", "0")),
                        "type": n.get("type", ""),
                    })
                vecs = []
                for v in elem.findall("vectors/SIFCSModifierVector"):
                    val = v.find("value")
                    vecs.append({
                        "type": v.get("type", ""),
                        "x": safe_float(val.get("x", "0")) if val is not None else 0.0,
                        "y": safe_float(val.get("y", "0")) if val is not None else 0.0,
                        "z": safe_float(val.get("z", "0")) if val is not None else 0.0,
                    })
                if nums or vecs:
                    ifcs_modifiers[guid] = {"numbers": nums, "vectors": vecs}
            elem.clear()

        elif not in_record:
            elem.clear()

        # A finished record leaves its cleared shell attached to the root's
        # child list — drop those so a 2.4 GB parse doesn't accumulate
        # millions of empty Elements.
        if root is not None and elem_type in _RECORD_TYPES:
            root.clear()

    elapsed = time.time() - start
    print(f"  Parse complete: {total_elements:,} elements, {entity_count} entities, "
          f"{mfr_count} manufacturers, {ammo_count} ammo, {inv_count} inventory in {elapsed:.0f}s")
    print(f"  Items: {len(items_by_class)}, Vehicles: {len(vehicles_by_class)}, GUIDs: {len(guid_to_class)}")

    # Resolve external loadout file references (SItemPortLoadoutXMLParams).
    # CargoBay items on Constellations and similar ships point at
    # cache/Data/Scripts/Loadouts/.../*.xml files instead of inlining their
    # entries. Expand those _loadoutPath markers into real entries.
    cache_root = os.path.dirname(os.path.dirname(xml_path)) if xml_path else None
    _resolve_external_loadouts(items_by_class, cache_root)
    _resolve_external_loadouts(vehicles_by_class, cache_root)

    # Key crafting blueprints by the GUID of the item they produce, repairing
    # CIG's shared-entityClass copy-paste defect along the way. Must run after
    # the parse loop so items_by_class is complete for className resolution.
    crafting_blueprints = _resolve_crafting_targets(raw_crafting_blueprints,
                                                    items_by_class)

    # Cache results
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        print("  Caching parse results...")
        cache_data = {
            "parsed_items.json": items_by_class,
            "parsed_vehicles.json": vehicles_by_class,
            "parsed_guids.json": guid_to_class,
            "parsed_manufacturers.json": manufacturers,
            "parsed_ammo.json": ammo_params,
            "parsed_inventory.json": inventory_containers,
            "parsed_gimbal_modifiers.json": gimbal_modifiers,
            "parsed_ifcs_modifiers.json": ifcs_modifiers,
            "parsed_crafting.json": crafting_blueprints,
            "parsed_gpp.json": gpp_records,
            "parsed_recoil_configs.json": recoil_configs,
            "parsed_recoil_modifiers.json": recoil_modifiers,
            "parsed_weapon_recoil_configs.json": weapon_recoil_configs,
            "parsed_misfire_defs.json": misfire_defs,
            "parsed_blueprint_pools.json": blueprint_pools,
            "parsed_faction_reputation.json": faction_reputation,
            "parsed_standings.json": standings,
            "parsed_reputation_scopes.json": reputation_scopes,
            "parsed_localities.json": localities,
            "parsed_contract_rewards.json": contract_rewards,
            "parsed_scenario_rewards.json": scenario_rewards,
            "parsed_mission_types.json": mission_types,
            "parsed_contract_templates.json": contract_templates,
            "parsed_mission_scenarios.json": mission_scenarios,
        }
        for filename, data in cache_data.items():
            with open(os.path.join(cache_dir, filename), "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
        print("  Done")

    return (items_by_class, vehicles_by_class, guid_to_class, manufacturers,
            ammo_params, inventory_containers, gimbal_modifiers, ifcs_modifiers,
            crafting_blueprints, gpp_records, recoil_configs, recoil_modifiers,
            weapon_recoil_configs, misfire_defs,
            blueprint_pools, faction_reputation, standings, reputation_scopes,
            localities, contract_rewards, scenario_rewards,
            mission_types, contract_templates, mission_scenarios)


def _parse_recoil_modifiers(elem):
    """Parse ActorProceduralRecoilModifiers — multipliers applied to base recoil curves.

    Spec mirrors the spreadsheet's Recoil tab: per-aim-state hands/aim/body/head
    parameters that drive procedural recoil. We capture the top-level scalar
    multipliers and skip the deeply nested curve modifiers (which are 3D vector
    modifiers per axis — too verbose for the catalogue and rarely meaningful
    independent of the underlying recoil curves).
    """
    result = {}

    hands = elem.find("actorProceduralHandsRecoilModifiers")
    if hands is not None:
        h = {
            "decay": safe_float(hands.get("decay", "1")),
            "endDecay": safe_float(hands.get("endDecay", "1")),
            "fireRecoilTime": safe_float(hands.get("fireRecoilTime", "1")),
            "fireRecoilStrengthFirst": safe_float(hands.get("fireRecoilStrengthFirst", "1")),
            "fireRecoilStrength": safe_float(hands.get("fireRecoilStrength", "1")),
            "angleRecoilStrength": safe_float(hands.get("angleRecoilStrength", "1")),
            "useRandomRotation": safe_bool(hands.get("useRandomRotation", "0")),
            "randomness": safe_float(hands.get("randomness", "0")),
            "randomnessBackPush": safe_float(hands.get("randomnessBackPush", "0")),
            "frontalOscillationRotation": safe_float(hands.get("frontalOscillationRotation", "0")),
            "frontalOscillationStrength": safe_float(hands.get("frontalOscillationStrength", "0")),
            "frontalOscillationDecay": safe_float(hands.get("frontalOscillationDecay", "0")),
            "frontalOscillationRandomness": safe_float(hands.get("frontalOscillationRandomness", "0")),
        }
        rot = hands.find("rotation")
        if rot is not None:
            h["rotation"] = {
                "x": safe_float(rot.get("x", "0")),
                "y": safe_float(rot.get("y", "0")),
                "z": safe_float(rot.get("z", "0")),
            }
        result["hands"] = h

    aim = elem.find("actorProceduralAimRecoilModifiers")
    if aim is not None:
        a = {
            "pullLeftPercentage": safe_float(aim.get("pull_left_percentage", "0")),
            "randomPitch": safe_float(aim.get("random_pitch", "0")),
            "randomYaw": safe_float(aim.get("random_yaw", "0")),
            "decay": safe_float(aim.get("decay", "1")),
            "endDecay": safe_float(aim.get("end_decay", "1")),
            "recoilTime": safe_float(aim.get("recoil_time", "1")),
            "delay": safe_float(aim.get("delay", "0")),
        }
        for key, attr in (("max", "max"), ("shotKickFirst", "shot_kick_first"), ("shotKick", "shot_kick")):
            v = aim.find(attr)
            if v is not None:
                a[key] = {"x": safe_float(v.get("x", "0")), "y": safe_float(v.get("y", "0"))}
        result["aim"] = a

    body = elem.find("actorProceduralBodyRecoilModifiers")
    if body is not None:
        result["body"] = {
            "hipsPushForce": safe_float(body.get("hipsPushForce", "1")),
            "hipsDampStrength": safe_float(body.get("hipsDampStrength", "1")),
            "hipsDampStrengthEnd": safe_float(body.get("hipsDampStrengthEnd", "1")),
            "spinePushForceFirst": safe_float(body.get("spinePushForceFirst", "1")),
            "spinePushForce": safe_float(body.get("spinePushForce", "1")),
            "spineDampStrength": safe_float(body.get("spineDampStrength", "1")),
            "spineDampStrengthEnd": safe_float(body.get("spineDampStrengthEnd", "1")),
        }

    head = elem.find("actorProceduralHeadRecoilModifiers")
    if head is not None:
        result["head"] = {
            "frequency": safe_float(head.get("frequency", "1")),
            "smoothFactor": safe_float(head.get("smoothFactor", "1")),
            "frequencyNoiseFactor": safe_float(head.get("frequencyNoiseFactor", "1")),
            "maxDistance": safe_float(head.get("maxDistance", "1")),
            "translationNoise": safe_float(head.get("translationNoise", "1")),
            "rotationNoise": safe_float(head.get("rotationNoise", "1")),
            "minSpeed": safe_float(head.get("minSpeed", "1")),
            "minScale": safe_float(head.get("minScale", "1")),
            "maxSpeed": safe_float(head.get("maxSpeed", "1")),
            "maxScale": safe_float(head.get("maxScale", "1")),
        }

    return result


def _parse_weapon_recoil_config(elem):
    """Parse WeaponProceduralRecoilConfigDef — per-firing-mode base recoil curves.

    Captures top-level scalars + curve max-values + min/max limits. Skips the
    deeply nested Bezier control-point arrays (8–17 points per curve, 30+
    curves per record) — too verbose for the catalogue and rarely meaningful
    independent of an in-game playback engine.
    """
    result = {}

    hands = elem.find("weaponProceduralHandsRecoil")
    if hands is not None:
        h = {
            "decay": safe_float(hands.get("decay", "0")),
            "endDecay": safe_float(hands.get("endDecay", "0")),
            "fireRecoilTime": safe_float(hands.get("fireRecoilTime", "0")),
            "fireRecoilStrengthFirst": safe_float(hands.get("fireRecoilStrengthFirst", "0")),
            "fireRecoilStrength": safe_float(hands.get("fireRecoilStrength", "0")),
            "angleRecoilStrength": safe_float(hands.get("angleRecoilStrength", "0")),
            "useRandomRotation": safe_bool(hands.get("useRandomRotation", "0")),
            "randomness": safe_float(hands.get("randomness", "0")),
            "randomnessBackPush": safe_float(hands.get("randomnessBackPush", "0")),
            "frontalOscillationRotation": safe_float(hands.get("frontalOscillationRotation", "0")),
            "frontalOscillationStrength": safe_float(hands.get("frontalOscillationStrength", "0")),
            "frontalOscillationDecay": safe_float(hands.get("frontalOscillationDecay", "0")),
            "frontalOscillationRandomness": safe_float(hands.get("frontalOscillationRandomness", "0")),
        }
        rot = hands.find("rotation")
        if rot is not None:
            h["rotation"] = {
                "x": safe_float(rot.get("x", "0")),
                "y": safe_float(rot.get("y", "0")),
                "z": safe_float(rot.get("z", "0")),
            }
        cr = hands.find("curveRecoil")
        if cr is not None:
            curve_block = {
                "totalRecoilTime": safe_float(cr.get("totalRecoilTime", "0")),
                "limitTransitionTime": safe_float(cr.get("limitTransitionTime", "0")),
                "minDecayTime": safe_float(cr.get("minDecayTime", "0")),
                "maxDecayTime": safe_float(cr.get("maxDecayTime", "0")),
            }
            for key, xml_key in (("position", "positionCurves"), ("rotation", "rotationCurves")):
                c = cr.find(xml_key)
                if c is not None:
                    cb = {
                        "xMaxValue": safe_float(c.get("xMaxValue", "0")),
                        "yMaxValue": safe_float(c.get("yMaxValue", "0")),
                        "zMaxValue": safe_float(c.get("zMaxValue", "0")),
                    }
                    for limit_key in ("minLimits", "maxLimits"):
                        l = c.find(limit_key)
                        if l is not None:
                            cb[limit_key] = {
                                "x": safe_float(l.get("x", "0")),
                                "y": safe_float(l.get("y", "0")),
                                "z": safe_float(l.get("z", "0")),
                            }
                    curve_block[key] = cb
            ro = cr.find("rotationOffset")
            if ro is not None:
                curve_block["rotationOffset"] = {
                    "x": safe_float(ro.get("x", "0")),
                    "y": safe_float(ro.get("y", "0")),
                    "z": safe_float(ro.get("z", "0")),
                }
            h["curveRecoil"] = curve_block
        result["hands"] = h

    aim = elem.find("weaponProceduralAimRecoil")
    if aim is not None:
        a = {
            "pullLeftPercentage": safe_float(aim.get("pull_left_percentage", "0")),
            "randomPitch": safe_float(aim.get("random_pitch", "0")),
            "randomYaw": safe_float(aim.get("random_yaw", "0")),
            "decay": safe_float(aim.get("decay", "0")),
            "endDecay": safe_float(aim.get("end_decay", "0")),
            "recoilTime": safe_float(aim.get("recoil_time", "0")),
            "delay": safe_float(aim.get("delay", "0")),
        }
        for key, attr in (("max", "max"), ("shotKickFirst", "shot_kick_first"),
                          ("shotKick", "shot_kick")):
            v = aim.find(attr)
            if v is not None:
                a[key] = {"x": safe_float(v.get("x", "0")),
                          "y": safe_float(v.get("y", "0"))}
        cr = aim.find("curveAimRecoil")
        if cr is not None:
            ac = {
                "yawMaxDegrees": safe_float(cr.get("yawMaxDegrees", "0")),
                "pitchMaxDegrees": safe_float(cr.get("pitchMaxDegrees", "0")),
                "rollMaxDegrees": safe_float(cr.get("rollMaxDegrees", "0")),
                "maxFireTime": safe_float(cr.get("maxFireTime", "0")),
                "recoilSmoothTime": safe_float(cr.get("recoilSmoothTime", "0")),
                "decayStartTime": safe_float(cr.get("decayStartTime", "0")),
                "minDecayTime": safe_float(cr.get("minDecayTime", "0")),
                "maxDecayTime": safe_float(cr.get("maxDecayTime", "0")),
            }
            for limit_key in ("minLimits", "maxLimits"):
                l = cr.find(limit_key)
                if l is not None:
                    ac[limit_key] = {
                        "x": safe_float(l.get("x", "0")),
                        "y": safe_float(l.get("y", "0")),
                        "z": safe_float(l.get("z", "0")),
                    }
            nc = cr.find("noiseCurves")
            if nc is not None:
                ac["noise"] = {
                    "yawNoiseMaxValue": safe_float(nc.get("yawNoiseMaxValue", "0")),
                    "pitchNoiseMaxValue": safe_float(nc.get("pitchNoiseMaxValue", "0")),
                    "rollNoiseMaxValue": safe_float(nc.get("rollNoiseMaxValue", "0")),
                }
            a["curveAimRecoil"] = ac
        result["aim"] = a

    body = elem.find("weaponProceduralBodyRecoil")
    if body is not None:
        result["body"] = {
            "hipsPushForce": safe_float(body.get("hipsPushForce", "0")),
            "hipsDampStrength": safe_float(body.get("hipsDampStrength", "0")),
            "hipsDampStrengthEnd": safe_float(body.get("hipsDampStrengthEnd", "0")),
            "spinePushForceFirst": safe_float(body.get("spinePushForceFirst", "0")),
            "spinePushForce": safe_float(body.get("spinePushForce", "0")),
            "spineDampStrength": safe_float(body.get("spineDampStrength", "0")),
            "spineDampStrengthEnd": safe_float(body.get("spineDampStrengthEnd", "0")),
        }

    head = elem.find("weaponProceduralHeadRecoil")
    if head is not None:
        result["head"] = {
            "frequency": safe_float(head.get("frequency", "0")),
            "smoothFactor": safe_float(head.get("smoothFactor", "0")),
            "frequencyNoiseFactor": safe_float(head.get("frequencyNoiseFactor", "0")),
            "maxDistance": safe_float(head.get("maxDistance", "0")),
            "phase": safe_float(head.get("phase", "0")),
            "translationNoise": safe_float(head.get("translationNoise", "0")),
            "rotationNoise": safe_float(head.get("rotationNoise", "0")),
            "usePerlinNoise": safe_bool(head.get("usePerlinNoise", "0")),
            "referenceSpeed": safe_float(head.get("referenceSpeed", "0")),
            "minSpeed": safe_float(head.get("minSpeed", "0")),
            "minScale": safe_float(head.get("minScale", "0")),
            "maxSpeed": safe_float(head.get("maxSpeed", "0")),
            "maxScale": safe_float(head.get("maxScale", "0")),
        }
        ht = head.find("translation")
        if ht is not None:
            result["head"]["translation"] = {
                "x": safe_float(ht.get("x", "0")),
                "y": safe_float(ht.get("y", "0")),
                "z": safe_float(ht.get("z", "0")),
            }
        hr = head.find("rotation")
        if hr is not None:
            result["head"]["rotation"] = {
                "x": safe_float(hr.get("x", "0")),
                "y": safe_float(hr.get("y", "0")),
                "z": safe_float(hr.get("z", "0")),
            }

    return result if result else None


def _parse_crafting_blueprint(elem):
    """Parse a CraftingBlueprintRecord into
    {targetGuid, blueprintClassName, tiers: [...]}.

    `blueprintClassName` is the record's own class (the element-tag suffix,
    e.g. `BP_CRAFT_COOL_TYDT_S02_IceBox_SCItem`); _resolve_crafting_targets
    uses it as a fallback when the entityClass GUID is unreliable.

    Returns None for non-creation blueprints (dismantle, salvage, etc.) and
    blueprints without a target entityClass.
    """
    proc = elem.find(".//processSpecificData/CraftingProcess_Creation")
    if proc is None:
        return None
    target_guid = proc.get("entityClass", "")
    if not target_guid:
        return None
    tag = elem.tag
    blueprint_class = tag.split(".", 1)[1] if "." in tag else ""

    tiers = []
    for tier in elem.findall(".//tiers/CraftingBlueprintTier"):
        tier_data = {"slots": []}

        ct = tier.find(".//craftTime/TimeValue_Partitioned")
        if ct is not None:
            tier_data["craftTime"] = {
                "days": safe_int(ct.get("days", "0")),
                "hours": safe_int(ct.get("hours", "0")),
                "minutes": safe_int(ct.get("minutes", "0")),
                "seconds": safe_int(ct.get("seconds", "0")),
            }

        for slot in tier.findall(".//mandatoryCost/CraftingCost_Select/options/CraftingCost_Select"):
            slot_data = _parse_blueprint_slot(slot)
            if slot_data:
                tier_data["slots"].append(slot_data)

        if tier_data["slots"] or tier_data.get("craftTime"):
            tiers.append(tier_data)

    if not tiers:
        return None
    return {"targetGuid": target_guid,
            "blueprintClassName": blueprint_class,
            "tiers": tiers}


def _resolve_crafting_targets(raw_blueprints, items_by_class):
    """Key parsed creation-blueprints by the GUID of the item they produce.

    The producing item is normally CraftingProcess_Creation.entityClass (a
    GUID). But CIG's data carries a copy-paste defect: several distinct
    blueprints sometimes share ONE entityClass GUID — e.g.
    BP_CRAFT_COOL_TYDT_S02_IceBox, _HeatSink and _NightFall all carry
    Cryo-Star SL's GUID. When N>=2 blueprints point at the same GUID, that
    GUID cannot be the true target for all of them.

    LAST-RESORT className fallback, gated on a collision (positive evidence the
    structural GUID is wrong): CIG names every recipe
    `BP_CRAFT_<targetItemClassName>` — verified to agree with entityClass for
    1526/1560 (97.8%) of the corpus. For colliding blueprints only, strip the
    `BP_CRAFT_` prefix and, if the result is a real item className whose GUID
    differs from the shared one, re-key to it. Non-colliding blueprints always
    keep their entityClass GUID — this never blanket-overrides the structural
    field. Removable once CIG stops duplicating entityClass values.

    This is a live in-game bug — the wrong blueprint is granted in-game too —
    tracked at Issue Council STARC-209920.
    """
    from collections import Counter

    class_to_guid = {cn.lower(): rec["guid"]
                     for cn, rec in items_by_class.items() if rec.get("guid")}

    # How many distinct blueprints claim each entityClass GUID as their target.
    target_counts = Counter(bp["targetGuid"].lower()
                            for bp in raw_blueprints if bp.get("targetGuid"))

    result = {}
    remapped = []
    for bp in raw_blueprints:
        target = bp.pop("targetGuid", "")
        bp_class = bp.pop("blueprintClassName", "")
        if not target:
            continue
        # Only second-guess the GUID when it collides with another blueprint.
        if target_counts[target.lower()] >= 2 and bp_class[:9].upper() == "BP_CRAFT_":
            derived = bp_class[9:]  # strip "BP_CRAFT_" -> intended item className
            derived_guid = class_to_guid.get(derived.lower(), "")
            if derived_guid and derived_guid.lower() != target.lower():
                remapped.append((bp_class, target, derived_guid))
                target = derived_guid
        # First-seen wins on any remaining tie (matches prior behaviour).
        if target not in result:
            result[target] = bp

    if remapped:
        print(f"  Crafting: re-keyed {len(remapped)} blueprint(s) off shared "
              f"entityClass GUIDs (CIG copy-paste defect) via BP_CRAFT_ className")
    return result


def _parse_blueprint_slot(slot_elem):
    """Parse one CraftingCost_Select slot (FRAME/WIRING/LENSES/etc.)."""
    name_info = slot_elem.find("nameInfo")
    slot_name = name_info.get("debugName", "") if name_info is not None else ""
    slot_display = name_info.get("displayName", "") if name_info is not None else ""

    modifiers = []
    for mod in slot_elem.findall(".//CraftingGameplayPropertyModifierCommon"):
        gpp_guid = mod.get("gameplayPropertyRecord", "")
        # Two value-range tag types coexist in CIG's crafting data:
        # - ValueRange_Linear: float multiplier (modifierAtStart/-End).
        #   Used for percentage-style buffs (Integrity 0.8x → 1.2x).
        # - ValueRange_LinearIntegerAdditive: integer delta added to the
        #   base property (additiveModifierAtStart/-End). Used for discrete
        #   step changes (Power Pips +2, Magazine size +1, etc.).
        # findall on `_Linear` does NOT match `_LinearIntegerAdditive`
        # (ET tag matching is exact), so both must be queried.
        for vr in mod.findall(".//CraftingGameplayPropertyModifierValueRange_Linear"):
            modifiers.append({
                "gppGuid": gpp_guid,
                "kind": "multiplier",
                "startQuality": safe_int(vr.get("startQuality", "0")),
                "endQuality": safe_int(vr.get("endQuality", "0")),
                "modifierAtStart": safe_float(vr.get("modifierAtStart", "1")),
                "modifierAtEnd": safe_float(vr.get("modifierAtEnd", "1")),
            })
        for vr in mod.findall(".//CraftingGameplayPropertyModifierValueRange_LinearIntegerAdditive"):
            modifiers.append({
                "gppGuid": gpp_guid,
                "kind": "additive",
                "startQuality": safe_int(vr.get("startQuality", "0")),
                "endQuality": safe_int(vr.get("endQuality", "0")),
                "modifierAtStart": safe_int(vr.get("additiveModifierAtStart", "0")),
                "modifierAtEnd": safe_int(vr.get("additiveModifierAtEnd", "0")),
            })

    costs = []
    options = slot_elem.find("options")
    if options is not None:
        for opt in list(options):
            tag = opt.tag
            poly = opt.get("__polymorphicType", "")
            if tag.endswith("CraftingCost_Resource") or poly == "CraftingCost_Resource":
                qty = 0.0
                qty_elem = opt.find(".//SStandardCargoUnit")
                if qty_elem is not None:
                    qty = safe_float(qty_elem.get("standardCargoUnits", "0"))
                else:
                    qty_elem = opt.find(".//SCentiCargoUnit")
                    if qty_elem is not None:
                        qty = safe_float(qty_elem.get("centiSCU", "0")) * 0.01
                costs.append({
                    "type": "Resource",
                    "guid": opt.get("resource", ""),
                    "quantity": qty,
                })
            elif tag.endswith("CraftingCost_Item") or poly == "CraftingCost_Item":
                costs.append({
                    "type": "Item",
                    "guid": opt.get("entityClass", ""),
                    "quantity": safe_int(opt.get("quantity", "1")),
                })

    return {
        "name": slot_name,
        "displayName": slot_display,
        "modifiers": modifiers,
        "costs": costs,
    }


def _parse_ammo_params(elem):
    """Parse an AmmoParams record for projectile data."""
    result = {
        "speed": safe_float(elem.get("speed")),
        "lifetime": safe_float(elem.get("lifetime")),
        "size": safe_int(elem.get("size")),
    }

    # P2b: top-level impulseScale (force-reaction strength multiplier)
    imp_scale = elem.get("impulseScale")
    if imp_scale is not None:
        result["impulseScale"] = safe_float(imp_scale)

    # P2a: Projectile physics (mass, airResistance, disableGravity, etc.)
    # Drives bullet drop calculation. Most laser projectiles set disableGravity=1
    # and are unaffected by airResistance — ballistic projectiles are the inverse.
    phys_ctrl = elem.find(".//SEntityParticlePhysicsControllerParams")
    if phys_ctrl is not None:
        result["projectilePhysics"] = {
            "mass": safe_float(phys_ctrl.get("Mass", "0")),
            "airResistance": safe_float(phys_ctrl.get("airResistance", "0")),
            "disableGravity": safe_bool(phys_ctrl.get("disableGravity", "0")),
            "radius": safe_float(phys_ctrl.get("radius", "0")),
            "thickness": safe_float(phys_ctrl.get("thickness", "0")),
            "length": safe_float(phys_ctrl.get("length", "0")),
            "pierceability": safe_int(phys_ctrl.get("pierceability", "0")),
            "accThrust": safe_float(phys_ctrl.get("accThrust", "0")),
        }

    # Projectile-type variants: BulletProjectileParams, TachyonProjectileParams, etc.
    # All share the same damage/penetration sub-structure.
    projectile_types = ("BulletProjectileParams", "TachyonProjectileParams",
                         "LaserProjectileParams", "MissileProjectileParams")
    for p_type in projectile_types:
        for bullet in elem.iter(p_type):
            # Damage
            dmg = bullet.find("damage")
            if dmg is not None:
                dmg_info = dmg.find("DamageInfo")
                if dmg_info is None:
                    for child in dmg:
                        dmg_info = child
                        break
                if dmg_info is not None:
                    result["damage"] = {
                        "physical": safe_float(dmg_info.get("DamagePhysical")),
                        "energy": safe_float(dmg_info.get("DamageEnergy")),
                        "distortion": safe_float(dmg_info.get("DamageDistortion")),
                        "thermal": safe_float(dmg_info.get("DamageThermal")),
                        "biochemical": safe_float(dmg_info.get("DamageBiochemical")),
                        "stun": safe_float(dmg_info.get("DamageStun")),
                    }

            # Detonation damage
            det = bullet.find("detonationParams")
            if det is not None:
                det_dmg = det.find(".//DamageInfo")
                if det_dmg is not None:
                    result["detonationDamage"] = {
                        "physical": safe_float(det_dmg.get("DamagePhysical")),
                        "energy": safe_float(det_dmg.get("DamageEnergy")),
                        "distortion": safe_float(det_dmg.get("DamageDistortion")),
                    }
                # Explosion radius from ExplosionParams attributes (minRadius/maxRadius)
                exp_params = det.find(".//ExplosionParams")
                if exp_params is None:
                    exp_params = det.find(".//explosionParams")
                if exp_params is not None:
                    min_r = safe_float(exp_params.get("minRadius", "0"))
                    max_r = safe_float(exp_params.get("maxRadius", "0"))
                    if min_r:
                        result["explosionRadiusMin"] = min_r
                    if max_r:
                        result["explosionRadiusMax"] = max_r

            # Penetration
            pen = bullet.find("penetrationParams")
            if pen is not None:
                result["penetration"] = {
                    "basePenetrationDistance": safe_float(pen.get("basePenetrationDistance")),
                    "nearRadius": safe_float(pen.get("nearRadius")),
                    "farRadius": safe_float(pen.get("farRadius")),
                }

            # Damage drop (distance-based damage falloff)
            drop = bullet.find(".//BulletDamageDropParams")
            if drop is not None:
                drop_result = {}
                for field, key in [("damageDropMinDistance", "minDistance"),
                                   ("damageDropPerMeter", "dropPerMeter"),
                                   ("damageDropMinDamage", "minDamage")]:
                    field_elem = drop.find(field)
                    if field_elem is not None:
                        dmg_info = field_elem.find("DamageInfo")
                        if dmg_info is not None:
                            vals = {}
                            for dt in ["Physical", "Energy", "Distortion", "Thermal",
                                       "Biochemical", "Stun"]:
                                v = safe_float(dmg_info.get(f"Damage{dt}"))
                                if v:
                                    vals[dt] = v
                            if vals:
                                drop_result[key] = vals
                if drop_result:
                    result["damageDrop"] = drop_result

            # Pierceability — armor-tier penetration (P2c) + max thickness
            pierce = bullet.find("pierceabilityParams")
            if pierce is not None:
                result["maxPenetrationThickness"] = safe_float(pierce.get("maxPenetrationThickness"))
                # Per-tier damage falloff (Light/Medium/Heavy armor) — drives the
                # spreadsheet's DmgRes calculations.
                falloffs = {
                    "level1": safe_float(pierce.get("damageFalloffLevel1", "0")),
                    "level2": safe_float(pierce.get("damageFalloffLevel2", "0")),
                    "level3": safe_float(pierce.get("damageFalloffLevel3", "0")),
                }
                if any(falloffs.values()):
                    result["pierceability"] = falloffs

            # Impulse falloff (P2b) — Force Reaction tab in spreadsheet.
            imp_fall = bullet.find("impulseFalloffParams/BulletImpulseFalloffParams")
            if imp_fall is None:
                imp_fall = bullet.find(".//BulletImpulseFalloffParams")
            if imp_fall is not None:
                result["impulseFalloff"] = {
                    "minDistance": safe_float(imp_fall.get("minDistance", "0")),
                    "dropFalloff": safe_float(imp_fall.get("dropFalloff", "0")),
                    "maxFalloff": safe_float(imp_fall.get("maxFalloff", "0")),
                }

    # CounterMeasure params (in CounterMeasureProjectileParams, not BulletProjectileParams)
    for cm_type in ["CounterMeasureChaffParams", "CounterMeasureFlareParams"]:
        cm = elem.find(f".//{cm_type}")
        if cm is not None:
            result["counterMeasure"] = {
                "StartInfrared": safe_float(cm.get("StartInfrared", "0")),
                "EndInfrared": safe_float(cm.get("EndInfrared", "0")),
                "StartElectromagnetic": safe_float(cm.get("StartElectromagnetic", "0")),
                "EndElectromagnetic": safe_float(cm.get("EndElectromagnetic", "0")),
                "StartCrossSection": safe_float(cm.get("StartCrossSection", "0")),
                "EndCrossSection": safe_float(cm.get("EndCrossSection", "0")),
                "StartDecibel": safe_float(cm.get("StartDecibel", "0")),
                "EndDecibel": safe_float(cm.get("EndDecibel", "0")),
            }
            result["counterMeasureType"] = "Chaff" if "Chaff" in cm_type else "Flare"
            break

    return result


def _parse_entity_record(elem, class_name, guid, path):
    """Parse an EntityClassDefinition element into a structured record."""
    record = {
        "className": class_name,
        "guid": guid,
        "path": path,
        "_is_vehicle": False,
    }

    # Capture top-level entity tag GUIDs (used for archetype/role lookup).
    # Structure: <EntityClassDefinition.X> <tags> <Reference value="GUID"/> ... </tags>
    tags_elem = elem.find("tags")
    if tags_elem is not None:
        tag_guids = [r.get("value", "") for r in tags_elem.findall("Reference")]
        if tag_guids:
            record["entityTagGuids"] = tag_guids

    # Capture StaticEntityClassData (has insurance, display params)
    static_data = elem.find("StaticEntityClassData")
    if static_data is not None:
        for child in static_data:
            poly = child.get("__polymorphicType", child.tag)
            if poly == "SEntityInsuranceProperties":
                ins = child.find("shipInsuranceParams")
                if ins is not None:
                    record["insurance"] = {
                        "baseWaitTimeMinutes": safe_float(ins.get("baseWaitTimeMinutes")),
                        "mandatoryWaitTimeMinutes": safe_float(ins.get("mandatoryWaitTimeMinutes")),
                        "baseExpeditingFee": safe_float(ins.get("baseExpeditingFee")),
                    }

    components_elem = elem.find("Components")
    if components_elem is None:
        return None

    components = {}
    attach_def = None

    for comp in components_elem:
        poly_type = comp.get("__polymorphicType", comp.tag)

        if poly_type == "SAttachableComponentParams":
            attach_def_elem = comp.find("AttachDef")
            if attach_def_elem is not None:
                attach_def = _parse_attach_def(attach_def_elem)
                record["attachDef"] = attach_def

        elif poly_type == "VehicleComponentParams":
            record["_is_vehicle"] = True
            record["vehicle"] = _parse_vehicle_params(comp)

        elif poly_type == "SHealthComponentParams":
            components["health"] = _parse_health_params(comp)

        elif poly_type == "SAmmoContainerComponentParams":
            components["ammo"] = {
                "maxAmmoCount": safe_int(comp.get("maxAmmoCount")),
                "initialAmmoCount": safe_int(comp.get("initialAmmoCount")),
                "ammoParamsRecord": comp.get("ammoParamsRecord", ""),
                "allowAmmoRepool": comp.get("allowAmmoRepool", "0") == "1",
            }

        elif poly_type == "EntityComponentPowerConnection":
            components["power"] = _parse_power_connection(comp)

        elif poly_type == "EntityComponentHeatConnection":
            components["heat"] = _parse_heat_connection(comp)

        elif poly_type == "SItemPortContainerComponentParams":
            components["ports"] = _parse_port_container(comp)
            # Ship-level PortTags (the tags this ship offers to its ports —
            # ports' `requiredTags="$X"` matches against these). The base
            # impl XML's `itemPortTags` is sometimes stale for variants
            # (F7C Mk2 uses ANVL_Hornet_F7A.xml impl whose itemPortTags
            # says "Anvil Hornet F7A", but the entity XML correctly
            # declares "ANVL_Hornet_Base ANVL_Hornet_Mk2 ANVL_Hornet_F7C_Mk2").
            ship_port_tags = comp.get("PortTags", "")
            if ship_port_tags:
                components["shipPortTags"] = ship_port_tags

        elif poly_type == "SEntityComponentDefaultLoadoutParams":
            loadout_entries = _parse_default_loadout(comp)
            if loadout_entries:
                components["defaultLoadout"] = loadout_entries

        elif poly_type == "SCItemWeaponComponentParams":
            components["weapon"] = _parse_weapon_params(comp)

        elif poly_type == "SCItemShieldGeneratorParams":
            components["shield"] = _parse_shield_params(comp)

        elif poly_type == "SCItemCoolerParams":
            components["cooler"] = _parse_cooler_params(comp)

        elif poly_type == "SCItemPowerPlantParams":
            components["powerPlant"] = _parse_power_plant_params(comp)

        elif poly_type == "SCItemQuantumDriveParams":
            components["quantumDrive"] = _parse_quantum_drive_params(comp)

        elif poly_type == "SCItemVehicleArmorParams":
            components["armor"] = _parse_armor_params(comp)

        elif poly_type == "SCItemMissileParams":
            components["missile"] = _parse_missile_params(comp)

        elif poly_type == "SCItemClothingParams":
            # Character clothing / armor-core stats. Carries environmental
            # resistance values (temperature, radiation) and the
            # Flight.gForceResistance bonus (added on PTU 4.8 — values
            # range −0.5..+1.0 across the catalogue; chest/undersuit items
            # provide the bulk of the bonus, summed across worn pieces and
            # capped at 1.0 in-game). Emitted as `components["clothing"]`
            # with typed float values (matches the other explicit handlers'
            # convention; replaces the generic SCItemClothingParams fallback).
            clothing = {}
            tr = comp.find("TemperatureResistance")
            if tr is not None:
                clothing["temperature"] = {
                    "min": safe_float(tr.get("MinResistance", "0")),
                    "max": safe_float(tr.get("MaxResistance", "0")),
                }
            rr = comp.find("RadiationResistance")
            if rr is not None:
                clothing["radiation"] = {
                    "maxCapacity": safe_float(rr.get("MaximumRadiationCapacity", "0")),
                    "dissipationRate": safe_float(rr.get("RadiationDissipationRate", "0")),
                }
            fl = comp.find("Flight")
            if fl is not None:
                # Single attribute today (gForceResistance). Stored as a
                # block so we can extend without breaking consumers.
                clothing["flight"] = {
                    "gForceResistance": safe_float(fl.get("gForceResistance", "0")),
                }
            if clothing:
                components["clothing"] = clothing

        elif poly_type == "SEntityPhysicsControllerParams":
            phys = comp.find(".//SEntityRigidPhysicsControllerParams")
            if phys is None:
                phys = comp.find("PhysType")
                if phys is not None:
                    for sub in phys:
                        if sub.get("Mass") is not None:
                            phys = sub
                            break
            if phys is not None:
                components["physics"] = {"mass": safe_float(phys.get("Mass"))}

            # Heat controller from temperature element
            temp = comp.find(".//temperature")
            if temp is not None:
                hc = {
                    "enableHeat": temp.get("enable") == "1",
                    "initialTemperature": safe_float(temp.get("initialTemperature")),
                }
                # Cooling equalization
                ceq = temp.find(".//CoolingEqualizationRateAtTemperatureDifference")
                if ceq is not None:
                    hc["coolingEqualization"] = {
                        "equalizationRate": safe_float(ceq.get("coolingEqualizationRate")),
                        "temperatureDifference": safe_float(ceq.get("temperatureDifference")),
                    }
                # Signature
                sig = temp.find("signatureParams")
                if sig is not None:
                    hc["signature"] = {
                        "enableSignature": sig.get("enable") == "1",
                        "minTemperatureForIR": safe_float(sig.get("minimumTemperatureForIR")),
                        "temperatureToIR": safe_float(sig.get("temperatureToIR")),
                    }
                # Overheat / item resource params
                irp = temp.find("itemResourceParams")
                if irp is not None:
                    hc["minOperatingTemperature"] = safe_float(irp.get("minOperatingTemperature"))
                    hc["minCoolingTemperature"] = safe_float(irp.get("minCoolingTemperature"))
                    hc["overheat"] = {
                        "enableOverheat": irp.get("enableOverheat") == "1",
                        "maxTemperature": safe_float(irp.get("overheatTemperature")),
                        "warningTemperature": safe_float(irp.get("overheatWarningTemperature")),
                        "recoveryTemperature": safe_float(irp.get("overheatRecoveryTemperature")),
                    }
                    hc["poweredAmbientCoolingMultiplier"] = safe_float(irp.get("poweredAmbientCoolingMultiplier"))

                components["heatController"] = hc

        else:
            # Capture ALL other components generically
            components[poly_type] = _elem_to_dict(comp)

    if components:
        record["components"] = components

    if not attach_def and not record.get("_is_vehicle") and not components:
        return None

    return record


def _parse_attach_def(elem):
    """Parse SItemDefinition (AttachDef) element."""
    result = {
        "type": elem.get("Type", ""),
        "subType": elem.get("SubType", ""),
        "size": safe_int(elem.get("Size")),
        "grade": safe_int(elem.get("Grade")),
        "tags": elem.get("Tags", ""),
        "requiredTags": elem.get("RequiredTags", ""),
    }

    manufacturer = elem.get("Manufacturer", "")
    if manufacturer and manufacturer != "00000000-0000-0000-0000-000000000000":
        result["manufacturerGuid"] = manufacturer

    loc_elem = elem.find("Localization")
    if loc_elem is not None:
        result["name"] = loc_elem.get("Name", "")
        result["shortName"] = loc_elem.get("ShortName", "")
        result["description"] = loc_elem.get("Description", "")

    # Volume from inventory occupancy
    vol_elem = elem.find(".//SMicroCargoUnit")
    if vol_elem is not None:
        result["volume"] = safe_int(vol_elem.get("microSCU"))

    return result


def _parse_vehicle_params(comp):
    """Parse VehicleComponentParams."""
    result = {
        "vehicleName": comp.get("vehicleName", ""),
        "vehicleDescription": comp.get("vehicleDescription", ""),
        "vehicleCareer": comp.get("vehicleCareer", ""),
        "vehicleRole": comp.get("vehicleRole", ""),
        "crewSize": safe_int(comp.get("crewSize")),
        "movementClass": comp.get("movementClass", ""),
        "isGravlevVehicle": safe_bool(comp.get("isGravlevVehicle")),
        "manufacturerGuid": comp.get("manufacturer", ""),
        "vehicleDefinition": comp.get("vehicleDefinition", ""),
        # Inline Modification name (e.g. "Zeus_CL", "F7C_Mk2"). Selects an
        # inline <Modification> block from the impl XML to apply per-variant
        # overrides (skipPart toggles, port renames, size changes).
        "modification": comp.get("modification", ""),
        # Penetration multipliers for Hull.PenetrationDamageMultiplier
        "fusePenetrationDamageMultiplier": safe_float(comp.get("fusePenetrationDamageMultiplier", "1")),
        "componentPenetrationDamageMultiplier": safe_float(comp.get("componentPenetrationDamageMultiplier", "1")),
    }

    # Bounding box = dimensions
    bbox = comp.find("maxBoundingBoxSize")
    if bbox is not None:
        result["dimensions"] = {
            "x": safe_float(bbox.get("x")),
            "y": safe_float(bbox.get("y")),
            "z": safe_float(bbox.get("z")),
        }

    return result


def _parse_health_params(comp):
    """Parse SHealthComponentParams with full damage resistance data."""
    result = {
        "health": safe_float(comp.get("Health")),
    }

    # Damage resistances
    resistances = comp.find(".//DamageResistance")
    if resistances is not None:
        dm = {}
        for res_type in ["Physical", "Energy", "Distortion", "Thermal", "Biochemical", "Stun"]:
            res_elem = resistances.find(f"{res_type}Resistance")
            if res_elem is not None:
                dm[res_type.lower()] = safe_float(res_elem.get("Multiplier"))
        if dm:
            result["damageMultipliers"] = dm

    return result


def _parse_weapon_params(comp):
    """Parse SCItemWeaponComponentParams with firing data."""
    result = {}

    # Gimbal mode modifier record GUID (references WeaponGimbalModeModifierDef)
    gimbal_guid = comp.get("gimbalModeModifierRecord", "")
    if gimbal_guid and gimbal_guid != "00000000-0000-0000-0000-000000000000":
        result["gimbalModeModifierRecord"] = gimbal_guid

    # Recoil config record GUID (FPS weapons — references ActorProceduralRecoilConfig)
    recoil_guid = comp.get("actorProceduralRecoilConfig", "")
    if recoil_guid and recoil_guid != "00000000-0000-0000-0000-000000000000":
        result["actorProceduralRecoilConfig"] = recoil_guid

    # Geometry / skin tag — non-empty value identifies a visual skin variant
    # (e.g. "Black02", "Tint01", "Collector01"). Empty on base items. Used by
    # cosmetic-variant detection to find the visual identifier without
    # parsing the className.
    geom_tags = comp.get("geometryTags", "")
    if geom_tags:
        result["geometryTags"] = geom_tags

    # Ammo repool params (FPS weapons — SWeaponAmmoRepoolParams)
    repool = comp.find(".//SWeaponAmmoRepoolParams")
    if repool is None:
        repool = comp.find("ammoRepoolParams")
    if repool is not None:
        result["ammoRepool"] = {
            "bulletsPerSecond": safe_float(repool.get("bulletsPerSecond")),
            "unstowMagDuration": safe_float(repool.get("unstowMagDuration")),
            "fullMagMergeDuration": safe_float(repool.get("fullMagMergeDuration")),
        }

    # Aim modifier spread (FPS weapons — from aimAction > aimModifier > weaponStats > spreadModifier)
    # Applies to all firing modes uniformly.
    aim_action = comp.find("aimAction")
    if aim_action is not None:
        aim_spread = aim_action.find(".//aimModifier/SWeaponModifierParams/weaponStats/spreadModifier")
        if aim_spread is not None:
            result["aimSpreadModifier"] = {
                "min": safe_float(aim_spread.get("minMultiplier", "0")),
                "max": safe_float(aim_spread.get("maxMultiplier", "0")),
                "firstAttack": safe_float(aim_spread.get("firstAttackMultiplier", "0")),
                "attack": safe_float(aim_spread.get("attackMultiplier", "0")),
                "decay": safe_float(aim_spread.get("decayMultiplier", "0")),
            }

        # Top-level ADS attributes — zoomScale + zoomTime drive the ADS UX.
        # Also capture optional depth-of-field settings.
        aim_simple = aim_action.find("SWeaponActionAimSimpleParams")
        if aim_simple is not None:
            zoom_scale = aim_simple.get("zoomScale")
            zoom_time = aim_simple.get("zoomTime")
            if zoom_scale is not None or zoom_time is not None:
                aim = {
                    "zoomScale": safe_float(zoom_scale) if zoom_scale is not None else 1.0,
                    "zoomTime": safe_float(zoom_time) if zoom_time is not None else 0.0,
                    "toggleZoomOverride": safe_bool(aim_simple.get("toggleZoomOverride", "0")),
                }
                dof = aim_simple.find("dofSettings/SWeaponAimDofSettings")
                if dof is not None:
                    aim["dof"] = {
                        "focalDistance": safe_float(dof.get("focalDistance", "0")),
                        "focalRange": safe_float(dof.get("focalRange", "0")),
                        "fstop": safe_float(dof.get("fstop", "0")),
                    }
                result["aim"] = aim

    # Weapon regen consumer params (ammo pool / capacitor)
    regen_elem = comp.find(".//SWeaponRegenConsumerParams")
    if regen_elem is not None:
        result["regenConsumer"] = {
            "requestedRegenPerSec": safe_float(regen_elem.get("requestedRegenPerSec")),
            "regenerationCooldown": safe_float(regen_elem.get("regenerationCooldown")),
            "regenerationCostPerBullet": safe_float(regen_elem.get("regenerationCostPerBullet")),
            "requestedAmmoLoad": safe_float(regen_elem.get("requestedAmmoLoad")),
            "maxAmmoLoad": safe_float(regen_elem.get("maxAmmoLoad")),
            "maxRegenPerSec": safe_float(regen_elem.get("maxRegenPerSec")),
        }

    # Connection params (power modes, heat)
    conn = comp.find("connectionParams")
    if conn is not None:
        result["heatRateOnline"] = safe_float(conn.get("heatRateOnline"))
        result["powerActiveCooldown"] = safe_float(conn.get("powerActiveCooldown"))
        # Spreadsheet "Lock On Overheat" + "Heat Reduce When Overheat Is Fixed".
        # Note CIG attribute name has typo: "lockOnOnverheat" (sic).
        result["lockOnOverheat"] = safe_bool(conn.get("lockOnOnverheat", "0"))
        hrwoif = conn.get("heatReduceWhenOverheatIsFixed")
        if hrwoif is not None:
            result["heatReduceWhenOverheatIsFixed"] = safe_float(hrwoif)

        # Simplified heat parameters (weapon-specific heat model)
        shp = conn.find(".//SWeaponSimplifiedHeatParams")
        if shp is not None:
            result["simplifiedHeat"] = {
                "minTemperature": safe_float(shp.get("minTemperature")),
                "overheatTemperature": safe_float(shp.get("overheatTemperature")),
                "coolingPerSecond": safe_float(shp.get("coolingPerSecond")),
                "temperatureAfterOverheatFix": safe_float(shp.get("temperatureAfterOverheatFix")),
                "timeTillCoolingStarts": safe_float(shp.get("timeTillCoolingStarts")),
                "overheatFixTime": safe_float(shp.get("overheatFixTime")),
            }
            # Heat-vs-damage scaling curve domain/range (P2e). The actual Bezier
            # curve points live in a separate BezierCurve record (referenced by
            # @temperatureCurve GUID) — only the axis bounds are surfaced here.
            tcp = shp.find(".//SWeaponSimplifiedHeatParamsTemperatureCurveParams")
            if tcp is not None:
                x_axis = tcp.find("xAxisMinMaxValues")
                y_axis = tcp.find("yAxisMinMaxValues")
                if x_axis is not None and y_axis is not None:
                    result["simplifiedHeat"]["temperatureCurveAxes"] = {
                        "xMin": safe_float(x_axis.get("x", "0")),
                        "xMax": safe_float(x_axis.get("y", "0")),
                        "yMin": safe_float(y_axis.get("x", "0")),
                        "yMax": safe_float(y_axis.get("y", "0")),
                    }

        for stats_name in ["noPowerStats", "underpowerStats", "overpowerStats", "overclockedStats"]:
            stats_elem = conn.find(stats_name)
            if stats_elem is not None:
                block = {
                    "fireRate": safe_float(stats_elem.get("fireRate")),
                    "fireRateMultiplier": safe_float(stats_elem.get("fireRateMultiplier")),
                    "damageMultiplier": safe_float(stats_elem.get("damageMultiplier")),
                    "projectileSpeedMultiplier": safe_float(stats_elem.get("projectileSpeedMultiplier")),
                    "pellets": safe_int(stats_elem.get("pellets")),
                    "burstShots": safe_int(stats_elem.get("burstShots")),
                    "ammoCost": safe_int(stats_elem.get("ammoCost")),
                    "ammoCostMultiplier": safe_float(stats_elem.get("ammoCostMultiplier")),
                    "heatGenerationMultiplier": safe_float(stats_elem.get("heatGenerationMultiplier")),
                    "chargeTimeMultiplier": safe_float(stats_elem.get("chargeTimeMultiplier", "1")),
                    "damageOverTimeMultiplier": safe_float(stats_elem.get("damageOverTimeMultiplier", "1")),
                    "soundRadiusMultiplier": safe_float(stats_elem.get("soundRadiusMultiplier", "1")),
                }
                # P3c: capture recoil/aim/spread/regen sub-blocks (top-level scalars
                # only; nested curve modifiers skipped for the same reason as the
                # ActorProceduralRecoilModifiers parser).
                rm = stats_elem.find("recoilModifier")
                if rm is not None:
                    block["recoilModifier"] = {
                        "decayMultiplier": safe_float(rm.get("decayMultiplier", "1")),
                        "endDecayMultiplier": safe_float(rm.get("endDecayMultiplier", "1")),
                        "fireRecoilTimeMultiplier": safe_float(rm.get("fireRecoilTimeMultiplier", "1")),
                        "fireRecoilStrengthFirstMultiplier": safe_float(rm.get("fireRecoilStrengthFirstMultiplier", "1")),
                        "fireRecoilStrengthMultiplier": safe_float(rm.get("fireRecoilStrengthMultiplier", "1")),
                        "angleRecoilStrengthMultiplier": safe_float(rm.get("angleRecoilStrengthMultiplier", "1")),
                        "randomnessMultiplier": safe_float(rm.get("randomnessMultiplier", "1")),
                        "randomnessBackPushMultiplier": safe_float(rm.get("randomnessBackPushMultiplier", "1")),
                        "frontalOscillationRotationMultiplier": safe_float(rm.get("frontalOscillationRotationMultiplier", "1")),
                        "frontalOscillationStrengthMultiplier": safe_float(rm.get("frontalOscillationStrengthMultiplier", "1")),
                        "frontalOscillationDecayMultiplier": safe_float(rm.get("frontalOscillationDecayMultiplier", "1")),
                        "frontalOscillationRandomnessMultiplier": safe_float(rm.get("frontalOscillationRandomnessMultiplier", "1")),
                        "animatedRecoilMultiplier": safe_float(rm.get("animatedRecoilMultiplier", "1")),
                        "disableRecoil": safe_bool(rm.get("disableRecoil", "0")),
                    }
                am = stats_elem.find("aimModifier")
                if am is not None:
                    block["aimModifier"] = {
                        "zoomScale": safe_float(am.get("zoomScale", "1")),
                        "secondZoomScale": safe_float(am.get("secondZoomScale", "1")),
                        "zoomTimeScale": safe_float(am.get("zoomTimeScale", "1")),
                        "fstopMultiplier": safe_float(am.get("fstopMultiplier", "1")),
                        "hideWeaponInADS": safe_bool(am.get("hideWeaponInADS", "0")),
                    }
                sm = stats_elem.find("spreadModifier")
                if sm is not None:
                    block["spreadModifier"] = {
                        "min": safe_float(sm.get("minMultiplier", "1")),
                        "max": safe_float(sm.get("maxMultiplier", "1")),
                        "firstAttack": safe_float(sm.get("firstAttackMultiplier", "1")),
                        "attack": safe_float(sm.get("attackMultiplier", "1")),
                        "decay": safe_float(sm.get("decayMultiplier", "1")),
                        "additive": safe_bool(sm.get("additiveModifier", "0")),
                    }
                regen = stats_elem.find("regenModifier")
                if regen is not None:
                    block["regenModifier"] = {
                        "maxAmmoLoadMultiplier": safe_float(regen.get("maxAmmoLoadMultiplier", "1")),
                        "maxRegenPerSecMultiplier": safe_float(regen.get("maxRegenPerSecMultiplier", "1")),
                        "powerRatioMultiplier": safe_float(regen.get("powerRatioMultiplier", "1")),
                    }
                result[stats_name] = block

    # Firing modes from weapon action params — walk top-level children of <fireActions>
    # in XML order so the output preserves the order ref uses.
    firing_modes = []

    fire_actions_elem = comp.find("fireActions")
    if fire_actions_elem is None:
        fire_actions_elem = comp

    # Capture the SET of fireAction element names present so downstream
    # classifiers can discriminate weapon types that the existing firingModes
    # extractor doesn't surface (notably HealingBeam — used by crlf_medgun_01
    # — which has no Single/Rapid/Burst/Charged mode and thus no entry in
    # firing_modes). Stripped form: "SWeaponAction" prefix and "Params"
    # suffix dropped, so "SWeaponActionFireHealingBeamParams" → "FireHealingBeam".
    fire_action_types = []
    for _child in list(fire_actions_elem):
        _tag = _child.tag
        if _tag.startswith("SWeaponAction") and _tag.endswith("Params"):
            short = _tag[len("SWeaponAction"):-len("Params")]
            if short not in fire_action_types:
                fire_action_types.append(short)
    if fire_action_types:
        result["fireActionTypes"] = fire_action_types

    _top_tag_to_type = {
        "SWeaponActionFireSingleParams": "single",
        "SWeaponActionFireRapidParams": "rapid",
        "SWeaponActionFireBurstParams": "burst",
    }

    for child in list(fire_actions_elem):
        tag = child.tag

        if tag == "SWeaponActionDynamicConditionParams":
            # rapidBeam-style weapon: emit a top-level mode with DefaultWeaponAction
            # and optional ConditionalWeaponActions sub-dicts.
            mode = {
                "name": child.get("name", ""),
                "localisedName": child.get("localisedName", ""),
                "fireType": "rapidBeam",
            }
            default_act = child.find("defaultWeaponAction")
            if default_act is not None:
                for sub in list(default_act):
                    inner_mode = _parse_dynamic_inner(sub)
                    if inner_mode:
                        mode["defaultWeaponAction"] = inner_mode
                        break
            cond_acts = child.find("conditionalWeaponActions")
            if cond_acts is not None:
                first_cwa = cond_acts.find("SConditionalWeaponAction")
                if first_cwa is not None:
                    inner = first_cwa.find("weaponAction")
                    if inner is not None:
                        for sub in list(inner):
                            inner_mode = _parse_dynamic_inner(sub)
                            if inner_mode:
                                mode["conditionalWeaponActions"] = inner_mode
                                break
            firing_modes.append(mode)
            continue

        if tag == "SWeaponActionSequenceParams":
            # Sequence wrapper — first inner fire action becomes the mode, plus entries.
            # The @mode attribute discriminates real burst weapons ("Looping" —
            # cycle loops while trigger held, e.g. Echion 3-shot burst) from
            # single-shot weapons that use a sequence purely for internal barrel
            # cycling ("Automatically" — Leonids: one shot per trigger pull,
            # entries describe barrel-cycling cooldowns, not a burst pattern).
            seq_entries = []
            for entry in child.iter("SWeaponSequenceEntryParams"):
                seq_entries.append({
                    "delay": safe_float(entry.get("delay")),
                    "unit": entry.get("unit", ""),
                    "repetitions": safe_int(entry.get("repetitions", "1")),
                })
            seq_mode = child.get("mode", "")
            inner_action = None
            for inner_tag in ("SWeaponActionFireSingleParams", "SWeaponActionFireRapidParams",
                              "SWeaponActionFireBurstParams", "SWeaponActionFireChargedParams"):
                found = child.iter(inner_tag)
                inner_action = next(found, None)
                if inner_action is not None:
                    break
            if inner_action is not None:
                mode = _parse_fire_action(inner_action)
                if mode:
                    mode["fireType"] = "sequence"
                    if seq_entries:
                        mode["sequenceEntries"] = seq_entries
                    if seq_mode:
                        mode["sequenceMode"] = seq_mode
                    firing_modes.append(mode)

        elif tag == "SWeaponActionFireChargedParams":
            # Charged wrapper with inner fire action
            inner_action = None
            for inner_tag in ("SWeaponActionFireSingleParams", "SWeaponActionFireRapidParams",
                              "SWeaponActionFireBurstParams"):
                found = child.iter(inner_tag)
                inner_action = next(found, None)
                if inner_action is not None:
                    break
            if inner_action is not None:
                mode = _parse_fire_action(inner_action)
            else:
                mode = _parse_fire_action(child)
            if mode:
                mode["fireType"] = "charged"
                # Override name/localisedName with charged wrapper values
                c_name = child.get("name", "")
                c_loc = child.get("localisedName", "")
                if c_name:
                    mode["name"] = c_name
                if c_loc:
                    mode["localisedName"] = c_loc
                mode["chargeTime"] = safe_float(child.get("chargeTime"))
                mode["overchargeTime"] = safe_float(child.get("overchargeTime"))
                mode["overchargedTime"] = safe_float(child.get("overchargedTime"))
                mode["cooldownTime"] = safe_float(child.get("cooldownTime"))
                mode["fireOnFullCharge"] = child.get("fireAutomaticallyOnFullCharge") == "1"
                mode["fireOnlyOnFullCharge"] = child.get("fireOnlyOnFullCharge") == "1"
                mcm = child.find("maxChargeModifier")
                if mcm is not None:
                    mode["chargeModifiers"] = {
                        "fireRateMultiplier": safe_float(mcm.get("fireRateMultiplier", "1")),
                        "projectileSpeedMultiplier": safe_float(mcm.get("projectileSpeedMultiplier", "1")),
                        "damageMultiplier": safe_float(mcm.get("damageMultiplier", "1")),
                        "damageOverTimeMultiplier": safe_float(mcm.get("damageOverTimeMultiplier", "1")),
                        "pellets": safe_int(mcm.get("pellets", "0")),
                    }
                firing_modes.append(mode)

        elif tag in _top_tag_to_type:
            mode = _parse_fire_action(child)
            if mode:
                mode["fireType"] = _top_tag_to_type[tag]
                firing_modes.append(mode)

        elif tag == "SWeaponActionFireBeamParams":
            mode = _parse_beam_action(child)
            if mode:
                firing_modes.append(mode)

        elif tag == "SWeaponActionFireTractorBeamParams":
            mode = {
                "name": child.get("name", ""),
                "localisedName": child.get("localisedName", ""),
                "fireType": "tractor",
                "minForce": safe_float(child.get("minForce")),
                "maxForce": safe_float(child.get("maxForce")),
                "minDistance": safe_float(child.get("minDistance")),
                "maxDistance": safe_float(child.get("maxDistance")),
                "fullStrengthDistance": safe_float(child.get("fullStrengthDistance")),
                "maxAngle": safe_float(child.get("maxAngle")),
                "maxVolume": safe_float(child.get("maxVolume")),
            }
            towing = child.find(".//SWeaponActionFireTractorBeamTowingParams")
            if towing is not None:
                mode["towing"] = {
                    "towingForce": safe_float(towing.get("towingForce")),
                    "towingMaxAcceleration": safe_float(towing.get("towingMaxAcceleration")),
                    "towingMaxDistance": safe_float(towing.get("towingMaxDistance")),
                    "quantumTowMassLimit": safe_float(towing.get("quantumTowMassLimit")),
                }
            firing_modes.append(mode)

    if firing_modes:
        result["firingModes"] = firing_modes

    return result


def _parse_dynamic_inner(elem):
    """Parse a fire action nested inside an SWeaponActionDynamicConditionParams
    wrapper (defaultWeaponAction / weaponAction inside conditionalWeaponActions).
    Returns a mode dict tagged with fireType, or None."""
    tag = elem.tag
    if tag == "SWeaponActionFireRapidParams":
        m = _parse_fire_action(elem)
        if m:
            m["fireType"] = "rapid"
        return m
    if tag == "SWeaponActionFireSingleParams":
        m = _parse_fire_action(elem)
        if m:
            m["fireType"] = "single"
        return m
    if tag == "SWeaponActionFireBurstParams":
        m = _parse_fire_action(elem)
        if m:
            m["fireType"] = "burst"
        return m
    if tag == "SWeaponActionFireBeamParams":
        return _parse_beam_action(elem)
    if tag == "SWeaponActionSequenceParams":
        # Take first inner fire action as the sequence mode
        for inner_tag in ("SWeaponActionFireSingleParams", "SWeaponActionFireRapidParams",
                          "SWeaponActionFireBurstParams"):
            inner = next(elem.iter(inner_tag), None)
            if inner is not None:
                m = _parse_fire_action(inner)
                if m:
                    m["fireType"] = "sequence"
                    seq_entries = []
                    for entry in elem.iter("SWeaponSequenceEntryParams"):
                        seq_entries.append({
                            "delay": safe_float(entry.get("delay")),
                            "unit": entry.get("unit", ""),
                            "repetitions": safe_int(entry.get("repetitions", "1")),
                        })
                    if seq_entries:
                        m["sequenceEntries"] = seq_entries
                return m
    return None


def _parse_beam_action(action):
    """Parse SWeaponActionFireBeamParams (mining lasers, weapon beams)."""
    mode = {
        "name": action.get("name", ""),
        "localisedName": action.get("localisedName", ""),
        "fireType": "beam",
    }
    # The "Mode" identifier comes from mannequinTag.tag
    mq = action.find("mannequinTag")
    if mq is not None:
        mode["mode"] = mq.get("tag", "")

    # Spread params (for FPS beam weapons inside dynamic-condition wrappers)
    sp = action.find(".//spreadParams/SSpreadParams")
    if sp is not None:
        mode["spread"] = {
            "min": safe_float(sp.get("min")),
            "max": safe_float(sp.get("max")),
            "firstAttack": safe_float(sp.get("firstAttack")),
            "attack": safe_float(sp.get("attack")),
            "decay": safe_float(sp.get("decay")),
        }

    # Beam-specific attributes
    mode["hitType"] = action.get("hitType", "")
    mode["hitRadius"] = safe_float(action.get("hitRadius"))
    mode["minEnergyDraw"] = safe_float(action.get("minEnergyDraw"))
    mode["maxEnergyDraw"] = safe_float(action.get("maxEnergyDraw"))
    mode["fullDamageRange"] = safe_float(action.get("fullDamageRange"))
    mode["zeroDamageRange"] = safe_float(action.get("zeroDamageRange"))
    mode["heatPerSecond"] = safe_float(action.get("heatPerSecond"))
    mode["wearPerSecond"] = safe_float(action.get("wearPerSecond"))
    mode["chargeUpTime"] = safe_float(action.get("chargeUpTime"))
    mode["chargeDownTime"] = safe_float(action.get("chargeDownTime"))

    # Damage (per second, with full type breakdown)
    dps = action.find("damagePerSecond")
    if dps is not None:
        dinfo = dps.find("DamageInfo")
        if dinfo is not None:
            dmg = {}
            for attr in ["DamagePhysical", "DamageEnergy", "DamageDistortion",
                         "DamageThermal", "DamageBiochemical", "DamageStun"]:
                val = safe_float(dinfo.get(attr))
                if val:
                    dmg[attr.replace("Damage", "")] = val
            mode["damagePerSecondBreakdown"] = dmg
            # Backwards-compat fields used by mining laser builder
            mode["damageEnergy"] = safe_float(dinfo.get("DamageEnergy"))
            mode["damagePhysical"] = safe_float(dinfo.get("DamagePhysical"))

    return mode


def _parse_fire_action(action):
    """Parse a weapon fire action (SWeaponActionFire*Params)."""
    mode = {
        "name": action.get("name", ""),
        "localisedName": action.get("localisedName", ""),
        "fireRate": safe_float(action.get("fireRate")),  # This is RPM
        "heatPerShot": safe_float(action.get("heatPerShot")),
        "wearPerShot": safe_float(action.get("wearPerShot")),
        "fireType": "single",
    }

    # Burst params — shotCount for "burst N" fireType
    burst_count = action.get("shotCount")
    if burst_count is not None:
        mode["shotCount"] = safe_int(burst_count)

    # Cooldown after firing (post-burst / post-shot recovery). Spreadsheet
    # "Cooldown Delay" column. Stored under both keys: `cooldownTime` is the
    # public name surfaced in stdItem; `innerCooldownTime` is kept for the
    # sequence-RPM logic in stditem._sequence_rpm_calc that already references it.
    cd = action.get("cooldownTime")
    if cd is not None:
        mode["cooldownTime"] = safe_float(cd)
        mode["innerCooldownTime"] = safe_float(cd)

    # Per-fire-mode external GUID references:
    # - @recoil → WeaponProceduralRecoilConfigDef (per-mode base recoil curves)
    # - @misfire → WeaponMisfireDef (jam mechanics)
    rcfg = action.get("recoil")
    if rcfg and rcfg != "00000000-0000-0000-0000-000000000000":
        mode["recoilConfig"] = rcfg
    mf = action.get("misfire")
    if mf and mf != "00000000-0000-0000-0000-000000000000":
        mode["misfire"] = mf

    # Spin-up/down for rapid fire (gatling) weapons
    spin_up = action.get("spinUpTime")
    spin_down = action.get("spinDownTime")
    if spin_up is not None:
        mode["spinUpTime"] = safe_float(spin_up)
    if spin_down is not None:
        mode["spinDownTime"] = safe_float(spin_down)

    # Launch params (ammoCost, pelletCount, spread)
    launcher = action.find(".//SProjectileLauncher")
    if launcher is not None:
        mode["ammoCost"] = safe_int(launcher.get("ammoCost"))
        mode["pelletCount"] = safe_int(launcher.get("pelletCount"))
        mode["damageMultiplier"] = safe_float(launcher.get("damageMultiplier", "1"))
        mode["soundRadius"] = safe_float(launcher.get("soundRadius"))

        spread = launcher.find("spreadParams")
        if spread is not None:
            mode["spread"] = {
                "min": safe_float(spread.get("min")),
                "max": safe_float(spread.get("max")),
                "firstAttack": safe_float(spread.get("firstAttack")),
                "attack": safe_float(spread.get("attack")),
                "decay": safe_float(spread.get("decay")),
            }

    # Charged fire params
    charge = action.find(".//fireChargedParams")
    if charge is None:
        # Try the element itself for charged params
        if action.get("chargeTime"):
            mode["chargeTime"] = safe_float(action.get("chargeTime"))
            mode["overchargeTime"] = safe_float(action.get("overchargeTime"))

    return mode


def _parse_shield_params(comp):
    """Parse SCItemShieldGeneratorParams with full resistance/absorption data."""
    result = {
        "maxShieldHealth": safe_float(comp.get("MaxShieldHealth")),
        "maxShieldRegen": safe_float(comp.get("MaxShieldRegen")),
        "downedRegenDelay": safe_float(comp.get("DownedRegenDelay")),
        "damagedRegenDelay": safe_float(comp.get("DamagedRegenDelay")),
    }

    # Reserve pool (attributes on the SCItemShieldGeneratorParams element itself)
    rp_init = comp.get("ReservePoolInitialHealthRatio")
    if rp_init is not None:
        result["reservePool"] = {
            "initialHealthRatio": safe_float(rp_init),
            "maxHealthRatio": safe_float(comp.get("ReservePoolMaxHealthRatio")),
            "regenRateRatio": safe_float(comp.get("ReservePoolRegenRateRatio")),
            "drainRateRatio": safe_float(comp.get("ReservePoolDrainRateRatio")),
        }

    # Damage type order for indexed arrays
    _DAMAGE_TYPES = ["Physical", "Energy", "Distortion", "Thermal", "Biochemical", "Stun"]

    # Resistance - 6 SShieldResistance entries in order
    res_section = comp.find("ShieldResistance")
    if res_section is not None:
        vals = {}
        for i, child in enumerate(res_section):
            if i < len(_DAMAGE_TYPES):
                vals[_DAMAGE_TYPES[i]] = {
                    "min": safe_float(child.get("Min")),
                    "max": safe_float(child.get("Max")),
                }
        if vals:
            result["resistance"] = vals

    # Absorption - 6 SShieldAbsorption entries in order
    abs_section = comp.find("ShieldAbsorption")
    if abs_section is not None:
        vals = {}
        for i, child in enumerate(abs_section):
            if i < len(_DAMAGE_TYPES):
                vals[_DAMAGE_TYPES[i]] = {
                    "min": safe_float(child.get("Min")),
                    "max": safe_float(child.get("Max")),
                }
        if vals:
            result["absorption"] = vals

    return result


def _parse_cooler_params(comp):
    return {
        "coolingRate": safe_float(comp.get("CoolingRate")),
        "suppressionIRFactor": safe_float(comp.get("SuppressionIRFactor")),
        "suppressionHeatFactor": safe_float(comp.get("SuppressionHeatFactor")),
    }


def _parse_power_plant_params(comp):
    return {"powerOutput": safe_float(comp.get("PowerOutput"))}


def _parse_quantum_drive_params(comp):
    result = {
        "FuelRate": safe_float(comp.get("quantumFuelRequirement")),
        "JumpRange": safe_float(comp.get("jumpRange")),
        "DisconnectRange": safe_float(comp.get("disconnectRange")),
        "InterdictionEffectTime": safe_float(comp.get("interdictionEffectTime")),
    }

    # Standard jump params (in "params" child element)
    std_jump = comp.find("params")
    if std_jump is not None:
        result["StandardJump"] = {
            "Speed": safe_float(std_jump.get("driveSpeed")),
            "Cooldown": safe_float(std_jump.get("cooldownTime")),
            "Stage1AccelerationRate": safe_float(std_jump.get("stageOneAccelRate")),
            "State2AccelerationRate": safe_float(std_jump.get("stageTwoAccelRate")),
            "SpoolUpTime": safe_float(std_jump.get("spoolUpTime")),
        }
        # InterdictionEffectTime is stored on the params child, not the parent
        iet = std_jump.get("interdictionEffectTime")
        if iet is not None:
            result["InterdictionEffectTime"] = safe_float(iet)

    # Spline jump params
    spline_jump = comp.find("splineJumpParams")
    if spline_jump is not None:
        result["SplineJump"] = {
            "Speed": safe_float(spline_jump.get("driveSpeed")),
            "Cooldown": safe_float(spline_jump.get("cooldownTime")),
            "Stage1AccelerationRate": safe_float(spline_jump.get("stageOneAccelRate")),
            "State2AccelerationRate": safe_float(spline_jump.get("stageTwoAccelRate")),
            "SpoolUpTime": safe_float(spline_jump.get("spoolUpTime")),
        }

    # Spline jump params
    spline_jump = comp.find("splineJump")
    if spline_jump is not None:
        result["splineJump"] = {
            "speed": safe_float(spline_jump.get("Speed", spline_jump.get("speed"))),
            "cooldown": safe_float(spline_jump.get("Cooldown", spline_jump.get("cooldown"))),
            "stage1AccelerationRate": safe_float(spline_jump.get("Stage1AccelerationRate")),
            "spoolUpTime": safe_float(spline_jump.get("SpoolUpTime", spline_jump.get("spoolUpTime"))),
        }

    return result


def _parse_missile_params(comp):
    result = {
        "maxLifetime": safe_float(comp.get("maxLifetime")),
        "armTime": safe_float(comp.get("armTime")),
        "igniteTime": safe_float(comp.get("igniteTime")),
        "explosionSafetyDistance": safe_float(comp.get("explosionSafetyDistance")),
        "projectileProximity": safe_float(comp.get("projectileProximity")),
    }

    # Explosion params
    explosion = comp.find("explosionParams")
    if explosion is not None:
        result["explosionMinRadius"] = safe_float(explosion.get("minRadius"))
        result["explosionMaxRadius"] = safe_float(explosion.get("maxRadius"))
        # Damage from nested DamageInfo
        damage = explosion.find("damage")
        if damage is not None:
            dinfo = damage.find("DamageInfo")
            if dinfo is not None:
                dmg = {}
                for attr in ["DamagePhysical", "DamageEnergy", "DamageDistortion",
                             "DamageThermal", "DamageBiochemical", "DamageStun"]:
                    val = safe_float(dinfo.get(attr))
                    if val:
                        key = attr.replace("Damage", "")
                        dmg[key] = val
                if dmg:
                    result["explosionDamage"] = dmg

    # Guidance and control params
    gcs = comp.find("GCSParams")
    if gcs is not None:
        result["linearSpeed"] = safe_float(gcs.get("linearSpeed"))
        result["fuelTankSize"] = safe_float(gcs.get("fuelTankSize"))
        result["boostPhaseDuration"] = safe_float(gcs.get("boostPhaseDuration"))
        result["terminalPhaseEngagementTime"] = safe_float(gcs.get("terminalPhaseEngagementTime"))
        result["terminalPhaseEngagementAngle"] = safe_float(gcs.get("terminalPhaseEngagementAngle"))

    # Targeting params
    targeting = comp.find("targetingParams")
    if targeting is not None:
        result["trackingSignalType"] = targeting.get("trackingSignalType", "")
        result["trackingSignalMin"] = safe_float(targeting.get("trackingSignalMin"))
        result["minRatioForLock"] = safe_float(targeting.get("minRatioForLock"))
        result["lockIncreaseRate"] = safe_float(targeting.get("lockIncreaseRate"))
        result["lockTime"] = safe_float(targeting.get("lockTime"))
        result["lockingAngle"] = safe_float(targeting.get("lockingAngle"))
        result["lockRangeMin"] = safe_float(targeting.get("lockRangeMin"))
        result["lockRangeMax"] = safe_float(targeting.get("lockRangeMax"))

    return result


def _parse_armor_params(comp):
    result = {}

    # Damage multipliers — inside damageMultiplier > DamageInfo child
    dmg_mult = comp.find("damageMultiplier")
    if dmg_mult is not None:
        dmg_info = dmg_mult.find("DamageInfo")
        src = dmg_info if dmg_info is not None else dmg_mult
        mults = {}
        for attr in ["DamagePhysical", "DamageEnergy", "DamageDistortion",
                      "DamageThermal", "DamageBiochemical", "DamageStun"]:
            val = src.get(attr)
            if val is not None:
                key = attr.replace("Damage", "").lower()
                mults[key] = safe_float(val)
        if mults:
            result["damageMultipliers"] = mults

    # Signal multipliers — attributes directly on SCItemVehicleArmorParams element
    sig = {}
    for attr, key in [("signalElectromagnetic", "em"),
                      ("signalInfrared", "ir"),
                      ("signalCrossSection", "cs")]:
        val = comp.get(attr)
        if val is not None:
            sig[key] = safe_float(val)
    if sig:
        result["signalMultipliers"] = sig

    # Damage deflection — armorDeflection > deflectionValue (DamageInfo child)
    armor_defl = comp.find("armorDeflection")
    if armor_defl is not None:
        defl_val = armor_defl.find("deflectionValue")
        if defl_val is not None:
            defl_info = defl_val.find("DamageInfo")
            src = defl_info if defl_info is not None else defl_val
            result["damageDeflection"] = {
                "physical": safe_float(src.get("DamagePhysical")),
                "energy": safe_float(src.get("DamageEnergy")),
                "distortion": safe_float(src.get("DamageDistortion")),
                "thermal": safe_float(src.get("DamageThermal")),
                "biochemical": safe_float(src.get("DamageBiochemical")),
                "stun": safe_float(src.get("DamageStun")),
            }

    # Penetration resistance — armorPenetrationResistance
    pen_res = comp.find("armorPenetrationResistance")
    if pen_res is not None:
        result["penetrationReduction"] = safe_float(pen_res.get("basePenetrationReduction", "1"))
        pen_abs = pen_res.find("penetrationAbsorptionForType")
        if pen_abs is not None:
            pen_info = pen_abs.find("DamageInfo")
            src = pen_info if pen_info is not None else pen_abs
            result["penetrationAbsorption"] = {
                "physical": safe_float(src.get("DamagePhysical", "0")),
                "energy": safe_float(src.get("DamageEnergy", "0")),
                "distortion": safe_float(src.get("DamageDistortion", "0")),
                "thermal": safe_float(src.get("DamageThermal", "0")),
                "biochemical": safe_float(src.get("DamageBiochemical", "0")),
                "stun": safe_float(src.get("DamageStun", "0")),
            }

    return result


def _parse_power_connection(comp):
    return {
        "powerBase": safe_float(comp.get("PowerBase")),
        "powerDraw": safe_float(comp.get("PowerDraw")),
        "powerToEM": safe_float(comp.get("PowerToEM")),
        "decayRateOfEM": safe_float(comp.get("DecayRateOfEM")),
        "isThrottleable": safe_bool(comp.get("IsThrottleable")),
        "isOverclockable": safe_bool(comp.get("IsOverclockable")),
        "overpowerPerformance": safe_float(comp.get("OverpowerPerformance")),
        "overclockPerformance": safe_float(comp.get("OverclockPerformance")),
    }


def _parse_heat_connection(comp):
    return {
        "temperatureToIR": safe_float(comp.get("TemperatureToIR")),
        "startIRTemperature": safe_float(comp.get("StartIRTemperature")),
        "thermalEnergyBase": safe_float(comp.get("ThermalEnergyBase")),
        "thermalEnergyDraw": safe_float(comp.get("ThermalEnergyDraw")),
        "thermalConductivity": safe_float(comp.get("ThermalConductivity")),
        "specificHeatCapacity": safe_float(comp.get("SpecificHeatCapacity")),
        "mass": safe_float(comp.get("Mass")),
        "surfaceArea": safe_float(comp.get("SurfaceArea")),
        "startCoolingTemperature": safe_float(comp.get("StartCoolingTemperature")),
        "maxCoolingRate": safe_float(comp.get("MaxCoolingRate")),
        "maxTemperature": safe_float(comp.get("MaxTemperature")),
        "overheatTemperature": safe_float(comp.get("OverheatTemperature")),
        "recoveryTemperature": safe_float(comp.get("RecoveryTemperature")),
        "minTemperature": safe_float(comp.get("MinTemperature")),
    }


def _parse_port_container(comp):
    """Parse SItemPortContainerComponentParams for hardpoint ports."""
    ports = []
    ports_elem = comp.find("Ports")
    if ports_elem is not None:
        for port_elem in ports_elem:
            port = _parse_item_port(port_elem)
            if port:
                ports.append(port)
    return ports


def _parse_item_port(elem):
    """Parse a single SItemPortDef."""
    flags = elem.get("Flags", "")
    # `controllableTag` is the entity-XML equivalent of impl-XML's
    # `<ControllerDef controllableTags="...">`. Capital ships (Paladin,
    # Polaris, capital-class PDC hosts) declare seat/WC priority chains here
    # rather than in impl XML. Capture so the RC seat resolver can use it.
    ctrl_tag = elem.get("controllableTag") or elem.get("controllableTags") or ""
    port = {
        "name": elem.get("Name", elem.get("name", "")),
        "minSize": safe_int(elem.get("MinSize")),
        "maxSize": safe_int(elem.get("MaxSize")),
        "portTags": elem.get("PortTags", ""),
        "requiredPortTags": elem.get("RequiredPortTags", ""),
        "flags": flags,
        # Uneditable is true if the explicit attribute is set OR if the flags
        # string contains "uneditable" / "$uneditable" (e.g. PDC turret
        # internal weapon ports use the flag form only).
        "uneditable": safe_bool(elem.get("Uneditable")) or "uneditable" in (flags or "").lower(),
    }
    if ctrl_tag:
        port["controllableTags"] = ctrl_tag

    # Entity-XML priority groups live under <control><SCItemControl*Params>
    # <controllableGroups><SCItemControllableGroupParams><priorityGroups>
    # <SCItemPriorityGroupParam itemType="X" defaultPriority="N">
    #   <tags><SCItemPriorityTagParam tag="Y" priority="V"/></tags>
    # Capture these into the same shape as impl-XML's exclusiveControl /
    # controlledTags / priorityControllers so the existing RC enricher can
    # consume them uniformly. Used by Paladin, Polaris-class PDC hosts.
    excl = []
    controlled = []
    prio_controllers = []
    for pg in elem.iter("SCItemPriorityGroupParam"):
        it_type = pg.get("itemType", "")
        if not it_type:
            continue
        # Each tag claim under this PG.
        tags_root = pg.find("tags")
        if tags_root is not None:
            for tag_param in tags_root.findall("SCItemPriorityTagParam"):
                tag_v = tag_param.get("tag", "")
                pri_v = tag_param.get("priority", "")
                if not tag_v or not pri_v:
                    continue
                if pri_v == "exclusive_control":
                    excl.append((it_type, tag_v))
                elif pri_v not in ("no_control", "observe_only"):
                    try:
                        prio_int = int(pri_v)
                    except (TypeError, ValueError):
                        prio_int = pri_v
                    controlled.append((it_type, tag_v, prio_int))
                    if it_type in ("WeaponController", "MissileController"):
                        prio_controllers.append((it_type, tag_v, prio_int
                                                  if isinstance(prio_int, int) else 0))
    if excl:
        existing = port.get("exclusiveControl") or []
        port["exclusiveControl"] = existing + excl
    if controlled:
        existing = port.get("controlledTags") or []
        port["controlledTags"] = existing + controlled
    if prio_controllers:
        existing = port.get("priorityControllers") or []
        port["priorityControllers"] = existing + prio_controllers

    # Types - each SItemPortDefTypes has a Type attr and SubTypes > Enum children
    types_elem = elem.find("Types")
    if types_elem is not None:
        types = []
        for type_elem in types_elem:
            t = type_elem.get("Type", type_elem.get("type", ""))
            if not t:
                continue
            # SubTypes are in child <SubTypes><Enum value="..." /></SubTypes>
            sub_types_elem = type_elem.find("SubTypes")
            if sub_types_elem is not None:
                has_subtypes = False
                for enum_elem in sub_types_elem:
                    st = enum_elem.get("value", "")
                    if not st:
                        continue
                    # Preserve "UNDEFINED" subtype for Bomb (ref emits "Bomb.UNDEFINED");
                    # for other types, UNDEFINED is a no-op we drop.
                    if st == "UNDEFINED" and t != "Bomb":
                        continue
                    types.append(f"{t}.{st}")
                    has_subtypes = True
                if not has_subtypes:
                    types.append(t)
            else:
                # Fallback: check SubType attribute directly
                st = type_elem.get("SubType", type_elem.get("subType", ""))
                types.append(f"{t}.{st}" if st and st != "UNDEFINED" else t)
        port["types"] = types

    # Default loadout. Scope the search to this port's own subtree minus
    # nested sub-ports (elem.iter also descends into <Ports>, where the
    # first hit would be a SUB-port's loadout entry misattributed to the
    # parent when the parent itself has none).
    nested_ports_elem = elem.find("Ports")
    nested_entries = (
        {id(e) for e in nested_ports_elem.iter("SItemPortLoadoutEntryParams")}
        if nested_ports_elem is not None else set()
    )
    for entry in elem.iter("SItemPortLoadoutEntryParams"):
        if id(entry) in nested_entries:
            continue
        cn = entry.get("entityClassName", "")
        ref = entry.get("entityClassReference", "")
        if cn:
            port["defaultLoadout"] = cn
        elif ref and ref != "00000000-0000-0000-0000-000000000000":
            port["defaultLoadoutRef"] = ref
        break

    # Sub-ports
    sub_ports_elem = elem.find("Ports")
    if sub_ports_elem is not None and sub_ports_elem is not elem.find("Types"):
        sub_ports = []
        for sp in sub_ports_elem:
            parsed = _parse_item_port(sp)
            if parsed:
                sub_ports.append(parsed)
        if sub_ports:
            port["subPorts"] = sub_ports

    return port


def _resolve_external_loadouts(records, cache_root):
    """Replace `_loadoutPath` markers in defaultLoadout entries with real entries
    parsed from the referenced external CryXML loadout file.

    SItemPortLoadoutXMLParams stores its entries in a file under
    cache/Data/Scripts/Loadouts/, with a structure like:
        <Loadout>
          <Items>
            <Item portName="X" itemName="Y">
              <Items>...</Items>  (recursive)
            </Item>
          </Items>
        </Loadout>

    The CryXML→text conversion has already happened by the time we get here.
    """
    if not cache_root:
        return

    loadout_cache = {}

    def _read_external(rel_path):
        if rel_path in loadout_cache:
            return loadout_cache[rel_path]
        # External path is relative to Data/, e.g.
        # "Scripts/Loadouts/Objects/Doors/...xml"
        full = os.path.join(cache_root, "Data", rel_path.replace("\\", "/"))
        if not os.path.isfile(full):
            loadout_cache[rel_path] = []
            return []
        try:
            tree = ET.parse(full)
            root = tree.getroot()
        except (ET.ParseError, OSError):
            loadout_cache[rel_path] = []
            return []

        def _walk_items(items_elem):
            out = []
            if items_elem is None:
                return out
            for item in items_elem.findall("Item"):
                entry = {
                    "portName": item.get("portName", ""),
                    "entityClassName": item.get("itemName", ""),
                }
                children = _walk_items(item.find("Items"))
                if children:
                    entry["children"] = children
                out.append(entry)
            return out

        entries = _walk_items(root.find("Items"))
        loadout_cache[rel_path] = entries
        return entries

    def _resolve(entries):
        if not isinstance(entries, list):
            return entries
        result = []
        for entry in entries:
            if "_loadoutPath" in entry:
                external = _read_external(entry["_loadoutPath"])
                # Bare path entries (the whole loadout is external) — splice in.
                if entry.get("portName") or entry.get("entityClassName"):
                    new_entry = {k: v for k, v in entry.items() if k != "_loadoutPath"}
                    new_entry["children"] = (new_entry.get("children") or []) + external
                    result.append(new_entry)
                else:
                    result.extend(external)
            else:
                if "children" in entry:
                    entry["children"] = _resolve(entry["children"])
                result.append(entry)
        return result

    for cn, rec in records.items():
        comps = rec.get("components")
        if not isinstance(comps, dict):
            continue
        loadout = comps.get("defaultLoadout")
        if isinstance(loadout, list):
            comps["defaultLoadout"] = _resolve(loadout)


def _parse_default_loadout(comp):
    """Parse SEntityComponentDefaultLoadoutParams into a loadout tree.

    Two storage forms exist:
    - SItemPortLoadoutManualParams: inline `<entries>` of
      SItemPortLoadoutEntryParams (most common).
    - SItemPortLoadoutXMLParams: a `loadoutPath` attribute pointing at an
      external CryXML file (e.g. Scripts/Loadouts/Objects/Doors/...).
      We capture the path here and resolve it later in
      `resolve_external_loadouts` once the localisation/path index is
      available.
    """

    def _parse_loadout_entry(entry_elem):
        entry = {
            "portName": entry_elem.get("itemPortName", entry_elem.get("portName", "")),
            "entityClassName": entry_elem.get("entityClassName", ""),
        }
        ref = entry_elem.get("entityClassReference", "")
        if ref and ref != "00000000-0000-0000-0000-000000000000":
            entry["entityClassReference"] = ref

        children = []
        entries_elem = entry_elem.find("loadout")
        if entries_elem is not None:
            xml_params = entries_elem.find("SItemPortLoadoutXMLParams")
            if xml_params is not None:
                lp = xml_params.get("loadoutPath", "")
                if lp:
                    entry["_loadoutPath"] = lp
            else:
                items_elem = entries_elem.find("SItemPortLoadoutManualParams")
                if items_elem is None:
                    items_elem = entries_elem
                entries_container = items_elem.find("entries") if items_elem is not None else None
                if entries_container is not None:
                    for child_entry in entries_container:
                        poly = child_entry.get("__polymorphicType", child_entry.tag)
                        if poly == "SItemPortLoadoutEntryParams":
                            children.append(_parse_loadout_entry(child_entry))
        if children:
            entry["children"] = children
        return entry

    results = []
    loadout = comp.find("loadout")
    if loadout is not None:
        xml_params = loadout.find("SItemPortLoadoutXMLParams")
        if xml_params is not None:
            lp = xml_params.get("loadoutPath", "")
            if lp:
                results.append({"_loadoutPath": lp})
            return results
        manual = loadout.find("SItemPortLoadoutManualParams")
        if manual is None:
            manual = loadout
        entries = manual.find("entries") if manual is not None else None
        if entries is not None:
            for entry_elem in entries:
                poly = entry_elem.get("__polymorphicType", entry_elem.tag)
                if poly == "SItemPortLoadoutEntryParams":
                    results.append(_parse_loadout_entry(entry_elem))
    return results


def _elem_to_dict(elem):
    """Recursively convert an XML element to a nested dict."""
    result = {}
    for k, v in elem.attrib.items():
        if not k.startswith("__"):
            result[k] = v

    for child in elem:
        child_dict = _elem_to_dict(child)
        tag = child.get("__polymorphicType", child.tag)
        if tag in result:
            existing = result[tag]
            if not isinstance(existing, list):
                result[tag] = [existing]
            result[tag].append(child_dict)
        else:
            result[tag] = child_dict

    return result


def _parse_simple_dict(elem):
    """Convert element to a simple dict of attributes."""
    return dict(elem.attrib)
