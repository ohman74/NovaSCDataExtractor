# Star Citizen Item Data Sources Reference

This document catalogs the exact source of every field in the `stdItem` output format, tracing from the Game2.xml (DataForge) XML structure through the parser layers to the final builder output. The format matches SPViewer/NovaTools conventions.

## Overview

The data extraction pipeline follows this flow:

1. **DataForge (Game2.xml)** → EntityClassDefinition records with Components and AttachDef
2. **dataforge_parser.py** → stream parses XML, extracts components and item definitions
3. **stditem.py** → builds stdItem JSON with full component data and cross-references
4. **builders/ships.py** → ship-level aggregation of components

---

## CryXML-binary files (require conversion)

Many `.xml` files extracted from `Data.p4k` are **CryXML binary format**, not text XML — they have `.xml` extension but start with the magic bytes `CryXmlB`. These must be converted to readable text via `unforge.exe` before any XML parser can read them. `unforge.exe` is bundled at `tools/unforge.exe` and operates in-place on the file.

### Detection
A file is CryXML-binary if its first 8 bytes start with `b"CryXml"`. Text XML files start with `b"<"`. The converter at `nova/converter.py::convert_entities` inspects the file header and re-runs `unforge` on any .xml with the binary signature — even ones previously cached.

### Known directories containing CryXML-binary .xml files
These are listed in `nova/extractor.py::CRYXML_BINARY_DIRS` and scanned automatically during Stage 3 (`scan_cryxml_binaries`):

| Path (under `cache/Data/`) | Purpose |
|---|---|
| `Libs/Foundry/Records/entities/spaceships/` | Ship entity definitions (ports, vehicle params, components) |
| `Libs/Foundry/Records/entities/ground/` | Ground-vehicle entity definitions |
| `Scripts/Entities/Vehicles/Implementations/Xml/` | Vehicle implementation XMLs (hull mass, structural HP tree, thruster HP, port definitions) |

If a new source dir of CryXML-binary files is added later, append it to `CRYXML_BINARY_DIRS` — the scan-and-convert step will pick them up on the next run. Don't try to parse a binary .xml directly; always run the conversion first.

### Pipeline sequencing
The flow is:

1. **Stage 1 — Extract**: `unp4k.exe` unpacks `Data.p4k` into `cache/`. Files land as-is (some text, some CryXML-binary).
2. **Stage 2 — DCB convert**: `Game2.dcb` → `Game2.xml` (via `unforge`).
3. **Stage 3 — Entity collection + CryXML scan**: `get_entity_files` collects the curated ship/ground entity lists, then `scan_cryxml_binaries` walks `CRYXML_BINARY_DIRS` and adds anything else whose header shows it's still binary.
4. **Stage 4 — Convert CryXML to text**: all collected paths go through `convert_entities`, which `unforge`s each binary file in place.
5. **Stage 5+**: parsers/builders consume now-readable text XML.

The conversion is idempotent — running the pipeline again after a fresh extract won't re-convert already-text files (the magic-byte check gates the conversion).

---

## Top-Level Item Fields

### ClassName
- **Target**: `stdItem.ClassName`
- **Source**: `EntityClassDefinition.tag` (after "." split)
- **Parser**: `dataforge_parser._parse_entity_record()` line 363
- **Builder**: `stditem.build_std_item()` line 253
- **Transformation**: Direct from parsed record

### Name
- **Target**: `stdItem.Name`
- **Source**: `EntityClassDefinition/Components/SItemDefinition/Localization@Name`
- **Parser**: `dataforge_parser._parse_attach_def()` line 527
- **Builder**: `stditem._resolve_item_name()` line 603-611
- **Transformation**: Resolved via `ctx.resolve_name()`, falls back to ClassName if unresolved or placeholder

### Description
- **Target**: `stdItem.Description`
- **Source**: `EntityClassDefinition/Components/SItemDefinition/Localization@Description`
- **Parser**: `dataforge_parser._parse_attach_def()` line 529
- **Builder**: `stditem.build_std_item()` line 250, 262-268
- **Transformation**: Via `_clean_description()` (line 614-635), removes metadata prefix and normalizes newlines; excluded if unresolved @-key or empty

### Classification
- **Target**: `stdItem.Classification`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@Type`, `@SubType`, plus `__path` context
- **Parser**: `dataforge_parser._parse_attach_def()` line 514-519
- **Builder**: `stditem._build_classification()` line 646-668
- **Transformation**: Prefix is "FPS" if "fps" in path (excluding "_fps_balance") or "personal" in type; otherwise "Ship". Appends Type/SubType parts, removes UNDEFINED suffix.

### Type (full_type)
- **Target**: `stdItem.Type`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@Type.SubType` (joined with ".")
- **Parser**: `dataforge_parser._parse_attach_def()` line 514-519
- **Builder**: `stditem.build_std_item()` line 245-248
- **Transformation**: `"{Type}.{SubType}"` if SubType exists, else just Type; preserves ".UNDEFINED" suffix

### Size
- **Target**: `stdItem.Size`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@Size`
- **Parser**: `dataforge_parser._parse_attach_def()` line 515, `safe_int()`
- **Builder**: `stditem.build_std_item()` line 254
- **Transformation**: Integer, direct assignment

### Grade
- **Target**: `stdItem.Grade`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@Grade`
- **Parser**: `dataforge_parser._parse_attach_def()` line 516, `safe_int()`
- **Builder**: `stditem.build_std_item()` line 255
- **Transformation**: Integer, direct assignment

### Class
- **Target**: `stdItem.Class`
- **Source**: Conditional logic based on description presence and type patterns; manufacturer code via SCItemManufacturer record
- **Parser**: Multiple: `_parse_attach_def()` (line 514-529), `stream_parse_dataforge()` (line 126-136 for manufacturers)
- **Builder**: `stditem.build_std_item()` line 337-396
- **Transformation**: Complex rule set:
  - Types in `_TYPES_NEVER_CLASS` → omit Class
  - Armor.Medium → only if ClassName in `_ARMOR_MEDIUM_WITH_CLASS`
  - MissileLauncher.MissileRack → omit if in `_MISSILERACK_WITHOUT_CLASS`
  - Turret.GunTurret → omit if in `_TURRETS_WITHOUT_CLASS`
  - For components (Shield, Cooler, etc.), set to manufacturer class via `MANUFACTURER_CLASS` dict (line 222-237)
  - Default: Class = "" if description is real localization key, else omit

### Manufacturer
- **Target**: `stdItem.Manufacturer`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@Manufacturer` (GUID) → cross-reference `SCItemManufacturer` record
- **Parser**: `dataforge_parser._parse_attach_def()` line 521-523, `stream_parse_dataforge()` line 126-136
- **Builder**: `stditem.build_std_item()` line 332-335, via `ctx.get_manufacturer()`
- **Transformation**: GUID lookup returns manufacturer name; omits if GUID is null/zero GUID

### Tags
- **Target**: `stdItem.Tags`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@Tags` (space-separated string)
- **Parser**: `dataforge_parser._parse_attach_def()` line 517
- **Builder**: `stditem.build_std_item()` line 269-271
- **Transformation**: Split on whitespace, filter empty strings; omit if empty list

### RequiredTags
- **Target**: `stdItem.RequiredTags`
- **Source**: `EntityClassDefinition/Components/SItemDefinition@RequiredTags` (space-separated string)
- **Parser**: `dataforge_parser._parse_attach_def()` line 518
- **Builder**: `stditem.build_std_item()` line 274-276
- **Transformation**: Split on whitespace; omit if empty

