# FPS Weapon Gap Implementation Plan

Companion to `fps_weapon_xml_audit.md`. Each section below is one self-contained patch — XML schema, parser change, cache layout, BuildContext wiring, output emission, and verification snippet. Apply in priority order; later patches don't depend on earlier ones, so you can ship them independently.

**Conventions used throughout:**

- The streaming parser is in `nova/dataforge_parser.py`. New top-level record types are added to the `__type` dispatch in the start/end loop. Self-closing records can be handled at end-of-element without setting `in_record = True`; records with deep children must set `in_record = True` so child elements are preserved during the streaming clear.
- Cache files live in `cache/parsed_*.json`, registered in `cache_files` and `cache_data` dicts.
- BuildContext (`nova/__main__.py`) gets a new field per cache; the constructor and the call site at the bottom of `main()` both need updating.
- Emission lives in `nova/builders/stditem.py`. FPS-only emission goes inside the `if "weapon" in components:` block. Generic emission goes after the type-specific blocks.

---

## P1a — WeaponProceduralRecoilConfigDef (per-firing-mode base recoil)

**This is the largest and highest-value patch.** It surfaces what the spreadsheet's "Recoil" tab actually shows.

### Reach path
`item.components.weapon.firingModes[].recoil` — the GUID is currently dropped during parsing because `firingModes` parser only extracts a fixed set of fields. First fix is to capture the GUID; second fix is to parse the record it points to.

### Record count
174 occurrences of `WeaponProceduralRecoilConfigDef` in Game2.xml (ref count includes both definition and reference). 87 distinct XML files in `cache/Data/Libs/Foundry/Records/weaponproceduralrecoil/`. Ratio of weapons-with-mode-recoil ≈ 50/56 (every player-class FPS weapon except gadgets/melee).

### Step 1 — capture the GUID in firing-mode parsing

In `_parse_weapon_params` (`nova/dataforge_parser.py`), the firing-mode loop currently extracts `name`, `fireRate`, `heatPerShot`, etc. but ignores the `@recoil` attribute. Add it:

```python
# In the per-firingMode block:
fm = {
    "name": fa.get("name", ""),
    # ... existing fields ...
    "recoilConfig": fa.get("recoil", "") or None,   # NEW
    "misfire": fa.get("misfire", "") or None,        # NEW (P3 below)
}
```

Apply at every per-firing-mode parser variant (Burst, Rapid, Single, Charged, Sequence, Beam — each calls a slightly different sub-parser; check call sites of the firing-mode-list iterator).

### Step 2 — register `WeaponProceduralRecoilConfigDef` as a top-level record

```python
# In stream_parse_dataforge():
if elem_type in ("EntityClassDefinition", "SCItemManufacturer", "AmmoParams",
                  "InventoryContainer", "WeaponGimbalModeModifierDef",
                  "SIFCSModifiersLegacy", "CraftingBlueprintRecord",
                  "ActorProceduralRecoilConfig", "ActorProceduralRecoilModifiers",
                  "WeaponProceduralRecoilConfigDef"):     # NEW
    in_record = True
```

Plus a new dict and handler:

```python
weapon_recoil_configs = {}   # guid -> {hands, aim, body, head}

# ... in the end-event dispatch ...
elif elem_type == "WeaponProceduralRecoilConfigDef":
    in_record = False
    guid = elem.get("__ref", "")
    if guid:
        rec = _parse_weapon_recoil_config(elem)
        if rec:
            weapon_recoil_configs[guid] = rec
    elem.clear()
```

### Step 3 — `_parse_weapon_recoil_config(elem)` helper

Mirrors `_parse_recoil_modifiers` (P1 already shipped) but with absolute values instead of multipliers, and with curves captured.

