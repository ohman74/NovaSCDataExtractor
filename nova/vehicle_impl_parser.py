"""Parse vehicle implementation XMLs for hull mass and port definitions.

These files are at Scripts/Entities/Vehicles/Implementations/Xml/ and contain:
- Hull mass on the main Part element
- Full port hierarchy with minSize, maxSize, Types, flags
- Pipe connections (power, heat, fuel, shield)
"""

import os
import xml.etree.ElementTree as ET

from .utils import safe_float, safe_int


def parse_vehicle_implementations(cache_dir):
    """Parse all vehicle implementation XMLs.

    Returns:
        dict mapping vehicle name (e.g., "AEGS_Gladius") to parsed data
    """
    veh_dir = os.path.join(cache_dir, "Data", "Scripts", "Entities",
                           "Vehicles", "Implementations", "Xml")

    if not os.path.isdir(veh_dir):
        print("  Vehicle implementation XMLs not found")
        return {}

    results = {}
    files = [f for f in os.listdir(veh_dir) if f.endswith(".xml")]
    parsed = 0
    failed = 0
    # Filled in while parsing the base impls, then consulted by the
    # parts-only Modifications files, which inherit their DamagesGroups
    # from whichever base they override.
    destroy_groups = _DestroyGroupRegistry()

    for filename in files:
        filepath = os.path.join(veh_dir, filename)
        try:
            data = _parse_vehicle_xml(filepath, destroy_groups)
            if data:
                name = data.get("name", os.path.splitext(filename)[0])
                results[name] = data
                parsed += 1
        except Exception as e:
            # _parse_vehicle_xml already returns None on ParseError, so
            # anything landing here is unexpected — count it, but say so.
            failed += 1
            print(f"  ! vehicle impl {filename}: {type(e).__name__}: {e}")

    # Variant overrides live in Modifications/<Variant>.xml — applied only
    # when the entity's VehicleComponentParams.modification field is set
    # (e.g. modification="Sentinel" selects Modifications/AEGS_Vanguard_Sentinel.xml).
    # We keep them in a separate index from base impls so that they never
    # shadow a base file via filename collision. The orphan-data case that
    # forced this split: Modifications/VNCL_Stinger.xml exists alongside the
    # base vncl_stinger.xml; no entity references the override (every
    # Stinger entity has modification=""), so it must not win the lookup.
    mod_dir = os.path.join(veh_dir, "Modifications")
    variant_overrides = {}
    if os.path.isdir(mod_dir):
        for filename in os.listdir(mod_dir):
            if not filename.endswith(".xml"):
                continue
            variant_name = os.path.splitext(filename)[0]
            filepath = os.path.join(mod_dir, filename)
            try:
                data = _parse_modification_xml(filepath, destroy_groups)
                if data:
                    if not data.get("name"):
                        data["name"] = variant_name
                    variant_overrides[variant_name] = data
            except Exception as e:
                failed += 1
                print(f"  ! vehicle mod {filename}: {type(e).__name__}: {e}")
        print(f"  Parsed {parsed} vehicle implementations + {len(variant_overrides)} variants ({failed} failed)")
    else:
        print(f"  Parsed {parsed} vehicle implementations ({failed} failed)")
    # Stash variant overrides on the results dict under a reserved key so
    # get_vehicle_impl_data can consult them when modification is set.
    results["__variant_overrides__"] = variant_overrides
    return results


