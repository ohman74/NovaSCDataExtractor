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


def read_member(z, info):
    """Read one socpak member, tolerating CIG's inconsistent path separators.

    ~83% of socpak members store the name with `\\` in the local file header
    while the central directory uses `/`. Python's zipfile compares the two and
    raises BadZipFile. Retry with the backslash spelling so a single odd member
    can't discard the whole archive.
    """
    try:
        return z.read(info)
    except zipfile.BadZipFile:
        saved = info.orig_filename
        info.orig_filename = info.filename.replace("/", "\\")
        try:
            return z.read(info)
        finally:
            info.orig_filename = saved


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
            for info in z.infolist():
                if not info.filename.endswith("_editor.xml"):
                    continue
                # Per-member guard: one unreadable editor XML must not discard
                # the placements already counted from this ship's other members.
                try:
                    content = read_member(z, info).decode("utf-8", errors="ignore")
                except (zipfile.BadZipFile, OSError):
                    continue
                for cn in _OBJECT_TYPE_RE.findall(content):
                    if cn in _INTERIOR_STORAGE_EXCLUDE:
                        continue
                    counts[cn] += 1
    except (zipfile.BadZipFile, OSError):
        pass
    return counts


# Placed loot containers bind to a SubHarvestableMultiConfigRecord through
# HarvestableComponent.HarvestableParams.looseSubConfigBase. In the binary
# .entxml the property name and the GUID are separated by NUL bytes, not
# whitespace, so the gap has to be matched permissively.
_MULTICONFIG_RE = re.compile(
    r"multiconfigref.{0,8}?"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.S,
)
# Nested object-container references, used to walk a module up to the system
# container that places it (module -> set -> PU/system/<system>/<body>.socpak).
_SOCPAK_REF_RE = re.compile(r"objectcontainers/([a-z0-9_/\-]+\.socpak)")
_TEXT_MEMBERS = (".entxml", ".xml", ".rmxml")


def _socpak_rel(cache_dir, path):
    """Normalise an absolute socpak path to `PU/loc/...` under ObjectContainers."""
    root = os.path.join(cache_dir, "Data", "ObjectContainers") + os.sep
    return path[len(root):].replace(os.sep, "/") if path.startswith(root) else path


def build_socpak_loot_index(cache_dir):
    """Index every ObjectContainer socpak for placed loot containers.

    Returns {"containers": {rel: {"presets": {guid: count}}},
             "refs": {rel: {child_rel: instance_count}}}

    Only socpaks that place at least one loot container land in `containers`,
    but `refs` is collected for every socpak so the caller can walk the
    placement chain.

    `instance_count` is the number of distinct `.entxml` members that
    reference the child, which is one per placed instance. That matters:
    a facility module is defined once but instantiated many times. Pyro IV
    references the Farro data-centre module from 10 entxml members, matching
    its 10 `Outpost_ASD_DF_Pyro4_FarroDataCenter_*` mission templates exactly;
    Pyro I references the Lazarus research module from 6, matching its 3
    Phoenix plus 3 Tithonus templates. Counting raw string occurrences instead
    double-counts, because a summary `.xml` member lists every child again.
    """
    oc_dir = os.path.join(cache_dir, "Data", "ObjectContainers")
    if not os.path.isdir(oc_dir):
        return {}

    index = {}
    refs = {}
    for root, _dirs, files in os.walk(oc_dir):
        for fn in files:
            if not fn.lower().endswith(".socpak"):
                continue
            full = os.path.join(root, fn)
            rel = _socpak_rel(cache_dir, full)
            presets = Counter()
            seen_refs = Counter()
            linked = set()
            try:
                z = zipfile.ZipFile(full)
            except (zipfile.BadZipFile, OSError):
                continue
            with z:
                for info in z.infolist():
                    if not info.filename.lower().endswith(_TEXT_MEMBERS):
                        continue
                    try:
                        data = read_member(z, info).decode("utf-8", errors="ignore").lower()
                    except (zipfile.BadZipFile, OSError):
                        continue
                    for guid in _MULTICONFIG_RE.findall(data):
                        presets[guid] += 1
                    found = set(_SOCPAK_REF_RE.findall(data))
                    if info.filename.lower().endswith(".entxml"):
                        # One entxml member per placed instance, so each
                        # member votes once no matter how often it names the
                        # child.
                        for child in found:
                            seen_refs[child] += 1
                    else:
                        # Summary members establish the edge but say nothing
                        # about how many copies exist.
                        linked.update(found)
            # A socpak always names itself; that self-reference is noise.
            seen_refs.pop(rel.lower(), None)
            linked.discard(rel.lower())
            # An edge seen only in a summary member still connects the chain;
            # assume a single instance rather than dropping it, which would
            # silently strand every module below it.
            for child in linked:
                seen_refs.setdefault(child, 1)
            refs[rel] = dict(seen_refs)
            if presets:
                index[rel] = {"presets": dict(presets), "refs": refs[rel]}

    # Keep the full reference graph so placement chains stay walkable even
    # through intermediate socpaks that hold no loot themselves.
    return {"containers": index, "refs": refs}


def resolve_placements(socpak_index):
    """Walk each loot-bearing socpak up to the system containers placing it.

    Returns {socpak_rel_path: {system socpak rel path: instance_count}}, where
    instance_count is how many copies of that module the system ends up with.
    A module is defined once but placed many times, so the multiplicities have
    to be multiplied along the chain and summed across alternative parents:
    the Lazarus research module holds 18 loot containers and Pyro I places it
    6 times, which is 108 containers in the world rather than 18.

    A module reachable from no system container yields an empty dict
    (unplaced dev content).
    """
    refs = socpak_index.get("refs", {})
    # child (lowercased) -> {parent (lowercased): times the parent places it}
    parents = {}
    for parent, children in refs.items():
        for child, count in children.items():
            parents.setdefault(child.lower(), {})[parent.lower()] = count

    def is_system(rel):
        return rel.startswith("pu/system/")

    cache = {}

    def instances(node, stack):
        """{system: multiplicity} for one module, memoised."""
        if is_system(node):
            return {node: 1}
        if node in cache:
            return cache[node]
        if node in stack:          # cyclic reference; contribute nothing
            return {}
        stack.add(node)
        total = {}
        for parent, mult in parents.get(node, {}).items():
            for system, count in instances(parent, stack).items():
                total[system] = total.get(system, 0) + count * mult
        stack.discard(node)
        cache[node] = total
        return total

    return {rel: dict(sorted(instances(rel.lower(), set()).items()))
            for rel in socpak_index.get("containers", {})}


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
