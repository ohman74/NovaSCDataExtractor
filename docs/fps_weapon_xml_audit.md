# FPS Weapon XML Structure — Recursive Audit

Audited 2026-05-06. Source weapons: `klwe_rifle_energy_01` (energy/laser, burst-only), `behr_rifle_ballistic_01` (ballistic, rapid+single), `ksar_smg_energy_01` (charged + rapid). Cross-referenced against ref4 (174 items) + finder.cstone.space spreadsheet column inventory.

**Legend** — extraction status applies to `output/fps_equipment.json[].stdItem`:

- **✓** = extracted, surfaced in output
- **✗** = parsed in cache but **not** surfaced in output
- **—** = not parsed (audio/visual/UI plumbing or runtime-only state)
- **GUID→** = pointer to external record (record schema documented in §3)

---

## §1 Top-level entity definition

```
<EntityClassDefinition.<className> __ref="GUID" __path="...">
  <defaultEditorColor .../>          —   editor only
  <tags />                            —   empty for weapons
  <StaticEntityClassData />           —   empty
  <Components>...</Components>        ✓   walked below
</EntityClassDefinition.<className>>
```

Root attributes:

| Attr | Example | Status | Notes |
|---|---|---|---|
| `__ref` | `8bc41f99-…` | ✓ | Stored as `record.guid` — used for crafting blueprint lookup, ammo record reference |
| `__path` | `libs/foundry/records/entities/scitem/weapons/fps_weapons/klwe_rifle_energy_01.xml` | ✓ | Stored as `record.path` — used for FPS-vs-ship discrimination |
| `Category` | `Items` | — | Editor metadata |
| `Icon`, `Invisible`, `BBoxSelection`, `entityDensityClass` | various | — | Editor/runtime only |

---

## §2 Components inventory

A typical FPS weapon has 25–30 components. Most are non-stat plumbing. The weapon-stat-bearing components are listed first, then the ignored plumbing.

| Component | Status | Doc'd in §2.x | Purpose |
|---|---|---|---|
| `SAttachableComponentParams` | ✓ | §2.1 | AttachDef (type/subType/size/grade/manufacturer/tags), localization, inventory volume |
| `SCItemWeaponComponentParams` | ✓ | §2.2 | The weapon. Firing modes, ammo container, recoil/animation/AR refs, heat, power-mode stats |
| `SCItemMeleeWeaponParams` | ✓ | §2.3 | Knives. Damage/swing parameters |
| `physics` | ✓ | §2.4 | Mass |
| `heatController` | ✗ | §2.5 | Generic heat (different from per-weapon `simplifiedHeat`); only mass-relevant fields used |
| `defaultLoadout` | ✓ | §2.6 | Magazine reference (port→entityClass) |
| `SCItemPurchasableParams` | partial | §2.7 | Display name, displayType (e.g. "@item_displayType_Rifle"), thumbnail; price stored elsewhere |
| `SCItemInspectableParams` | — | — | Inspect-mode rotation limits, animation tags |
| `SInteractionStateMachineParams` | — | — | Hold/aim/reload state graph |
| `SInteractionLinkParams` | — | — | Interaction routing |
| `SItemPortContainerComponentParams` | partial | §2.8 | Sub-ports (magazine_attach, optics_attach, barrel_attach, underbarrel_attach) |
| `SDegradationParams` | partial | §2.9 | Wear-per-shot, lifetime hours, degradation curves |
| `SARDataComponentParams` | — | — | AR overlay (label position, range) |
| `SActorUsableParams` | — | — | First/third-person hand alignment slots |
| `SAnimationControllerParams` | — | — | Animation graph |
| `SEntityComponentSequencerParams` | — | — | Animation sequencer |
| `SEntityComponentEffects` | — | — | Particle/sound effects |
| `SEntityComponentCarryableParams` | — | — | "Can be picked up" flag + interaction binding |
| `SCItemInspectableParams` | — | — | Inspect-mode animations |
| `SPersistentComponentParams` | — | — | Save/load tags |
| `SObservableComponentParams` | — | — | Net replication policy |
| `SEntityInteractableParams` | — | — | Generic interactable bus |
| `SSCSignatureSystemParams` | — | — | EM/IR/CS signature emission curves (mostly zero for handheld) |
| `EntityPhysicalAudioParams` | — | — | Drop/slide/roll audio triggers |
| `AudioPropagationParams` | — | — | Reverb settings |
| `SARDataComponentParams` | — | — | AR overlay |
| `ItemControlComponentParams` | — | — | Master mode (turn on/off) |
| `UIRenderToTextureEntityComponentParams`, `UIBuilding…`, `UIBindings…` | — | — | UI screens (multitool only) |
| `StatusEntityComponentParams` | — | — | Status effects (multitool only) |
| `SCItemRadarComponentParams` | — | — | Multitool's built-in radar (irrelevant for guns) |

---

### §2.1 `SAttachableComponentParams`

Attach metadata + inventory volume + localization. Fully extracted into the top-level stdItem fields.

```
SAttachableComponentParams
  @attachToTileItemPort = NoConnection                                              —
  AttachDef
    @Type = WeaponPersonal | Knife | Grenade                                        ✓ stdItem.Type / fps_equipment[].type
    @SubType = Medium | Small | Large | Gadget | Weapon | Grenade                   ✓ stdItem.Type (composed) / fps_equipment[].subType
    @Size = 2                                                                       ✓ stdItem.Size
    @Grade = 1                                                                      ✓ stdItem.Grade
    @Manufacturer = <GUID→SCItemManufacturer>                                       ✓ stdItem.Manufacturer.{Code,Name}
    @inheritParentManufacturer = 0                                                  —
    @Tags = "stocked klwe_rifle_energy_01 rifle"                                    ✓ stdItem.Tags (split on space)
    @RequiredTags = ""                                                              ✓ fps_equipment[].requiredTags
    @DisplayType = ""                                                               —
    @ignoredAttachAxis = None                                                       —
    @attachCheckCenterOfMass = 0                                                    —
    Localization
      @Name = @item_Nameklwe_rifle_energy_01                                        ✓ stdItem.Name (resolved via translations)
      @ShortName = @item_Nameklwe_rifle_energy_01_short                             ✗ NOT EMITTED
      @Description = @item_Descklwe_rifle_energy_01                                 ✓ stdItem.Description
      displayFeatures
        @Callout1, @Callout2, @Callout3 = @LOC_EMPTY                                ✗ marketing copy, all empty in current build
        @History = @LOC_EMPTY                                                       ✗ marketing copy
        @LogoSimplifiedWhite = ""                                                   —
        @FrontendBackground = ""                                                    —
        @UIPriority = 0                                                             —
    mannequinTags
      @mannequinClassTag = klwe_rifle_energy_01                                     —   animation routing
      @mannequinBaseTag, @mannequinTypeTag = ""                                     —
    inventoryOccupancyVolume.SMicroCargoUnit
      @microSCU = 13000                                                             ✓ stdItem.Volume = 13000
    inventoryOccupancyDimensions { @x, @y, @z }                                     ✗ NOT EMITTED — physical bounding box
    inventoryOccupancyLocalBoundsMin, inventoryOccupancyLocalBoundsMax              ✗ NOT EMITTED
    inventoryOccupancyDimensionsUIOverride.Vec3 { @x, @y, @z }                      ✗ NOT EMITTED — UI grid display override
    inventoryOccupancyFixedGridDimensionsUIV4 { @x, @y }                            ✗ NOT EMITTED — UI grid 2D display
  entityAttachParams                                                                —   empty
  audioAttachParams                                                                 —   audio triggers
```