def _parse_modification_xml(filepath, registry=None):
    """Parse a Modifications/<Variant>.xml file.

    Two structures occur:
    - <Modifications><Vehicle name="<base>"> ... </Vehicle></Modifications>
      Full vehicle override (e.g. AEGS_Vanguard_Sentinel) — parse via the
      shared _extract_vehicle_data on the inner Vehicle element.
    - <Modifications><Parts> ... </Parts></Modifications>
      Parts-only override (e.g. ANVL_Hornet_F7CM, ORIG_350r) — parse the
      Parts tree directly to extract this variant's port hierarchy.
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError:
        return None
    if root.tag != "Modifications":
        return None
    # A variant file may carry its own <Damages> override (Sentinel,
    # Hoplite) but usually inherits the base's groups, so union both.
    groups = _destroy_groups(root, registry)
    veh = root.find("Vehicle")
    if veh is not None:
        return _extract_vehicle_data(veh, groups)
    parts_elem = root.find("Parts")
    if parts_elem is None:
        return None
    main_part = parts_elem.find("Part")
    if main_part is None:
        return None
    structural = _collect_structural_parts(main_part, groups)
    return {
        "name": "",
        "ports": _parse_parts_recursive(main_part),
        "structuralParts": structural,
        "mass": _mass_from_parts(structural),
        "hullHP": _hull_hp_from_parts(structural),
    }


def _parse_vehicle_xml(filepath, registry=None):
    """Parse a single vehicle implementation XML."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError:
        return None

    if root.tag != "Vehicle":
        return None

    # Base impls define every damage group they reference, so their own
    # <Damages> block is authoritative; the registry only collects them
    # for the variant files parsed afterwards.
    if registry is not None:
        registry.observe(root)
    return _extract_vehicle_data(root, _destroy_groups(root))


def _extract_vehicle_data(root, destroy_groups=None):
    """Extract vehicle metadata + ports from a <Vehicle> element."""
    if destroy_groups is None:
        destroy_groups = _destroy_groups(root)
    result = {
        "name": root.get("name", ""),
        "displayName": root.get("displayname", ""),
        "subType": root.get("subType", ""),
        "size": safe_int(root.get("size")),
        "itemPortTags": root.get("itemPortTags", ""),
    }

    # Parse parts tree for mass and ports
    parts_elem = root.find("Parts")
    if parts_elem is not None:
        main_part = parts_elem.find("Part")
        if main_part is not None:
            # One walk of the structural tree feeds both mass and hull HP,
            # and keeps the part ids that inline <Elem> overrides target.
            structural = _collect_structural_parts(main_part, destroy_groups)
            result["structuralParts"] = structural
            result["mass"] = _mass_from_parts(structural)
            result["ports"] = _parse_parts_recursive(main_part)
            result["hullHP"] = _hull_hp_from_parts(structural)

    # Wheeled / tracked ground-vehicle dynamics (PhysicalWheeled or PhysicalTracked).
    # Used for SteerCharacteristics + TrackSteerCharacteristics + TrackWheeledCharacteristics.
    physics = _collect_ground_vehicle_dynamics(root)
    if physics:
        result["groundDynamics"] = physics

    # Inline <Modifications> at the root carry per-variant overrides keyed
    # by name (Zeus_CL, F7C_Mk2, ...). Each Modification names the patch
    # file it layers on top of, and carries Elems whose idRef targets a
    # Part by id, so we record both the patchFile and the (idRef, attr,
    # value) triples for callers to resolve per variant.
    inline_mods = _extract_inline_modifications(root)
    if inline_mods:
        result["inlineModifications"] = inline_mods

    return result


