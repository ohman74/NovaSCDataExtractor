# Section A bugfixes — output diffs for external verification

Rebuild of `output/LIVE` after the section A correctness fixes from
`docs/code_review_2026-07.md`. Baseline = pre-fix output (same Data/, same
patch). Every changed value below comes from data the old code silently
dropped or misrouted — verify a sample against SPViewer (fresh download —
`temp/reference/` is from an older patch and only useful for structure) and
erkul.games.

## What changed and why

**1. GUID-form loadout references now resolve (A1)** — `TotalShieldHP`,
`PilotBurstDPS`, `TurretsBurstDPS` in vehicle_stats. Ships whose loadout
references items via GUID (`entityClassReference`) contributed 0 to these
BaseLoadout sums; ~207 ships gained PilotBurstDPS, ~105 TotalShieldHP, ~74
TurretsBurstDPS. Partial cases existed too (e.g. CNOU_Nomad shield 4320 →
6480: one of the shields was GUID-referenced).
*Verify:* pick any ship that went 0 → value and check total shield HP /
burst DPS on erkul. Note erkul computes DPS per weapon; our BaseLoadout is
the sum over installed pilot weapons (first firing mode, pellets × dmg ×
rpm/60).

**2. Hull thruster/door HP: GUID fix + one classifier (A2+A5)** —
`Hull.ThrustersHealthPoints` / `Hull.DoorsHealthPoints` in
vehicle_hardpoints (mirrored in vehicle_stats). Two effects:
(a) GUID-referenced thrusters/doors now counted — 74 ships gained thruster
blocks (253 vs 179), 44 gained door blocks (100 vs 56);
(b) role assignment now uses the same name-first classifier as
FlightCharacteristics/FuelManagement (`thrusterType` is unreliable per the
2026-05-05 audit) — ~138 ports moved bucket, mainly Main→VTOL (58, the
Hull_A pattern: VTOL thrusters whose thrusterType says "main") and
Maneuvering→Retro (32, the Retaliator pattern).
*Verify:* thruster HP per port is hard to see externally; check a couple of
role assignments in-game or against a fresh SPViewer dump instead.

**3. Shared thruster classifier learned `_main` port names** — Redeemer's
`thruster_wing_*_main_*` (thrusterType "main", port name says main) were in
Maneuvering; now Main. This also corrected
`FlightCharacteristics.ThrustCapacity` (Redeemer Main 14,993,558 →
30,986,686; Maneuvering 61,373,632 → 45,380,504) and FuelManagement burn
splits for affected ships.
*Verify:* Redeemer main-thrust acceleration on erkul.
*Open question for verification:* `thruster_aux_left/right` (Reclaimer,
Cutter, Hull_A, Pulse) carry thrusterType "main" but stay in Maneuvering
(name-first policy). If erkul/SPViewer counts aux thrusters as Main we
should add an "aux" rule.

**4. Grenade Explosive block was double-dead, now emitted (A6)** —
`fps_equipment.json`. The old code expected a dict where the parser emits a
list and read `ExplosionParams` where the data says `explosionParams` — so
NO item ever got an Explosive block. Now:
- `behr_gren_frag_01`: DetonationDelay 5.0, RadiusMin 4.0, RadiusMax 5.5,
  Pressure 280, Damage Physical 20 — byte-identical to the SPViewer
  reference entry we have on disk.
- `ksar_gren_frag_01`: DetonationDelay 0.0 (impact-triggered), RadiusMin
  4.0, RadiusMax 5.5, Pressure 5, Damage Thermal 2.
*Verify:* both grenades in a fresh SPViewer dump.

**5. Pilot ctrl-tag sets unified (A4)** — `mainweaponscontrol` added to the
shared `_PILOT_CTRL_TAGS`. No output changes on the current corpus (Idris
railgun was already routed to PilotWeapons); the fix removes a silent
divergence between the classifier and the claims precompute.

**6. Non-output fixes** (no diff entries, listed for completeness):
- dataforge_parser: `in_record` reset for SReputationStandingParams /
  MissionType (iterparse memory-bloat bug);
- dataforge_parser: port defaultLoadout no longer misattributes a nested
  sub-port's loadout entry to its parent (no observable change on the
  current corpus);
- dataforge_parser: parsed_*.json cache now invalidated when Game2.xml is
  newer (stale-cache guard);
- vehicle_impl_parser: swallowed exceptions are now logged;
- cosmetic_classifier: loadout ports keyed hierarchically so same-named
  ports under different turrets can't mask functional swaps (no grouping
  changes on the current corpus — vehicle_metadata is unchanged).

## Sanity checks already done locally

- Zero regressions against the (old) SPViewer reference: nothing that
  matched before stopped matching.
- PilotBurstDPS/TurretsBurstDPS agree with the old reference within ±1
  (integer rounding) for 183/196 resp. 180/196 ships — the remainder is
  expected patch drift.
- All shield values are exactly 0.8 × the old reference — item-level
  `Shield.Health` shows the same uniform 0.8, so this is a global CIG
  shield rebalance since that dump, not an extraction error.

Raw per-ship diffs follow. `<absent>` means the field did not exist on that
side. Machine-readable version: `section_a_diffs.json` (same content).

---


## fps_equipment.json — 2 changed value(s)

### [behr_gren_frag_01]
- `[behr_gren_frag_01].stdItem.Explosive`: <absent> -> {"DetonationDelay": 5.0, "RadiusMin": 4.0, "RadiusMax": 5.5, "Pressure": 280.0, "Damage": {"Physical": 20.0}}

### [ksar_gren_frag_01]
- `[ksar_gren_frag_01].stdItem.Explosive`: <absent> -> {"DetonationDelay": 0.0, "RadiusMin": 4.0, "RadiusMax": 5.5, "Pressure": 5.0, "Damage": {"Thermal": 2.0}}

## metadata.json — 1 changed value(s)

### extractionTimestamp
- `extractionTimestamp`: 2026-07-02T10:55:47 -> 2026-07-02T16:27:04

## vehicle_hardpoints.json — 507 changed value(s)

### [AEGS_Hammerhead_GS]
- `[AEGS_Hammerhead_GS].Hull.DoorsHealthPoints`: <absent> -> {"door_cargo_02": 56000.0, "door_left_02": 24000.0, "door_right_02": 24000.0, "door_nose_airlock": 24000.0}
- `[AEGS_Hammerhead_GS].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 25000.0, "thruster_main_bottom_left": 25000.0, "thruster_main_top_right": 25000.0, "thruster_main_bottom_right": 25000.0}, "Retro": {"thruster_retro_left": 23400.0, "thruster_retro_rig…

### [AEGS_Idris_M]
- `[AEGS_Idris_M].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 24000.0, "door_rear": 2520000.0, "door_argo": 100000.0, "door_front_left": 100000.0, "door_front_right": 100000.0, "door_airlock_front_left": 24000.0, "door_airlock_front_right": 24000.0}
- `[AEGS_Idris_M].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left_1": 100000.0, "engine_right_1": 100000.0, "engine_left_2": 500000.0, "engine_right_2": 500000.0, "engine_left_3": 500000.0, "engine_right_3": 500000.0}, "Retro": {"thruster_retro_left": 80000.0, "t…

### [AEGS_Idris_P]
- `[AEGS_Idris_P].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 24000.0, "door_rear": 2520000.0, "door_argo": 100000.0, "door_front_left": 100000.0, "door_front_right": 100000.0, "door_airlock_front_left": 24000.0, "door_airlock_front_right": 24000.0}
- `[AEGS_Idris_P].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left_1": 100000.0, "engine_right_1": 100000.0, "engine_left_2": 500000.0, "engine_right_2": 500000.0, "engine_left_3": 500000.0, "engine_right_3": 500000.0}, "Retro": {"thruster_retro_left": 80000.0, "t…

### [AEGS_Idris_P_Collector_Military]
- `[AEGS_Idris_P_Collector_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 24000.0, "door_rear": 2520000.0, "door_argo": 100000.0, "door_front_left": 100000.0, "door_front_right": 100000.0, "door_airlock_front_left": 24000.0, "door_airlock_front_right": 24000.0}
- `[AEGS_Idris_P_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left_1": 100000.0, "engine_right_1": 100000.0, "engine_left_2": 500000.0, "engine_right_2": 500000.0, "engine_left_3": 500000.0, "engine_right_3": 500000.0}, "Retro": {"thruster_retro_left": 80000.0, "t…

### [AEGS_Reclaimer]
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 28500.0
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 28500.0
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 28500.0 -> <absent>
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 28500.0 -> <absent>

### [AEGS_Reclaimer_Showdown]
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 28500.0 -> <absent>
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 28500.0 -> <absent>

### [AEGS_Reclaimer_Teach]
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 28500.0 -> <absent>
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 28500.0 -> <absent>

### [AEGS_Redeemer]
- `[AEGS_Redeemer].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_wing_bottom`: 28950.0 -> <absent>
- `[AEGS_Redeemer].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_mav_wing_bottom": 28950.0}

### [AEGS_Tiburon]
- `[AEGS_Tiburon].Hull.DoorsHealthPoints`: <absent> -> {"door_cargo_02": 56000.0, "door_left_02": 24000.0, "door_right_02": 24000.0}
- `[AEGS_Tiburon].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 25000.0, "thruster_main_bottom_left": 25000.0, "thruster_main_top_right": 25000.0, "thruster_main_bottom_right": 25000.0}, "Retro": {"thruster_retro_left": 23400.0, "thruster_retro_rig…

### [ANVL_Asgard]
- `[ANVL_Asgard].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 6000.0, "door_left": 6000.0, "door_rear": 14000.0}
- `[ANVL_Asgard].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_left": 17600.0, "thruster_main_rear_right": 17600.0, "thruster_main_front_left": 17600.0, "thruster_main_front_right": 17600.0, "thruster_aux_left": 17600.0, "thruster_aux_right": 17600.0}, …

### [ANVL_Asgard_Collector_Military]
- `[ANVL_Asgard_Collector_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 6000.0, "door_left": 6000.0, "door_rear": 14000.0}
- `[ANVL_Asgard_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_left": 17600.0, "thruster_main_rear_right": 17600.0, "thruster_main_front_left": 17600.0, "thruster_main_front_right": 17600.0, "thruster_aux_left": 17600.0, "thruster_aux_right": 17600.0}, …

### [ANVL_Carrack]
- `[ANVL_Carrack].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left_large": 30000.0, "thruster_main_right_large": 30000.0, "thruster_main_left_small": 27500.0, "thruster_main_right_small": 27500.0}, "Retro": {"thruster_retro_forward": 28950.0, "thruster_retr…

### [ANVL_Carrack_Expedition]
- `[ANVL_Carrack_Expedition].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left_large": 30000.0, "thruster_main_right_large": 30000.0, "thruster_main_left_small": 27500.0, "thruster_main_right_small": 27500.0}, "Retro": {"thruster_retro_forward": 28950.0, "thruster_retr…

### [ANVL_Gladiator]
- `[ANVL_Gladiator].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 7256.0 -> <absent>
- `[ANVL_Gladiator].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 7256.0 -> <absent>
- `[ANVL_Gladiator].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_left": 7256.0, "thruster_top_front_right": 7256.0}

### [ANVL_Hornet_F7A_Mk1]
- `[ANVL_Hornet_F7A_Mk1].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7A_Mk1].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7A_Mk1].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7CM]
- `[ANVL_Hornet_F7CM].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7CM_Heartseeker]
- `[ANVL_Hornet_F7CM_Heartseeker].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM_Heartseeker].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM_Heartseeker].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7CM_Mk2]
- `[ANVL_Hornet_F7CM_Mk2].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_S5": 7000.0}, "Retro": {"retro_thruster_left": 8250.0, "retro_thruster_right": 8250.0}, "Maneuvering": {"thruster_bottom_back_left": 5000.0, "thruster_bottom_back_right": 5000.0, "thruster_bottom_front_…

### [ANVL_Hornet_F7CM_Mk2_Heartseeker]
- `[ANVL_Hornet_F7CM_Mk2_Heartseeker].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_S5": 7000.0}, "Retro": {"retro_thruster_left": 8250.0, "retro_thruster_right": 8250.0}, "Maneuvering": {"thruster_bottom_back_left": 5000.0, "thruster_bottom_back_right": 5000.0, "thruster_bottom_front_…

### [ANVL_Hornet_F7CR]
- `[ANVL_Hornet_F7CR].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CR].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CR].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7CS]
- `[ANVL_Hornet_F7CS].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CS].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CS].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7C]
- `[ANVL_Hornet_F7C].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7C_Wildfire]
- `[ANVL_Hornet_F7C_Wildfire].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C_Wildfire].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C_Wildfire].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}

### [ANVL_Hornet_F7_Mk2_Collector_Mod]
- `[ANVL_Hornet_F7_Mk2_Collector_Mod].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_S5": 7000.0}, "Retro": {"retro_thruster_left": 8250.0, "retro_thruster_right": 8250.0}, "Maneuvering": {"thruster_bottom_back_left": 5000.0, "thruster_bottom_back_right": 5000.0, "thruster_bottom_front_…

### [ANVL_Paladin]
- `[ANVL_Paladin].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 10000.0, "thruster_main_right": 10000.0}, "Retro": {"thruster_retro_left": 5000.0, "thruster_retro_right": 5000.0}, "Maneuvering": {"anim_thruster_flap_01": 100.0, "anim_thruster_flap_02":…

### [ANVL_Terrapin]
- `[ANVL_Terrapin].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_front_left": 6000.0, "thruster_main_front_right": 6000.0, "thruster_main_rear_left": 6000.0, "thruster_main_rear_right": 6000.0}, "Retro": {"thruster_retro_left": 5240.0, "thruster_retro_right": …

### [ANVL_Terrapin_Medic]
- `[ANVL_Terrapin_Medic].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_front_left": 6000.0, "thruster_main_front_right": 6000.0, "thruster_main_rear_left": 6000.0, "thruster_main_rear_right": 6000.0}, "Retro": {"thruster_retro_left": 5240.0, "thruster_retro_right": …

### [ANVL_Terrapin_Medic_Collector_Medic]
- `[ANVL_Terrapin_Medic_Collector_Medic].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_front_left": 6000.0, "thruster_main_front_right": 6000.0, "thruster_main_rear_left": 6000.0, "thruster_main_rear_right": 6000.0}, "Retro": {"thruster_retro_left": 5240.0, "thruster_retro_right": …

### [ARGO_MOLE]
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_front_vtol_left": 14500.0, "thruster_front_vtol_right": 14500.0, "thruster_rear_vtol_left": 14500.0, "thruster_rear_vtol_right": 14500.0}
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_left`: 14500.0 -> <absent>
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_left`: 14500.0 -> <absent>