### Mass
- **Target**: `stdItem.Mass`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/PhysType/SEntityRigidPhysicsControllerParams@Mass`
- **Parser**: `dataforge_parser._parse_entity_record()` line 449-458
- **Builder**: `stditem.build_std_item()` line 285-325
- **Transformation**: Float value from `safe_float()`; omit for types in `_TYPES_NO_MASS`, base types in `_BASE_TYPES_NO_MASS`, or specific conditions (volume==1 placeholders, ship-integrated modules). Forced inclusion for items in `_MASS_FORCE_INCLUDE`.

### Volume
- **Target**: `stdItem.Volume`
- **Source**: `EntityClassDefinition/Components/SItemDefinition/.../SMicroCargoUnit@microSCU`
- **Parser**: `dataforge_parser._parse_attach_def()` line 532-534
- **Builder**: `stditem.build_std_item()` line 327-329
- **Transformation**: Integer from inventory occupancy; omit if zero/missing

---

## Durability Block

### Durability.Health
- **Target**: `stdItem.Durability.Health`
- **Source**: `EntityClassDefinition/Components/SHealthComponentParams@Health`
- **Parser**: `dataforge_parser._parse_health_params()` line 565-582
- **Builder**: `stditem._build_durability()` line 671-725, line 674
- **Transformation**: Direct float value from `safe_float()`

### Durability.DamageMultipliers
- **Target**: `stdItem.Durability.DamageMultipliers`
- **Source**: `EntityClassDefinition/Components/SHealthComponentParams/DamageResistance/{Physical|Energy|Distortion|Thermal|Biochemical|Stun}Resistance@Multiplier`
- **Parser**: `dataforge_parser._parse_health_params()` line 572-580
- **Builder**: `stditem._build_durability()` line 694-703
- **Transformation**: Capitalized damage type keys with float values; omit if zero or missing

### Durability.Distortion
- **Target**: `stdItem.Durability.Distortion`
- **Source**: `EntityClassDefinition/Components/SDistortionParams@{Maximum, DecayDelay, DecayRate, RecoveryRatio}`
- **Parser**: Generic component capture via `_elem_to_dict()` line 499, stored as `SDistortionParams`
- **Builder**: `stditem._build_durability()` line 678-692
- **Transformation**: Object with MaximumDamage, DecayDelay, DecayRate (rounded to 7 decimals), RecoveryTime (calculated as DecayDelay + effective_damage / DecayRate)

### Durability.Lifetime
- **Target**: `stdItem.Durability.Lifetime`
- **Source**: `EntityClassDefinition/Components/SDegradationParams/accumulators/SWearAccumulatorParams@MaxLifetimeHours`
- **Parser**: Generic component capture line 499; extracted in stditem line 416-424
- **Builder**: `stditem.build_std_item()` line 416-431, `stditem._build_durability()` line 675-676
- **Transformation**: Float hours from accumulated wear params; only included if degradation present

### Durability.Misfire
- **Target**: `stdItem.Durability.Misfire`
- **Source**: `EntityClassDefinition/Components/EntityComponentMisfireParams/misfires/SHostExplosionEffect@{explosionChance, explosionCountdown, healthCancelRatio}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem.build_std_item()` line 402-414, `stditem._build_durability()` line 705-713
- **Transformation**: Explosion sub-object with Chance, Countdown, HealthCancelRatio (floats)

### Durability.SelfRepair
- **Target**: `stdItem.Durability.SelfRepair`
- **Source**: `EntityClassDefinition/Components/ItemResourceComponentParams/selfRepair@{maxRepairCount, timeToRepair, healthRatio}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_durability()` line 716-723
- **Transformation**: Object with MaxRepair, TimeToRepair, HealthRatio (floats)

---

## HeatController Block

### HeatController.EnableHeat
- **Target**: `stdItem.HeatController.EnableHeat`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature@enable` (or SAttachableComponentParams derived heat, 0/1 string)
- **Parser**: `dataforge_parser._parse_entity_record()` line 461-495
- **Builder**: `stditem.build_std_item()` line 441-446, `stditem._build_heat_controller_from_hc()` line 904-936
- **Transformation**: Boolean from safe_bool(); default False

### HeatController.InitialTemperature
- **Target**: `stdItem.HeatController.InitialTemperature`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature@initialTemperature`
- **Parser**: `dataforge_parser._parse_entity_record()` line 465
- **Builder**: `stditem._build_heat_controller_from_hc()` line 908
- **Transformation**: Float; default -1

### HeatController.MinOperatingTemperature
- **Target**: `stdItem.HeatController.MinOperatingTemperature`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature/itemResourceParams@minOperatingTemperature`
- **Parser**: `dataforge_parser._parse_entity_record()` line 485
- **Builder**: `stditem._build_heat_controller_from_hc()` line 910
- **Transformation**: Float; default 0

### HeatController.MinCoolingTemperature
- **Target**: `stdItem.HeatController.MinCoolingTemperature`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature/itemResourceParams@minCoolingTemperature`
- **Parser**: `dataforge_parser._parse_entity_record()` line 486
- **Builder**: `stditem._build_heat_controller_from_hc()` line 911
- **Transformation**: Float; default 300

### HeatController.CoolingEqualization
- **Target**: `stdItem.HeatController.CoolingEqualization`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature/CoolingEqualizationRateAtTemperatureDifference@{coolingEqualizationRate, temperatureDifference}`
- **Parser**: `dataforge_parser._parse_entity_record()` line 468-473
- **Builder**: `stditem._build_heat_controller_from_hc()` line 913-918
- **Transformation**: Object with EqualizationRate, TemperatureDifference (floats)

### HeatController.Signature
- **Target**: `stdItem.HeatController.Signature`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature/signatureParams@{enable, minimumTemperatureForIR, temperatureToIR}`
- **Parser**: `dataforge_parser._parse_entity_record()` line 475-481
- **Builder**: `stditem._build_heat_controller_from_hc()` line 920-926
- **Transformation**: Object with EnableSignature (bool), MinTemperatureForIR (float), TemperatureToIR (float), StartIREmission (hardcoded 0.0)

### HeatController.Overheat
- **Target**: `stdItem.HeatController.Overheat`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature/itemResourceParams@{enableOverheat, overheatTemperature, overheatWarningTemperature, overheatRecoveryTemperature}`
- **Parser**: `dataforge_parser._parse_entity_record()` line 487-492
- **Builder**: `stditem._build_heat_controller_from_hc()` line 928-934
- **Transformation**: Object with EnableOverheat (bool), MaxTemperature, WarningTemperature, RecoveryTemperature (floats)

### HeatController.PoweredAmbientCoolingMultiplier
- **Target**: `stdItem.HeatController.PoweredAmbientCoolingMultiplier`
- **Source**: `EntityClassDefinition/Components/SEntityPhysicsControllerParams/temperature/itemResourceParams@poweredAmbientCoolingMultiplier`
- **Parser**: `dataforge_parser._parse_entity_record()` line 493
- **Builder**: `stditem._build_heat_controller_from_hc()` line 909
- **Transformation**: Float; default 1

---

## ResourceNetwork Block

### ResourceNetwork (array of state objects)
- **Target**: `stdItem.ResourceNetwork`
- **Source**: `EntityClassDefinition/Components/ItemResourceComponentParams/states/ItemResourceState[]/deltas/{Consumption|Generation|Conversion}*`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem.build_std_item()` line 433-438, `stditem._build_resource_network_from_irp()` line 728-819
- **Transformation**: Array of state objects, each with State name, Consumption[], Generation[], Signatures, PowerRanges, Conversion

### ResourceNetwork[].State
- **Target**: `stdItem.ResourceNetwork[].State`
- **Source**: `ItemResourceState@name` (or default "Online")
- **Parser**: Generic capture
- **Builder**: `stditem._build_resource_network_from_irp()` line 753, 814
- **Transformation**: String state name

### ResourceNetwork[].Consumption[]
- **Target**: `stdItem.ResourceNetwork[].Consumption[].Resource`
- **Source**: `ItemResourceComponentParams/states/ItemResourceState/deltas/{*Consumption*}/consumption@resource`
- **Parser**: Generic capture
- **Builder**: `stditem._build_resource_network_from_irp()` line 756-780, `_extract_consumption()` line 847-861
- **Transformation**: Array of consumption objects with Resource (string), UnitPerSec/MicroUnitPerSec/Segment (float), MinConsumptionFraction (float)

### ResourceNetwork[].Generation[]
- **Target**: `stdItem.ResourceNetwork[].Generation[].Resource`
- **Source**: `ItemResourceComponentParams/states/ItemResourceState/deltas/{*Generation*}/generation@resource`
- **Parser**: Generic capture
- **Builder**: `stditem._build_resource_network_from_irp()` line 756-784, `_extract_generation()` line 864-878
- **Transformation**: Array of generation objects with Resource (string), field name (UnitPerSec, etc.), MinConsumptionFraction

### ResourceNetwork[].Signatures
- **Target**: `stdItem.ResourceNetwork[].Signatures`
- **Source**: `ItemResourceState/signatureParams/{EMSignature|IRSignature}@{nominalSignature, decayRate}`
- **Parser**: Generic capture
- **Builder**: `stditem._build_resource_network_from_irp()` line 786-796
- **Transformation**: Object mapping signal type (Electromagnetic/Infrared) to {Nominal, DecayRate} (floats)

### ResourceNetwork[].PowerRanges
- **Target**: `stdItem.ResourceNetwork[].PowerRanges`
- **Source**: `ItemResourceState/powerRanges/{low|medium|high}@{start, modifier, registerRange}`
- **Parser**: Generic capture
- **Builder**: `stditem._build_resource_network_from_irp()` line 798-811
- **Transformation**: Object with low/medium/high keys, each containing Start, Modifier (floats), RegisterRange (bool from "1"/"true")

---

## Weapon Block

### Weapon.Ammunition
- **Target**: `stdItem.Weapon.Ammunition`
- **Source**: Cross-reference AmmoParams record via `SAmmoContainerComponentParams@ammoParamsRecord` GUID
- **Parser**: `dataforge_parser._parse_entity_record()` line 406-411, `_parse_ammo_params()` line 251-357
- **Builder**: `stditem._build_weapon_data()` line 956-1218, line 1108-1160
- **Transformation**: Object with Speed, LifeTime, Range (computed as speed×lifetime), Size, ImpactDamage, DetonationDamage, Penetration, ExplosionRadiusMin/Max, Capacity, DamageDrop (for SalvageHead items with impact damage)

### Weapon.Ammunition.ImpactDamage
- **Target**: `stdItem.Weapon.Ammunition.ImpactDamage`
- **Source**: `AmmoParams/.../BulletProjectileParams/damage/DamageInfo@{DamagePhysical, DamageEnergy, DamageDistortion, DamageThermal, DamageBiochemical, DamageStun}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 264-281
- **Builder**: `stditem._build_weapon_data()` line 1135-1142
- **Transformation**: Object with capitalized damage types (Physical, Energy, etc.) as keys; only non-zero values included