```python
def _parse_weapon_recoil_config(elem):
    """Parse WeaponProceduralRecoilConfigDef — base recoil curves per fire mode.
    Returns {hands, aim, body, head} dict. Captures top-level scalars + the
    primary curve max-values + min/max limits. Skips deeply nested Bezier
    point arrays (8–17 control points per curve, 30+ curves per record —
    too verbose for the catalogue).
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
            h["rotation"] = {"x": safe_float(rot.get("x", "0")),
                             "y": safe_float(rot.get("y", "0")),
                             "z": safe_float(rot.get("z", "0"))}
        cr = hands.find("curveRecoil")
        if cr is not None:
            h["curveRecoil"] = {
                "totalRecoilTime": safe_float(cr.get("totalRecoilTime", "0")),
                "limitTransitionTime": safe_float(cr.get("limitTransitionTime", "0")),
                "minDecayTime": safe_float(cr.get("minDecayTime", "0")),
                "maxDecayTime": safe_float(cr.get("maxDecayTime", "0")),
            }
            for curve_key, xml_key in [("position", "positionCurves"), ("rotation", "rotationCurves")]:
                c = cr.find(xml_key)
                if c is not None:
                    h["curveRecoil"][curve_key] = {
                        "xMaxValue": safe_float(c.get("xMaxValue", "0")),
                        "yMaxValue": safe_float(c.get("yMaxValue", "0")),
                        "zMaxValue": safe_float(c.get("zMaxValue", "0")),
                    }
                    for limit_key in ("minLimits", "maxLimits"):
                        l = c.find(limit_key)
                        if l is not None:
                            h["curveRecoil"][curve_key][limit_key] = {
                                "x": safe_float(l.get("x", "0")),
                                "y": safe_float(l.get("y", "0")),
                                "z": safe_float(l.get("z", "0")),
                            }
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
        for key, attr in [("max", "max"), ("shotKickFirst", "shot_kick_first"),
                          ("shotKick", "shot_kick")]:
            v = aim.find(attr)
            if v is not None:
                a[key] = {"x": safe_float(v.get("x", "0")),
                          "y": safe_float(v.get("y", "0"))}
        cr = aim.find("curveAimRecoil")
        if cr is not None:
            a["curveAimRecoil"] = {
                "yawMaxDegrees": safe_float(cr.get("yawMaxDegrees", "0")),
                "pitchMaxDegrees": safe_float(cr.get("pitchMaxDegrees", "0")),
                "rollMaxDegrees": safe_float(cr.get("rollMaxDegrees", "0")),
                "maxFireTime": safe_float(cr.get("maxFireTime", "0")),
                "recoilSmoothTime": safe_float(cr.get("recoilSmoothTime", "0")),
                "decayStartTime": safe_float(cr.get("decayStartTime", "0")),
                "minDecayTime": safe_float(cr.get("minDecayTime", "0")),
                "maxDecayTime": safe_float(cr.get("maxDecayTime", "0")),
            }
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
        }

    return result if result else None
```

### Step 4 — cache + tuple

Add to `cache_files` map, return tuple, cache write loop, and cached-load gate. Following the existing ifcs/gimbal pattern.

```python
# cache_files in the cached-load gate:
"weapon_recoil_configs": os.path.join(cache_dir, "parsed_weapon_recoil_configs.json"),

# return tuple grows by one:
return (..., recoil_configs, recoil_modifiers, weapon_recoil_configs)
```

### Step 5 — BuildContext

`nova/__main__.py` `BuildContext.__init__`:

```python
weapon_recoil_configs=None,
# ...
self.weapon_recoil_configs = weapon_recoil_configs or {}
```

Plus the unpack at the `stream_parse_dataforge(...)` call site and the keyword pass at `BuildContext(...)`.

### Step 6 — emit on each firing mode

In `nova/builders/stditem.py`, the firing-mode loop already produces per-mode dicts. Add one line that resolves the recoil GUID and merges:

```python
# In the firing-mode emitter (e.g. _build_firing_modes):
for fm_raw in firing_modes:
    fm_out = { ... existing keys ... }
    rcfg_guid = fm_raw.get("recoilConfig")
    if rcfg_guid:
        rcfg = ctx.weapon_recoil_configs.get(rcfg_guid)
        if rcfg:
            fm_out["Recoil"] = {
                "Hands": rcfg.get("hands"),
                "Aim": rcfg.get("aim"),
                "Body": rcfg.get("body"),
                "Head": rcfg.get("head"),
            }
    yield fm_out
```

### Output schema