### [ARGO_MOLE_Teach]
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_front_vtol_left": 14500.0, "thruster_front_vtol_right": 14500.0, "thruster_rear_vtol_left": 14500.0, "thruster_rear_vtol_right": 14500.0}
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_left`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_left`: 14500.0 -> <absent>

### [ARGO_MOTH]
- `[ARGO_MOTH].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left_top": 14500.0, "thruster_main_left_bottom": 14500.0, "thruster_main_right_top": 14500.0, "thruster_main_right_bottom": 14500.0}, "Retro": {"thruster_retro_left": 13500.0, "thruster_retro_rig…

### [ARGO_MPUV]
- `[ARGO_MPUV].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 400.0, "door_right": 400.0, "door_rear": 400.0}

### [ARGO_MPUV_Transport]
- `[ARGO_MPUV_Transport].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}

### [ARGO_RAFT]
- `[ARGO_RAFT].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_right_2": 4500.0, "thruster_main_right_1": 4500.0, "thruster_main_left_2": 4500.0, "thruster_main_left_1": 4500.0}, "Retro": {"thruster_retro_right": 4500.0, "thruster_retro_left": 4500.0}, "Mane…

### [ARGO_RAFT_Collector_Indust]
- `[ARGO_RAFT_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_right_2": 4500.0, "thruster_main_right_1": 4500.0, "thruster_main_left_2": 4500.0, "thruster_main_left_1": 4500.0}, "Retro": {"thruster_retro_right": 4500.0, "thruster_retro_left": 4500.0}, "Mane…

### [ARGO_SRV]
- `[ARGO_SRV].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_FLT": 21000.0, "thruster_VTOL_FRT": 21000.0, "thruster_VTOL_ML": 21000.0, "thruster_VTOL_MR": 21000.0, "thruster_VTOL_RL": 21000.0, "thruster_VTOL_RR": 21000.0, "thruster_VTOL_FLB": 21000.0, "thruster_VTO…
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FRB`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FLT`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FRT`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_ML`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FLB`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_RL`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_MR`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_RR`: 21000.0 -> <absent>

### [CNOU_Nomad]
- `[CNOU_Nomad].Hull.DoorsHealthPoints`: <absent> -> {"door_entrance": 1000.0}

### [CNOU_Nomad_Teach]
- `[CNOU_Nomad_Teach].Hull.DoorsHealthPoints`: <absent> -> {"door_entrance": 1000.0}

### [CRUS_Intrepid]
- `[CRUS_Intrepid].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 1200.0, "thruster_main_aux_01_left": 1200.0, "thruster_main_aux_02_left": 1200.0, "thruster_main_aux_03_left": 1200.0, "thruster_main_right": 1200.0, "thruster_main_aux_01_right": 1200.0, …

### [CRUS_Intrepid_Collector_Indust]
- `[CRUS_Intrepid_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 1200.0, "thruster_main_aux_01_left": 1200.0, "thruster_main_aux_02_left": 1200.0, "thruster_main_aux_03_left": 1200.0, "thruster_main_right": 1200.0, "thruster_main_aux_01_right": 1200.0, …

### [CRUS_Spirit_A1]
- `[CRUS_Spirit_A1].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01_left": 16500.0, "thruster_main_02_left": 16500.0, "thruster_main_03_left": 16500.0, "thruster_main_04_left": 16500.0, "thruster_main_01_right": 16500.0, "thruster_main_02_right": 16500.0, "thr…

### [CRUS_Spirit_C1]
- `[CRUS_Spirit_C1].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01_left": 16500.0, "thruster_main_02_left": 16500.0, "thruster_main_03_left": 16500.0, "thruster_main_04_left": 16500.0, "thruster_main_01_right": 16500.0, "thruster_main_02_right": 16500.0, "thr…

### [CRUS_Spirit_C1_Civilian]
- `[CRUS_Spirit_C1_Civilian].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01_left": 16500.0, "thruster_main_02_left": 16500.0, "thruster_main_03_left": 16500.0, "thruster_main_04_left": 16500.0, "thruster_main_01_right": 16500.0, "thruster_main_02_right": 16500.0, "thr…

### [CRUS_Star_Runner]
- `[CRUS_Star_Runner].Hull.DoorsHealthPoints`: <absent> -> {"door_rear_ramp": 9800.0}
- `[CRUS_Star_Runner].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 18500.0, "thruster_main_right": 18500.0, "thruster_main_extra_left": 18500.0, "thruster_main_extra_right": 18500.0}, "Retro": {"thruster_retro_left": 18500.0, "thruster_retro_right": 18500…

### [CRUS_Starlifter_A2]
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>

### [CRUS_Starlifter_A2_Collector_Military]
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>

### [CRUS_Starlifter_C2]
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>

### [CRUS_Starlifter_M2]
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>

### [DRAK_Buccaneer]
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Rear_Bot_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Top_Front_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Top_Front_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Front_X-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Top_Rear_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Front_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Rear_Bot_X-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Rear_Top_X-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Rear_Top_X+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Rear_Bot_X+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Bot_Front_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Front_X+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Bot_Rear_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Top_Rear_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Rear_Bot_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Top_Front_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Top_Front_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Bot_Front_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Front_X+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Front_X-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Top_Rear_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Bot_Rear_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Front_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Rear_Bot_X-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Rear_Top_X-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Rear_Top_X+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Top_Rear_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Rear_Bot_X+`: <absent> -> 9150.0

### [DRAK_Clipper]
- `[DRAK_Clipper].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top": 9100.0, "thruster_main_bottom": 9100.0, "thruster_main_aux_right": 9100.0, "thruster_main_aux_left_top": 9100.0, "thruster_main_aux_left_bottom": 9100.0}, "Retro": {"thruster_retro_right": …

### [DRAK_Corsair]
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"retro_thruster_a_left": 30000.0, "retro_thruster_b_left": 30000.0, "retro_thruster_c_left": 30000.0, "retro_thruster_a_right": 30000.0, "retro_thruster_b_right": 30000.0, "retro_thruster_c_right": 30000.0}
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Main`: <absent> -> {"main_thruster_a_left": 24000.0, "main_thruster_b_left": 24000.0, "main_thruster_c_left": 24000.0, "main_thruster_a_right": 24000.0, "main_thruster_b_right": 24000.0, "main_thruster_c_right": 24000.0}

### [DRAK_Corsair_Exec_Military]
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"retro_thruster_a_left": 30000.0, "retro_thruster_b_left": 30000.0, "retro_thruster_c_left": 30000.0, "retro_thruster_a_right": 30000.0, "retro_thruster_b_right": 30000.0, "retro_thruster_c_right": 30000.0}
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Main`: <absent> -> {"main_thruster_a_left": 24000.0, "main_thruster_b_left": 24000.0, "main_thruster_c_left": 24000.0, "main_thruster_a_right": 24000.0, "main_thruster_b_right": 24000.0, "main_thruster_c_right": 24000.0}

### [DRAK_Corsair_Exec_StealthIndustrial]
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"retro_thruster_a_left": 30000.0, "retro_thruster_b_left": 30000.0, "retro_thruster_c_left": 30000.0, "retro_thruster_a_right": 30000.0, "retro_thruster_b_right": 30000.0, "retro_thruster_c_right": 30000.0}
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Main`: <absent> -> {"main_thruster_a_left": 24000.0, "main_thruster_b_left": 24000.0, "main_thruster_c_left": 24000.0, "main_thruster_a_right": 24000.0, "main_thruster_b_right": 24000.0, "main_thruster_c_right": 24000.0}

### [DRAK_Cutlass_Black]
- `[DRAK_Cutlass_Black].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…

### [DRAK_Cutlass_Black_Exec_Military]
- `[DRAK_Cutlass_Black_Exec_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black_Exec_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…

### [DRAK_Cutlass_Black_Exec_Stealth]
- `[DRAK_Cutlass_Black_Exec_Stealth].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black_Exec_Stealth].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…

### [DRAK_Cutlass_Black_ShipShowdown]
- `[DRAK_Cutlass_Black_ShipShowdown].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black_ShipShowdown].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…

### [DRAK_Cutlass_Blue]
- `[DRAK_Cutlass_Blue].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 4600.0}
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Tail`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Main`: <absent> -> {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}

### [DRAK_Cutlass_Red]
- `[DRAK_Cutlass_Red].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 4600.0}
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Tail`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Main`: <absent> -> {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}

### [DRAK_Cutlass_Steel]
- `[DRAK_Cutlass_Steel].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 2000.0, "door_right": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Steel].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…

### [DRAK_Cutter]
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 9000.0
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 9000.0
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0}
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.Main`: {"thruster_aux_left": 9000.0, "thruster_aux_right": 9000.0, "thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0} -> <absent>

### [DRAK_Cutter_Rambler]
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 9000.0
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 9000.0
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0}
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.Main`: {"thruster_aux_left": 9000.0, "thruster_aux_right": 9000.0, "thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0} -> <absent>

### [DRAK_Cutter_Scout]
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 9000.0
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 9000.0
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0}
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.Main`: {"thruster_aux_left": 9000.0, "thruster_aux_right": 9000.0, "thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0} -> <absent>

### [DRAK_Golem]
- `[DRAK_Golem].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…

### [DRAK_Golem_Collector_Indust]
- `[DRAK_Golem_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…

### [DRAK_Golem_OX]
- `[DRAK_Golem_OX].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…

### [DRAK_Golem_Teach]
- `[DRAK_Golem_Teach].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…

### [DRAK_Herald]
- `[DRAK_Herald].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top": 18500.0, "thruster_main_bottom": 18500.0}, "Retro": {"thruster_front_right_front": 17500.0, "thruster_front_left_front": 17500.0}, "Maneuvering": {"thruster_front_left_top": 16500.0, "thrus…

### [DRAK_Ironclad]
- `[DRAK_Ironclad].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 43000.0, "thruster_main_top_middle": 43000.0, "thruster_main_top_right": 43000.0, "thruster_main_bottom_left": 43000.0, "thruster_main_bottom_middle": 43000.0, "thruster_main_bottom_ri…

### [DRAK_Ironclad_Assault]
- `[DRAK_Ironclad_Assault].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 43000.0, "thruster_main_top_middle": 43000.0, "thruster_main_top_right": 43000.0, "thruster_main_bottom_left": 43000.0, "thruster_main_bottom_middle": 43000.0, "thruster_main_bottom_ri…

### [DRAK_Pitbull]
- `[DRAK_Pitbull].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main": 700.0}, "Retro": {"thruster_retro_left": 300.0, "thruster_retro_right": 300.0}, "Maneuvering": {"thruster_mav_FTL": 300.0, "thruster_mav_RTL": 300.0, "thruster_mav_RSL": 300.0, "thruster_mav_FB…

### [ESPR_Talon]
- `[ESPR_Talon].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_left`: 4000.0 -> <absent>
- `[ESPR_Talon].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_right`: 4000.0 -> <absent>
- `[ESPR_Talon].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_bottom_right": 4000.0, "thruster_bottom_left": 4000.0}

### [ESPR_Talon_Shrike]
- `[ESPR_Talon_Shrike].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_left`: 4000.0 -> <absent>
- `[ESPR_Talon_Shrike].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_right`: 4000.0 -> <absent>
- `[ESPR_Talon_Shrike].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_bottom_right": 4000.0, "thruster_bottom_left": 4000.0}

### [GAMA_Railen]
- `[GAMA_Railen].Hull.DoorsHealthPoints`: <absent> -> {"door_rear_airlock": 11400.0, "door_front": 11400.0}
- `[GAMA_Railen].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_wing_top_left": 8000.0, "thruster_main_wing_top_right": 8000.0, "thruster_main_wing_bottom_left": 8000.0, "thruster_main_wing_bottom_right": 8000.0, "thruster_aux_main_top": 8000.0, "thruster_aux…

### [GAMA_Tyilui]
- `[GAMA_Tyilui].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 12600.0, "door_rear": 12600.0}
- `[GAMA_Tyilui].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_wing_top_left": 8000.0, "thruster_main_wing_top_right": 8000.0, "thruster_main_wing_bottom_left": 8000.0, "thruster_main_wing_bottom_right": 8000.0, "thruster_aux_main_top": 8000.0, "thruster_aux…

### [GLSN_Shiv]
- `[GLSN_Shiv].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 3500.0}
- `[GLSN_Shiv].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 7500.0, "Main_Thruster_Left": 7500.0, "Main_Thruster_Side_Right": 7500.0, "Main_Thruster_Side_Left": 7500.0}, "Retro": {"Main_Retro_Right": 5000.0, "Main_Retro_Left": 5000.0}, "Maneuverin…

### [KRIG_L21_Wolf]
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Maneuvering`: <absent> -> {"thruster_mav_FBL": 800.0, "thruster_mav_FBR": 800.0, "thruster_mav_FSL": 800.0, "thruster_mav_FSR": 800.0, "thruster_mav_FTL": 800.0, "thruster_mav_FTR": 800.0, "thruster_mav_MBL": 800.0, "thruster_mav_MBR": 800.0, "th…
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_retro_left": 1250.0, "thruster_retro_right": 1250.0}
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main`: <absent> -> 2000.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_inner`: <absent> -> 1250.0

### [KRIG_L21_Wolf_Collector_Military]
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Maneuvering`: <absent> -> {"thruster_mav_FBL": 800.0, "thruster_mav_FBR": 800.0, "thruster_mav_FSL": 800.0, "thruster_mav_FSR": 800.0, "thruster_mav_FTL": 800.0, "thruster_mav_FTR": 800.0, "thruster_mav_MBL": 800.0, "thruster_mav_MBR": 800.0, "th…
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_retro_left": 1250.0, "thruster_retro_right": 1250.0}
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main`: <absent> -> 2000.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_inner`: <absent> -> 1250.0

### [KRIG_L21_Wolf_Collector_Stealth]
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Maneuvering`: <absent> -> {"thruster_mav_FBL": 800.0, "thruster_mav_FBR": 800.0, "thruster_mav_FSL": 800.0, "thruster_mav_FSR": 800.0, "thruster_mav_FTL": 800.0, "thruster_mav_FTR": 800.0, "thruster_mav_MBL": 800.0, "thruster_mav_MBR": 800.0, "th…
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_retro_left": 1250.0, "thruster_retro_right": 1250.0}
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main`: <absent> -> 2000.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_inner`: <absent> -> 1250.0

### [KRIG_L22_AlphaWolf]
- `[KRIG_L22_AlphaWolf].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main": 2000.0, "thruster_main_wing_left_inner": 1250.0, "thruster_main_wing_left_outer": 1250.0, "thruster_main_wing_right_inner": 1250.0, "thruster_main_wing_right_outer": 1250.0, "main_thruster_pipe…

### [KRIG_L22_AlphaWolf_Collector_Military]
- `[KRIG_L22_AlphaWolf_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main": 2000.0, "thruster_main_wing_left_inner": 1250.0, "thruster_main_wing_left_outer": 1250.0, "thruster_main_wing_right_inner": 1250.0, "thruster_main_wing_right_outer": 1250.0, "main_thruster_pipe…

### [MISC_Fortune]
- `[MISC_Fortune].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}
- `[MISC_Fortune].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_middle": 11400.0, "thruster_main_rear_right": 11400.0, "thruster_main_rear_left": 11400.0, "thruster_main_front_right": 11400.0, "thruster_main_front_left": 11400.0}, "Retro": {"thruster_ret…

### [MISC_Fortune_Collector_Industrial]
- `[MISC_Fortune_Collector_Industrial].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}
- `[MISC_Fortune_Collector_Industrial].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_middle": 11400.0, "thruster_main_rear_right": 11400.0, "thruster_main_rear_left": 11400.0, "thruster_main_front_right": 11400.0, "thruster_main_front_left": 11400.0}, "Retro": {"thruster_ret…

### [MISC_Fortune_Teach]
- `[MISC_Fortune_Teach].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}
- `[MISC_Fortune_Teach].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_middle": 11400.0, "thruster_main_rear_right": 11400.0, "thruster_main_rear_left": 11400.0, "thruster_main_front_right": 11400.0, "thruster_main_front_left": 11400.0}, "Retro": {"thruster_ret…

### [MISC_Hull_A]
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 7400.0
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 7400.0
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_rear_left": 6500.0, "thruster_vtol_rear_right": 6500.0, "thruster_vtol_front_left": 6500.0, "thruster_vtol_front_right": 6500.0}
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_front_left`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_rear_left`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_front_right`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_rear_right`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 7400.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 7400.0 -> <absent>

### [MISC_Hull_B]
- `[MISC_Hull_B].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 12000.0, "thruster_main_left_lower": 10500.0, "thruster_main_left_upper": 10500.0, "thruster_main_right": 12000.0, "thruster_main_right_lower": 10500.0, "thruster_main_right_upper": 10500.…

