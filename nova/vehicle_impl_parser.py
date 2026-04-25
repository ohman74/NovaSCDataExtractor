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

    for filename in files:
        filepath = os.path.join(veh_dir, filename)
        try:
            data = _parse_vehicle_xml(filepath)
            if data:
                name = data.get("name", os.path.splitext(filename)[0])
                results[name] = data
                parsed += 1
        except Exception as e:
            failed += 1

    # Variant overrides live in Modifications/<Variant>.xml. Each file has a
    # <Modifications><Vehicle name="<Base>"> structure where the inner Vehicle
    # element contains the full ports tree for the variant. The variant name
    # comes from the filename (e.g. AEGS_Vanguard_Sentinel.xml). These need
    # to be loaded so variant-specific port types/sizes/flags override the
    # base vehicle's.
    mod_dir = os.path.join(veh_dir, "Modifications")
    if os.path.isdir(mod_dir):
        mod_parsed = 0
        for filename in os.listdir(mod_dir):
            if not filename.endswith(".xml"):
                continue
            variant_name = os.path.splitext(filename)[0]
            filepath = os.path.join(mod_dir, filename)
            try:
                data = _parse_modification_xml(filepath)
                if data:
                    # Carry the base name through but key by variant filename.
                    if not data.get("name"):
                        data["name"] = variant_name
                    results[variant_name] = data
                    mod_parsed += 1
            except Exception:
                failed += 1
        print(f"  Parsed {parsed} vehicle implementations + {mod_parsed} variants ({failed} failed)")
    else:
        print(f"  Parsed {parsed} vehicle implementations ({failed} failed)")
    return results


def _parse_modification_xml(filepath):
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
    veh = root.find("Vehicle")
    if veh is not None:
        return _extract_vehicle_data(veh)
    parts_elem = root.find("Parts")
    if parts_elem is None:
        return None
    main_part = parts_elem.find("Part")
    if main_part is None:
        return None
    return {
        "name": "",
        "ports": _parse_parts_recursive(main_part),
        "mass": _sum_structural_mass(main_part),
        "hullHP": _collect_hull_hp(main_part),
    }


