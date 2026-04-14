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
from .extractor import extract_all_xml_and_dcb, get_entity_files, get_localization_file
from .converter import convert_game_dcb, convert_entities
from .dataforge_parser import stream_parse_dataforge
from .entity_parser import parse_entity_file
from .vehicle_impl_parser import parse_vehicle_implementations
from .utils import parse_localization, resolve_name
from .builders.ships import build_ships
from .builders.vehicles import build_vehicles
from .builders.ship_equipment import build_ship_equipment
from .builders.vehicle_equipment import build_vehicle_equipment
from .builders.fps_weapons import build_fps_weapons
from .builders.fps_attachments import build_fps_attachments


class BuildContext:
    """Shared context passed to all builders."""
    def __init__(self, items_by_class, vehicles_by_class, guid_to_class,
                 manufacturers, ammo_params, translations, vehicle_impls=None,
                 inventory_containers=None, gimbal_modifiers=None,
                 weapon_pool_sizes=None):
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
    "ships": ("ships.json", build_ships, True),
    "vehicles": ("vehicles.json", build_vehicles, True),
    "ship_equipment": ("ship_equipment.json", build_ship_equipment, False),
    "vehicle_equipment": ("vehicle_equipment.json", build_vehicle_equipment, False),
    "fps_weapons": ("fps_weapons.json", build_fps_weapons, False),
    "fps_attachments": ("fps_attachments.json", build_fps_attachments, False),
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
    game_version = config.get_game_version()
    print(f"\nGame version: {game_version}")
    print(f"Data.p4k: {config.p4k_path}")
    p4k_size = os.path.getsize(config.p4k_path) / (1024 * 1024 * 1024)
    print(f"Data.p4k size: {p4k_size:.1f} GB")

    start_time = time.time()

    # Stage 1: Extract all XML + DCB files in one pass
    dcb_path = extract_all_xml_and_dcb(config)

    # Stage 2: Convert DCB to XML
    xml_path = convert_game_dcb(config, dcb_path)

    # Stage 3: Get entity files (already extracted in stage 1)
    entity_files = []
    for entity_type in ["spaceships", "ground"]:
        found = get_entity_files(config, entity_type)
        print(f"  Found {len(found)} {entity_type} entity files")
        entity_files.extend(found)

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
    import re
    _POOL_RE = re.compile(r'FixedPowerPool\s+itemType="WeaponGun"\s+poolSize="(\d+)"')
    for original, xml_file in entity_xml_map.items():
        data = parse_entity_file(xml_file)
        if data:
            class_name = data.get("ClassName", data.get("className", ""))
            if not class_name:
                class_name = os.path.splitext(os.path.basename(original))[0]
            entity_data_map[class_name] = data

        # Extract weapon pool size from entity XML via regex (fast)
        try:
            with open(xml_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            m = _POOL_RE.search(content)
            if m:
                cn = os.path.splitext(os.path.basename(original))[0]
                weapon_pool_sizes[cn.lower()] = int(m.group(1))
        except Exception:
            pass
    print(f"  Parsed {len(entity_data_map)} entity files, {len(weapon_pool_sizes)} weapon pool sizes")

    print("\n[PARSE] Loading localization...")
    translations = parse_localization(loc_path)
    print(f"  Loaded {len(translations)} translations")

    print("\n[PARSE] Parsing vehicle implementations...")
    vehicle_impls = parse_vehicle_implementations(config.cache_dir)

    # Build context shared by all builders
    ctx = BuildContext(items_by_class, vehicles_by_class, guid_to_class,
                       manufacturers, ammo_params, translations, vehicle_impls,
                       inventory_containers, gimbal_modifiers, weapon_pool_sizes)

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