def _extract_inline_modifications(root):
    """Return {variant_name: {patchFile, elems}} for inline mods.

    Modifications elements appear directly under the Vehicle root and group
    one or more `<Modification name="...">` blocks, each optionally naming
    a `patchFile` and containing
    `<Elems><Elem idRef="..." name="..." value="..." /></Elems>` overrides.

    `patchFile` is the explicit link from a variant name to the
    Modifications/ file that rewrites the part tree for it, e.g.

        <Modification name="F7CM_Heartseeker"
                      patchFile="Modifications/ANVL_Hornet_F7CM">

    Several variants can share one patch file (the Heartseeker is an F7CM
    with different turrets and paint), which is why the file cannot be
    found by matching the entity class name against the filename.
    """
    mods_elem = root.find("Modifications")
    if mods_elem is None:
        return None
    out = {}
    for mod in mods_elem.findall("Modification"):
        name = mod.get("name", "")
        if not name:
            continue
        patch_file = mod.get("patchFile", "") or ""
        elems = []
        # Both <Elems><Elem .../></Elems> and direct <Elem .../> are seen.
        for child in list(mod):
            if child.tag == "Elems":
                for e in child.findall("Elem"):
                    elems.append({
                        "idRef": e.get("idRef", ""),
                        "name": e.get("name", ""),
                        "value": e.get("value", ""),
                    })
            elif child.tag == "Elem":
                elems.append({
                    "idRef": child.get("idRef", ""),
                    "name": child.get("name", ""),
                    "value": child.get("value", ""),
                })
        if elems or patch_file:
            out[name] = {"patchFile": patch_file, "elems": elems}
    return out or None


def _collect_ground_vehicle_dynamics(root):
    """Extract ground-vehicle steer/drive/track params from impl XML.

    Looks for <PhysicalWheeled> (wheeled cars/buggies) and <PhysicalTracked>
    (tank-style tracked vehicles like the Tumbril Storm). Tracked vehicles
    additionally provide <Engine> drive params under TrackWheeledCharacteristics
    in the reference; the engine block lives at the root level.
    """
    out = {}
    for elem in root.iter():
        if elem.tag == "PhysicalWheeled":
            out["physicalWheeled"] = dict(elem.attrib)
        elif elem.tag == "ArcadeWheeled":
            # Arcade-physics wheeled vehicles (DRAK_Mule, etc.) — same steer
            # attribute names as PhysicalWheeled, no separate Engine element.
            out["physicalWheeled"] = dict(elem.attrib)
        elif elem.tag == "TrackWheeled":
            # Tank/tracked vehicles (Tumbril Storm, Nova) — single element
            # carries both steer params and engine params on the same node.
            out["trackWheeled"] = dict(elem.attrib)
        elif elem.tag == "Engine":
            # Multiple Engine elements may exist (e.g. one per wheel group); take
            # the first non-empty one.
            if "engine" not in out and elem.attrib:
                out["engine"] = dict(elem.attrib)
        elif elem.tag == "Power" and elem.attrib:
            # Arcade-physics vehicles (DRAK_Mule, etc.) put acceleration /
            # topSpeed / reverseSpeed on a <Power> element rather than
            # <Engine>. Capture the first one we see.
            if "power" not in out:
                out["power"] = dict(elem.attrib)
    return out if out else None


class _DestroyGroupRegistry:
    """Corpus-wide record of which DamagesGroup names destroy the vehicle.

    Parts-only `Modifications/<Variant>.xml` files redefine the part tree
    (including each part's `<DamageBehavior class="Group">` wiring) but
    inherit `<Damages><DamagesGroups>` from the base impl, and carry no
    pointer back to it. So we accumulate group definitions while parsing
    the base impls (which are always self-contained) and let the variant
    files resolve their group references against that.

    A name only counts when every definition of it in the corpus carries a
    `class="Destroy"` behavior, so a name reused for something else
    somewhere cannot leak into a variant that never meant it.
    """

    def __init__(self):
        self._destroy = set()
        self._other = set()

    def observe(self, root):
        """Record every DamagesGroup defined in this document."""
        for name, is_destroy in _damage_group_classes(root).items():
            (self._destroy if is_destroy else self._other).add(name)

    def unambiguous(self):
        """Group names that mean "destroy the vehicle" everywhere."""
        return self._destroy - self._other


