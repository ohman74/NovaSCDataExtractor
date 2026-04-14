"""Build the stdItem object for any item record.

This produces the rich item data format matching the SPViewer reference,
with Durability, ResourceNetwork, HeatController, Weapon stats, etc.
"""

import re

from ..utils import safe_float, safe_int, resolve_name

# Manufacturer code -> equipment class mapping
MANUFACTURER_CLASS = {
    "ACAS": "Competition", "ACOM": "Competition",
    "AEG": "Military", "AMRS": "Military",
    "ARCC": "Civilian", "ASAS": "Stealth",
    "BANU": "Military", "BASL": "Industrial",
    "BEH": "Civilian", "BLTR": "Stealth",
    "CHCO": "Industrial", "GODI": "Military",
    "GRNP": "Military", "JSPN": "Civilian",
    "JUST": "Industrial", "LPLT": "Civilian",
    "NAVE": "Competition", "ORIG": "Industrial",
    "RACO": "Stealth", "RSI": "Civilian",
    "SASU": "Civilian", "SECO": "Civilian",
    "TARS": "Civilian", "TYDT": "Stealth",
    "WCPR": "Civilian", "WETK": "Military",
    "WLOP": "Civilian", "YORM": "Competition",
}


def build_std_item(record, ctx, external_loadout=None, nested=False):
    """Build a full stdItem dict from a parsed entity record."""
    attach_def = record.get("attachDef", {})
    components = record.get("components", {})

    item_type = attach_def.get("type", "")
    sub_type = attach_def.get("subType", "")
    # Keep .UNDEFINED for types like Shield.UNDEFINED to match reference
    full_type = f"{item_type}.{sub_type}" if sub_type else item_type

    description = _clean_description(ctx.resolve_name(attach_def.get("description", "")))

    si = {
        "ClassName": record.get("className", ""),
        "Size": attach_def.get("size", 0),
        "Grade": attach_def.get("grade", 0),
        "Type": full_type,
        "Name": _resolve_item_name(attach_def.get("name", ""), record.get("className", ""), ctx),
    }

    # Description: in nested/InstalledItem context, exclude if unresolved or placeholder
    if nested:
        if description and not description.startswith("@") and description != "<= PLACEHOLDER =>":
            si["Description"] = description
    else:
        si["Description"] = description
    tags = [t for t in attach_def.get("tags", "").split() if t]
    if tags:
        si["Tags"] = tags

    # RequiredTags from attachDef
    req_tags_str = attach_def.get("requiredTags", "")
    if req_tags_str:
        si["RequiredTags"] = req_tags_str.split()

    # Classification (excluded for nested/InstalledItem)
    if not nested:
        path = record.get("path", "")
        classification = _build_classification(full_type, path)
        if classification:
            si["Classification"] = classification

    # Mass from physics
    physics = components.get("physics", {})
    if physics.get("mass"):
        si["Mass"] = physics["mass"]

    # Volume from attachDef
    if attach_def.get("volume"):
        si["Volume"] = float(attach_def["volume"])

    # Manufacturer
    mfr_guid = attach_def.get("manufacturerGuid", "")
    mfr = ctx.get_manufacturer(mfr_guid)
    if mfr:
        si["Manufacturer"] = mfr
        # Class derived from manufacturer — only for specific component types
        _COMPONENT_TYPES = {"Shield", "Cooler", "PowerPlant", "QuantumDrive", "Radar",
                            "LifeSupportGenerator", "JumpDrive", "QuantumInterdictionGenerator"}
        base = item_type.split(".")[0] if item_type else ""
        if base in _COMPONENT_TYPES:
            si["Class"] = MANUFACTURER_CLASS.get(mfr["Code"], "")
        else:
            si["Class"] = ""

    # Durability (from SHealthComponentParams + SDistortionParams + misfire + ItemResourceComponentParams.selfRepair)
    health = components.get("health", {})
    irp = components.get("ItemResourceComponentParams", {})
    distortion = components.get("SDistortionParams", {})
    # Misfire data from EntityComponentMisfireParams (generically captured)
    misfire_comp = components.get("EntityComponentMisfireParams", {})
    misfire_effect = {}
    if isinstance(misfire_comp, dict):
        misfires = misfire_comp.get("misfires", {})
        if isinstance(misfires, dict):
            she = misfires.get("SHostExplosionEffect", {})
            if isinstance(she, dict) and she.get("explosionChance"):
                misfire_effect = {
                    "chance": safe_float(she.get("explosionChance")),
                    "countdown": safe_float(she.get("explosionCountdown")),
                    "healthCancelRatio": safe_float(she.get("healthCancelRatio")),
                }
    # Lifetime from SDegradationParams
    deg = components.get("SDegradationParams", {})
    has_degradation = False
    lifetime = 0.0
    if isinstance(deg, dict):
        accum = deg.get("accumulators", {})
        wear = accum.get("SWearAccumulatorParams", {})
        if isinstance(wear, dict) and wear:
            has_degradation = True
            lifetime = safe_float(wear.get("MaxLifetimeHours", "0"))

    if health:
        si["Durability"] = _build_durability(health, irp, distortion, misfire_effect,
                                              lifetime, has_degradation)
    elif has_degradation:
        # Item has degradation but no health component — still include Durability with Lifetime
        si["Durability"] = {"Lifetime": lifetime}

    # ResourceNetwork (from ItemResourceComponentParams)
    if irp:
        resource_net = _build_resource_network_from_irp(irp)
        # Include even if empty list (ref includes [] for items with IRP but no states)
        if resource_net is not None:
            si["ResourceNetwork"] = resource_net

    # HeatController (from physics temperature element or EntityComponentHeatConnection)
    hc = components.get("heatController", {})
    heat = components.get("heat", {})
    if hc:
        si["HeatController"] = _build_heat_controller_from_hc(hc)
    elif heat:
        si["HeatController"] = _build_heat_controller_from_heat(heat)

    # Type-specific data
    if "weapon" in components:
        weapon_data = _build_weapon_data(components, ctx)
        if weapon_data:
            # For FPS weapons, ammo is in the magazine (via defaultLoadout)
            if not weapon_data.get("Ammunition") and "defaultLoadout" in components:
                _resolve_fps_ammo(weapon_data, components["defaultLoadout"], ctx)
            # Reorder keys to match reference format
            ordered = {}
            if "Modifiers" in weapon_data:
                ordered["Modifiers"] = weapon_data["Modifiers"]
            if "Ammunition" in weapon_data:
                ordered["Ammunition"] = weapon_data["Ammunition"]
            if "Firing" in weapon_data:
                ordered["Firing"] = weapon_data["Firing"]
            if "Consumption" in weapon_data:
                ordered["Consumption"] = weapon_data["Consumption"]
            if "HeatParameters" in weapon_data:
                ordered["HeatParameters"] = weapon_data["HeatParameters"]
            si["Weapon"] = ordered

    if "shield" in components:
        si["Shield"] = _build_shield_data(components["shield"])

    if "cooler" in components:
        si["Cooler"] = components["cooler"]

    if "powerPlant" in components:
        si["PowerPlant"] = components["powerPlant"]

    if "quantumDrive" in components:
        si["QuantumDrive"] = _build_quantum_drive(components["quantumDrive"])

    if "missile" in components:
        si["Missile"] = components["missile"]

    if "armor" in components:
        si["Armour"] = _build_armour(components["armor"])

    # MissileRack — count and size from missile ports
    ports = components.get("ports", [])
    missile_rack = _build_missile_rack(ports, item_type)
    if missile_rack:
        si["MissileRack"] = missile_rack

    # Turret — yaw/pitch axis data
    turret_params = components.get("SCItemTurretParams")
    if turret_params:
        turret = _build_turret(turret_params)
        if turret:
            si["Turret"] = turret

    # ShieldEmitter
    shield_emitter = components.get("SCItemShieldEmitterParams")
    if shield_emitter:
        si["ShieldEmitter"] = _build_shield_emitter(shield_emitter)

    # CounterMeasure from ammo's counterMeasure params
    if "WeaponDefensive" in item_type:
        ammo_comp = components.get("ammo", {})
        ammo_guid = ammo_comp.get("ammoParamsRecord", "")
        ammo_data = ctx.get_ammo(ammo_guid)
        if ammo_data and ammo_data.get("counterMeasure"):
            cm = ammo_data["counterMeasure"]
            cm_type = ammo_data.get("counterMeasureType", "Chaff")
            si["CounterMeasure"] = {cm_type: cm}

    # Ifcs from IFCSParams
    ifcs_params = components.get("IFCSParams")
    if ifcs_params:
        si["Ifcs"] = _build_ifcs(ifcs_params)

    # Radar from SCItemRadarComponentParams
    radar_params = components.get("SCItemRadarComponentParams")
    if radar_params:
        si["Radar"] = _build_radar(radar_params)

    # JumpDrive from SCItemJumpDriveParams
    jd_params = components.get("SCItemJumpDriveParams")
    if jd_params:
        si["JumpDrive"] = _build_jump_drive(jd_params)

    # EMP from SCItemEMPParams
    emp_params = components.get("SCItemEMPParams")
    if emp_params:
        si["Emp"] = _build_emp(emp_params)

    # SelfDestruct from SSCItemSelfDestructComponentParams
    sd_params = components.get("SSCItemSelfDestructComponentParams")
    if sd_params:
        si["SelfDestruct"] = _build_self_destruct(sd_params)

    # QuantumInterdiction from SCItemQuantumInterdictionGeneratorParams
    qi_params = components.get("SCItemQuantumInterdictionGeneratorParams")
    if qi_params:
        si["QuantumInterdiction"] = _build_quantum_interdiction(qi_params)

    # MiningLaser from SEntityComponentMiningLaserParams
    mining_params = components.get("SEntityComponentMiningLaserParams")
    if mining_params:
        si["MiningLaser"] = _build_mining_laser(mining_params, components)

    # Module/SalvageModifier from EntityComponentAttachableModifierParams
    modifier_params = components.get("EntityComponentAttachableModifierParams")
    if modifier_params:
        _build_modifier(si, modifier_params, item_type)

    # TractorBeam - from weapon firing modes for tractor items
    if "TractorBeam" in item_type or "TowingBeam" in item_type:
        tractor = _build_tractor_beam(components)
        if tractor:
            si["TractorBeam"] = tractor

    # Bomb from SCItemBombParams
    bomb_params = components.get("SCItemBombParams")
    if bomb_params:
        si["Bomb"] = _build_bomb(bomb_params)

    # MissilesController from SCItemMissileControllerParams
    mc_params = components.get("SCItemMissileControllerParams")
    if mc_params:
        si["MissilesController"] = _build_missiles_controller(mc_params)

    # CargoGrid/CargoContainers from ResourceContainer
    rc = components.get("ResourceContainer")
    if rc and ("Container" in item_type or "Cargo" in item_type):
        _build_cargo_fields(si, rc)

    # Ports
    if ports:
        default_loadout = components.get("defaultLoadout", []) or external_loadout or []
        si["Ports"] = _build_ports(ports, si.get("Tags", []), ctx, default_loadout)

    # Weapon modifier (for FPS attachments — recoil, spread, zoom modifiers)
    if not nested:
        weapon_mod = components.get("SWeaponModifierComponentParams", {})
        if weapon_mod:
            modifier = weapon_mod.get("modifier", {})
            if modifier:
                si["WeaponModifier"] = modifier

    return si


