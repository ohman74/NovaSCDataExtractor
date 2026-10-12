# Weapon DPS model

How a weapon's rate of fire is derived, why the raw `fireRate` in the XML is not it,
and why there is exactly one function in the codebase allowed to answer the question.

## The single source of truth

`nova/builders/stditem.py:_firing_cadence(mode, fire_type, is_fps, shot_count)`

Returns `(rpm, burst_rpm, shot_count)` for one firing mode. Two callers:

| Caller | Uses it for |
|---|---|
| `stditem.py:_build_weapon_data` | `stdItem.Weapon.Firing[].RoundsPerMinute` / `BurstRoundsPerMinute` / `ShotPerAction` |
| `ships.py:_compute_hardpoint_dps` | `vehicle_stats.BaseLoadout.PilotBurstDPS` / `TurretsBurstDPS` |

Anything that needs a rate of fire must call this. Reading `mode["fireRate"]`
directly is the bug this function exists to prevent.

## Why `fireRate` is not the rate of fire

`SWeaponActionFireSingleParams.fireRate` is the rate limit of **one fire action**.
For a plain single-shot weapon that happens to equal the weapon's rate, which is why
reading it directly looks correct on most of the corpus. It is wrong for two families:

**Charged weapons.** The cycle is `chargeTime + max(cooldownTime, 60/fireRate)`, so the
nominal rate is never reached. Singe Cannon (S3) is authored at `fireRate=90` and
actually fires at 18.9 RPM, a factor 4.8.

**Sequence weapons.** The cadence comes from the `SWeaponSequenceEntryParams.delay`
values, not from the inner `fireRate`. See below.

## Sequence weapons

A `SWeaponActionSequenceParams` steps through `sequenceEntries`. Each entry carries its
own `weaponAction` and, crucially, **its own barrel** (`fireHelper`). This was verified
across all 135 ship sequence weapons in 4.10.190: every multi-entry sequence has one
distinct `fireHelper` per entry. So each barrel fires once per loop.

```
loop time  = sum over entries of (60 / delay)        # delay in RPM units
weapon rpm = shots per loop x 60 / loop time
```

The inner `fireRate` still constrains the result, but as a **per-barrel** limit, not a
weapon-level one. A barrel that fires once per loop needs `loop time >= 60/fireRate`,
which means:

```
weapon rpm <= n_barrels x inner fireRate
```

For a single-entry sequence `n_barrels == 1` and this reduces to the plain
`min(delay, fireRate)`, which is what such weapons have always produced.

### Worked example: Whiptail STR-E2 Repeater

Three entries, each `delay="550" unit="RPM"`, each `fireRate="180"`, barrels
`barrel_01_out` / `barrel_02_out` / `barrel_03_out`.

```
loop time  = 3 x 60/550           = 0.3273 s
sequence   = 3 x 60 / 0.3273      = 550.00 rpm
barrel cap = 3 x 180              = 540.00 rpm     <- binding
weapon     = min(550, 540)        = 540.00 rpm
dps        = 30 energy x 540 / 60 = 270.0
```

540 rather than 550 because each barrel needs 333 ms to recycle while the sequence only
gives it 327 ms. CIG authored `180` as roughly `550/3`, i.e. deliberately as the
per-barrel rate.

### Authoring is inconsistent, so the inner rate cannot be trusted as a cap

| Convention | Example | `delay` | inner `fireRate` |
|---|---|---|---|
| inner == weapon rate (majority) | KLWE laser repeaters | 750 | 750 |
| inner == per-barrel rate | Whiptail STR-E2 | 550 | 180 |
| inner far above either | Axiom L-22 | 550 | 750 |
| inner between the two | BEHR SW16BR line | 750-900 | 500 |

Treating the inner value as a weapon-level ceiling therefore understated every
multi-barrel weapon whose author picked one of the last three conventions.

## Burst vs sustained

`BurstRoundsPerMinute` is emitted only when the peak instantaneous rate inside the loop
is meaningfully higher than the sustained rate. That happens when the entry delays are
**non-uniform**: Echion Repeater runs 800/450/450, so it fires the first pair 800 RPM
apart while sustaining 526.83 RPM. A uniform sequence has burst == sustained by
definition and emits nothing.

Note that `PilotBurstDPS` uses the **sustained** rate, not `burst_rpm`. "Burst DPS" in
this dataset means damage while the trigger is held, as opposed to a sustained figure
that would additionally account for capacitor drain and overheating. It is not a
reference to burst-fire mode.

## What changed in August 2026

Two defects, fixed together.

**1. The per-barrel cap.** `capped_uniform` compared the sequence rate against the raw
inner `fireRate` instead of `n_barrels x fireRate`. Six weapons were understated:

| Weapon | before | after |
|---|---|---|
| Whiptail STR-E2 Repeater | 180 | 540 |
| SW16BR1 "Buzzsaw" Repeater | 500 | 900 |
| SW16BR2 "Sawbuck" Repeater | 500 | 825 |
| BRVS Repeater | 500 | 825 |
| SW16BR3 "Shredder" Repeater | 500 | 750 |
| Tormenter S3 Repeater | 750 | 850 |

129 of the 135 sequence weapons were unaffected, and no FPS weapon was: the rule is
gated on `not is_fps`.

**2. Two competing DPS calculations.** `ships.py:_compute_hardpoint_dps` read
`fm["fireRate"]` directly and so bypassed all of the above. 25 weapons disagreed with
their own `RoundsPerMinute` (7 understated, 18 overstated), moving `PilotBurstDPS` on
19 ships. The largest corrections:

| Ship | before | after | cause |
|---|---|---|---|
| AEGS_Idris_M | 14416.0 | 4805.3 | Destroyer Mass Driver, charged |
| BANU_Defender | 6075.0 | 1275.8 | Singe Cannon S3, charged |
| RSI_Meteor_Collector_Military | 5401.2 | 6357.0 | Leonids Cannon, sequence |
| VNCL_Scythe | 3281.7 | 2336.7 | 'WAR' Cannon, sequence |
| KRIG_S65_Stingray | 2485.0 | 2638.3 | Whiptail up, Axiom L-22 down |

The Stingray moved in both directions at once: its four S2 mounts carry Whiptails
(understated) and its two S4 mounts carry Axiom L-22 Repeaters (overstated).

## Corroboration

CIG's own item descriptions confirm the barrel counts independently of the XML:

- SW16BR1 "Buzzsaw": *"Firing from two barrels"*
- SW16BR2 "Sawbuck": *"Its sequential-firing double barrel configuration offers ... a
  higher rate of fire than a cannon"*
- SW16BR3 "Shredder": *"distributes heat across both barrels to keep it firing"*
- Whiptail STR-E2: *"a torrent of laser fire ... firing in rapid succession"*

The Sawbuck line is the clearest: it markets the sequential double barrel as the reason
for a higher rate of fire, which is exactly the mechanic the old cap removed.