**Gaps worth surfacing:** `inventoryOccupancyDimensions` (real bounding box for physical inventory), `inventoryOccupancyDimensionsUIOverride` (UI grid display).

---

### §2.2 `SCItemWeaponComponentParams` — the weapon proper

The largest single component. Splits into:

- §2.2.1 Top-level GUID references (recoil, ammo, animation, AR modifier)
- §2.2.2 Generic settings + reticle + AI metadata
- §2.2.3 `connectionParams` — heat & power
- §2.2.4 `noPowerStats` / `underpowerStats` / `overpowerStats` — power-mode multipliers
- §2.2.5 `aimAction` — ADS settings (single instance)
- §2.2.6 `fireActions` — list of firing modes (Burst/Rapid/Single/Charged/Beam/etc.)

#### §2.2.1 Top-level attrs (GUID references + flags)

| Attr | Example | Status | Notes |
|---|---|---|---|
| `@actorProceduralRecoilConfig` | `33b70bb1-…` | ✓ GUID→ | §3.2 ActorProceduralRecoilConfig — per-aim-state modifiers |
| `@ammoContainerRecord` | `0988e9ce-…` | partial | Resolved indirectly via defaultLoadout magazine. Direct primary lookup would let us emit ammo for weapons without magazine ports |
| `@arModifierRecord` | `950caf1e-…` | ✗ GUID→ | Augmented Reality / aim assist modifier — record type **not parsed** |
| `@proceduralAnimationRecord` | `a3558136-…` | ✗ GUID→ | Reload/draw animation reference — record type **not parsed** |
| `@aimableAnglesRecord` | zero-GUID | — | Yaw/pitch limits when mounted; usually empty for FPS |
| `@gimbalModeModifierRecord` | zero-GUID | — | Ship-weapon gimbal modes; FPS = empty |
| `@allowFiringDuringFiremodeSwitch` | 1 | ✗ | Bool — small QoL flag |
| `@ShouldIgnorePrimaryAmmoContainer` | 0 | ✗ | Bool — alt ammo source flag |
| `@fireOnAim` | 0 | ✗ | Bool |
| `@isAllowedInGreenZones` | 0 | ✗ | Bool |
| `@supplementaryFireTime` | 0 | ✗ | Float |
| `@uncollapseOnTurnedOn` | 0 | — | Animation flag |
| `@useAdsHelper` | 1 | — | Animation hint |
| `@geometryTags` | "" | — | Mesh routing |

`secondaryAmmoContainers` — list of additional ammo containers (multi-ammo weapons). **Not parsed.**

`onAmmoEmptyParams.attachmentsToHide` — visual cosmetic. **—**

`defaultAdsCameraOffset { x, y, z }` — ✗ NOT EMITTED (small camera offset when ADS).

`onAttachParams.SWeaponOnAttachParams` — itemPort+animation tag routing. **—**

`reticleParams { @adsReticle, @defaultReticle }` — reticle name string. ✗ NOT EMITTED.

`weaponAIData` — AI combat tuning (separate from player stats):

| Attr | Example | Status | Notes |
|---|---|---|---|
| `@CombatRangeCategory` | `Medium` | ✗ | enum (Short/Medium/Long) |
| `@idealCombatRange` | 30 | ✗ | metres |
| `@maxFiringRange` | 50 | ✗ | metres |
| `@baseAccuracy` | 0.13 | ✗ | float |
| `@bulletBendingAngleLimit`, `@firingValidationAngleTolerance`, `@impactRadiusForFriendlyFire`, `@canShootWhenObstructed` | various | ✗ | AI tuning |
| `accuracyRange { @minimum, @maximum }` | 1, 50 | ✗ | metres |
| `accuracyRangeCurve.points[Vec2]` | 15 points | ✗ | Bezier curve |
| `shootingTimeAccuracyData.timePrecisionCurve` | curve + maxShootingTime=10 | ✗ | accuracy-over-time |
| `weaponAimingMethod.WeaponAIAimingMethodDirect.@enableSpread` | 0 | ✗ | enum |

**Gap:** `weaponAIData` is a meaningful sub-category for AI-vs-player damage modelling but not surfaced today.

#### §2.2.3 `connectionParams` — heat & power coupling

| Path | Example | Status | Notes |
|---|---|---|---|
| `@heatRateOnline` | 25 | ✓ stdItem.Weapon.HeatParameters / `weapon_comp.heatRateOnline` |
| `@heatReduceWhenOverheatIsFixed` | 100000 | ✗ | Spreadsheet col "Heat Reduce When Overheat Is Fixed" |
| `@lockOnOnverheat` | 1 | ✗ | Spreadsheet col "Lock On Overheat" |
| `@maxGlow` | 100 | — | Visual |
| `@powerActiveCooldown` | 1 | ✓ |
| `@glowTag` | zero | — | Visual |
| `simplifiedHeatParams.SWeaponSimplifiedHeatParams.*` |||
| `  @minTemperature` | 0 | ✓ |
| `  @overheatTemperature` | 100 | ✓ |
| `  @coolingPerSecond` | 3 | ✓ |
| `  @timeTillCoolingStarts` | 1 | ✓ |
| `  @overheatFixTime` | 0 | ✓ |
| `  @temperatureAfterOverheatFix` | 0 | ✓ |
| `  @whitelistFPSOverheat` | 0 | ✗ |
| `  @heatModifierCurve` | zero-GUID | — |
| `  temperatureCurveParams.SWeaponSimplifiedHeatParamsTemperatureCurveParams.@temperatureCurve` | GUID | ✗ GUID→ | Heat→damage scaling curve (BezierCurve record) — record type not parsed |
| `  temperatureCurveParams.{xAxisMinMaxValues, yAxisMinMaxValues}` | (-100,140) (0.2,2) | ✗ | curve domain/range |
| `  glowParams { @maxGlowValue, @fadeoutTime, @glowCurve, glowColor }` | various | — | Visual |
| `  heatRangeAudioTriggers` | empty | — | Audio |

**Gaps:** `lockOnOnverheat`, `heatReduceWhenOverheatIsFixed`, `temperatureCurveParams.{xAxisMinMaxValues,yAxisMinMaxValues}`.

