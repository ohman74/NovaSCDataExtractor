"""Extract files from Data.p4k using unp4k.exe.

unp4k.exe behavior:
- Extracts files to CWD preserving directory structure
- Filter is a case-insensitive substring match on the archive path
- Special filter "xml" extracts all .xml files plus .dcb files
- Skips files that already exist on disk
- Output: one line per file like "ZStd | Plain | Data/path/to/file.ext"
"""

import os
import subprocess
import time


def extract_files(unp4k_path, p4k_path, pattern, output_dir, timeout=600):
    """Extract files matching pattern from Data.p4k.

    Args:
        unp4k_path: Path to unp4k.exe
        p4k_path: Path to Data.p4k
        pattern: Substring filter (e.g., "xml" for all XML+DCB files)
        output_dir: Directory to extract into (files extracted under CWD)
        timeout: Max seconds to wait

    Returns:
        List of extracted file paths
    """
    os.makedirs(output_dir, exist_ok=True)

    cmd = [unp4k_path, p4k_path, pattern]
    print(f"  Extracting with filter: {pattern}")
    print(f"  Output dir: {output_dir}")
    print(f"  This may take several minutes for a 143 GB archive...")

    start = time.time()
    result = subprocess.run(
        cmd,
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise RuntimeError(f"unp4k failed (exit {result.returncode}): {stderr}")

    # Count output lines to see how many files were processed
    lines = result.stdout.strip().splitlines() if result.stdout else []
    print(f"  unp4k processed {len(lines)} entries in {elapsed:.1f}s")

    # Collect all files in output directory
    extracted = []
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            extracted.append(os.path.join(root, f))

    print(f"  Total files in cache: {len(extracted)}")
    return extracted


def extract_all_xml_and_dcb(config):
    """Extract all XML and DCB files from Data.p4k in one pass.

    The "xml" filter is a special unp4k filter that extracts:
    - All .xml files (entity definitions, configs, etc.)
    - All .dcb files (DataForge databases like Game2.dcb)

    This is much more efficient than multiple targeted extractions
    since the 143 GB archive only needs to be scanned once.

    Returns:
        Tuple of (dcb_path, entity_xml_dir, localization_dir)
    """
    cache_dir = config.cache_dir
    data_dir = os.path.join(cache_dir, "Data")

    # Check if we already have cached extraction
    dcb_path = _find_dcb(data_dir)
    if dcb_path:
        print("\n[1/3] Using cached extraction")
        print(f"  DCB: {dcb_path}")
        return dcb_path

    print("\n[1/3] Extracting XML and DCB files from Data.p4k...")
    extract_files(
        config.unp4k_path,
        config.p4k_path,
        "xml",
        cache_dir,
        timeout=1800,  # 30 min timeout for large archive
    )

    dcb_path = _find_dcb(data_dir)
    if not dcb_path:
        raise RuntimeError("No .dcb file found after extraction. Check unp4k output.")

    print(f"  DCB found: {dcb_path} ({os.path.getsize(dcb_path) / (1024*1024):.0f} MB)")
    return dcb_path


def get_entity_files(config, entity_type="spaceships"):
    """Get list of entity XML files from the cache.

    These are extracted as part of extract_all_xml_and_dcb().
    Entity files are CryXML binary format and need conversion.
    """
    # The entity files could be in various locations
    search_dirs = [
        os.path.join(config.cache_dir, "Data", "Libs", "Foundry", "Records", "entities", entity_type),
        os.path.join(config.cache_dir, "Data", "Objects", "Spaceships"),
    ]

    files = []
    for search_dir in search_dirs:
        if os.path.isdir(search_dir):
            for root, dirs, filenames in os.walk(search_dir):
                for f in filenames:
                    if f.endswith((".xml", ".dcb")):
                        files.append(os.path.join(root, f))

    return files


def get_vehicle_impl_files(config):
    """Get list of vehicle implementation XML files (CryXML binary)."""
    impl_dir = os.path.join(config.cache_dir, "Data", "Scripts", "Entities",
                            "Vehicles", "Implementations", "Xml")
    if not os.path.isdir(impl_dir):
        return []
    return [os.path.join(impl_dir, f) for f in os.listdir(impl_dir) if f.endswith(".xml")]


# Directories known to contain CryXML-binary .xml files (magic bytes "CryXmlB").
# These files have .xml extension but are binary and MUST be converted with
# unforge.exe before they can be read as text XML. This list is scanned after
# the initial unp4k extraction to ensure all binary XMLs get converted in one
# pass. Extend this list when new CryXML-bearing directories are discovered.
CRYXML_BINARY_DIRS = [
    os.path.join("Data", "Libs", "Foundry", "Records", "entities", "spaceships"),
    os.path.join("Data", "Libs", "Foundry", "Records", "entities", "ground"),
    os.path.join("Data", "Scripts", "Entities", "Vehicles", "Implementations", "Xml"),
]


def scan_cryxml_binaries(config):
    """Scan the cache for CryXML-binary .xml files under known directories.

    Called after unp4k extraction. Any .xml file whose first 8 bytes begin with
    "CryXml" is binary and needs conversion via unforge.exe. Returns a list of
    file paths that should be passed to convert_entities().
    """
    binary_files = []
    for rel in CRYXML_BINARY_DIRS:
        root_dir = os.path.join(config.cache_dir, rel)
        if not os.path.isdir(root_dir):
            continue
        for root, dirs, files in os.walk(root_dir):
            for f in files:
                if not f.endswith(".xml"):
                    continue
                path = os.path.join(root, f)
                try:
                    with open(path, "rb") as fh:
                        head = fh.read(8)
                except OSError:
                    continue
                if head.startswith(b"CryXml"):
                    binary_files.append(path)
    return binary_files


def get_localization_file(config):
    """Get the English localization file path from cache."""
    candidates = [
        os.path.join(config.cache_dir, "Data", "Localization", "english", "global.ini"),
        os.path.join(config.cache_dir, "Data", "Localization", "english", "Global.ini"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    # The global.ini might not be extracted by the "xml" filter since it's .ini
    # Try extracting it separately
    print("  Localization not found in cache, extracting separately...")
    extract_files(
        config.unp4k_path,
        config.p4k_path,
        "global.ini",
        config.cache_dir,
        timeout=600,
    )

    for path in candidates:
        if os.path.isfile(path):
            return path

    print("  [WARN] Localization file not found. Names may show raw keys.")
    return None


def _find_dcb(data_dir):
    """Find the DataForge .dcb file in the extracted data."""
    if not os.path.isdir(data_dir):
        return None

    # Look for common DCB names
    for name in ["Game2.dcb", "game.dcb", "Game.dcb"]:
        path = os.path.join(data_dir, name)
        if os.path.isfile(path):
            return path

    # Search recursively
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            if f.endswith(".dcb"):
                return os.path.join(root, f)

    return None