```json
"Firing": [
  {
    "Name": "Burst",
    "RoundsPerMinute": 900,
    ...,
    "Recoil": {
      "Hands": {
        "decay": 2.0, "endDecay": 15.0,
        "fireRecoilTime": 0.1, "fireRecoilStrengthFirst": 0.0, "fireRecoilStrength": 0.0,
        "angleRecoilStrength": 0.0,
        "useRandomRotation": false,
        "randomness": 0.0, "randomnessBackPush": 0.0,
        "frontalOscillationRotation": 0.0, "frontalOscillationStrength": 0.0, "frontalOscillationDecay": 0.0, "frontalOscillationRandomness": 0.0,
        "rotation": {"x": 0, "y": 0, "z": 0},
        "curveRecoil": {
          "totalRecoilTime": 0.06, "limitTransitionTime": 1.0, "minDecayTime": 2.0, "maxDecayTime": 3.0,
          "position": {"xMaxValue": -0.0005, "yMaxValue": -0.03, "zMaxValue": -0.00125,
                       "minLimits": {"x": -0.3, "y": -0.038, "z": -0.003},
                       "maxLimits": {"x": 0.3,  "y":  0.006, "z":  0.003}},
          "rotation": {"xMaxValue": 0.22, "yMaxValue": 1.0, "zMaxValue": 0.125,
                       "minLimits": {"x": -0.5, "y": -8.0, "z": -1.35},
                       "maxLimits": {"x":  0.95,"y":  8.0, "z":  2.5}}
        }
      },
      "Aim": {
        "pullLeftPercentage": 0, "randomPitch": 0, "randomYaw": 0,
        "decay": 20, "endDecay": 20, "recoilTime": 0, "delay": 0,
        "max": {"x": 0, "y": 0}, "shotKickFirst": {"x": 0, "y": 0}, "shotKick": {"x": 0, "y": 0},
        "curveAimRecoil": {"yawMaxDegrees": 0.005, "pitchMaxDegrees": 0.1, "rollMaxDegrees": 0,
                           "maxFireTime": 1.0, "recoilSmoothTime": 0.09, "decayStartTime": 0.13,
                           "minDecayTime": 1.0, "maxDecayTime": 1.75}
      },
      "Body": {"hipsPushForce": 0.0065, "hipsDampStrength": 2.0, ...},
      "Head": {"frequency": 15.0, "smoothFactor": 5.0, ...}
    }
  }
]
```

### Verification

```python
# After build:
w = next(e for e in out if e['className'] == 'klwe_rifle_energy_01')
fm = w['stdItem']['Weapon']['Firing'][0]
assert fm['Name'] == 'Burst'
assert fm['Recoil']['Hands']['curveRecoil']['totalRecoilTime'] == 0.06
assert fm['Recoil']['Aim']['curveAimRecoil']['yawMaxDegrees'] == 0.005
```

Disambiguation note: this `Recoil` block is **per-firing-mode** and lives under `Weapon.Firing[].Recoil`. The existing top-level `Recoil` block at `stdItem.Recoil` is the **per-aim-state multipliers** (ActorProceduralRecoilConfig). Both are needed; the consumer multiplies the multipliers on top of the per-mode base values.

---

## P1b — `aimAction.@zoomScale` / `@zoomTime`

Tiny patch. Two scalars on the single `aimAction` element. Spreadsheet maps to "Zoom" column.

### Parser change
In `_parse_weapon_params`:

```python
# Existing block reads aimAction.aimModifier.spreadModifier — extend:
aim_action = comp.find("aimAction")
if aim_action is not None:
    # NEW: capture top-level aim attrs
    aim_simple = aim_action.find("SWeaponActionAimSimpleParams")
    if aim_simple is not None:
        result["aim"] = {
            "zoomScale": safe_float(aim_simple.get("zoomScale", "1")),
            "zoomTime": safe_float(aim_simple.get("zoomTime", "0")),
            "toggleZoomOverride": safe_bool(aim_simple.get("toggleZoomOverride", "0")),
        }
        # dofSettings (optional)
        dof = aim_simple.find("dofSettings/SWeaponAimDofSettings")
        if dof is not None:
            result["aim"]["dof"] = {
                "focalDistance": safe_float(dof.get("focalDistance", "0")),
                "focalRange": safe_float(dof.get("focalRange", "0")),
                "fstop": safe_float(dof.get("fstop", "0")),
            }
    # ... existing aimSpreadModifier extraction continues ...
```

### No new cache/context — just emit

In `_build_weapon_data`:

```python
aim = comp.get("aim")
if aim:
    weapon_data["Aim"] = {
        "ZoomScale": aim.get("zoomScale", 1.0),
        "ZoomTime": aim.get("zoomTime", 0.0),
    }
    if "dof" in aim:
        weapon_data["Aim"]["DepthOfField"] = {
            "FocalDistance": aim["dof"]["focalDistance"],
            "FocalRange": aim["dof"]["focalRange"],
            "FStop": aim["dof"]["fstop"],
        }
```

