# Star Citizen XML Architecture: Item-Port Hierarchy

_Investigation date: 2026-04-26. Based on data in `cache/` directory._

---

## 1. File Structure Overview

### Vehicle Implementation XMLs

**Location:** `cache/Data/Scripts/Entities/Vehicles/Implementations/Xml/<ShipClass>.xml`  
**Variants:** `cache/Data/Scripts/Entities/Vehicles/Implementations/Xml/Modifications/<Variant>.xml`

These files define the **physical layout** of each ship: which slots exist on the hull,
their port names, accepted size ranges, type constraints, and pipe connections.

The `Modifications/` subdirectory holds variant overrides. Two sub-formats exist:
- `<Vehicle name="...">` wrapper — full vehicle tree (e.g., `AEGS_Vanguard_Sentinel.xml`)
- `<Parts>` wrapper — parts-only tree (e.g., `ANVL_Hornet_F7CM.xml`)

**Key attributes on `<Vehicle>`:**
| Attribute | Meaning |
|---|---|
| `name` | Base vehicle class name |
| `subType` | e.g., `Vehicle_Spaceship`, `Vehicle_Ground` |
| `size` | Ship size tier (1–6) |
| `itemPortTags` | Space-separated tags available to all top-level ports |

### Item Entity XMLs

**Location:** `cache/Data/Libs/Foundry/Records/entities/scitem/ships/<category>/<item>.xml`

Key subcategories:
| Directory | Contents |
|---|---|
| `turret/` | Manned turret items (TurretBase.MannedTurret) |
| `weapon_mounts/gimbal/` | Gimbal mounts (Turret.GunTurret), both standard and ship-specific |
| `weapons/` | Actual weapons (WeaponGun.Gun, WeaponGun.Rocket, etc.) |
| `displays/` | MFD/screen items (Display) |

### Parsed Context (nova)

`nova/vehicle_impl_parser.py` — parses the vehicle XMLs into port dicts  
`nova/dataforge_parser.py` — parses item entity XMLs into item dicts  
`nova/builders/ships.py` — orchestrates ship data assembly from loadout + impl data

---

## 2. Vehicle ItemPort Syntax

Inside `<Parts><Part class="ItemPort"><ItemPort ...>`:

```xml
<Part name="hardpoint_turret" class="ItemPort">
  <ItemPort
    minSize="1" maxSize="6"
    flags="$uneditable lower"
    defaultWeaponGroup="1"
    portTags="..."
    requiredTags="..."
    display_name="port_NameTurret"
  >
    <Types>
      <Type type="TurretBase" subtypes="MannedTurret"/>
      <Type type="WeaponGun" subtypes="Gun,GunTurret"/>
    </Types>
    <Pitch min="-30" max="30"/>
    <Yaw min="-30" max="30"/>
    <Connections>
      <Connection pipeClass="Power" pipe="MainPower"/>
      <Connection pipeClass="WeaponRegen" pipe="WeaponRegenTurret"/>
    </Connections>
    <ControllerDef controllableTags="pilotSeat">
      <UserDef>
        <PriorityGroups>
          <PriorityGroup itemType="WeaponController" defaultPriority="exclusive_control"/>
          ...
        </PriorityGroups>
      </UserDef>
      <UsableDef>
        <PriorityGroups>...</PriorityGroups>
      </UsableDef>
    </ControllerDef>
  </ItemPort>
</Part>
```

**Key `<ItemPort>` attributes:**
| Attribute | Meaning |
|---|---|
| `minSize` / `maxSize` | Size range of item that can be installed |
| `flags` | Space-separated: `uneditable`, `$uneditable`, `invisible`, `lower`, orientation tags |
| `defaultWeaponGroup` | Non-empty = pilot-controlled weapon (used to classify PilotWeapons vs MannedTurrets) |
| `portTags` | Tags this port exposes to the installed item |
| `requiredTags` | Tags the installed item must carry |

**`<Types><Type>`:** `type` attribute is the item category (e.g., `TurretBase`, `WeaponGun`).
`subtypes` is comma-separated (e.g., `"Gun,GunTurret"`). In code these are joined as `Type.SubType`.

**`<ControllerDef>`:** Wires ports to seats for Remote Controller resolution. `controllableTags`
marks this port as controllable. `UserDef/PriorityGroups` defines which item types this seat
controls, with Priority values of `exclusive_control`, `no_control`, `observe_only`, or numeric.
`UsableDef` specifies what this port (as a seat) can be used as.

