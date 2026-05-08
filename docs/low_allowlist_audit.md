# LOW-tier allowlist audit — `nova/builders/stditem.py`

| Set | Members | Verdict | Confidence |
|---|---:|---|---|
| `_WEAPONDEFENSIVE_CN_WITHOUT_CLASS` | 4 | NO STRUCTURAL SIGNAL | high |
| `_CLASS_VALUE_OVERRIDES` | 16 | PARTIAL (capital-ship subset reducible) | medium |
| `_TOOLARM_WITH_TURRET` | 3 | PARTIAL (component-presence catches members but over-matches) | medium |
| `_CLASS_OMIT_CLASSNAMES` | 15 | PARTIAL (PowerPlant subset reducible) | medium |
| `_TURRETS_WITHOUT_CLASS` | 10 | NO STRUCTURAL SIGNAL | medium |
| `_PAINTS_WITHOUT_CLASS` | 10 | NO STRUCTURAL SIGNAL | high |
| `_MISSILERACK_WITHOUT_CLASS` | 23 | NO STRUCTURAL SIGNAL | high |
| `_ARMOR_MEDIUM_WITH_CLASS` | 18 | NO STRUCTURAL SIGNAL | high |
| `_FPS_CLASS_OMIT` | 3 | NO STRUCTURAL SIGNAL | medium |
| `_FPS_CLASS_EMPTY` | 7 | NO STRUCTURAL SIGNAL — editorial empty-Class allowlist | high |
| `_FPS_CLASS_BY_CLASSNAME` | 15 | PARTIAL (multitool subset reducible) | medium |

Notes on confidence: "high" means investigation produced a near-categorical
answer (full corpus check or simulation); "medium" means there's a candidate
discriminator but it either over-matches non-members or only handles a subset.

**Implemented (commit 772187e):** `_MISSILERACK_WITHOUT_MASS` (2 entries)
and `_MASS_FORCE_INCLUDE` (10 entries) confirmed dead code by build
byte-diff and removed. Their sections were dropped from this doc.
`_FPS_CLASS_EMPTY` was *also* flagged as dead code by the original
audit but byte-diff revealed it was wrong (5 of 7 entries regress to
non-empty Class via the structural ammo-damage-profile rule); the
verdict has been corrected to `NO STRUCTURAL SIGNAL — editorial`.

---

## 1. `_WEAPONDEFENSIVE_CN_WITHOUT_CLASS` (line 88, 4 members)

**Members.** `MISC_Reliant_CML_Chaff`, `MISC_Reliant_CML_Flare`,
`MRAI_Guardian_CML_Decoy`, `MRAI_Guardian_CML_Noise`.

**What the set toggles.** Inside the inverted-Class branch for
`WeaponDefensive.CountermeasureLauncher`. Code path
`build_std_item` ~line 666:
```python
if class_name in _WEAPONDEFENSIVE_CN_WITHOUT_CLASS:
    should_have_class = False
elif mfr_code in _WEAPONDEFENSIVE_MFR_WITH_CLASS:
    should_have_class = True
```
The 4 members override the manufacturer-code allowlist (MIS) which would
otherwise force Class.

**Structural fields inspected.** All four members share:
- `type='WeaponDefensive'`, `subType='CountermeasureLauncher'`
- `tags=''`, `requiredTags=''`
- `size=1`, `grade=1`, `volume=84000`
- Same components keys as 166 sibling non-members:
  `['ItemControlComponentParams', 'SARDataComponentParams', 'SCItemPurchasableParams', 'SGeometryResourceParams', 'ammo', 'health', 'heatController', 'physics', 'weapon']`

**Side-by-side, MISC mfr group only:**
```
[*] MISC_Reliant_CML_Chaff      desc='@item_DescMISC_Reliant_CML_Chaff'
[ ] MISC_Fortune_CML_Chaff      desc='@item_DescMISC_Prospector_CML_Chaff'
[ ] MISC_Hull_A_CML_Chaff       desc='@item_DescMISC_Prospector_CML_Chaff'
[ ] MISC_Prospector_CML_Chaff   desc='@item_DescMISC_Prospector_CML_Chaff'
```
Members have a *unique-per-className description* (`@item_DescMISC_Reliant…`)
while non-members borrow `@item_DescMISC_Prospector…`. That's almost
the inverse of the rule we'd want — uniqueness of description should
correlate with *more* descriptive Class, not less.

The MRAI items do the opposite: they re-use AEGS/JOKR descriptions and
*are* in the omit set.