Add `"Aim"` to the ordered-key list in the Weapon block builder so it appears in a stable position (suggested: after `Repool`).

### Verification
```python
# Gallant Rifle — zoomScale=1.4, zoomTime=0.3
assert w['stdItem']['Weapon']['Aim']['ZoomScale'] == 1.4
assert w['stdItem']['Weapon']['Aim']['ZoomTime'] == 0.3
```

---

## P1c — `fireActions[].@cooldownTime` / `@innerCooldownTime`

Even smaller. Already inside the firing-mode loop.

### Parser change
```python
# In each firing-mode parser variant, add to the output dict:
fm["cooldownTime"] = safe_float(fa.get("cooldownTime", "0"))
# Burst-only:
if fa.get("__polymorphicType") == "SWeaponActionFireBurstParams":
    fm["innerCooldownTime"] = safe_float(fa.get("innerCooldownTime", "0"))
```

### Emit
```python
# Existing per-firing-mode dict — add:
"CooldownTime": fm_raw.get("cooldownTime", 0.0),
# Burst:
"InnerCooldownTime": fm_raw["innerCooldownTime"]   # only if present
```

### Verification
```python
# Gallant Rifle Burst-3: cooldownTime=0.25, innerCooldownTime=0.15
fm = w['stdItem']['Weapon']['Firing'][0]
assert fm['CooldownTime'] == 0.25
assert fm['InnerCooldownTime'] == 0.15
```

---

## P2a — Bullet drop (AmmoParams.physicsControllerParams)

The ammo's projectile physics — gravity, mass, air resistance — drives the spreadsheet's "Bullet Drop" tab.

### Parser change

In `_parse_ammo_params` (`nova/dataforge_parser.py`):

```python
# After the existing damage/penetration/damageDrop blocks:
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
```

### Emit
In `_resolve_fps_ammo` and the ship-weapon equivalent in `_build_weapon_data`:

```python
phys = ammo_data.get("projectilePhysics")
if phys:
    ammo["Projectile"] = {
        "Mass": phys["mass"],
        "AirResistance": phys["airResistance"],
        "DisableGravity": phys["disableGravity"],
        "Radius": phys["radius"],
        "Pierceability": phys["pierceability"],
    }
```

Place under `Ammunition.Projectile` (new sub-block).

### Verification
```python
# Lumin V SMG — energy weapon: disableGravity=1 expected (laser doesn't drop)
# P4-AR — ballistic: disableGravity=0, mass>0 → drops
```

---

## P2b — Force reaction (AmmoParams.impulseFalloffParams + impulseScale)

Spreadsheet "Force Reaction" tab.

### Parser change
```python
# In _parse_ammo_params, add to result top-level:
result["impulseScale"] = safe_float(elem.get("impulseScale", "1"))

# Inside the BulletProjectileParams parsing:
impulse_falloff = bullet.find("impulseFalloffParams/BulletImpulseFalloffParams")
if impulse_falloff is not None:
    result["impulseFalloff"] = {
        "minDistance": safe_float(impulse_falloff.get("minDistance", "0")),
        "dropFalloff": safe_float(impulse_falloff.get("dropFalloff", "0")),
        "maxFalloff": safe_float(impulse_falloff.get("maxFalloff", "0")),
    }
```

### Emit
```python
# Inside Ammunition block:
if ammo_data.get("impulseScale") or ammo_data.get("impulseFalloff"):
    ammo["Impulse"] = {
        "Scale": ammo_data.get("impulseScale", 1.0),
    }
    if ammo_data.get("impulseFalloff"):
        ammo["Impulse"]["Falloff"] = {
            "MinDistance": ammo_data["impulseFalloff"]["minDistance"],
            "DropPerMeter": ammo_data["impulseFalloff"]["dropFalloff"],
            "MaxFalloff": ammo_data["impulseFalloff"]["maxFalloff"],
        }
```

---

## P2c — Armor-tier penetration (AmmoParams.pierceabilityParams)

Spreadsheet "DmgRes" / penetration calculations against armor tiers.