def _resolve_item_name(raw_name, class_name, ctx):
    """Resolve item name, falling back to className for placeholders/unresolved."""
    resolved = ctx.resolve_name(raw_name)
    if not resolved or resolved == "<= PLACEHOLDER =>" or resolved == "@LOC_PLACEHOLDER":
        return class_name or raw_name
    # If still unresolved (@key), fall back to className
    if resolved.startswith("@"):
        return class_name or raw_name
    return resolved


def _clean_description(desc):
    """Strip metadata prefix from descriptions (Manufacturer:, Item Type:, etc.)."""
    if not desc:
        return desc
    # Keep unresolved localization keys as-is
    if desc.startswith("@"):
        return desc
    # Restore placeholder markers
    if desc == "<= PLACEHOLDER =>":
        return "@LOC_PLACEHOLDER"
    # Localization files use literal \n — convert to real newlines
    if "\\n" in desc:
        desc = desc.replace("\\n", "\n")
    # Strip metadata prefix: lines of "Key: Value" followed by blank line "\n\n"
    if "\n\n" in desc:
        parts = desc.split("\n\n", 1)
        prefix = parts[0]
        lines = prefix.split("\n")
        if all(":" in line for line in lines if line.strip()):
            desc = parts[1] if len(parts) > 1 else desc
    # Reference removes newlines from descriptions
    return desc.replace("\n", "")


_CLASSIFICATION_TYPE_MAP = {
    "TurretBase": "Turret",
    "WeaponGun": "Weapon",
    "WeaponMining": "Mining",
    "ToolArm": "Turret",
    "UtilityTurret": "Turret",
}

def _build_classification(full_type, path):
    """Build classification string like 'Ship.WeaponDefensive.CountermeasureLauncher'."""
    if not full_type:
        return ""
    path_lower = path.lower() if path else ""
    type_lower = full_type.lower()
    if "fps" in path_lower or ("personal" in type_lower and "paints" not in type_lower):
        prefix = "FPS"
    else:
        prefix = "Ship"

    # Split type parts and clean up
    parts = full_type.split(".")
    # Map base type (e.g. TurretBase -> Turret)
    if parts[0] in _CLASSIFICATION_TYPE_MAP:
        parts[0] = _CLASSIFICATION_TYPE_MAP[parts[0]]
    # Remove UNDEFINED suffix
    parts = [p for p in parts if p != "UNDEFINED"]

    return f"{prefix}.{'.'.join(parts)}"


def _build_durability(health_data, irp=None, distortion_data=None, misfire_data=None,
                      lifetime=0.0, has_degradation=False):
    """Build Durability object from health component, distortion, misfire, and ItemResourceComponentParams."""
    result = {"Health": health_data.get("health", 0)}
    if has_degradation:
        result["Lifetime"] = lifetime

    # Distortion from SDistortionParams
    if distortion_data:
        max_dmg = safe_float(distortion_data.get("Maximum", "0"))
        decay_delay = safe_float(distortion_data.get("DecayDelay", "0"))
        decay_rate = safe_float(distortion_data.get("DecayRate", "0"))
        # RecoveryTime = DecayDelay + Maximum * (1 - RecoveryRatio) / DecayRate
        recovery_ratio = safe_float(distortion_data.get("RecoveryRatio", "0"))
        effective_dmg = max_dmg * (1 - recovery_ratio) if recovery_ratio else max_dmg
        recovery = round(decay_delay + effective_dmg / decay_rate, 2) if decay_rate else 0.0
        result["Distortion"] = {
            "MaximumDamage": max_dmg,
            "DecayDelay": decay_delay,
            "DecayRate": round(decay_rate, 7),
            "RecoveryTime": recovery,
        }

    dm = health_data.get("damageMultipliers", {})
    if dm:
        mults = {}
        for key, field in [("physical", "Physical"), ("energy", "Energy"),
                           ("distortion", "Distortion"), ("thermal", "Thermal"),
                           ("biochemical", "Biochemical"), ("stun", "Stun")]:
            val = dm.get(key)
            if val is not None and val != 0.0:
                mults[field] = val
        result["DamageMultipliers"] = mults

    # Misfire (power plants — from SHostExplosionEffect)
    if misfire_data and misfire_data.get("chance"):
        result["Misfire"] = {
            "Explosion": {
                "Chance": misfire_data.get("chance", 0),
                "Countdown": misfire_data.get("countdown", 0),
                "HealthCancelRatio": misfire_data.get("healthCancelRatio", 0),
            }
        }

    # SelfRepair from ItemResourceComponentParams
    if irp:
        self_repair = irp.get("selfRepair", {})
        if self_repair:
            result["SelfRepair"] = {
                "MaxRepair": safe_float(self_repair.get("maxRepairCount")),
                "TimeToRepair": safe_float(self_repair.get("timeToRepair")),
                "HealthRatio": safe_float(self_repair.get("healthRatio")),
            }

    return result