#### §2.2.4 Power-mode stat blocks (`noPowerStats`, `underpowerStats`, `overpowerStats`)

Three identical-shape blocks, applied as multipliers when the weapon is at the corresponding power level. All-1.0 means "no change at this power level".

| Path | Status | Notes |
|---|---|---|
| `@fireRate`, `@fireRateMultiplier` | ✓ partial | We extract `fireRateMultiplier` only — absolute `fireRate` (overrides per-mode) not surfaced |
| `@damageMultiplier`, `@damageOverTimeMultiplier` | ✓ |
| `@projectileSpeedMultiplier`, `@chargeTimeMultiplier`, `@heatGenerationMultiplier`, `@soundRadiusMultiplier`, `@ammoCostMultiplier` | ✓ partial | We extract a subset; charged time multiplier missing |
| `@pellets`, `@burstShots`, `@ammoCost` | ✗ | Absolute overrides |
| `@useAlternateProjectileVisuals`, `@useAugmentedRealityProjectiles`, `@disableMisfire` | ✗ | Bools |
| `recoilModifier { 14 multiplier scalars + headRotationMultiplier + aimRecoilModifier + curveRecoil + curveRecoilHead }` | partial | Same shape as ActorProceduralRecoilModifiers (§3.3); we extract `aimSpreadModifier` only |
| `spreadModifier { @min, @max, @firstAttack, @attack, @decay, @additiveModifier }` | ✓ | extracted as `weapon.aimSpreadModifier` |
| `aimModifier { @zoomScale, @secondZoomScale, @zoomTimeScale, @fstopMultiplier, @hideWeaponInADS }` | ✗ | Spreadsheet "Zoom" column |
| `regenModifier { @maxAmmoLoadMultiplier, @maxRegenPerSecMultiplier, @powerRatioMultiplier }` | ✗ | Energy-pool regen tuning |
| `salvageModifier { @extractionEfficiency, @radiusMultiplier, @salvageSpeedMultiplier }` | ✗ | Salvage/multitool only |

**Gap:** Power-mode delta blocks are partly extracted (we surface `noPowerStats/underpowerStats/overpowerStats` flat into output, but with limited fields). Adding `aimModifier.zoomScale` is high-value.

#### §2.2.5 `aimAction.SWeaponActionAimSimpleParams` — ADS

Single instance. Represents aim-down-sights state.

| Attr | Example | Status | Notes |
|---|---|---|---|
| `@aiShootingMode` | Single | ✗ | enum |
| `@zoomScale` | 1.4 | ✗ | **Spreadsheet "Zoom" column** — directly map-able |
| `@zoomTime` | 0.3 | ✗ | aim-in time |
| `@toggleZoomOverride` | 0 | ✗ | bool |
| `@hasReloadModesOnUI` | 0 | — | UI flag |
| `@localisedName`, `@name`, `@uiBindingsTag`, `@entityTag`, `@glintTag` | various | — | UI/runtime |
| `mannequinTag.@tag`, `entityTags.tags` | "" | — | animation routing |
| `dofSettings.SWeaponAimDofSettings { @focalDistance, @focalRange, @fstop }` | 0.2, 2, 100 | ✗ | depth-of-field |
| `aimModifier.SWeaponModifierParams.weaponStats.*` | full power-mode block | ✗ | Same structure as §2.2.4 — applied when ADS active |
| `aimGeometryTags.SWeaponGeometryTagsParams { @firstPerson, @startDelay, @stopDelay, @tags, @thirdPerson }` | various | — | Mesh visibility routing |
| `mannequinTags.SMannequinTagParams.@tag` | ADS | — | animation |
| `aimRTPC.@rtpc`, `aimStart`, `aimStop`, `timeSinceLast*Rtpc` | various | — | Audio |
| `selectableCondition` | empty | — | conditional logic |

**Gaps:** `zoomScale`, `zoomTime`, ADS-specific `weaponStats` block (zoom-active recoil/spread modifiers).

#### §2.2.6 `fireActions` — list of firing modes

Variable-length list. Each entry is one of:

- `SWeaponActionFireBurstParams` — burst-fire (klwe_rifle has two: Burst-3 and Burst-5)
- `SWeaponActionFireRapidParams` — rapid/automatic
- `SWeaponActionFireSingleParams` — single shot
- `SWeaponActionFireChargedParams` — charge-up
- `SWeaponActionFireSequenceParams` — sequence (shotguns with delays)
- `SWeaponActionFireBeamParams` — continuous beam (multitool)

Common attrs across all firing actions:

| Attr | Example | Status | Notes |
|---|---|---|---|
| `@name` | "Burst" | ✓ Firing[].Name |
| `@localisedName` | "@FireMode_Burst" | ✓ Firing[].LocalisedName |
| `@aiShootingMode` | enum (Single/Burst/Auto) | ✗ |
| `@fireRate` | 900 (RPM) | ✓ Firing[].RoundsPerMinute |
| `@cooldownTime` | 0.25 (s) | ✗ | **Spreadsheet "Cooldown Delay"** column |
| `@heatPerShot` | 2.8 | ✓ Firing[].HeatPerShot |
| `@wearPerShot` | 0.04 | ✓ Firing[].WearPerShot |
| `@adaptiveTriggerParams` | zero-GUID | — | PS5 controller |
| `@misfire` | `40fb222b-…` | ✗ GUID→ | **MisfireParams** record — not parsed; controls jam behaviour |
| `@recoil` | `d49257c4-…` | ✗ GUID→ | **WeaponProceduralRecoilConfigDef** — §3.4 — per-mode recoil curves; **major gap** |
| `@entityTag`, `@uiBindingsTag` | various | — | UI/runtime |
| `@hasReloadModesOnUI` | 0 | — |
| `mannequinTag.@tag`, `entityTags.tags` | "" | — | animation routing |
| `switchFireModeAudioTrigger.@audioTrigger` | string | — | audio |
| `selectableCondition` | empty | — | conditional logic |
| `launchParams.SProjectileLauncher.*` ||||
| `  @ammoCost` | 1 | ✓ Firing[].AmmoPerShot |
| `  @damageMultiplier` | 1 | ✓ Firing[].DamageMultiplier |
| `  @pelletCount` | 1 | ✓ Firing[].PelletsPerShot |
| `  @projectileType` | Primary | ✗ | enum (Primary/Secondary/Bomb) |
| `  @soundRadius` | 150 | ✓ Firing[].SoundRadius |
| `  @fireHelper` | "muzzle_flash" | — | mesh helper |
| `  @muzzleHelper` | "" | — | mesh helper |
| `  spreadParams { @min, @max, @firstAttack, @attack, @decay }` | 0.05/2.41/1.21/1.03/5 | ✓ Firing[].Spread |
| `fireFragment { @fragment, @forceWeaponController }` | "burst_fire", 0 | — | animation |
| `startFireAudioTrigger`, `stopFireAudioTrigger`, `dryFireAudioTrigger`, `startFireOneShotAudioTrigger` | various | — | audio |
| `NLPCAudioTriggers` | various | — | audio |
| `burstSizeRTPC.@rtpc`, `fireRateRTPC.@rtpc` | strings | — | audio |
| `fireEffects[SWeaponParticleEffectParams]` (list) | various | — | muzzle flash particles |
| `stopFireEffects[SWeaponParticleEffectParams]` (list) | various | — | vent particles (beam/laser) |
| `vibrationParams.@vibrationImpulse` | 2500 | ✗ | controller rumble |
| `signatureEmitterParams` | empty | — | EM/IR signature on fire |