### Parser change
```python
# Inside BulletProjectileParams parsing:
pierce = bullet.find("pierceabilityParams")
if pierce is not None:
    result["pierceability"] = {
        "damageFalloffLevel1": safe_float(pierce.get("damageFalloffLevel1", "0")),
        "damageFalloffLevel2": safe_float(pierce.get("damageFalloffLevel2", "0")),
        "damageFalloffLevel3": safe_float(pierce.get("damageFalloffLevel3", "0")),
        "maxPenetrationThickness": safe_float(pierce.get("maxPenetrationThickness", "0")),
    }
```

### Emit
```python
pierce = ammo_data.get("pierceability")
if pierce:
    ammo["ArmorPenetration"] = {
        "FalloffLevel1": pierce["damageFalloffLevel1"],
        "FalloffLevel2": pierce["damageFalloffLevel2"],
        "FalloffLevel3": pierce["damageFalloffLevel3"],
        "MaxThickness": pierce["maxPenetrationThickness"],
    }
```

Note: existing `Penetration` block (basePenetrationDistance/nearRadius/farRadius) is from a **different** XML element (`penetrationParams` vs `pierceabilityParams`). Keep both — they describe different mechanics.

---

## P2d — Heat: lockOnOverheat / heatReduceWhenOverheatIsFixed

Two scalars on `connectionParams`. Spreadsheet "Heat Stats" columns.

### Parser change
In `_parse_weapon_params`, the `connectionParams` block already exists. Add:

```python
conn = comp.find("connectionParams")
if conn is not None:
    result["heatRateOnline"] = safe_float(conn.get("heatRateOnline"))
    result["powerActiveCooldown"] = safe_float(conn.get("powerActiveCooldown"))
    # NEW:
    result["lockOnOverheat"] = safe_bool(conn.get("lockOnOnverheat", "0"))  # NB: typo in CIG attr name
    result["heatReduceWhenOverheatIsFixed"] = safe_float(conn.get("heatReduceWhenOverheatIsFixed", "0"))
    # ... existing simplifiedHeat extraction ...
```

### Emit
Inside the existing HeatParameters block:

```python
heat_params = {
    # ... existing ...
    "LockOnOverheat": comp.get("lockOnOverheat", False),
    "HeatReduceWhenFixed": comp.get("heatReduceWhenOverheatIsFixed", 0),
}
```

---

## P2e — temperatureCurveParams (heat→damage scaling)

Reached via `connectionParams.simplifiedHeatParams.SWeaponSimplifiedHeatParams.temperatureCurveParams.SWeaponSimplifiedHeatParamsTemperatureCurveParams`. Has `@temperatureCurve` GUID + `xAxisMinMaxValues` + `yAxisMinMaxValues`. The GUID points to a `BezierCurve` record.

For now, surface the axis bounds (without the full Bezier curve). This is enough for damage-vs-heat visualization.

```python
# Inside simplifiedHeat parser:
tcp = shp.find(".//SWeaponSimplifiedHeatParamsTemperatureCurveParams")
if tcp is not None:
    x_axis = tcp.find("xAxisMinMaxValues")
    y_axis = tcp.find("yAxisMinMaxValues")
    if x_axis is not None and y_axis is not None:
        result["simplifiedHeat"]["temperatureCurve"] = {
            "xMin": safe_float(x_axis.get("x", "0")),
            "xMax": safe_float(x_axis.get("y", "0")),
            "yMin": safe_float(y_axis.get("x", "0")),
            "yMax": safe_float(y_axis.get("y", "0")),
        }
```

Defer full BezierCurve parsing until P4.

---

## P3a — WeaponMisfireDef (jam mechanics)

Reached via `firingModes[].misfire`. **5 records** total in the catalogue (one per fire-type: burst/rapid/single/charge/beam) — they are SHARED across weapons.

### Schema (verified)
```
WeaponMisfireDef.<Mode>_misfire
  @minorMisfireDuration                    # seconds
  @minorMisfireCooldown                    # seconds
  @majorMisfireCooldown                    # seconds
  minorMisfire.SWeaponMisfireEntry
    @hitType "punish"
    misfireProbabilityCurve.BezierCurve.points  # empty in current data
    damage                                       # empty in current data
  majorMisfire.SWeaponMisfireEntry             # same shape
  criticalMisfire.SWeaponMisfireEntry          # same shape
```