def _build_resource_network_from_irp(irp):
    """Build ResourceNetwork array from ItemResourceComponentParams."""
    states_data = irp.get("states", {})
    if not states_data:
        return []

    # states can be a single dict or a list of dicts
    state_list = states_data
    if isinstance(states_data, dict):
        # Check if it has a single state or multiple
        if "ItemResourceState" in states_data:
            state_obj = states_data["ItemResourceState"]
            if isinstance(state_obj, list):
                state_list = state_obj
            else:
                state_list = [state_obj]
        else:
            state_list = [states_data]

    result = []
    for state in state_list:
        if not isinstance(state, dict):
            continue

        entry = {}
        state_name = state.get("name", "Online")

        # Consumption
        deltas = state.get("deltas", {})
        consumption_list = []
        generation_list = []

        # Handle deltas that can be dict or list
        if isinstance(deltas, dict):
            for dk, dv in deltas.items():
                # dv can be a single dict or a list of dicts
                items_list = dv if isinstance(dv, list) else [dv]
                for delta_item in items_list:
                    if not isinstance(delta_item, dict):
                        continue
                    if "Consumption" in dk:
                        c = _extract_consumption(delta_item)
                        if c:
                            consumption_list.append(c)
                    elif "Generation" in dk:
                        g = _extract_generation(delta_item)
                        if g:
                            generation_list.append(g)
                    elif "Conversion" in dk:
                        conv = _extract_conversion(delta_item)
                        if conv:
                            entry["Conversion"] = [conv]

        if consumption_list:
            entry["Consumption"] = consumption_list
        if generation_list:
            entry["Generation"] = generation_list

        # Signatures
        sig_params = state.get("signatureParams", {})
        signatures = {}
        for sig_key, sig_name in [("EMSignature", "Electromagnetic"), ("IRSignature", "Infrared")]:
            sig = sig_params.get(sig_key, {})
            if sig:
                nominal = safe_float(sig.get("nominalSignature"))
                decay = safe_float(sig.get("decayRate", "0.15"))
                signatures[sig_name] = {"Nominal": nominal, "DecayRate": decay}
        if signatures:
            entry["Signatures"] = signatures

        # Power ranges
        power_ranges = state.get("powerRanges", {})
        if power_ranges:
            pr = {}
            for level in ["low", "medium", "high"]:
                pr_data = power_ranges.get(level, {})
                if pr_data:
                    pr[level.capitalize()] = {
                        "Start": safe_float(pr_data.get("start")),
                        "Modifier": safe_float(pr_data.get("modifier")),
                        "RegisterRange": pr_data.get("registerRange") in ("1", "true", True),
                    }
            if pr:
                entry["PowerRanges"] = pr

        # State goes last (after Consumption, Signatures, PowerRanges)
        entry["State"] = state_name

        if entry:
            result.append(entry)

    return result if result else None


def _extract_resource_amount(amount_data):
    """Extract resource amount and field name from resourceAmountPerSecond dict.

    Returns (field_name, value) where field_name is UnitPerSec, Segment, or MicroUnitPerSec.
    """
    if not amount_data:
        return "UnitPerSec", 0
    for k, v in amount_data.items():
        if isinstance(v, dict):
            if "standardResourceUnits" in v:
                return "UnitPerSec", safe_float(v["standardResourceUnits"])
            elif "units" in v and "Segment" in k:
                return "Segment", safe_float(v["units"])
            elif "microResourceUnits" in v:
                return "MicroUnitPerSec", safe_float(v["microResourceUnits"])
            # Fallback: try first numeric value
            for vk, vv in v.items():
                val = safe_float(vv)
                if val:
                    return "UnitPerSec", val
        else:
            return "UnitPerSec", safe_float(v)
    return "UnitPerSec", 0


def _extract_consumption(delta):
    """Extract consumption data from a delta entry."""
    consumption = delta.get("consumption", {})
    if not consumption:
        return None
    resource = consumption.get("resource", "")
    amount_data = consumption.get("resourceAmountPerSecond", {})
    field_name, value = _extract_resource_amount(amount_data)
    min_frac = safe_float(delta.get("minimumConsumptionFraction"))
    result = {
        "Resource": resource,
        "MinConsumptionFraction": min_frac,
        field_name: value,
    }
    return result


def _extract_generation(delta):
    """Extract generation data from a delta entry."""
    generation = delta.get("generation", {})
    if not generation:
        return None
    resource = generation.get("resource", "")
    amount_data = generation.get("resourceAmountPerSecond", {})
    field_name, value = _extract_resource_amount(amount_data)
    min_frac = safe_float(delta.get("minimumConsumptionFraction", "0"))
    result = {
        "Resource": resource,
        "MinConsumptionFraction": min_frac,
        field_name: value,
    }
    return result


def _extract_conversion(delta):
    """Extract conversion data from a delta entry."""
    gen = delta.get("generation", {})
    cons = delta.get("consumption", {})
    result = {}
    if gen:
        gen_res = gen.get("resource", "")
        gen_amount = gen.get("resourceAmountPerSecond", {})
        field_name, value = _extract_resource_amount(gen_amount)
        result["Generation"] = {"Resource": gen_res, field_name: value}
    if cons:
        cons_res = cons.get("resource", "")
        cons_amount = cons.get("resourceAmountPerSecond", {})
        cons_entry = {"Resource": cons_res}
        if cons_amount:
            field_name, value = _extract_resource_amount(cons_amount)
            cons_entry[field_name] = value
        result["Consumption"] = cons_entry
    min_frac = safe_float(delta.get("minimumConsumptionFraction"))
    result["MinConsumptionFraction"] = min_frac
    return result if result else None


def _build_heat_controller_from_hc(hc):
    """Build HeatController from parsed heatController component data."""
    result = {
        "EnableHeat": hc.get("enableHeat", False),
        "InitialTemperature": hc.get("initialTemperature", -1),
        "PoweredAmbientCoolingMultiplier": hc.get("poweredAmbientCoolingMultiplier", 1),
        "MinOperatingTemperature": hc.get("minOperatingTemperature", 0),
        "MinCoolingTemperature": hc.get("minCoolingTemperature", 300),
    }
    ceq = hc.get("coolingEqualization", {})
    if ceq:
        result["CoolingEqualization"] = {
            "EqualizationRate": ceq.get("equalizationRate", 0),
            "TemperatureDifference": ceq.get("temperatureDifference", 0),
        }

    sig = hc.get("signature", {})
    result["Signature"] = {
        "EnableSignature": sig.get("enableSignature", False),
        "MinTemperatureForIR": sig.get("minTemperatureForIR", 250),
        "TemperatureToIR": sig.get("temperatureToIR", 0),
        "StartIREmission": 0.0,
    }

    overheat = hc.get("overheat", {})
    result["Overheat"] = {
        "EnableOverheat": overheat.get("enableOverheat", False),
        "MaxTemperature": overheat.get("maxTemperature", 0),
        "WarningTemperature": overheat.get("warningTemperature", 0),
        "RecoveryTemperature": overheat.get("recoveryTemperature", 0),
    }

    return result


def _build_heat_controller_from_heat(heat):
    """Build HeatController from EntityComponentHeatConnection."""
    return {
        "MinOperatingTemperature": heat.get("minTemperature", 0),
        "MinCoolingTemperature": heat.get("startCoolingTemperature", 300),
        "Signature": {
            "MinTemperatureForIR": heat.get("startIRTemperature", 250),
            "TemperatureToIR": heat.get("temperatureToIR", 0),
        },
        "Overheat": {
            "MaxTemperature": heat.get("maxTemperature", 0),
            "WarningTemperature": heat.get("overheatTemperature", 0),
            "RecoveryTemperature": heat.get("recoveryTemperature", 0),
        },
    }