Burst-specific (`SWeaponActionFireBurstParams`):
| Attr | Example | Status |
|---|---|---|
| `@shotCount` | 3 | ✓ Firing[].ShotPerAction |
| `@innerCooldownTime` | 0.15 | ✗ |

Charged-specific (`SWeaponActionFireChargedParams`):
| Attr | Example | Status |
|---|---|---|
| `@chargeTime` | 3 | ✓ Firing[].FireChargedParameters.ChargeTime |
| `@overchargeTime` | 4 | ✓ FireChargedParameters.OverchargeTime |
| `@overchargedTime` | 2 | ✓ FireChargedParameters.OverchargedTime |
| `@chargeAutomatically` | 0 | ✗ |
| `@fireAutomaticallyOnFullCharge` | 0 | ✗ |
| `@fireOnlyOnFullCharge` | 0 | ✗ |
| `@interpolateChargeBonus` | 1 | ✗ |
| `@maxGlow`, `@glowTag` | 100, GUID | — | Visual |
| `chargingBuff` | empty | — |
| `maxChargeModifier { weaponStats... }` | full power-mode block | ✓ FireChargedParameters.Modifiers — partial |

Sequence-specific (shotguns): `sequenceEntries[{delay, unit, repetitions}]` — ✓ extracted.

**Major gap:** Per-firingMode `@recoil` GUID points to `WeaponProceduralRecoilConfigDef` (§3.4) which contains the **actual** per-mode recoil curves. The `Recoil` block we currently emit (§3.3 ActorProceduralRecoilModifiers) is per-aim-state multipliers, **not** the base curves.

---

### §2.4 `physics`

| Attr | Status | Notes |
|---|---|---|
| `@mass` | ✓ stdItem.Mass | kg |
| `@density`, `@buoyancy`, etc. | — | runtime physics |

---

### §2.5 `heatController`

Different from `simplifiedHeat` inside the weapon component. **Not currently parsed.** Likely a redundant generic heat block.

---

### §2.6 `defaultLoadout`

List of `{portName, entityClassName}` pairs.

| portName | entityClassName | Use |
|---|---|---|
| `magazine_attach` | `klwe_rifle_energy_01_mag` | ✓ Walked to resolve ammo + Capacity |
| `optics_attach` | "" or `behr_optics_tsco_x8_s3` | — |
| `barrel_attach` | "" | — |
| `underbarrel_attach` | "" | — |

The magazine entity itself contains `components.ammo.{maxAmmoCount, initialAmmoCount, ammoParamsRecord, allowAmmoRepool}`. We extract `maxAmmoCount` (Capacity) + walk `ammoParamsRecord` GUID for damage/penetration/etc.

---

### §2.7 `SCItemPurchasableParams`

| Attr | Status | Notes |
|---|---|---|
| `@displayName` | ✓ used as Name fallback |
| `@displayType` | ✗ | "@item_displayType_Rifle" — high-value (weapon class hint) |
| `@displayThumbnail` | — |
| `@allowQuickBuy`, `@allowTryOn`, `@tryOnInteractionText` | — |
| `interactionPoints.WeakPointer.@interactionPoints` | — |

**Gap:** `displayType` could supplement our structural Class derivation for sub-categories that don't show in damage profile.

---

### §2.8 `SItemPortContainerComponentParams`

Sub-port definitions for what can be attached to the weapon. Each `SItemPortDef`:

| Attr | Example | Status | Notes |
|---|---|---|---|
| `@Name` | `magazine_attach` / `optics_attach` / `barrel_attach` / `underbarrel_attach` | ✓ stdItem.Ports[].Name |
| `@MinSize`, `@MaxSize` | 1, 1 / 1, 2 / 2, 2 / 1, 1 | ✓ stdItem.Ports[].MinSize/MaxSize |
| `@Flags` | "" / "inventory" / "inventory energy_barrel" | partial | We surface as bool flags |
| `@PortTags`, `@RequiredPortTags` | weapon-specific filter strings | partial | Port-tag filtering for compatibility |
| `Types.SItemPortDefTypes.{@Type, SubTypes.Enum.@value}` | WeaponAttachment.Magazine/IronSight/Barrel/BottomAttachment | ✓ stdItem.Ports[].Types |
| `defaultItem.{@entityClass, @itemPort}` | usually zero | partial |
| `PitchLimit/YawLimit/RollLimit { @x, @y }` | (0,0) for FPS | — |
| `InteractionPointOffset { x, y, z }` | — |
| `AttachmentImplementation.SItemPortDefAttachmentImplementationBone.Helper` | bone-attachment routing | — |
| `Breakable { @BreakStrain, @Breakable, @YieldStrain, @YoungsModulus }` | all 0 for FPS | — |
| `interactions { @detach, @placeInteractionBlockText, @allowPlaceInteractionFromInventory }` | UI strings | — |
| `linkedItemPorts`, `itemPortRules` | empty for FPS | — |
| `detachDirection { x, y, z }` | (0, 0, -1) | — |

---

### §2.9 `SDegradationParams`

| Attr | Example | Status | Notes |
|---|---|---|---|
| `@StopDegradingIfDestroyed` | 0 | ✗ |
| `accumulators[SWearAccumulatorParams]` |||
| `  @MaxLifetimeHours` | 0 | ✗ | 0 = no time-based wear |
| `  @DamageConversionRate` | 0.01 | ✗ | wear-per-damage |
| `  @AccumulationEventThreshold` | 1 | ✗ | shots before next wear tick |
| `  @AtmosphereMultiplier` | 1 | ✗ |
| `  @PortTags`, `@RequiredPortTags` | "" | — |
| `  @AccumulateOnlyAfterTractorBeam`, `@AccumulateOnlyWhenAttached`, `@AccumulateWhenUnstreamed`, `@StopAccumulationWhenAttached`, `@UseAsTimer` | various bools | ✗ |
| `  @InitialAccumulationRatio`, `@InitialAgeRatio`, `@InitialUsageRatio` | 0 | ✗ | starting wear |
| `  HeatMultipliers { @NormalTemperatureMultiplier, @OverheatTemperatureMultiplier }` | (1, 1) | ✗ |
| `  FunctionalityMultiplier { @UsePowerRatio, FunctionalityMultiplyCurve }` | empty | ✗ |
| `  EffectCurve.points` | empty | ✗ |
| `  degradeFromParentParams` | empty | — |
| `  DegradationPercentageRTPC.@rtpc` | "" | — |