Probability curves are currently empty (CIG hasn't tuned them). The cooldowns/durations are the only populated values today.

### Parser change
```python
# In stream_parse_dataforge __type set:
"WeaponMisfireDef",

# New record handler:
elif elem_type == "WeaponMisfireDef":
    in_record = False
    guid = elem.get("__ref", "")
    if guid:
        misfire_defs[guid] = {
            "minorDuration": safe_float(elem.get("minorMisfireDuration", "0")),
            "minorCooldown": safe_float(elem.get("minorMisfireCooldown", "0")),
            "majorCooldown": safe_float(elem.get("majorMisfireCooldown", "0")),
        }
    elem.clear()
```

### Emit (per firing mode)
```python
mf_guid = fm_raw.get("misfire")
if mf_guid:
    mf = ctx.misfire_defs.get(mf_guid)
    if mf:
        fm_out["Misfire"] = {
            "MinorDuration": mf["minorDuration"],
            "MinorCooldown": mf["minorCooldown"],
            "MajorCooldown": mf["majorCooldown"],
        }
```

---

## P3b — SDegradationParams (wear model)

Currently only `Durability.Lifetime = 0` placeholder is emitted. Full schema:

### Parser change
Add `SDegradationParams` to the component dispatch in `_parse_entity_record`:

```python
elif poly_type == "SDegradationParams":
    accums = []
    for acc in comp.findall("accumulators/SWearAccumulatorParams"):
        accums.append({
            "maxLifetimeHours": safe_float(acc.get("MaxLifetimeHours", "0")),
            "damageConversionRate": safe_float(acc.get("DamageConversionRate", "0")),
            "accumulationEventThreshold": safe_int(acc.get("AccumulationEventThreshold", "1")),
            "atmosphereMultiplier": safe_float(acc.get("AtmosphereMultiplier", "1")),
            "initialAccumulationRatio": safe_float(acc.get("InitialAccumulationRatio", "0")),
            "initialAgeRatio": safe_float(acc.get("InitialAgeRatio", "0")),
            "initialUsageRatio": safe_float(acc.get("InitialUsageRatio", "0")),
            "useAsTimer": safe_bool(acc.get("UseAsTimer", "0")),
        })
        # Heat multipliers
        hm = acc.find("HeatMultipliers")
        if hm is not None:
            accums[-1]["heatMultipliers"] = {
                "normal": safe_float(hm.get("NormalTemperatureMultiplier", "1")),
                "overheat": safe_float(hm.get("OverheatTemperatureMultiplier", "1")),
            }
    components["degradation"] = {
        "stopIfDestroyed": safe_bool(comp.get("StopDegradingIfDestroyed", "0")),
        "accumulators": accums,
    }
```

### Emit
Replace the placeholder Durability block:

```python
# Currently:  si["Durability"] = {"Lifetime": 0}
# Replace with:
deg = components.get("degradation")
if deg and deg.get("accumulators"):
    acc = deg["accumulators"][0]   # weapons typically have 1 accumulator
    si["Durability"] = {
        "MaxLifetimeHours": acc["maxLifetimeHours"],
        "DamageConversionRate": acc["damageConversionRate"],
        "AccumulationEventThreshold": acc["accumulationEventThreshold"],
        "AtmosphereMultiplier": acc["atmosphereMultiplier"],
    }
    if "heatMultipliers" in acc:
        si["Durability"]["HeatMultipliers"] = acc["heatMultipliers"]
```

---

## P3c — Power-mode block (full surfacing)

Currently `noPowerStats/underpowerStats/overpowerStats` are partially extracted (only top-level multipliers, no recoil/spread/aim sub-blocks). Spreadsheet treats them as full alternative weapon profiles.

### Parser change
Extend the existing power-mode block extraction in `_parse_weapon_params` to capture `aimModifier`, `regenModifier`, and the recoil multipliers (same shape as ActorProceduralRecoilModifiers — extract scalar fields only):

```python
def _parse_power_stats(elem):
    if elem is None:
        return None
    s = {
        # existing scalar fields...
    }
    # Recoil modifier scalars (NEW)
    rm = elem.find("recoilModifier")
    if rm is not None:
        s["recoilModifier"] = {
            "decayMultiplier": safe_float(rm.get("decayMultiplier", "1")),
            "fireRecoilStrengthMultiplier": safe_float(rm.get("fireRecoilStrengthMultiplier", "1")),
            "randomnessMultiplier": safe_float(rm.get("randomnessMultiplier", "1")),
            # ... rest of multipliers ...
        }
    # Aim modifier (NEW)
    am = elem.find("aimModifier")
    if am is not None:
        s["aimModifier"] = {
            "zoomScale": safe_float(am.get("zoomScale", "1")),
            "secondZoomScale": safe_float(am.get("secondZoomScale", "1")),
            "zoomTimeScale": safe_float(am.get("zoomTimeScale", "1")),
            "fstopMultiplier": safe_float(am.get("fstopMultiplier", "1")),
        }
    return s
```

### Emit
Power-mode blocks already pass through to output. Just verify the new fields appear under `Weapon.PowerModes.{NoPower, UnderPower, OverPower}.{recoilModifier, aimModifier}`.

---

## P4 — BezierCurve capture (low priority)

Many curves are referenced (spread accuracy curves, recoil position/rotation curves, heat-vs-damage curves). All share a uniform schema:

```
BezierCurve
  @useLUT (bool)
  points.[Vec2{@x, @y}]
```

Currently captured **inline** wherever curves appear (`accuracyRangeCurve.points`, etc.) but never emitted.

If/when needed, add a generic helper:

```python
def _parse_bezier_curve(elem):
    if elem is None:
        return None
    points = []
    for v in elem.findall("points/Vec2"):
        points.append({"x": safe_float(v.get("x", "0")), "y": safe_float(v.get("y", "0"))})
    return {"useLUT": safe_bool(elem.get("useLUT", "0")), "points": points} if points else None
```

Then call it for any curve we want to surface. The output is verbose — only emit on demand for curves consumers care about.

**Skipped categories (intentionally):**

- `WeaponProceduralAnimation` — animation clip routing only (53 records, all are filter→clip-GUID mappings; no weapon-stat data)
- `WeaponARModifier` — single default record, all multipliers = 1.0 (no per-weapon variation; would always emit the same trivial block)
- `weaponAIData.accuracyRangeCurve` — AI-only accuracy curve (15-point Bezier, doesn't affect player damage)
- All audio/visual/UI components (§2 ignored list in audit)

---

## Summary of cache + context additions

After applying P1a + P3a (the two patches that add new top-level record types), the parser will have these new caches:

| Cache file | Records | Source XML record type |
|---|---|---|
| `parsed_weapon_recoil_configs.json` | ~87 | `WeaponProceduralRecoilConfigDef` |
| `parsed_misfire_defs.json` | 5 | `WeaponMisfireDef` |

BuildContext gains two fields: `weapon_recoil_configs`, `misfire_defs`.

P1b/P1c/P2*/P3b are **inline** extensions — they reuse existing record streams (item entity + AmmoParams) and don't require new top-level record types.

---

## Suggested implementation order

1. **P1c** (cooldownTime — 5 lines, instant win)
2. **P1b** (zoomScale/zoomTime — ~15 lines, instant win)
3. **P2d** (heat lockOnOverheat — 5 lines)
4. **P3a** (Misfire — small new record, simple)
5. **P2a/P2b/P2c** (ammo physics + impulse + pierceability — bundle, all in `_parse_ammo_params`)
6. **P1a** (per-mode recoil — biggest patch, most user-visible value)
7. **P3b** (degradation — extends existing Durability block)
8. **P3c** (full power-mode block — extends existing power-mode parsing)
9. **P2e** (heat curve axes — small)
10. **P4** (BezierCurves — only if a consumer needs them)

---

## Verification harness

After each patch, run the extractor and check the diff against ref4 to confirm no regressions:

```python
import json
out_pre = json.load(open('output/fps_equipment.json.bak', encoding='utf-8'))
out_post = json.load(open('output/fps_equipment.json', encoding='utf-8'))
# By className, compare; new fields should appear, existing ones should match
pre_idx = {e['className']: e for e in out_pre}
for e in out_post:
    pre = pre_idx.get(e['className'])
    if pre:
        # Check existing top-level fields match
        for k in pre.keys():
            if k != 'stdItem':
                assert pre[k] == e[k], f"Regression on {e['className']}.{k}"
```

Plus a Class-derivation regression check (must remain 56/56 vs ref4):

```python
ref4 = json.load(open('temp/reference/entry_4.json', encoding='utf-8-sig'))
ref_idx = {e['className']: e for e in ref4}
for e in out_post:
    if e.get('type') == 'WeaponPersonal':
        ref = ref_idx.get(e['className'])
        if ref:
            assert e['stdItem'].get('Class') == ref['stdItem'].get('Class')
```