**Important flag semantics:**
- `$uneditable` — port is locked to its default item (variant-specific mounts, nose guns with tags)
- `uneditable` — non-modifiable (controllers, fuel tanks, etc.)
- `invisible` — hidden slot (radars, motherboards, etc.)

---

## 3. Item SItemPortDef Syntax

Inside item entity XMLs, under `<Components><SItemPortContainerComponentParams><Ports>`:

```xml
<SItemPortDef
  Name="turret_left"
  DisplayName="@port_NameWeaponTopLeft"
  MinSize="2" MaxSize="2"
  Flags="$uneditable"
  DefaultWeaponGroup="UNDEFINED"
  controllableTag=""
  resourceLinkToParent="1"
  PortTags=""
  RequiredPortTags=""
  ...
>
  <Types>
    <SItemPortDefTypes Type="WeaponGun">
      <SubTypes>
        <Enum value="Gun"/>
      </SubTypes>
    </SItemPortDefTypes>
    <SItemPortDefTypes Type="Turret">
      <SubTypes>
        <Enum value="GunTurret"/>
      </SubTypes>
    </SItemPortDefTypes>
  </Types>
  <defaultItem itemPort="" entityClass="00000000-..."/>
  <Connections>
    <SItemPortConnectionParam Name="MainPower" Klass="Power"/>
  </Connections>
  ...
</SItemPortDef>
```

**Important attributes on `SItemPortDef`:**
| Attribute | Meaning |
|---|---|
| `Name` | Port identifier (e.g., `turret_left`, `hardpoint_class_2`, `Screen_Radar`) |
| `MinSize` / `MaxSize` | Accepted item size range |
| `Flags` | `$uneditable` = locked slot; empty = player-swappable |
| `DefaultWeaponGroup` | Usually `UNDEFINED` on turret items; non-UNDEFINED on vehicle impl ports |
| `resourceLinkToParent` | `1` = weapon regen connects to parent item (typical for weapon mounts) |

The difference between **vehicle impl** Types syntax and **item XML** Types syntax:
- Vehicle impl: `<Type type="Turret" subtypes="Gun,GunTurret"/>` (subtypes as attribute, comma-separated)
- Item XML: `<SItemPortDefTypes Type="Turret"><SubTypes><Enum value="GunTurret"/></SubTypes>` (subtypes as child elements)

---

## 4. Item Categories and Type Values

### TurretBase.MannedTurret (turret items)

Ship-specific turrets installed in vehicle `hardpoint_turret*` ports. Examples:
- `AEGS_Vanguard_SCItem_Turret` (5 ports: 2 weapon + 3 Display)
- `AEGS_Reclaimer_SCItem_Turret` (7 ports: 2 weapon + 5 Display)
- `AEGS_Hammerhead_SCItem_Turret_Top` (9 ports: 4 weapon + 5 Display)
- `AEGS_Hammerhead_SCItem_Turret_Side_FrontLeft` (10 ports: 4 weapon + 5 Display + 1 Room/OC)

Turret items serve as containers. Their ports are where gimbals or weapons are installed.

### Turret.GunTurret (gimbal mounts)

Installed in turret weapon-mount ports. They have exactly **1 sub-port**: `hardpoint_class_2`.
All standard gimbals (S1–S8) share this structure. Ship-specific gimbals may vary.

```
entityclassdefinition.mount_gimbal_s2.xml: 1 port (hardpoint_class_2, WeaponGun)
entityclassdefinition.mount_gimbal_s3.xml: 1 port (hardpoint_class_2, WeaponGun)
entityclassdefinition.mount_gimbal_s4.xml: 1 port (hardpoint_class_2, WeaponGun)
entityclassdefinition.mount_gimbal_s5.xml: 1 port (hardpoint_class_2, WeaponGun)
```

### WeaponGun.Gun (weapon items)

Installed in `hardpoint_class_2` gimbal ports. Standard weapons have exactly **4 sub-ports**:

| Port | Type |
|---|---|
| BAR1 | WeaponAttachment.Barrel |
| MEC | WeaponAttachment.FiringMechanism |
| POW | WeaponAttachment.PowerArray |
| VEN | WeaponAttachment.Ventilation |

Verified for: BEHR_BallisticRepeater_S2, KLWE_LaserRepeater_S3/S4/S5, GATS_BallisticGatling_S1,
KBAR_BallisticCannon_S1/S2/S3. All have the same 4 WeaponAttachment sub-ports regardless of size.

### Display (screen items)

Installed in `Screen_*` ports of turret items. Screen items have **0 sub-ports**.
Examples: `Radar_Display_Screen_Template`, `Vehicle_Screen_MFD`.