### [MISC_Razor]
- `[MISC_Razor].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left": 5670.0, "engine_right": 5670.0}, "Retro": {"thruster_retro_left": 5000.0, "thruster_retro_right": 5000.0}, "Maneuvering": {"thruster_FL_top": 4560.0, "thruster_FL_side": 4560.0, "thruster_FL_bott…

### [MISC_Reliant]
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Reliant_Mako]
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Reliant_Sen]
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Reliant_Tana]
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Starlancer_Max]
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0, "thruster_vtol_SL": 2000.0, "thruster_vtol_SR": 2000.0}
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_SR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_SL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlancer_Max_Collector_Indust]
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0, "thruster_vtol_SL": 2000.0, "thruster_vtol_SR": 2000.0}
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_SR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_SL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlancer_TAC]
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0}
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlancer_TAC_Collector_Military]
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0}
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlite]
- `[MISC_Starlite].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_right": 11500.0, "thruster_main_left": 11500.0, "thruster_main_bottom_right": 11500.0, "thruster_main_bottom_left": 11500.0}, "Retro": {"thruster_retro_right": 10500.0, "thruster_retro_left": 105…

### [MRAI_Guardian]
- `[MRAI_Guardian].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…

### [MRAI_Guardian_MX]
- `[MRAI_Guardian_MX].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…

### [MRAI_Guardian_MX_Collector_Military]
- `[MRAI_Guardian_MX_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…

### [MRAI_Guardian_Military]
- `[MRAI_Guardian_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…

### [MRAI_Guardian_QI]
- `[MRAI_Guardian_QI].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…

### [MRAI_Guardian_QI_Collector_Indust]
- `[MRAI_Guardian_QI_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…

### [MRAI_Pulse_LX]
- `[MRAI_Pulse_LX].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux`: <absent> -> 2750.0
- `[MRAI_Pulse_LX].Hull.ThrustersHealthPoints.Main.thruster_aux`: 2750.0 -> <absent>

### [ORIG_400i]
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_rear_right`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_front_right`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_front_left`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_rear_left`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_bottom_front_left": 16000.0, "thruster_bottom_front_right": 16000.0, "thruster_bottom_rear_left": 16000.0, "thruster_bottom_rear_right": 16000.0}

### [ORIG_m80]
- `[ORIG_m80].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 8000.0, "thruster_main_middle": 8000.0, "thruster_main_right": 8000.0}, "Retro": {"thruster_retro_left": 6500.0, "thruster_retro_right": 6500.0, "thruster_retro_underleft": 6500.0, "thrust…

### [RSI_Apollo_Medivac]
- `[RSI_Apollo_Medivac].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Apollo_Medivac].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…

### [RSI_Apollo_Triage]
- `[RSI_Apollo_Triage].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Apollo_Triage].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…

### [RSI_Apollo_Triage_Collector_Stealth]
- `[RSI_Apollo_Triage_Collector_Stealth].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Apollo_Triage_Collector_Stealth].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…

### [RSI_Aurora_GS_CL]
- `[RSI_Aurora_GS_CL].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_CL].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_CL].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}

### [RSI_Aurora_GS_ES]
- `[RSI_Aurora_GS_ES].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_ES].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_ES].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}

### [RSI_Aurora_GS_LN]
- `[RSI_Aurora_GS_LN].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_LN].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}

### [RSI_Aurora_GS_LX]
- `[RSI_Aurora_GS_LX].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_LX].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_LX].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}

### [RSI_Aurora_GS_MR]
- `[RSI_Aurora_GS_MR].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_MR].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_MR].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}

### [RSI_Aurora_GS_SE]
- `[RSI_Aurora_GS_SE].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_SE].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}

### [RSI_Aurora_Mk2]
- `[RSI_Aurora_Mk2].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 2500.0, "thruster_main_right": 2500.0}, "Retro": {"thruster_retro_right": 1500.0, "thruster_retro_left": 1500.0}, "Maneuvering": {"thruster_mav_nose_top_left": 600.0, "thruster_mav_nose_le…

### [RSI_Constellation_Andromeda]
- `[RSI_Constellation_Andromeda].Hull.DoorsHealthPoints.door_elevator`: <absent> -> 4000.0
- `[RSI_Constellation_Andromeda].Hull.DoorsHealthPoints.door_airlock_neck_top`: <absent> -> 6000.0

### [RSI_Constellation_Aquila]
- `[RSI_Constellation_Aquila].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_body_left": 6000.0, "door_airlock_body_right": 6000.0, "door_airlock_neck_top": 6000.0}

### [RSI_Constellation_Phoenix]
- `[RSI_Constellation_Phoenix].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_neck_top": 6000.0}

### [RSI_Constellation_Phoenix_Emerald]
- `[RSI_Constellation_Phoenix_Emerald].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_neck_top": 6000.0}

### [RSI_Constellation_Taurus]
- `[RSI_Constellation_Taurus].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_body_left": 6000.0, "door_airlock_body_right": 6000.0, "door_airlock_neck_top": 6000.0}

### [RSI_Constellation_Taurus_Military]
- `[RSI_Constellation_Taurus_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_body_left": 6000.0, "door_airlock_body_right": 6000.0, "door_airlock_neck_top": 6000.0}

### [RSI_Hermes]
- `[RSI_Hermes].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Hermes].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…

### [RSI_Mantis]
- `[RSI_Mantis].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Mantis].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…

