"""Parse ship-interior ObjectContainer .socpak archives.

Each ship entity XML lists `SVehicleObjectContainerParams.fileName` references
to `Data/ObjectContainers/Ships/{MFR}/{Ship}/*.socpak` archives. Inside each
socpak, the `*_editor.xml` member contains `<Object type="PersonalStorage_*"/>`
records — one per physical locker placement in the ship's interior.

This module walks the chain and emits a per-ship Counter of placement counts
keyed by item className.
"""
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

# Item-classNames that should be excluded from interior-storage counts.
# These are visual-only fixtures REF doesn't include in Storage:
#   - PersonalStorage_RSI_Com_Suit_Locker_Overhead — overhead suit lockers
#     placed in Polaris hab corridors; not gameplay storage hardpoints.
_INTERIOR_STORAGE_EXCLUDE = {
    "PersonalStorage_RSI_Com_Suit_Locker_Overhead",
}

_OBJECT_TYPE_RE = re.compile(r'type="(PersonalStorage_\w+)"')


def parse_ship_socpaks(entity_xml_path):
    """Return list of socpak fileName strings referenced by a ship entity.

    Returns empty list if entity XML is missing / unparseable / has no
    SVehicleObjectContainerParams elements.
    """
    try:
        tree = ET.parse(entity_xml_path)
    except (FileNotFoundError, ET.ParseError):
        return []
    paks = []
    for elem in tree.getroot().iter("SVehicleObjectContainerParams"):
        fn = elem.get("fileName", "")
        if fn.lower().endswith(".socpak"):
            paks.append(fn)
    return paks


def count_storage_placements(socpak_path):
    """Count PersonalStorage_X object placements in a socpak's editor XMLs.

    Returns Counter keyed by item className.
    """
    counts = Counter()
    if not os.path.isfile(socpak_path):
        return counts
    try:
        with zipfile.ZipFile(socpak_path) as z:
            for name in z.namelist():
                if not name.endswith("_editor.xml"):
                    continue
                content = z.read(name).decode("utf-8", errors="ignore")
                for cn in _OBJECT_TYPE_RE.findall(content):
                    if cn in _INTERIOR_STORAGE_EXCLUDE:
                        continue
                    counts[cn] += 1
    except (zipfile.BadZipFile, OSError):
        pass
    return counts


def build_ship_storage_index(cache_dir):
    """Walk every spaceship entity XML, follow its socpak refs, and tally
    interior storage placements per ship.

    Returns dict: {className: {item_classname: count, ...}, ...}
    Skips ships with no socpak refs or no PersonalStorage placements.
    """
    spaceships_dir = os.path.join(
        cache_dir, "Data", "Libs", "Foundry", "Records", "entities", "spaceships",
    )
    if not os.path.isdir(spaceships_dir):
        return {}

    index = {}
    for f in os.listdir(spaceships_dir):
        if not f.endswith(".xml"):
            continue
        entity_path = os.path.join(spaceships_dir, f)
        # ClassName: derive from filename (case-restoration via root tag).
        try:
            tree = ET.parse(entity_path)
            root = tree.getroot()
            # Tag is `EntityClassDefinition.AEGS_Reclaimer` etc.
            tag = root.tag
            if "." in tag:
                class_name = tag.split(".", 1)[1]
            else:
                class_name = os.path.splitext(f)[0]
        except (FileNotFoundError, ET.ParseError):
            continue

        paks = parse_ship_socpaks(entity_path)
        if not paks:
            continue

        total = Counter()
        for pak in paks:
            full = os.path.join(cache_dir, "Data", pak.replace("/", os.sep))
            total.update(count_storage_placements(full))

        if total:
            index[class_name] = dict(total)

    return index