def _build_weapon_data(components, ctx):
    """Build Weapon object with Ammunition, Firing modes, Consumption."""
    weapon = components.get("weapon", {})
    ammo_comp = components.get("ammo", {})

    result = {}

    # Firing modes
    firing_modes = weapon.get("firingModes", [])
    if firing_modes:
        firing = []
        for mode in firing_modes:
            fire_type = mode.get("fireType", "single")
            shot_count = mode.get("shotCount", 0)
            # Burst type includes shot count: "burst 1", "burst 3"
            if fire_type == "burst" and shot_count:
                fire_type = f"burst {shot_count}"

            # Compute effective RPM for charged weapons
            rpm = float(mode.get("fireRate", 0))
            if fire_type == "charged" and rpm > 0:
                charge_time = mode.get("chargeTime", 0)
                cooldown_time = mode.get("cooldownTime", 0)
                if charge_time:
                    fire_interval = 60.0 / rpm
                    # Use cooldownTime if it exceeds the fire interval
                    recovery = max(fire_interval, cooldown_time) if cooldown_time else fire_interval
                    cycle_time = charge_time + recovery
                    rpm = round(60.0 / cycle_time, 1) if cycle_time > 0 else rpm

            fm = {
                "Name": mode.get("name", ""),
                "LocalisedName": ctx.resolve_name(mode.get("localisedName", "")),
                "RoundsPerMinute": rpm,
                "FireType": fire_type,
                "AmmoPerShot": float(mode.get("ammoCost", 1)),
                "PelletsPerShot": float(mode.get("pelletCount", 1)),
                "HeatPerShot": float(mode.get("heatPerShot", 0)),
                "WearPerShot": float(mode.get("wearPerShot", 0)),
            }
            # ShotPerAction (burst count)
            if shot_count:
                fm["ShotPerAction"] = float(shot_count)

            # SpinUp/SpinDown for rapid fire (gatling)
            if mode.get("spinUpTime"):
                fm["SpinUpTime"] = float(mode["spinUpTime"])
            if mode.get("spinDownTime"):
                fm["SpinDownTime"] = float(mode["spinDownTime"])

            # FireChargedParameters for charged weapons
            if fire_type == "charged" and mode.get("chargeTime"):
                fcp = {
                    "ChargeTime": float(mode.get("chargeTime", 0)),
                    "OverchargeTime": float(mode.get("overchargeTime", 0)),
                    "OverchargedTime": float(mode.get("overchargedTime", 0)),
                    "Cooldown": float(mode.get("cooldownTime", 0)),
                    "FireOnFullCharge": mode.get("fireOnFullCharge", False),
                    "FireOnlyOnFullCharge": mode.get("fireOnlyOnFullCharge", False),
                }
                cm = mode.get("chargeModifiers")
                if cm:
                    fcp["Modifiers"] = {
                        "FireRateMultiplier": cm.get("fireRateMultiplier", 1.0),
                        "ProjectileSpeedMultiplier": cm.get("projectileSpeedMultiplier", 1.0),
                        "DamageMultiplier": cm.get("damageMultiplier", 1.0),
                        "DamageOverTimeMultiplier": cm.get("damageOverTimeMultiplier", 1.0),
                    }
                fm["FireChargedParameters"] = fcp

            spread = mode.get("spread")
            if spread:
                fm["Spread"] = {
                    "Min": spread.get("min", 0),
                    "Max": spread.get("max", 0),
                    "FirstAttack": spread.get("firstAttack", 0),
                    "PerAttack": spread.get("attack", 0),
                    "Decay": spread.get("decay", 0),
                }
            firing.append(fm)
        result["Firing"] = firing

    # Ammunition (from AmmoParams cross-reference)
    ammo_guid = ammo_comp.get("ammoParamsRecord", "")
    ammo_data = ctx.get_ammo(ammo_guid)
    if ammo_data:
        ammo = {
            "Speed": float(ammo_data.get("speed", 0)),
            "LifeTime": float(ammo_data.get("lifetime", 0)),
            "Range": float(round(ammo_data.get("speed", 0) * ammo_data.get("lifetime", 0))),
            "Size": float(ammo_data.get("size", 0)),
        }
        # Explosion radius
        exp_min = ammo_data.get("explosionRadiusMin")
        exp_max = ammo_data.get("explosionRadiusMax")
        if exp_min:
            ammo["ExplosionRadiusMin"] = float(exp_min)
        if exp_max:
            ammo["ExplosionRadiusMax"] = float(exp_max)

        ammo["Capacity"] = float(ammo_comp.get("maxAmmoCount", 0))

        pen = ammo_data.get("penetration", {})
        if pen:
            ammo["Penetration"] = {
                "BasePenetrationDistance": float(pen.get("basePenetrationDistance", 0)),
                "NearRadius": float(pen.get("nearRadius", 0)),
                "FarRadius": float(pen.get("farRadius", 0)),
            }
        dmg = ammo_data.get("damage", {})
        impact = {}
        if dmg:
            for key in ["physical", "energy", "distortion", "thermal", "biochemical", "stun"]:
                val = dmg.get(key, 0)
                if val:
                    impact[key.capitalize()] = float(val)
        ammo["ImpactDamage"] = impact

        det_dmg = ammo_data.get("detonationDamage", {})
        if det_dmg:
            det = {}
            for key in ["physical", "energy", "distortion"]:
                val = det_dmg.get(key, 0)
                if val:
                    det[key.capitalize()] = val
            if det:
                ammo["DetonationDamage"] = det

        result["Ammunition"] = ammo

        # Compute DPS for each firing mode (always include DamagePerShot/DamagePerSecond)
        # Use detonation damage for DPS if impact damage is negligible
        dps_source = dmg if dmg else {}
        total_impact = sum(abs(v) for v in (dmg or {}).values() if isinstance(v, (int, float)))
        total_det = sum(abs(v) for v in (det_dmg or {}).values() if isinstance(v, (int, float)))
        if total_impact < 0.01 and total_det > 0:
            dps_source = det_dmg or {}

        if firing_modes:
            for fm in result.get("Firing", []):
                rpm = fm.get("RoundsPerMinute", 0)
                pellets = fm.get("PelletsPerShot", 1)
                fm["DamagePerShot"] = {}
                fm["DamagePerSecond"] = {}
                if dps_source:
                    for key in ["physical", "energy", "distortion", "thermal"]:
                        val = dps_source.get(key, 0)
                        if val:
                            k = key.capitalize()
                            dps_val = round(val * pellets, 2)
                            if dps_val:
                                fm["DamagePerShot"][k] = dps_val
                                fm["DamagePerSecond"][k] = round(dps_val * rpm / 60.0, 2) if rpm else 0.0

    # Modifiers from gimbal mode modifier record
    gimbal_guid = weapon.get("gimbalModeModifierRecord")
    if gimbal_guid:
        gm = ctx.get_gimbal_modifier(gimbal_guid)
        frm = gm["fireRateMultiplier"] if gm and gm.get("fireRateMultiplier") else 1.0
        result["Modifiers"] = {
            "FireRateMultiplier": {
                "Precision": frm,
                "Target": frm,
                "Gimbal": frm,
            },
        }

    # Consumption from weapon regen consumer params
    regen = weapon.get("regenConsumer")
    consumption = {}
    if regen:
        if regen.get("requestedRegenPerSec"):
            consumption["RequestedRegenPerSec"] = regen["requestedRegenPerSec"]
        if regen.get("regenerationCooldown"):
            consumption["Cooldown"] = regen["regenerationCooldown"]
        if regen.get("regenerationCostPerBullet"):
            consumption["CostPerBullet"] = regen["regenerationCostPerBullet"]
        if regen.get("requestedAmmoLoad"):
            consumption["RequestedAmmoLoad"] = regen["requestedAmmoLoad"]
        if regen.get("maxAmmoLoad"):
            consumption["MaxAmmo"] = regen["maxAmmoLoad"]
        if regen.get("maxRegenPerSec"):
            consumption["MaxRegenPerSec"] = regen["maxRegenPerSec"]
    if consumption:
        result["Consumption"] = consumption

    # HeatParameters from SWeaponSimplifiedHeatParams
    shp = weapon.get("simplifiedHeat")
    if shp:
        result["HeatParameters"] = {
            "MinTemp": shp.get("minTemperature", 0.0),
            "OverheatTemp": shp.get("overheatTemperature", 100.0),
            "CoolingPerSecond": shp.get("coolingPerSecond", 0.0),
            "TimeTillCoolingStarts": shp.get("timeTillCoolingStarts", 0.0),
            "OverheatFixTime": shp.get("overheatFixTime", 0.0),
            "TempAfterOverheatFix": shp.get("temperatureAfterOverheatFix", 0.0),
        }

    return result if result else None