### [RSI_Meteor]
- `[RSI_Meteor].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Meteor].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…

### [RSI_Meteor_Collector_Military]
- `[RSI_Meteor_Collector_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Meteor_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…

### [RSI_Meteor_Collector_Stealth]
- `[RSI_Meteor_Collector_Stealth].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Meteor_Collector_Stealth].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…

### [RSI_Perseus]
- `[RSI_Perseus].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_right": 30000.0, "thruster_main_top_left": 30000.0, "thruster_main_bottom_right": 30000.0, "thruster_main_bottom_left": 30000.0}, "Retro": {"thruster_retro_front_right_top": 5000.0, "thruster…

### [RSI_Salvation]
- `[RSI_Salvation].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_top_left": 2500.0, "engine_top_right": 2500.0, "engine_bottom_left": 2500.0, "engine_bottom_right": 2500.0}, "Retro": {"retro_bottom_left": 1700.0, "retro_bottom_right": 1700.0, "retro_top_left": 1700.0…

### [RSI_Zeus_CL]
- `[RSI_Zeus_CL].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…

### [RSI_Zeus_CL_Collector_Indust]
- `[RSI_Zeus_CL_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…

### [RSI_Zeus_ES]
- `[RSI_Zeus_ES].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…

### [RSI_Zeus_ES_Collector_Indust]
- `[RSI_Zeus_ES_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…

### [VNCL_Stinger]
- `[VNCL_Stinger].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01": 14000.0, "thruster_main_02": 14000.0, "thruster_main_03": 9000.0}, "Retro": {"thruster_retro_left": 7000.0, "thruster_retro_right": 7000.0}, "Maneuvering": {"thruster_rear_top_left": 3000.0,…

### [XNAA_SanTokYai]
- `[XNAA_SanTokYai].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"main_thruster_top_left": 15000.0, "main_thruster_top_right": 15000.0, "main_thruster_bottom_left": 15000.0, "main_thruster_bottom_right": 15000.0, "mav_thruster_backward_right": 12500.0, "mav_thruster_backward…

## vehicle_stats.json — 905 changed value(s)

### [AEGS_Avenger_Stalker]
- `[AEGS_Avenger_Stalker].BaseLoadout.PilotBurstDPS`: 0.0 -> 2359.5

### [AEGS_Avenger_Titan]
- `[AEGS_Avenger_Titan].BaseLoadout.PilotBurstDPS`: 0.0 -> 2359.5

### [AEGS_Avenger_Titan_Renegade]
- `[AEGS_Avenger_Titan_Renegade].BaseLoadout.PilotBurstDPS`: 0.0 -> 1548.8

### [AEGS_Avenger_Warlock]
- `[AEGS_Avenger_Warlock].BaseLoadout.PilotBurstDPS`: 0.0 -> 2359.5

### [AEGS_Eclipse]
- `[AEGS_Eclipse].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [AEGS_Gladius]
- `[AEGS_Gladius].BaseLoadout.PilotBurstDPS`: 0.0 -> 1597.9

### [AEGS_Gladius_Dunlevy]
- `[AEGS_Gladius_Dunlevy].BaseLoadout.PilotBurstDPS`: 0.0 -> 1597.9
- `[AEGS_Gladius_Dunlevy].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [AEGS_Gladius_PIR]
- `[AEGS_Gladius_PIR].BaseLoadout.PilotBurstDPS`: 0.0 -> 1597.9

### [AEGS_Gladius_Valiant]
- `[AEGS_Gladius_Valiant].BaseLoadout.PilotBurstDPS`: 0.0 -> 1639.1

### [AEGS_Hammerhead]
- `[AEGS_Hammerhead].BaseLoadout.TurretsBurstDPS`: 0.0 -> 19629.0

### [AEGS_Hammerhead_GS]
- `[AEGS_Hammerhead_GS].Hull.DoorsHealthPoints`: <absent> -> {"door_cargo_02": 56000.0, "door_left_02": 24000.0, "door_right_02": 24000.0, "door_nose_airlock": 24000.0}
- `[AEGS_Hammerhead_GS].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 25000.0, "thruster_main_bottom_left": 25000.0, "thruster_main_top_right": 25000.0, "thruster_main_bottom_right": 25000.0}, "Retro": {"thruster_retro_left": 23400.0, "thruster_retro_rig…
- `[AEGS_Hammerhead_GS].BaseLoadout.TurretsBurstDPS`: 0.0 -> 19629.0
- `[AEGS_Hammerhead_GS].BaseLoadout.TotalShieldHP`: 0.0 -> 211200.0

### [AEGS_Hammerhead_Showdown]
- `[AEGS_Hammerhead_Showdown].BaseLoadout.TurretsBurstDPS`: 0.0 -> 19629.0

### [AEGS_Idris_M]
- `[AEGS_Idris_M].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 24000.0, "door_rear": 2520000.0, "door_argo": 100000.0, "door_front_left": 100000.0, "door_front_right": 100000.0, "door_airlock_front_left": 24000.0, "door_airlock_front_right": 24000.0}
- `[AEGS_Idris_M].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left_1": 100000.0, "engine_right_1": 100000.0, "engine_left_2": 500000.0, "engine_right_2": 500000.0, "engine_left_3": 500000.0, "engine_right_3": 500000.0}, "Retro": {"thruster_retro_left": 80000.0, "t…
- `[AEGS_Idris_M].BaseLoadout.PilotBurstDPS`: 0.0 -> 14416.0
- `[AEGS_Idris_M].BaseLoadout.TurretsBurstDPS`: 1833.3 -> 33608.9
- `[AEGS_Idris_M].BaseLoadout.TotalShieldHP`: 0.0 -> 2112000.0

### [AEGS_Idris_P]
- `[AEGS_Idris_P].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 24000.0, "door_rear": 2520000.0, "door_argo": 100000.0, "door_front_left": 100000.0, "door_front_right": 100000.0, "door_airlock_front_left": 24000.0, "door_airlock_front_right": 24000.0}
- `[AEGS_Idris_P].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left_1": 100000.0, "engine_right_1": 100000.0, "engine_left_2": 500000.0, "engine_right_2": 500000.0, "engine_left_3": 500000.0, "engine_right_3": 500000.0}, "Retro": {"thruster_retro_left": 80000.0, "t…
- `[AEGS_Idris_P].BaseLoadout.TurretsBurstDPS`: 1833.3 -> 32217.2
- `[AEGS_Idris_P].BaseLoadout.TotalShieldHP`: 0.0 -> 2112000.0

### [AEGS_Idris_P_Collector_Military]
- `[AEGS_Idris_P_Collector_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 24000.0, "door_rear": 2520000.0, "door_argo": 100000.0, "door_front_left": 100000.0, "door_front_right": 100000.0, "door_airlock_front_left": 24000.0, "door_airlock_front_right": 24000.0}
- `[AEGS_Idris_P_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left_1": 100000.0, "engine_right_1": 100000.0, "engine_left_2": 500000.0, "engine_right_2": 500000.0, "engine_left_3": 500000.0, "engine_right_3": 500000.0}, "Retro": {"thruster_retro_left": 80000.0, "t…
- `[AEGS_Idris_P_Collector_Military].BaseLoadout.TurretsBurstDPS`: 1833.3 -> 25961.3
- `[AEGS_Idris_P_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 2112000.0

### [AEGS_Reclaimer]
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 28500.0
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 28500.0
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 28500.0 -> <absent>
- `[AEGS_Reclaimer].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 28500.0 -> <absent>
- `[AEGS_Reclaimer].BaseLoadout.TurretsBurstDPS`: 1166.7 -> 10168.9

### [AEGS_Reclaimer_Showdown]
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 28500.0 -> <absent>
- `[AEGS_Reclaimer_Showdown].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 28500.0 -> <absent>
- `[AEGS_Reclaimer_Showdown].BaseLoadout.TurretsBurstDPS`: 1166.7 -> 10168.9

### [AEGS_Reclaimer_Teach]
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 28500.0
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 28500.0 -> <absent>
- `[AEGS_Reclaimer_Teach].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 28500.0 -> <absent>
- `[AEGS_Reclaimer_Teach].BaseLoadout.TurretsBurstDPS`: 1166.7 -> 10168.9

### [AEGS_Redeemer]
- `[AEGS_Redeemer].FuelManagement.FuelBurnRatePer10KNewton.Maneuvering`: 17.5 -> 12.5
- `[AEGS_Redeemer].FuelManagement.FuelBurnRatePer10KNewton.Main`: 2.5 -> 7.5
- `[AEGS_Redeemer].FuelManagement.FuelUsagePerSecond.Maneuvering`: 7671.704 -> 5672.563
- `[AEGS_Redeemer].FuelManagement.FuelUsagePerSecond.Main`: 1874.195 -> 3873.336
- `[AEGS_Redeemer].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_wing_bottom`: 28950.0 -> <absent>
- `[AEGS_Redeemer].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_mav_wing_bottom": 28950.0}
- `[AEGS_Redeemer].FlightCharacteristics.ThrustCapacity.Maneuvering`: 61373632.0 -> 45380504.0
- `[AEGS_Redeemer].FlightCharacteristics.ThrustCapacity.Main`: 14993558.0 -> 30986686.0
- `[AEGS_Redeemer].BaseLoadout.PilotBurstDPS`: 0.0 -> 541.7
- `[AEGS_Redeemer].BaseLoadout.TurretsBurstDPS`: 2532.0 -> 7798.6

### [AEGS_Sabre]
- `[AEGS_Sabre].BaseLoadout.PilotBurstDPS`: 0.0 -> 2182.5

### [AEGS_Sabre_Comet]
- `[AEGS_Sabre_Comet].BaseLoadout.PilotBurstDPS`: 0.0 -> 2017.5

### [AEGS_Sabre_Firebird]
- `[AEGS_Sabre_Firebird].BaseLoadout.PilotBurstDPS`: 0.0 -> 1013.3

### [AEGS_Sabre_Firebird_Collector_Milt]
- `[AEGS_Sabre_Firebird_Collector_Milt].BaseLoadout.PilotBurstDPS`: 0.0 -> 1013.3
- `[AEGS_Sabre_Firebird_Collector_Milt].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [AEGS_Sabre_Peregrine_Collector_Competition]
- `[AEGS_Sabre_Peregrine_Collector_Competition].BaseLoadout.TotalShieldHP`: 0.0 -> 3840.0

### [AEGS_Sabre_Raven]
- `[AEGS_Sabre_Raven].BaseLoadout.PilotBurstDPS`: 0.0 -> 1093.5

### [AEGS_Tiburon]
- `[AEGS_Tiburon].Hull.DoorsHealthPoints`: <absent> -> {"door_cargo_02": 56000.0, "door_left_02": 24000.0, "door_right_02": 24000.0}
- `[AEGS_Tiburon].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 25000.0, "thruster_main_bottom_left": 25000.0, "thruster_main_top_right": 25000.0, "thruster_main_bottom_right": 25000.0}, "Retro": {"thruster_retro_left": 23400.0, "thruster_retro_rig…
- `[AEGS_Tiburon].BaseLoadout.TurretsBurstDPS`: 0.0 -> 14004.8
- `[AEGS_Tiburon].BaseLoadout.TotalShieldHP`: 0.0 -> 211200.0

### [AEGS_Vanguard]
- `[AEGS_Vanguard].BaseLoadout.PilotBurstDPS`: 1819.8 -> 3526.8
- `[AEGS_Vanguard].BaseLoadout.TurretsBurstDPS`: 0.0 -> 900.0

### [AEGS_Vanguard_Harbinger]
- `[AEGS_Vanguard_Harbinger].BaseLoadout.PilotBurstDPS`: 0.0 -> 3327.0

### [AEGS_Vanguard_Hoplite]
- `[AEGS_Vanguard_Hoplite].BaseLoadout.PilotBurstDPS`: 0.0 -> 3507.0
- `[AEGS_Vanguard_Hoplite].BaseLoadout.TurretsBurstDPS`: 0.0 -> 900.0

### [AEGS_Vanguard_Sentinel]
- `[AEGS_Vanguard_Sentinel].BaseLoadout.PilotBurstDPS`: 0.0 -> 875.0

### [ANVL_Arrow]
- `[ANVL_Arrow].BaseLoadout.PilotBurstDPS`: 0.0 -> 1494.5

### [ANVL_Asgard]
- `[ANVL_Asgard].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 6000.0, "door_left": 6000.0, "door_rear": 14000.0}
- `[ANVL_Asgard].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_left": 17600.0, "thruster_main_rear_right": 17600.0, "thruster_main_front_left": 17600.0, "thruster_main_front_right": 17600.0, "thruster_aux_left": 17600.0, "thruster_aux_right": 17600.0}, …
- `[ANVL_Asgard].BaseLoadout.PilotBurstDPS`: 0.0 -> 3273.8
- `[ANVL_Asgard].BaseLoadout.TurretsBurstDPS`: 403.2 -> 2039.0

### [ANVL_Asgard_Collector_Military]
- `[ANVL_Asgard_Collector_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 6000.0, "door_left": 6000.0, "door_rear": 14000.0}
- `[ANVL_Asgard_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_left": 17600.0, "thruster_main_rear_right": 17600.0, "thruster_main_front_left": 17600.0, "thruster_main_front_right": 17600.0, "thruster_aux_left": 17600.0, "thruster_aux_right": 17600.0}, …
- `[ANVL_Asgard_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 3097.9
- `[ANVL_Asgard_Collector_Military].BaseLoadout.TurretsBurstDPS`: 403.2 -> 2039.0

### [ANVL_C8R_Pisces]
- `[ANVL_C8R_Pisces].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [ANVL_C8X_Pisces_Expedition]
- `[ANVL_C8X_Pisces_Expedition].BaseLoadout.PilotBurstDPS`: 0.0 -> 847.8

### [ANVL_C8_Pisces]
- `[ANVL_C8_Pisces].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [ANVL_Carrack]
- `[ANVL_Carrack].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left_large": 30000.0, "thruster_main_right_large": 30000.0, "thruster_main_left_small": 27500.0, "thruster_main_right_small": 27500.0}, "Retro": {"thruster_retro_forward": 28950.0, "thruster_retr…
- `[ANVL_Carrack].BaseLoadout.TurretsBurstDPS`: 0.0 -> 6543.0
- `[ANVL_Carrack].BaseLoadout.TotalShieldHP`: 0.0 -> 144000.0

### [ANVL_Carrack_Expedition]
- `[ANVL_Carrack_Expedition].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left_large": 30000.0, "thruster_main_right_large": 30000.0, "thruster_main_left_small": 27500.0, "thruster_main_right_small": 27500.0}, "Retro": {"thruster_retro_forward": 28950.0, "thruster_retr…
- `[ANVL_Carrack_Expedition].BaseLoadout.TurretsBurstDPS`: 0.0 -> 6543.0
- `[ANVL_Carrack_Expedition].BaseLoadout.TotalShieldHP`: 0.0 -> 144000.0

### [ANVL_Centurion]
- `[ANVL_Centurion].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3773.2

### [ANVL_Gladiator]
- `[ANVL_Gladiator].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 7256.0 -> <absent>
- `[ANVL_Gladiator].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 7256.0 -> <absent>
- `[ANVL_Gladiator].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_left": 7256.0, "thruster_top_front_right": 7256.0}
- `[ANVL_Gladiator].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2

### [ANVL_Hawk]
- `[ANVL_Hawk].BaseLoadout.PilotBurstDPS`: 0.0 -> 1312.2

### [ANVL_Hornet_F7A_Mk1]
- `[ANVL_Hornet_F7A_Mk1].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7A_Mk1].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7A_Mk1].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7A_Mk1].BaseLoadout.PilotBurstDPS`: 0.0 -> 4279.4

### [ANVL_Hornet_F7A_Mk2]
- `[ANVL_Hornet_F7A_Mk2].BaseLoadout.PilotBurstDPS`: 0.0 -> 4719.0

### [ANVL_Hornet_F7A_Mk2_Exec_Military]
- `[ANVL_Hornet_F7A_Mk2_Exec_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 5382.0
- `[ANVL_Hornet_F7A_Mk2_Exec_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [ANVL_Hornet_F7A_Mk2_Exec_Stealth]
- `[ANVL_Hornet_F7A_Mk2_Exec_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 5382.0
- `[ANVL_Hornet_F7A_Mk2_Exec_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 4488.0

### [ANVL_Hornet_F7CM]
- `[ANVL_Hornet_F7CM].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7CM].BaseLoadout.PilotBurstDPS`: 0.0 -> 2106.8

### [ANVL_Hornet_F7CM_Heartseeker]
- `[ANVL_Hornet_F7CM_Heartseeker].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM_Heartseeker].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CM_Heartseeker].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7CM_Heartseeker].BaseLoadout.PilotBurstDPS`: 0.0 -> 2476.2

### [ANVL_Hornet_F7CM_Mk2]
- `[ANVL_Hornet_F7CM_Mk2].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_S5": 7000.0}, "Retro": {"retro_thruster_left": 8250.0, "retro_thruster_right": 8250.0}, "Maneuvering": {"thruster_bottom_back_left": 5000.0, "thruster_bottom_back_right": 5000.0, "thruster_bottom_front_…
- `[ANVL_Hornet_F7CM_Mk2].BaseLoadout.PilotBurstDPS`: 0.0 -> 4714.5

### [ANVL_Hornet_F7CM_Mk2_Heartseeker]
- `[ANVL_Hornet_F7CM_Mk2_Heartseeker].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_S5": 7000.0}, "Retro": {"retro_thruster_left": 8250.0, "retro_thruster_right": 8250.0}, "Maneuvering": {"thruster_bottom_back_left": 5000.0, "thruster_bottom_back_right": 5000.0, "thruster_bottom_front_…
- `[ANVL_Hornet_F7CM_Mk2_Heartseeker].BaseLoadout.PilotBurstDPS`: 0.0 -> 5467.8

### [ANVL_Hornet_F7CR]
- `[ANVL_Hornet_F7CR].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CR].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CR].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7CR].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2

### [ANVL_Hornet_F7CR_Mk2]
- `[ANVL_Hornet_F7CR_Mk2].BaseLoadout.PilotBurstDPS`: 0.0 -> 2532.0

### [ANVL_Hornet_F7CS]
- `[ANVL_Hornet_F7CS].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CS].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7CS].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7CS].BaseLoadout.PilotBurstDPS`: 0.0 -> 1093.5

### [ANVL_Hornet_F7CS_Mk2]
- `[ANVL_Hornet_F7CS_Mk2].BaseLoadout.PilotBurstDPS`: 0.0 -> 2532.0

### [ANVL_Hornet_F7C]
- `[ANVL_Hornet_F7C].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7C].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2

### [ANVL_Hornet_F7C_Mk2]
- `[ANVL_Hornet_F7C_Mk2].BaseLoadout.PilotBurstDPS`: 0.0 -> 2532.0

### [ANVL_Hornet_F7C_Wildfire]
- `[ANVL_Hornet_F7C_Wildfire].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_right`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C_Wildfire].Hull.ThrustersHealthPoints.Maneuvering.thruster_top_front_left`: 4700.0 -> <absent>
- `[ANVL_Hornet_F7C_Wildfire].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_top_front_right": 4700.0, "thruster_top_front_left": 4700.0}
- `[ANVL_Hornet_F7C_Wildfire].BaseLoadout.PilotBurstDPS`: 0.0 -> 2176.8

### [ANVL_Hornet_F7_Mk2_Collector_Mod]
- `[ANVL_Hornet_F7_Mk2_Collector_Mod].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_S5": 7000.0}, "Retro": {"retro_thruster_left": 8250.0, "retro_thruster_right": 8250.0}, "Maneuvering": {"thruster_bottom_back_left": 5000.0, "thruster_bottom_back_right": 5000.0, "thruster_bottom_front_…
- `[ANVL_Hornet_F7_Mk2_Collector_Mod].BaseLoadout.PilotBurstDPS`: 0.0 -> 4714.5
- `[ANVL_Hornet_F7_Mk2_Collector_Mod].BaseLoadout.TotalShieldHP`: 3168.0 -> 9504.0