def _damage_group_classes(root):
    """Map every DamagesGroup name in the document to "is this a kill?".

    The kill group is identified by what it *does*, i.e. it contains a
    `<DamageBehavior class="Destroy" />`, not by what it is called. The
    impls also define a `DestroyEngine` group that only raises a
    MovementNotification, so a name-based rule mislabels every part wired
    to it.
    """
    out = {}
    for group in root.iter("DamagesGroup"):
        name = group.get("name", "")
        if not name:
            continue
        is_destroy = any(b.get("class") == "Destroy"
                         for b in group.iter("DamageBehavior"))
        out[name] = out.get(name, False) or is_destroy
    return out


def _destroy_groups(root, registry=None):
    """Destroy-group names in scope for this document."""
    names = {n for n, is_destroy in _damage_group_classes(root).items()
             if is_destroy}
    if registry is not None:
        names |= registry.unambiguous()
    return names


def _part_is_vital(part_elem, destroy_groups):
    """True when destroying this part destroys the whole vehicle.

    The part's own `<DamageBehaviors>` must hand off to a damage group that
    kills the vehicle:

        <DamageBehaviors>
          <DamageBehavior class="Group" damageRatioMin="1">
            <Group name="Destroy" />
          </DamageBehavior>
        </DamageBehaviors>
    """
    if not destroy_groups:
        return False
    behaviors = part_elem.find("DamageBehaviors")
    if behaviors is None:
        return False
    for behavior in behaviors.findall("DamageBehavior"):
        if behavior.get("class") != "Group":
            continue
        for group in behavior.iter("Group"):
            if group.get("name", "") in destroy_groups:
                return True
    return False


def _collect_structural_parts(main_part, destroy_groups=()):
    """Flat list of every structural part, main_part first.

    Only includes structural parts (AnimatedJoint, Animated, etc.) and
    skips ItemPort and MassBox parts (those are swappable components, not
    hull).

    Keeping each part's `id` alongside its mass and damageMax is what lets
    a variant's inline overrides reach the hull. Those elems target Parts
    by id:

        <Elem idRef="modPart_body" name="damageMax" value="700" />

    and the parsed port tree they would otherwise be applied to does not
    contain Parts at all, so they used to be dropped on the floor. Across
    the impls that is 205 damageMax, 70 mass and 42 name overrides.

    `vital` records whether destroying the part destroys the vehicle (see
    _part_is_vital). No elem rewires damage behaviors, so it is read from
    the XML once and survives any override.
    """
    parts = []

    def _add(elem, root=False):
        entry = {
            "id": elem.get("id", ""),
            "name": elem.get("name", ""),
            "mass": safe_float(elem.get("mass", "0")),
            "damageMax": safe_float(elem.get("damageMax", "0")),
            "vital": _part_is_vital(elem, destroy_groups),
        }
        if root:
            # The hull root carries the ship's own mass but is not itself
            # one of the hull parts the Hull stats enumerate.
            entry["root"] = True
        parts.append(entry)

    def _walk(elem):
        for child in elem:
            if child.tag == "Part":
                if child.get("class", "") in ("ItemPort", "MassBox"):
                    continue
                _add(child)
                _walk(child)
            elif child.tag == "Parts":
                _walk(child)

    _add(main_part, root=True)
    _walk(main_part)
    return parts


def _mass_from_parts(parts):
    """Hull mass: the sum over every structural part, root included."""
    return sum(p["mass"] for p in parts)


def _hull_hp_from_parts(parts):
    """Build {VitalParts: {name: hp}, Parts: {name: hp}} from the part list.

    VitalParts = parts whose destruction triggers a damage group that
    destroys the vehicle, at any depth in the tree: the Hornet F7A wires
    nose and tail while both hang off Body.
    Parts = everything else with damageMax.
    """
    vital_parts = {}
    other = {}
    for part in parts:
        if part.get("root") or not part["damageMax"]:
            continue
        target = vital_parts if part["vital"] else other
        target[part["name"]] = part["damageMax"]

    result = {}
    if vital_parts:
        result["VitalParts"] = vital_parts
    if other:
        result["Parts"] = other
    return result if result else None