### Weapon.Ammunition.Penetration
- **Target**: `stdItem.Weapon.Ammunition.Penetration`
- **Source**: `AmmoParams/.../BulletProjectileParams/penetrationParams@{basePenetrationDistance, nearRadius, farRadius}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 306-312
- **Builder**: `stditem._build_weapon_data()` line 1128-1134
- **Transformation**: Object with BasePenetrationDistance, NearRadius, FarRadius (floats)

### Weapon.Firing[] (firing modes)
- **Target**: `stdItem.Weapon.Firing[]`
- **Source**: `EntityClassDefinition/Components/SCItemWeaponComponentParams/fireActions/{SWeaponActionFire*Params}` and wrapping elements (SWeaponActionSequenceParams, SWeaponActionFireChargedParams)
- **Parser**: `dataforge_parser._parse_weapon_params()` line 639-773
- **Builder**: `stditem._build_weapon_data()` line 963-1106
- **Transformation**: Complex parsing logic:
  - Sequence wrappers: first fire action inside gets fireType="sequence", includes sequenceEntries with timing
  - Charged wrappers: inner fire action with fireType="charged" + charge params
  - Top-level fire actions: single/rapid/burst
  - Beam/tractor/mining: specialized parsing
  - Effective RPM computed for charged/sequence modes based on charge time, cycle time, and entry delays

### Weapon.Firing[].Name
- **Target**: `stdItem.Weapon.Firing[].Name`
- **Source**: `SWeaponActionFire*Params@name`
- **Parser**: `dataforge_parser._parse_fire_action()` line 819-869
- **Builder**: `stditem._build_weapon_data()` line 1035
- **Transformation**: String, direct from action element; overridden for charged modes from wrapper

### Weapon.Firing[].LocalisedName
- **Target**: `stdItem.Weapon.Firing[].LocalisedName`
- **Source**: `SWeaponActionFire*Params@localisedName`
- **Parser**: `dataforge_parser._parse_fire_action()` line 822
- **Builder**: `stditem._build_weapon_data()` line 1031-1033
- **Transformation**: Resolved via `ctx.resolve_name()`, converted to "@LOC_PLACEHOLDER" if resolves to placeholder

### Weapon.Firing[].RoundsPerMinute
- **Target**: `stdItem.Weapon.Firing[].RoundsPerMinute`
- **Source**: `SWeaponActionFire*Params@fireRate` (base RPM)
- **Parser**: `dataforge_parser._parse_fire_action()` line 824
- **Builder**: `stditem._build_weapon_data()` line 979-1022
- **Transformation**: Float RPM; recomputed for charged (based on charge_time + cooldown) and sequence (based on sequence entries with delay units of "Seconds" or "RPM") modes

### Weapon.Firing[].FireType
- **Target**: `stdItem.Weapon.Firing[].FireType`
- **Source**: Derived from SWeaponAction* type and wrapper context
- **Parser**: `dataforge_parser._parse_weapon_params()` line 639-773
- **Builder**: `stditem._build_weapon_data()` line 971-978
- **Transformation**: One of: "single", "rapid", "burst", "charged", "sequence", "beam", "tractorbeam", "mining"

### Weapon.Firing[].AmmoPerShot
- **Target**: `stdItem.Weapon.Firing[].AmmoPerShot`
- **Source**: `SProjectileLauncher@ammoCost` (inside SWeaponActionFire*Params)
- **Parser**: `dataforge_parser._parse_fire_action()` line 844-859
- **Builder**: `stditem._build_weapon_data()` line 1039
- **Transformation**: Float; default 0 for beam/tractor, 1 for others

### Weapon.Firing[].PelletsPerShot
- **Target**: `stdItem.Weapon.Firing[].PelletsPerShot`
- **Source**: `SProjectileLauncher@pelletCount`
- **Parser**: `dataforge_parser._parse_fire_action()` line 847
- **Builder**: `stditem._build_weapon_data()` line 1040
- **Transformation**: Float; default 0 for beam/tractor, 1 for others

### Weapon.Firing[].HeatPerShot
- **Target**: `stdItem.Weapon.Firing[].HeatPerShot`
- **Source**: `SWeaponActionFire*Params@heatPerShot`
- **Parser**: `dataforge_parser._parse_fire_action()` line 825
- **Builder**: `stditem._build_weapon_data()` line 1041
- **Transformation**: Float; default 0

### Weapon.Firing[].WearPerShot
- **Target**: `stdItem.Weapon.Firing[].WearPerShot`
- **Source**: `SWeaponActionFire*Params@wearPerShot`
- **Parser**: `dataforge_parser._parse_fire_action()` line 826
- **Builder**: `stditem._build_weapon_data()` line 1042
- **Transformation**: Float; default 0

### Weapon.Firing[].ShotPerAction
- **Target**: `stdItem.Weapon.Firing[].ShotPerAction`
- **Source**: `SWeaponActionFireBurstParams@shotCount`
- **Parser**: `dataforge_parser._parse_fire_action()` line 831-833
- **Builder**: `stditem._build_weapon_data()` line 1044-1046
- **Transformation**: Float shot count; only included if non-zero (burst mode indicator)

### Weapon.Firing[].SpinUpTime / SpinDownTime
- **Target**: `stdItem.Weapon.Firing[].SpinUpTime`
- **Source**: `SWeaponActionFireRapidParams@{spinUpTime, spinDownTime}`
- **Parser**: `dataforge_parser._parse_fire_action()` line 836-841
- **Builder**: `stditem._build_weapon_data()` line 1049-1052
- **Transformation**: Float seconds; only included if present (gatling/rapid fire)

### Weapon.Firing[].FireChargedParameters
- **Target**: `stdItem.Weapon.Firing[].FireChargedParameters`
- **Source**: `SWeaponActionFireChargedParams@{chargeTime, overchargeTime, overchargedTime, cooldownTime, fireAutomaticallyOnFullCharge, fireOnlyOnFullCharge}` + `maxChargeModifier`
- **Parser**: `dataforge_parser._parse_weapon_params()` line 698-712
- **Builder**: `stditem._build_weapon_data()` line 1055-1072
- **Transformation**: Object with ChargeTime, OverchargeTime, OverchargedTime, Cooldown (floats), FireOnFullCharge, FireOnlyOnFullCharge (bools), and optional Modifiers sub-object

### Weapon.Firing[].Spread
- **Target**: `stdItem.Weapon.Firing[].Spread`
- **Source**: `SProjectileLauncher/spreadParams@{min, max, firstAttack, attack, decay}`
- **Parser**: `dataforge_parser._parse_fire_action()` line 851-859
- **Builder**: `stditem._build_weapon_data()` line 1074-1082
- **Transformation**: Object with Min, Max, FirstAttack, PerAttack, Decay (floats)

### Weapon.Firing[].Beam (for beam weapons)
- **Target**: `stdItem.Weapon.Firing[].Beam`
- **Source**: `SWeaponActionFireBeamParams@{hitType, hitRadius, minEnergyDraw, maxEnergyDraw, fullDamageRange, zeroDamageRange, heatPerSecond, wearPerSecond, chargeUpTime, chargeDownTime}`
- **Parser**: `dataforge_parser._parse_beam_action()` line 776-816
- **Builder**: `stditem._build_weapon_data()` line 1091-1102
- **Transformation**: Object with HitType (string), HitRadius, MinEnergyDraw, MaxEnergyDraw, FullDamageRange, ZeroDamageRange, HeatPerSecond, WearPerSecond, ChargeUpTime, ChargeDownTime (floats)

### Weapon.Firing[].DamagePerSecond (for beam weapons)
- **Target**: `stdItem.Weapon.Firing[].DamagePerSecond`
- **Source**: `SWeaponActionFireBeamParams/damagePerSecond/DamageInfo@{DamagePhysical, DamageEnergy, ...}`
- **Parser**: `dataforge_parser._parse_beam_action()` line 801-814
- **Builder**: `stditem._build_weapon_data()` line 1103-1104
- **Transformation**: Object with damage types as keys (capitalized), float values

### Weapon.Consumption
- **Target**: `stdItem.Weapon.Consumption`
- **Source**: `SCItemWeaponComponentParams/connectionParams/SWeaponRegenConsumerParams@{requestedRegenPerSec, regenerationCooldown, regenerationCostPerBullet, requestedAmmoLoad, maxAmmoLoad, maxRegenPerSec}`
- **Parser**: `dataforge_parser._parse_weapon_params()` line 594-604
- **Builder**: `stditem._build_weapon_data()` line 1187-1204
- **Transformation**: Object with RequestedRegenPerSec, Cooldown, CostPerBullet, RequestedAmmoLoad, MaxAmmo, MaxRegenPerSec (floats); only included if any value present

### Weapon.Modifiers
- **Target**: `stdItem.Weapon.Modifiers`
- **Source**: `SCItemWeaponComponentParams@gimbalModeModifierRecord` (GUID) → WeaponGimbalModeModifierDef record
- **Parser**: `dataforge_parser._parse_weapon_params()` line 590-592, `stream_parse_dataforge()` line 209-219
- **Builder**: `stditem._build_weapon_data()` line 1174-1185
- **Transformation**: Object with FireRateMultiplier sub-object (Precision, Target, Gimbal all set to same value from gimbal modifier fireRateMultiplier)

### Weapon.HeatParameters
- **Target**: `stdItem.Weapon.HeatParameters`
- **Source**: `SCItemWeaponComponentParams/connectionParams/SWeaponSimplifiedHeatParams@{minTemperature, overheatTemperature, coolingPerSecond, temperatureAfterOverheatFix, timeTillCoolingStarts, overheatFixTime}`
- **Parser**: `dataforge_parser._parse_weapon_params()` line 612-622
- **Builder**: `stditem._build_weapon_data()` line 1206-1216
- **Transformation**: Object with MinTemp, OverheatTemp, CoolingPerSecond, TimeTillCoolingStarts, OverheatFixTime, TempAfterOverheatFix (floats)

---

## Turret Block

### Turret.yawAxis / pitchAxis
- **Target**: `stdItem.Turret.yawAxis`, `stdItem.Turret.pitchAxis`
- **Source**: `SCItemTurretParams/movementList/SCItemTurretJointMovementParams/{yawAxis|pitchAxis}/SCItemTurretJointMovementAxisParams@{speed, acceleration_timeToFullSpeed, accelerationDecay, angleLimits}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_turret()` line 1525-1592
- **Transformation**: Object with Speed, TimeToFullSpeed, AccelerationDecay (floats), LowestAngle/HighestAngle (from angleLimits.SCItemTurretStandardAngleLimitParams or defaults -180/180). Pitch inherits angle limits from yaw (ref convention).

### Turret.OnlyUsableInRemoteCamera
- **Target**: `stdItem.Turret.OnlyUsableInRemoteCamera`
- **Source**: `SCItemTurretParams/remoteTurret/SCItemTurretRemoteParams@turretOnlyUsableInRemoteCamera`
- **Parser**: Generic component capture
- **Builder**: `stditem._build_turret()` line 1587-1590
- **Transformation**: Boolean; only included if true

---

## Shield Block

### Shield.Health
- **Target**: `stdItem.Shield.Health`
- **Source**: `SCItemShieldGeneratorParams@MaxShieldHealth`
- **Parser**: `dataforge_parser._parse_shield_params()` line 872-920
- **Builder**: `stditem._build_shield_data()` line 1307-1331
- **Transformation**: Float from safe_float()

### Shield.RegenRate
- **Target**: `stdItem.Shield.RegenRate`
- **Source**: `SCItemShieldGeneratorParams@MaxShieldRegen`
- **Parser**: `dataforge_parser._parse_shield_params()` line 876
- **Builder**: `stditem._build_shield_data()` line 1311
- **Transformation**: Float

### Shield.DownedDelay / DamagedDelay
- **Target**: `stdItem.Shield.DownedDelay`
- **Source**: `SCItemShieldGeneratorParams@{DownedRegenDelay, DamagedRegenDelay}`
- **Parser**: `dataforge_parser._parse_shield_params()` line 877-878
- **Builder**: `stditem._build_shield_data()` line 1312-1313
- **Transformation**: Float seconds

### Shield.ReservePool
- **Target**: `stdItem.Shield.ReservePool`
- **Source**: `SCItemShieldGeneratorParams@{ReservePoolInitialHealthRatio, ReservePoolMaxHealthRatio, ReservePoolRegenRateRatio, ReservePoolDrainRateRatio}`
- **Parser**: `dataforge_parser._parse_shield_params()` line 882-889
- **Builder**: `stditem._build_shield_data()` line 1316-1323
- **Transformation**: Object with InitialHealthRatio, MaxHealthRatio, RegenRateRatio, DrainRateRatio (floats)

### Shield.Resistance / Absorption
- **Target**: `stdItem.Shield.Resistance`
- **Source**: `SCItemShieldGeneratorParams/ShieldResistance/SShieldResistance[] @{Min, Max}` (6 entries ordered by damage type: Physical, Energy, Distortion, Thermal, Biochemical, Stun)
- **Parser**: `dataforge_parser._parse_shield_params()` line 895-905
- **Builder**: `stditem._build_shield_data()` line 1325-1329
- **Transformation**: Object with damage type keys mapping to {Minimum, Maximum} (floats). Absorption follows same structure.

---

## Missile Block

### Missile.Explosion
- **Target**: `stdItem.Missile.Explosion`
- **Source**: `SCItemMissileParams/explosionParams@{minRadius, maxRadius}` + `damage/DamageInfo@{DamagePhysical, DamageEnergy, ...}`
- **Parser**: `dataforge_parser._parse_missile_params()` line 991-1009
- **Builder**: `stditem._build_missile()` line 2234-2296
- **Transformation**: Object with Damage (dict of damage types), MinRadius, MaxRadius, Proximity (floats)

### Missile.TrackingSignal
- **Target**: `stdItem.Missile.TrackingSignal`
- **Source**: `SCItemMissileParams/targetingParams@trackingSignalType`
- **Parser**: `dataforge_parser._parse_missile_params()` line 1023
- **Builder**: `stditem._build_missile()` line 2260-2262
- **Transformation**: String signal type

### Missile.MinTrackingSignal / MinLockRatio / LockRate / LockTime / LockAngle / LockRangeMin/Max
- **Target**: `stdItem.Missile.*`
- **Source**: `SCItemMissileParams/targetingParams@{trackingSignalMin, minRatioForLock, lockIncreaseRate, lockTime, lockingAngle, lockRangeMin, lockRangeMax}`
- **Parser**: `dataforge_parser._parse_missile_params()` line 1020-1030
- **Builder**: `stditem._build_missile()` line 2264-2273
- **Transformation**: Float values from safe_float()

### Missile.Speed / FuelTankSize / MaxLifeTime / MaxDistance
- **Target**: `stdItem.Missile.Speed`
- **Source**: `SCItemMissileParams/GCSParams@{linearSpeed, fuelTankSize, boostPhaseDuration, ...}` (linearSpeed) + `SCItemMissileParams@maxLifetime`
- **Parser**: `dataforge_parser._parse_missile_params()` line 1011-1018, 984
- **Builder**: `stditem._build_missile()` line 2275-2284
- **Transformation**: Speed (float), FuelTankSize (float), MaxLifeTime (float), MaxDistance computed as Speed × MaxLifeTime

### Missile.ArmTime / IgniteTime / BoostPhaseDuration / TerminalPhaseEngagementTime/Angle / SafetyDistance
- **Target**: `stdItem.Missile.ArmTime`
- **Source**: `SCItemMissileParams@{armTime, igniteTime, boostPhaseDuration, terminalPhaseEngagementTime, terminalPhaseEngagementAngle, explosionSafetyDistance}`
- **Parser**: `dataforge_parser._parse_missile_params()` line 985-1018
- **Builder**: `stditem._build_missile()` line 2286-2294
- **Transformation**: Float seconds/angles

---

## Radar Block

### Radar.[IR|EM|CS|DB|RS|ID|Scan1|Scan2]
- **Target**: `stdItem.Radar.IR`, etc.
- **Source**: `SCItemRadarComponentParams/signatureDetection/SCItemRadarSignatureDetection[] @{sensitivity, piercing, permitPassiveDetection, permitActiveDetection}` (array indexed by signal type)
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_radar()` line 1861-1921
- **Transformation**: Object with Sensitivity, GroundSensitivity, Piercing (floats), PermitPassiveDetection, PermitActiveDetection (bools). Index mapping: 0=EM, 1=IR, 2=CS, 3=DB, 4=RS, 5=ID, 6=Scan1, 7=Scan2. Output order: IR, EM, CS, DB, RS, ID, Scan1, Scan2.

