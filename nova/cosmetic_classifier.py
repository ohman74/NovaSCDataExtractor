"""Classify pairs of ship records as cosmetic-only or functional.

Two ships with the same `vehicleDefinition` (impl XML) are "cosmetic
twins" if every structural difference between their per-ship entity XMLs
is confined to cosmetic fields: palette/material GUIDs, localization
strings, self-referencing tags, interior-art filenames, paint/flair port
installs, rename-only impl-XML modification blocks, or items that are
themselves item-level cosmetic twins.

The extractor uses `identify_cosmetic_variants()` during build to
populate a set of ClassNames that should be filtered (keeping only the
base ship of each cosmetic group). The same helpers are reused by
`find_cosmetic_dupes.py` as a CLI audit tool.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Iterable


# ───────────────────────────── classification rules ──────────────────────

COSMETIC_PATH_PREFIXES = (
    "//Components/SGeometryResourceParams/Geometry/Geometry/Palette",
    "//Components/SGeometryResourceParams/Geometry/SubGeometry/Geometry/Palette",
    # Shader material / material-variant refs — visual only.
    "//Components/SGeometryResourceParams/Geometry/Geometry/Material",
    "//Components/SGeometryResourceParams/Geometry/SubGeometry/Geometry/Material",
    "//Components/SGeometryResourceParams/Material",  # materialVariants/SMaterialNodeParams
    "//Components/SAttachableComponentParams/AttachDef/Localization",
    # Default-loadout entries — port-level diff owns this semantics.
    "//Components/SEntityComponentDefaultLoadoutParams",
    # UI decal descriptors — canvas art / stickers, visual only.
    "//Components/UICanvasDecalDescriptorEntityComponentParams",
)
COSMETIC_ATTR_ALLOW = {
    "//Components/VehicleComponentParams": {
        "vehicleName", "vehicleDescription", "vehicleImagePath",
    },
    "//Components/SCItemPurchasableParams": {
        "displayName", "displayType", "displayThumbnail",
    },
    "//Components/SAttachableComponentParams/AttachDef": {
        "Tags", "RequiredTags",
    },
    "//StaticEntityClassData/SEntityInsuranceProperties/shipInsuranceParams": {
        "shipEntityClassName",
    },
}
# Multi-instance SItemPortDef path: checked via per-port-name attr diff.
COSMETIC_PORTDEF_ATTRS = {"PortTags"}
# Interior-art object-container fileName swaps (pirate decor etc.).
OBJECT_CONTAINER_PATH_SUFFIX = "SVehicleObjectContainerParams"

# (idRef, name) pairs inside a <Modification> <Elems> block that we count
# as cosmetic. Anything else marks the modification as functional.
COSMETIC_MOD_ELEMS = {
    ("modVehicle", "displayname"),
    ("modVehicle", "shortname"),
    ("modVehicle", "description"),
}

# Item-level cosmetic-equivalence allow-lists.
COSMETIC_ITEM_COMPONENTS = {
    "SGeometryResourceParams",
    "SEntityComponentObjectMetadataParams",
    # Actor-use slots carry self-referencing tags (parent ship's className).
    "SActorUsableParams",
}
COSMETIC_ATTACHDEF_FIELDS = {
    "name", "description", "shortName", "displayName",
    "tags", "requiredTags",  # commonly self-reference the parent ship
}
ITEM_TOPLEVEL_IGNORE = {"className", "guid", "path", "_is_vehicle"}


# ───────────────────────────── XML helpers ───────────────────────────────

def _flatten(xml_path):
    out = defaultdict(list)
    tree = ET.parse(xml_path)

    def walk(e, p=""):
        tag = e.tag
        if tag.startswith("EntityClassDefinition."):
            tag = "X"
        pp = f"{p}/{tag}" if p else "/"
        attrs = {k: v for k, v in e.attrib.items() if k not in ("__ref", "__path")}
        out[pp].append(attrs)
        for c in e:
            walk(c, pp)

    walk(tree.getroot())
    return out


def _loadout_ports(xml_path):
    out = {}
    for e in ET.parse(xml_path).getroot().iter("SItemPortLoadoutEntryParams"):
        name = e.get("itemPortName", "")
        cls = e.get("entityClassName", "") or e.get("entityClassReference", "")
        if name and name not in out:
            out[name] = cls
    return out


def _port_defs(xml_path):
    out = {}
    for e in ET.parse(xml_path).getroot().iter("SItemPortDef"):
        name = e.get("Name", "")
        if name:
            out[name] = dict(e.attrib)
    return out


def _port_def_diffs_are_cosmetic(base_path, other_path):
    a = _port_defs(base_path)
    b = _port_defs(other_path)
    if set(a) != set(b):
        return False
    for name in a:
        aa, bb = a[name], b[name]
        diffs = {k for k in set(aa) | set(bb) if aa.get(k) != bb.get(k)}
        if not diffs:
            continue
        if not diffs.issubset(COSMETIC_PORTDEF_ATTRS):
            return False
    return True


# ────────────────────────── modification resolver ────────────────────────

def load_impl_xml_modifications(impl_dirs):
    """Scan impl XML dirs; return {impl_basename.lower(): {mod_name: [elems]}}."""
    impl_index = {}
    for d in impl_dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".xml"):
                continue
            key = os.path.splitext(fn)[0].lower()
            try:
                tree = ET.parse(os.path.join(d, fn))
            except ET.ParseError:
                continue
            mods = {}
            for mod in tree.getroot().iter("Modification"):
                elems = []
                elems_parent = mod.find("Elems")
                if elems_parent is not None:
                    for e in elems_parent.findall("Elem"):
                        elems.append(
                            (e.get("idRef", ""), e.get("name", ""), e.get("value", ""))
                        )
                mods[mod.get("name", "")] = elems
            impl_index[key] = mods
    return impl_index


def _modification_is_cosmetic(impl_xml_path, mod_name, impl_modifications):
    if not mod_name:
        return True
    if not impl_xml_path:
        return False
    key = os.path.splitext(os.path.basename(impl_xml_path))[0].lower()
    mods = impl_modifications.get(key)
    if mods is None:
        return False
    if mod_name not in mods:
        return False
    for id_ref, name, _value in mods[mod_name]:
        if (id_ref, name) not in COSMETIC_MOD_ELEMS:
            return False
    return True


# ─────────────────────── item-level cosmetic-equivalence ─────────────────

def items_cosmetic_equivalent(items_db, cn_a, cn_b):
    """True iff the two item records differ only in cosmetic fields.

    Strict: unknown items and component keyset mismatches return False.
    """
    if cn_a == cn_b:
        return True
    if not cn_a or not cn_b:
        return False
    a = items_db.get(cn_a)
    b = items_db.get(cn_b)
    if not a or not b:
        return False

    # Top-level keys that should match exactly.
    for k in set(a) | set(b):
        if k in ITEM_TOPLEVEL_IGNORE:
            continue
        if k in ("attachDef", "components"):
            continue
        if a.get(k) != b.get(k):
            return False

    ad_a = a.get("attachDef") or {}
    ad_b = b.get("attachDef") or {}
    for k in set(ad_a) | set(ad_b):
        if k in COSMETIC_ATTACHDEF_FIELDS:
            continue
        if ad_a.get(k) != ad_b.get(k):
            return False

    ca = a.get("components") or {}
    cb = b.get("components") or {}
    if set(ca.keys()) != set(cb.keys()):
        return False
    for k in ca:
        if k in COSMETIC_ITEM_COMPONENTS:
            continue
        if ca[k] != cb[k]:
            return False
    return True


def _is_cosmetic_port(port_name):
    n = port_name.lower()
    return ("paint" in n) or ("flair" in n) or ("decal" in n)


# ─────────────────────────── pair classifier ─────────────────────────────

def classify_pair(base_path, other_path, base_impl_path, impl_modifications, items_db):
    """Returns: (kind, details)
    kind: 'identical' | 'cosmetic' | 'functional'
    """
    a = _flatten(base_path)
    b = _flatten(other_path)

    functional_paths = []
    cosmetic_paths = []

    portdef_cosmetic = _port_def_diffs_are_cosmetic(base_path, other_path)

    for p in sorted(set(a) | set(b)):
        if a.get(p) == b.get(p):
            continue

        if any(p.startswith(pfx) for pfx in COSMETIC_PATH_PREFIXES):
            cosmetic_paths.append(p)
            continue
        if p.endswith(OBJECT_CONTAINER_PATH_SUFFIX):
            cosmetic_paths.append(p)
            continue
        if p.startswith("//Components/SItemPortContainerComponentParams/Ports/SItemPortDef"):
            if portdef_cosmetic:
                cosmetic_paths.append(p)
                continue

        if p in COSMETIC_ATTR_ALLOW and len(a.get(p, [])) == 1 == len(b.get(p, [])):
            aa, bb = a[p][0], b[p][0]
            attr_diffs = {k for k in set(aa) | set(bb) if aa.get(k) != bb.get(k)}
            allowed = COSMETIC_ATTR_ALLOW[p]

            if p == "//Components/VehicleComponentParams" and "modification" in attr_diffs:
                a_mod = aa.get("modification", "")
                b_mod = bb.get("modification", "")
                a_cos = _modification_is_cosmetic(base_impl_path, a_mod, impl_modifications)
                b_cos = _modification_is_cosmetic(base_impl_path, b_mod, impl_modifications)
                if a_cos and b_cos:
                    attr_diffs.discard("modification")

            if attr_diffs.issubset(allowed):
                cosmetic_paths.append(p)
                continue

        functional_paths.append(p)

    ap = _loadout_ports(base_path)
    bp = _loadout_ports(other_path)
    functional_ports = []
    cosmetic_ports = []
    for name in sorted(set(ap) | set(bp)):
        ai, bi = ap.get(name, ""), bp.get(name, "")
        if ai == bi:
            continue
        if _is_cosmetic_port(name):
            cosmetic_ports.append(name)
            continue
        if items_cosmetic_equivalent(items_db, ai, bi):
            cosmetic_ports.append(name)
            continue
        functional_ports.append((name, ai, bi))

    details = {
        "cosmetic_paths": cosmetic_paths,
        "cosmetic_ports": cosmetic_ports,
        "functional_paths": functional_paths,
        "functional_ports": functional_ports,
    }
    if not functional_paths and not functional_ports:
        if not cosmetic_paths and not cosmetic_ports:
            return "identical", details
        return "cosmetic", details
    return "functional", details


# ───────────────────────── extractor integration ─────────────────────────

def identify_cosmetic_variants(
    vehicles_by_class: dict,
    entity_xml_by_class: dict,
    items_db: dict,
    impl_modifications: dict,
    kept_class_names: Iterable[str] | None = None,
) -> set:
    """Return the set of ClassNames that are cosmetic-only variants of
    another ship sharing the same `vehicleDefinition`.

    The *base* of each group is the shortest ClassName; every other member
    whose pair-classification against the base is 'cosmetic' or 'identical'
    is returned for filtering.

    Args:
        vehicles_by_class:   {ClassName: parsed vehicle record} (for vehicleDefinition).
        entity_xml_by_class: {ClassName: absolute path to per-ship entity XML}.
        items_db:            {ClassName: parsed item record} for item-level diffs.
        impl_modifications:  output of load_impl_xml_modifications().
        kept_class_names:    restrict consideration to these ClassNames (typically
                             the ships that survived earlier filters). None = all.

    Returns:
        Set of ClassNames that should be excluded as cosmetic duplicates.
    """
    kept = set(kept_class_names) if kept_class_names is not None else set(vehicles_by_class)
    # Group by vehicleDefinition.
    by_impl = defaultdict(list)
    for cn, record in vehicles_by_class.items():
        if cn not in kept:
            continue
        vd = (record.get("vehicle") or {}).get("vehicleDefinition", "").lower()
        if vd and cn in entity_xml_by_class:
            by_impl[vd].append(cn)

    to_drop = set()
    for impl, members in by_impl.items():
        if len(members) < 2:
            continue
        # Sort members by ClassName length (shortest first). For each member,
        # classify it against every SHORTER member; if any pair is cosmetic,
        # the longer member is a cosmetic variant of an existing base and
        # should be filtered. Sibling-aware: handles groups like
        # {F8, F8C, F8C_Plat} where F8 is shortest but F8C_Plat is cosmetic
        # to F8C, not to F8.
        members_sorted = sorted(members, key=lambda x: (len(x), x))
        for i, cn in enumerate(members_sorted):
            if i == 0:
                continue
            other_path = entity_xml_by_class[cn]
            for base_cn in members_sorted[:i]:
                base_path = entity_xml_by_class[base_cn]
                base_impl_path = _impl_xml_for_vehicle(
                    vehicles_by_class[base_cn], impl_modifications
                )
                try:
                    kind, _ = classify_pair(
                        base_path, other_path, base_impl_path,
                        impl_modifications, items_db,
                    )
                except ET.ParseError:
                    continue
                if kind in ("cosmetic", "identical"):
                    to_drop.add(cn)
                    break  # already identified as cosmetic twin of some base
    return to_drop


def _impl_xml_for_vehicle(vehicle_record, impl_modifications):
    """vehicle_record.vehicle.vehicleDefinition is a path like
    'Scripts/Entities/Vehicles/Implementations/Xml/aegs_gladius.xml'.
    The impl_modifications index is keyed by the bare filename stem (lowercase),
    so we return the basename here — _modification_is_cosmetic only reads it
    via os.path.basename anyway."""
    vd = (vehicle_record.get("vehicle") or {}).get("vehicleDefinition", "")
    if not vd:
        return ""
    return vd  # the basename is what _modification_is_cosmetic will extract