Reference confirms (`temp/reference/entry_3.json`):
- 4 set members → Class missing.
- `MISC_Fortune_CML_Chaff`, `MISC_Prospector_CML_Chaff`, `MISC_Hull_A_CML_Chaff` → `Class=""`.
- `AEGS_Avenger_CML_Chaff` → Class missing (driven by the regular inverted rule, AEGS is not in MFR_WITH_CLASS).
- `AEGS_Firebird_CML_Chaff` (placeholder desc) → `Class="@LOC_PLACEHOLDER"`.

**Discriminator candidates tried.**
- Manufacturer code: members are MIS, but most other MIS items get Class. Fails.
- `requiredTags`: empty for both members and non-members. Fails.
- Description sharing pattern: anti-correlated. Fails.
- Component presence: identical across all 170 CountermeasureLaunchers. Fails.

**Verdict: NO STRUCTURAL SIGNAL.** This set encodes editorial decisions
specific to two ship variants (Reliant, Guardian). The four classnames
share neither manufacturer nor any other attachDef/component field that
isn't also true of non-omitted MIS-mfr items.

---

## 2. `_CLASS_VALUE_OVERRIDES` (line 103, 16 members)

**Members.** Mix of `COOL_*`, `POWR_*`, `QDMP_*`, `QDRV_*`, `QED_*`,
`SHLD_*` (capital-ship components), plus 3 outliers: `Paint_325a_microTech_Security`,
`RADR_S02_Fake`, `RADR_Default`.

**What the set toggles.** Two-stage:
1. Forces `should_have_class=True` (line 647).
2. Forces `si["Class"] = _CLASS_VALUE_OVERRIDES[class_name]` (line 680).

**Structural breakdown of members.**

| ClassName | Override | full_type | mfrGuid | Size |
|---|---|---|---|---|
| COOL_AEGS_S04_Reclaimer | `Industrial` | Cooler.UNDEFINED | (EMPTY) | 4 |
| COOL_ORIG_S04_890J_SCItem | `Civilian` | Cooler.UNDEFINED | (EMPTY) | 4 |
| POWR_LPLT_S00_Radix_SCItem_SM_TE | `Civilian` | PowerPlant.Power | (EMPTY) | 0 |
| POWR_ORIG_S04_890J_SCItem | `Civilian` | PowerPlant.Power | (EMPTY) | 4 |
| QDRV_ORIG_S04_890J_SCItem | `Civilian` | QuantumDrive.UNDEFINED | (EMPTY) | 4 |
| SHLD_AEGS_S04_Reclaimer_SCItem | `Industrial` | Shield.UNDEFINED | (EMPTY) | 4 |
| COOL_ACOM_S01_QuickCool_SCItem | `""` | Cooler.UNDEFINED | 5d616e6f | 1 |
| QDMP_RSI_S03_Captor | `""` | QuantumInterdictionGenerator.UNDEFINED | 093e6eba | 3 |
| QED_RSI_S03_Scorpius | `""` | QuantumInterdictionGenerator.UNDEFINED | 093e6eba | 3 |
| SHLD_GODI_S04_Idris_*_SCItem (×2) | `""` | Shield.UNDEFINED | 57bfcf3d | 4 |
| COOL_WCPR_S03_Elsen_SCItem | `Civilian` | Cooler.UNDEFINED | cf4a74bf | 3 |
| SHLD_RSI_S04_Polaris_SCItem | `Industrial` | Shield.UNDEFINED | 093e6eba | 4 |
| Paint_325a_microTech_Security | `@LOC_PLACEHOLDER` | Paints.UNDEFINED | 1e47a9ec | 1 |
| RADR_S02_Fake | `@LOC_PLACEHOLDER` | Radar.MidRangeRadar | (EMPTY) | 2 |
| RADR_Default | `@item_Desc_RADR_Default` | Radar.MidRangeRadar | (EMPTY) | 1 |

**Sub-pattern A — empty-mfrGuid + Cooler/PowerPlant/QuantumDrive components (5 items):**
The members `COOL_AEGS_S04_Reclaimer`, `COOL_ORIG_S04_890J_SCItem`,
`POWR_ORIG_S04_890J_SCItem`, `QDRV_ORIG_S04_890J_SCItem`,
`SHLD_AEGS_S04_Reclaimer_SCItem` all share *no* manufacturer record but
have a real description. Without an mfr code, the generic `MANUFACTURER_CLASS`
lookup returns "" — the override forces `Industrial`/`Civilian`.

**This is structurally derivable** — the override values come from the
*ship* the item is bound to (Reclaimer→Industrial, 890J→Civilian). But
the linkage from item → ship class isn't carried in the item record.
You'd need a vehicle cross-reference.