### Radar.[*].GroundSensitivity
- **Target**: `stdItem.Radar.IR.GroundSensitivity`
- **Source**: `SCItemRadarComponentParams/sensitivityModifiers/SCItemRadarSensitivityModifier@sensitivityAddition` + IR sensitivity
- **Parser**: Generic component capture
- **Builder**: `stditem._build_radar()` line 1880-1916
- **Transformation**: Computed as max(0, IR_sensitivity + ground_add)

---

## QuantumDrive Block

### QuantumDrive.FuelRate
- **Target**: `stdItem.QuantumDrive.FuelRate`
- **Source**: `SCItemQuantumDriveParams@quantumFuelRequirement`
- **Parser**: `dataforge_parser._parse_quantum_drive_params()` line 937
- **Builder**: `stditem._build_quantum_drive()` line 1614-1648
- **Transformation**: Float divided by 1,000,000 (raw data in 1e-6 units)

### QuantumDrive.JumpRange / DisconnectRange / InterdictionEffectTime
- **Target**: `stdItem.QuantumDrive.JumpRange`
- **Source**: `SCItemQuantumDriveParams@{jumpRange, disconnectRange, interdictionEffectTime}`
- **Parser**: `dataforge_parser._parse_quantum_drive_params()` line 938-940, 954-956
- **Builder**: `stditem._build_quantum_drive()` line 1631-1634
- **Transformation**: Float meters/seconds

