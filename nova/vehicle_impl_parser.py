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

    print(f"  Parsed {parsed} vehicle implementations ({failed} failed)")
    return results


def _parse_vehicle_xml(filepath):
    """Parse a single vehicle implementation XML."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError:
        return None

    if root.tag != "Vehicle":
        return None

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

    return result


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
        "minSize": safe_int(ip_elem.get("minSize")),
        "maxSize": safe_int(ip_elem.get("maxSize")),
    }

    flags = ip_elem.get("flags", "")
    if flags:
        port["flags"] = [f.strip().lstrip("$") for f in flags.split() if f.strip()]
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

    Args:
        vehicle_impls: dict from parse_vehicle_implementations
        vehicle_definition: path like "Scripts/Entities/Vehicles/Implementations/Xml/AEGS_Gladius.xml"
        class_name: fallback className like "AEGS_Gladius"

    Returns:
        parsed vehicle impl data dict, or None
    """
    # Try by vehicleDefinition filename
    if vehicle_definition:
        basename = os.path.splitext(os.path.basename(vehicle_definition))[0]
        data = vehicle_impls.get(basename)
        if data:
            return data

    # Try by className (strip variant suffixes)
    for name in [class_name]:
        data = vehicle_impls.get(name)
        if data:
            return data

    # Try matching by removing common suffixes
    base = class_name.split("_")
    for i in range(len(base), 1, -1):
        candidate = "_".join(base[:i])
        data = vehicle_impls.get(candidate)
        if data:
            return data

    return None