### [ANVL_Hurricane]
- `[ANVL_Hurricane].BaseLoadout.PilotBurstDPS`: 0.0 -> 1635.8
- `[ANVL_Hurricane].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [ANVL_Lightning_F8C]
- `[ANVL_Lightning_F8C].BaseLoadout.PilotBurstDPS`: 0.0 -> 3266.5

### [ANVL_Lightning_F8C_Collector_Military]
- `[ANVL_Lightning_F8C_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 3266.5
- `[ANVL_Lightning_F8C_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 21120.0

### [ANVL_Lightning_F8C_Collector_Stealth]
- `[ANVL_Lightning_F8C_Collector_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 3266.5
- `[ANVL_Lightning_F8C_Collector_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 14960.0

### [ANVL_Lightning_F8C_Exec]
- `[ANVL_Lightning_F8C_Exec].BaseLoadout.PilotBurstDPS`: 0.0 -> 3266.5

### [ANVL_Lightning_F8C_Exec_Military]
- `[ANVL_Lightning_F8C_Exec_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 4749.0
- `[ANVL_Lightning_F8C_Exec_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 21120.0

### [ANVL_Lightning_F8C_Exec_Stealth]
- `[ANVL_Lightning_F8C_Exec_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 4749.0
- `[ANVL_Lightning_F8C_Exec_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 14960.0

### [ANVL_Lightning_F8C_Plat]
- `[ANVL_Lightning_F8C_Plat].BaseLoadout.PilotBurstDPS`: 0.0 -> 3266.5

### [ANVL_Lightning_F8]
- `[ANVL_Lightning_F8].BaseLoadout.PilotBurstDPS`: 0.0 -> 5876.7

### [ANVL_Paladin]
- `[ANVL_Paladin].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 10000.0, "thruster_main_right": 10000.0}, "Retro": {"thruster_retro_left": 5000.0, "thruster_retro_right": 5000.0}, "Maneuvering": {"anim_thruster_flap_01": 100.0, "anim_thruster_flap_02":…
- `[ANVL_Paladin].BaseLoadout.TurretsBurstDPS`: 0.0 -> 8181.0
- `[ANVL_Paladin].BaseLoadout.TotalShieldHP`: 0.0 -> 72000.0

### [ANVL_Spartan]
- `[ANVL_Spartan].BaseLoadout.TurretsBurstDPS`: 0.0 -> 677.3

### [ANVL_Terrapin]
- `[ANVL_Terrapin].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_front_left": 6000.0, "thruster_main_front_right": 6000.0, "thruster_main_rear_left": 6000.0, "thruster_main_rear_right": 6000.0}, "Retro": {"thruster_retro_left": 5240.0, "thruster_retro_right": …
- `[ANVL_Terrapin].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[ANVL_Terrapin].BaseLoadout.TotalShieldHP`: 0.0 -> 20000.0

### [ANVL_Terrapin_Medic]
- `[ANVL_Terrapin_Medic].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_front_left": 6000.0, "thruster_main_front_right": 6000.0, "thruster_main_rear_left": 6000.0, "thruster_main_rear_right": 6000.0}, "Retro": {"thruster_retro_left": 5240.0, "thruster_retro_right": …
- `[ANVL_Terrapin_Medic].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[ANVL_Terrapin_Medic].BaseLoadout.TotalShieldHP`: 0.0 -> 20000.0

### [ANVL_Terrapin_Medic_Collector_Medic]
- `[ANVL_Terrapin_Medic_Collector_Medic].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_front_left": 6000.0, "thruster_main_front_right": 6000.0, "thruster_main_rear_left": 6000.0, "thruster_main_rear_right": 6000.0}, "Retro": {"thruster_retro_left": 5240.0, "thruster_retro_right": …
- `[ANVL_Terrapin_Medic_Collector_Medic].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[ANVL_Terrapin_Medic_Collector_Medic].BaseLoadout.TotalShieldHP`: 0.0 -> 14400.0

### [ANVL_Valkyrie]
- `[ANVL_Valkyrie].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2
- `[ANVL_Valkyrie].BaseLoadout.TurretsBurstDPS`: 1635.8 -> 3818.2

### [ANVL_Valkyrie_CitizenCon]
- `[ANVL_Valkyrie_CitizenCon].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2
- `[ANVL_Valkyrie_CitizenCon].BaseLoadout.TurretsBurstDPS`: 1635.8 -> 3818.2

### [ARGO_MOLE]
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_front_vtol_left": 14500.0, "thruster_front_vtol_right": 14500.0, "thruster_rear_vtol_left": 14500.0, "thruster_rear_vtol_right": 14500.0}
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_left`: 14500.0 -> <absent>
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_left`: 14500.0 -> <absent>
- `[ARGO_MOLE].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [ARGO_MOLE_Teach]
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_front_vtol_left": 14500.0, "thruster_front_vtol_right": 14500.0, "thruster_rear_vtol_left": 14500.0, "thruster_rear_vtol_right": 14500.0}
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_left`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_front_vtol_right`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].Hull.ThrustersHealthPoints.Main.thruster_rear_vtol_left`: 14500.0 -> <absent>
- `[ARGO_MOLE_Teach].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [ARGO_MOTH]
- `[ARGO_MOTH].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left_top": 14500.0, "thruster_main_left_bottom": 14500.0, "thruster_main_right_top": 14500.0, "thruster_main_right_bottom": 14500.0}, "Retro": {"thruster_retro_left": 13500.0, "thruster_retro_rig…
- `[ARGO_MOTH].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[ARGO_MOTH].BaseLoadout.TotalShieldHP`: 0.0 -> 100000.0

### [ARGO_MPUV]
- `[ARGO_MPUV].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 400.0, "door_right": 400.0, "door_rear": 400.0}

### [ARGO_MPUV_Transport]
- `[ARGO_MPUV_Transport].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}

### [ARGO_RAFT]
- `[ARGO_RAFT].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_right_2": 4500.0, "thruster_main_right_1": 4500.0, "thruster_main_left_2": 4500.0, "thruster_main_left_1": 4500.0}, "Retro": {"thruster_retro_right": 4500.0, "thruster_retro_left": 4500.0}, "Mane…
- `[ARGO_RAFT].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1367.3
- `[ARGO_RAFT].BaseLoadout.TotalShieldHP`: 0.0 -> 21600.0

### [ARGO_RAFT_Collector_Indust]
- `[ARGO_RAFT_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_right_2": 4500.0, "thruster_main_right_1": 4500.0, "thruster_main_left_2": 4500.0, "thruster_main_left_1": 4500.0}, "Retro": {"thruster_retro_right": 4500.0, "thruster_retro_left": 4500.0}, "Mane…
- `[ARGO_RAFT_Collector_Indust].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1003.3
- `[ARGO_RAFT_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 21600.0

### [ARGO_SRV]
- `[ARGO_SRV].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_FLT": 21000.0, "thruster_VTOL_FRT": 21000.0, "thruster_VTOL_ML": 21000.0, "thruster_VTOL_MR": 21000.0, "thruster_VTOL_RL": 21000.0, "thruster_VTOL_RR": 21000.0, "thruster_VTOL_FLB": 21000.0, "thruster_VTO…
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FRB`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FLT`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FRT`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_ML`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_FLB`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_RL`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_MR`: 21000.0 -> <absent>
- `[ARGO_SRV].Hull.ThrustersHealthPoints.Main.thruster_VTOL_RR`: 21000.0 -> <absent>

### [BANU_Defender]
- `[BANU_Defender].BaseLoadout.PilotBurstDPS`: 0.0 -> 6075.0

### [CNOU_Mustang_Alpha]
- `[CNOU_Mustang_Alpha].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [CNOU_Mustang_Beta]
- `[CNOU_Mustang_Beta].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [CNOU_Mustang_Delta]
- `[CNOU_Mustang_Delta].BaseLoadout.PilotBurstDPS`: 0.0 -> 1312.2

### [CNOU_Mustang_Gamma]
- `[CNOU_Mustang_Gamma].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [CNOU_Mustang_Omega]
- `[CNOU_Mustang_Omega].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [CNOU_Nomad]
- `[CNOU_Nomad].Hull.DoorsHealthPoints`: <absent> -> {"door_entrance": 1000.0}
- `[CNOU_Nomad].BaseLoadout.PilotBurstDPS`: 0.0 -> 1636.9
- `[CNOU_Nomad].BaseLoadout.TotalShieldHP`: 4320.0 -> 6480.0

### [CNOU_Nomad_Teach]
- `[CNOU_Nomad_Teach].Hull.DoorsHealthPoints`: <absent> -> {"door_entrance": 1000.0}
- `[CNOU_Nomad_Teach].BaseLoadout.PilotBurstDPS`: 0.0 -> 1636.9
- `[CNOU_Nomad_Teach].BaseLoadout.TotalShieldHP`: 0.0 -> 6480.0

### [CRUS_Intrepid]
- `[CRUS_Intrepid].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 1200.0, "thruster_main_aux_01_left": 1200.0, "thruster_main_aux_02_left": 1200.0, "thruster_main_aux_03_left": 1200.0, "thruster_main_right": 1200.0, "thruster_main_aux_01_right": 1200.0, …
- `[CRUS_Intrepid].BaseLoadout.PilotBurstDPS`: 0.0 -> 817.9
- `[CRUS_Intrepid].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [CRUS_Intrepid_Collector_Indust]
- `[CRUS_Intrepid_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 1200.0, "thruster_main_aux_01_left": 1200.0, "thruster_main_aux_02_left": 1200.0, "thruster_main_aux_03_left": 1200.0, "thruster_main_right": 1200.0, "thruster_main_aux_01_right": 1200.0, …
- `[CRUS_Intrepid_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 817.9
- `[CRUS_Intrepid_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [CRUS_Spirit_A1]
- `[CRUS_Spirit_A1].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01_left": 16500.0, "thruster_main_02_left": 16500.0, "thruster_main_03_left": 16500.0, "thruster_main_04_left": 16500.0, "thruster_main_01_right": 16500.0, "thruster_main_02_right": 16500.0, "thr…
- `[CRUS_Spirit_A1].BaseLoadout.PilotBurstDPS`: 0.0 -> 2734.6
- `[CRUS_Spirit_A1].BaseLoadout.TurretsBurstDPS`: 0.0 -> 656.1
- `[CRUS_Spirit_A1].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [CRUS_Spirit_C1]
- `[CRUS_Spirit_C1].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01_left": 16500.0, "thruster_main_02_left": 16500.0, "thruster_main_03_left": 16500.0, "thruster_main_04_left": 16500.0, "thruster_main_01_right": 16500.0, "thruster_main_02_right": 16500.0, "thr…
- `[CRUS_Spirit_C1].BaseLoadout.PilotBurstDPS`: 0.0 -> 2734.6
- `[CRUS_Spirit_C1].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [CRUS_Spirit_C1_Civilian]
- `[CRUS_Spirit_C1_Civilian].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01_left": 16500.0, "thruster_main_02_left": 16500.0, "thruster_main_03_left": 16500.0, "thruster_main_04_left": 16500.0, "thruster_main_01_right": 16500.0, "thruster_main_02_right": 16500.0, "thr…
- `[CRUS_Spirit_C1_Civilian].BaseLoadout.PilotBurstDPS`: 0.0 -> 2734.6
- `[CRUS_Spirit_C1_Civilian].BaseLoadout.TotalShieldHP`: 0.0 -> 10000.0

### [CRUS_Star_Runner]
- `[CRUS_Star_Runner].Hull.DoorsHealthPoints`: <absent> -> {"door_rear_ramp": 9800.0}
- `[CRUS_Star_Runner].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 18500.0, "thruster_main_right": 18500.0, "thruster_main_extra_left": 18500.0, "thruster_main_extra_right": 18500.0}, "Retro": {"thruster_retro_left": 18500.0, "thruster_retro_right": 18500…
- `[CRUS_Star_Runner].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2
- `[CRUS_Star_Runner].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5
- `[CRUS_Star_Runner].BaseLoadout.TotalShieldHP`: 0.0 -> 72000.0

### [CRUS_Starfighter_Inferno]
- `[CRUS_Starfighter_Inferno].BaseLoadout.PilotBurstDPS`: 0.0 -> 4380.0

### [CRUS_Starfighter_Inferno_Collector_Military]
- `[CRUS_Starfighter_Inferno_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 4380.0

### [CRUS_Starfighter_Ion]
- `[CRUS_Starfighter_Ion].BaseLoadout.PilotBurstDPS`: 0.0 -> 4720.8

### [CRUS_Starfighter_Ion_Collector_Stealth]
- `[CRUS_Starfighter_Ion_Collector_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 4720.8

### [CRUS_Starlifter_A2]
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[CRUS_Starlifter_A2].BaseLoadout.TurretsBurstDPS`: 0.0 -> 13725.7
- `[CRUS_Starlifter_A2].BaseLoadout.TotalShieldHP`: 0.0 -> 316800.0

### [CRUS_Starlifter_A2_Collector_Military]
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_A2_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 1750.0
- `[CRUS_Starlifter_A2_Collector_Military].BaseLoadout.TurretsBurstDPS`: 0.0 -> 12717.8
- `[CRUS_Starlifter_A2_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 316800.0

### [CRUS_Starlifter_C2]
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_C2].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[CRUS_Starlifter_C2].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3686.7
- `[CRUS_Starlifter_C2].BaseLoadout.TotalShieldHP`: 0.0 -> 144000.0

### [CRUS_Starlifter_M2]
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_VTOL_wing_left": 22200.0, "thruster_VTOL_wing_right": 22200.0, "thruster_VTOL_side_left": 22200.0, "thruster_VTOL_side_right": 22200.0}
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_left`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_side_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].Hull.ThrustersHealthPoints.Main.thruster_VTOL_wing_right`: 22200.0 -> <absent>
- `[CRUS_Starlifter_M2].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[CRUS_Starlifter_M2].BaseLoadout.TurretsBurstDPS`: 0.0 -> 5737.6
- `[CRUS_Starlifter_M2].BaseLoadout.TotalShieldHP`: 0.0 -> 211200.0

### [DRAK_Buccaneer]
- `[DRAK_Buccaneer].FuelManagement.FuelBurnRatePer10KNewton.Maneuvering`: 30.0 -> 12.5
- `[DRAK_Buccaneer].FuelManagement.FuelBurnRatePer10KNewton.Main`: 2.5 -> 20.0
- `[DRAK_Buccaneer].FuelManagement.FuelUsagePerSecond.Maneuvering`: 1123.8 -> 468.25
- `[DRAK_Buccaneer].FuelManagement.FuelUsagePerSecond.Main`: 784.663 -> 1440.213
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Rear_Bot_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Top_Front_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Top_Front_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Front_X-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Top_Rear_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Front_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Rear_Bot_X-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Rear_Top_X-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Rear_Top_X+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Rear_Bot_X+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Bot_Front_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Front_X+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Main_Bot_Rear_Z+`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Main_Top_Rear_Z-`: 9150.0 -> <absent>
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Rear_Bot_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Top_Front_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Top_Front_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Bot_Front_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Front_X+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Front_X-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Top_Rear_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Bot_Rear_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Front_Z+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Rear_Bot_X-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Rear_Top_X-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Rear_Top_X+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Left_Main_Top_Rear_Z-`: <absent> -> 9150.0
- `[DRAK_Buccaneer].Hull.ThrustersHealthPoints.Main.Man_Thruster_Right_Main_Rear_Bot_X+`: <absent> -> 9150.0
- `[DRAK_Buccaneer].FlightCharacteristics.ThrustCapacity.Maneuvering`: 8990400.0 -> 3746000.0
- `[DRAK_Buccaneer].FlightCharacteristics.ThrustCapacity.Main`: 6277304.0 -> 11521704.0
- `[DRAK_Buccaneer].BaseLoadout.PilotBurstDPS`: 0.0 -> 2760.4

### [DRAK_Caterpillar]
- `[DRAK_Caterpillar].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3271.5

### [DRAK_Caterpillar_Pirate]
- `[DRAK_Caterpillar_Pirate].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3271.5

### [DRAK_Caterpillar_ShipShowdown]
- `[DRAK_Caterpillar_ShipShowdown].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3271.5

### [DRAK_Clipper]
- `[DRAK_Clipper].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top": 9100.0, "thruster_main_bottom": 9100.0, "thruster_main_aux_right": 9100.0, "thruster_main_aux_left_top": 9100.0, "thruster_main_aux_left_bottom": 9100.0}, "Retro": {"thruster_retro_right": …
- `[DRAK_Clipper].BaseLoadout.PilotBurstDPS`: 0.0 -> 2106.8
- `[DRAK_Clipper].BaseLoadout.TotalShieldHP`: 0.0 -> 4320.0

### [DRAK_Corsair]
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"retro_thruster_a_left": 30000.0, "retro_thruster_b_left": 30000.0, "retro_thruster_c_left": 30000.0, "retro_thruster_a_right": 30000.0, "retro_thruster_b_right": 30000.0, "retro_thruster_c_right": 30000.0}
- `[DRAK_Corsair].Hull.ThrustersHealthPoints.Main`: <absent> -> {"main_thruster_a_left": 24000.0, "main_thruster_b_left": 24000.0, "main_thruster_c_left": 24000.0, "main_thruster_a_right": 24000.0, "main_thruster_b_right": 24000.0, "main_thruster_c_right": 24000.0}
- `[DRAK_Corsair].BaseLoadout.PilotBurstDPS`: 0.0 -> 7174.4
- `[DRAK_Corsair].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1968.3
- `[DRAK_Corsair].BaseLoadout.TotalShieldHP`: 0.0 -> 100000.0

### [DRAK_Corsair_Exec_Military]
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"retro_thruster_a_left": 30000.0, "retro_thruster_b_left": 30000.0, "retro_thruster_c_left": 30000.0, "retro_thruster_a_right": 30000.0, "retro_thruster_b_right": 30000.0, "retro_thruster_c_right": 30000.0}
- `[DRAK_Corsair_Exec_Military].Hull.ThrustersHealthPoints.Main`: <absent> -> {"main_thruster_a_left": 24000.0, "main_thruster_b_left": 24000.0, "main_thruster_c_left": 24000.0, "main_thruster_a_right": 24000.0, "main_thruster_b_right": 24000.0, "main_thruster_c_right": 24000.0}
- `[DRAK_Corsair_Exec_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 7174.4
- `[DRAK_Corsair_Exec_Military].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2261.7
- `[DRAK_Corsair_Exec_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 105600.0

### [DRAK_Corsair_Exec_StealthIndustrial]
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_left_top_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nose_right_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_nacelle_left_bottom`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_tail_right_top`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Maneuvering.thruster_mav_body_left_bottom_side`: <absent> -> 30000.0
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"retro_thruster_a_left": 30000.0, "retro_thruster_b_left": 30000.0, "retro_thruster_c_left": 30000.0, "retro_thruster_a_right": 30000.0, "retro_thruster_b_right": 30000.0, "retro_thruster_c_right": 30000.0}
- `[DRAK_Corsair_Exec_StealthIndustrial].Hull.ThrustersHealthPoints.Main`: <absent> -> {"main_thruster_a_left": 24000.0, "main_thruster_b_left": 24000.0, "main_thruster_c_left": 24000.0, "main_thruster_a_right": 24000.0, "main_thruster_b_right": 24000.0, "main_thruster_c_right": 24000.0}
- `[DRAK_Corsair_Exec_StealthIndustrial].BaseLoadout.PilotBurstDPS`: 0.0 -> 7174.4
- `[DRAK_Corsair_Exec_StealthIndustrial].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2115.0
- `[DRAK_Corsair_Exec_StealthIndustrial].BaseLoadout.TotalShieldHP`: 0.0 -> 72000.0

### [DRAK_Cutlass_Black]
- `[DRAK_Cutlass_Black].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…
- `[DRAK_Cutlass_Black].BaseLoadout.PilotBurstDPS`: 0.0 -> 2104.6
- `[DRAK_Cutlass_Black].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[DRAK_Cutlass_Black].BaseLoadout.TotalShieldHP`: 0.0 -> 7200.0

### [DRAK_Cutlass_Black_Exec_Military]
- `[DRAK_Cutlass_Black_Exec_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black_Exec_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…
- `[DRAK_Cutlass_Black_Exec_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 2850.0
- `[DRAK_Cutlass_Black_Exec_Military].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[DRAK_Cutlass_Black_Exec_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [DRAK_Cutlass_Black_Exec_Stealth]
- `[DRAK_Cutlass_Black_Exec_Stealth].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black_Exec_Stealth].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…
- `[DRAK_Cutlass_Black_Exec_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 2850.0
- `[DRAK_Cutlass_Black_Exec_Stealth].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[DRAK_Cutlass_Black_Exec_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 7480.0

### [DRAK_Cutlass_Black_ShipShowdown]
- `[DRAK_Cutlass_Black_ShipShowdown].Hull.DoorsHealthPoints`: <absent> -> {"door_right": 2000.0, "door_left": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Black_ShipShowdown].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…
- `[DRAK_Cutlass_Black_ShipShowdown].BaseLoadout.PilotBurstDPS`: 0.0 -> 2104.6
- `[DRAK_Cutlass_Black_ShipShowdown].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[DRAK_Cutlass_Black_ShipShowdown].BaseLoadout.TotalShieldHP`: 0.0 -> 7200.0

### [DRAK_Cutlass_Blue]
- `[DRAK_Cutlass_Blue].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 4600.0}
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Tail`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}
- `[DRAK_Cutlass_Blue].Hull.ThrustersHealthPoints.Main`: <absent> -> {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}
- `[DRAK_Cutlass_Blue].BaseLoadout.PilotBurstDPS`: 0.0 -> 1013.3
- `[DRAK_Cutlass_Blue].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[DRAK_Cutlass_Blue].BaseLoadout.TotalShieldHP`: 0.0 -> 7200.0

### [DRAK_Cutlass_Red]
- `[DRAK_Cutlass_Red].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 4600.0}
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Tail`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Wing_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Center_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Outer_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Center`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Rear_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Left_Front`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Front_Bot`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Outer_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Maneuvering.Man_Thruster_Right_Wing_Top`: <absent> -> 10240.0
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}
- `[DRAK_Cutlass_Red].Hull.ThrustersHealthPoints.Main`: <absent> -> {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}
- `[DRAK_Cutlass_Red].BaseLoadout.PilotBurstDPS`: 0.0 -> 2104.6
- `[DRAK_Cutlass_Red].BaseLoadout.TotalShieldHP`: 0.0 -> 7200.0

### [DRAK_Cutlass_Steel]
- `[DRAK_Cutlass_Steel].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 2000.0, "door_right": 2000.0, "door_rear": 4600.0}
- `[DRAK_Cutlass_Steel].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 11500.0, "Main_Thruster_Left": 11500.0}, "Retro": {"Main_Retro_Right": 12340.0, "Main_Retro_Left": 12340.0}, "Maneuvering": {"Man_Thruster_Center_Bot": 10240.0, "Man_Thruster_Center_Top":…
- `[DRAK_Cutlass_Steel].BaseLoadout.PilotBurstDPS`: 0.0 -> 2104.6
- `[DRAK_Cutlass_Steel].BaseLoadout.TurretsBurstDPS`: 1008.0 -> 2755.3
- `[DRAK_Cutlass_Steel].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [DRAK_Cutter]
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 9000.0
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 9000.0
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0}
- `[DRAK_Cutter].Hull.ThrustersHealthPoints.Main`: {"thruster_aux_left": 9000.0, "thruster_aux_right": 9000.0, "thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0} -> <absent>
- `[DRAK_Cutter].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [DRAK_Cutter_Rambler]
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 9000.0
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 9000.0
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0}
- `[DRAK_Cutter_Rambler].Hull.ThrustersHealthPoints.Main`: {"thruster_aux_left": 9000.0, "thruster_aux_right": 9000.0, "thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0} -> <absent>
- `[DRAK_Cutter_Rambler].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [DRAK_Cutter_Scout]
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 9000.0
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 9000.0
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0}
- `[DRAK_Cutter_Scout].Hull.ThrustersHealthPoints.Main`: {"thruster_aux_left": 9000.0, "thruster_aux_right": 9000.0, "thruster_main_vtol_left": 9000.0, "thruster_main_vtol_right": 9000.0} -> <absent>
- `[DRAK_Cutter_Scout].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [DRAK_Golem]
- `[DRAK_Golem].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…
- `[DRAK_Golem].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[DRAK_Golem].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [DRAK_Golem_Collector_Indust]
- `[DRAK_Golem_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…
- `[DRAK_Golem_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 506.0
- `[DRAK_Golem_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [DRAK_Golem_OX]
- `[DRAK_Golem_OX].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…
- `[DRAK_Golem_OX].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[DRAK_Golem_OX].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [DRAK_Golem_Teach]
- `[DRAK_Golem_Teach].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"rear_main_thruster_left": 2800.0, "rear_main_thruster_right": 2800.0}, "Retro": {"retro_front_left": 1800.0, "retro_front_right": 1800.0}, "Maneuvering": {"mav_front_bottom_left": 1050.0, "mav_front_bottom_rig…
- `[DRAK_Golem_Teach].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[DRAK_Golem_Teach].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [DRAK_Herald]
- `[DRAK_Herald].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top": 18500.0, "thruster_main_bottom": 18500.0}, "Retro": {"thruster_front_right_front": 17500.0, "thruster_front_left_front": 17500.0}, "Maneuvering": {"thruster_front_left_top": 16500.0, "thrus…
- `[DRAK_Herald].BaseLoadout.PilotBurstDPS`: 0.0 -> 1162.8
- `[DRAK_Herald].BaseLoadout.TotalShieldHP`: 0.0 -> 4488.0

### [DRAK_Ironclad]
- `[DRAK_Ironclad].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 43000.0, "thruster_main_top_middle": 43000.0, "thruster_main_top_right": 43000.0, "thruster_main_bottom_left": 43000.0, "thruster_main_bottom_middle": 43000.0, "thruster_main_bottom_ri…
- `[DRAK_Ironclad].BaseLoadout.TurretsBurstDPS`: 0.0 -> 8522.3
- `[DRAK_Ironclad].BaseLoadout.TotalShieldHP`: 0.0 -> 288000.0

### [DRAK_Ironclad_Assault]
- `[DRAK_Ironclad_Assault].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_left": 43000.0, "thruster_main_top_middle": 43000.0, "thruster_main_top_right": 43000.0, "thruster_main_bottom_left": 43000.0, "thruster_main_bottom_middle": 43000.0, "thruster_main_bottom_ri…
- `[DRAK_Ironclad_Assault].BaseLoadout.TurretsBurstDPS`: 0.0 -> 19067.3
- `[DRAK_Ironclad_Assault].BaseLoadout.TotalShieldHP`: 0.0 -> 288000.0

### [DRAK_Pitbull]
- `[DRAK_Pitbull].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main": 700.0}, "Retro": {"thruster_retro_left": 300.0, "thruster_retro_right": 300.0}, "Maneuvering": {"thruster_mav_FTL": 300.0, "thruster_mav_RTL": 300.0, "thruster_mav_RSL": 300.0, "thruster_mav_FB…
- `[DRAK_Pitbull].BaseLoadout.PilotBurstDPS`: 0.0 -> 1530.9
- `[DRAK_Pitbull].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [DRAK_Vulture]
- `[DRAK_Vulture].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [DRAK_Vulture_Teach]
- `[DRAK_Vulture_Teach].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [ESPR_Prowler]
- `[ESPR_Prowler].BaseLoadout.PilotBurstDPS`: 0.0 -> 3414.0
- `[ESPR_Prowler].BaseLoadout.TurretsBurstDPS`: 0.0 -> 923.4
- `[ESPR_Prowler].BaseLoadout.TotalShieldHP`: 14960.0 -> 29920.0

### [ESPR_Prowler_Utility]
- `[ESPR_Prowler_Utility].BaseLoadout.PilotBurstDPS`: 0.0 -> 1385.1
- `[ESPR_Prowler_Utility].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1518.0
- `[ESPR_Prowler_Utility].BaseLoadout.TotalShieldHP`: 14960.0 -> 29920.0

### [ESPR_Prowler_Utility_Collector_Indust]
- `[ESPR_Prowler_Utility_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 1639.4
- `[ESPR_Prowler_Utility_Collector_Indust].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1518.0
- `[ESPR_Prowler_Utility_Collector_Indust].BaseLoadout.TotalShieldHP`: 14400.0 -> 28800.0

### [ESPR_Talon]
- `[ESPR_Talon].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_left`: 4000.0 -> <absent>
- `[ESPR_Talon].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_right`: 4000.0 -> <absent>
- `[ESPR_Talon].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_bottom_right": 4000.0, "thruster_bottom_left": 4000.0}
- `[ESPR_Talon].BaseLoadout.PilotBurstDPS`: 0.0 -> 1385.1

### [ESPR_Talon_Shrike]
- `[ESPR_Talon_Shrike].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_left`: 4000.0 -> <absent>
- `[ESPR_Talon_Shrike].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_right`: 4000.0 -> <absent>
- `[ESPR_Talon_Shrike].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_bottom_right": 4000.0, "thruster_bottom_left": 4000.0}
- `[ESPR_Talon_Shrike].BaseLoadout.PilotBurstDPS`: 0.0 -> 617.0

### [GAMA_Railen]
- `[GAMA_Railen].Hull.DoorsHealthPoints`: <absent> -> {"door_rear_airlock": 11400.0, "door_front": 11400.0}
- `[GAMA_Railen].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_wing_top_left": 8000.0, "thruster_main_wing_top_right": 8000.0, "thruster_main_wing_bottom_left": 8000.0, "thruster_main_wing_bottom_right": 8000.0, "thruster_aux_main_top": 8000.0, "thruster_aux…
- `[GAMA_Railen].BaseLoadout.PilotBurstDPS`: 0.0 -> 3271.5
- `[GAMA_Railen].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3271.5
- `[GAMA_Railen].BaseLoadout.TotalShieldHP`: 0.0 -> 144000.0

### [GAMA_Syulen]
- `[GAMA_Syulen].BaseLoadout.PilotBurstDPS`: 0.0 -> 1636.9

### [GAMA_Syulen_Exec_Military]
- `[GAMA_Syulen_Exec_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 2137.5
- `[GAMA_Syulen_Exec_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [GAMA_Syulen_Exec_Stealth]
- `[GAMA_Syulen_Exec_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 1970.6
- `[GAMA_Syulen_Exec_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 4488.0

### [GAMA_Tyilui]
- `[GAMA_Tyilui].Hull.DoorsHealthPoints`: <absent> -> {"door_front": 12600.0, "door_rear": 12600.0}
- `[GAMA_Tyilui].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_wing_top_left": 8000.0, "thruster_main_wing_top_right": 8000.0, "thruster_main_wing_bottom_left": 8000.0, "thruster_main_wing_bottom_right": 8000.0, "thruster_aux_main_top": 8000.0, "thruster_aux…
- `[GAMA_Tyilui].BaseLoadout.PilotBurstDPS`: 0.0 -> 3271.5
- `[GAMA_Tyilui].BaseLoadout.TurretsBurstDPS`: 0.0 -> 5454.0
- `[GAMA_Tyilui].BaseLoadout.TotalShieldHP`: 0.0 -> 144000.0

### [GLSN_Shiv]
- `[GLSN_Shiv].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 3500.0}
- `[GLSN_Shiv].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"Main_Thruster_Right": 7500.0, "Main_Thruster_Left": 7500.0, "Main_Thruster_Side_Right": 7500.0, "Main_Thruster_Side_Left": 7500.0}, "Retro": {"Main_Retro_Right": 5000.0, "Main_Retro_Left": 5000.0}, "Maneuverin…
- `[GLSN_Shiv].BaseLoadout.PilotBurstDPS`: 0.0 -> 1906.7
- `[GLSN_Shiv].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1975.0
- `[GLSN_Shiv].BaseLoadout.TotalShieldHP`: 0.0 -> 7200.0

### [GRIN_MDC]
- `[GRIN_MDC].BaseLoadout.TotalShieldHP`: 0.0 -> 720.0

### [GRIN_MTC]
- `[GRIN_MTC].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[GRIN_MTC].BaseLoadout.TotalShieldHP`: 0.0 -> 720.0

### [KRIG_L21_Wolf]
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Maneuvering`: <absent> -> {"thruster_mav_FBL": 800.0, "thruster_mav_FBR": 800.0, "thruster_mav_FSL": 800.0, "thruster_mav_FSR": 800.0, "thruster_mav_FTL": 800.0, "thruster_mav_FTR": 800.0, "thruster_mav_MBL": 800.0, "thruster_mav_MBR": 800.0, "th…
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_retro_left": 1250.0, "thruster_retro_right": 1250.0}
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main`: <absent> -> 2000.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf].BaseLoadout.PilotBurstDPS`: 0.0 -> 1995.0
- `[KRIG_L21_Wolf].BaseLoadout.TotalShieldHP`: 0.0 -> 4320.0

### [KRIG_L21_Wolf_Collector_Military]
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Maneuvering`: <absent> -> {"thruster_mav_FBL": 800.0, "thruster_mav_FBR": 800.0, "thruster_mav_FSL": 800.0, "thruster_mav_FSR": 800.0, "thruster_mav_FTL": 800.0, "thruster_mav_FTR": 800.0, "thruster_mav_MBL": 800.0, "thruster_mav_MBR": 800.0, "th…
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_retro_left": 1250.0, "thruster_retro_right": 1250.0}
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main`: <absent> -> 2000.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 1995.0
- `[KRIG_L21_Wolf_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [KRIG_L21_Wolf_Collector_Stealth]
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Maneuvering`: <absent> -> {"thruster_mav_FBL": 800.0, "thruster_mav_FBR": 800.0, "thruster_mav_FSL": 800.0, "thruster_mav_FSR": 800.0, "thruster_mav_FTL": 800.0, "thruster_mav_FTR": 800.0, "thruster_mav_MBL": 800.0, "thruster_mav_MBR": 800.0, "th…
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_retro_left": 1250.0, "thruster_retro_right": 1250.0}
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main`: <absent> -> 2000.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_left_outer`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].Hull.ThrustersHealthPoints.Main.thruster_main_wing_right_inner`: <absent> -> 1250.0
- `[KRIG_L21_Wolf_Collector_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 1995.0
- `[KRIG_L21_Wolf_Collector_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 4488.0

### [KRIG_L22_AlphaWolf]
- `[KRIG_L22_AlphaWolf].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main": 2000.0, "thruster_main_wing_left_inner": 1250.0, "thruster_main_wing_left_outer": 1250.0, "thruster_main_wing_right_inner": 1250.0, "thruster_main_wing_right_outer": 1250.0, "main_thruster_pipe…
- `[KRIG_L22_AlphaWolf].BaseLoadout.PilotBurstDPS`: 0.0 -> 2125.0
- `[KRIG_L22_AlphaWolf].BaseLoadout.TotalShieldHP`: 0.0 -> 4320.0

### [KRIG_L22_AlphaWolf_Collector_Military]
- `[KRIG_L22_AlphaWolf_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main": 2000.0, "thruster_main_wing_left_inner": 1250.0, "thruster_main_wing_left_outer": 1250.0, "thruster_main_wing_right_inner": 1250.0, "thruster_main_wing_right_outer": 1250.0, "main_thruster_pipe…
- `[KRIG_L22_AlphaWolf_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 2125.0
- `[KRIG_L22_AlphaWolf_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [KRIG_P52_Merlin]
- `[KRIG_P52_Merlin].BaseLoadout.PilotBurstDPS`: 0.0 -> 887.4

### [KRIG_P72_Archimedes]
- `[KRIG_P72_Archimedes].BaseLoadout.PilotBurstDPS`: 0.0 -> 874.8

### [KRIG_P72_Archimedes_Emerald]
- `[KRIG_P72_Archimedes_Emerald].BaseLoadout.PilotBurstDPS`: 0.0 -> 874.8

### [MISC_Fortune]
- `[MISC_Fortune].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}
- `[MISC_Fortune].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_middle": 11400.0, "thruster_main_rear_right": 11400.0, "thruster_main_rear_left": 11400.0, "thruster_main_front_right": 11400.0, "thruster_main_front_left": 11400.0}, "Retro": {"thruster_ret…
- `[MISC_Fortune].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[MISC_Fortune].BaseLoadout.TotalShieldHP`: 0.0 -> 6480.0

### [MISC_Fortune_Collector_Industrial]
- `[MISC_Fortune_Collector_Industrial].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}
- `[MISC_Fortune_Collector_Industrial].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_middle": 11400.0, "thruster_main_rear_right": 11400.0, "thruster_main_rear_left": 11400.0, "thruster_main_front_right": 11400.0, "thruster_main_front_left": 11400.0}, "Retro": {"thruster_ret…
- `[MISC_Fortune_Collector_Industrial].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[MISC_Fortune_Collector_Industrial].BaseLoadout.TotalShieldHP`: 0.0 -> 9000.0

### [MISC_Fortune_Teach]
- `[MISC_Fortune_Teach].Hull.DoorsHealthPoints`: <absent> -> {"door_rear": 400.0}
- `[MISC_Fortune_Teach].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_rear_middle": 11400.0, "thruster_main_rear_right": 11400.0, "thruster_main_rear_left": 11400.0, "thruster_main_front_right": 11400.0, "thruster_main_front_left": 11400.0}, "Retro": {"thruster_ret…
- `[MISC_Fortune_Teach].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[MISC_Fortune_Teach].BaseLoadout.TotalShieldHP`: 0.0 -> 6480.0

### [MISC_Freelancer]
- `[MISC_Freelancer].BaseLoadout.PilotBurstDPS`: 0.0 -> 2734.6

### [MISC_Freelancer_DUR]
- `[MISC_Freelancer_DUR].BaseLoadout.PilotBurstDPS`: 0.0 -> 2006.7

### [MISC_Freelancer_MAX]
- `[MISC_Freelancer_MAX].BaseLoadout.PilotBurstDPS`: 0.0 -> 2187.0

### [MISC_Freelancer_MIS]
- `[MISC_Freelancer_MIS].BaseLoadout.PilotBurstDPS`: 0.0 -> 2734.6

### [MISC_Fury]
- `[MISC_Fury].BaseLoadout.PilotBurstDPS`: 0.0 -> 1312.2

### [MISC_Hull_A]
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_right`: <absent> -> 7400.0
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux_left`: <absent> -> 7400.0
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_rear_left": 6500.0, "thruster_vtol_rear_right": 6500.0, "thruster_vtol_front_left": 6500.0, "thruster_vtol_front_right": 6500.0}
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_front_left`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_rear_left`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_front_right`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Retro.thruster_vtol_rear_right`: 6500.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Main.thruster_aux_right`: 7400.0 -> <absent>
- `[MISC_Hull_A].Hull.ThrustersHealthPoints.Main.thruster_aux_left`: 7400.0 -> <absent>
- `[MISC_Hull_A].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [MISC_Hull_B]
- `[MISC_Hull_B].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 12000.0, "thruster_main_left_lower": 10500.0, "thruster_main_left_upper": 10500.0, "thruster_main_right": 12000.0, "thruster_main_right_lower": 10500.0, "thruster_main_right_upper": 10500.…
- `[MISC_Hull_B].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2
- `[MISC_Hull_B].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[MISC_Hull_B].BaseLoadout.TotalShieldHP`: 0.0 -> 28800.0

### [MISC_Hull_C]
- `[MISC_Hull_C].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2
- `[MISC_Hull_C].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [MISC_Prospector]
- `[MISC_Prospector].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [MISC_Prospector_Collector_Indust]
- `[MISC_Prospector_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 633.0

### [MISC_Razor]
- `[MISC_Razor].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_left": 5670.0, "engine_right": 5670.0}, "Retro": {"thruster_retro_left": 5000.0, "thruster_retro_right": 5000.0}, "Maneuvering": {"thruster_FL_top": 4560.0, "thruster_FL_side": 4560.0, "thruster_FL_bott…
- `[MISC_Razor].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[MISC_Razor].BaseLoadout.TotalShieldHP`: 0.0 -> 1920.0

### [MISC_Razor_EX]
- `[MISC_Razor_EX].BaseLoadout.PilotBurstDPS`: 0.0 -> 1120.0
- `[MISC_Razor_EX].BaseLoadout.TotalShieldHP`: 0.0 -> 1920.0

### [MISC_Razor_LX]
- `[MISC_Razor_LX].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[MISC_Razor_LX].BaseLoadout.TotalShieldHP`: 0.0 -> 1920.0

### [MISC_Reliant]
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Reliant_Mako]
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant_Mako].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Reliant_Sen]
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant_Sen].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Reliant_Tana]
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_ULF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_URB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_URF`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LRB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Maneuvering.thruster_LLB`: 6250.0 -> <absent>
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"thruster_LLF": 6250.0, "thruster_LRF": 6250.0, "thruster_ULF": 6250.0, "thruster_URF": 6250.0}
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_ULB`: <absent> -> 6250.0
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_LRB`: <absent> -> 6250.0
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_LLB`: <absent> -> 6250.0
- `[MISC_Reliant_Tana].Hull.ThrustersHealthPoints.Main.thruster_URB`: <absent> -> 6250.0

### [MISC_Starfarer]
- `[MISC_Starfarer].BaseLoadout.PilotBurstDPS`: 0.0 -> 4101.8
- `[MISC_Starfarer].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3818.2

### [MISC_Starfarer_Gemini]
- `[MISC_Starfarer_Gemini].BaseLoadout.PilotBurstDPS`: 0.0 -> 4101.8
- `[MISC_Starfarer_Gemini].BaseLoadout.TurretsBurstDPS`: 0.0 -> 4637.2

### [MISC_Starfarer_Teach]
- `[MISC_Starfarer_Teach].BaseLoadout.PilotBurstDPS`: 0.0 -> 4101.8
- `[MISC_Starfarer_Teach].BaseLoadout.TurretsBurstDPS`: 0.0 -> 3818.2

### [MISC_Starlancer_Max]
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0, "thruster_vtol_SL": 2000.0, "thruster_vtol_SR": 2000.0}
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_SR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_SL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlancer_Max_Collector_Indust]
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0, "thruster_vtol_SL": 2000.0, "thruster_vtol_SR": 2000.0}
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_SR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_SL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>
- `[MISC_Starlancer_Max_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 72000.0

### [MISC_Starlancer_TAC]
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0}
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlancer_TAC_Collector_Military]
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_vtol_FR": 2000.0, "thruster_vtol_FL": 2000.0, "thruster_vtol_RR": 2000.0, "thruster_vtol_RL": 2000.0}
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_RR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_RL`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_FR`: 2000.0 -> <absent>
- `[MISC_Starlancer_TAC_Collector_Military].Hull.ThrustersHealthPoints.Main.thruster_vtol_FL`: 2000.0 -> <absent>

### [MISC_Starlite]
- `[MISC_Starlite].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_right": 11500.0, "thruster_main_left": 11500.0, "thruster_main_bottom_right": 11500.0, "thruster_main_bottom_left": 11500.0}, "Retro": {"thruster_retro_right": 10500.0, "thruster_retro_left": 105…
- `[MISC_Starlite].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1
- `[MISC_Starlite].BaseLoadout.TurretsBurstDPS`: 0.0 -> 656.1
- `[MISC_Starlite].BaseLoadout.TotalShieldHP`: 0.0 -> 4320.0

### [MRAI_Guardian]
- `[MRAI_Guardian].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…
- `[MRAI_Guardian].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[MRAI_Guardian].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [MRAI_Guardian_MX]
- `[MRAI_Guardian_MX].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…
- `[MRAI_Guardian_MX].BaseLoadout.PilotBurstDPS`: 0.0 -> 3271.5
- `[MRAI_Guardian_MX].BaseLoadout.TotalShieldHP`: 0.0 -> 21120.0

### [MRAI_Guardian_MX_Collector_Military]
- `[MRAI_Guardian_MX_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…
- `[MRAI_Guardian_MX_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 2333.3
- `[MRAI_Guardian_MX_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 21120.0

### [MRAI_Guardian_Military]
- `[MRAI_Guardian_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…
- `[MRAI_Guardian_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[MRAI_Guardian_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [MRAI_Guardian_QI]
- `[MRAI_Guardian_QI].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…
- `[MRAI_Guardian_QI].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[MRAI_Guardian_QI].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

### [MRAI_Guardian_QI_Collector_Indust]
- `[MRAI_Guardian_QI_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 5000.0, "thruster_main_right": 5000.0}, "Retro": {"thruster_retro_top_left": 2200.0, "thruster_retro_top_right": 2200.0, "thruster_retro_bottom_left": 2200.0, "thruster_retro_bottom_right"…
- `[MRAI_Guardian_QI_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 3072.6
- `[MRAI_Guardian_QI_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 6400.0

### [MRAI_Pulse_LX]
- `[MRAI_Pulse_LX].Hull.ThrustersHealthPoints.Maneuvering.thruster_aux`: <absent> -> 2750.0
- `[MRAI_Pulse_LX].Hull.ThrustersHealthPoints.Main.thruster_aux`: 2750.0 -> <absent>

### [ORIG_100i]
- `[ORIG_100i].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2

### [ORIG_125a]
- `[ORIG_125a].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2

### [ORIG_135c]
- `[ORIG_135c].BaseLoadout.PilotBurstDPS`: 0.0 -> 1091.2

### [ORIG_300i]
- `[ORIG_300i].BaseLoadout.PilotBurstDPS`: 0.0 -> 2033.6

### [ORIG_315p]
- `[ORIG_315p].BaseLoadout.PilotBurstDPS`: 0.0 -> 1350.0

### [ORIG_325a]
- `[ORIG_325a].BaseLoadout.PilotBurstDPS`: 0.0 -> 2375.5

### [ORIG_350r]
- `[ORIG_350r].BaseLoadout.PilotBurstDPS`: 0.0 -> 1774.9

### [ORIG_400i]
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_rear_right`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_front_right`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_front_left`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.Maneuvering.thruster_bottom_rear_left`: 16000.0 -> <absent>
- `[ORIG_400i].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"thruster_bottom_front_left": 16000.0, "thruster_bottom_front_right": 16000.0, "thruster_bottom_rear_left": 16000.0, "thruster_bottom_rear_right": 16000.0}
- `[ORIG_400i].BaseLoadout.PilotBurstDPS`: 0.0 -> 1635.8
- `[ORIG_400i].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [ORIG_600i]
- `[ORIG_600i].BaseLoadout.PilotBurstDPS`: 0.0 -> 4608.9
- `[ORIG_600i].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [ORIG_600i_Executive_Edition]
- `[ORIG_600i_Executive_Edition].BaseLoadout.PilotBurstDPS`: 0.0 -> 4608.9
- `[ORIG_600i_Executive_Edition].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [ORIG_600i_Touring]
- `[ORIG_600i_Touring].BaseLoadout.PilotBurstDPS`: 0.0 -> 4608.9
- `[ORIG_600i_Touring].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [ORIG_85X]
- `[ORIG_85X].BaseLoadout.PilotBurstDPS`: 656.1 -> 1093.5

### [ORIG_890Jump]
- `[ORIG_890Jump].BaseLoadout.TurretsBurstDPS`: 1166.7 -> 7451.0

### [ORIG_m50]
- `[ORIG_m50].BaseLoadout.PilotBurstDPS`: 0.0 -> 656.1

### [ORIG_m80]
- `[ORIG_m80].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 8000.0, "thruster_main_middle": 8000.0, "thruster_main_right": 8000.0}, "Retro": {"thruster_retro_left": 6500.0, "thruster_retro_right": 6500.0, "thruster_retro_underleft": 6500.0, "thrust…
- `[ORIG_m80].BaseLoadout.PilotBurstDPS`: 0.0 -> 4090.5
- `[ORIG_m80].BaseLoadout.TotalShieldHP`: 0.0 -> 20000.0

### [RSI_Apollo_Medivac]
- `[RSI_Apollo_Medivac].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Apollo_Medivac].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…
- `[RSI_Apollo_Medivac].BaseLoadout.PilotBurstDPS`: 0.0 -> 1635.8
- `[RSI_Apollo_Medivac].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1013.3
- `[RSI_Apollo_Medivac].BaseLoadout.TotalShieldHP`: 0.0 -> 28800.0

### [RSI_Apollo_Triage]
- `[RSI_Apollo_Triage].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Apollo_Triage].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…
- `[RSI_Apollo_Triage].BaseLoadout.PilotBurstDPS`: 0.0 -> 1635.8
- `[RSI_Apollo_Triage].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1367.3
- `[RSI_Apollo_Triage].BaseLoadout.TotalShieldHP`: 0.0 -> 28800.0

### [RSI_Apollo_Triage_Collector_Stealth]
- `[RSI_Apollo_Triage_Collector_Stealth].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Apollo_Triage_Collector_Stealth].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…
- `[RSI_Apollo_Triage_Collector_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 1166.7
- `[RSI_Apollo_Triage_Collector_Stealth].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1367.3
- `[RSI_Apollo_Triage_Collector_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 29920.0

### [RSI_Aurora_GS_CL]
- `[RSI_Aurora_GS_CL].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_CL].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_CL].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}
- `[RSI_Aurora_GS_CL].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [RSI_Aurora_GS_ES]
- `[RSI_Aurora_GS_ES].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_ES].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_ES].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}
- `[RSI_Aurora_GS_ES].BaseLoadout.PilotBurstDPS`: 0.0 -> 405.0

### [RSI_Aurora_GS_LN]
- `[RSI_Aurora_GS_LN].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_LN].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_LN].BaseLoadout.PilotBurstDPS`: 0.0 -> 874.8

### [RSI_Aurora_GS_LX]
- `[RSI_Aurora_GS_LX].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_LX].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_LX].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}
- `[RSI_Aurora_GS_LX].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [RSI_Aurora_GS_MR]
- `[RSI_Aurora_GS_MR].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_MR].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_MR].Hull.ThrustersHealthPoints.Retro`: <absent> -> {"Retro_Thruster_Left": 8000.0, "Retro_Thruster_Right": 8000.0}
- `[RSI_Aurora_GS_MR].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [RSI_Aurora_GS_SE]
- `[RSI_Aurora_GS_SE].Hull.DoorsHealthPoints`: <absent> -> {"door_left": 1000.0, "door_right": 1000.0}
- `[RSI_Aurora_GS_SE].Hull.ThrustersHealthPoints.VTOL`: <absent> -> {"fan_left_rear": 8750.0, "fan_left_front": 8750.0, "fan_right_rear": 8750.0, "fan_right_front": 8750.0}
- `[RSI_Aurora_GS_SE].BaseLoadout.PilotBurstDPS`: 0.0 -> 874.8

### [RSI_Aurora_Mk2]
- `[RSI_Aurora_Mk2].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 2500.0, "thruster_main_right": 2500.0}, "Retro": {"thruster_retro_right": 1500.0, "thruster_retro_left": 1500.0}, "Maneuvering": {"thruster_mav_nose_top_left": 600.0, "thruster_mav_nose_le…
- `[RSI_Aurora_Mk2].BaseLoadout.PilotBurstDPS`: 0.0 -> 1312.2
- `[RSI_Aurora_Mk2].BaseLoadout.TotalShieldHP`: 0.0 -> 6000.0

### [RSI_Constellation_Andromeda]
- `[RSI_Constellation_Andromeda].Hull.DoorsHealthPoints.door_elevator`: <absent> -> 4000.0
- `[RSI_Constellation_Andromeda].Hull.DoorsHealthPoints.door_airlock_neck_top`: <absent> -> 6000.0
- `[RSI_Constellation_Andromeda].BaseLoadout.PilotBurstDPS`: 0.0 -> 4909.5

### [RSI_Constellation_Aquila]
- `[RSI_Constellation_Aquila].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_body_left": 6000.0, "door_airlock_body_right": 6000.0, "door_airlock_neck_top": 6000.0}
- `[RSI_Constellation_Aquila].BaseLoadout.PilotBurstDPS`: 0.0 -> 6145.2

### [RSI_Constellation_Phoenix]
- `[RSI_Constellation_Phoenix].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_neck_top": 6000.0}
- `[RSI_Constellation_Phoenix].BaseLoadout.PilotBurstDPS`: 0.0 -> 4921.6

### [RSI_Constellation_Phoenix_Emerald]
- `[RSI_Constellation_Phoenix_Emerald].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_neck_top": 6000.0}
- `[RSI_Constellation_Phoenix_Emerald].BaseLoadout.PilotBurstDPS`: 0.0 -> 4921.6

### [RSI_Constellation_Taurus]
- `[RSI_Constellation_Taurus].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_body_left": 6000.0, "door_airlock_body_right": 6000.0, "door_airlock_neck_top": 6000.0}
- `[RSI_Constellation_Taurus].BaseLoadout.PilotBurstDPS`: 0.0 -> 4909.5

### [RSI_Constellation_Taurus_Military]
- `[RSI_Constellation_Taurus_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 4000.0, "door_airlock_body_left": 6000.0, "door_airlock_body_right": 6000.0, "door_airlock_neck_top": 6000.0}
- `[RSI_Constellation_Taurus_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 4909.5
- `[RSI_Constellation_Taurus_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 105600.0

### [RSI_Hermes]
- `[RSI_Hermes].Hull.DoorsHealthPoints`: <absent> -> {"door_elevator": 6000.0}
- `[RSI_Hermes].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 6000.0, "thruster_main_right": 6000.0, "thruster_main_nacelle_left": 6000.0, "thruster_main_nacelle_right": 6000.0}, "Retro": {"thruster_retro_left": 6000.0, "thruster_retro_right": 6000.0…
- `[RSI_Hermes].BaseLoadout.PilotBurstDPS`: 0.0 -> 1635.8
- `[RSI_Hermes].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1635.8
- `[RSI_Hermes].BaseLoadout.TotalShieldHP`: 0.0 -> 28800.0

### [RSI_Lynx]
- `[RSI_Lynx].BaseLoadout.PilotBurstDPS`: 0.0 -> 607.5

### [RSI_Mantis]
- `[RSI_Mantis].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Mantis].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…
- `[RSI_Mantis].BaseLoadout.PilotBurstDPS`: 0.0 -> 923.4
- `[RSI_Mantis].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [RSI_Meteor]
- `[RSI_Meteor].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Meteor].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…
- `[RSI_Meteor].BaseLoadout.PilotBurstDPS`: 0.0 -> 4513.5
- `[RSI_Meteor].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [RSI_Meteor_Collector_Military]
- `[RSI_Meteor_Collector_Military].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Meteor_Collector_Military].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…
- `[RSI_Meteor_Collector_Military].BaseLoadout.PilotBurstDPS`: 0.0 -> 5401.2
- `[RSI_Meteor_Collector_Military].BaseLoadout.TotalShieldHP`: 0.0 -> 6336.0

### [RSI_Meteor_Collector_Stealth]
- `[RSI_Meteor_Collector_Stealth].Hull.DoorsHealthPoints`: <absent> -> {"door_lift": 1000.0}
- `[RSI_Meteor_Collector_Stealth].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_left": 7500.0, "thruster_main_right": 7500.0}, "Retro": {"thruster_retro_left": 6950.0, "thruster_retro_right": 6950.0}, "Maneuvering": {"thruster_mav_left_front_top": 6500.0, "thruster_mav_left_…
- `[RSI_Meteor_Collector_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 4853.7
- `[RSI_Meteor_Collector_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 4488.0

### [RSI_Perseus]
- `[RSI_Perseus].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_top_right": 30000.0, "thruster_main_top_left": 30000.0, "thruster_main_bottom_right": 30000.0, "thruster_main_bottom_left": 30000.0}, "Retro": {"thruster_retro_front_right_top": 5000.0, "thruster…
- `[RSI_Perseus].BaseLoadout.TurretsBurstDPS`: 1000.0 -> 23053.3
- `[RSI_Perseus].BaseLoadout.TotalShieldHP`: 0.0 -> 211200.0

### [RSI_Salvation]
- `[RSI_Salvation].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"engine_top_left": 2500.0, "engine_top_right": 2500.0, "engine_bottom_left": 2500.0, "engine_bottom_right": 2500.0}, "Retro": {"retro_bottom_left": 1700.0, "retro_bottom_right": 1700.0, "retro_top_left": 1700.0…
- `[RSI_Salvation].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[RSI_Salvation].BaseLoadout.TotalShieldHP`: 0.0 -> 4320.0

### [RSI_Scorpius]
- `[RSI_Scorpius].BaseLoadout.PilotBurstDPS`: 0.0 -> 2182.5
- `[RSI_Scorpius].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5

### [RSI_Scorpius_Antares]
- `[RSI_Scorpius_Antares].BaseLoadout.PilotBurstDPS`: 0.0 -> 2182.5

### [RSI_Scorpius_Stealth]
- `[RSI_Scorpius_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 2182.5
- `[RSI_Scorpius_Stealth].BaseLoadout.TurretsBurstDPS`: 0.0 -> 2182.5
- `[RSI_Scorpius_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 7480.0

### [RSI_Ursa_Medivac]
- `[RSI_Ursa_Medivac].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [RSI_Ursa_Medivac_Stealth]
- `[RSI_Ursa_Medivac_Stealth].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4
- `[RSI_Ursa_Medivac_Stealth].BaseLoadout.TotalShieldHP`: 0.0 -> 720.0

### [RSI_Ursa_Rover]
- `[RSI_Ursa_Rover].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [RSI_Ursa_Rover_Emerald]
- `[RSI_Ursa_Rover_Emerald].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [RSI_Zeus_CL]
- `[RSI_Zeus_CL].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…
- `[RSI_Zeus_CL].BaseLoadout.PilotBurstDPS`: 0.0 -> 1639.4
- `[RSI_Zeus_CL].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2

### [RSI_Zeus_CL_Collector_Indust]
- `[RSI_Zeus_CL_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…
- `[RSI_Zeus_CL_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 1639.4
- `[RSI_Zeus_CL_Collector_Indust].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[RSI_Zeus_CL_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 21600.0

### [RSI_Zeus_ES]
- `[RSI_Zeus_ES].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…
- `[RSI_Zeus_ES].BaseLoadout.PilotBurstDPS`: 0.0 -> 1639.4
- `[RSI_Zeus_ES].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2

### [RSI_Zeus_ES_Collector_Indust]
- `[RSI_Zeus_ES_Collector_Indust].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_bottom_left": 14350.0, "thruster_main_bottom_right": 14350.0, "thruster_main_top_left": 14350.0, "thruster_main_top_right": 14350.0}, "Retro": {"thruster_retro_left": 15250.0, "thruster_retro_rig…
- `[RSI_Zeus_ES_Collector_Indust].BaseLoadout.PilotBurstDPS`: 0.0 -> 1639.4
- `[RSI_Zeus_ES_Collector_Indust].BaseLoadout.TurretsBurstDPS`: 0.0 -> 1091.2
- `[RSI_Zeus_ES_Collector_Indust].BaseLoadout.TotalShieldHP`: 0.0 -> 28800.0

### [TMBL_Nova]
- `[TMBL_Nova].BaseLoadout.TotalShieldHP`: 0.0 -> 2160.0

### [VNCL_Blade]
- `[VNCL_Blade].BaseLoadout.PilotBurstDPS`: 0.0 -> 2665.4

### [VNCL_Glaive]
- `[VNCL_Glaive].BaseLoadout.PilotBurstDPS`: 0.0 -> 2470.5

### [VNCL_Scythe]
- `[VNCL_Scythe].BaseLoadout.PilotBurstDPS`: 0.0 -> 3550.5

### [VNCL_Stinger]
- `[VNCL_Stinger].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"thruster_main_01": 14000.0, "thruster_main_02": 14000.0, "thruster_main_03": 9000.0}, "Retro": {"thruster_retro_left": 7000.0, "thruster_retro_right": 7000.0}, "Maneuvering": {"thruster_rear_top_left": 3000.0,…
- `[VNCL_Stinger].BaseLoadout.PilotBurstDPS`: 0.0 -> 4197.1
- `[VNCL_Stinger].BaseLoadout.TotalShieldHP`: 0.0 -> 21120.0

### [XIAN_Nox]
- `[XIAN_Nox].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [XIAN_Nox_Collector_Mod]
- `[XIAN_Nox_Collector_Mod].BaseLoadout.PilotBurstDPS`: 0.0 -> 437.4

### [XIAN_Scout]
- `[XIAN_Scout].BaseLoadout.PilotBurstDPS`: 0.0 -> 1635.8

### [XNAA_SanTokYai]
- `[XNAA_SanTokYai].Hull.ThrustersHealthPoints`: <absent> -> {"Main": {"main_thruster_top_left": 15000.0, "main_thruster_top_right": 15000.0, "main_thruster_bottom_left": 15000.0, "main_thruster_bottom_right": 15000.0, "mav_thruster_backward_right": 12500.0, "mav_thruster_backward…
- `[XNAA_SanTokYai].BaseLoadout.PilotBurstDPS`: 0.0 -> 1822.5
- `[XNAA_SanTokYai].BaseLoadout.TotalShieldHP`: 0.0 -> 10560.0