### QuantumDrive.StandardJump / SplineJump
- **Target**: `stdItem.QuantumDrive.StandardJump`
- **Source**: `SCItemQuantumDriveParams/params` and `splineJumpParams` sub-elements with `@{driveSpeed, cooldownTime, stageOneAccelRate, stageTwoAccelRate, spoolUpTime}`
- **Parser**: `dataforge_parser._parse_quantum_drive_params()` line 944-977
- **Builder**: `stditem._build_quantum_drive()` line 1637-1646
- **Transformation**: Object with Speed, Cooldown, Stage1AccelerationRate, State2AccelerationRate, SpoolUpTime (floats)

---

## JumpDrive Block

### JumpDrive.AlignmentRate / TuningRate / FuelUsageEfficiencyMultiplier
- **Target**: `stdItem.JumpDrive.AlignmentRate`
- **Source**: `SCItemJumpDriveParams@{alignmentRate, alignmentDecayRate, tuningRate, fuelUsageEfficiencyMultiplier}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_jump_drive()` line 1924-1940
- **Transformation**: Float values. TuningDecayRate mirrors AlignmentDecayRate (ref convention).

---

## EMP Block

### Emp.ChargeTime / UnleashTime / Damage / MinRadius / MaxRadius / CooldownTime
- **Target**: `stdItem.Emp.ChargeTime`
- **Source**: `SCItemEMPParams@{chargeTime, unleashTime, distortionDamage, minEmpRadius, empRadius, cooldownTime}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_emp()` line 1943-1952
- **Transformation**: Float values; MaxRadius from empRadius attribute

---

## SelfDestruct Block

### SelfDestruct.Countdown / Damage / MinRadius / MaxRadius
- **Target**: `stdItem.SelfDestruct.Countdown`
- **Source**: `SSCItemSelfDestructComponentParams@{time, damage, minRadius, radius}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_self_destruct()` line 1955-1962
- **Transformation**: Float values; MaxRadius from radius attribute

---

## QuantumInterdiction Block

### QuantumInterdiction.JammingRange / InterdictionRange / ChargeTime / ActivationTime / DisperseChargeTime / DischargeTime / CooldownTime
- **Target**: `stdItem.QuantumInterdiction.JammingRange`
- **Source**: `SCItemQuantumInterdictionGeneratorParams/jammerSettings/SCItemQuantumJammerParams@jammerRange` + `quantumInterdictionPulseSettings/SCItemQuantumInterdictionPulseParams@{radiusMeters, chargeTimeSecs, activationPhaseDuration_seconds, disperseChargeTimeSeconds, dischargeTimeSecs, cooldownTimeSecs}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_quantum_interdiction()` line 1965-1983
- **Transformation**: Float values; radiusMeters maps to InterdictionRange

---

## MiningLaser Block

### MiningLaser.ThrottleLerpSpeed / ThrottleMinimum
- **Target**: `stdItem.MiningLaser.ThrottleLerpSpeed`
- **Source**: `SEntityComponentMiningLaserParams@{throttleLerpSpeed, throttleMinimum}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_mining_laser()` line 1986-1990
- **Transformation**: Float values

### MiningLaser.[ResistanceModifier|LaserInstability|OptimalWindowRateModifier|OptimalChargeWindowModifier|InertMaterialsFilter]
- **Target**: `stdItem.MiningLaser.ResistanceModifier`
- **Source**: `SEntityComponentMiningLaserParams/miningLaserModifiers/{resistanceModifier|laserInstability|...}/FloatModifierMultiplicative@value`
- **Parser**: Generic component capture
- **Builder**: `stditem._build_mining_laser()` line 2000-2014
- **Transformation**: Float values extracted from nested FloatModifierMultiplicative; only included if value present

### MiningLaser.Firing[]
- **Target**: `stdItem.MiningLaser.Firing[]`
- **Source**: `SCItemWeaponComponentParams/fireActions/SWeaponActionFireBeamParams` (mining laser uses beam fire type)
- **Parser**: `dataforge_parser._parse_weapon_params()` line 735-741, `_parse_beam_action()` line 776-816
- **Builder**: `stditem._build_mining_laser()` line 2016-2033
- **Transformation**: Array of firing modes with Mode, FireType="beam", LaserPower, FullDamageDistance, MinDamageDistance (floats)

---

## TractorBeam Block

### TractorBeam.Tractor[]
- **Target**: `stdItem.TractorBeam.Tractor[]`
- **Source**: `SCItemWeaponComponentParams/fireActions/SWeaponActionFireTractorBeamParams@{minForce, maxForce, minDistance, maxDistance, fullStrengthDistance, maxAngle, maxVolume}`
- **Parser**: `dataforge_parser._parse_weapon_params()` line 743-768
- **Builder**: `stditem._build_tractor_beam()` line 2138-2184
- **Transformation**: Array of tractor mode objects with Mode, MinForce, MaxForce, MinDistance, MaxDistance, FullStrengthDistance, MaxAngle, MaxVolume (floats)

