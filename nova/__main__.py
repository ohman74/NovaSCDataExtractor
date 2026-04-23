"""Nova Star Citizen Data Extractor - CLI entry point.

Usage:
    python -m nova
    python -m nova --config path/to/config.json
    python -m nova --channel PTU
    python -m nova --force
    python -m nova --only ships
"""

import argparse
import json
import os
import sys
import time

from . import __version__
from .config import Config
from .tool_downloader import ensure_tools
from .extractor import (extract_all_xml_and_dcb, get_entity_files, get_localization_file,
                          get_vehicle_impl_files, scan_cryxml_binaries)
from .converter import convert_game_dcb, convert_entities
from .dataforge_parser import stream_parse_dataforge
from .entity_parser import parse_entity_file
from .vehicle_impl_parser import parse_vehicle_implementations
from .utils import parse_localization, resolve_name
from .cosmetic_classifier import (
    identify_cosmetic_variants,
    load_impl_xml_modifications,
)
from .builders.slices import (
    build_vehicle_metadata,
    build_vehicle_stats,
    build_vehicle_hardpoints,
    build_vehicle_equipment,
    build_fps_equipment,
)


class BuildContext:
    """Shared context passed to all builders."""
    def __init__(self, items_by_class, vehicles_by_class, guid_to_class,
                 manufacturers, ammo_params, translations, vehicle_impls=None,
                 inventory_containers=None, gimbal_modifiers=None,
                 weapon_pool_sizes=None, shield_pool_sizes=None,
                 inclusion_modes=None, cosmetic_variants=None):
        self.items = items_by_class
        self.vehicles = vehicles_by_class
        self.guids = guid_to_class
        self.manufacturers = manufacturers
        self.ammo = ammo_params
        self.translations = translations
        self.vehicle_impls = vehicle_impls or {}
        self.inventory_containers = inventory_containers or {}
        self.gimbal_modifiers = gimbal_modifiers or {}
        self.weapon_pool_sizes = weapon_pool_sizes or {}
        self.shield_pool_sizes = shield_pool_sizes or {}
        # className -> EAEntityDataParams.inclusionMode ("ReadyToInclude" /
        # "DoNotInclude" / ""). Populated from per-ship entity XMLs. Used by
        # the ships filter to drop records CIG flagged not-for-PU.
        self.inclusion_modes = inclusion_modes or {}
        # Set of ClassNames identified as cosmetic-only variants of another
        # ship sharing the same vehicleDefinition. Populated by the
        # cosmetic_classifier. The extractor filters these so each cosmetic
        # group is represented by its base ClassName only.
        self.cosmetic_variants = cosmetic_variants or set()

    def resolve_name(self, raw_name):
        return resolve_name(raw_name, self.translations)

    def get_manufacturer(self, guid):
        """Resolve a manufacturer GUID to {code, name}."""
        if not guid or guid == "00000000-0000-0000-0000-000000000000":
            return None
        mfr = self.manufacturers.get(guid)
        if mfr:
            name = self.resolve_name(mfr["name"])
            # Keep @LOC_PLACEHOLDER as-is; convert "<= PLACEHOLDER =>" back
            if name == "<= PLACEHOLDER =>":
                name = "@LOC_PLACEHOLDER"
            result = {"Code": mfr["code"]}
            # Keep @LOC_PLACEHOLDER, exclude other unresolved @keys and empty
            if name == "<= PLACEHOLDER =>" or name == "@LOC_PLACEHOLDER":
                result["Name"] = "@LOC_PLACEHOLDER"
            elif name and not name.startswith("@"):
                result["Name"] = name
            return result
        return None

    def get_ammo(self, guid):
        """Get ammo params by GUID."""
        if not guid or guid == "00000000-0000-0000-0000-000000000000":
            return None
        return self.ammo.get(guid)

    def get_item(self, class_name):
        """Look up an item by className."""
        return self.items.get(class_name)

    def get_inventory_capacity(self, guid):
        """Get inventory container capacity in SCU by GUID."""
        if not guid or guid == "00000000-0000-0000-0000-000000000000":
            return 0
        container = self.inventory_containers.get(guid)
        if container:
            return container.get("capacity", 0)
        return 0

    def resolve_guid(self, guid):
        """Resolve a GUID to a className."""
        if not guid or guid == "00000000-0000-0000-0000-000000000000":
            return None
        return self.guids.get(guid)

    def get_gimbal_modifier(self, guid):
        """Get gimbal mode modifier data by GUID."""
        if not guid or guid == "00000000-0000-0000-0000-000000000000":
            return None
        return self.gimbal_modifiers.get(guid)