We currently emit **only** `stdItem.Durability.Lifetime = 0` placeholder. The real wear model is here.

---

## §3 External record types referenced

When a weapon attribute is a GUID, it points to a separate top-level record. Below are the schemas of records reachable from a weapon.

### §3.1 `AmmoParams` — projectile data

Reached via `defaultLoadout → magazine.components.ammo.ammoParamsRecord`. **Fully parsed** in `parsed_ammo.json`.

```
AmmoParams.<name>
  @speed (m/s)                          ✓ Ammunition.Speed
  @lifetime (seconds)                   ✓ Ammunition.LifeTime  → Range = speed*lifetime
  @size                                 ✓ Ammunition.Size
  @bulletType                           ✗ enum (1=physical, 2=laser, ...)
  @hitPoints                            ✗
  @impulseScale                         ✗
  @ammoCategory                         ✗ enum
  @inheritVelocity                      ✗ bool
  @noBulletHits, @quietRemoval, @useInConvergence | ✗ bools
  @whizSoundDistance, @shotsPerAudioLoop | — audio
  @spawnType, @UIIconType, @displayName, @showtime | — runtime
  whizSound, ricochetSound, projectileLoopStart/Stop  — audio
  trailParticles                                       — visual
  geometryResourceParams                               — visual
  geometryTransformParams                              — visual
  physicsControllerParams.SEntityPhysicsControllerParams.PhysType
    SEntityParticlePhysicsControllerParams
      @Mass                              ✗ ammo Mass
      @airResistance                     ✗ key for bullet drop calc
      @disableGravity                    ✗ key for bullet drop calc
      @radius, @thickness, @length, @pierceability, @accThrust  | ✗
      @rayCollision, @traceable, @singleContact, @noRoll, @noSpin, @noPathAlignment, @noSelfCollision, @noImpulse, @decoupleHeading, @aiNavigationType, @surfaceIdName | — physics
  lightPoolParams.PooledLightData
      @flareName, @flareScale, @radius, @diffuseMultiplier, @specularMultiplier, @attenuationBulbSize, @animSpeed, @rampTime, @fake, @autoClip, @style, @animPhase, @flareLensOpticsFrustumAngle | — visual
      diffuseColor.{r,g,b}                — visual
  projectileParams.<polymorphic>:
    BulletProjectileParams                — most common
      @impactRadius, @minImpactRadius     ✗
      @ignitionChanceOverride             ✗
      @keepAliveOnZeroDamage              ✗
      @hitType                            ✗ "bullet" / "energy" — enum
      detonationParams                    ✓ ImpactDamage / DetonationDamage
      proximityTriggerParams              ✗
      damage.DamageInfo                   ✓ Ammunition.ImpactDamage{Physical,Energy,Distortion,Thermal,Biochemical,Stun}
      damageDropParams.BulletDamageDropParams
        damageDropMinDistance.DamageInfo  ✓ Ammunition.DamageDrop.MinDistance
        damageDropPerMeter.DamageInfo     ✓ Ammunition.DamageDrop.DropPerMeter
        damageDropMinDamage.DamageInfo    ✓ Ammunition.DamageDrop.MinDamage
      impulseFalloffParams.BulletImpulseFalloffParams
        @minDistance, @dropFalloff, @maxFalloff   ✗ "Force Reaction" spreadsheet tab
      pierceabilityParams.BulletPierceabilityParams
        @damageFalloffLevel1/2/3            ✗ armor-tier penetration
        @maxPenetrationThickness            ✓ via penetrationParams (different scalar)
      penetrationParams.AmmoPenetrationParams
        @basePenetrationDistance, @nearRadius, @farRadius   ✓ Ammunition.Penetration
      visualParams.BulletVisualParams
        @maxLength, @meshOffset, @geometryRadius, @renderFrequency, @renderProbability, @hitEffect | — visual
        Material.@path                      — visual
      alternateVisualParams                 — visual
      electronParams                        ✗ electron-weapon-specific (EMP behaviour)
      additionalProjectilesParams           ✗ multi-projectile (cluster) launches
      hitBehaviors                          ✗ on-hit effects (DoT, debuff)
    MissileProjectileParams                 — different schema (rockets)
    LaserProjectileParams                   — different schema (continuous)
    TachyonProjectileParams                 — different schema (instant beam)
  radarObjectParams                         — runtime
```

**Gaps in our extraction:** `airResistance`+`disableGravity` (bullet drop), `impulseFalloffParams` (force reaction), `pierceabilityParams.damageFalloffLevel1/2/3` (armor tiers), `electronParams` (electron EMP), `hitBehaviors` (on-hit DoT/debuff), `additionalProjectilesParams` (cluster).

### §3.2 `ActorProceduralRecoilConfig` (per weapon, parsed)

```
ActorProceduralRecoilConfig.<name>_Config
  actorProceduralRecoilSetup
    [ActorProceduralRecoilSetup ...]              # filter list
      @filterByAimStanceState  ADS / Hipfire / Any  ✓ Recoil.Setups[].AimStance
      @filterByStanceState                          ✓ .Stance
      @filterByPoseState                            ✓ .Pose
      @filterByMotionSpeed                          (parsed, not emitted)
      @filterByLeanState, @filterByHeldItemType, @filterBySkeleton, @filterByCharacterType, @filterByRestrainedState, @filterByPlayerCamera, @filterByAimingRestriction  | — runtime filters
      @actorProceduralRecoilModifiers   GUID→     §3.3
```

### §3.3 `ActorProceduralRecoilModifiers` (multipliers, parsed + emitted)

```
ActorProceduralRecoilModifiers.<name>_<state>_Modifiers
  actorProceduralHandsRecoilModifiers          ✓ Recoil.Setups[].Hands
    @decay, @endDecay
    @fireRecoilTime
    @fireRecoilStrengthFirst, @fireRecoilStrength
    @angleRecoilStrength
    @useRandomRotation                          (bool)
    @randomness, @randomnessBackPush
    @frontalOscillationRotation, @frontalOscillationStrength, @frontalOscillationDecay, @frontalOscillationRandomness
    @resetCurveRecoilWhenApplying               (bool, currently not surfaced)
    rotation.{x,y,z}
    curveRecoil   (deeply nested per-axis curve modifiers — currently NOT surfaced; only top scalars)
      @recoilTimeModifier, @minDecayTimeModifier, @maxDecayTimeModifier
      positionModifiers.SXYZCurvesWithMaxValuesModifer
        @xMaxValueModifier/@yMaxValueModifier/@zMaxValueModifier
        minLimitsModifier/maxLimitsModifier (Vec3)
        noiseModifier (xNoise/yNoise/zNoise)
      rotationModifiers (same shape)
      positionDecayModifiers/rotationDecayModifiers (decayTimeMultiplierModifier, decayMaxValueModifier, decayMinScalingFactorModifier — all Vec3)
  actorProceduralAimRecoilModifiers            ✓ Recoil.Setups[].Aim
    @pull_left_percentage
    @random_pitch, @random_yaw
    @decay, @end_decay
    @recoil_time, @delay
    max.{x,y}, shot_kick_first.{x,y}, shot_kick.{x,y}
    curveRecoil (same nested structure as above, NOT currently surfaced)
  actorProceduralBodyRecoilModifiers           ✓ Recoil.Setups[].Body
    @hipsPushForce, @hipsDampStrength, @hipsDampStrengthEnd
    @spinePushForceFirst, @spinePushForce, @spineDampStrength, @spineDampStrengthEnd
  actorProceduralHeadRecoilModifiers           ✓ Recoil.Setups[].Head
    @frequency, @smoothFactor, @frequencyNoiseFactor
    @maxDistance, @phase
    @translationNoise, @rotationNoise
    @usePerlinNoise (bool, not surfaced)
    @referenceSpeed, @minSpeed, @minScale, @maxSpeed, @maxScale
    translation.{x,y,z}, rotation.{x,y,z}
    curveRecoil (head-specific curve mods, NOT surfaced)
```