### Room / hardpoint_OC

Some side turrets (e.g., Hammerhead side turrets) have a `hardpoint_OC` port of type `Room`.
This is an Operator Console port. It contains a lighting/OC item, has 0 weapon sub-ports.
The top/rear Hammerhead turrets lack this port (9 ports vs 10 for side turrets).

### Turret.NoseMounted, Turret.BallTurret, Turret.CanardTurret

Variants of turret-style mounts with different port structures:
- `Turret.NoseMounted` (e.g., `BEHR_PC2_Dual_S3`): 2 weapon sub-ports, no gimbal
- `Turret.BallTurret` (e.g., `ANVL_Hornet_F7CM_Mk2_BallTurret`): multiple weapon and missile sub-ports
- `Turret.CanardTurret` (e.g., Hornet F7CM Mk2 nose): 2 weapon S1 sub-ports

---

## 5. Walking the Full Hierarchy

The complete item-port chain for a manned turret (e.g., AEGS_Vanguard):

```
Vehicle XML
  hardpoint_turret [1-6, TurretBase.MannedTurret]           <- vehicle-level port
    ↓ DefaultLoadout installs: AEGS_Vanguard_SCItem_Turret
    ↓ Turret item XML has SItemPortDef:
      turret_left [2-2, WeaponGun.Gun, Turret.GunTurret]    <- turret sub-port
        ↓ DefaultLoadout installs: Mount_Gimbal_S2
        ↓ Gimbal item XML has SItemPortDef:
          hardpoint_class_2 [1-2, WeaponGun.Gun]             <- gimbal sub-port
            ↓ DefaultLoadout installs: BEHR_BallisticRepeater_S2
            ↓ Weapon item XML has SItemPortDef:
              BAR1 [1-1, WeaponAttachment.Barrel]             <- weapon attach port
              MEC  [1-1, WeaponAttachment.FiringMechanism]
              POW  [1-1, WeaponAttachment.PowerArray]
              VEN  [1-1, WeaponAttachment.Ventilation]
      turret_right [2-2, WeaponGun.Gun, Turret.GunTurret]   <- (same chain as above)
      Screen_Radar [1-1, Display]                            <- display port
      Screen_Right_Top [1-1, Display]
      Screen_Left_Top [1-1, Display]
```

**Chain depth:** vehicle → turret item → weapon mount → gimbal → weapon → weapon attachments

**Where data comes from:**
- Vehicle port: vehicle impl XML (`AEGS_Vanguard.xml`)
- Turret sub-ports: turret item XML (`aegs_vanguard_scitem_turret.xml`)
- Gimbal sub-ports: gimbal item XML (`entityclassdefinition.mount_gimbal_s2.xml`)
- Weapon sub-ports: weapon item XML (`behr_ballisticrepeater_s2.xml`)

**The `Ports[]` list in our output** only shows ports with **installed items** (from the default loadout).
Display ports that have an installed screen item DO appear. Weapon attachment ports (BAR1 etc.)
do NOT appear because we don't resolve the weapon item XMLs during loadout walking.

---

## 6. Hardpoints Count Formulas

### 6.1 PilotWeapons.Hardpoints

**REF formula:** Recursive count of the `InstalledItems` tree, **excluding** items with Missile
or BombLauncher types.

```python
EXCL_TYPES = {'Missile', 'MissileLauncher', 'GroundVehicleMissileLauncher', 'BombLauncher', 'Bomb'}

def count_pw_hardpoints(items):
    total = 0
    for item in items:
        type_prefix = item.get('BaseLoadout',{}).get('Type','').split('.')[0]
        if type_prefix not in EXCL_TYPES:
            total += 1
            total += count_pw_hardpoints(item.get('Ports', []))
    return total
```

**Accuracy:** 88.6% (148/167 ships). Remaining 12% mismatches involve:

1. **Empty gimbal sub-ports** — When a gimbal mount is installed but has no weapon in its
   `hardpoint_class_2` slot, the REF still counts that empty slot as +1. Our tree omits it
   (the `Ports[]` for the gimbal shows empty list).
   _Example: ARGO_RAFT — 2 gimbals with empty class2 slots, REF=4 (2 gimbals + 2 empty slots)
   but tree=2._

2. **Unresolved empty weapon ports** — Some ships have PilotWeapons ports with `type=None`
   (no item installed), but the vehicle XML defines the port as a gimbal slot.
   REF counts these ports + their expected sub-slots.
   _Example: CNOU_Mustang_Alpha — wing mounts with no gimbals installed._

