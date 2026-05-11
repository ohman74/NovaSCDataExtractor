"""Classify pairs of ship records as cosmetic-only or functional.

Two ships sharing the same `vehicleDefinition` are cosmetic twins iff
they differ only in fields that don't affect gameplay. This classifier
uses an ALLOW-LIST of gameplay-relevant signals — anything not on the
list is cosmetic by default. The opposite polarity (deny-list of
cosmetic XML paths) requires constant maintenance whenever CIG adds a
new effect / UI / state-machine path; the allow-list approach treats
new structural noise as cosmetic without code changes.

The signals checked:

  1. Loadout-port hardware swaps where the swapped item carries a
     gameplay item type (weapons, shields, power, coolers, q-drive,
     thrusters, radar, fuel intake/tank, armor, modules, cargo grid,
     mining/salvage tools, EMP/QED, life support, flight controller,
     etc.) AND the items are not item-cosmetic-equivalent. Boost
     capacity lives on the FlightController item (IFCSParams) and is
     naturally caught by the deep item compare.

  2. Global ship attributes under whitelisted top-level XML paths
     (`VehicleComponentParams` crewSize/dimensions/movementClass/etc.,
     `SSCSignatureSystemParams` emissions, ship insurance params).

  3. Modification blocks whose <Elems> reference non-cosmetic ids.

Everything else (paint, decals, materials, particle effects, UI
prompts, state machines, internal [HEX] handles, self-referencing
tags, localization strings, helper-port swaps, seat/door/light/landing
controllers, self-destruct) is cosmetic by default.

The extractor uses `identify_cosmetic_variants()` during build to
populate the variant→base mapping written to
`cache/cosmetic_variants.json`.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Iterable


# ───────────────────────── gameplay allow-lists ──────────────────────────

# Item types whose presence at a loadout port marks the port as
# gameplay-relevant. Items at non-gameplay ports (paint, seats, doors,
# lights, displays, decals, landing helpers, self-destruct, ...) are
# ignored regardless of whether they differ.
#
# Liberal on controllers — they're often generic across ships and
# items_cosmetic_equivalent gates per-ship custom variants by deep
# component compare. The cost of a false-positive controller is one
# extra ship marked functional; the cost of a false-negative on real
# hardware is a wrong cosmetic-twin classification, so we err toward
# inclusion.
GAMEPLAY_ITEM_TYPES = frozenset({
    # Weapons + ordnance
    "WeaponGun", "WeaponDefensive", "WeaponMount", "WeaponMining",
    "WeaponAttachment",
    "MissileLauncher", "GroundVehicleMissileLauncher", "BombLauncher",
    "Missile", "Bomb", "SpaceMine", "AmmoBox",
    "Turret", "TurretBase", "UtilityTurret",
    # Defense
    "Shield", "Armor",
    # Power & cooling
    "PowerPlant", "Battery", "Cooler",
    # Quantum / interdiction
    "QuantumDrive", "JumpDrive", "QuantumFuelTank",
    "EMP", "QuantumInterdictionGenerator",
    # Fuel
    "FuelIntake", "FuelTank", "ExternalFuelTank",
    # Sensors
    "Radar", "Scanner", "Sensor", "FPS_Radar",
    # Life support / environment
    "LifeSupportGenerator", "LifeSupportVent", "GravityGenerator",
    # Propulsion
    "MainThruster", "ManneuverThruster",
    # Modular / cargo / docking
    "Module", "Cargo", "CargoGrid", "DockingCollar",
    "TractorBeam", "TowingBeam",
    # Mining / salvage
    "MiningModifier",
    "SalvageHead", "SalvageFieldEmitter", "SalvageFieldSupporter",
    "SalvageFillerStation", "SalvageInternalStorage", "SalvageModifier",
    # Identity
    "Transponder",
    # Controllers (FlightController = the "flight blade"; others handle
    # firing groups, capacitor balance, etc.). Generic shared controllers
    # pass items_cosmetic_equivalent and don't trigger functional flagging.
    "FlightController", "WheeledController",
    "ShieldController", "CapacitorAssignmentController",
    "WeaponController", "MissileController", "CoolerController",
    "FuelController", "EnergyController",
    "MiningController", "SalvageController",
    "AIModule", "TargetSelector",
})

# Whitelisted top-level ship-XML paths to compare directly. Within each
# path's attribute set, denied attrs are ignored. Anything else differing
# at a whitelisted path is a functional diff.
GAMEPLAY_GLOBAL_PATHS = (
    "//Components/VehicleComponentParams",
    "//Components/SSCSignatureSystemParams",
    "//StaticEntityClassData/SEntityInsuranceProperties/shipInsuranceParams",
)
GAMEPLAY_GLOBAL_ATTR_DENY = {
    "//Components/VehicleComponentParams": frozenset({
        "vehicleName", "vehicleDescription", "vehicleImagePath",
        "vehicleCareer", "vehicleRole",
        "modification",  # checked separately via _modification_is_cosmetic
        # AI-only behavior flags. Player-owned variants share the same
        # physical ship; these flags only steer NPC pilots / spawn rules.
        "dogfightEnabled", "aiDamageModifiers", "ignoreHostility",
    }),
    "//StaticEntityClassData/SEntityInsuranceProperties/shipInsuranceParams":
        frozenset({"shipEntityClassName"}),  # self-reference
}

# Subtrees rooted under a GAMEPLAY_GLOBAL_PATHS prefix that we still want
# to skip. Interior socpak swaps (pirate decor, cargo-bay decoration,
# NPC-spawn placements) sit under VehicleComponentParams/objectContainers
# and aren't player-controlled gameplay — actual cargo capacity comes
# from CargoGrid items at hardpoint_cargogrid_module ports.
GAMEPLAY_GLOBAL_PATH_EXCLUDE = (
    "//Components/VehicleComponentParams/objectContainers",
)

# (idRef, name) pairs inside a <Modification> <Elems> block that count
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
    "SActorUsableParams",  # carries self-referencing tags (parent ship's className)
}
COSMETIC_ATTACHDEF_FIELDS = {
    "name", "description", "shortName", "displayName",
    "tags", "requiredTags",  # commonly self-reference the parent ship
}
ITEM_TOPLEVEL_IGNORE = {"className", "guid", "path", "_is_vehicle"}


# ───────────────────────────── XML helpers ───────────────────────────────

_GUID_INDEX_CACHE: dict[int, dict[str, str]] = {}


def _guid_index_for(items_db):
    """Build / cache a {guid_lower: className} map for items_db."""
    key = id(items_db)
    cached = _GUID_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    idx = {rec["guid"].lower(): cn
           for cn, rec in items_db.items() if rec.get("guid")}
    _GUID_INDEX_CACHE[key] = idx
    return idx


def _loadout_ports(xml_path, items_db):
    """Return {port_name: className} for the entity XML.

    Resolves entityClassReference (GUID) to className via items_db so
    that two ships with identical loadouts but mixed name/GUID refs
    compare equal.
    """
    guid_to_class = _guid_index_for(items_db)
    out = {}
    for e in ET.parse(xml_path).getroot().iter("SItemPortLoadoutEntryParams"):
        name = e.get("itemPortName", "")
        if not name or name in out:
            continue
        cls = e.get("entityClassName", "")
        if not cls:
            ref = e.get("entityClassReference", "")
            if ref:
                cls = guid_to_class.get(ref.lower(), ref)
        out[name] = cls
    return out


def _walk_paths(xml_path, allowed_prefixes):
    """Walk entity XML; collect attrs at every node whose path starts
    with one of `allowed_prefixes`. Returns {path: [attrs_dict, ...]}.
    Multi-instance paths (e.g. multiple particle entries) preserve order.
    """
    out = defaultdict(list)
    tree = ET.parse(xml_path)

    def walk(e, p=""):
        tag = e.tag
        if tag.startswith("EntityClassDefinition."):
            tag = "X"
        pp = f"{p}/{tag}" if p else "/"
        if any(pp.startswith(pfx) for pfx in allowed_prefixes):
            attrs = {k: v for k, v in e.attrib.items()
                     if k not in ("__ref", "__path")}
            out[pp].append(attrs)
        for c in e:
            walk(c, pp)

    walk(tree.getroot())
    return out


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


def _is_gameplay_port(item_a, item_b, items_db):
    """A port is gameplay-relevant iff at least one side's item carries a
    type in GAMEPLAY_ITEM_TYPES. Empty / unknown items default to non-
    gameplay (skip).
    """
    for cn in (item_a, item_b):
        if not cn:
            continue
        rec = items_db.get(cn)
        if not rec:
            continue
        ad = rec.get("attachDef") or {}
        if ad.get("type") in GAMEPLAY_ITEM_TYPES:
            return True
    return False


# ─────────────────────────── pair classifier ─────────────────────────────

def classify_pair(base_path, other_path, base_impl_path, impl_modifications, items_db):
    """Classify two ship entity XMLs as 'cosmetic' or 'functional'.

    Returns (kind, details). `kind` is 'cosmetic' or 'functional'.
    `details` lists the functional ports/paths plus the cosmetic-port
    diffs that were ignored, for audit.
    """
    functional_ports = []
    cosmetic_ports = []
    functional_paths = []

    # 1. Loadout-port hardware swaps.
    ap = _loadout_ports(base_path, items_db)
    bp = _loadout_ports(other_path, items_db)
    for name in sorted(set(ap) | set(bp)):
        ai, bi = ap.get(name, ""), bp.get(name, "")
        if ai == bi:
            continue
        if not _is_gameplay_port(ai, bi, items_db):
            cosmetic_ports.append(name)
            continue
        if items_cosmetic_equivalent(items_db, ai, bi):
            cosmetic_ports.append(name)
            continue
        functional_ports.append((name, ai, bi))

    # 2. Global ship-attribute diffs at whitelisted paths.
    a = _walk_paths(base_path, GAMEPLAY_GLOBAL_PATHS)
    b = _walk_paths(other_path, GAMEPLAY_GLOBAL_PATHS)
    for p in sorted(set(a) | set(b)):
        if any(p.startswith(pfx) for pfx in GAMEPLAY_GLOBAL_PATH_EXCLUDE):
            continue
        av, bv = a.get(p, []), b.get(p, [])
        if av == bv:
            continue
        if len(av) != len(bv):
            functional_paths.append(p)
            continue
        deny = GAMEPLAY_GLOBAL_ATTR_DENY.get(p, frozenset())
        all_equal = True
        for ea, eb in zip(av, bv):
            ka = {k: v for k, v in ea.items() if k not in deny}
            kb = {k: v for k, v in eb.items() if k not in deny}
            # Modification name is in `deny` for VehicleComponentParams,
            # so it never reaches here. Below is only reachable if a
            # future maintainer removes it from the deny-set.
            if (p == "//Components/VehicleComponentParams"
                    and ka.get("modification") != kb.get("modification")):
                a_mod = ka.get("modification", "")
                b_mod = kb.get("modification", "")
                if (_modification_is_cosmetic(base_impl_path, a_mod, impl_modifications)
                        and _modification_is_cosmetic(base_impl_path, b_mod, impl_modifications)):
                    ka.pop("modification", None)
                    kb.pop("modification", None)
            if ka != kb:
                all_equal = False
                break
        if not all_equal:
            functional_paths.append(p)

    # 3. Modification-only diffs aren't separately checked here because the
    # modification attribute is part of VehicleComponentParams (handled in
    # the loop above when not denied) and the actual modification block
    # contents only matter if they appear as XML diffs — which they don't,
    # because modifications are loaded by the impl XML at runtime, not
    # serialized into the per-ship entity XML.

    details = {
        "cosmetic_ports": cosmetic_ports,
        "functional_ports": functional_ports,
        "functional_paths": functional_paths,
    }
    if functional_ports or functional_paths:
        return "functional", details
    return "cosmetic", details


# ───────────────────────── extractor integration ─────────────────────────

def identify_cosmetic_variants(
    vehicles_by_class: dict,
    entity_xml_by_class: dict,
    items_db: dict,
    impl_modifications: dict,
    kept_class_names: Iterable[str] | None = None,
) -> dict:
    """Map each cosmetic-variant ClassName to its base ClassName.

    Two ships sharing the same `vehicleDefinition` are pair-classified;
    if they differ only in cosmetic / non-gameplay fields, the longer-
    named member is recorded as a cosmetic variant of the shorter-named
    base. Sibling-aware: handles groups like {F8, F8C, F8C_Plat} where
    F8 is shortest but F8C_Plat is cosmetic to F8C, not to F8.
    """
    kept = set(kept_class_names) if kept_class_names is not None else set(vehicles_by_class)
    by_impl = defaultdict(list)
    for cn, record in vehicles_by_class.items():
        if cn not in kept:
            continue
        vd = (record.get("vehicle") or {}).get("vehicleDefinition", "").lower()
        if vd and cn in entity_xml_by_class:
            by_impl[vd].append(cn)

    variant_to_base = {}
    for impl, members in by_impl.items():
        if len(members) < 2:
            continue
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
                if kind == "cosmetic":
                    variant_to_base[cn] = base_cn
                    break
    return variant_to_base


def _impl_xml_for_vehicle(vehicle_record, impl_modifications):
    """Return the impl-XML path stored in the vehicle record's
    `vehicleDefinition`. Used by `_modification_is_cosmetic` (which
    extracts the basename to look up modifications)."""
    vd = (vehicle_record.get("vehicle") or {}).get("vehicleDefinition", "")
    return vd or ""
