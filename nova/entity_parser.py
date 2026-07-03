"""Parse individual ship/vehicle entity XML files for hardpoint and loadout data."""

import os
import xml.etree.ElementTree as ET


def parse_entity_file(xml_path, raw=None):
    """Parse a single entity XML file.

    `raw` optionally carries the file's bytes when the caller already read
    them (avoids a second disk read); xml_path is still used for messages.
    Returns a dict with the entity's component hierarchy, ports, and loadouts.
    Returns None if the file cannot be parsed.
    """
    try:
        if raw is not None:
            root = ET.fromstring(raw)
        else:
            root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        print(f"  [WARN] Failed to parse {os.path.basename(xml_path)}: {e}")
        return None

    entity = _elem_to_dict(root)
    return entity


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
