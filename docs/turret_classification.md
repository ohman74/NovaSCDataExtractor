# Turret Classification (Manned / Remote / Slaved / PDC)

_Investigation date: 2026-05-03. Companion to `xml_architecture.md` (§5 walks the full port-tree hierarchy; §6.2.5 documents the WeaponMount.WeaponControl wrapper) and `heuristics_audit.md` (G4 records the structural-signal coverage audit for remote-turret detection)._

## Summary — what's structural vs what isn't

Behaviour categories the user observes at the gameplay layer:

- **Manned** — a crewmember boards the turret via SeatAccess; the turret is its own enclosed seat (e.g. Vanguard rear turret).
- **Remote** — operator sits at a console seat elsewhere; the turret is a gun pod with no internal seat (e.g. Cutlass Steel tail).
- **Slaved** — pilot fires it as part of a weapon group; rigidly mounted under the pilot's reticle.
- **Slaved+Remote (combined)** — same physical mount that the pilot fires by default but a copilot can take over (Super Hornet center, Prowler spine).
- **PDC** — small auto-tracking gun mount operated by an AI brain (anti-missile defense).

Mapping these to the JSON output slices the extractor emits — `MannedTurrets`, `RemoteTurrets`, `PilotWeapons`, `PDCTurrets`, `UtilityHardpoints` (tractor/salvage/mining) — works **mostly** structurally, but not entirely. Three signals reach a useful coverage; none alone resolves every case.