def _resolve_fps_ammo(weapon_data, default_loadout, ctx):
    """Resolve FPS weapon ammo from the magazine in the default loadout."""
    for entry in default_loadout:
        pn = entry.get("portName", "").lower()
        if "magazine" not in pn and "ammo" not in pn:
            continue

        cn = entry.get("entityClassName", "")
        ref = entry.get("entityClassReference", "")

        resolved = cn
        if not cn and ref:
            resolved = ctx.resolve_guid(ref)
        if not resolved:
            continue

        mag_item = ctx.get_item(resolved)
        if not mag_item:
            continue

        mag_ammo = mag_item.get("components", {}).get("ammo", {})
        ammo_guid = mag_ammo.get("ammoParamsRecord", "")
        ammo_data = ctx.get_ammo(ammo_guid)

        if ammo_data:
            ammo = {
                "Speed": ammo_data.get("speed", 0),
                "LifeTime": ammo_data.get("lifetime", 0),
                "Range": ammo_data.get("speed", 0) * ammo_data.get("lifetime", 0),
                "Size": ammo_data.get("size", 0),
                "Capacity": mag_ammo.get("maxAmmoCount", 0),
            }
            pen = ammo_data.get("penetration", {})
            if pen:
                ammo["Penetration"] = {
                    "BasePenetrationDistance": pen.get("basePenetrationDistance", 0),
                    "NearRadius": pen.get("nearRadius", 0),
                    "FarRadius": pen.get("farRadius", 0),
                }
            dmg = ammo_data.get("damage", {})
            if dmg:
                impact = {}
                for key in ["physical", "energy", "distortion", "thermal"]:
                    val = dmg.get(key, 0)
                    if val:
                        impact[key.capitalize()] = val
                if impact:
                    ammo["ImpactDamage"] = impact

            det_dmg = ammo_data.get("detonationDamage", {})
            if det_dmg:
                det = {}
                for key in ["physical", "energy", "distortion"]:
                    val = det_dmg.get(key, 0)
                    if val:
                        det[key.capitalize()] = val
                if det:
                    ammo["DetonationDamage"] = det

            drop = ammo_data.get("damageDrop", {})
            if drop:
                ammo["DamageDrop"] = {
                    "MinDistance": drop.get("minDistance", {}),
                    "DropPerMeter": drop.get("dropPerMeter", {}),
                    "MinDamage": drop.get("minDamage", {}),
                }

            weapon_data["Ammunition"] = ammo

            # Compute DPS for firing modes
            if dmg and weapon_data.get("Firing"):
                for fm in weapon_data["Firing"]:
                    rpm = fm.get("RoundsPerMinute", 0)
                    pellets = fm.get("PelletsPerShot", 1)
                    fm["DamagePerShot"] = {}
                    fm["DamagePerSecond"] = {}
                    for key in ["physical", "energy", "distortion", "thermal"]:
                        val = dmg.get(key, 0)
                        if val:
                            k = key.capitalize()
                            fm["DamagePerShot"][k] = val * pellets
                            fm["DamagePerSecond"][k] = round(val * pellets * rpm / 60.0, 2) if rpm else 0

        break  # Only process first magazine


def _build_shield_data(shield):
    """Build Shield object with full resistance/absorption data."""
    result = {
        "Health": shield.get("maxShieldHealth", 0),
        "RegenRate": shield.get("maxShieldRegen", 0),
        "DownedDelay": shield.get("downedRegenDelay", 0),
        "DamagedDelay": shield.get("damagedRegenDelay", 0),
    }

    if "reservePool" in shield:
        rp = shield["reservePool"]
        result["ReservePool"] = {
            "InitialHealthRatio": rp.get("initialHealthRatio", rp.get("InitialHealthRatio", 0)),
            "MaxHealthRatio": rp.get("maxHealthRatio", rp.get("MaxHealthRatio", 0)),
            "RegenRateRatio": rp.get("regenRateRatio", rp.get("RegenRateRatio", 0)),
            "DrainRateRatio": rp.get("drainRateRatio", rp.get("DrainRateRatio", 0)),
        }

    if "resistance" in shield:
        result["Resistance"] = _capitalize_damage_ranges(shield["resistance"])

    if "absorption" in shield:
        result["Absorption"] = _capitalize_damage_ranges(shield["absorption"])

    return result


def _capitalize_damage_ranges(data):
    """Capitalize damage type keys in min/max range dicts."""
    result = {}
    for key, val in data.items():
        cap_key = key.capitalize() if key[0].islower() else key
        if isinstance(val, dict):
            result[cap_key] = {
                "Minimum": val.get("min", 0),
                "Maximum": val.get("max", 0),
            }
        else:
            result[cap_key] = val
    return result


def _build_ports(ports, parent_tags=None, ctx=None, default_loadout=None):
    """Build Ports array for items."""
    # Build lookup from defaultLoadout entries by portName
    dl_by_port = {}
    if default_loadout:
        for dl_entry in default_loadout:
            pn = dl_entry.get("portName", "")
            if pn:
                dl_by_port[pn] = dl_entry

    result = []
    for port in ports:
        port_name = port.get("name", "")
        p = {
            "PortName": port_name,
            "MinSize": port.get("minSize", 0),
            "MaxSize": port.get("maxSize", 0),
        }
        if port.get("types"):
            p["Types"] = port["types"]

        # Loadout and InstalledItem — first from port's own defaultLoadout/Ref,
        # then from the item's SEntityComponentDefaultLoadoutParams
        loadout_class = port.get("defaultLoadout", "")
        loadout_ref = port.get("defaultLoadoutRef", "")

        # If not in port def, check defaultLoadout component
        if not loadout_class and not loadout_ref and port_name in dl_by_port:
            dl_entry = dl_by_port[port_name]
            loadout_class = dl_entry.get("entityClassName", "")
            loadout_ref = dl_entry.get("entityClassReference", "")

        # Get children from defaultLoadout for passing to InstalledItem
        dl_children = dl_by_port.get(port_name, {}).get("children", []) if dl_by_port else []

        if loadout_class and ctx:
            p["Loadout"] = loadout_class
            installed_record = ctx.get_item(loadout_class)
            if installed_record:
                p["InstalledItem"] = build_std_item(installed_record, ctx, dl_children, nested=True)
        elif loadout_ref and loadout_ref != "00000000-0000-0000-0000-000000000000" and ctx:
            p["Loadout"] = loadout_ref
            resolved_class = ctx.resolve_guid(loadout_ref)
            if resolved_class:
                installed_record = ctx.get_item(resolved_class)
                if installed_record:
                    p["InstalledItem"] = build_std_item(installed_record, ctx, dl_children, nested=True)

        flags_str = port.get("flags", "")
        flags_lower = flags_str.lower() if isinstance(flags_str, str) else ""
        is_uneditable = "uneditable" in flags_lower
        # Only include Flags if non-empty
        if flags_str:
            flags = flags_str.split() if isinstance(flags_str, str) else flags_str
            p["Flags"] = flags
        if parent_tags:
            p["Tags"] = parent_tags

        # RequiredTags from port definition
        req_tags = port.get("requiredPortTags", "")
        if req_tags:
            p["RequiredTags"] = req_tags.split() if isinstance(req_tags, str) else req_tags

        # PortTags from port definition
        port_tags = port.get("portTags", "")
        if port_tags:
            p["PortTags"] = port_tags.split() if isinstance(port_tags, str) else port_tags

        # Only include Uneditable if true
        if is_uneditable:
            p["Uneditable"] = True
        if port.get("subPorts"):
            # Pass children from defaultLoadout for sub-ports
            dl_entry = dl_by_port.get(port_name, {})
            sub_dl = dl_entry.get("children", []) if dl_entry else []
            p["Ports"] = _build_ports(port["subPorts"], parent_tags, ctx, sub_dl)
        result.append(p)
    return result