def _parse_parts_recursive(part_elem):
    """Recursively parse Part elements to extract ItemPort definitions."""
    ports = []

    for child in part_elem:
        if child.tag == "Part":
            part_class = child.get("class", "")
            part_name = child.get("name", "")

            if part_class == "ItemPort":
                port = _parse_item_port(child)
                if port:
                    port["partName"] = part_name
                    ports.append(port)
            elif part_class in ("Animated", "AnimatedJoint", "Static",
                                "SubPart", "Mass", "Light", ""):
                # Recurse into container parts
                sub_ports = _parse_parts_recursive(child)
                ports.extend(sub_ports)

            # Also check for sub-parts within ItemPort parts
            sub_parts = child.find("Parts")
            if sub_parts is not None:
                sub_ports = _parse_parts_recursive(sub_parts)
                if sub_ports:
                    # Attach sub-ports to the current port if it's an ItemPort
                    if part_class == "ItemPort" and ports and ports[-1].get("partName") == part_name:
                        ports[-1]["subPorts"] = sub_ports
                    else:
                        ports.extend(sub_ports)

        elif child.tag == "Parts":
            sub_ports = _parse_parts_recursive(child)
            ports.extend(sub_ports)

    return ports


def _parse_item_port(part_elem):
    """Parse an ItemPort Part element."""
    ip_elem = part_elem.find("ItemPort")
    if ip_elem is None:
        return None

    port = {
        "name": part_elem.get("name", ""),
        "minSize": safe_int(ip_elem.get("minSize") or ip_elem.get("minsize")),
        "maxSize": safe_int(ip_elem.get("maxSize") or ip_elem.get("maxsize")),
    }
    # `id` is the modification target identifier — inline <Modifications>
    # blocks reference these ids via `<Elem idRef="..." />` to override
    # specific port attributes per variant (Zeus_CL enables modCompCLTurret,
    # F7C_Mk2 enables modPartPowerPlant02, etc.). The id can sit on the
    # outer <Part> (e.g. modPartPowerPlant02 — used for skipPart toggles)
    # OR on the inner <ItemPort> (e.g. modPortPowerPlant01 — used for
    # size/flag overrides). Both can apply to the same port: F7C Mk2's
    # modification list flips modPartPowerPlant02.skipPart=0 AND sets
    # modPortPowerPlant01.minSize/maxSize=1, both targeting power-plant
    # ports on the same impl. Capture both so the indexer can find this
    # port under either reference.
    ids = []
    pid = part_elem.get("id")
    if pid:
        ids.append(pid)
    ipid = ip_elem.get("id")
    if ipid and ipid != pid:
        ids.append(ipid)
    if ids:
        port["ids"] = ids
    # skipPart marks variant-only / disabled ports (Zeus EMP/QED, etc.) —
    # reference omits these entirely. Inline modifications can re-enable
    # via `<Elem idRef="<id>" name="skipPart" value="0" />`.
    if part_elem.get("skipPart") == "1":
        port["skipPart"] = True

    # defaultWeaponGroup: presence signals a pilot-controlled mount (reference
    # classifies these as PilotWeapons even when the Type list includes a
    # Turret subtype like BallTurret). Absence means no pilot fire-group
    # assignment, i.e. crew-operated turrets and other non-weapon hardpoints.
    wg = ip_elem.get("defaultWeaponGroup")
    if wg is not None:
        port["defaultWeaponGroup"] = wg

    flags = ip_elem.get("flags", "")
    if flags:
        # Preserve the $ prefix — it carries semantic weight
        # (e.g. "$uneditable" vs "uneditable").
        port["flags"] = [f.strip() for f in flags.split() if f.strip()]
        port["uneditable"] = "uneditable" in flags

    # PortTags and RequiredTags
    port_tags = ip_elem.get("portTags", "")
    if port_tags:
        port["portTags"] = port_tags
    req_tags = ip_elem.get("requiredTags", "")
    if req_tags:
        port["requiredPortTags"] = req_tags

    # Types - vehicle impl uses "subtypes" attr (comma-separated) not SubType elements
    types_elem = ip_elem.find("Types")
    if types_elem is not None:
        types = []
        for type_elem in types_elem:
            t = type_elem.get("type", "")
            if not t:
                continue
            subtypes_str = type_elem.get("subtypes", "")
            if subtypes_str:
                for st in subtypes_str.split(","):
                    st = st.strip()
                    if st:
                        types.append(f"{t}.{st}")
            else:
                st = type_elem.get("subType", "")
                types.append(f"{t}.{st}" if st else t)
        port["types"] = types

    # ControllerDef.controllableTags + PriorityGroups (used to wire weapon
    # ports to operator seats for the RemoteController.Seats field).
    cd = ip_elem.find("ControllerDef")
    if cd is not None:
        controllable = cd.get("controllableTags") or ""
        if controllable:
            port["controllableTags"] = controllable
        # PriorityGroups specify which item types + tags this port (when
        # occupied as a seat) exclusively controls. Used to map weapon
        # ports' controllableTags back to seat ports.
        # Captures both <UserDef> (seat-occupier-side) and <UsableDef>
        # (controller-port-side) PriorityGroups — both follow the same
        # itemType/tags/Priority shape.
        excl = []
        controlled_tags = []
        # `defaultPriorities` maps itemType -> defaultPriority value as
        # written on the PriorityGroup element. Captures the broad-gunner
        # signal: e.g. Prowler copilot WC has Turret/WeaponGun
        # defaultPriority="50" (numeric, broad). Pilot WCs with empty/empty
        # default (implicit exclusive_control) appear as "" here. Used to
        # detect "non-pilot broad-gunner" status when classifying ports.
        default_priorities = {}
        for parent_def in (cd.find("UserDef"), cd.find("UsableDef")):
            if parent_def is None:
                continue
            pg_root = parent_def.find("PriorityGroups")
            if pg_root is None:
                continue
            for pg in pg_root:
                it_type = pg.get("itemType")
                if not it_type:
                    continue
                # Capture defaultPriority once per itemType. Prefer the first
                # encountered value if both UserDef and UsableDef declare it.
                dp = pg.get("defaultPriority")
                if dp is not None and it_type not in default_priorities:
                    default_priorities[it_type] = dp
                for tags_elem in pg:
                    if tags_elem.tag != "tags":
                        continue
                    tag = tags_elem.get("tag")
                    pri = tags_elem.find("Priority")
                    pri_v = pri.get("value") if pri is not None else None
                    if not tag:
                        continue
                    if pri_v == "exclusive_control":
                        excl.append((it_type, tag))
                    elif pri_v and pri_v not in ("no_control", "observe_only"):
                        # Numeric priority or other — controller has
                        # non-exclusive control over this tag. Preserve
                        # the priority value (int when parseable, else str)
                        # so downstream code can compare cross-tag claims.
                        try:
                            prio_val = int(pri_v)
                        except (TypeError, ValueError):
                            prio_val = pri_v
                        controlled_tags.append((it_type, tag, prio_val))
        if excl:
            port["exclusiveControl"] = excl
        if controlled_tags:
            port["controlledTags"] = controlled_tags
        if default_priorities:
            port["defaultPriorities"] = default_priorities

        # Numeric-priority WeaponController/MissileController PG entries on
        # SEAT ports (UserDef). Reclaimer pilot has priority "50" on
        # TurretConsole01 (vs console_01 priority "100"); REF picks pilot
        # (lower number wins). Used as a tie-breaker for RC seat selection
        # when no port has exclusive_control on the tag.
        prio_controllers = []
        ud = cd.find("UserDef")
        if ud is not None:
            pg_root = ud.find("PriorityGroups")
            if pg_root is not None:
                for pg in pg_root:
                    it_type = pg.get("itemType")
                    if it_type not in ("WeaponController", "MissileController"):
                        continue
                    for tags_elem in pg:
                        if tags_elem.tag != "tags":
                            continue
                        tag = tags_elem.get("tag")
                        pri = tags_elem.find("Priority")
                        pri_v = pri.get("value") if pri is not None else None
                        if not tag or not pri_v:
                            continue
                        if pri_v in ("exclusive_control", "no_control",
                                      "observe_only"):
                            continue
                        try:
                            prio_int = int(pri_v)
                        except ValueError:
                            continue
                        prio_controllers.append((it_type, tag, prio_int))
        if prio_controllers:
            port["priorityControllers"] = prio_controllers

    return port