**Sub-pattern B — `Class=""` for QED/Shield items (5 items):**
`QDMP_RSI_S03_Captor`, `QED_RSI_S03_Scorpius`,
`SHLD_GODI_S04_Idris_*_SCItem`. These have non-empty mfrGuid → generic
rule would apply `MANUFACTURER_CLASS["RSI"]="Civilian"` /
`MANUFACTURER_CLASS["GODI"]="Military"` etc — wrong.

The override forces `""`. There is no structural signal that distinguishes
these from sibling items that *do* get the manufacturer class.

**Sub-pattern C — Outliers (3 items):**
`Paint_325a_microTech_Security`, `RADR_S02_Fake`, `RADR_Default` are
unique editorial assignments. `RADR_Default` and `RADR_S02_Fake` have
empty mfrGuid → generic `Class=""`, but ref wants `@item_Desc_RADR_Default`
(matching `Description`) and `@LOC_PLACEHOLDER` respectively.

**Discriminator candidates tried.**
- Empty mfrGuid: 16 147 items have it; over-matches by ×1000.
- Empty mfrGuid + Cooler/Shield/PowerPlant + size>=4: catches 4–5 of the
  capital-ship subset cleanly, but misses the rest.

**Verdict: PARTIAL.** Only the capital-ship empty-mfr subset is
structurally derivable, and even then it requires a *ship-class lookup*
the item record doesn't carry (would need vehicle cross-ref).

**Implementation plan (partial — sub-pattern A only):**
Build a vehicle-level lookup `ship_classname → MANUFACTURER_CLASS[ship.mfr_code]`
indexed by item references. For items whose `manufacturerGuid` is empty
*and* whose component type is in `_COMPONENT_TYPES_CLASSED`, use the
referencing ship's manufacturer class. Validate against the 5 capital-ship
members. The remaining 11 items would still need a name-based override
list. Likely not worth it given partial reduction.

---

## 3. `_TOOLARM_WITH_TURRET` (line 124, 3 members)

**Members.** `MISC_Fortune_Salvage_Arm`, `RSI_Salvation_Salvage_Arm_Left`,
`RSI_Salvation_Salvage_Arm_Right`.

**What the set toggles.** `skip_turret = (full_type == "ToolArm.UNDEFINED" and className not in _TOOLARM_WITH_TURRET)` (line 901). Members expose
the `Turret` block; non-members suppress it.

**Structural fields.** All ToolArm.UNDEFINED items (14 total):

| ClassName | hasSCItemTurretParams | tags |
|---|---|---|
| AEGS_Reclaimer_Salvage_Arm | False | salvageMount |
| ARGO_MOTH_Salvage_Arm | False | salvageMount |
| ARGO_MPUV_Arm | False | miningMount |
| ARGO_SRV_MainTractorBeamArm | False | miningMount |
| DRAK_Golem_Mining_Arm | False | $miningMount |
| DRAK_Vulture_Salvage_Arm_Left | **True** | salvageMount |
| DRAK_Vulture_Salvage_Arm_Right | **True** | salvageMount |
| ESPR_Prowler_Utility_Tractor_Beam_Arm | False | miningMount |
| MISC_Fortune_Salvage_Arm | **True** | salvageMount |
| MISC_Prospector_Mining_Arm | False | miningMount |
| RSI_Hermes_Utility_Tractor_Beam_Arm | False | (empty) |
| RSI_Salvation_Salvage_Arm_Left | **True** | salvageMount |
| RSI_Salvation_Salvage_Arm_Right | **True** | salvageMount |
| RSI_Zeus_Tractor_Beam_Arm | False | miningMount |

**Discriminator candidate: `components.SCItemTurretParams` presence.**
- Members with SCItemTurretParams: 3/3 (100%).
- Non-members with SCItemTurretParams: 2/11 (DRAK_Vulture_Salvage_Arm_Left/Right).

**Coverage stats.** 3/3 members caught. But 2 non-members (DRAK_Vulture
salvage arms) also have the component. The current code suppresses
Turret block for them; if we switched to "expose Turret iff component
present", DRAK_Vulture would gain a Turret block.

**Verification needed.** Need to check ref output for DRAK_Vulture salvage
arms — does ref expose Turret for them too? If yes, the structural rule
is correct and the current allowlist is *missing* DRAK_Vulture (under-match
in current code, not the structural alternative). If no, the allowlist
encodes an editorial decision that overrides component presence.

**Verdict: PARTIAL.** Strong structural signal but possible
under-coverage in current allowlist. Worth checking ref output for
DRAK_Vulture before switching.

**Implementation plan.**
1. In `temp/reference/entry_3.json` (or matching ref slice), look up
   `DRAK_Vulture_Salvage_Arm_Left` — does it have a `Turret` field?