def _parse_vehicle_xml(filepath):
    """Parse a single vehicle implementation XML."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError:
        return None

    if root.tag != "Vehicle":
        return None

    return _extract_vehicle_data(root)


def _extract_vehicle_data(root):
    """Extract vehicle metadata + ports from a <Vehicle> element."""
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
            # Mass: sum all structural part masses (excluding ItemPort and MassBox)
            result["mass"] = _sum_structural_mass(main_part)
            result["ports"] = _parse_parts_recursive(main_part)
            # Hull HP: structural part damageMax values + thruster HP
            result["hullHP"] = _collect_hull_hp(main_part)

    # Wheeled / tracked ground-vehicle dynamics (PhysicalWheeled or PhysicalTracked).
    # Used for SteerCharacteristics + TrackSteerCharacteristics + TrackWheeledCharacteristics.
    physics = _collect_ground_vehicle_dynamics(root)
    if physics:
        result["groundDynamics"] = physics

    return result


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


def _sum_structural_mass(elem):
    """Sum mass of all structural parts (excluding ItemPort and MassBox)."""
    part_class = elem.get("class", "")
    if part_class in ("ItemPort", "MassBox"):
        return 0

    total = safe_float(elem.get("mass", "0"))
    for child in elem:
        if child.tag == "Part":
            total += _sum_structural_mass(child)
        elif child.tag == "Parts":
            for sub in child:
                if sub.tag == "Part":
                    total += _sum_structural_mass(sub)
    return total


def _sum_mass_recursive(elem):
    """Sum all mass attributes in a part tree (hull mass + sub-part masses)."""
    total = safe_float(elem.get("mass", "0"))
    for child in elem:
        if child.tag == "Part":
            total += _sum_mass_recursive(child)
        elif child.tag == "Parts":
            for sub in child:
                if sub.tag == "Part":
                    total += _sum_mass_recursive(sub)
    return total


def _collect_hull_hp(main_part):
    """Collect damageMax from structural parts for Hull stats.

    Only includes structural parts (AnimatedJoint, Animated, etc.) — skips
    ItemPort and MassBox parts (those are swappable components, not hull).

    Returns flat dict: {VitalParts: {name: hp}, Parts: {name: hp}}
    VitalParts = top-level structural (Body, Nose).
    Parts = everything else with damageMax.
    """
    _VITAL_NAMES = {"body", "nose", "hull", "fuselage"}
    vital_parts = {}
    parts = {}

    def _walk(elem, is_top_level=False):
        for child in elem:
            if child.tag == "Part":
                part_class = child.get("class", "")
                if part_class in ("ItemPort", "MassBox"):
                    continue
                name = child.get("name", "")
                dmg_max = safe_float(child.get("damageMax", "0"))
                if dmg_max:
                    if is_top_level and name.lower() in _VITAL_NAMES:
                        vital_parts[name] = dmg_max
                    else:
                        parts[name] = dmg_max
                _walk(child, is_top_level=False)
            elif child.tag == "Parts":
                _walk(child, is_top_level=is_top_level)

    # Children of main_part are top-level structural parts
    _walk(main_part, is_top_level=True)

    result = {}
    if vital_parts:
        result["VitalParts"] = vital_parts
    if parts:
        result["Parts"] = parts
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
            elif part_class in ("Animated", "Static", "SubPart", "Mass", "Light", ""):
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

    # defaultWeaponGroup: presence signals a pilot-controlled mount (reference
    # classifies these as PilotWeapons even when the Type list includes a
    # Turret subtype like BallTurret). Absence means no pilot fire-group
    # assignment, i.e. crew-operated turrets and other non-weapon hardpoints.
    wg = ip_elem.get("defaultWeaponGroup")
    if wg is not None:
        port["defaultWeaponGroup"] = wg

    flags = ip_elem.get("flags", "")
    if flags:
        # Preserve the $ prefix — the SPViewer reference keeps it, and it
        # carries semantic weight (e.g. "$uneditable" vs "uneditable").
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

    return port


def get_vehicle_impl_data(vehicle_impls, vehicle_definition, class_name):
    """Look up vehicle implementation data by vehicleDefinition path or className.

    Lookup is case-insensitive because vehicleDefinition paths from the game
    data are lowercase while impl filenames use proper casing (AEGS_Gladius).

    Args:
        vehicle_impls: dict from parse_vehicle_implementations
        vehicle_definition: path like "scripts/.../xml/aegs_gladius.xml" (lowercase)
        class_name: fallback className like "AEGS_Gladius"

    Returns:
        parsed vehicle impl data dict, or None
    """
    # Build a case-insensitive index once (cached on the dict)
    idx = vehicle_impls.get("__lower_index__")
    if idx is None:
        idx = {k.lower(): k for k in vehicle_impls.keys() if not k.startswith("__")}
        vehicle_impls["__lower_index__"] = idx

    def _get(key):
        orig = idx.get(key.lower())
        return vehicle_impls.get(orig) if orig else None

    # Try by className exact match FIRST. Modifications/<Variant>.xml files
    # supersede the base impl when present — e.g. AEGS_Vanguard_Sentinel.xml
    # in Modifications/ overrides AEGS_Vanguard.xml's port types/sizes for
    # the Sentinel variant. The vehicle's vehicleDefinition still points to
    # the base file, so we have to prefer className for the lookup.
    data = _get(class_name)
    if data:
        return data

    # Try by vehicleDefinition filename
    if vehicle_definition:
        basename = os.path.splitext(os.path.basename(vehicle_definition))[0]
        data = _get(basename)
        if data:
            return data

    # Try matching by removing common suffixes
    base = class_name.split("_")
    for i in range(len(base), 1, -1):
        candidate = "_".join(base[:i])
        data = _get(candidate)
        if data:
            return data

    return None