3. **MissileLauncher sub-ports inside ball turrets** — Our code currently INCLUDES these
   (e.g., Hornet F7CM Mk2 ball turret has 8 missile slots that should be excluded).

4. **Door/Room/Display items included in PilotWeapons** — Items like weapon lockers, Room doors,
   or Display items that appear in PilotWeapons ports should be excluded.
   _Example: AEGS_Vanguard — `hardpoint_weapon_locker_warden` is Door.UNDEFINED, REF=10 but
   ours=11 because we include the door._

**Current code produces:** `_count_hardpoints(items)` = total recursive count without type filtering.
This overcounts when non-weapon items are in the PilotWeapons list.

### 6.2 MannedTurrets.Hardpoints — FORMULA UNKNOWN

**Key finding:** After exhaustive testing, the REF `MannedTurrets.Hardpoints` value **cannot be
derived** from the InstalledItems tree using any consistent recursive formula. This was proven by
finding ships with identical tree structure but different REF values:

| Ship | Turret item | Gimbal | Weapon | REF | Tree items |
|---|---|---|---|---|---|
| ANVL_Gladiator | ANVL_Gladiator_SCItem_Turret | Mount_Gimbal_S3 | KLWE_LaserRepeater_S3 | 16 | 5 |
| RSI_Constellation_Taurus | RSI_Constellation_SCItem_Turret_Upper | Mount_Gimbal_S3 | KLWE_LaserRepeater_S3 | 27 | 5 |

Both ships have:
- Identical turret item XML structure (5 ports: 2 weapons + 3 screens)
- Identical gimbal (1 port: hardpoint_class_2)
- Identical weapon (4 attachment ports)
- Yet REF values differ by 11

Additional proof from variants:
- AEGS_Vanguard_Harbinger has **rocket pods** (0 sub-ports each) but REF=16 — same as Vanguard
  with full gimbal+weapon chain. Cannot be weapon-attachment-count derived.