### §3.4 `WeaponProceduralRecoilConfigDef` (per firing-mode base curves, **NOT parsed**)

This is the **major gap**. Reached via `fireActions[].@recoil` GUID. Contains the **actual** procedural recoil curves (not multipliers).

```
WeaponProceduralRecoilConfigDef.<name>_<mode>
  weaponProceduralHandsRecoil.SWeaponProceduralHandsRecoilConfigDef
    @decay, @endDecay
    @fireRecoilTime, @fireRecoilStrengthFirst, @fireRecoilStrength
    @angleRecoilStrength
    @useRandomRotation, @randomness, @randomnessBackPush
    @frontalOscillationRotation/Strength/Decay/Randomness
    rotation.{x,y,z}
    curveRecoil
      @totalRecoilTime, @limitTransitionTime
      @minDecayTime, @maxDecayTime
      positionRecoilTimeModifiers.{x,y,z}, rotationRecoilTimeModifiers.{x,y,z}
      positionCurves.SXYZCurvesWithMaxValues
        @xMaxValue, @yMaxValue, @zMaxValue
        minLimits.{x,y,z}, maxLimits.{x,y,z}
        curves.SXYZCurvesArrays
          xCurves[SCurve.curve.BezierCurve.points[Vec2{x,y}]]   # Bezier control points
          yCurves[...]
          zCurves[...]
        noiseParams.SHandsRecoilCurveNoiseParams
          @xNoise/@yNoise/@zNoise
          @canInvertXCurve/@canInvertYCurve/@canInvertZCurve
      rotationCurves (same shape)
      positionDecay.SDecayTimesAndCurves
        decayTimeMultipliers.{x,y,z}
        decayCurveMaxValues.{x/y/z}MaxValueParams.{maxValue, minScalingFactor, useDecayScaling, useWeaponOrientation}
        decayCurves.SXYZCurves.{xCurve,yCurve,zCurve}.curve.BezierCurve.points
      rotationDecay (same shape)
      rotationOffset.{x,y,z}
      timeModifier (empty in observed sample)
  weaponProceduralAimRecoil.SWeaponProceduralAimRecoilConfigDef
    @pull_left_percentage, @random_pitch, @random_yaw
    @decay, @end_decay, @recoil_time, @delay
    max.{x,y}, shot_kick_first.{x,y}, shot_kick.{x,y}
    curveAimRecoil.SWeaponProceduralAimRecoilCurveConfigDef
      @yawMaxDegrees, @pitchMaxDegrees, @rollMaxDegrees
      @maxFireTime, @recoilSmoothTime, @decayStartTime
      @minDecayTime, @maxDecayTime
      minLimits/maxLimits (Vec3)
      yawPitchRollCurves.SYawPitchRollCurves.{yawCurve, pitchCurve, rollCurve}
      yawPitchRollDecayCurves (same)
      noiseCurves.SAimRecoilNoiseCurves
        @yawNoiseMaxValue, @pitchNoiseMaxValue, @rollNoiseMaxValue
        yawPitchRollNoiseCurves (curves)
  weaponProceduralBodyRecoil.SWeaponProceduralBodyRecoilConfigDef
    @hipsPushForce, @hipsDampStrength, @hipsDampStrengthEnd
    @spinePushForceFirst, @spinePushForce, @spineDampStrength, @spineDampStrengthEnd
  weaponProceduralHeadRecoil.SWeaponProceduralHeadRecoilConfigDef
    @frequency, @smoothFactor, @frequencyNoiseFactor
    @maxDistance, @phase, @translationNoise, @rotationNoise
    @usePerlinNoise, @referenceSpeed, @minSpeed, @minScale, @maxSpeed, @maxScale
    translation.{x,y,z}, rotation.{x,y,z}
    curveRecoil
      @headRecoilTime, @frequency, @smoothingSpeed
      position.SVecWithNoiseParams { offset.Vec3, noise.SHeadRecoilNoiseParams }
      rotation (same shape)
      curves.SAmplitudeFreqencyDecayCurves
        frequencyDecayCurve, amplitudeDecayCurve (Bezier)
```

**This is what the spreadsheet's "Recoil" tab reads.** The ActorProceduralRecoilModifiers we already emit are **multipliers** on these base curves. To match the spreadsheet's "Total Recoil", "Recoil Time", "Limit Transition Time", "Position Curves", etc. columns, this record type must be parsed and surfaced.

### §3.5 `CraftingBlueprintRecord` (parsed + emitted)

```
CraftingBlueprintRecord.BP_CRAFT_<name>
  blueprint.CraftingBlueprint
    @category                                           ✗ category GUID (item type taxonomy)
    @blueprintName                                      — placeholder
    processSpecificData.CraftingProcess_Creation
      @entityClass    GUID→ target item                 ✓ index key
    tiers.[CraftingBlueprintTier]                       ✓ Crafting.Tiers
      recipe.CraftingRecipe
        costs.CraftingRecipeCosts
          craftTime.TimeValue_Partitioned
            @days/@hours/@minutes/@seconds              ✓ CraftTime
          mandatoryCost.CraftingCost_Select count="N"
            options.[CraftingCost_Select count="1"]     ✓ Slots[]
              nameInfo
                @debugName "FRAME"/"WIRING"/"LENSES"    ✓ Slots[].Name
                @displayName "@crafting_ui_slotname_*"  ✓ Slots[].DisplayName
              context.CraftingCostContext_ResultGameplayPropertyModifiers
                gameplayPropertyModifiers.CraftingGameplayPropertyModifiers_List
                  gameplayPropertyModifiers
                    [CraftingGameplayPropertyModifierCommon]
                      @gameplayPropertyRecord  GUID→ §3.6 GPP
                      valueRanges
                        [CraftingGameplayPropertyModifierValueRange_Linear]
                          @startQuality / @endQuality (0–1000)   ✓ Modifiers[].StartQuality/EndQuality
                          @modifierAtStart / @modifierAtEnd      ✓ Modifiers[].ModifierAtStart/AtEnd
              options
                [CraftingCost_Resource | CraftingCost_Item]
                  @resource (GUID) | @entityClass (GUID)  ✓ Costs[].Reference (resource resolution NOT yet)
                  quantity.{SStandardCargoUnit | SCentiCargoUnit}
                    @standardCargoUnits | @centiSCU      ✓ Costs[].Quantity (in SCU)
          optionalCosts                                  ✗ optional crafting upgrades
        results                                          ✗ usually empty (target = entityClass)
      research                                           ✗ research-progression chain
```