### TractorBeam.Towing[]
- **Target**: `stdItem.TractorBeam.Towing[]`
- **Source**: `SWeaponActionFireTractorBeamParams/towingBeamParams/SWeaponActionFireTractorBeamTowingParams@{towingForce, towingMaxAcceleration, towingMaxDistance, quantumTowMassLimit}`
- **Parser**: `dataforge_parser._parse_weapon_params()` line 760-767
- **Builder**: `stditem._build_tractor_beam()` line 2160-2176
- **Transformation**: Array of towing mode objects with TowingForce, TowingMaxAcceleration, TowingMaxDistance, QuantumTowMassLimit (floats); always includes zero-filled towing entry if tractors present but no towing data

---

## Module Block

### Module.Charges
- **Target**: `stdItem.Module.Charges`
- **Source**: `EntityComponentAttachableModifierParams@charges`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_modifier()` line 2038-2136, line 2068
- **Transformation**: Integer charges count

### Module.Modifiers[]
- **Target**: `stdItem.Module.Modifiers[]`
- **Source**: Multiple sources within EntityComponentAttachableModifierParams/modifiers:
  - LaserPowerModifier: `ItemWeaponModifiersParams/weaponModifier/weaponStats@damageMultiplier`
  - Mining modifiers: `ItemMiningModifierParams/MiningLaserModifier` or `ItemMineableRockModifierParams/MiningLaserModifier` with nested FloatModifierMultiplicative values
  - InertMaterialsFilter: `MiningFilterItemModifierParams/filterParams/filterModifier/FloatModifierMultiplicative@value`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_modifier()` line 2070-2134
- **Transformation**: Array of modifier objects, each with one or more modifier fields (LaserPowerModifier, LaserInstability, ResistanceModifier, OptimalChargeWindowSizeModifier, OptimalChargeWindowRateModifier, ShatterDamageModifier, ClusterFactorModifier, CatastrophicChargeWindowRateModifier, InertMaterialsFilter, Duration)

---

## SalvageModifier Block

### SalvageModifier[]
- **Target**: `stdItem.SalvageModifier[]`
- **Source**: `EntityComponentAttachableModifierParams/modifiers/ItemWeaponModifiersParams/weaponModifier/weaponStats/salvageModifier@{salvageSpeedMultiplier, radiusMultiplier, extractionEfficiency}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_modifier()` line 2055-2065
- **Transformation**: Array with single entry containing SpeedMultiplier, RadiusMultiplier, ExtractionEfficiency (floats)

---

## CounterMeasure Block

### CounterMeasure.[Chaff|Flare]
- **Target**: `stdItem.CounterMeasure.Chaff`
- **Source**: Cross-reference AmmoParams record (via SAmmoContainerComponentParams@ammoParamsRecord) → CounterMeasureChaffParams or CounterMeasureFlareParams @{StartInfrared, EndInfrared, StartElectromagnetic, EndElectromagnetic, StartCrossSection, EndCrossSection, StartDecibel, EndDecibel}
- **Parser**: `dataforge_parser._parse_ammo_params()` line 340-355
- **Builder**: `stditem.build_std_item()` line 511-519
- **Transformation**: Object mapped by type name (Chaff or Flare) with IR start/end, EM start/end, CS start/end, dB start/end values (floats)

---

## Bomb Block

