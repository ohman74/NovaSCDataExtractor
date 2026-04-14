"""Parse individual ship/vehicle entity XML files for hardpoint and loadout data."""

import os
import xml.etree.ElementTree as ET

from .utils import safe_float, safe_int, safe_bool


def parse_entity_file(xml_path):
    """Parse a single entity XML file.

    Returns a dict with the entity's component hierarchy, ports, and loadouts.
    Returns None if the file cannot be parsed.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"  [WARN] Failed to parse {os.path.basename(xml_path)}: {e}")
        return None

    entity = _elem_to_dict(root)
    return entity


def extract_ports(entity_data):
    """Extract all ports (hardpoints) from an entity definition.

    Returns a list of port dicts with:
    - name, minSize, maxSize, types, tags, defaultLoadout, subPorts
    """
    ports = []
    _walk_ports(entity_data, ports)
    return ports


def _walk_ports(data, ports, depth=0):
    """Recursively walk entity data to find port definitions."""
    if not isinstance(data, dict):
        return

    # Check for SItemPortContainerComponentParams or similar
    for key, value in data.items():
        if isinstance(value, dict):
            # Look for port definitions
            if "Ports" in value or "ports" in value:
                port_list = value.get("Ports") or value.get("ports")
                if isinstance(port_list, list):
                    for p in port_list:
                        port = _parse_port(p)
                        if port:
                            ports.append(port)
                elif isinstance(port_list, dict):
                    port = _parse_port(port_list)
                    if port:
                        ports.append(port)

            _walk_ports(value, ports, depth + 1)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _walk_ports(item, ports, depth + 1)


def _parse_port(port_data):
    """Parse a single port definition."""
    if not isinstance(port_data, dict):
        return None

    port = {
        "portName": port_data.get("Name", port_data.get("name", port_data.get("PortName", ""))),
        "minSize": safe_int(port_data.get("MinSize", port_data.get("minSize"))),
        "maxSize": safe_int(port_data.get("MaxSize", port_data.get("maxSize"))),
        "types": [],
        "tags": port_data.get("PortTags", port_data.get("Tags", "")),
        "requiredTags": port_data.get("RequiredTags", port_data.get("requiredTags", "")),
        "flags": safe_int(port_data.get("Flags", port_data.get("flags"))),
        "uneditable": safe_bool(port_data.get("Uneditable", port_data.get("uneditable"))),
    }

    # Parse types
    types = port_data.get("Types", port_data.get("types"))
    if isinstance(types, str):
        port["types"] = [t.strip() for t in types.split(",") if t.strip()]
    elif isinstance(types, list):
        port["types"] = types

    # Parse default loadout
    loadout = port_data.get("DefaultLoadout", port_data.get("defaultLoadout",
                port_data.get("Loadout", port_data.get("loadout"))))
    if loadout:
        if isinstance(loadout, dict):
            port["defaultLoadout"] = loadout.get("ClassName", loadout.get("className",
                                      loadout.get("__guid", "")))
        else:
            port["defaultLoadout"] = str(loadout)

    # Parse sub-ports recursively
    sub_ports_data = port_data.get("Ports", port_data.get("ports"))
    if sub_ports_data:
        sub_ports = []
        if isinstance(sub_ports_data, list):
            for sp in sub_ports_data:
                parsed = _parse_port(sp)
                if parsed:
                    sub_ports.append(parsed)
        elif isinstance(sub_ports_data, dict):
            parsed = _parse_port(sub_ports_data)
            if parsed:
                sub_ports.append(parsed)
        if sub_ports:
            port["subPorts"] = sub_ports

    return port


def classify_port(port):
    """Classify a port into a category based on its types and name.

    Returns one of:
        'pilotWeapon', 'remoteTurret', 'mannedTurret', 'pdcTurret',
        'missileRack', 'bombRack', 'utilityHardpoint', 'utilityTurret',
        'powerPlant', 'cooler', 'shield', 'quantumDrive', 'radar',
        'lifeSupport', 'controller', 'capacitor', 'module', 'unknown'
    """
    types = port.get("types", [])
    name = port.get("portName", "").lower()
    type_str = " ".join(str(t).lower() for t in types)

    # Component types
    if "powerplant" in type_str or "power_plant" in name:
        return "powerPlant"
    if "cooler" in type_str or "cooler" in name:
        return "cooler"
    if "shield" in type_str or "shield" in name:
        return "shield"
    if "quantumdrive" in type_str or "quantum" in name:
        return "quantumDrive"
    if "radar" in type_str or "radar" in name:
        return "radar"
    if "lifesupport" in type_str or "life_support" in name:
        return "lifeSupport"
    if "flightcontroller" in type_str or "controller" in name:
        return "controller"
    if "capacitor" in type_str:
        return "capacitor"

    # Weapon types
    if "missilerack" in type_str or "missile" in type_str:
        return "missileRack"
    if "bomb" in type_str:
        return "bombRack"
    if "turret" in type_str:
        if "pdc" in name or "point_def" in name:
            return "pdcTurret"
        if "remote" in name or "slaved" in name:
            return "remoteTurret"
        if "utility" in type_str:
            return "utilityTurret"
        return "mannedTurret"
    if "weapongun" in type_str or "weapon" in type_str:
        if "utility" in type_str:
            return "utilityHardpoint"
        return "pilotWeapon"

    if "module" in type_str:
        return "module"

    return "unknown"


def _elem_to_dict(elem):
    """Recursively convert an XML element to a dict."""
    result = dict(elem.attrib)

    children_by_tag = {}
    for child in elem:
        tag = child.tag
        child_dict = _elem_to_dict(child)
        if tag in children_by_tag:
            existing = children_by_tag[tag]
            if isinstance(existing, list):
                existing.append(child_dict)
            else:
                children_by_tag[tag] = [existing, child_dict]
        else:
            children_by_tag[tag] = child_dict

    result.update(children_by_tag)
    return result