**Gaps:** `optionalCosts`, `research`, `category` resolution.

### §3.6 `CraftingGameplayPropertyDef` (parsed + emitted in Crafting block)

```
CraftingGameplayPropertyDef.<className>
  @propertyName  "@StatName_GPP_Weapon_Damage"   ✓
  @unitFormat    "@StatUnits_Percent"             ✓
  className                                       ✓ ("GPP_Weapon_Damage" etc.)
```

14 records exist in the catalogue (7 weapon + 4 armor + 2 crafter + 1 other).

### §3.7 `MisfireParams` — **NOT parsed**

Reached via `fireActions[].@misfire` GUID. Schema unknown. Likely contains misfire chance + clear-time + animation triggers. **Investigation needed.**

### §3.8 `WeaponProceduralAnimationConfig` — **NOT parsed**

Reached via weapon's `@proceduralAnimationRecord` GUID. Schema unknown. Likely contains reload animation timings.

### §3.9 `WeaponARModifierConfig` — **NOT parsed**

Reached via weapon's `@arModifierRecord` GUID. Schema unknown. Likely contains AR/aim-assist modifiers.

### §3.10 `BezierCurve` — **inline**

Used for spread, accuracy, recoil decay curves. Schema:

```
BezierCurve
  @useLUT (bool)
  points.[Vec2{@x,@y}]   # control points (in/anchor/out triples)
```

We currently capture none of these — only scalar inputs to the curves.

### §3.11 `SCItemManufacturer` (parsed + emitted)

Reached via attachDef `@Manufacturer` GUID. Documented. ✓.

---

## §4 Extraction-status matrix (FPS-weapon stat coverage)

Property categories from finder.cstone.space's spreadsheet ("SC FPS Data 4.7"), mapped to current extraction status.

| Spreadsheet category | Sub-property | Status | XML location |
|---|---|---|---|
| **Item identity** | ClassName / Name / Manufacturer / Type / SubType / Size / Grade / Tags | ✓ | SAttachableComponentParams.AttachDef |
| **Mass / Volume** | Mass (kg) / μSCU | ✓ | physics.@mass / SAttachableComponentParams.AttachDef.inventoryOccupancyVolume.SMicroCargoUnit.@microSCU |
| **Class derivation** | Energy/Plasma/Laser/Electron/Ballistic | ✓ struct | derived from ammo damage profile + damageDrop |
| **Magazine** | Capacity (Ammo Count) | ✓ | defaultLoadout → mag.components.ammo.@maxAmmoCount |
| **Magazine** | Initial / Allow Repool | ✗ | mag.components.ammo.{initialAmmoCount,allowAmmoRepool} |
| **Ammo / projectile** | Speed / Range / Lifetime / Size | ✓ | AmmoParams.@{speed,lifetime,size} |
| **Ammo / damage** | Physical/Energy/Distortion/Thermal/Biochemical/Stun | ✓ | AmmoParams.projectileParams.BulletProjectileParams.damage.DamageInfo |
| **Ammo / damage drop** | MinDistance / DropPerMeter / MinDamage | ✓ | AmmoParams.projectileParams.BulletProjectileParams.damageDropParams.BulletDamageDropParams |
| **Ammo / detonation** | Detonation per type + radius | ✓ | AmmoParams.projectileParams.BulletProjectileParams.detonationParams |
| **Ammo / penetration** | basePenetrationDistance / nearRadius / farRadius | ✓ | AmmoParams.projectileParams.BulletProjectileParams.penetrationParams |
| **Bullet drop** | airResistance + disableGravity + Mass | ✗ | AmmoParams.physicsControllerParams.…SEntityParticlePhysicsControllerParams |
| **Force Reaction** | impulseScale + impulseFalloff{minDistance,dropFalloff,maxFalloff} | ✗ | AmmoParams.@impulseScale + AmmoParams.projectileParams.BulletProjectileParams.impulseFalloffParams |
| **Armor penetration** | damageFalloffLevel1/2/3 / maxPenetrationThickness | ✗ | AmmoParams.projectileParams.BulletProjectileParams.pierceabilityParams |
| **Electron-specific** | electronParams | ✗ | AmmoParams.projectileParams.BulletProjectileParams.electronParams |
| **Per fire-mode** | Name / RPM / FireType / PelletsPerShot / ShotPerAction / AmmoPerShot / DamageMultiplier / SoundRadius / HeatPerShot / WearPerShot | ✓ | fireActions[].* |
| **Per fire-mode** | Spread (min/max/firstAttack/attack/decay) | ✓ | fireActions[].launchParams.SProjectileLauncher.spreadParams |
| **Per fire-mode** | Cooldown delay | ✗ | fireActions[].@cooldownTime |
| **Per fire-mode** | innerCooldownTime (burst) | ✗ | fireActions[SWeaponActionFireBurstParams].@innerCooldownTime |
| **Per fire-mode** | Misfire (jam) | ✗ GUID→ | fireActions[].@misfire (record schema unknown) |
| **Per fire-mode** | Vibration (controller rumble) | ✗ | fireActions[].vibrationParams.@vibrationImpulse |
| **Charge mode** | ChargeTime / OverchargeTime / OverchargedTime | ✓ | fireActions[SWeaponActionFireChargedParams].@chargeTime/etc |
| **Charge mode** | chargeAutomatically / fireOnFullCharge / fireOnlyOnFullCharge / interpolateChargeBonus | ✗ | same |
| **Charge mode** | maxChargeModifier (full power-mode block applied at full charge) | ✓ partial | extracted as Modifiers (DamageMultiplier, FireRateMultiplier, ProjectileSpeedMultiplier) |
| **Sequence (shotgun)** | sequenceEntries[{delay,unit,repetitions}] | ✓ | fireActions[SWeaponActionFireSequenceParams].sequenceEntries |
| **Heat** | minTemp / overheatTemp / coolingPerSecond / timeTillCoolingStarts / overheatFixTime / temperatureAfterOverheatFix | ✓ | weapon.connectionParams.simplifiedHeatParams.SWeaponSimplifiedHeatParams |
| **Heat** | lockOnOverheat / heatReduceWhenOverheatIsFixed | ✗ | weapon.connectionParams.@lockOnOnverheat / @heatReduceWhenOverheatIsFixed |
| **Heat** | temperatureCurveParams (heat-vs-damage scaling curve) | ✗ GUID→ | record type unknown |
| **Power modes** | noPower/underpower/overpower stat blocks | ✓ partial | weapon.{noPowerStats,underpowerStats,overpowerStats} — only fireRate/damage/etc multipliers |
| **Repool (regen)** | bulletsPerSecond / unstowMagDuration / fullMagMergeDuration | ✓ | weapon.ammoRepool (SWeaponAmmoRepoolParams) |
| **Power regen** | requestedRegenPerSec / regenerationCooldown / regenerationCostPerBullet / requestedAmmoLoad / maxAmmoLoad / maxRegenPerSec | ✓ | weapon.regenConsumer (SWeaponRegenConsumerParams) — energy-pool weapons |
| **ADS / aim** | zoomScale / zoomTime | ✗ | aimAction.SWeaponActionAimSimpleParams.@zoomScale/@zoomTime |
| **ADS / aim** | dofSettings (focal distance/range/fstop) | ✗ | aimAction.dofSettings.SWeaponAimDofSettings |
| **ADS / aim** | spread modifier when ADS | ✓ partial | aimAction.aimModifier.SWeaponModifierParams.weaponStats.spreadModifier (extracted as `weapon.aimSpreadModifier`) |
| **ADS / aim** | recoil modifier when ADS | ✓ struct | via ActorProceduralRecoilConfig.setups[aimStance=ADS] |
| **Recoil base curves** | per-mode procedural recoil (hands/aim/body/head) | ✗ GUID→ | fireActions[].@recoil → WeaponProceduralRecoilConfigDef (§3.4) — **not parsed** |
| **Recoil multipliers** | per-aim-state (ADS/Hipfire) | ✓ | ActorProceduralRecoilConfig + ActorProceduralRecoilModifiers |
| **Recoil power-mode** | recoilModifier blocks in noPower/underpower/overpower/aimAction | ✗ | weapon.{noPowerStats,…}.recoilModifier |
| **Crafting** | CraftTime / Slots[Modifiers + Costs] | ✓ | CraftingBlueprintRecord (per-target-GUID) |
| **Crafting GPP units** | StatUnits_Percent / RPM / Time / Temperature | ✓ | CraftingGameplayPropertyDef.@unitFormat |
| **Degradation** | MaxLifetimeHours / DamageConversionRate / AccumulationEventThreshold / HeatMultipliers / FunctionalityMultiplier / EffectCurve | ✗ | SDegradationParams.accumulators[SWearAccumulatorParams] |
| **Inspect** | inspectAnimations / inspectRotateLimits | — | SCItemInspectableParams |
| **Sub-ports** | magazine_attach / optics_attach / barrel_attach / underbarrel_attach | ✓ | SItemPortContainerComponentParams.Ports |
| **Sub-ports** | port flags / required tags | ✓ partial | SItemPortDef.@Flags/@RequiredPortTags |
| **AI tuning** | weaponAIData (combat range, accuracy curves) | ✗ | weapon.weaponAIData |
| **Misc flags** | allowFiringDuringFiremodeSwitch / fireOnAim / isAllowedInGreenZones / supplementaryFireTime / ShouldIgnorePrimaryAmmoContainer | ✗ | weapon top-level attrs |
| **AR / aim assist** | arModifierRecord | ✗ GUID→ | record type unknown |
| **Procedural animation** | proceduralAnimationRecord | ✗ GUID→ | record type unknown |
| **Adaptive trigger** | adaptiveTriggerParams (PS5) | — | fireActions[].@adaptiveTriggerParams (consoles only) |

