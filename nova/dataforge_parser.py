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
            "gimbal_modifiers": os.path.join(cache_dir, "parsed_gimbal_modifiers.json"),
        }

        if all(os.path.isfile(f) for f in cache_files.values()):
            print("  Loading cached parse results...")
            data = {}
            for key, path in cache_files.items():
                with open(path, "r", encoding="utf-8") as f:
                    data[key] = json.load(f)
            print(f"  Loaded {len(data['items'])} items, {len(data['vehicles'])} vehicles, "
                  f"{len(data['guids'])} GUIDs, {len(data['manufacturers'])} manufacturers, "
                  f"{len(data['ammo'])} ammo, {len(data['inventory'])} inventory, "
                  f"{len(data['gimbal_modifiers'])} gimbal modifiers")
            return (data["items"], data["vehicles"], data["guids"],
                    data["manufacturers"], data["ammo"], data["inventory"],
                    data["gimbal_modifiers"])

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

    start = time.time()
    entity_count = 0
    mfr_count = 0
    ammo_count = 0
    total_elements = 0
    inv_count = 0
    in_record = False  # Track if inside any top-level record that needs children preserved

    context = ET.iterparse(xml_path, events=("start", "end"))

    for event, elem in context:
        total_elements += 1

        if event == "start":
            elem_type = elem.get("__type")
            if elem_type in ("EntityClassDefinition", "SCItemManufacturer", "AmmoParams",
                              "InventoryContainer", "WeaponGimbalModeModifierDef"):
                in_record = True
            continue

        # event == "end"
        if total_elements % 4000000 == 0:
            elapsed = time.time() - start
            print(f"  {total_elements:,} elements | {entity_count} entities | "
                  f"{len(items_by_class)} items | {len(vehicles_by_class)} vehicles | "
                  f"{mfr_count} mfrs | {ammo_count} ammo | {elapsed:.0f}s")

        elem_type = elem.get("__type")

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
                cap_elem = elem.find(".//SStandardCargoUnit")
                if cap_elem is None:
                    cap_elem = elem.find(".//SMicroCargoUnit")
                capacity = 0
                if cap_elem is not None:
                    capacity = safe_float(cap_elem.get("standardCargoUnits",
                                          cap_elem.get("microSCU", "0")))
                    if cap_elem.tag == "SMicroCargoUnit":
                        capacity = capacity / 1000000.0  # microSCU to SCU

                # Fallback: compute SCU from interiorDimensions grid-fit
                if not capacity:
                    dim_elem = elem.find("interiorDimensions")
                    if dim_elem is not None:
                        dx = safe_float(dim_elem.get("x", "0"))
                        dy = safe_float(dim_elem.get("y", "0"))
                        dz = safe_float(dim_elem.get("z", "0"))
                        if dx and dy and dz:
                            capacity = int(dx / 1.25) * int(dy / 1.25) * int(dz / 1.25)

                inventory_containers[guid] = {"capacity": capacity}
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

        elif not in_record:
            elem.clear()

    elapsed = time.time() - start
    print(f"  Parse complete: {total_elements:,} elements, {entity_count} entities, "
          f"{mfr_count} manufacturers, {ammo_count} ammo, {inv_count} inventory in {elapsed:.0f}s")
    print(f"  Items: {len(items_by_class)}, Vehicles: {len(vehicles_by_class)}, GUIDs: {len(guid_to_class)}")

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
        }
        for filename, data in cache_data.items():
            with open(os.path.join(cache_dir, filename), "w", encoding="utf-8") as f:
                json.dump(data, f)
        print("  Done")

    return (items_by_class, vehicles_by_class, guid_to_class, manufacturers,
            ammo_params, inventory_containers, gimbal_modifiers)