| Signal (XML field) | What it discriminates well | What it conflicts on |
|---|---|---|
| **Port `types` family** | `TurretBase.MannedTurret` ↔ Manned (100% of MT in REF — 48/48). `Turret.PDCTurret` ↔ PDC. `UtilityTurret.*` / `Turret.Utility` ↔ utility. | Every other category lives under `Turret.X` or bare `Turret` — type alone doesn't split Remote vs Slaved vs PilotFixed. |
| **Port `defaultWeaponGroup`** (set / not) | Pilot-fired (~95% of PW: 189/193). | RT-with-dwg exist (Ballista, Centurion, MISC_Reliant Wing_Tip_S3 — pilot fire-group routing for what gameplay treats as remote). |
| **Port `controllableTags`** | Pilot vs non-pilot operator namespace. | CIG inconsistency: `weaponCopilot` → REF.PilotWeapons; `coPilotSeat` → REF.RemoteTurrets. Same role, different tag spelling. ~76% structural coverage. |
| **Port `portTags="PDC"` + `requiredPortTags="$PDC"`** | PDC, cleanly (and the only signal that does — most PDC ports aren't even in the impl XML, they live in entity `components.ports`). | None — clean signal. |

The 2026-05-02 G4 audit (heuristics_audit.md) tested every remote-turret detection candidate against the corpus and concluded that **no single XML signal cleanly classifies Remote vs Pilot**. The current implementation combines item-className (`_remote+_turret` / `_ai_turret`) with port-name (`remote_turret`) and reaches ~100% — but that is by composition, not by a single structural rule.

This document records what each signal means, what each category structurally looks like, and where the unavoidable gaps sit. It is descriptive of the data, not prescriptive of a refactor.

---

## XML signals available

### Port-level (vehicle-impl XML, parsed into `port_def`)

| Field | Source XML | Meaning |
|---|---|---|
| `types` | `<Types><Type type=".." subtypes=".." /></Types>` | Family + subtype list. `TurretBase.MannedTurret`, `Turret.GunTurret`, `Turret.MissileTurret`, `Turret.PDCTurret` (rare; usually item-only), `Turret.Utility`, `UtilityTurret.MannedTurret`, `UtilityTurret.BallTurret`, `Module`, `Turret.BallTurret/CanardTurret/NoseMounted/TopTurret/BottomTurret/Gun`. |
| `controllableTags` | `<ControllerDef controllableTags="..." />` | Identifies the SEAT/CONTROLLER that operates this port. Authoritative discriminator for "pilot-fired" (`pilotSeat`, `pilotseat_weapons`, `weapon_controller_pilot`, `gunNose`, `weaponPilot`) vs "copilot/console-fired" (`copilotSeat`, `coPilotSeat`, `weapon_controller_copilot`, `Turret`, `UpperTurret`, `LowerTurret`, `TurretSideRight`, `TurretConsole01_turret`, `RT_Nose`, `remote_turret`, `turret_center`). For manned `TurretBase.MannedTurret` ports, the tag names a turret-internal namespace (`Turret`, `UpperTurret`, `TurretBackRight`) — the seat lives inside the turret-base item. |
| `exclusiveControl` | `<UserDef>` / `<UsableDef>` `<PriorityGroups><PriorityGroup itemType="X"><tags tag="Y"><Priority value="exclusive_control"/>` | Pairs `(itemType, tag)` for which this port (when occupied as a SEAT) gets exclusive control. Used to find which seat governs which weapon. |
| `controlledTags` | Same path with numeric `Priority value="N"` | Non-exclusive priority claims. Lower number wins (per existing comment in parser). The Super Hornet's "copilot beats pilot for `remote_turret`" pattern is encoded as pilot=50, copilot=100 with lower-wins. |
| `defaultWeaponGroup` | `<ItemPort defaultWeaponGroup="N">` | Set on pilot-fired weapons; assigns the mount to weapon-group N for the pilot's fire-group system. Presence is the canonical "pilot fires this" marker for slaved/fixed mounts that have no Manned turret seat. |
| `flags` | `<ItemPort flags="...">` | `$uneditable`, `lower`, `center`, `wing`, `nose`, `intake_left`, etc. Layout/UI flags; not used for turret classification. |
| `portTags` / `requiredPortTags` | `<ItemPort portTags="..." requiredTags="...">` | **`portTags="PDC"` + `requiredTags="$PDC"` is the canonical PDC discriminator.** Other portTags (`VanguardNose`, `ANVL_Hornet_Mk2_Center`, `RSI_Polaris`) gate variant-specific weapons. |
| `partName` | Outer `<Part name="...">` | Used for sub-port grouping; same as port `name` in current parser. |
| `subPorts` | Recursive `<Parts><Part class="ItemPort">` inside an ItemPort's `<Parts>` | Nested ports, e.g. ammo storage inside a turret base. |

### Vehicle-level (impl XML, beyond port_def)

A vehicle's seat ports follow the same pattern. The TWO sides are linked via `controllableTags`:

- **Seat port** (`hardpoint_seat_pilot`, `hardpoint_seat_copilot`, `hardpoint_turret_console_01`, etc.): has `<Types><Type type="Seat"/></Types>` and `<ControllerDef controllableTags="X">`. Its `<UserDef>` block lists what the seated operator can control (priorities on `WeaponController`, `MissileController`, `FlightController`, `Turret`, `Display`, etc.).
- **Weapon mount port** (the actual gun mount): has `<ControllerDef controllableTags="Y">`. The seat's `UserDef.PriorityGroup itemType="WeaponController"` claim with tag matching `Y` (or with priority on tags appearing in mount controllers) is what couples them.
- **Intermediate WeaponController port** (`hardpoint_controller_weapon`, `hardpoint_controller_weapon_remote_01`): has type `WeaponController` and a `controllableTags` matching some seat's, plus a `<UsableDef>` granting exclusive_control to specific weapon tags. This is the "weapon controller" item the seat operates, which in turn operates the turrets tagged accordingly.

A typical chain (Reclaimer):

```
hardpoint_turret_console_01 (Seat, controllableTags="TurretConsole01")
  └─ pilot's WeaponController PG: tag="TurretConsole01" priority=100
hardpoint_controller_weapon_remote_01 (WeaponController, controllableTags="TurretConsole01")
  └─ UsableDef Turret tag="TurretConsole01_turret" priority=exclusive_control
hardpoint_remote_turret_top (Turret.GunTurret, controllableTags="TurretConsole01_turret")
```

This is why you sometimes see one seat operating many remote turrets — Reclaimer Console01 → six turrets.

### Loadout chain — how a turret is "installed" at a port

A vehicle's `defaultLoadout` (under `<EntityComponentDefaultLoadoutParams>`) wires ports → items via GUID (`entityClassReference`) or className. The chain for a multi-gun ball turret like the F7C-M Mk2 weapon-center is:

```
hardpoint_weapon_center  (impl-XML port; types=[Turret.BallTurret, Module], dwg=2, ctrl=remote_turret)
  └─ entityClassReference → ANVL_Hornet_F7CM_Mk2_BallTurret  (turret entity item)
       ├─ hardpoint_weapon_left      (item sub-port)
       │    └─ entityClassRef → Mount_Gimbal_S2
       │         └─ hardpoint_class_2
       │              └─ <weapon item>
       ├─ hardpoint_weapon_right     (item sub-port)
       │    └─ … same chain …
       └─ hardpoint_missile_rack     (item sub-port)
            └─ entityClassRef → <missile rack>
                 ├─ missile_01_attach
                 ├─ … (8 attach points)
```

The ship's impl XML defines the *outer port* (`hardpoint_weapon_center`) with its types/ctrl/dwg. The *inner ports* (`hardpoint_weapon_left/right`, `hardpoint_missile_rack`) are defined inside the BallTurret item's own `SItemPortContainerComponentParams`. The loadout XML chains both layers together via GUID references.

This means **the same logical "turret" has TWO classification questions**:

1. **The outer port** — does this slot, on this hull, surface as Manned / Remote / Pilot / PDC in the output? (Decided by the port's types + ctrl + dwg + portTags, with the heuristic edges noted above.)
2. **The inner items** — what gets emitted as `InstalledItems` and counted toward `Hardpoints`? (Decided by walking the loadout tree under that port.)

For F7CM_Mk2, the outer port routes to PilotWeapons (it has `dwg=2`); the inner left/right gun-mount sub-ports become the `InstalledItems` entries; the missile-rack sub-port is excluded from the PilotWeapons hardpoint count (per `EXCL_TYPES` in xml_architecture.md §6.1).

The same loadout chain applies to wrapper items like `WeaponMount.WeaponControl` (Asgard side doors, Cutlass Steel pintle): the outer port installs a wrapper, the wrapper's inner `weapon` port becomes the visible InstalledItem (xml_architecture.md §6.2.5).

### Item-level (parsed_items.json)

| Field | Distinguishes |
|---|---|
| `attachDef.type` | `TurretBase.MannedTurret` (manned), `Turret.GunTurret`/`Turret.MissileTurret`/`Turret.NoseMounted`/`Turret.CanardTurret`/`Turret.BallTurret`/`Turret.TopTurret`/`Turret.BottomTurret` (remote-or-slaved), `Turret.PDCTurret` (PDC), `Turret.Utility` (utility/salvage turret), `UtilityTurret.*` (mining cabs, ROC arm), `AIModule.UNDEFINED` (PDC AI brain), `WeaponController.UNDEFINED` (intermediate controller), `WeaponGun.Gun`/`WeaponGun.Rocket` (raw gun, no aim/turret servo). |
| `attachDef.tags` | Carries `flightReady`, `PDC`, `gimbalMount`, hull-keying tags (`RSI_Polaris`, `MISC_Reliant_Mount`, `ANVL_Hornet_Mk2_Center`). The `PDC` tag pairs with port `requiredTags="$PDC"`. The `gimbalMount` tag is the existing pilot-mount override signal. |
| `components.SCItemSeatParams` | **Present only on items that contain a seat** — i.e. `TurretBase.MannedTurret` items and seat items. Cleanest single-bit "this is manned" check on the item side. |
| `components.SCItemTurretParams` | Present on every turret-bearing item. Properties (`rotationStyle`, `defaultMovementTag`, `recenterIfUnused`, `switchToCachedOperatorModeOnExit`) are common across manned/remote/PDC and don't discriminate. |
| `components.AITargetableComponentParams` | Present on PDC items (the AI lock-on target component). Also on most manned items as a passive-target marker, so weak signal alone. |
| `components.SCItemAIModuleParams` + `AISeatOperatorComponentParams` | Present only on `AIModule_*_PDC` items. These items "sit" in the AIModule companion port; they're the pilot-substitute for PDC. |
| `components.SCItemWeaponControllerParams` | Present on `WeaponController.*` items and on manned-turret items (manned turrets carry their own internal weapon controller). |

---

## Category definitions

### Manned

**Behaviour**: a crewmember boards the turret directly via a SeatAccess hatch; the turret is its own enclosed seat. Operator gets full Turret/WeaponGun/Display/SeatDashboard exclusive control.

**Distinguishing XML signature**:
- Port `types` contains `TurretBase.MannedTurret` (or `UtilityTurret.MannedTurret` for mining cabs).
- Port has its own `<ControllerDef controllableTags="X">` where `X` is a turret-internal tag (`Turret`, `UpperTurret`, `LowerTurret`, `TurretSideLeft`, `TurretBackRight`, `TurretRear`, `TurretTop`, `mining_cab_front`, etc.).
- Port `<UserDef>` `PriorityGroups` claim `itemType="TurretBase"` and `itemType="Turret"` and `itemType="Seat"` and `itemType="SeatDashboard"` all with `Priority value="exclusive_control"` against the same tag — i.e. the port is BOTH a seat host and a turret host.
- Installed item has `attachDef.type = TurretBase.MannedTurret` and `components.SCItemSeatParams` present.

**Worked examples**:
- `AEGS_Vanguard::hardpoint_turret` types=`['TurretBase.MannedTurret']` ctrl=`Turret`
- `AEGS_Hammerhead::turret_top` types=`['TurretBase.MannedTurret']` ctrl=`TurretTop` (and 5 more turret_*)
- `DRAK_Caterpillar::hardpoint_turret_top` ctrl=`UpperTurret`, `hardpoint_turret_bottom` ctrl=`LowerTurret`
- `RSI_Polaris::hardpoint_turret_side_left/right`, `hardpoint_turret_top_left/right`, `hardpoint_turret_lower_front`
- `ANVL_Carrack::hardpoint_turret_left/right`, `hardpoint_turret_back_rear`
- `AEGS_Reclaimer::hardpoint_turret` ctrl=`Turret` (the bridge manned turret; distinct from the 6 remote turrets)
- `ARGO_MOLE::hardpoint_mining_cab_*` (UtilityTurret.MannedTurret variant)

### Remote

**Behaviour**: gunner sits at a console seat elsewhere on the ship; the mount is a slaved gun pod (no internal seat). Multiple remote turrets often share one console.

**Distinguishing XML signature**:
- Port `types` contains `Turret.GunTurret`, `Turret.MissileTurret`, `Turret.TopTurret`, `Turret.BottomTurret`, `Turret.Utility`, or bare `Turret` (NOT `TurretBase.*`).
- Port has `<ControllerDef controllableTags="Y">` where `Y` is NOT a pilot tag and NOT a turret-internal tag — it names a SEAT (or intermediate WeaponController) elsewhere. Example tags: `CopilotSeat`, `coPilotSeat`, `passengerRightSeat`, `TurretConsole01_turret`, `RT_Nose`, `TBeamLeftSeat`, `turretseatleft`, `SupportLeftSeat`, `mining_cab_front`.
- Port has NO `defaultWeaponGroup` (the pilot does not fire it).
- Installed item has `attachDef.type` like `Turret.GunTurret`/`Turret.MissileTurret`/`Turret.Utility` and NO `SCItemSeatParams`.

**Worked examples**:
- `AEGS_Reclaimer::hardpoint_remote_turret_top/front_left/...` types=`['Turret.GunTurret']` ctrl=`TurretConsole01_turret` (six turrets, two consoles)
- `RSI_Polaris::hardpoint_turret_remote_top` types=`['Turret.MissileTurret']` ctrl=`turretseatleft`
- `RSI_Polaris::hardpoint_turret_remote_bottom` types=`['Turret.GunTurret']` ctrl=`turretseatright`
- `CRUS_Starlifter::hardpoint_remote_turret_bottom/rear` types=`['Turret.GunTurret']` ctrl=`CopilotSeat`
- `ANVL_Carrack::hardpoint_turret_remote_turret` types=`['Turret.GunTurret']` ctrl=`passengerRightSeat`
- `ANVL_Valkyrie` rear remote turret (Turret.GunTurret + non-pilot ctrl)
- `MISC_Reliant::Hardpoint_Weapon_Wing_Tip_S3_Right` types=`['Turret.GunTurret']` dwg=`2` ctrl=`copilotSeat` — note: also has `dwg`, but the controller is copilot — this is a HYBRID: pilot weapon-group routing replaced by copilot when present.

### Slaved-only (PilotFixed / PilotWeapons)

**Behaviour**: pilot fires the gun directly via fire group N. Weapon is rigidly mounted (or limited gimbal under pilot's reticle). No separate operator possible.

**Distinguishing XML signature**:
- Port `types` typically `Turret.GunTurret + WeaponGun.Gun` (gimballed pilot guns) or `Turret.CanardTurret`/`Turret.NoseMounted`/`Turret.BallTurret`/`WeaponGun.NoseMounted` (fixed mounts).
- Port has `defaultWeaponGroup="N"` set.
- Port has either NO `<ControllerDef>` at all, OR `controllableTags` is a pilot-side tag (`pilotSeat`, `pilotseat_weapons`, `weaponPilot`, `gunNose`, `weapon_controller_pilot`).
- Installed item is `WeaponGun.Gun` or a `Turret.*` item (gimballed), with NO seat.

**Worked examples**:
- `ANVL_Hornet_F7A::hardpoint_weapon_left_wing/right_wing` dwg=`1`/`1234`, NO ctrl
- `ANVL_Hornet_F7A::hardpoint_weapon_nose` types=`['Turret.CanardTurret']` dwg=`2`, NO ctrl
- `ANVL_Hornet_F7A::hardpoint_weapon_center` (single-seat F7A) types=`['Turret.BallTurret', 'Module', 'QuantumInterdictionGenerator']` dwg=`2`, NO ctrl — the same physical mount that becomes Slaved-when-alone on F7CM_Mk2
- `AEGS_Vanguard::hardpoint_weapon_gun_nose` dwg=`1`; `hardpoint_weapon_gun_nose_fixed_001..004` dwg=`2`
- `MISC_Reliant::Hardpoint_Weapon_Wing_S1_Left/Right` dwg=`1`, NO ctrl
- `CRUS_Starlifter::hardpoint_weapon_top_left/right` dwg=`1` ctrl=`pilotseat_weapons` (explicit pilot tag)
- `rsi_apollo::hardpoint_weapon_left/right` types=`['Turret.GunTurret', 'WeaponGun.Gun']` ctrl=`pilotSeat`, no dwg — pilot's WeaponController claims these via priority 10

### Slaved+Remote (dual-mode) — Super Hornet, Corsair, RAFT, Hull_C, Valkyrie, Prowler, 400i, F7CM_Mk1

**Behaviour**: pilot fires the mount via a weapon group whenever the secondary seat is empty; the named controller takes over fire control when occupied. The same physical port behaves differently by crew occupancy.

This pattern is widespread, not exotic. It's how almost every two-seat Anvil / Drake / RSI / Origin / Argo design encodes its gunner-seat weapons.

**Distinguishing XML signature**:
- Port has BOTH `defaultWeaponGroup="N"` AND `<ControllerDef controllableTags="X">` where `X` is a non-pilot tag (`remote_turret`, `Remote_Turret`, `turret_center`, `coPilotSeat`, `CopilotSeat`, `RT_Left`, `RT_Right`, etc.).
- Pilot's `hardpoint_controller_weapon` UsableDef has a `Turret`/`WeaponGun` `PriorityGroup` claim against the same tag, with some priority value (or `no_control`).
- Secondary seat's `hardpoint_controller_weapon_*` UsableDef has its own claim against the same tag.
- Lower priority number wins when both seats are occupied. `no_control` on the pilot side means "copilot-only when present, port falls dormant when copilot absent".

**REF placement (PW vs RT) hinges on which side wins the priority** when both seats are filled — NOT visible in the port_def alone, requires walking sibling WeaponController PriorityGroups:

| Outcome | Example | REF |
|---|---|---|
| Pilot wins (pilot priority < copilot priority) | F7CM_Mk2 weapon_center: pilot=50, copilot=100 | PW |
| Copilot wins (copilot priority < pilot priority) | DRAK_Corsair chin guns: copilot takes over | PW (because the default-state, pilot-alone, fires) |
| Both can claim equally as remote | ESPR_Prowler spine: either crew remote-claims | RT |
| Pilot has no_control | F7CM_Mk1 gun_center: copilot-only fire mode | RT |

The PW vs RT outcome cannot be derived from port-level data alone. WeaponController PriorityGroups must be inspected — and even then, no single rule captures every case. The 2026-05-03 inspection of pilot/copilot WeaponController priorities on `Remote_Turret`-tagged ports yielded:

| Ship | Pilot's WC default / Remote_Turret tag | Copilot's WC default / Remote_Turret tag | REF |
|---|---|---|---|
| ANVL_Hornet_F7CM_Mk2 weapon_center | (data) 50 | (data) 100 | **PW** |
| DRAK_Corsair chin | default 100 / tag 50 | default no_control / tag 100 | **PW** |
| ORIG_85X turret | implicit exclusive_control | default no_control / tag 11 | **PW** |
| ESPR_Prowler spine | default 100 / tag 50 | default 50 / tag 100 | **RT** |
| DRAK_Cutlass_Red turret | (no pilot claim) | default no_control / tag 20 | **RT** |
| ARGO_RAFT remote_turret | pilot ctrl uses `pilotseat_weapons` only — no `Remote_Turret`/`CopilotSeat` claim | (RAFT has no copilot WC; copilot seat itself owns the port) | **RT** |
| MISC_Hull_C front/rear top | pilot ctrl uses `weaponPilot` only — no `copilotSeat` claim | (Hull_C copilot seat owns port directly) | **RT** |

### Priority resolution rules (empirical, per the dataset)

The "lower-priority-wins" rule that earlier session memory cited turns out to apply only inside numeric vs numeric comparisons. Within Slaved+Remote ports, the actual rules deduced from the dataset are:

1. **`default="no_control"` + tag-specific numeric override = exclusive when seated.** When a controller's PriorityGroup has `defaultPriority="no_control"` and a `<tags tag="X"><Priority value="N"/></tags>` override, that controller becomes the EXCLUSIVE operator of the X tag when its seat is occupied — even if another controller has a numerically lower priority on the same tag. The numeric value (N) is largely cosmetic in this case; the discriminator is the `default=no_control` shape.
   - F7CM_Mk2, Corsair chin, 85X, F7CM_Mk1 all follow this pattern. Gunner/copilot exclusively claims the port when seated; pilot's claim becomes a slaved-fire fallback for the unseated case.
2. **Two numeric defaults = standard priority comparison.** When BOTH sides have numeric `defaultPriority` values (no `no_control`), the lower-numbered claim wins for tags that override the default.
   - Prowler: pilot default=100 / Remote_Turret=50 vs copilot default=50 / Remote_Turret=100. Pilot's 50 < copilot's 100 → pilot wins on the spine specifically. Copilot wins on every other Turret/WeaponGun (50 < 100).
3. **Pilot has no claim at all = pure-Remote.** When the pilot's WeaponController has no PriorityGroup entry for the port's ctrl_tag (or `defaultPriority="no_control"` with no tag override), the pilot literally cannot fire it. Cutlass_Red is the canonical case (pilot WC has no claim on `remote_turret`). RAFT and Hull_C use a slightly different shape — the copilot SEAT itself owns the port via UserDef (no copilot WeaponController exists).

### Empirical PW vs RT outcomes

Combining the priority rules with REF placement:

| Pattern | Example | REF |
|---|---|---|
| Copilot `default=no_control` + tag override; pilot has tag claim | F7CM_Mk2, Corsair chin, 85X | **PW** |
| Pilot has no tag claim; copilot has tag override | Cutlass_Red, F7CM_Mk1 | **RT** |
| Both sides have numeric defaults; pilot wins on this tag but copilot is broader gunner | Prowler spine | **RT** |
| Copilot seat directly owns port (no copilot WC) | RAFT, Hull_C | **RT** |

The pattern that emerges:

- **REF=PW iff the pilot has a slaved-fire-when-alone fallback on this port** AND no other seat is the broad gunner (i.e. copilot's WeaponController has `default=no_control`). Pilot's role is "primary trigger when alone, deferred when crewed."
- **REF=RT iff** any of: pilot has no claim; OR another seat is the broad gunner (numeric default on Turret/WeaponGun); OR the copilot seat directly owns the port via UserDef.

This is best captured as a chain of structural checks on sibling WeaponController/Seat ports, not a single-port-level rule.

Additional REF=RT exceptions independent of priorities:
- Ground vehicles (Ballista, Centurion, Spartan, TMBL_Nova) — separate classification regime.
- CIG data bug: DRAK_Corsair tail (`dwg=1`, pilot can't actually control). REF=RT is gameplay-correct.

### REF UI confirms the dual-control encoding

The reference UI labels every Slaved+Remote turret with BOTH operator seats in a "Seat X / Seat Y" annotation, regardless of which output category (PW or RT) the turret lives in. Confirmed via UI screenshots across:

| Ship | UI label | REF category |
|---|---|---|
| DRAK_Corsair chin guns | "Seat Copilot / Seat Pilot" | PilotWeapons |
| ANVL_Hornet_F7CM_Mk2 ball turret | "Seat Pilot / Seat Copilot" | PilotWeapons |
| ANVL_Paladin S5 sides | "Pilot Seat / Remote Turret Seat" | RemoteTurrets |
| ANVL_Valkyrie wings | "Seat Pilot / Turret Console Left/Right" | RemoteTurrets |
| ARGO_RAFT remote turret | "Seat Pilot / Seat CoPilot" | RemoteTurrets |
| ESPR_Prowler spine | "Seat CoPilot / Seat Pilot" | RemoteTurrets |
| GLSN_Shiv hardpoint_turret | "Seat Pilot / Seat CoPilot" (per `RemoteController.Seats`) | RemoteTurrets |

This gives us a clearer empirical rule for both classification AND seat resolution.

### Empirical PW-vs-RT discriminator (refined)

Across all examined Slaved+Remote ports, the cleanest structural discriminator is the **non-pilot WeaponController's `defaultPriority` on Turret/WeaponGun**:

| Non-pilot WC default | Examples | REF category |
|---|---|---|
| `no_control` (specialist takeover only) | F7CM_Mk2, Corsair chin, 85X | **PW** |
| numeric (broad gunner role) | Prowler spine, Paladin sides, Valkyrie wings | **RT** |
| no copilot WC; copilot seat directly owns port | RAFT, Hull_C | **RT** |
| both pilot AND non-pilot defaults are `no_control` (both specialists) | Shiv | **RT** |
| pilot has no claim at all on the tag | Cutlass_Red, F7CM_Mk1 | **RT** |

Decision tree (refined):

```
1. types contains TurretBase.MannedTurret           → MT
2. portTags contains "PDC"                          → PDC
3. types contains TurretBase.Unmanned               → RT
4. pilot WC has tag claim on port's ctrl_tag:
   4a. non-pilot WC has default="no_control" + tag → PW (specialist takeover)
   4b. otherwise (numeric default, or no copilot WC, or both specialists) → RT
5. pilot WC has no tag claim on port's ctrl_tag    → RT
```

### Seats resolution (refined)

For `RemoteController.Seats`, emit the **union** of:

- **Direct**: seats whose `controllableTags` matches the port's `controllableTags` AND whose UserDef has `WeaponController exclusive_control` on a tag the controller covers.
- **Indirect via WC chain**: for every WeaponController port whose UsableDef has a tag claim (numeric or exclusive_control) on the port's ctrl_tag, walk back to the seat that operates that WC (via `tag_to_seats[wc.controllableTags]`).

Do NOT prefer one over the other; do NOT pick "lowest priority"; emit ALL seats with claims. REF emits the full operator list, not a priority-resolved single winner.

`RemoteController.Slaved` = True iff some WC has a NUMERIC (non-exclusive) priority on the port's ctrl_tag. Multi-controller weapons get Slaved=True automatically.

### Seats resolution rules (verified 2026-05-03 against full corpus)

The complete `RemoteController.Seats` resolution combines four layers:

1. **Direct seat-tag match**: a seat port whose UserDef has `WeaponController exclusive_control` or numeric priority claim on the port's `controllableTags` (e.g. RAFT pilot WC has `exclusiveControl=[(WeaponController, pilotseat_weapons)]` for tag `pilotseat_weapons`).

2. **Numeric seat priorityControllers**: a seat that numerically claims the WC tag (e.g. RAFT pilot has priorityControllers=[(WeaponController, CopilotSeat, 50)] — pilot can co-operate copilot's WC at priority 50). Both exclusive_control AND numeric claims populate `tag_to_seats`.

3. **Indirect via WC chain (exclusive)**: when a WeaponController port has `exclusive_control` on a Turret/WeaponGun/MissileLauncher tag, the seats that operate that WC (via tag_to_seats lookup on the WC's controllableTags) are propagated to the claimed tag (Reclaimer pattern).

4. **Indirect via WC chain (numeric)**: same as #3 but with numeric priorities. Has cross-tag rule:
   - Same-tag claim (claim tag == WC's ctrl_tag) → always propagate
   - Cross-tag with no same-tag claim of the same itemType → propagate (the cross-tag is the only path)
   - Cross-tag with a same-tag claim of the same itemType → propagate ONLY if cross-tag priority is STRICTLY LOWER (better) than same-tag priority

The cross-tag-priority comparison handles the Polaris vs Starlifter discrimination:
- **Polaris bridge MissileController** (ctrl=`turretseatleft`): numeric claim `(MissileLauncher, torpedoSeat, 10)` is cross-tag, same-tag claim is `(MissileLauncher, turretseatleft, 10)`. Equal priority → cross-tag is fallback → don't propagate. Bridge_MissileOnly seat correctly excluded from torpedo Seats.
- **Starlifter pilot WC** (ctrl=`pilotseat_weapons`): cross-tag `(Turret, RT_Nose, 1)` vs same-tag `(Turret, pilotseat_weapons, 50)`. Cross-tag priority 1 < same-tag 50 → cross-tag is the primary purpose → propagate. Pilot correctly included in bridge_remote_turret Seats.

This required parser extension (`vehicle_impl_parser.py`): `controlledTags` entries are now 3-tuples `(itemType, tag, priority)` — the priority value was previously dropped.

### Slaved flag — fully structural (item-level)

`RemoteController.Slaved` is determined by the installed turret item's:

```
components.SCItemTurretParams.remoteTurret.SCItemTurretRemoteParams.turretOnlyUsableInRemoteCamera
```

| Value | Meaning | Slaved |
|---|---|---|
| `"1"` | Operator MUST use remote camera (cannot fire slaved) | False |
| `"0"` | Operator can fire it slaved when alone (pilot-fireable) | True |
| absent (no `SCItemTurretRemoteParams` on the item) | Not a remote-mode-capable item — gimbals, missile racks, fixed mounts | Fall back to tag-in-slaved_tags rule |

**Verified across 14 ships (2026-05-04):** Reclaimer 6 remote turrets, F7CM Mk1 base, Cutlass_Red, RAFT, Hull_C, Valkyrie wings, Prowler spine, 85X, Shiv, 890Jump, Ballista — all match REF.Slaved exactly when the param is read.

Previous sessions assumed Slaved was port-level (port_def signals). The Reclaimer experiment proved otherwise: front_left and top have IDENTICAL port_def yet REF.Slaved differs (front_left=True, top=False). Same item type, same port shape, different `turretOnlyUsableInRemoteCamera` value.

**Implementation in `_enrich_remote_controllers`** (ships.py): looks up the installed item via `port_to_item` map, walks `components.SCItemTurretParams.remoteTurret.SCItemTurretRemoteParams.turretOnlyUsableInRemoteCamera`, and overrides the legacy slaved_tags rule when present.

Remaining 6 mismatches are upstream RC=None cases (Heartseeker, Paladin middle) or edge items lacking the param (Reliant Tana, Perseus turret_bottom, Zeus_CL/ES turret_bottom).

### Pilot-claim detection for Slaved+Remote routing

Implemented in `_build_hardpoints` (precomputes `pilot_claimed_tags` set) and `_classify_port` (consumes the set).

**Pilot's WC claims a tag iff:**

1. Explicit tag override on the port's ctrl_tag in pilot's `exclusiveControl` or `controlledTags`. OR
2. Implicit broad claim: pilot WC port has Turret/WeaponGun PriorityGroup with empty `defaultPriority` and no tag overrides. This signals "pilot fires anything Turret/WeaponGun by default, unless another seat has exclusive_control on the specific tag." Marker: `*` sentinel in `pilot_claimed_tags`.

**Override rules at classification time:**

- When a port has a non-pilot `controllableTags` (would normally route to RemoteTurrets), check if pilot has a claim:
  - If `pilot_claimed_tags` contains the port's ctrl_tag → pilot fires it slaved-when-alone → route to **PilotWeapons**.
  - If `*` is in `pilot_claimed_tags` (broad claim) AND ctrl_tag is NOT in `non_pilot_exclusive_tags` (i.e., no other WC has `exclusive_control` on this tag) → broad claim applies → route to **PilotWeapons**.
- TurretBase.Unmanned port type ALWAYS overrides to RemoteTurrets (Cutlass_Red).

**Confirmed routing fixes (2026-05-03):**

- F7CM_Mk1, F7CM_Mk2, F7CM_Heartseeker → PilotWeapons (was RemoteTurrets)
- ORIG_85X turret → PilotWeapons
- DRAK_Corsair chin guns → PilotWeapons
- CRUS_Spirit nose+wings → PilotWeapons
- RSI_Constellation top/bottom guns → PilotWeapons
- MISC_Reliant Wing_Tip_S3_Right → PilotWeapons
- MISC_Starlancer_TAC missile turrets → still RemoteTurrets (under-correction, see below)
- Cutlass_Red: stays RemoteTurrets (TurretBase.Unmanned override) ✓
- Reclaimer remote turrets: stay RemoteTurrets (TurretConsole01_turret in non_pilot_exclusive_tags) ✓

**Remaining gaps (irreducible without deeper analysis):**

- 11 ports REF places in RT but our broad-claim rule places in PW: Carrack, Redeemer, Starlifter bridge, Prowler spine, Shiv, Perseus, Polaris. These have non-pilot WCs with NUMERIC (not exclusive) claims that REF respects. The rule needs another signal for "non-pilot WC with numeric claim that 'owns' the tag."
- 6 ports REF places in PW but our rule places in RT: TMBL_Nova/Storm primary turret, Carrack remote turret, Starlancer_TAC missile turrets, GRIN_MTC. Pilot WC uses a non-standard ctrl_tag (e.g. Carrack's `Console_Weapons`, TMBL's `weapon_primary`) not in our pilot tag whitelist. Detection needs to follow seat→WC chain via seat's UserDef WeaponController claim.

These are deferred; the existing rule reaches ~76% precision on the previously-mismatched set with no further heuristics.

### Validator findings (2026-05-03 corpus run)

A structural-rule validator running across all 131 spaceship impl XMLs (excluding ground vehicles) classified 105 of 112 turret-with-ctrl_tag ports identically to REF. The 7 remaining mismatches:

| Ship | Port | Rule | REF | Notes |
|---|---|---|---|---|
| ANVL_Paladin | 3 remoteturret_* ports | undetermined | RT | Paladin's seat/WC ports live in `components.ports` (entity-level), not in impl XML `<ControllerDef>`. The component-level ports carry no priority data — the priority chain is on the installed WeaponController items themselves. Walking that requires loadout-resolution. |
| DRAK_Corsair | hardpoint_tail_turret | PW | RT | CIG data bug. `dwg=1` on a port pilot cannot actually control. REF gameplay-correct. |
| GLSN_Shiv | hardpoint_turret | PW | RT | Slaved+Remote like F7CM_Mk2 (pilot fires alone, copilot takes over). Pilot WC `copilotSeat=10`, copilot WC `copilotSeat=50`, both with `default=no_control`. REF chooses RT despite gameplay-equivalence to F7CM_Mk2 (PW). |
| ORIG_85X | hardpoint_turret | RT | PW | Empty pilot WC default counts as a slaved claim here even though it is "no specific tag override". The semantic distinction between Cutlass_Red (empty default = pilot CANNOT fire) and 85X (empty default = pilot CAN fire) appears to live in the structural type (`TurretBase.Unmanned` vs `Turret.GunTurret`) — see edge below. |
| TMBL_Storm | hardpoint_primary_turret | RT | PW | Pilot's WeaponController has the non-standard ctrl=`weapon_primary` tag (not in the hardcoded pilot-tag whitelist). The WC needs to be detected via the seat-operates-WC chain rather than tag string matching. |

Three "rule-vs-REF" disagreements where the user's tier framing (pilot-can-ever-fire → PW) diverges from REF:

- **ESPR_Prowler spine**: Pilot fires slaved when alone; copilot can opt into remote turret. Per tier rule = PW; REF = RT. Likely REF inconsistency.
- **GLSN_Shiv hardpoint_turret**: Same gameplay shape as F7CM_Mk2/Corsair chin/85X (pilot slaved, copilot takeover). Per tier rule = PW; REF = RT. The structural difference between Shiv and F7CM_Mk2 is the port's ctrl_tag namespace: `copilotSeat` (seat-name) for Shiv vs `remote_turret` (turret-name) for F7CM_Mk2. REF appears to discriminate on tag-name semantics.
- **ANVL_Valkyrie wing left/right**: Despite outer appearance, pilot has empty default + no tag override on `RT_Left`/`RT_Right` — pilot literally cannot claim. REF correctly = RT; gameplay-side: pilot can NOT fire these alone. (Earlier guess this was Slaved+Remote was wrong.)
- **ANVL_Paladin left/right (S5)**: Slaved to pilot by default; 2 optional dedicated gunner seats can override. Per tier rule = PW; REF = RT. Paladin's middle (S6) is gunner-only and correctly = RT in both. The Paladin priority data lives on installed WeaponController items rather than in impl-XML ControllerDef, so the structural rule needs loadout-resolution to read it.

#### Where the priority data lives — impl XML vs entity components vs installed items

CIG encodes the seat→controller→turret priority chain in three different places depending on the ship:

1. **impl XML `<ControllerDef>` priorities** (most ships): pilot/copilot WeaponController ports declared in the impl XML, with full `<UsableDef><PriorityGroups>` entries. F7CM_Mk2, Corsair, Prowler, 85X, RAFT, Hull_C, Cutlass_Red, Shiv all use this. The validator can read priorities directly.

2. **Entity-level `components.ports`** (Paladin, possibly other capital/dedicated-gunner ships): seats/WCs are declared at the component level without priority claims. The priorities are carried by the INSTALLED WeaponController items themselves — accessible only by resolving the defaultLoadout entity references.

3. **Capital-ship `SItemPortContainerComponentParams.ports`** (Polaris/Idris/Javelin PDCs): port-level structure, often with `portTags="PDC"` markers. No priority chain because PDC ports are AI-operated.

The structural rule covers (1) cleanly. (2) requires walking the installed item's own SItemPortDef priorities. (3) is handled by the PDC discriminator. Ships using a mix (most capital ships) need the validator to merge data from all three sources.

#### Empty default ambiguity (Cutlass_Red vs 85X)

Two ships have structurally identical pilot-WC shapes (empty `defaultPriority=""` with no tags on Turret/WeaponGun) but REF places them differently:

- DRAK_Cutlass_Red `hardpoint_turret`: types=`['TurretBase.Unmanned']` → REF=RT (pilot cannot fire)
- ORIG_85X `hardpoint_turret`: types=`['Turret.GunTurret']` → REF=PW (pilot can fire)

The discriminator is the port `types`: **`TurretBase.Unmanned`** is a structural marker for "this is an unmanned/AI/remote turret base" — pilot is NOT expected to claim it. **`Turret.GunTurret`** is generic, and an empty pilot WC default falls back to "pilot fires by default."

This adds a third structural rule:

> If port `types` contains `TurretBase.Unmanned` → REF=RT regardless of pilot-WC empty defaults.

#### Tag-name semantic discriminator (the Shiv-vs-F7CM_Mk2 distinction)

Among ports with identical pilot/copilot specialist priority shapes (`pilot tag=N₁, copilot tag=N₂, both default=no_control`), REF appears to distinguish by the port's ctrl_tag NAME:

- ctrl_tag containing `remote_turret`/`Remote_Turret` → REF tends to PW (treated as slaved-with-takeover)
- ctrl_tag matching a seat name (`copilotSeat`, `RT_Left`, `RT_Right`) → REF tends to RT (treated as gunner-station)

This is structurally a name-based discriminator on the port's controllableTags. It is not a clean structural rule — REF appears to encode editorial intent here, distinguishing "weapon-namespace tag" from "seat-namespace tag" by string content.

The user's tier rule (pilot-can-ever-fire → PW) is internally consistent across these cases; REF's rule layers in tag-namespace semantics that produce different outcomes for gameplay-identical ports.

**Worked examples**:
- `ANVL_Hornet_F7CM_Mk2 (anvl_hornet_f7cm_mk2.xml)::hardpoint_weapon_center` types=`['Turret.BallTurret', 'Module']` dwg=`2` ctrl=`remote_turret`. Pilot priority=50, Copilot priority=100 on `remote_turret` for `Turret`+`WeaponGun`. With copilot present, copilot's claim (100) beats pilot's (50); without copilot, pilot's claim is the only one and dwg=2 routes the gun into pilot's group 2.
- `ANVL_Spartan::hardpoint_turret` types=`['Turret.BallTurret', 'WeaponGun.Gun']` dwg=`1` ctrl=`remote_turret` — same shape.
- `ESPR_Prowler::hardpoint_weapon_spine` types=`['Turret.Gun', 'Turret.GunTurret', 'Turret.BallTurret', 'WeaponGun.Gun']` dwg=`1` ctrl=`Remote_Turret` — same shape (capital R).
- `MISC_Reliant::Hardpoint_Weapon_Wing_Tip_S3_Right` dwg=`2` ctrl=`copilotSeat` — same shape, different tag namespace.

**Variant note**: `ANVL_Hornet_F7CM_Mk1` (`Modifications/ANVL_Hornet_F7CM.xml`) has `hardpoint_gun_center` types=`['Turret.BallTurret', 'Container.Cargo']` dwg=`2` ctrl=`turret_center`, BUT the pilot's `weapon_controller_pilot` UsableDef has empty PriorityGroups for Turret/WeaponGun (= `no_control`), and only the copilot's `weapon_controller_copilot` claims `turret_center` with priority 11. So Mk1 is pure-Remote (no slaved-to-pilot fallback), Mk2 is the dual-mode. Both look superficially identical at the port level — the distinction lives in the WeaponController seat priorities.

### PDC (Point-Defense-Cannon, AI-operated)

**Behaviour**: small auto-tracking gun mount operated by an AI brain (not by any player seat). Engages incoming missiles autonomously.

**Distinguishing XML signature**:
- Port has `portTags` containing `PDC` and `requiredPortTags` containing `$PDC` (the cleanest single-attribute discriminator).
- Port `types` is bare `Turret` (subtype-less).
- Sibling ports `*_aimodule_*` (type `AIModule`) and `*_wcontroller_*` (type `WeaponController`), `*_mcontroller_*` (type `MissileController`) cluster around each PDC base port.
- The PDC turret port is typically NOT in the vehicle's impl XML — it lives in the entity's `SItemPortContainerComponentParams` and is parsed into `parsed_vehicles.json` `components.ports`. (Capital ships' impl XMLs declare crewed structure; PDCs are added at component level so they can be procedurally placed and AI-driven.)
- Installed turret item has `attachDef.type = Turret.PDCTurret` and `attachDef.tags` contains `PDC`.
- Installed AIModule item (in the sibling aimodule port) has `attachDef.type = AIModule.UNDEFINED`, has `SCItemAIModuleParams` and `AISeatOperatorComponentParams`.

**Worked examples**:
- `RSI_Polaris::hardpoint_pdc_top_01..03 / hardpoint_pdc_bottom_01..04` portTags=`PDC` requiredTags=`$PDC` types=`['Turret']` (in `components.ports`); paired with `hardpoint_pdc_aimodule_top_*` types=`['AIModule']` (default `AIModule_Unmanned_PU_PDC`) and `Turret_PDC_BEHR_A` at the turret port.
- `AEGS_Idris_P::hardpoint_pdc_01..11` (11 PDCs, with `_wc/_mc/_ac` companion ports — same shape).
- `AEGS_Javelin` (similar 11+ PDCs).

### UtilityTurret / Tractor / Salvage

**Behaviour**: non-weapon turret mount (tractor beam, salvage head, mining laser). Either pilot-controlled, copilot-controlled, or a dedicated console seat.

**Distinguishing XML signature**:
- Port `types` may be `Turret.GunTurret` (tractor), `Turret.Utility` (salvage), `UtilityTurret.MannedTurret` (mining cab), `UtilityTurret.BallTurret` (ROC arm), or `ToolArm`.
- Installed item's `attachDef.type` reveals tractor/salvage/mining nature: `Turret.GunTurret` with className `MISC_Reliant_Remote_Tractor_Turret` / `RSI_Polaris_SCItem_Remote_Turret_Tractor`; or `Turret.Utility` for salvage; or `UtilityTurret.*`.
- Port `controllableTags` names the dedicated station (`tractorStation`, `TBeamLeftSeat`, `TractorBeamLeftSeat`, `mining_cab_front`).

**Worked examples**:
- `DRAK_Caterpillar::hardpoint_tractorbeam_left/right` types=`['Turret.GunTurret']` ctrl=`TractorBeamLeftSeat`/`TractorBeamRightSeat`
- `AEGS_Reclaimer::hardpoint_remote_turret_salvage_left/right` types=`['Turret.Utility']` ctrl=`TBeamLeftSeat`/`TBeamRightSeat`
- `RSI_Polaris::hardpoint_remote_turret_interior_tractor` ctrl=`tractorStation`
- `MISC_Reliant_Remote_Tractor_Turret` (pilot-controlled tractor)
- `ARGO_MOLE::hardpoint_mining_cab_front/right` types=`['UtilityTurret.MannedTurret']` ctrl=`mining_cab_front`
- `GRIN_ROC::hardpoint_mining_arm` types=`['UtilityTurret.BallTurret', 'ToolArm']`

These currently land in `MiningHardpoints` / `SalvageHardpoints` / `UtilityHardpoints` in the existing code; "Tractor" sub-classification still relies on port-name `tractor` substring — see "What can't be derived" below.

### Module bay (cargo / turret swap)

**Behaviour**: variable mount that may receive either a turret or a cargo grid based on equipped module item.

**Distinguishing XML signature**:
- Port `types` contains both `TurretBase.MannedTurret` AND `Container.CargoGrid` (or similar dual typing) AND port name contains `module`.
- Cyclone variants only.

**Worked examples**:
- `TMBL_Cyclone::hardpoint_module_attach` types=`['TurretBase.MannedTurret', 'Container.CargoGrid']` ctrl=`turretSeat`. Cyclone_AA installs an AA turret item; Cyclone_TR installs a tractor item; Cyclone_RC installs a comms module; etc.

---

## Decision matrix

Pseudocode, evaluated top-to-bottom (first match wins). This is the **best-effort structural classifier**; the audited gaps below it record where REF disagrees with structure and additional discriminators (item className, port name) are still needed. See heuristics_audit.md G4 for the corpus-wide coverage breakdown.

All checks operate on the parsed `port_def` plus the resolved `item_record` for the installed item.

```
def classify_turret_port(port_def, item_record, sibling_ports):
    types = set(port_def.get('types', []))
    type_families = {t.split('.')[0] for t in types}
    ctrl = port_def.get('controllableTags', '') or ''
    dwg  = port_def.get('defaultWeaponGroup')
    port_tags = port_def.get('portTags', '') or ''
    item_ad = (item_record or {}).get('attachDef', {})
    item_type = item_ad.get('type', '')
    item_subtype = item_ad.get('subType', '')
    item_full_type = f"{item_type}.{item_subtype}".strip('.')
    item_tags = item_ad.get('tags', '') or ''
    item_comps = (item_record or {}).get('components', {})

    # 1. PDC — cleanest signal: portTags="PDC", or item is Turret.PDCTurret,
    #    or item tags include "PDC", or sibling AIModule port present.
    if 'PDC' in port_tags.split() \
       or item_full_type == 'Turret.PDCTurret' \
       or 'PDC' in item_tags.split() \
       or any(p['name'].startswith(port_def['name'].replace('hardpoint_pdc_', 'hardpoint_pdc_aimodule_'))
              for p in sibling_ports):
        return 'PDC'

    # 2. Manned — TurretBase.MannedTurret port type OR installed item is
    #    TurretBase.MannedTurret (the item carries SCItemSeatParams).
    if 'TurretBase.MannedTurret' in types \
       or item_full_type == 'TurretBase.MannedTurret' \
       or 'SCItemSeatParams' in item_comps:
        # Disambiguate utility-manned (mining cab) from gun-manned: utility
        # items have UtilityTurret.* subtypes. Mining cabs land elsewhere.
        if 'UtilityTurret.MannedTurret' in types \
           or item_full_type.startswith('UtilityTurret.'):
            return 'UtilityTurret'  # Mining cabs etc.
        return 'Manned'

    # 3. Module attach (Cyclone variants) — dual-typed port with module name.
    if 'TurretBase.MannedTurret' in types \
       and ('Container.CargoGrid' in types or 'Cargo' in types) \
       and 'module' in port_def['name'].lower():
        return 'ModuleBay'  # Routes via module item subtype.

    # 4. Tractor / Salvage / Mining — utility turret types.
    if 'Turret.Utility' in types \
       or 'UtilityTurret' in type_families \
       or 'ToolArm' in types \
       or item_full_type == 'Turret.Utility':
        return 'UtilityTurret'

    # 5. Slaved-when-alone (Super Hornet) — pilot+copilot dual mode:
    #    has dwg AND a non-pilot ctrl tag.
    if dwg is not None and ctrl and not is_pilot_tag(ctrl):
        return 'SlavedWhenAlone'

    # 6. Remote — Turret.* port type with non-pilot ctrl, no dwg.
    if any(t.startswith('Turret.') or t == 'Turret' for t in types) \
       and ctrl and not is_pilot_tag(ctrl) \
       and dwg is None:
        return 'Remote'

    # 7. Slaved / PilotFixed — has dwg, OR has explicit pilot ctrl tag,
    #    OR is a Turret.* port with no ctrl tag.
    if dwg is not None \
       or is_pilot_tag(ctrl) \
       or (any(t.startswith('Turret.') or t == 'Turret' for t in types) and not ctrl):
        return 'PilotFixed'

    # 8. WeaponGun.* item with no other signal → fall back to PilotFixed
    #    (single-mount weapon, e.g. ARGO_MOLE wings).
    if item_full_type.startswith('WeaponGun.'):
        return 'PilotFixed'

    return None  # Not a turret port.

def is_pilot_tag(tag: str) -> bool:
    """Pilot-operator tag set. Authoritative — covers all pilot-direct tags
    encountered across the corpus."""
    t = tag.lower()
    return t in {
        'pilotseat', 'pilot_seat', 'weaponpilot', 'pilotseat_weapons',
        'weapon_controller_pilot', 'gunnose',
    }
```

The current code's `PILOT_CTRL_TAGS` set already covers most of these except `weapon_controller_pilot` (Hornet F7CM Mk1's pilot weapon-controller controllableTag — but this tag never appears on a TURRET port directly; it's only on the controller port itself, which the seat operates).

### Annotated edge cases (gameplay × XML × REF)

The 2026-05-03 corpus walk surfaced concrete cases where structural signals don't agree with REF. The gameplay descriptions below were confirmed by the user (a Star Citizen player familiar with these ships); they help interpret what the XML is actually encoding.

#### Slaved+Remote dual mode — much more widespread than just the Super Hornet

The same shape — port has BOTH `defaultWeaponGroup` set AND a non-pilot `controllableTags` — appears across many ships. The gameplay behaviour is "pilot fires it slaved when alone; the named seat takes over when occupied." REF's choice of PW vs RT for these ships hinges on **which side wins the priority claim when both seats are filled**, captured in the sibling WeaponController PriorityGroups (not visible in the port_def alone).

| Ship | Port | dwg | ctrl_tag | REF | Gameplay |
|---|---|---|---|---|---|
| ANVL_Hornet_F7CM_Mk2 | hardpoint_weapon_center | 2 | remote_turret | PW | Pilot fires slaved when alone; gunner takes over and pilot cannot override when copilot is seated. Pilot priority=50 / copilot=100 with copilot `default=no_control` — the copilot's tag override on a no_control default = copilot-exclusive when seated. |
| DRAK_Corsair | hardpoint_chin_weapon_left/right | 1 | remote_turret | PW | Pilot fires by default; copilot takes over the 2 chin guns when seated (pilot loses control of these). REF still PW because pilot is the default operator. |
| ORIG_85X | hardpoint_turret | — | Remote_Turret | PW | Pilot fires slaved when alone; copilot can enter remote and take over. Pilot's WeaponController has implicit `exclusive_control` on Turret/WeaponGun; copilot has `defaultPriority=no_control` with `Remote_Turret=11` override. The numeric tag-specific priority overrides the broad `exclusive_control` when the seat is occupied. **Has NO `dwg`** — proving the Slaved+Remote pattern doesn't always set `dwg` on the port. |
| ARGO_RAFT | hardpoint_remote_turret | — | CopilotSeat | RT | Slaved to pilot; copilot uses it as remote when present. REF treats as RT. |
| MISC_Hull_C | hardpoint_turret_front_top, rear_top | — | copilotSeat | RT | Same — slaved/copilot remote. |
| ORIG_400i | hardpoint_remote_turret_top/bottom | — | CopilotSeatRight/Left | RT | Slaved/copilot remote (one per copilot seat). |
| ANVL_Valkyrie | hardpoint_weapon_wing_left/right | — | RT_Left/RT_Right | RT | Side guns slaved to pilot by default; individually controlled by two separate gunner seats. |
| ESPR_Prowler | hardpoint_weapon_spine | 1 | Remote_Turret | RT | Spine turret housing 2 guns (loadout: turret entity → `hardpoint_weapon_left/right` → class_2 gun each), so 4 guns total on the ship: 2 wing-fixed (pilot-only, ctrl=None) + 2 spine. Pilot fires the spine slaved by default; copilot does NOT automatically take over but can DELIBERATELY enter the remote-turret interaction to claim it. Pilot WC priority=50 / copilot=100 with copilot `default=50` — copilot's numeric default flags them as a broad-gunner role at the WC level even though the spine-specific claim is weaker. |
| DRAK_Corsair | hardpoint_tail_turret | 1 | coPilotSeat | RT | **CIG data bug**: dwg=1 makes it appear as a pilot gun in the MFD, but the pilot cannot actually control it. Copilot-only remote in practice. REF correctly classifies as RT. |

The Slaved+Remote pattern is the rule, not the exception. The structural fact captured at the port level (`dwg` + non-pilot `ctrl`) does NOT alone tell you whether REF will choose PW or RT — that decision lives in the WeaponController PriorityGroups one level deeper. The current code's `pilot fire-group override` (line 1620-ish) treats `dwg` set as PW, which gets the F7CM_Mk2 / Corsair-chin cases right but fails for Prowler-spine / Corsair-tail.

#### Multi-turret per console — Reclaimer pattern

```
hardpoint_turret_console_01 (Seat, ctrl=TurretConsole01)
hardpoint_controller_weapon_remote_01 (WeaponController, ctrl=TurretConsole01)
   └─ UsableDef Turret tag=TurretConsole01_turret priority=exclusive_control
hardpoint_remote_turret_top         (Turret.GunTurret, ctrl=TurretConsole01_turret)  ← console_01 turret 1
hardpoint_remote_turret_front_left  (Turret.GunTurret, ctrl=TurretConsole01_turret)  ← console_01 turret 2
hardpoint_remote_turret_front_right (Turret.GunTurret, ctrl=TurretConsole01_turret)  ← console_01 turret 3
hardpoint_turret_console_02 (Seat, ctrl=TurretConsole02)
hardpoint_controller_weapon_remote_02 (WeaponController, ctrl=TurretConsole02)
hardpoint_remote_turret_bottom      (Turret.GunTurret, ctrl=TurretConsole02_turret)  ← console_02 turret 1
hardpoint_remote_turret_rear_left   (Turret.GunTurret, ctrl=TurretConsole02_turret)  ← console_02 turret 2
hardpoint_remote_turret_rear_right  (Turret.GunTurret, ctrl=TurretConsole02_turret)  ← console_02 turret 3
```

The Reclaimer's 6 remote gun turrets (NOT utility — they're `Turret.GunTurret`) are grouped into 2 banks of 3, each operated from one console seat via a shared WeaponController. The salvage turrets are separate (`TBeamLeftSeat`/`TBeamRightSeat`, type `Turret.Utility`, route to SalvageHardpoints).

The structural rule "if `controllableTags` matches a sibling Seat or WeaponController port" is the cleanest way to identify these as Remote — independent of whether the tag spelling contains "remote".

#### Carrack passengerRightSeat — bridge passenger remote gun

`ANVL_Carrack::hardpoint_turret_remote_turret` is a small `Turret.GunTurret` controlled from the right bridge passenger seat (`hardpoint_seat_bridge_r`, ctrl=`passengerRightSeat`). Wired through `hardpoint_turret_remote_turret_controller` (WeaponController, same ctrl). A defensive remote gun for whoever sits in the right bridge chair.

#### Ground vehicles — distinct classification regime

ANVL_Ballista, ANVL_Centurion, ANVL_Spartan, TMBL_Nova all have ground-vehicle ports with `dwg` set + non-pilot `ctrl` that REF places in RT. These follow ground-vehicle gunnery conventions (driver + gunner seats, different from spaceship pilot/copilot model). For the current investigation, set them aside — their classification needs ground-vehicle-specific rules separate from the spaceship logic above.

#### CIG data bugs

- **DRAK_Corsair tail turret**: `dwg=1` is misleading; pilot cannot actually fire it. REF=RT is correct gameplay; the `dwg` field is a CIG data error visible in the MFD UI.

These cases cannot be structurally distinguished from genuine pilot-fired ports — they're best handled either by accepting REF's classification (if available) or by accumulating a small known-CIG-bug exception list with a code comment naming the issue.

### Audited gaps (G4 corpus)

The 2026-05-02 audit (heuristics_audit.md G4) tested every candidate single-signal classifier against 358 turret ports + 50 RT / 193 PW / 48 MT REF entries. Results:

- `type == TurretBase.MannedTurret` → 100% MT precision/recall (48/48). **Solid.**
- `defaultWeaponGroup` set → 95% PW recall (189/193). Misses 13 PW edge-cases AND classifies 5+ RT ports as PW (Ballista, Centurion). **Useful but not exclusive.**
- `controllableTags substring "remote"` → 38/50 RT, with 96 disagreements. Many remote ports use seat-specific tags (`RearLeftBackSeat`, `gunnerSeat`, `passengerRightSeat`, `TBeamLeftSeat`) instead of "remote". **Insufficient on its own.**
- `controllableTags substring "copilot"` — **conflict**: `weaponCopilot` → REF.PilotWeapons; `coPilotSeat` → REF.RemoteTurrets. Same case-folded substring, different REF treatment. **Don't trust this substring alone.**
- Combined: `_remote+_turret` className OR `_ai_turret` className OR `remote_turret` portname → ~100% RT, no regressions. **What the current implementation uses.**

The `is_pilot_tag()` set in the pseudocode above is a best-effort whitelist; the irreducible inconsistency in CIG's `controllableTags` naming means a perfect single-signal pilot-vs-non-pilot test does not exist. The real classification needs to combine types + dwg + ctrl + item className + port name + (occasionally) the item's seat-presence component, with each signal narrowing the next.

---

## Combined modes — how Super Hornet/Prowler are encoded

The "remote when copilot present, slaved to pilot when copilot absent" pattern is encoded by **dual priority claims on the same tag in two seats' WeaponController PriorityGroups**, plus the turret port carrying both `defaultWeaponGroup` (pilot fire-group routing) and `controllableTags` (operator-tag for the WeaponController-mediated path).

For Hornet F7CM Mk2 (`anvl_hornet_f7cm_mk2.xml`):

| Element | XML | Effect |
|---|---|---|
| `hardpoint_weapon_center` | `dwg=2`, `ctrl=remote_turret` | Pilot fires it as group 2 by default; controllable by anyone with `remote_turret` tag |
| Pilot's `hardpoint_controller_weapon` | UsableDef Turret tag=`remote_turret` priority=`50` | Pilot's WeaponController claims `remote_turret` at priority 50 |
| Copilot's `hardpoint_controller_weapon_copilot` | UsableDef Turret tag=`remote_turret` priority=`100` | Copilot claims at priority 100 |
| Pilot seat | UserDef WeaponController tag=`pilotSeat` priority=`100` | Pilot operates pilot's WeaponController |
| Copilot seat | UserDef WeaponController tag=`copilotSeat` priority=`100` | Copilot operates copilot's WeaponController |

Resolution rule (per parser comments and Reclaimer reference): **lower numeric priority wins**, so pilot's 50 beats copilot's 100 when both are seated. With copilot's seat empty, copilot's claim is voided and pilot retains the only claim. Result: F7CM Mk2 is pilot-fired in all states (Reference classifies it as PilotWeapons). The "slaved-when-alone" framing is more accurate for cases where the copilot's claim is LOWER (e.g. `MISC_Reliant`), where copilot wins when present and pilot fires when copilot is absent.

For the Prowler the structure is identical (dwg=1 on `hardpoint_weapon_spine` plus ctrl=`Remote_Turret`). For the Spartan likewise.

---

## What CAN'T be derived structurally (heuristics still needed)

Items below have no clean XML discriminator and require name-based or className-based heuristics:

1. **Tractor sub-classification of Turret.GunTurret items**. Many tractor turrets are typed `Turret.GunTurret` (Caterpillar tractor beams, Polaris interior tractor, MISC Reliant tractor) — the type alone doesn't say "tractor". Disambiguation requires the installed item's className substring (`tractor_turret`, `tractor_beam`) or port name (`*_tractor_turret`, `_tractorbeam_*`). The component-level signal that COULD work is `attachDef.type=Turret.GunTurret` combined with the absence of damage/ammo and a component named `SCItemTractorBeamParams` (worth verifying).

2. **Bomb turret vs gun turret**. Starlifter A2/M2's `hardpoint_bomb_turret` carries `types=['Turret']` ctrl=`bomb_turret`. The port type "Turret" alone doesn't say bomb. Discriminator: port-name `bomb_turret` substring AND the installed item's className containing `bomb_turret`. Reference omits these regardless, so the existing skip-by-className rule is acceptable.

3. **Camera turret / door turret / blanking caps**. These are `TurretBase.MannedTurret` ports (structurally indistinguishable from manned turrets) that receive decorative items. Discriminator is purely on the installed item's className (`Camera_Turret`, `Door_*_Cover`, `*_turret_cap`). Reference omits these. No structural signal exists for "this turret port is intended as decorative".

4. **PDC ports lacking impl-XML declaration**. Polaris/Idris/Javelin PDCs are not in the impl-XML port tree at all — they live in `components.ports` (entity-level component override). Classification code that only reads the impl XML will MISS these entirely. The fix is to merge `vehicle_data.components.ports` into the port set passed to the classifier. The PDC discriminator (`portTags="PDC"`) then works cleanly.

5. **Slaved vs Slaved-when-alone (Mk1 vs Mk2 distinction)**. The port-level signature is identical for F7CM Mk1 and F7CM Mk2. The distinguisher is **whether the pilot's WeaponController has any priority claim on the port's ctrl tag**:
   - Mk1: pilot's controller has `no_control` for `turret_center` → pure remote (copilot only).
   - Mk2: pilot's controller has priority 50 for `remote_turret` → pilot + copilot dual claim.

   This requires walking sibling WeaponController ports' UsableDef PriorityGroups, which the parser currently captures via `exclusiveControl` and `controlledTags` (and `priorityControllers`) but the classifier doesn't yet consult. This IS structurally derivable; just not from the current port_def alone.

6. **PilotFixed-with-pilot-ctrl-tag vs Pilot-routed-via-WeaponController**. Apollo's `hardpoint_weapon_left/right` use `ctrl=pilotSeat` with NO `dwg`. F7A's wing weapons use `dwg=1` with NO ctrl. Both fire under pilot control; both should land in `PilotWeapons`. The structural rule is "either has a pilot ctrl OR has dwg" → pilot-fired, which the decision matrix above handles.

7. **Hornet "Heartseeker" / `ANVL_Hornet` (vanilla F7C-M) vs `ANVL_Hornet_F7A` / F7A_Mk2**. Vanilla Hornet's `hardpoint_class_4_center` has `dwg=2` + NO ctrl tag → just PilotFixed (no remote-override). F7A_Mk2 same shape. F7CM Mk1 has `ctrl=turret_center` (different tag). F7CM Mk2 has `ctrl=remote_turret`. These are all derivable from the port definitions; no heuristic needed.

8. **Remote-turret name override for `defaultWeaponGroup`-bearing ports**. The current code has an exception: ports named `*remote_turret*` stay Remote even when `dwg` is set (Cutlass Steel tail). This case is rare and may be an artifact of CIG inconsistency. The structural rule "non-pilot ctrl → Remote (with dual-mode if dwg also set)" handles it without name matching, given the port has a non-pilot ctrl tag. If a port has `dwg` AND a non-pilot ctrl AND the user wants "Remote" priority over "Slaved-when-alone", this is policy, not structure.

### Decorative item exclusion (structural)

REF excludes door-cover items and turret caps installed at TurretBase ports. The cleanest structural signal is the installed item's INNER PORT TYPES:

- **Idris turret-tail door covers** (`Door_Ship_Exterior_Idris_Turret_Cover` and similar): the item's inner ports use `ControlPanel.DoorPart`, `Button.DoorPart`, `Misc.DoorPart` subtypes. Any `.DoorPart` subtype anywhere in the item's inner ports = door assembly = decorative.
- **Misc.UNDEFINED / AttachedPart.UNDEFINED turret caps** (Starlifter chin caps, Stinger turret cap): outer item type already routes via the SKIP_PORT_TYPES check.

Implementation in `_classify_port`: walk `item_record.components.ports`, check if any inner port has a type containing `.DoorPart` substring. If yes, return None (skip).

Items without clean structural signal (kept as className substring heuristics):

- **Bomb turrets** (`CRUS_Starlifter_Bomb_Turret`): outer type `Turret.GunTurret`, inner ports `WeaponGun.Gun` + countermeasures + missile rack — same shape as a real combat turret.
- **Camera turrets** (`AEGS_Idris_Remote_Camera_Turret_Lower/Upper`): outer type `Turret.GunTurret`, inner ports `WeaponGun.Gun` — structurally identical to real turrets.
- **Generic `_turret_cap` className** patterns at any port type — irreducible.

### Tractor sub-classification (structural)

Tractor turrets carry outer `Turret.GunTurret` (same as combat turrets) but their INNER PORT TYPE is `TractorBeam` (vs `WeaponGun.Gun` for combat). This is the structural discriminator — replaces the previous port-name `tractor` substring match.

Implementation in `_classify_port`: walk `item_record.components.ports`, check if any inner port has type `TractorBeam` (or `TractorBeam.X`). If yes, route to UtilityHardpoints.

className `tractor_turret` / `tractor_*_turret` and port-name `tractor` retained as fallbacks for items where the parser doesn't expose inner-port types.

### Tag-ownership rules for Slaved+Remote routing (final, 2026-05-04)

When a port has a non-pilot `controllableTags`, the pilot's claim (explicit or implicit-broad) is OVERRIDDEN by any of these structural ownership signals:

1. **Non-pilot WC has `exclusive_control` claim on the tag** (Reclaimer's `controller_weapon_remote_01` exclusive on TurretConsole01_turret).
2. **Non-pilot WC has a numeric SAME-TAG claim** — claim tag matches the WC's own `controllableTags` (Carrack `passengerRightSeat`, Shiv `copilotSeat`, Starlifter A2 `bridge_remote_turret_controller` ctrl=RT_Nose claiming Turret:RT_Nose).
3. **Non-pilot WC has numeric `defaultPriority` on Turret/WeaponGun** (broad gunner role) — globally suppresses pilot's claims (Prowler copilot WC default=50).
4. **Dedicated turret seat** — a non-pilot SEAT port whose `controllableTags` matches the target port's `controllableTags` (Paladin's `hardpoint_seat_remoteturret_left` ctrl=Remote_Turret_Left, Carrack `hardpoint_seat_bridge_r` ctrl=passengerRightSeat).

When NONE of these own the tag and the pilot has a claim (explicit tag override OR implicit-broad), the port routes to PilotWeapons (Slaved+Remote). Otherwise routes to RemoteTurrets.

**Result**: 0 classification mismatches (every PW vs RT routing matches REF).

### Final tag-ownership rule set (2026-05-04)

Pilot's claim is OVERRIDDEN when the tag is "owned" by:

1. **WC `exclusive_control` claim** — any WC port with exclusive_control on a Turret/WeaponGun tag owns that tag, regardless of who operates the WC. (Reclaimer's `controller_weapon_remote_01` exclusive on `TurretConsole01_turret`, even though pilot operates remote_01 via seat→WC chain.)
2. **WC numeric same-tag claim** — a WC port whose ctrl_tag equals the claim tag (Carrack, Shiv, Ballista, Starlifter A2 bridge).
3. **Non-pilot WC numeric `defaultPriority`** on Turret/WeaponGun (broad gunner) — globally suppresses pilot's claims (Prowler).
4. **Dedicated SEAT port** with ctrl matching the target port's ctrl (Paladin S5 sides, Carrack passenger).

### Override paths (pilot CAN claim despite ownership)

Two structural overrides allow pilot to bypass ownership and route to PilotWeapons:

A. **gimbalMount item-tag + no inner Turret.X**: items tagged `gimbalMount` whose installed item has NO inner port with `Turret.X` type are pilot gimbal mounts. Starlancer_TAC missile gimbals fit this — they have only `MissileLauncher.MissileRack` inner. Prowler spine items also carry `gimbalMount` but their inner ports are real combat turrets (`Turret.GunTurret`) → don't bypass.

B. **dwg + pilot-broad + no inner Turret.X**: when the port has `defaultWeaponGroup`, the pilot WC is broadly-implicit, AND the installed item lacks inner `Turret.X` (it's a scanner/sensor/single-gimbal mount, not a real combat turret). Reliant Mako/Sen/Tana wing tips fit this. Real combat turrets (Redeemer/Spirit/Scorpius) have inner `turret_left/right` with `Turret.GunTurret` type → don't bypass.

### Pilot WC detection — derived from seat→WC chain

Pilot WC ctrl_tags are the union of:

- **Literal**: `_PILOT_CTRL_TAGS = {pilotSeat, pilot_seat, weaponPilot, pilotseat_weapons, weapon_controller_pilot, gunNose}`.
- **Derived**: any tag X where a pilot SEAT (ctrl in `_PILOT_CTRL_TAGS`) has a UserDef `WeaponController` or `MissileController` claim (exclusive or numeric) on tag X. TMBL_Nova/Storm driver-seat numerically claims `weapon_primary` → that WC port (ctrl=weapon_primary) becomes a pilot WC.

This works correctly with rule #1 above (always-add exclusive_control to ownership) — Reclaimer's pilot-derived `remote_01` WC still owns `TurretConsole01_turret` via its exclusive_control claim, so the turret routes to RT despite pilot operating the WC.

### Two bypass paths for the dwg + non-real-turret-item override

When a port has `defaultWeaponGroup` set AND the installed item is NOT a "real combat turret" (no inner port with `Turret.X` type), the dwg signal indicates pilot-fire-group routing. Two distinct bypass paths:

- **Path (a) — pilot_broad**: pilot WC has implicit-broad claim (`*` in pilot_claimed_tags). Bypass even when the tag IS owned by a non-pilot WC. Reliant Mako/Sen/Tana wing tips fit this — copilot WC owns `copilotSeat` numerically but pilot's broad claim wins because the port has dwg.

- **Path (b) — no detected pilot WC + tag not owned**: when pilot_claimed_tags is empty (no pilot WC at all) AND the tag is NOT owned. Used for ships with minimal entity data (GRIN_MTC: pilot driver-seat operates WC via numeric defaultPriority that our parser doesn't expose as a tag claim, but the turret port has dwg + no ownership signal → driver fires it via fire-group).

Path (b) is gated on `not pilot_claimed_tags` (entirely empty) to avoid mis-routing ports where pilot HAS some claims but specifically not on this tag. TMBL_Nova `hardpoint_secondary_turret` correctly stays RT: pilot has explicit claim on `primary_remote_turret` (so `pilot_claimed_tags` is non-empty), but doesn't claim `secondary_remote_turret` → path (b) doesn't fire → RT.

In summary:

- **Cleanly structural** (single signal sufficient):
  - Manned: `types` contains `TurretBase.MannedTurret` (48/48 in REF).
  - PDC: `portTags="PDC"` + `requiredPortTags="$PDC"`, OR item's `attachDef.type == "Turret.PDCTurret"`.
  - Slaved flag: `item.SCItemTurretParams.remoteTurret.SCItemTurretRemoteParams.turretOnlyUsableInRemoteCamera` (verified across 14 ships).
  - Door-cover decorative skip: any inner port has `.DoorPart` subtype.
  - Tractor sub-classification: any inner port has `TractorBeam` type.
  - Slaved+Remote routing: 4 tag-ownership rules above (combined with pilot-claim detection).
- **Mostly structural with edges**:
  - PilotFixed/Slaved: `defaultWeaponGroup` set is a strong signal (95% PW) but conflicts with a handful of RT-with-dwg ports (Ballista, Centurion, Reliant Wing_Tip).
- **Composition required** (no single signal — see G4):
  - Remote: `Turret.X` types + non-pilot `controllableTags` + no dwg gets ~76%; full coverage requires also matching item className (`_remote_turret`, `_ai_turret`) and port name. CIG inconsistency in copilot tag spelling (`weaponCopilot` vs `coPilotSeat`) means there is no clean single-string substitute.
- **Heuristic-only** (no structural signal at all):
  - Tractor sub-classification within Turret.GunTurret items (item className needed).
  - Decorative/cap items at TurretBase ports (item className: `door_*`, `*_turret_cap`, `Camera_Turret`, `Bomb_Turret`).
  - Sub-classification of MainThruster/ManneuverThruster into Retro/VTOL/Maneuvering (port name; same parent type).

The "best derivable" classifier is the decision matrix above; the residual heuristics in `nova/builders/ships.py::_categorize_port` reflect these unavoidable gaps. The 2026-05-02 audit removed 35+ once-thought-needed name-fallback branches as confirmed dead code; what remains is the irreducible substrate.