def _build_armour(armor_data):
    """Build Armour object with proper casing matching the reference format."""
    result = {}

    defl = armor_data.get("damageDeflection", {})
    if defl:
        result["DamageDeflection"] = {
            "Physical": safe_float(defl.get("physical", 0)),
            "Energy": safe_float(defl.get("energy", 0)),
            "Distortion": safe_float(defl.get("distortion", 0)),
            "Thermal": safe_float(defl.get("thermal", 0)),
            "Biochemical": safe_float(defl.get("biochemical", 0)),
            "Stun": safe_float(defl.get("stun", 0)),
        }

    pen_red = armor_data.get("penetrationReduction")
    if pen_red is not None:
        result["PenetrationReduction"] = safe_float(pen_red)

    pen_abs = armor_data.get("penetrationAbsorption", {})
    if pen_abs:
        result["PenetrationAbsorption"] = {
            "Physical": safe_float(pen_abs.get("physical", 0)),
            "Energy": safe_float(pen_abs.get("energy", 0)),
            "Distortion": safe_float(pen_abs.get("distortion", 0)),
            "Thermal": safe_float(pen_abs.get("thermal", 0)),
            "Biochemical": safe_float(pen_abs.get("biochemical", 0)),
            "Stun": safe_float(pen_abs.get("stun", 0)),
        }

    mults = armor_data.get("damageMultipliers", {})
    if mults:
        result["DamageMultipliers"] = {
            "Physical": safe_float(mults.get("physical", 1.0)),
            "Energy": safe_float(mults.get("energy", 1.0)),
            "Distortion": safe_float(mults.get("distortion", 1.0)),
            "Thermal": safe_float(mults.get("thermal", 1.0)),
            "Biochemical": safe_float(mults.get("biochemical", 1.0)),
            "Stun": safe_float(mults.get("stun", 1.0)),
        }

    sig = armor_data.get("signalMultipliers", {})
    if sig:
        result["SignalMultipliers"] = {
            "Electromagnetic": safe_float(sig.get("em", 1.0)),
            "Infrared": safe_float(sig.get("ir", 1.0)),
            "CrossSection": safe_float(sig.get("cs", 1.0)),
        }

    return result if result else None


def _build_missile_rack(ports, item_type):
    """Build MissileRack {Count, Size} from missile/bomb ports."""
    if not ports:
        return None
    base = item_type.split(".")[0] if item_type else ""
    if base not in ("MissileLauncher", "BombLauncher", "GroundVehicleMissileLauncher"):
        return None

    # Count = total number of ports on the launcher item
    count = len(ports)

    # Size from the first port with a missile/bomb type
    size = 0
    for p in ports:
        types = p.get("types", [])
        if any(t.startswith(("Missile", "Bomb")) for t in types):
            size = p.get("maxSize", 0)
            break
    if not size and ports:
        size = ports[0].get("maxSize", 0)

    return {"Count": count, "Size": size}


def _extract_angle_limits(limits):
    """Extract angle limits from standard angle limit params."""
    std = limits.get("SCItemTurretStandardAngleLimitParams", {})
    if std:
        return safe_float(std.get("LowestAngle", -180)), safe_float(std.get("HighestAngle", 180))
    return -180.0, 180.0


def _build_turret(turret_params):
    """Build Turret object with yaw/pitch axis rotation data."""
    ml = turret_params.get("movementList", {})
    joints = ml.get("SCItemTurretJointMovementParams", [])
    if isinstance(joints, dict):
        joints = [joints]

    yaw_data = None
    pitch_data = None

    for joint in joints:
        yaw = joint.get("yawAxis", {})
        if yaw:
            params = yaw.get("SCItemTurretJointMovementAxisParams", {})
            if params and not yaw_data:
                limits = params.get("angleLimits", {})
                low, high = _extract_angle_limits(limits)
                yaw_data = {
                    "Speed": safe_float(params.get("speed", 0)),
                    "TimeToFullSpeed": safe_float(params.get("acceleration_timeToFullSpeed", 0)),
                    "AccelerationDecay": safe_float(params.get("accelerationDecay", 0)),
                    "LowestAngle": low,
                    "HighestAngle": high,
                }

        pitch = joint.get("pitchAxis", {})
        if pitch:
            params = pitch.get("SCItemTurretJointMovementAxisParams", {})
            if params and not pitch_data:
                limits = params.get("angleLimits", {})
                low, high = _extract_angle_limits(limits)
                pitch_data = {
                    "Speed": safe_float(params.get("speed", 0)),
                    "TimeToFullSpeed": safe_float(params.get("acceleration_timeToFullSpeed", 0)),
                    "AccelerationDecay": safe_float(params.get("accelerationDecay", 0)),
                    "LowestAngle": low,
                    "HighestAngle": high,
                }

    result = {}
    if yaw_data:
        result["yawAxis"] = yaw_data
    if pitch_data:
        result["pitchAxis"] = pitch_data

    # OnlyUsableInRemoteCamera from remoteTurret params
    remote = turret_params.get("remoteTurret", {})
    remote_params = remote.get("SCItemTurretRemoteParams", {})
    if isinstance(remote_params, dict) and remote_params.get("turretOnlyUsableInRemoteCamera") == "1":
        result["OnlyUsableInRemoteCamera"] = True

    return result if result else None


def _build_shield_emitter(params):
    """Build ShieldEmitter from SCItemShieldEmitterParams."""
    result = {}
    ft = params.get("FaceType", "")
    if ft:
        result["FaceType"] = ft
    max_realloc = params.get("MaxReallocation")
    if max_realloc is not None:
        result["MaxReallocation"] = safe_float(max_realloc)
    reconfig = params.get("ReconfigurationCooldown")
    if reconfig is not None:
        result["ReconfigurationCooldown"] = safe_float(reconfig)
    max_elec = params.get("MaxElectricalChargeDamageRate")
    if max_elec is not None:
        result["MaxElectricalChargeDamageRate"] = safe_float(max_elec)
    result["Curves"] = {}
    return result


def _build_quantum_drive(qd):
    """Build QuantumDrive with proper format matching reference output."""
    result = {}

    # Direct float fields
    for src, dst in [("quantumFuelRequirement", "FuelRate"),
                     ("jumpRange", "JumpRange"),
                     ("disconnectRange", "DisconnectRange"),
                     ("calibrationRate", "CalibrationRate"),
                     ("calibrationDelayInSeconds", "CalibrationDelayInSeconds"),
                     ("calibrationProcessAngleLimit", "CalibrationProcessAngleLimit"),
                     ("calibrationWarningAngleLimit", "CalibrationWarningAngleLimit"),
                     ("spoolUpTime", "SpoolUpTime"),
                     ("cooldownTime", "CooldownTime"),
                     ("stageOneAccelRate", "StageOneAccelRate"),
                     ("stageTwoAccelRate", "StageTwoAccelRate"),
                     ("maxSpeed", "MaxSpeed"),
                     ("interdictionEffectTime", "InterdictionEffectTime"),
                     ("engageSpeed", "EngageSpeed"),
                     ("driveSpeed", "DriveSpeed")]:
        val = qd.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    # HeatRampUp
    for src, dst in [("heatEnergyPerSecond", "HeatEnergyPerSecond"),
                     ("minHeatForSpool", "MinHeatForSpool")]:
        val = qd.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    return result if result else None