def _parse_ammo_params(elem):
    """Parse an AmmoParams record for projectile data."""
    result = {
        "speed": safe_float(elem.get("speed")),
        "lifetime": safe_float(elem.get("lifetime")),
        "size": safe_int(elem.get("size")),
    }

    # Find BulletProjectileParams for damage data
    for bullet in elem.iter("BulletProjectileParams"):
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
                        for dt in ["Physical", "Energy", "Distortion"]:
                            v = safe_float(dmg_info.get(f"Damage{dt}"))
                            if v:
                                vals[dt] = v
                        if vals:
                            drop_result[key] = vals
            if drop_result:
                result["damageDrop"] = drop_result

        # Pierceability
        pierce = bullet.find("pierceabilityParams")
        if pierce is not None:
            result["maxPenetrationThickness"] = safe_float(pierce.get("maxPenetrationThickness"))

        break  # Only process first BulletProjectileParams

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
            }

        elif poly_type == "EntityComponentPowerConnection":
            components["power"] = _parse_power_connection(comp)

        elif poly_type == "EntityComponentHeatConnection":
            components["heat"] = _parse_heat_connection(comp)

        elif poly_type == "SItemPortContainerComponentParams":
            components["ports"] = _parse_port_container(comp)

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

        for stats_name in ["noPowerStats", "underpowerStats", "overpowerStats", "overclockedStats"]:
            stats_elem = conn.find(stats_name)
            if stats_elem is not None:
                result[stats_name] = {
                    "fireRate": safe_float(stats_elem.get("fireRate")),
                    "fireRateMultiplier": safe_float(stats_elem.get("fireRateMultiplier")),
                    "damageMultiplier": safe_float(stats_elem.get("damageMultiplier")),
                    "projectileSpeedMultiplier": safe_float(stats_elem.get("projectileSpeedMultiplier")),
                    "pellets": safe_int(stats_elem.get("pellets")),
                    "burstShots": safe_int(stats_elem.get("burstShots")),
                    "ammoCost": safe_int(stats_elem.get("ammoCost")),
                    "ammoCostMultiplier": safe_float(stats_elem.get("ammoCostMultiplier")),
                    "heatGenerationMultiplier": safe_float(stats_elem.get("heatGenerationMultiplier")),
                }

    # Firing modes from weapon action params
    # Track which elements are wrapped (inside sequence or charged) to avoid double-counting
    firing_modes = []
    wrapped_children = set()

    # First pass: find sequence wrappers — take only the first inner fire action
    for seq in comp.iter("SWeaponActionSequenceParams"):
        wrapped_children.add(id(seq))
        first_found = False
        for fire_type in ["SWeaponActionFireSingleParams", "SWeaponActionFireRapidParams",
                          "SWeaponActionFireBurstParams", "SWeaponActionFireChargedParams"]:
            for action in seq.iter(fire_type):
                wrapped_children.add(id(action))
                if not first_found:
                    mode = _parse_fire_action(action)
                    if mode:
                        mode["fireType"] = "sequence"
                        firing_modes.append(mode)
                        first_found = True

    # Second pass: find charged wrappers and their child fire actions
    for charged in comp.iter("SWeaponActionFireChargedParams"):
        if id(charged) in wrapped_children:
            continue
        wrapped_children.add(id(charged))
        # Parse the inner fire action (single/rapid/burst inside charged)
        found_inner = False
        for fire_type in ["SWeaponActionFireSingleParams", "SWeaponActionFireRapidParams",
                          "SWeaponActionFireBurstParams"]:
            for action in charged.iter(fire_type):
                mode = _parse_fire_action(action)
                if mode:
                    mode["fireType"] = "charged"
                    # Override name/localisedName with charged wrapper values
                    charged_name = charged.get("name", "")
                    charged_loc = charged.get("localisedName", "")
                    if charged_name:
                        mode["name"] = charged_name
                    if charged_loc:
                        mode["localisedName"] = charged_loc
                    # Copy charge params from the wrapper
                    mode["chargeTime"] = safe_float(charged.get("chargeTime"))
                    mode["overchargeTime"] = safe_float(charged.get("overchargeTime"))
                    mode["overchargedTime"] = safe_float(charged.get("overchargedTime"))
                    mode["cooldownTime"] = safe_float(charged.get("cooldownTime"))
                    mode["fireOnFullCharge"] = charged.get("fireAutomaticallyOnFullCharge") == "1"
                    mode["fireOnlyOnFullCharge"] = charged.get("fireOnlyOnFullCharge") == "1"
                    # maxChargeModifier stats
                    mcm = charged.find("maxChargeModifier")
                    if mcm is not None:
                        mode["chargeModifiers"] = {
                            "fireRateMultiplier": safe_float(mcm.get("fireRateMultiplier", "1")),
                            "projectileSpeedMultiplier": safe_float(mcm.get("projectileSpeedMultiplier", "1")),
                            "damageMultiplier": safe_float(mcm.get("damageMultiplier", "1")),
                            "damageOverTimeMultiplier": safe_float(mcm.get("damageOverTimeMultiplier", "1")),
                        }
                    firing_modes.append(mode)
                    wrapped_children.add(id(action))
                    found_inner = True
        if not found_inner:
            # Charged element itself has fire data
            mode = _parse_fire_action(charged)
            if mode:
                mode["fireType"] = "charged"
                firing_modes.append(mode)

    # Third pass: top-level fire actions (not inside any wrapper)
    for fire_type, ft_name in [("SWeaponActionFireSingleParams", "single"),
                                ("SWeaponActionFireRapidParams", "rapid"),
                                ("SWeaponActionFireBurstParams", "burst")]:
        for action in comp.iter(fire_type):
            if id(action) in wrapped_children:
                continue
            mode = _parse_fire_action(action)
            if mode:
                mode["fireType"] = ft_name
                firing_modes.append(mode)

    if firing_modes:
        result["firingModes"] = firing_modes

    return result


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
        "trackingSignalType": comp.get("trackingSignalType", ""),
        "lockTime": safe_float(comp.get("lockTime")),
        "lockRangeMax": safe_float(comp.get("lockRangeMax")),
        "lockRangeMin": safe_float(comp.get("lockRangeMin")),
        "lockAngle": safe_float(comp.get("lockAngle")),
    }

    explosion = comp.find("explosionParams")
    if explosion is not None:
        result["explosionDamage"] = safe_float(explosion.get("damage"))
        result["explosionRadius"] = safe_float(explosion.get("radius"))

    gcs = comp.find("GCS")
    if gcs is not None:
        result["maxSpeed"] = safe_float(gcs.get("maxSpeed"))

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
    port = {
        "name": elem.get("Name", elem.get("name", "")),
        "minSize": safe_int(elem.get("MinSize")),
        "maxSize": safe_int(elem.get("MaxSize")),
        "portTags": elem.get("PortTags", ""),
        "requiredPortTags": elem.get("RequiredPortTags", ""),
        "flags": elem.get("Flags", ""),
        "uneditable": safe_bool(elem.get("Uneditable")),
    }

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
                    if st and st != "UNDEFINED":
                        types.append(f"{t}.{st}")
                        has_subtypes = True
                if not has_subtypes:
                    types.append(t)
            else:
                # Fallback: check SubType attribute directly
                st = type_elem.get("SubType", type_elem.get("subType", ""))
                types.append(f"{t}.{st}" if st and st != "UNDEFINED" else t)
        port["types"] = types

    # Default loadout
    for entry in elem.iter("SItemPortLoadoutEntryParams"):
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


def _parse_default_loadout(comp):
    """Parse SEntityComponentDefaultLoadoutParams into a loadout tree."""

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