def get_vehicle_impl_data(vehicle_impls, vehicle_definition, class_name,
                          modification=None):
    """Look up vehicle implementation data by vehicleDefinition path or className.

    Resolution order (the variant steps are gated on the entity's
    `modification` field, the structural signal of intent to use one):
    1. Base impl by vehicleDefinition basename, falling back to className.
       This is the authoritative pointer and also the document that
       declares what each variant name means.
    2. Variant override, taken from the base impl's inline
       `<Modification name="X" patchFile="Modifications/Y">`: the patch
       file named there is the ship's real part tree. Several variants
       routinely share one patch file (F7CM, F7CM_Heartseeker, CalMason
       and F7CM_SQ42 all patch from ANVL_Hornet_F7CM), so the file cannot
       be found by matching the entity class name.
       When the Modification declares no patchFile, or it points at a file
       this build does not ship, fall back to a Modifications/ file named
       after the entity class, then to the base impl untouched.
    3. Apply that same Modification's `<Elems>` on top, which is how the
       game layers per-variant attribute tweaks over the patched tree.
       (F7C_Mk2/F7CR_Mk2/F7CS_Mk2 layered on F7A.xml; Zeus CL/MR/ST
       layered on RSI_Zeus.xml.)

    Lookup is case-insensitive because vehicleDefinition paths from the
    game data are lowercase while impl filenames use proper casing
    (AEGS_Gladius).

    Args:
        vehicle_impls: dict from parse_vehicle_implementations
        vehicle_definition: path like "scripts/.../xml/aegs_gladius.xml" (lowercase)
        class_name: fallback className like "AEGS_Gladius"
        modification: variant name from VehicleComponentParams.modification

    Returns:
        parsed vehicle impl data dict, or None
    """
    # Case-insensitive index over base impls only — variant overrides live
    # in a separate map and are only consulted when modification is set.
    idx = vehicle_impls.get("__lower_index__")
    if idx is None:
        idx = {k.lower(): k for k in vehicle_impls.keys() if not k.startswith("__")}
        vehicle_impls["__lower_index__"] = idx

    def _get(key):
        orig = idx.get(key.lower())
        return vehicle_impls.get(orig) if orig else None

    overrides = vehicle_impls.get("__variant_overrides__") or {}
    override_idx = vehicle_impls.get("__variant_overrides_lower__")
    if override_idx is None:
        override_idx = {k.lower(): k for k in overrides.keys()}
        vehicle_impls["__variant_overrides_lower__"] = override_idx

    def _override(key):
        orig = override_idx.get((key or "").lower()) if key else None
        return overrides.get(orig) if orig else None

    # 1. Base impl by vehicleDefinition (authoritative path), then
    #    className as fallback for entities whose vehicleDefinition is
    #    missing or stale.
    data = None
    if vehicle_definition:
        basename = os.path.splitext(os.path.basename(vehicle_definition))[0]
        data = _get(basename)
    if data is None:
        data = _get(class_name)

    # The base impl is what declares the variant, so read the Modification
    # block from there rather than from whatever we end up returning.
    mod_entry = None
    if modification and data:
        mod_entry = (data.get("inlineModifications") or {}).get(modification)

    # 2. Variant override. patchFile is the explicit link and wins; the
    #    className-keyed filename match is the weaker fallback for
    #    Modification blocks that declare no patch file.
    if modification:
        variant = None
        patch_file = mod_entry.get("patchFile") if mod_entry else ""
        if patch_file:
            stem = os.path.splitext(
                os.path.basename(patch_file.replace("\\", "/")))[0]
            variant = _override(stem)
        if variant is None:
            variant = _override(class_name)
        if variant is not None:
            data = variant

    if data is None:
        return None

    # 3. Apply the variant's inline Elems (Zeus_CL, F7C_Mk2, ...) on top of
    #    whatever tree step 2 settled on.
    elems = mod_entry.get("elems") if mod_entry else None
    if not elems and modification:
        own = (data.get("inlineModifications") or {}).get(modification)
        elems = own.get("elems") if own else None
    if elems:
        data = _apply_inline_modification(data, elems)
    return data