# Builder registry: (filename, builder_fn, uses_vehicles)
# All builders receive BuildContext as first arg
BUILDERS = {
    "vehicle_metadata":   ("vehicle_metadata.json",   build_vehicle_metadata,   True),
    "vehicle_stats":      ("vehicle_stats.json",      build_vehicle_stats,      True),
    "vehicle_hardpoints": ("vehicle_hardpoints.json", build_vehicle_hardpoints, True),
    "vehicle_equipment":  ("vehicle_equipment.json",  build_vehicle_equipment,  False),
    "fps_equipment":      ("fps_equipment.json",      build_fps_equipment,      False),
}


def main():
    parser = argparse.ArgumentParser(
        description=f"Nova Star Citizen Data Extractor v{__version__}"
    )
    parser.add_argument("--config", default=None, help="Path to nova_config.json")
    parser.add_argument("--channel", default=None, help="Override channel (LIVE, PTU)")
    parser.add_argument("--force", action="store_true", help="Force re-extraction (bypass cache)")
    parser.add_argument("--only", nargs="+", choices=list(BUILDERS.keys()),
                        help="Extract only specific categories")
    args = parser.parse_args()

    print(f"=== Nova Star Citizen Data Extractor v{__version__} ===\n")

    # Load config
    config_path = args.config
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nova_config.json")

    if not os.path.isfile(config_path):
        print(f"[ERROR] Config not found: {config_path}")
        print("Please create nova_config.json with your SC install path.")
        sys.exit(1)

    config = Config(config_path)

    if args.channel:
        config.sc_live_path = os.path.join(
            os.path.dirname(config.sc_live_path), args.channel
        )
        config.p4k_path = os.path.join(config.sc_live_path, "Data.p4k")

    config.ensure_dirs()

    # Clear cache if forced
    if args.force:
        print("[FORCE] Clearing cache...")
        import shutil
        if os.path.isdir(config.cache_dir):
            shutil.rmtree(config.cache_dir)
        config.ensure_dirs()

    # Ensure tools
    if not ensure_tools(config.tools_dir):
        print("[ERROR] Failed to set up tools. Please download unp4k manually.")
        sys.exit(1)

    # Validate
    errors = config.validate()
    if errors:
        for e in errors:
            print(f"[ERROR] {e}")
        sys.exit(1)

    # Get game version
    version_info = config.get_version_info()
    game_version = version_info["branch"]
    version_label = version_info["version"] or "unknown"
    print(f"\nGame branch:   {game_version}")
    print(f"Build version: {version_label}")
    if version_info["p4_change"]:
        print(f"P4 changelist: {version_info['p4_change']}")
    print(f"Data.p4k: {config.p4k_path}")
    p4k_size = os.path.getsize(config.p4k_path) / (1024 * 1024 * 1024)
    print(f"Data.p4k size: {p4k_size:.1f} GB")

    # Staleness check: cache extracted from a different p4k than the one on disk
    staleness = config.is_cache_stale()
    if staleness["stale"] and not args.force:
        from datetime import datetime
        c_mtime = datetime.fromtimestamp(staleness["cache_mtime"]).strftime("%Y-%m-%d %H:%M")
        p_mtime = datetime.fromtimestamp(staleness["p4k_mtime"]).strftime("%Y-%m-%d %H:%M")
        print(f"\n[WARN] Cache is older than Data.p4k (cache {c_mtime} vs p4k {p_mtime}).")
        print("       Reported gameVersion reflects the current Live manifest, but the")
        print("       extracted data is from the previous p4k contents. Re-run with")
        print("       --force to invalidate the cache and extract from current p4k.")

    start_time = time.time()

    # Stage 1: Extract all XML + DCB files in one pass
    dcb_path = extract_all_xml_and_dcb(config)

    # Stage 2: Convert DCB to XML
    xml_path = convert_game_dcb(config, dcb_path)

    # Stage 3: Get entity files (already extracted in stage 1)
    entity_files = []
    for entity_type in ["spaceships", "groundvehicles"]:
        found = get_entity_files(config, entity_type)
        print(f"  Found {len(found)} {entity_type} entity files")
        entity_files.extend(found)

    # Scan cache for CryXML-binary .xml files under known-binary directories
    # (covers vehicle implementation files + any other newly added binary XMLs).
    cryxml_files = scan_cryxml_binaries(config)
    # Exclude ones already in entity_files to avoid double-queueing
    seen_paths = {os.path.abspath(p) for p in entity_files}
    for p in cryxml_files:
        if os.path.abspath(p) not in seen_paths:
            entity_files.append(p)
    print(f"  Found {len(cryxml_files)} CryXML-binary .xml files needing conversion")

    # Stage 4: Convert entity files (CryXML binary -> readable XML)
    if entity_files:
        entity_xml_map = convert_entities(config, entity_files)
    else:
        print("  [WARN] No entity files found.")
        entity_xml_map = {}

    # Stage 5: Get localization
    loc_path = get_localization_file(config)

    # Parse everything
    print("\n[PARSE] Parsing DataForge data...")
    (items_by_class, vehicles_by_class, guid_to_class, manufacturers,
     ammo_params, inventory_containers, gimbal_modifiers) = \
        stream_parse_dataforge(xml_path, config.cache_dir)

    print("\n[PARSE] Parsing entity files...")
    entity_data_map = {}
    weapon_pool_sizes = {}  # className (lower) -> pool size
    shield_pool_sizes = {}  # className (lower) -> shield maxItemCount
    inclusion_modes = {}    # className -> EAEntityDataParams.inclusionMode
    import re
    _POOL_RE = re.compile(r'FixedPowerPool\s+itemType="WeaponGun"\s+poolSize="(\d+)"')
    _SHIELD_POOL_RE = re.compile(r'DynamicPowerPool\s+itemType="Shield"\s+maxItemCount="(-?\d+)"')
    _INCLUSION_RE = re.compile(
        r'EAEntityDataParams[^>]*\binclusionMode="([^"]*)"'
    )
    _ROOT_TAG_RE = re.compile(r'<EntityClassDefinition\.(\w+)')
    for original, xml_file in entity_xml_map.items():
        data = parse_entity_file(xml_file)
        parsed_cn = ""
        if data:
            parsed_cn = data.get("ClassName", data.get("className", ""))
            if not parsed_cn:
                parsed_cn = os.path.splitext(os.path.basename(original))[0]
            entity_data_map[parsed_cn] = data
        # pool sizes are keyed by lowercase filename basename (existing convention);
        # inclusion_modes are keyed by the parsed CamelCase ClassName to match
        # ctx.vehicles.
        fname_cn = os.path.splitext(os.path.basename(original))[0]
        try:
            with open(xml_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            m = _POOL_RE.search(content)
            if m:
                weapon_pool_sizes[fname_cn.lower()] = int(m.group(1))
            m2 = _SHIELD_POOL_RE.search(content)
            if m2:
                val = int(m2.group(1))
                if val > 0:  # -1 means unlimited, don't emit
                    shield_pool_sizes[fname_cn.lower()] = val
            m3 = _INCLUSION_RE.search(content)
            if m3:
                # The XML root is <EntityClassDefinition.<ClassName> …> —
                # extract the CamelCase class name directly so it matches
                # ctx.vehicles keys (not the lowercased filename).
                mr = _ROOT_TAG_RE.search(content)
                cn_key = mr.group(1) if mr else (parsed_cn or fname_cn)
                inclusion_modes[cn_key] = m3.group(1)
        except Exception:
            pass
    print(f"  Parsed {len(entity_data_map)} entity files, {len(weapon_pool_sizes)} weapon pool sizes, {len(shield_pool_sizes)} shield pool sizes, {len(inclusion_modes)} inclusion flags")

    print("\n[PARSE] Loading localization...")
    translations = parse_localization(loc_path)
    print(f"  Loaded {len(translations)} translations")

    print("\n[PARSE] Parsing vehicle implementations...")
    vehicle_impls = parse_vehicle_implementations(config.cache_dir)

    print("\n[PARSE] Classifying cosmetic-only ship variants...")
    # Per-ClassName path to the per-ship entity XML (already converted).
    entity_xml_by_class = {}
    for original, xml_file in entity_xml_map.items():
        # entity_xml_map keys are original file paths; look up by basename
        # (lowercased) matches the ClassName case-insensitively, but
        # entity_data_map keys are the CamelCase ClassNames. Prefer those.
        cn_lower = os.path.splitext(os.path.basename(original))[0].lower()
        # Find the CamelCase ClassName matching this file stem.
        # Use entity_data_map if it was parsed; otherwise fall back to
        # vehicles_by_class keys.
        matched = None
        for cn in vehicles_by_class:
            if cn.lower() == cn_lower:
                matched = cn
                break
        if matched:
            entity_xml_by_class[matched] = xml_file

    # Parse impl-XML <Modification> blocks for rename-only detection.
    impl_dirs = [
        os.path.join(config.cache_dir, "Data", "Scripts", "Entities",
                      "Vehicles", "Implementations", "Xml"),
    ]
    impl_modifications = load_impl_xml_modifications(impl_dirs)

    cosmetic_variants = identify_cosmetic_variants(
        vehicles_by_class, entity_xml_by_class, items_by_class, impl_modifications,
    )
    print(f"  Identified {len(cosmetic_variants)} cosmetic-only variants")
    # Emit for downstream audit tools (compare_matrix) so they can recognise
    # matrix SKUs intentionally omitted from our output as cosmetic-of-base
    # rather than reporting them as gaps.
    cv_path = os.path.join(config.cache_dir, "cosmetic_variants.json")
    with open(cv_path, "w", encoding="utf-8") as f:
        json.dump(sorted(cosmetic_variants), f, indent=2)

    # Build context shared by all builders
    ctx = BuildContext(items_by_class, vehicles_by_class, guid_to_class,
                       manufacturers, ammo_params, translations, vehicle_impls,
                       inventory_containers, gimbal_modifiers, weapon_pool_sizes,
                       shield_pool_sizes, inclusion_modes, cosmetic_variants)

    # Build output
    categories = args.only if args.only else list(BUILDERS.keys())

    print(f"\n[BUILD] Building {len(categories)} dataset(s)...")

    for category in categories:
        filename, builder_fn, uses_vehicles = BUILDERS[category]
        print(f"\n  Building {category}...")
        result = builder_fn(ctx)

        output_path = os.path.join(config.output_dir, filename)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  Wrote {output_path} ({len(result)} items)")

    # Write metadata
    metadata = {
        "gameVersion": game_version,
        "buildVersion": version_info["version"],
        "p4Change": version_info["p4_change"],
        "buildDate": version_info["build_date"],
        "channel": os.path.basename(config.sc_live_path),
        "extractionTimestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "novaVersion": __version__,
        "counts": {},
    }

    for category in categories:
        filename = BUILDERS[category][0]
        output_path = os.path.join(config.output_dir, filename)
        if os.path.isfile(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            metadata["counts"][category] = len(data)

    meta_path = os.path.join(config.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    elapsed = time.time() - start_time
    print(f"\n=== Done! Total time: {elapsed:.0f}s ===")
    print(f"Output: {config.output_dir}")
    for category in categories:
        filename = BUILDERS[category][0]
        count = metadata["counts"].get(category, "?")
        print(f"  {filename}: {count} items")


if __name__ == "__main__":
    main()