### Bomb.Explosion
- **Target**: `stdItem.Bomb.Explosion`
- **Source**: `SCItemBombParams/ExplosionParams@{DamagePhysical, DamageEnergy, DamageDistortion, maxRadius}` + `projectileProximity`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_bomb()` line 2187-2231
- **Transformation**: Object with Damage (dict of types), Radius, Proximity (floats)

### Bomb.ArmTime / IgniteTime
- **Target**: `stdItem.Bomb.ArmTime`
- **Source**: `SCItemBombParams@{armTime, igniteTime}`
- **Parser**: Generic component capture
- **Builder**: `stditem._build_bomb()` line 2224-2229
- **Transformation**: Float seconds; only included if non-zero

---

## MissilesController Block

### MissilesController.LockAngleAtMin / LockAngleAtMax / MaxArmedMissiles / LaunchCooldownTime
- **Target**: `stdItem.MissilesController.LockAngleAtMin`
- **Source**: `SCItemMissileControllerParams@{lockAngleAtMin, lockAngleAtMax, maxArmedMissiles, launchCooldownTime}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_missiles_controller()` line 2299-2306
- **Transformation**: Float values from safe_float()

---

## MissileRack Block

### MissileRack.Count / Size
- **Target**: `stdItem.MissileRack.Count`
- **Source**: Port container count + first missile port's maxSize
- **Parser**: `dataforge_parser._parse_port_container()` line 1132-1141, `_parse_item_port()` line 1144-1207
- **Builder**: `stditem._build_missile_rack()` line 1493-1514
- **Transformation**: Count = total number of ports; Size = maxSize of first missile/bomb port (or first port if no missile type found)

---

## Armour Block

### Armour.DamageDeflection
- **Target**: `stdItem.Armour.DamageDeflection`
- **Source**: `SCItemVehicleArmorParams/armorDeflection/deflectionValue/DamageInfo@{DamagePhysical, DamageEnergy, DamageDistortion, DamageThermal, DamageBiochemical, DamageStun}`
- **Parser**: `dataforge_parser._parse_armor_params()` line 1064-1078
- **Builder**: `stditem._build_armour()` line 1441-1454
- **Transformation**: Object with capitalized damage type keys mapping to float values

### Armour.PenetrationReduction / PenetrationAbsorption
- **Target**: `stdItem.Armour.PenetrationReduction`
- **Source**: `SCItemVehicleArmorParams/armorPenetrationResistance@basePenetrationReduction` + `penetrationAbsorptionForType/DamageInfo` for absorption by type
- **Parser**: `dataforge_parser._parse_armor_params()` line 1081-1095
- **Builder**: `stditem._build_armour()` line 1456-1469
- **Transformation**: PenetrationReduction is float; PenetrationAbsorption is object with damage type keys → float values

### Armour.DamageMultipliers
- **Target**: `stdItem.Armour.DamageMultipliers`
- **Source**: `SCItemVehicleArmorParams/damageMultiplier/DamageInfo@{DamagePhysical, ...}` or direct attributes on damageMultiplier element
- **Parser**: `dataforge_parser._parse_armor_params()` line 1039-1051
- **Builder**: `stditem._build_armour()` line 1471-1480
- **Transformation**: Object with capitalized damage type keys mapping to float values; defaults to 1.0 if missing

### Armour.SignalMultipliers
- **Target**: `stdItem.Armour.SignalMultipliers`
- **Source**: `SCItemVehicleArmorParams@{signalElectromagnetic, signalInfrared, signalCrossSection}`
- **Parser**: `dataforge_parser._parse_armor_params()` line 1054-1062
- **Builder**: `stditem._build_armour()` line 1482-1488
- **Transformation**: Object with Electromagnetic, Infrared, CrossSection keys mapping to float values

---

## ShieldEmitter Block

### ShieldEmitter.FaceType / MaxReallocation / ReconfigurationCooldown / MaxElectricalChargeDamageRate
- **Target**: `stdItem.ShieldEmitter.FaceType`
- **Source**: `SCItemShieldEmitterParams@{FaceType, MaxReallocation, ReconfigurationCooldown, MaxElectricalChargeDamageRate}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_shield_emitter()` line 1595-1611
- **Transformation**: String for FaceType; floats for numeric values. Includes placeholder Curves object (empty dict).

---

## Ifcs Block

### Ifcs.MaxSpeed / SCMSpeed
- **Target**: `stdItem.Ifcs.MaxSpeed`
- **Source**: `IFCSParams@{maxSpeed, scmSpeed}`
- **Parser**: Generic component capture line 499
- **Builder**: `stditem._build_ifcs()` line 1651-1721
- **Transformation**: Float values from safe_float()

### Ifcs.[TorqueImbalanceMultiplier|LiftMultiplier|DragMultiplier|...|ScmMaxDragMultiplier]
- **Target**: `stdItem.Ifcs.TorqueImbalanceMultiplier`
- **Source**: `IFCSParams@{torqueImbalanceMultiplier, liftMultiplier, dragMultiplier, precisionMinDistance, precisionMaxDistance, precisionLandingMultiplier, linearAccelDecay, angularAccelDecay, scmMaxDragMultiplier}`
- **Parser**: Generic component capture
- **Builder**: `stditem._build_ifcs()` line 1660-1671
- **Transformation**: Float values from safe_float()

### Ifcs.MasterModes
- **Target**: `stdItem.Ifcs.MasterModes`
- **Source**: `IFCSParams@{boostSpeedForward, boostSpeedBackward}`
- **Parser**: Generic component capture
- **Builder**: `stditem._build_ifcs()` line 1673-1682
- **Transformation**: Object with BoostSpeedForward, BoostSpeedBackward (floats); only included if any value present

### Ifcs.AngularVelocity
- **Target**: `stdItem.Ifcs.AngularVelocity`
- **Source**: `IFCSParams/maxAngularVelocity@{x, y, z}` (x→Pitch, z→Yaw, y→Roll mapping)
- **Parser**: Generic component capture
- **Builder**: `stditem._build_ifcs()` line 1703-1714
- **Transformation**: Object with Pitch, Yaw, Roll keys mapping to float values

### Ifcs.Gravlev
- **Target**: `stdItem.Ifcs.Gravlev`
- **Source**: `GravlevParams/handling@{turnFriction, selfRightingAccelBoost, hoverMaxSpeed, airControlMultiplier, antiFallMultiplier, lateralStrafeMultiplier}`
- **Parser**: Generic component capture
- **Builder**: `stditem._build_ifcs()` line 1684-1701
- **Transformation**: Object with TurnFriction, SelfRightingAccelBoost, HoverMaxSpeed, AirControlMultiplier, AntiFallMultiplier, LateralStrafeMultiplier (floats); only for hover vehicles

### Ifcs.AfterBurner
- **Target**: `stdItem.Ifcs.AfterBurner`
- **Source**: `IFCSParams/afterburner` with complex sub-structure
- **Parser**: Generic component capture
- **Builder**: `stditem._build_afterburner()` line 1795-1858
- **Transformation**: Complex object with AccelMultiplier* vectors, Capacitor sub-object (Size, Curves, Regen data), etc.

---

## Ports Block (and InstalledItem)

### Ports[]
- **Target**: `stdItem.Ports[]`
- **Source**: `EntityClassDefinition/Components/SItemPortContainerComponentParams/Ports/SItemPortDef[]`
- **Parser**: `dataforge_parser._parse_port_container()` line 1132-1141, `_parse_item_port()` line 1144-1207
- **Builder**: `stditem._build_ports()` line 1349-1438
- **Transformation**: Array of port objects

### Ports[].PortName
- **Target**: `stdItem.Ports[].PortName`
- **Source**: `SItemPortDef@Name` (or @name fallback)
- **Parser**: `dataforge_parser._parse_item_port()` line 1147
- **Builder**: `stditem._build_ports()` line 1361-1362
- **Transformation**: String name

### Ports[].MinSize / MaxSize
- **Target**: `stdItem.Ports[].MinSize`
- **Source**: `SItemPortDef@{MinSize, MaxSize}`
- **Parser**: `dataforge_parser._parse_item_port()` line 1148-1149
- **Builder**: `stditem._build_ports()` line 1364-1365
- **Transformation**: Integer sizes from safe_int()

### Ports[].Types
- **Target**: `stdItem.Ports[].Types`
- **Source**: `SItemPortDef/Types/SItemPortDefTypes/Type@type` + `SubTypes/Enum@value` (sub-types combined as "Type.SubType")
- **Parser**: `dataforge_parser._parse_item_port()` line 1156-1184
- **Builder**: `stditem._build_ports()` line 1367-1368
- **Transformation**: Array of type strings like "Weapon.Gun", "Shield.UNDEFINED"; omits UNDEFINED sub-types except for Bomb type

### Ports[].Loadout
- **Target**: `stdItem.Ports[].Loadout`
- **Source**: `SItemPortDef/SItemPortLoadoutEntryParams@entityClassName` or `@entityClassReference` (or from parent's defaultLoadout by port name)
- **Parser**: `dataforge_parser._parse_item_port()` line 1187-1194
- **Builder**: `stditem._build_ports()` line 1372-1395
- **Transformation**: String class name or GUID reference; resolved via SEntityComponentDefaultLoadoutParams if not in port def

### Ports[].InstalledItem
- **Target**: `stdItem.Ports[].InstalledItem`
- **Source**: Resolved from Loadout class name via ctx.get_item() → recursive stdItem build (nested=True)
- **Parser**: N/A (cross-reference)
- **Builder**: `stditem._build_ports()` line 1388-1401, calls `build_std_item()` recursively with nested=True
- **Transformation**: Full stdItem object for the installed item (excludes Classification, WeaponModifier when nested=True)

### Ports[].Flags / Tags / RequiredTags / PortTags
- **Target**: `stdItem.Ports[].Flags`
- **Source**: `SItemPortDef@{Flags, PortTags, RequiredPortTags}` + parent item tags
- **Parser**: `dataforge_parser._parse_item_port()` line 1150-1151
- **Builder**: `stditem._build_ports()` line 1403-1427
- **Transformation**: Space-separated strings split into arrays; Flags and RequiredTags only included if non-empty

### Ports[].Uneditable
- **Target**: `stdItem.Ports[].Uneditable`
- **Source**: `SItemPortDef@Flags` (contains "$uneditable" or plain "uneditable", but not when flag is capitalized "Uneditable")
- **Parser**: `dataforge_parser._parse_item_port()` line 1152-1153
- **Builder**: `stditem._build_ports()` line 1403-1431
- **Transformation**: Boolean; only included if true

### Ports[].Ports (sub-ports)
- **Target**: `stdItem.Ports[].Ports[]`
- **Source**: Recursive SItemPortDef/Ports sub-elements
- **Parser**: `dataforge_parser._parse_item_port()` line 1196-1205
- **Builder**: `stditem._build_ports()` line 1432-1436
- **Transformation**: Recursive port array with same structure

---

## CargoGrid & CargoContainers Block

### CargoGrid
- **Target**: `stdItem.CargoGrid`
- **Source**: `EntityClassDefinition/Components/SCItemInventoryContainerComponentParams@containerParams` (GUID) → InventoryContainer record with interiorDimensions and capacity, or ResourceContainer/SStandardCargoUnit
- **Parser**: `dataforge_parser._parse_entity_record()` line 581-584, `stream_parse_dataforge()` line 149-207
- **Builder**: `stditem._build_cargo_fields()` line 2309-2404
- **Transformation**: Object with Capacity (float SCU), Width/Height/Depth (computed from interiorDimensions ÷ 1.25, grid slots), MinContainerSize/MaxContainerSize sub-objects. Different rules for ship mining pods (no CargoGrid), ground pods (Width only), and regular containers.

### CargoGrid.MinContainerSize / MaxContainerSize
- **Target**: `stdItem.CargoGrid.MinContainerSize`
- **Source**: `InventoryContainer/minPermittedItemSize` and `maxPermittedItemSize` (x,y,z) from containerParams lookup
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 196-205
- **Builder**: `stditem._build_cargo_fields()` line 2375-2392
- **Transformation**: Object with Capacity (computed as width × height × depth or 1.0), Width, Height, Depth (floats) computed from dimensions ÷ 1.25

### CargoContainers
- **Target**: `stdItem.CargoContainers`
- **Source**: ResourceContainer capacity (from SStandardCargoUnit or InventoryContainer lookup)
- **Parser**: `dataforge_parser._parse_entity_record()` line 581-584
- **Builder**: `stditem._build_cargo_fields()` line 2323-2340, 2357
- **Transformation**: Object with Capacity (float SCU); always included for ship mining pods even if Capacity=0 (Collapsed)

---

## Top-Level Records (Non-stdItem)

### SCItemManufacturer

#### Code
- **Target**: `manufacturers[guid].Code`
- **Source**: `SCItemManufacturer@Code`
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 126-136
- **Transformation**: String code (e.g., "ANVL", "ACOM")

#### Name
- **Target**: `manufacturers[guid].Name`
- **Source**: `SCItemManufacturer/Localization@Name`
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 131-132
- **Transformation**: Resolved localization name

---

### AmmoParams

#### Speed
- **Target**: `ammo[guid].speed`
- **Source**: `AmmoParams@speed`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 254
- **Transformation**: Float projectile speed (m/s)

#### LifeTime
- **Target**: `ammo[guid].lifetime`
- **Source**: `AmmoParams@lifetime`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 255
- **Transformation**: Float seconds before projectile expires

#### Size
- **Target**: `ammo[guid].size`
- **Source**: `AmmoParams@size`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 256
- **Transformation**: Integer size class

#### Damage (ImpactDamage)
- **Target**: `ammo[guid].damage`
- **Source**: `AmmoParams/.../BulletProjectileParams/damage/DamageInfo@{DamagePhysical, DamageEnergy, ...}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 264-281
- **Transformation**: Dict with lowercase damage type keys → float values