def _apply_inline_modification(impl_data, elems):
    """Return a copy of impl_data with `elems` applied.

    Each elem has {idRef, name, value}. An id addresses either an ItemPort
    or a structural Part, so both trees are indexed and each elem lands
    wherever its id actually lives. Port elems override the named
    attribute, with skipPart special-cased so "0" clears the flag and "1"
    sets it. Part elems override mass, damageMax or name, after which hull
    mass and Hull HP are recomputed from the patched list. The ORIG 350r
    is the shape of it: its Modification skips six flair ports and pulls
    body and tail down to 700 damageMax in the same block.

    The same id can appear at multiple positions in the parsed port tree
    (the recursive parser duplicates Parts nodes that sit inside
    non-ItemPort containers); we apply to every match so the override
    sticks regardless of which instance the consumer encounters.
    """
    import copy
    new_data = copy.deepcopy(impl_data)

    ports_by_id = {}
    parts_by_id = {}
    for part in new_data.get("structuralParts") or []:
        if part.get("id"):
            parts_by_id.setdefault(part["id"], []).append(part)

    def _index(ports):
        for p in ports:
            if not isinstance(p, dict):
                continue
            for pid in p.get("ids") or ():
                ports_by_id.setdefault(pid, []).append(p)
            _index(p.get("subPorts") or [])

    _index(new_data.get("ports") or [])

    hull_touched = False
    for elem in elems:
        idref = elem.get("idRef") or ""
        attr = elem.get("name") or ""
        value = elem.get("value") or ""
        for part in parts_by_id.get(idref) or ():
            if attr in ("mass", "damageMax"):
                # safe_float turns an unparseable value into 0.0, which
                # here would silently erase a real hull number. The data
                # does carry one such value (the Gladius Valiant asks for
                # a mass of "501.51" with a stray direction mark and an
                # S glued on), so leave the part alone rather than zero it.
                try:
                    part[attr] = float(value)
                except (TypeError, ValueError):
                    continue
            elif attr == "name":
                part["name"] = value
            else:
                # Every other attr on a Part (Delay, filename, ...) is
                # outside what the Hull stats are built from.
                continue
            hull_touched = True
        targets = ports_by_id.get(idref) or []
        for port in targets:
            if attr == "skipPart":
                if value == "0":
                    port.pop("skipPart", None)
                elif value == "1":
                    port["skipPart"] = True
            elif attr in ("minSize", "maxSize", "minsize", "maxsize"):
                # Normalise both attr-name spellings to canonical camelCase.
                key = "minSize" if attr.lower() == "minsize" else "maxSize"
                port[key] = safe_int(value)
            else:
                # Generic pass-through for `name`, `flags`, etc. The port dict
                # uses the same key names as the impl XML attributes.
                port[attr] = value

    if hull_touched:
        structural = new_data["structuralParts"]
        new_data["mass"] = _mass_from_parts(structural)
        new_data["hullHP"] = _hull_hp_from_parts(structural)

    return new_data