- ANVL_Hurricane has **4 gimbals** (vs Vanguard's 2) but REF=16 — same as 2-gimbal ships.

**What is known about the formula structure:**

The REF InstalledItems tree **excludes** Display ports (Screen_* items) from the Ports[] list.
The tree also excludes Room/OC ports. But the Hardpoints count is always larger than the
cleaned tree count, so something else is being counted.

**Formula attempts tested:**

| Formula | Vanguard | Reclaimer | Hammerhead | Notes |
|---|---|---|---|---|
| tree count | 5 | 5 | 54 | REF: 16 / 16 / 109 |
| tree + weapon_attach (2*4=8) | 13 | 13 | 150 | Fails all 3 |
| veh_port + turret_xml_ports + gimbal_ports + weapon_ports | 16 ✓ | 18 ✗ | 184 ✗ | Fails Reclaimer |
| (above) + all Display ports capped at 3 | 16 ✓ | 16 ✓ | varies | Works for 7/38 ships |

The most promising formula `1 + N_turret_item_ports + N_gimbals*(1 + N_weapon_attach)` matches
Vanguard exactly (1 + 5 + 2*(1+4) = 16) but fails for Reclaimer (1 + 7 + 2*(1+4) = 18, not 16).

**Hypothesis (unproven):** The REF value may be computed using GUID-based item
resolution (the raw SpeedTree/DataForge GUID for each installed item rather than the ClassName),
accessing data not available in our cached XML files, or using a lookup table compiled when
the reference data was generated.

Alternatively, the reference hardpoint count may come from a separate pass over the vehicle
impl XML combined with item XMLs that is more conservative than our current recursive walk.

**Current extractor behavior:** Uses `_count_hardpoints(items)` = recursive count of
InstalledItems. For Vanguard this gives 8 (vs REF 16), for Hammerhead 88 (vs REF 109).

### 6.2.5 WeaponMount.WeaponControl wrapper pattern

A previously-unknown structural pattern: ships can have **fixed/non-swappable mounted weapons**
via the `WeaponMount.WeaponControl` item type. These appear as turret-like ports but the
"installed item" is a wrapper that bundles a weapon + ammo + controller. Examples:

- **ANVL_Asgard side doors:** `hardpoint_turret_door_left/right` ports of type
  `WeaponMount.WeaponControl` install `WeaponMount_Gun_S1_ANVL_Asgard_Door_Left/Right` items.
  Each wrapper has 3 internal ports (`weapon`, `ammo_slot`, `weapon_controller`) and a
  defaultLoadout that pre-installs `GATS_BallisticGatling_Mounted_S1_DRAK_Cutlass_Steel`
  (which is the **GT-210 YellowJacket** Gallenson Tactical Systems gatling — same name as on
  the Cutlass Steel pintle mounts despite the `_DRAK_Cutlass_Steel` suffix).
- **DRAK_Cutlass_Steel pintle gun:** also uses the WeaponMount wrapper pattern (the
  `_DRAK_Cutlass_Steel` suffix on the GATS classname is the discriminator).

**REF behaviour:** The wrapper item is *not* shown — REF promotes the inner `weapon` port to
the top level of `MannedTurrets.InstalledItems` with the literal `PortName="weapon"` (not the
ship's outer port name). This is structurally similar to AnimatedJoint promotion but operates
on the WeaponMount.WeaponControl wrapper rather than on physical attached parts.

**Item structure (verified from XML):**

```
hardpoint_turret_door_left  [WeaponMount.WeaponControl, controllableTags="turret_doorleft"]
  └── WeaponMount_Gun_S1_ANVL_Asgard_Door_Left  (3 ports)
       ├── weapon              [WeaponGun.Gun | MissileLauncher, requiredPortTags="DRAK_Cutlass_Steel"]
       │     └── GATS_BallisticGatling_Mounted_S1_DRAK_Cutlass_Steel  ← YellowJacket
       │           ├── BAR1   [WeaponAttachment.Barrel]
       │           ├── MEC    [WeaponAttachment.FiringMechanism]
       │           ├── POW    [WeaponAttachment.PowerArray]
       │           └── VEN    [WeaponAttachment.Ventilation]
       ├── ammo_slot           [AmmoBox.Gun]
       │     └── AmmoBox_GATS_BallisticGatling_Mounted_S1  (0 ports)
       └── weapon_controller   [WeaponController]
             └── Controller_Weapon_UnmannedTurret  (0 ports)
```

**Implementation implication:** When extracting MannedTurrets.InstalledItems, ports of type
`WeaponMount.WeaponControl` should have their wrapper unwrapped and the inner `weapon` port
emitted as a top-level entry with `PortName="weapon"` (literal). This explains the 2 phantom
"weapon" entries in Asgard's REF data.

### 6.3 ANVL_Asgard MannedTurrets Detail (added 2026-04-28)

Asgard provides a third independent disproof of formula derivability. **REF=35**, 3 InstalledItems.

**REF InstalledItems tree:**
```
[0] PortName=hardpoint_turret_bottom    Item=ANVL_Asgard_Turret_Bubble  (TurretBase.MannedTurret)
    └── 2 weapon mounts (Mount_Gimbal_S4 → KLWE_LaserRepeater_S4)   recursive count: 5
[1] PortName="weapon"                    Item=GATS_BallisticGatling_Mounted_S1_DRAK_Cutlass_Steel  (WeaponGun.Gun)
    └── (no Ports)   recursive count: 1
[2] PortName="weapon"                    Item=GATS_BallisticGatling_Mounted_S1_DRAK_Cutlass_Steel  (duplicate)
    └── (no Ports)   recursive count: 1
```

**Identified structure (corrected 2026-04-28):**
- The 2 "weapon" entries originate from `hardpoint_turret_door_left/right` ports on the Asgard
  hull (type `WeaponMount.WeaponControl`). See section 6.2.5 — each port installs a WeaponMount
  wrapper that has an inner `weapon` port with a YellowJacket gatling pre-installed. REF
  promotes the inner port to top-level with the literal name "weapon".
- The `_DRAK_Cutlass_Steel` suffix on the GATS classname is misleading — this is the
  GT-210 YellowJacket weapon shared between Asgard side doors and Cutlass Steel pintle mounts.

**Per-port count (Vanguard-formula style):**
- Bubble turret (`hardpoint_turret_bottom`): 1 + 5 (item ports) + 2*(1+4) = 16
- Each side door (`hardpoint_turret_door_X`): 1 + 3 (WeaponMount inner ports) + 4 (gun
  attachments) = 8. AmmoBox (0 ports) and Controller (0 ports) add nothing.
- 2 side doors: 2*8 = 16
- **Total: 16 + 16 = 32**

REF = 35. **Off by 3** — much closer than before, but still not exact. The unaccounted 3
might come from the WeaponMount wrappers themselves being counted (1 per door = +2) plus
something else, or from the 3 screens in the bubble turret being double-counted.

This adds a third datapoint where the recursive/structural formula fails:

| Ship | Tree count | Vanguard formula | REF | Δ |
|---|---|---|---|---|
| ANVL_Vanguard | 5 | 16 | 16 | 0 ✓ |
| AEGS_Reclaimer | 5 | 18 | 16 | -2 |
| AEGS_Hammerhead | 54 | 184 | 109 | -75 |
| **ANVL_Asgard** | **7** | **32** | **35** | **+3** |
| ANVL_Gladiator | 5 | 16 | 16 | 0 ✓ |
| RSI_Constellation_Taurus | 5 | 16 | 27 | +11 |

The Asgard delta has the *opposite sign* from Reclaimer/Hammerhead (REF higher, not lower),
strengthening the conclusion that no consistent multiplicative or additive correction exists.
Asgard's "phantom" GATS entries with literal `PortName="weapon"` suggest REF pulls from a data
source we cannot reach (compiled lookup table, possibly cross-referenced with Cutlass_Steel
manifest entries).

### 6.4 Hammerhead MannedTurrets Detail

6 turrets total: 4 side (Front_Left, Front_Right, Back_Left, Back_Right) + Top + Rear.

**REF InstalledItems tree (shows only non-Display ports):**
- Each side turret: 4 weapon mounts (hardpoint_weapon_left/right_upper/lower)
- Each top/rear turret: 4 weapon mounts (same)
- Each weapon mount: gimbal (Mount_Gimbal_S4) → hardpoint_class_2 → KLWE_LaserRepeater_S4
- REF tree count: 6*(1+4+4) = 54 items

**Actual turret XML port counts (from item XMLs):**
- Side turrets: 4 weapon + 1 OC (hardpoint_OC, Room) + 5 screens = 10 ports
- Top/Rear turrets: 4 weapon + 5 screens = 9 ports (no OC port)

**REF Hardpoints = 109** (approx 18.2 per turret on average).

If weapon attachment ports (4 per weapon) were included:
4 side × (1+10+4*1+4*4) = 4×31=124, 2 center × (1+9+4*1+4*4)=2×30=60 → total 184 (not 109)

---

## 7. Component Types Map

Types seen in vehicle impl XMLs and item XMLs:

| Type | SubType examples | Notes |
|---|---|---|
| `TurretBase` | `MannedTurret` | Manned turret items — top-level turret containers |
| `Turret` | `GunTurret`, `Gun`, `NoseMounted`, `BallTurret`, `PDCTurret`, `CanardTurret`, `Utility` | Gimbal mounts and turret variants |
| `WeaponGun` | `Gun`, `Rocket` | Ship weapons — installed in class2 ports |
| `WeaponAttachment` | `Barrel`, `FiringMechanism`, `PowerArray`, `Ventilation` | Weapon sub-ports (BAR1/MEC/POW/VEN) |
| `WeaponDefensive` | `CountermeasureLauncher` | Countermeasure launchers |
| `MissileLauncher` | `MissileRack` | Missile racks |
| `Missile` | `Missile`, `GroundVehicleMissile` | Individual missile slots |
| `Display` | (empty subtype) | Screen/MFD items — counted in MannedTurrets tree but excluded from InstalledItems display |
| `Room` | (empty) | Operator Console (OC) ports — excluded from InstalledItems tree |
| `Seat` | `Pilot`, (empty) | Pilot/crew seats |
| `SeatAccess` | (empty) | Seat entry animations |
| `SeatDashboard` | (empty) | Dashboard interactions |
| `FlightController` | (empty) | Integrated flight control |
| `WeaponController` | (empty) | Weapon fire control |
| `PowerPlant` | (empty) | Power plants |
| `Shield` | (empty) | Shield generators |
| `Cooler` | (empty) | Coolers |
| `QuantumDrive` | `QDrive` | QD items |
| `Radar` | `ShortRangeRadar`, `MidRangeRadar` | Radar items |
| `Avionics` | `Motherboard` | Avionics |
| `Armor` | (empty) | Armor items |
| `CargoGrid` | (empty) | Cargo containers |
| `Door` | (empty) | Door/access items |
| `MainThruster` | (empty) | Main engines |
| `ManneuverThruster` | `FixedThruster` | Maneuvering thrusters |
| `Paints` | (empty) | Paint items |
| `Flair_Cockpit` | `Flair_Hanging` | Cockpit decorations |

---

## 8. Fields Explaining Classification

### PilotWeapons vs MannedTurrets

In the **vehicle impl XML**, a port is classified as PilotWeapons if it has a non-empty
`defaultWeaponGroup` attribute on its `<ItemPort>` element. Turrets (MannedTurrets) have no
`defaultWeaponGroup` (or an empty string).

This is captured in `nova/vehicle_impl_parser.py` as `port["defaultWeaponGroup"]`.

The ship builder in `ships.py` uses this to route ports to either PilotWeapons or MannedTurrets
during the `_build_hardpoints` pass.

**Exception — BallTurrets:** The Hornet F7CM Mk2's ball turret (`hardpoint_weapon_center`) appears
in PilotWeapons because the port has `defaultWeaponGroup` set (it's pilot-controlled). Its
sub-ports include Missile slots — those should be excluded from the Hardpoints count.

### RemoteTurrets vs MannedTurrets

Remote turrets have `Type=Turret.GunTurret` (not `TurretBase.MannedTurret`) on the vehicle-level
port. Manned turrets have `TurretBase.MannedTurret`.

In the Reclaimer:
- `hardpoint_turret` (TurretBase.MannedTurret) → MannedTurrets
- `hardpoint_remote_turret_*` (Turret.GunTurret) → RemoteTurrets
- `hardpoint_pdc_*` (Turret.PDCTurret) → PDCTurrets

**Current bug:** Our code includes remote turrets, salvage turrets, PDC turrets, and operator
console seats in `MannedTurrets.InstalledItems`. The REF only puts `TurretBase.MannedTurret`
items in `MannedTurrets`.

---

## 9. Known Bugs in Current Extractor

### 9.1 Reclaimer InstalledItems Overcounting

REF `MannedTurrets.InstalledItems` for Reclaimer = 1 item (just `hardpoint_turret`).
Our output = 18 items (includes remote turrets, PDCs, salvage turrets, consoles).

This inflates our `MannedTurrets.Hardpoints` from the correct 16 to our computed 61.

**Root cause:** The classification logic doesn't restrict MannedTurrets to only ports with
installed items of type `TurretBase.MannedTurret`. All turret-related ports are lumped together.

### 9.2 PilotWeapons Non-Weapon Items

Our PilotWeapons includes Door/Room items (like `hardpoint_weapon_locker_warden` on Vanguard).
REF excludes these. This adds +1 to our count.

**Fix needed:** Filter out non-weapon item types (Door, Room, Display, SeatDashboard, etc.)
from the InstalledItems list before counting Hardpoints.

### 9.3 Gladiator Wing Gimbals in MannedTurrets

Our output includes `hardpoint_class_2_left_wing` and `hardpoint_class_2_right_wing` in
MannedTurrets for ANVL_Gladiator. REF puts only `hardpoint_turret` (the rear turret).

These wing mounts are fixed/bespoke gimbals (no defaultWeaponGroup on vehicle port), so
they get routed to MannedTurrets. The REF treats them differently (possibly as PilotWeapons
or a separate sub-category).

### 9.4 Valkyrie PilotWeapons / MannedTurrets Classification  

Our Valkyrie has `MannedTurrets.Hardpoints=27` but REF=96. Our PilotWeapons=26 but REF=3.
Many items are being misrouted between the two categories.

---

## 10. What Can Be Derived vs What Remains Unknown

### Derivable from Available Data

1. **Item port tree structure** — Complete hierarchy from vehicle XML + item XMLs
2. **Port types and sizes** — All attributes available in XML
3. **Installed items** — From default loadout tree
4. **PilotWeapons InstalledItems** — Can be correctly built by filtering on `defaultWeaponGroup`
5. **MannedTurrets InstalledItems** — Can be correctly filtered to only `TurretBase.MannedTurret`
6. **PilotWeapons.Hardpoints** — Recursive count of filtered InstalledItems (excl. Missile types)
   matches REF for ~88% of ships; remaining 12% are edge cases involving empty slots
7. **RemoteTurrets, PDCTurrets classification** — Via Type field on installed items

### Unknown / Cannot Be Derived

1. **MannedTurrets.Hardpoints exact formula** — Identical XML structures produce different REF
   values across ships (Gladiator=16, Taurus=27 with same turret/gimbal/weapon XMLs).
   The formula requires data unavailable in our cached XMLs, or is hardcoded in the reference data.

2. **Empty weapon slot counting** — When a gimbal has no weapon installed, REF counts the
   empty sub-port (+1 per empty gimbal). We don't track empty slots in the loadout walker.

3. **Some PilotWeapons edge cases** — Ships like ARGO_RAFT (empty gimbals), CNOU_Mustang
   (uninstalled wing ports), Aurora (empty wing gimbals) have REF values +1 or +2 higher
   than our tree count for reasons related to empty port definitions.

---

## 11. Implementation Recommendations

### Priority 1: Fix MannedTurrets InstalledItems Classification

Only include items whose `BaseLoadout.Type` starts with `TurretBase` in `MannedTurrets`.
Route other turret types to appropriate categories:
- `Turret.GunTurret` (remote turrets) → `RemoteTurrets`
- `Turret.PDCTurret` → `PDCTurrets`  
- `Turret.NoseMounted` (fixed dual mounts) → `PilotWeapons` (if pilot-controlled)
- `Seat.UNDEFINED` (operator consoles) → exclude from weapon categories

### Priority 2: Fix PilotWeapons Item Filtering

Before adding an item to `PilotWeapons.InstalledItems`, check its type:
- Exclude `Door`, `Room`, `Display`, `SeatDashboard`, `Seat`, `SeatAccess`, `MISC`
- Keep only types that are actual weapons or weapon mounts

### Priority 3: PilotWeapons Hardpoints Formula

Apply missile-exclusion recursive count:
```python
EXCL_PW_TYPES = {'Missile', 'MissileLauncher', 'GroundVehicleMissileLauncher',
                 'BombLauncher', 'Bomb', 'Door', 'Room', 'Display'}

def count_pw_hardpoints(items):
    total = 0
    for item in items:
        type_prefix = item.get('BaseLoadout',{}).get('Type','').split('.')[0]
        if type_prefix not in EXCL_PW_TYPES:
            total += 1
            total += count_pw_hardpoints(item.get('Ports', []))
    return total
```

### Priority 4: MannedTurrets.Hardpoints — Accept the Gap

Given that the MannedTurrets.Hardpoints formula cannot be derived from available data,
options are:
1. **Accept current count** (recursive tree count) — undercounts but is structurally correct
2. **Leave the field out** / mark as `null` — honest about the gap
3. **Hardcode values per ship** — maintain a lookup table for known ships (fragile)
4. **Use vehicle port-based count** — count `TurretBase.MannedTurret` slots in vehicle impl
   XML and multiply by a per-slot estimate — still approximate

The recursive tree count (current behavior) gives:
- Vanguard: 8 (REF=16)
- Reclaimer: 5 (REF=16, after fixing classification bug)
- Hammerhead: 54 (REF=109)

The ratio REF/tree varies from ~2x to ~6x with no consistent pattern.

---

## 12. Concrete Examples

### AEGS_Vanguard MannedTurrets Chain

```
Vehicle port:  hardpoint_turret          [minSize=1, maxSize=6, TurretBase.MannedTurret]
                 ↓ installed: AEGS_Vanguard_SCItem_Turret  (5 ports in item XML)
Turret ports:  turret_left               [2-2, WeaponGun.Gun, Turret.GunTurret]
               turret_right              [2-2, WeaponGun.Gun, Turret.GunTurret]
               Screen_Radar             [1-1, Display]
               Screen_Right_Top         [1-1, Display]
               Screen_Left_Top          [1-1, Display]

               turret_left installed: Mount_Gimbal_S2        (1 port in item XML)
Gimbal ports:  hardpoint_class_2         [1-2, WeaponGun.Gun]
               
               class_2 installed: BEHR_BallisticRepeater_S2  (4 ports in item XML)
Weapon ports:  BAR1                      [1-1, WeaponAttachment.Barrel]
               MEC                       [1-1, WeaponAttachment.FiringMechanism]
               POW                       [1-1, WeaponAttachment.PowerArray]
               VEN                       [1-1, WeaponAttachment.Ventilation]
               (same for turret_right chain)

REF InstalledItems tree: hardpoint_turret→[turret_left→[class_2], turret_right→[class_2]]
  (screens EXCLUDED from tree display)

REF.Hardpoints = 16
Our current = 8 (tree + 3 screen ports in tree = 1+5+2=8 in our code;
                 REF tree = 1+2+2=5 but REF.Hardpoints=16)
```

### AEGS_Hammerhead MannedTurrets Summary

6 turrets × (1 vehicle port + 4 weapon mounts + 4 gimbal ports + screens + OC):
- 4 side turrets: 10 sub-ports each (4 weapon + 5 Display + 1 Room/OC)
- 2 center (top/rear): 9 sub-ports each (4 weapon + 5 Display, no OC)

REF InstalledItems shows only weapon chains (no Display, no OC):
- Each turret in REF tree: 1 + 4 gimbals + 4 class2 = 9 items per turret
- Total REF tree: 6 × 9 = 54

REF.Hardpoints = 109 (ratio 109/54 ≈ 2.0, but weapon attach = 54+24*4=150, not 109)

---

_End of investigation. Document generated 2026-04-26._