#### DetonationDamage
- **Target**: `ammo[guid].detonationDamage`
- **Source**: `AmmoParams/.../BulletProjectileParams/detonationParams/DamageInfo@{DamagePhysical, DamageEnergy, DamageDistortion}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 284-292
- **Transformation**: Dict with damage type keys → float values

#### ExplosionRadius
- **Target**: `ammo[guid].explosionRadiusMin`, `ammo[guid].explosionRadiusMax`
- **Source**: `AmmoParams/.../BulletProjectileParams/detonationParams/ExplosionParams@{minRadius, maxRadius}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 294-303
- **Transformation**: Float meters; only included if non-zero

#### Penetration
- **Target**: `ammo[guid].penetration`
- **Source**: `AmmoParams/.../BulletProjectileParams/penetrationParams@{basePenetrationDistance, nearRadius, farRadius}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 306-312
- **Transformation**: Dict with field names as keys → float values

#### DamageDrop
- **Target**: `ammo[guid].damageDrop`
- **Source**: `AmmoParams/.../BulletProjectileParams/BulletDamageDropParams/{damageDropMinDistance, damageDropPerMeter, damageDropMinDamage}` each with nested DamageInfo
- **Parser**: `dataforge_parser._parse_ammo_params()` line 314-333
- **Transformation**: Dict with minDistance, dropPerMeter, minDamage keys, each containing damage type sub-dict

#### MaxPenetrationThickness
- **Target**: `ammo[guid].maxPenetrationThickness`
- **Source**: `AmmoParams/.../BulletProjectileParams/pierceabilityParams@maxPenetrationThickness`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 336-338
- **Transformation**: Float thickness (mm or cm)

#### CounterMeasure
- **Target**: `ammo[guid].counterMeasure`
- **Source**: `AmmoParams/.../CounterMeasureChaffParams or CounterMeasureFlareParams@{StartInfrared, EndInfrared, StartElectromagnetic, EndElectromagnetic, StartCrossSection, EndCrossSection, StartDecibel, EndDecibel}`
- **Parser**: `dataforge_parser._parse_ammo_params()` line 340-355
- **Transformation**: Dict with IR/EM/CS/dB start/end keys → float values; counterMeasureType set to "Chaff" or "Flare"

---

### InventoryContainer

#### Capacity
- **Target**: `inventory[guid].capacity`
- **Source**: `InventoryContainer/{SCentiCargoUnit|SStandardCargoUnit|SMicroCargoUnit}@{centiSCU|standardCargoUnits|microSCU}` (preferred order: centi > standard > micro)
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 154-168
- **Transformation**: Float SCU with scale applied (0.01 for centi, 1.0 for standard, 1e-6 for micro)

#### interiorDimensions
- **Target**: `inventory[guid].interiorDimensions`
- **Source**: `InventoryContainer/interiorDimensions@{x, y, z}`
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 171-178
- **Transformation**: Dict with x, y, z keys → float meters

#### minPermittedItemSize / maxPermittedItemSize
- **Target**: `inventory[guid].minPermittedItemSize`
- **Source**: `InventoryContainer/{minPermittedItemSize|maxPermittedItemSize}@{x, y, z}`
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 196-205
- **Transformation**: Dict with x, y, z keys → float meters; only included if present

---

### WeaponGimbalModeModifierDef

#### fireRateMultiplier
- **Target**: `gimbal_modifiers[guid].fireRateMultiplier`
- **Source**: `WeaponGimbalModeModifierDef/.../SWeaponModifierParams/weaponStats@fireRateMultiplier`
- **Parser**: `dataforge_parser.stream_parse_dataforge()` line 209-219
- **Transformation**: Float multiplier (e.g., 1.5 for 50% increase); only included if != 1.0

---

### SIFCSModifiersLegacy (Blade Modifiers)

These are applied as deltas to IFCS fields for items with "_Blade_HND" or "_Blade_SPD" suffix:

#### Blade_HND (Handling variant)
- **Deltas**: MaxSpeed -25, SCMSpeed -8, BoostSpeedForward -10, BoostSpeedBackward -10, Pitch +1, Yaw +1, Roll +2
- **Source**: Applied in `stditem._apply_blade_modifier()` line 1753-1792
- **Transformation**: Subtracted from base IFCS values when className ends with "_Blade_HND" or "_Flight_Blade_HND"

#### Blade_SPD (Speed variant)
- **Deltas**: MaxSpeed +25, SCMSpeed +8, BoostSpeedForward +10, BoostSpeedBackward +10, Pitch -1, Yaw -1, Roll -2
- **Source**: Applied in `stditem._apply_blade_modifier()` line 1753-1792
- **Transformation**: Added to base IFCS values when className ends with "_Blade_SPD" or "_Flight_Blade_SPD"

---

## Ship-Level Records (from builders/ships.py)

### Ships.FuelManagement
- **Source**: Computed from defaultLoadout fuel tanks and thrusters
- **Builder**: `ships._build_fuel_management()`
- **Extracting**: Fuel tank capacities, intake rates, thruster consumption by class

### Ships.FlightCharacteristics
- **Source**: IFCSParams from flight controller + SCItemThrusterParams from thrusters
- **Builder**: `ships._build_flight_characteristics()` line 460-600+
- **Extracting**: Max speeds, thrust values (Main, Retro, VTOL, Maneuvering), quantum drive spool-up time

### Ships.Armor (ship-level)
- **Source**: Armor item in ship's default loadout
- **Builder**: `ships._build_armor_stats()` line 295-371
- **Extracting**: Health from SHealthComponentParams, DamageMultipliers, DamageDeflection, PenetrationReduction from armor component

### Ships.Hull
- **Source**: Vehicle implementation XML (veh_impl_parser)
- **Builder**: `ships._build_hull_stats()` line 443-457
- **Extracting**: Structural HP for vital parts and ship parts

### Ships.BaseLoadout
- **Source**: Computed from Hardpoints (aggregate installed items by port category)
- **Builder**: `ships._build_base_loadout_summary()` line ~700+
- **Extracting**: Summary of default weapons, shields, coolers, power plants, etc.

---

## Notes on Data Pipeline

1. **Localization Resolution**: All @-prefixed strings (e.g., `@item_NameFoo`) are resolved via `ctx.resolve_name()`, which looks up the key in the global.ini localization file. Unresolved keys are kept as-is or fall back to ClassName/placeholder markers.

2. **GUID Cross-References**: GUIDs (128-bit UUIDs in format `12345678-1234-1234-1234-123456789012`) reference other records:
   - Manufacturer GUID → SCItemManufacturer record (Code + Name)
   - Ammo GUID → AmmoParams record (Speed, Lifetime, Damage, etc.)
   - Container GUID → InventoryContainer record (Capacity, Dimensions)
   - Gimbal modifier GUID → WeaponGimbalModeModifierDef record (fireRateMultiplier)
   - Loadout reference → resolved to ClassName via guid_to_class map

3. **Type System**: Item types follow `Type.SubType` convention (e.g., `Shield.UNDEFINED`, `Weapon.Gun.Laser`). The Type/SubType are used for Classification and Class logic. UNDEFINED sub-types are preserved in Type output but stripped from Classification.

4. **Safe Type Converters**: `safe_float()`, `safe_int()`, `safe_bool()` (utils.py line 45-72) handle missing or malformed values with sensible defaults (0.0, 0, False respectively).

5. **Nested Component Parsing**: Generic `_elem_to_dict()` captures unknown component types for extensibility. Known types (SCItemWeaponComponentParams, SHealthComponentParams, etc.) are parsed explicitly; unknown types fall through to generic dict capture.

---

This reference documents all known field sources as of the current codebase. Developers adding new fields should follow the same pattern: extract from XML component, parse in dataforge_parser or entity_parser, build in the appropriate builder function, and document the source path and transformation logic here.