2. If yes: replace the allowlist with
   ```python
   skip_turret = (full_type == "ToolArm.UNDEFINED"
                  and "SCItemTurretParams" not in components)
   ```
   This expands the rule to all 5 component-bearing arms (3 current
   members + 2 DRAK_Vulture). Verify diff against ref.
3. If no: ref's rule is editorial and the allowlist must stay.

---

## 4. `_CLASS_OMIT_CLASSNAMES` (line 132, 15 members)

**Members per full_type:**
- PowerPlant.Power: 3 (`POWR_AEGS_S04_Idris/Reclaimer_SCItem`, `POWR_RSI_S04_Bengal_SCItem`)
- Radar.MidRangeRadar: 3 (`RADR_GNRP_S03_Idris_TEMP`, `RADR_RSI_S04_Polaris`, `RADR_WLOP_S03_Lephari`)
- Turret.BallTurret: 2 (`ANVL_Terrapin_Nose_Turret_S3`, `CNOU_Mustang_Nose_Turret_S3`)
- WeaponMining.Gun: 2 (`Mining_Laser_SHIN_Hofstede_S0`, `Mining_Laser_THCN_Helix_S0`)
- Flair_Cockpit.Flair_Static: 2 (Bobblehead_01/02)
- Module.UNDEFINED: 1 (`UMNT_ANVL_S5_Rotodome_Mk2`)
- Missile.Torpedo: 1 (`MISL_S09_CS_TALN_Argos_2`)
- WeaponGun.Gun: 1 (`BEHR_LaserCannon_S2_CleanAir`)

**What the set toggles.** First-line fast-path: when `class_name in
_CLASS_OMIT_CLASSNAMES`, force `should_have_class=False`.

**Sub-pattern: capital-ship PowerPlant.** Discriminator
`type=='PowerPlant' and subType=='Power' and size>=4 and not
manufacturerGuid and name != '@LOC_PLACEHOLDER'` matches:
```
POWR_AEGS_S04_Idris_SCItem    (in set)
POWR_AEGS_S04_Reclaimer_SCItem (in set)
POWR_ORIG_S04_890J_SCItem     (NOT in set — in _CLASS_VALUE_OVERRIDES with Class='Civilian')
POWR_RSI_S04_Bengal_SCItem    (in set)
```
3/3 members caught, but 1 non-member also matches. So *almost* clean —
but POWR_ORIG_S04_890J is editorially classed `Civilian`, breaking the rule.

**Sub-pattern: ship-integrated turrets with placeholder description.**
The 2 BallTurret members (`ANVL_Terrapin_Nose_Turret_S3`,
`CNOU_Mustang_Nose_Turret_S3`) have `requiredTags='ANVL_Terrapin_Base'`
and `'CNOU_Mustang_Base'` — a strong ship-binding signal. But many other
ship-bound BallTurrets DO get Class. Not derivable.

**Sub-pattern: `Mining_Laser_*_S0` placeholders.** The 2 mining members
have `desc='@item_descMining_Head_S00_<Family>_SCItem'` (lowercase
'desc' segment; uppercase elsewhere). All sibling items use
`'@item_Mining_MiningLaser_<…>_Desc'` (uppercase). That's a real
structural difference but a fragile one — depends on CIG's stable use of
case (which they have empirically not maintained).

**Other items.** Each is a one-off:
- `BEHR_LaserCannon_S2_CleanAir`: a special variant of an S2 LaserCannon.
- `MISL_S09_CS_TALN_Argos_2`: a torpedo with className suffix `_2`.
- `RADR_GNRP_S03_Idris_TEMP`: name has `_TEMP` suffix.
- `Bobblehead_01/02`: cockpit flair, distinct from generic Flair_Static.
- `UMNT_ANVL_S5_Rotodome_Mk2`: Module subtype, ship-integrated rotodome.

No structural attribute they share that isn't shared by some non-omitted
sibling.

**Verdict: PARTIAL.** Only the PowerPlant.S04 sub-pattern is *almost*
derivable, but contradicted by `POWR_ORIG_S04_890J_SCItem` which is in a
different list with a non-empty Class.

**Implementation plan.** Not recommended. The reduction would catch 3/15
items but introduce a conflict with `_CLASS_VALUE_OVERRIDES`. The
remaining 12 items have no shared structural signal.

---

## 5. `_TURRETS_WITHOUT_CLASS` (line 150, 10 members)