def _build_ifcs(ifcs):
    """Build Ifcs from IFCSParams. Ref format: {MaxSpeed, SCMSpeed, TorqueImbalanceMultiplier, ...}"""
    result = {}
    for src, dst in [("maxSpeed", "MaxSpeed"), ("scmSpeed", "SCMSpeed")]:
        val = ifcs.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    # Direct float fields
    for src, dst in [("torqueImbalanceMultiplier", "TorqueImbalanceMultiplier"),
                     ("liftMultiplier", "LiftMultiplier"),
                     ("dragMultiplier", "DragMultiplier"),
                     ("precisionMinDistance", "PrecisionMinDistance"),
                     ("precisionMaxDistance", "PrecisionMaxDistance"),
                     ("precisionLandingMultiplier", "PrecisionLandingMultiplier"),
                     ("linearAccelDecay", "LinearAccelDecay"),
                     ("angularAccelDecay", "AngularAccelDecay"),
                     ("scmMaxDragMultiplier", "ScmMaxDragMultiplier")]:
        val = ifcs.get(src)
        if val is not None:
            result[dst] = safe_float(val)

    # MasterModes
    mm = {}
    boost_fwd = ifcs.get("boostSpeedForward")
    boost_bwd = ifcs.get("boostSpeedBackward")
    if boost_fwd is not None:
        mm["BoostSpeedForward"] = safe_float(boost_fwd)
    if boost_bwd is not None:
        mm["BoostSpeedBackward"] = safe_float(boost_bwd)

    ifcs_core = ifcs.get("ifcsCoreParams", {})
    spool = ifcs_core.get("spoolUpTime")
    if spool is not None:
        mm["SpoolUpTime"] = safe_float(spool)

    if mm:
        result["MasterModes"] = mm

    return result if result else None


def _build_radar(radar):
    """Build Radar from SCItemRadarComponentParams."""
    result = {}

    # AimAssist
    aa = radar.get("aimAssist", {})
    if isinstance(aa, dict) and aa:
        result["AimAssist"] = {
            "DistanceMin": safe_float(aa.get("distanceMinAssignment", aa.get("distanceMin", 0))),
            "DistanceMax": safe_float(aa.get("distanceMaxAssignment", aa.get("distanceMax", 0))),
            "OutsideRangeBufferDistance": safe_float(aa.get("outsideRangeBufferDistance", 0)),
        }

    # Signal detection types
    sd = radar.get("signatureDetection", {})
    sd_list = sd.get("SCItemRadarSignatureDetection", [])
    if isinstance(sd_list, dict):
        sd_list = [sd_list]

    # Sensitivity modifiers for ground
    sm = radar.get("sensitivityModifiers", {})
    ground_add = 0.0
    if isinstance(sm, dict):
        mod = sm.get("SCItemRadarSensitivityModifier", {})
        if isinstance(mod, dict):
            ground_add = safe_float(mod.get("sensitivityAddition", "0"))

    # Signal order: 0=IR, 1=EM, 2=CS, 3=unused, 4=RS
    signal_names = {0: "IR", 1: "EM", 2: "CS", 4: "RS"}
    for idx, name in signal_names.items():
        if idx < len(sd_list):
            entry = sd_list[idx]
            sens = safe_float(entry.get("sensitivity", "0"))
            piercing = safe_float(entry.get("deltaSignaturePierce", entry.get("piercing", "0")))
            passive = entry.get("permitPassiveDetection", "1") == "1"
            active = entry.get("permitActiveDetection", "1") == "1"
            result[name] = {
                "Sensitivity": sens,
                "GroundSensitivity": round(sens + ground_add, 4) if ground_add else 0.0,
                "Piercing": piercing,
                "PermitPassiveDetection": passive,
                "PermitActiveDetection": active,
            }

    return result if result else None


def _build_jump_drive(jd):
    """Build JumpDrive from SCItemJumpDriveParams."""
    result = {}
    for src, dst in [("alignmentRate", "AlignmentRate"),
                     ("alignmentDecayRate", "AlignmentDecayRate"),
                     ("tuningRate", "TuningRate"),
                     ("tuningDecayRate", "TuningDecayRate"),
                     ("fuelUsageEfficiencyMultiplier", "FuelUsageEfficiencyMultiplier")]:
        val = jd.get(src)
        if val is not None:
            result[dst] = safe_float(val)
    return result if result else None


def _build_emp(emp):
    """Build Emp from SCItemEMPParams."""
    return {
        "ChargeTime": safe_float(emp.get("chargeTime", 0)),
        "UnleashTime": safe_float(emp.get("unleashTime", 0)),
        "Damage": safe_float(emp.get("distortionDamage", 0)),
        "MinRadius": safe_float(emp.get("minEmpRadius", 0)),
        "MaxRadius": safe_float(emp.get("empRadius", 0)),
        "CooldownTime": safe_float(emp.get("cooldownTime", 0)),
    }


def _build_self_destruct(sd):
    """Build SelfDestruct from SSCItemSelfDestructComponentParams."""
    return {
        "Countdown": safe_float(sd.get("time", 0)),
        "Damage": safe_float(sd.get("damage", 0)),
        "MinRadius": safe_float(sd.get("minRadius", 0)),
        "MaxRadius": safe_float(sd.get("radius", 0)),
    }


def _build_quantum_interdiction(qi):
    """Build QuantumInterdiction from SCItemQuantumInterdictionGeneratorParams."""
    jammer = qi.get("jammerSettings", {})
    if isinstance(jammer, dict):
        jammer = jammer.get("SCItemQuantumJammerParams", jammer)
    pulse = qi.get("quantumInterdictionPulseSettings", {})
    if isinstance(pulse, dict):
        pulse = pulse.get("SCItemQuantumInterdictionPulseParams", pulse)
    result = {}
    if isinstance(jammer, dict):
        result["JammingRange"] = safe_float(jammer.get("jammerRange", 0))
        result["InterdictionRange"] = safe_float(pulse.get("radiusMeters", 0)) if isinstance(pulse, dict) else 0.0
    if isinstance(pulse, dict):
        result["ChargeTime"] = safe_float(pulse.get("chargeTimeSecs", 0))
        result["ActivationTime"] = safe_float(pulse.get("increaseChargeRateTimeSeconds", 0))
        result["DisperseChargeTime"] = safe_float(pulse.get("decreaseChargeRateTimeSeconds", 0))
        result["DischargeTime"] = safe_float(pulse.get("dischargeTimeSecs", 0))
        result["CooldownTime"] = safe_float(pulse.get("cooldownTimeSecs", 0))
    return result if result else None


def _build_mining_laser(mining, components):
    """Build MiningLaser from SEntityComponentMiningLaserParams + weapon firing modes."""
    result = {}
    result["ThrottleLerpSpeed"] = safe_float(mining.get("throttleLerpSpeed", 0))
    result["ThrottleMinimum"] = safe_float(mining.get("throttleMinimum", 0))

    # Modifiers from miningLaserModifiers
    mods = mining.get("miningLaserModifiers", {})
    if isinstance(mods, dict):
        for src, dst in [("resistanceModifier", "ResistanceModifier"),
                         ("laserInstability", "LaserInstability"),
                         ("optimalChargeWindowRateModifier", "OptimalWindowRateModifier"),
                         ("optimalChargeWindowSizeModifier", "OptimalChargeWindowModifier"),
                         ("inertMaterialsFilter", "InertMaterialsFilter")]:
            mod = mods.get(src, {})
            if isinstance(mod, dict):
                # FloatModifierMultiplicative has a "value" field
                inner = mod.get("FloatModifierMultiplicative", mod)
                if isinstance(inner, dict):
                    result[dst] = safe_float(inner.get("value", 0))

    # Firing modes from weapon
    weapon = components.get("weapon", {})
    firing_modes = weapon.get("firingModes", [])
    if firing_modes:
        firing = []
        for mode in firing_modes:
            fm = {"Mode": mode.get("name", ""), "FireType": mode.get("fireType", "")}
            firing.append(fm)
        if firing:
            result["Firing"] = firing

    return result if result else None