---

## §5 Summary

### What we extract well today

- All identity/manufacturer/size/grade/tag fields
- Mass + Volume
- Magazine capacity (Capacity)
- Per-firing-mode common fields (RPM, spread, pellets, ammo cost, heat per shot, wear, sound radius)
- Charge-mode fields (ChargeTime, OverchargeTime, modifiers)
- Sequence fire (shotguns) with delays
- Ammunition damage profile (all 6 damage types) + damage drop + penetration
- Ammo speed/lifetime/range
- Heat (simplifiedHeat block)
- Repool / regen consumer
- Sub-ports (magazine/optics/barrel/underbarrel)
- ADS spread modifier (`aimSpreadModifier`)
- Recoil **multipliers** per aim-state
- Crafting (CraftTime + Slots with modifiers + costs)
- Class derivation (Ballistic / Laser / Plasma / Electron) — structurally from ammo damage profile

### Highest-value gaps (priority)

| Priority | Gap | Why |
|---|---|---|
| **P1** | `WeaponProceduralRecoilConfigDef` (§3.4) per-firing-mode | What the spreadsheet's "Recoil" tab actually shows. ActorProceduralRecoilModifiers without these are just unitless multipliers. |
| **P1** | `aimAction.@zoomScale/@zoomTime` | First-class FPS UX value, single attr each |
| **P1** | `fireActions[].@cooldownTime`, `@innerCooldownTime` | Affects sustained DPS calc. Spreadsheet has "Cooldown Delay" column |
| **P2** | `AmmoParams.physicsControllerParams.…@airResistance/@disableGravity/@Mass` | Bullet drop calc |
| **P2** | `AmmoParams.projectileParams.BulletProjectileParams.impulseFalloffParams` | Force reaction — knockback |
| **P2** | `AmmoParams.projectileParams.BulletProjectileParams.pierceabilityParams.@damageFalloffLevel1/2/3` | Armor-tier penetration |
| **P2** | `connectionParams.@lockOnOnverheat/@heatReduceWhenOverheatIsFixed` | Heat-recovery model |
| **P3** | `SDegradationParams.accumulators[SWearAccumulatorParams]` | Wear/durability model |
| **P3** | `weapon.weaponAIData` | NPC-specific tuning |
| **P3** | `MisfireParams` record schema | Jam mechanics |
| **P4** | `WeaponARModifierConfig` record schema | Aim-assist (likely platform-specific) |
| **P4** | `WeaponProceduralAnimationConfig` record schema | Reload-animation timings (cosmetic) |
| **P4** | `BezierCurve` capture for spread/accuracy curves | Currently scalar-only — curves give per-shot trajectory |

### Components intentionally ignored (audio/visual/UI plumbing)

`SAnimationControllerParams`, `SEntityComponentSequencerParams`, `SEntityComponentEffects`, `EntityPhysicalAudioParams`, `AudioPropagationParams`, `SARDataComponentParams`, `SCItemInspectableParams`, `SInteractionStateMachineParams`, `SInteractionLinkParams`, `SActorUsableParams` (alignment slots), `SObservableComponentParams`, `SPersistentComponentParams`, `SEntityInteractableParams`, `SEntityComponentCarryableParams`, `ItemControlComponentParams`, plus all UI* components (multitool only). These do not contain weapon stats.