**Members.** `ANVL_Asgard_Nose_Turret_S4`, `ANVL_Valkyrie_Nose_Turret_S3`,
`BEHR_PC2_Dual_S1`, `DRAK_Dual_S1`, `DRAK_Dual_S3`, `Default_Fixed_Mount_S3`,
`Default_Fixed_Mount_S4`, `MISC_Starlancer_TAC_Missile_Gimbal`,
`MISC_Starlancer_TAC_Missile_Gimbal_R`, `ORIG_85X_Turret`.

**What the set toggles.** `Turret.GunTurret + className in set →
should_have_class=False` (line 657).

**Structural breakdown of all `Turret.GunTurret` (153 total):**
- Members with non-empty `requiredTags`: 7/10
- Non-members with non-empty `requiredTags`: 102/143

So `requiredTags` presence is *common* in the parent set; not a discriminator.

**Detailed comparison:**

| ClassName | mfrGuid | size | tags | reqT |
|---|---|---|---|---|
| ANVL_Asgard_Nose_Turret_S4 | b922abdb | 3 | $anvl_asgard | anvl_asgard |
| BEHR_PC2_Dual_S1 | (EMPTY) | 3 | gimbalMount flightReady | (empty) |
| DRAK_Dual_S1 | (EMPTY) | 3 | gimbalMount flightReady | DRAK_Caterpillar_Base |
| Default_Fixed_Mount_S3 | b922abdb | 3 | turretMount flightReady | (empty) |
| MISC_Starlancer_TAC_Missile_Gimbal | (EMPTY) | 4 | gimbalMount flightReady $… | MISC_Starlancer_… |
| ORIG_85X_Turret | 1e47a9ec | 3 | flightReady $ORIG_85x_Turret | ORIG_85x_Turret |

Members are mixed: some have empty mfrGuid, some don't; some have
`gimbalMount`, some have `turretMount`. No shared field beyond
`type=Turret`, `subType=GunTurret`.

Non-members carry the same fields with identical distributions. For
example `AEGS_Idris_Lower_Camera_Mount` has `tags='Idris_Base'`,
`reqT=''`, `mfrGuid=cf4a74bf` — structurally identical to many members.

**Verdict: NO STRUCTURAL SIGNAL.** Members are scattered across
manufacturer, size, tag and requiredTag combinations that all overlap
with non-members.

---

## 6. `_PAINTS_WITHOUT_CLASS` (line 162, 10 members)

**Members.** 1 Cutter paint, 8 Perseus paints, 1 Starlifter paint.

**What the set toggles.** `Paints.UNDEFINED + className in set →
should_have_class=False` (line 655).

**Structural comparison.**
- Total `Paints.UNDEFINED` items: 1 008.
- Member attachDef keys: identical to non-members' (`set()` exclusive
  on either side).
- Member components keys: `{'SGeometryResourceParams', 'SCItemPurchasableParams'}`
  — identical to non-members.

**Side-by-side detail (Cutter family):**

| ClassName | tags | reqT | desc |
|---|---|---|---|
| **Paint_Cutter_Black_Silver_Stripe** *(in set)* | `Paint_Cutter @Paint_Cutter_Black_Silver_Stripe` | `Paint_Cutter` | `@item_DescCutter_Paint_Black_Silver_Stripe` |
| Paint_Cutter_Beige_Orange | `Paint_Cutter @Paint_Cutter_Beige_Orange` | `Paint_Cutter` | `@item_DescCutter_Paint_Beige_Orange` |
| Paint_Cutter_Pearl_Silver | `Paint_Cutter @Paint_Cutter_Pearl_Silver` | `Paint_Cutter` | `@item_DescCutter_Paint_Pearl_Silver` |

Members and non-members are character-for-character indistinguishable
except by className.

**Verdict: NO STRUCTURAL SIGNAL.** This set encodes pure editorial
intent — the 10 specific paint variants ref omits Class for, with no
underlying data difference from siblings that do get Class.

---

## 7. `_MISSILERACK_WITHOUT_CLASS` (line 197, 23 members)

**Members.** All `MRCK_S{01,02,03,04,05,06,09,12}_*` ship-rack items.

**What the set toggles.** `MissileLauncher.MissileRack + className in
set → should_have_class=False` (line 653).

**Structural breakdown of all 130 MissileLauncher.MissileRack:**
- Members with empty mfrGuid: 0/23
- Non-members with empty mfrGuid: 0/107