def _build_modifier(si, modifier_params, item_type):
    """Build Module or SalvageModifier from EntityComponentAttachableModifierParams."""
    modifiers = modifier_params.get("modifiers", {})

    if "Salvage" in item_type:
        # Check ItemWeaponModifiersParams for salvage data
        iwm = modifiers.get("ItemWeaponModifiersParams", {})
        entries = iwm.get("SItemSalvageModifierParams", [])
        if isinstance(entries, dict):
            entries = [entries]
        if not entries:
            entries = modifiers.get("SItemSalvageModifierParams", [])
            if isinstance(entries, dict):
                entries = [entries]
        if entries:
            si["SalvageModifier"] = [{
                "SpeedMultiplier": safe_float(e.get("speedMultiplier", 0)),
                "RadiusMultiplier": safe_float(e.get("radiusMultiplier", 0)),
                "ExtractionEfficiency": safe_float(e.get("extractionEfficiency", 0)),
            } for e in entries]
    else:
        # Module (mining consumable)
        charges = safe_int(modifier_params.get("charges", 0))
        iwm = modifiers.get("ItemMiningModifierParams", modifiers.get("ItemWeaponModifiersParams", {}))
        mod_entries = iwm.get("SMiningModifierParams", [])
        if isinstance(mod_entries, dict):
            mod_entries = [mod_entries]
        if not mod_entries:
            mod_entries = modifiers.get("SMiningModifierParams", [])
            if isinstance(mod_entries, dict):
                mod_entries = [mod_entries]
        mod_list = []
        for e in mod_entries:
            entry = {}
            for src, dst in [("laserInstability", "LaserInstability"),
                             ("resistanceModifier", "ResistanceModifier"),
                             ("optimalChargeWindowSizeModifier", "OptimalChargeWindowSizeModifier"),
                             ("optimalChargeWindowRateModifier", "OptimalChargeWindowRateModifier"),
                             ("shatterDamageModifier", "ShatterDamageModifier"),
                             ("clusterFactorModifier", "ClusterFactorModifier"),
                             ("catastrophicChargeWindowRateModifier", "CatastrophicChargeWindowRateModifier")]:
                val = e.get(src)
                if isinstance(val, dict):
                    inner = val.get("FloatModifierMultiplicative", val)
                    if isinstance(inner, dict):
                        inner = inner.get("value", 0)
                    entry[dst] = safe_float(inner)
                elif val is not None:
                    entry[dst] = safe_float(val)
                else:
                    entry[dst] = 0.0
            mod_list.append(entry)
        si["Module"] = {"Charges": charges, "Modifiers": mod_list}


def _build_tractor_beam(components):
    """Build TractorBeam from weapon firing modes for tractor/towing beam items."""
    weapon = components.get("weapon", {})
    modes = weapon.get("firingModes", [])

    result = {}
    tractor_list = []
    towing_list = []

    for mode in modes:
        name = mode.get("name", "").lower()
        entry = {"Mode": mode.get("name", "")}
        if "tow" in name:
            towing_list.append(entry)
        else:
            tractor_list.append(entry)

    # Tractor data comes from SCItemTractorBeamParams if present
    tb = components.get("SCItemTractorBeamParams", {})
    if isinstance(tb, dict) and tb:
        modes_data = tb.get("tractorModes", {})
        tractor_entries = modes_data.get("SCItemTractorBeamMode", [])
        if isinstance(tractor_entries, dict):
            tractor_entries = [tractor_entries]
        tractor_list = []
        for e in tractor_entries:
            tractor_list.append({
                "Mode": e.get("modeName", "TractorBeam"),
                "MinForce": safe_float(e.get("minForce", 0)),
                "MaxForce": safe_float(e.get("maxForce", 0)),
                "MinDistance": safe_float(e.get("minDistance", 0)),
                "MaxDistance": safe_float(e.get("maxDistance", 0)),
                "FullStrengthDistance": safe_float(e.get("fullStrengthDistance", 0)),
                "MaxAngle": safe_float(e.get("maxAngle", 0)),
                "MaxVolume": safe_float(e.get("maxVolume", 0)),
            })

    tow = components.get("SCItemTowingBeamParams", {})
    if isinstance(tow, dict) and tow:
        towing_list = [{
            "TowingForce": safe_float(tow.get("towingForce", 0)),
            "TowingMaxAcceleration": safe_float(tow.get("towingMaxAcceleration", 0)),
            "TowingMaxDistance": safe_float(tow.get("towingMaxDistance", 0)),
            "QuantumTowMassLimit": safe_float(tow.get("quantumTowMassLimit", 0)),
        }]

    if tractor_list:
        result["Tractor"] = tractor_list
    if towing_list:
        result["Towing"] = towing_list

    return result if result else None


def _build_bomb(bomb):
    """Build Bomb from SCItemBombParams."""
    result = {}

    # Explosion damage — key may be PascalCase or camelCase
    exp = bomb.get("ExplosionParams", bomb.get("explosionParams", {}))
    if isinstance(exp, dict):
        damage = {}
        # Damage fields directly on ExplosionParams
        for src, dst in [("DamagePhysical", "Physical"), ("DamageEnergy", "Energy"),
                         ("DamageDistortion", "Distortion")]:
            val = safe_float(exp.get(src, 0))
            if val:
                damage[dst] = val
        # Fallback: nested damage/DamageInfo
        if not damage:
            di = exp.get("damage", {})
            if isinstance(di, dict):
                dinfo = di.get("DamageInfo", di)
                if isinstance(dinfo, dict):
                    for src, dst in [("DamagePhysical", "Physical"), ("DamageEnergy", "Energy")]:
                        val = safe_float(dinfo.get(src, 0))
                        if val:
                            damage[dst] = val

        explosion = {}
        if damage:
            explosion["Damage"] = damage
        radius = safe_float(exp.get("maxRadius", 0))
        if radius:
            explosion["Radius"] = radius
        proximity = safe_float(bomb.get("projectileProximity", 0))
        explosion["Proximity"] = proximity

        if explosion:
            result["Explosion"] = explosion

    arm = safe_float(bomb.get("armTime", 0))
    if arm:
        result["ArmTime"] = arm
    ignite = safe_float(bomb.get("igniteTime", 0))
    if ignite:
        result["IgniteTime"] = ignite

    return result if result else None


def _build_missiles_controller(mc):
    """Build MissilesController from SCItemMissileControllerParams."""
    return {
        "LockAngleAtMin": safe_float(mc.get("lockAngleAtMin", 0)),
        "LockAngleAtMax": safe_float(mc.get("lockAngleAtMax", 0)),
        "MaxArmedMissiles": safe_float(mc.get("maxArmedMissiles", 0)),
        "LaunchCooldownTime": safe_float(mc.get("launchCooldownTime", 0)),
    }


def _build_cargo_fields(si, rc):
    """Build CargoGrid and CargoContainers from ResourceContainer."""
    cap = rc.get("capacity", {})
    scu = cap.get("SStandardCargoUnit", {}) if isinstance(cap, dict) else {}
    capacity = safe_float(scu.get("standardCargoUnits", 0)) if isinstance(scu, dict) else 0

    if capacity:
        si["CargoGrid"] = {
            "Capacity": capacity,
            "Width": 1.0,
            "Height": 0.0,
            "Depth": 0.0,
        }
        si["CargoContainers"] = {"Capacity": capacity}