So mfrGuid emptiness is not a discriminator. (Notable contrast vs
`_CLASS_VALUE_OVERRIDES`'s capital-ship subset.)

- Members with `name=@LOC_PLACEHOLDER`: 2/23
- Non-members with `name=@LOC_PLACEHOLDER`: 0/107

`name=@LOC_PLACEHOLDER` IS a clean discriminator — for those 2 (`MRCK_S01_TMBL_Storm_AA_Custom`, `MRCK_S02_TMBL_Storm_AA_Custom`) — but the remaining 21 members have real names.

- Members with `name=@LOC_EMPTY`: 2/23 (`MRCK_S02_ORIG_100i_Dual_S02`, `MRCK_S02_ORIG_125a_Quad_S02`).

**Side-by-side compare of MRCK_S04 group:**

```
[*] MRCK_S04_RSI_Constellation       name='@item_NameMRCK_S04_RSI_Constellation' reqT='RSI_Constellation_Base'
[*] MRCK_S04_RSI_Scorpius            name='@item_NameMRCK_S04_RSI_Constellation' reqT='RSI_Scorpius'
[ ] MRCK_S03_AEGS_Sabre_Firebird     name='@item_NameMRCK_S03_AEGS_Sabre_Firebird' reqT=''
[ ] MRCK_S03_BEHR_Quad_S01           name='@item_NameMRCK_S03_BEHR_Quad_S01' reqT=''
[ ] MRCK_S02_RSI_Apollo_Triage       name='@item_NameMRCK_S02_RSI_Apollo' reqT='RSI_Apollo_Triage'
```

Members and non-members alike have ship-binding `requiredTags`. There's
no clean structural pattern that captures all 23 without false positives.

**Verdict: NO STRUCTURAL SIGNAL.** Like `_PAINTS_WITHOUT_CLASS` and
`_TURRETS_WITHOUT_CLASS`, this is editorial: ref decided these specific
23 ship-rack items don't get Class, with no data field tracking the
decision.

---

## 8. `_ARMOR_MEDIUM_WITH_CLASS` (line 225, 18 members)

**Members.** 3 AEGS_Sabre variants, 4 ANVL_Pisces/Gladiator items,
8 ANVL_Hornet variants, 3 ORIG (100i/125a/135c).

**What the set toggles.** `full_type=='Armor.Medium' → should_have_class
= className in set` (line 651). Default for Armor.Medium is no Class.

**Structural breakdown of all 192 Armor.Medium:**
- Members with real description: 18/18.
- Non-members with real description: 68/174.

So "real description" is necessary but not sufficient — 68 non-members
also have real descriptions and they don't get Class.

**Direct compare ARMR_AEGS_SabreRaven (member) vs ARMR_AEGS_Sabre (non-member):**
Identical except className:
- Both: `tags='AEGS_Sabre'`, `reqT=''`, `size=1`, `grade=1`, `volume=1`,
  same `manufacturerGuid='cf4a74bf…'`.
- Identical `armor` component params (damageMultipliers, signalMultipliers,
  damageDeflection, penetrationReduction, penetrationAbsorption — every
  field byte-for-byte equal).
- Both referenced as default armor in vehicles
  (`AEGS_Sabre_Raven` references `ARMR_AEGS_SabreRaven`; `AEGS_Sabre`
  references `ARMR_AEGS_Sabre`).

**Discriminator candidates tried.**
- `armor` component byte-equality → identical.
- `tags` / `requiredTags` → identical.
- Vehicle reference count → both members and non-members are referenced.
- `manufacturerGuid` → same for both (cf4a74bf for AEGS).
- `size` / `grade` / `volume` → identical.

**Verdict: NO STRUCTURAL SIGNAL.** The 68-vs-18 split among real-desc
items is editorial. Two armors with identical XML and identical armor
parameters can land on different sides of the allowlist boundary.

---

## 9. `_FPS_CLASS_OMIT` (line 267, 3 members)

**Members.**
- `gmni_optics_tsco_x4_s2` — `WeaponAttachment.IronSight`
- `grin_cutter_01` — `WeaponPersonal.Medium`, tags `stocked grin_cutter_01`
- `Multitool_Attachment` — `WeaponAttachment.Utility`, name `@LOC_PLACEHOLDER`

**What the set toggles.** Returns `(False, None)` from
`_fps_class_value` — omits Class entirely.

**Without the allowlist, the natural rule for these would be:**
- `gmni_optics_tsco_x4_s2`: WeaponAttachment.IronSight → `(True, "")`
- `grin_cutter_01`: WeaponPersonal.Medium with no damage profile → `(True, "")`
- `Multitool_Attachment`: WeaponAttachment.Utility, NOT in the
  Barrel/IronSight/Bottom/Missile bucket → `(True, "")`.

So the allowlist's effect is to *remove* the Class field instead of
emitting it as empty. We need ref data to confirm which is correct.

**Looking for structural signals:**
- `Multitool_Attachment` has `name='@LOC_PLACEHOLDER'` and
  `desc='@LOC_EMPTY'` — it's a template. Other Utility items have real
  names (the 5 `grin_multitool_01_*` variants).
- `gmni_optics_tsco_x4_s2` has the same components as other ironsights
  (54 total), all of which currently get `Class=""`. No distinguishing
  field.
- `grin_cutter_01` has `tags='stocked grin_cutter_01'` — the
  `grin_cutter_01` self-tag is distinctive but appears in only one item.

**Verdict: NO STRUCTURAL SIGNAL.** Three items with ad-hoc reasons.
`Multitool_Attachment`'s placeholder name is the closest thing to a
signal but doesn't generalize.

---

## 10. `_FPS_CLASS_EMPTY` (line 274, 7 members)

**Members.** `none_pistol_ballistic_01`, `none_special_ballistic_01`,
`volt_shotgun_energy_01`, `volt_sniper_energy_01`, `behr_binoculars_01`,
`behr_gren_frag_01`, `crlf_medgun_01`.

**What the set toggles.** Force `(True, "")` return from
`_fps_class_value` (line 487).

**Original audit conclusion (incorrect).** The first audit pass claimed
this was dead code, on the theory that all 7 members had no
`weapon.ammoParamsRecord` → `damage_profile=None` → fall through to the
default `(True, "")` return. The simulation (`temp/audit_low7.py`)
appeared to confirm this.

**Correction (commit 772187e).** Build byte-diff after deleting the
allowlist showed 5 of 7 entries regressed:

```
crlf_medgun_01              Class:  '' → 'Energy (Laser)'
none_pistol_ballistic_01    Class:  '' → 'Ballistic'
none_special_ballistic_01   Class:  '' → 'Ballistic'
volt_shotgun_energy_01      Class:  '' → 'Energy (Electron)'
volt_sniper_energy_01       Class:  '' → 'Energy (Electron)'
```

These 5 items *do* have a resolvable damage profile via
`_get_fps_damage_profile` (the simulation harness mis-resolved it as
`None`, hiding the regression). The structural ammo-damage-profile
classifier fires on them, producing non-empty Class values that diverge
from ref. The other 2 (`behr_binoculars_01`, `behr_gren_frag_01`)
genuinely fall through, but the allowlist is needed to suppress the
classifier on the 5 weapons.

**Verdict: NO STRUCTURAL SIGNAL — editorial empty-Class allowlist.**
The 5 ref-empty entries can't be reduced because the structural
classifier is *correct* about their damage profile and would emit a
sensible label; ref simply chooses to omit it. Pure editorial.

---

## 11. `_FPS_CLASS_BY_CLASSNAME` (line 285, 15 members)

**Members and target Class values:**

```
grin_multitool_01_cutter         → Cutter
grin_multitool_01_healing        → Medical
grin_multitool_01_mining         → Mining
grin_multitool_01_salvage_repair → Salvage and Repair
grin_multitool_01_tractorbeam    → Tractor Beam
grin_multitool_01                → Gadget
grin_tractor_01                  → Gadget
kegr_fire_extinguisher_01        → Gadget
klwe_smg_energy_01               → Laser
ksar_smg_energy_01               → Energy (Laser)   [non-breaking space variant]
ksar_rifle_energy_01             → Energy (Plasma)
ksar_shotgun_energy_01           → Energy (Plasma)
volt_pistol_energy_01            → Energy (Laser)
none_smg_energy_01               → Energy (Laser)
sasu_pistol_toy_01               → Foam Dart
```

**What the set toggles.** Forces a specific Class label, taking
precedence over the structural damage-profile classification.

**Sub-pattern A — Multitool attachments (5 items).** All have
`type='WeaponAttachment.Utility'` and `tags='grin_multitool_01'`. Their
className suffix (`_cutter`, `_healing`, `_mining`, `_salvage_repair`,
`_tractorbeam`) maps directly to the Class label. Inside
`SWeaponModifierComponentParams.modifier.weaponStats`, each one carries
a different `salvageModifier`/etc. block, but the structural shape is
identical across all 5.

This is *partially structural*: the mapping `suffix → label` could be
encoded as a className-suffix lookup. Suffix is purely the className
again, so it's still name-based. But the multitool family (5 items) is
structurally identifiable by `type='WeaponAttachment.Utility' and
tags contains 'grin_multitool_01'`.

Note: `Multitool_Attachment` (the 6th item with that family signature)
is the *template* and lives in `_FPS_CLASS_OMIT`. Distinguishable by
`name=='@LOC_PLACEHOLDER'`.

**Sub-pattern B — Gadgets (3 items).** `grin_multitool_01`,
`grin_tractor_01`, `kegr_fire_extinguisher_01` — all
`type='WeaponPersonal.Gadget'`. Inspection of all WP.Gadget items shows
several others (`behr_binoculars_01`, `Carryable_*`) — and ref labels
those differently (binoculars get Class="" in `_FPS_CLASS_EMPTY`).
No clean structural rule isolates these 3.

**Sub-pattern C — Energy weapons with editorial labels (6 items).**
`klwe_smg`, `ksar_smg/rifle/shotgun`, `volt_pistol`, `none_smg` — all
have no damage profile (verified) and would default to `(True, "")`.
The override forces specific labels like `Laser` (klwe), `Energy
(Plasma)` (ksar rifle), `Energy (Laser)` (ksar smg with NBSP). These
labels deviate from what the structural ammo-damage-profile rule would
emit if the items *had* damage profiles.

**Sub-pattern D — Toy (1 item).** `sasu_pistol_toy_01` → "Foam Dart".
Pure editorial.

**Verdict: PARTIAL.**

**Implementation plan (multitool subset only):**
1. Add a new helper:
   ```python
   _MULTITOOL_SUFFIX_CLASS = {
       "_cutter": "Cutter", "_healing": "Medical",
       "_mining": "Mining", "_salvage_repair": "Salvage and Repair",
       "_tractorbeam": "Tractor Beam",
   }
   if (full_type == "WeaponAttachment.Utility"
       and "grin_multitool_01" in tags
       and attach_def.get("name") != "@LOC_PLACEHOLDER"):
       for sfx, cls in _MULTITOOL_SUFFIX_CLASS.items():
           if class_name.endswith(sfx):
               return (True, cls)
   ```
2. Remove the 5 multitool-suffix entries from `_FPS_CLASS_BY_CLASSNAME`.
3. The remaining 10 entries (gadgets, energy-weapon labels, toy) stay
   as the editorial allowlist.

Coverage: 5/15 entries reduced to a structural rule. The remaining
10 have no shared structural signal that would replace them.

---

## Implemented (commit 772187e)

`_MISSILERACK_WITHOUT_MASS` (2 entries) and `_MASS_FORCE_INCLUDE`
(10 entries) — verified dead code by build byte-diff against snapshot,
both removed. Net: 12 of 132 LOW-tier name entries removed (~9%).
Their dedicated sections were dropped from this doc.

The audit also flagged `_FPS_CLASS_EMPTY` (7 entries) as dead code,
but byte-diff revealed 5 of 7 regress to non-empty Class via the
structural damage-profile classifier — the allowlist *is* live, and
its verdict is corrected to `NO STRUCTURAL SIGNAL` above.

## Summary of partial reductions (open)

- `_TOOLARM_WITH_TURRET`: replaceable with `'SCItemTurretParams' in
  components`, *if* DRAK_Vulture_Salvage_Arm is verified to also expose
  Turret in ref. (3/3 members caught + 2 non-members would gain Turret.)
- `_CLASS_VALUE_OVERRIDES` (sub-pattern A only): 5 capital-ship items
  with empty mfrGuid could be derived via vehicle cross-ref to ship class.
- `_CLASS_OMIT_CLASSNAMES` (PowerPlant subset): 3 of 15 members reducible
  via `PowerPlant.Power + size>=4 + empty mfrGuid + name != @LOC_PLACEHOLDER`,
  but conflicts with `_CLASS_VALUE_OVERRIDES["POWR_ORIG_S04_890J_SCItem"]`.
- `_FPS_CLASS_BY_CLASSNAME` (multitool subset): 5 of 15 members reducible
  via `WeaponAttachment.Utility + tags contains 'grin_multitool_01' +
  className suffix lookup`.

## No-signal sets (editorial)

`_WEAPONDEFENSIVE_CN_WITHOUT_CLASS`, `_TURRETS_WITHOUT_CLASS`,
`_PAINTS_WITHOUT_CLASS`, `_MISSILERACK_WITHOUT_CLASS`,
`_ARMOR_MEDIUM_WITH_CLASS`, `_FPS_CLASS_OMIT`, `_FPS_CLASS_EMPTY` — all
encode editorial decisions whose underlying signal is not in the item
record. For `_ARMOR_MEDIUM_WITH_CLASS` in particular, two armors with
byte-identical XML can land on different sides of the line.

**Process lesson.** The original audit ran member-by-member simulations
in isolated harnesses (`temp/audit_low*.py`) without rebuilding to compare
against the actual extractor output. For `_FPS_CLASS_EMPTY`, the
isolated simulation mis-resolved the damage profile as `None` for items
whose live extraction *does* find a profile, hiding the regression.
Future audits should byte-diff against a real rebuild before claiming
"dead code" — the simulation can lie.
