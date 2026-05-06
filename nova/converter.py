"""Convert CryXML/DataForge binary files to readable XML using unforge.exe."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def convert_file(unforge_path, input_path, timeout=300):
    """Convert a single CryXML/DataForge file to XML.

    unforge.exe creates the output file alongside the input file
    with a .xml extension (or .raw.xml for .dcb files).

    Returns:
        Path to the converted XML file, or None on failure.
    """
    if not os.path.isfile(input_path):
        return None

    cmd = [unforge_path, input_path]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        print(f"  [WARN] Failed to convert {os.path.basename(input_path)}: {stderr}")
        return None

    # unforge outputs as .xml or .raw.xml
    base = input_path
    for ext in [".raw.xml", ".xml"]:
        candidate = os.path.splitext(base)[0] + ext
        if os.path.isfile(candidate):
            return candidate

    # Check if the file itself was modified (some versions overwrite)
    xml_path = input_path + ".xml"
    if os.path.isfile(xml_path):
        return xml_path

    # Try looking for any new XML in the same directory
    directory = os.path.dirname(input_path)
    basename = os.path.splitext(os.path.basename(input_path))[0]
    for f in os.listdir(directory):
        if f.startswith(basename) and f.endswith(".xml"):
            return os.path.join(directory, f)

    return None


def convert_game_dcb(config, dcb_path):
    """Convert game.dcb to XML. This produces a large file (2-4 GB)."""
    print("\n[2/5] Converting game.dcb to XML (this may take a while)...")

    # Check for cached conversion
    xml_path = os.path.splitext(dcb_path)[0] + ".xml"
    raw_xml_path = os.path.splitext(dcb_path)[0] + ".raw.xml"

    for candidate in [xml_path, raw_xml_path]:
        if os.path.isfile(candidate):
            size_mb = os.path.getsize(candidate) / (1024 * 1024)
            print(f"  Using cached: {candidate} ({size_mb:.0f} MB)")
            return candidate

    start = time.time()
    result = convert_file(config.unforge_path, dcb_path, timeout=1800)
    elapsed = time.time() - start

    if result is None:
        raise RuntimeError("Failed to convert game.dcb")

    size_mb = os.path.getsize(result) / (1024 * 1024)
    print(f"  Converted in {elapsed:.1f}s ({size_mb:.0f} MB)")
    return result


def convert_entities(config, entity_files, max_workers=4):
    """Convert multiple entity files in parallel.

    Returns:
        Dict mapping original path to converted XML path.
    """
    print(f"\n[4/5] Converting {len(entity_files)} entity files...")

    results = {}
    already_converted = 0
    to_convert = []

    for f in entity_files:
        xml_candidate = os.path.splitext(f)[0] + ".xml"
        if os.path.isfile(xml_candidate) and not f.endswith(".xml"):
            results[f] = xml_candidate
            already_converted += 1
        elif f.endswith(".xml"):
            # File has .xml extension but could still be CryXML binary.
            # Check the first bytes: text XML starts with "<", binary
            # starts with "CryXmlB" magic.
            try:
                with open(f, "rb") as fh:
                    head = fh.read(8)
                if head.startswith(b"CryXmlB") or head.startswith(b"CryXml"):
                    to_convert.append(f)
                    continue
            except OSError:
                pass
            results[f] = f
            already_converted += 1
        else:
            to_convert.append(f)

    if already_converted > 0:
        print(f"  {already_converted} already converted (cached)")

    if not to_convert:
        return results

    start = time.time()
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(convert_file, config.unforge_path, f): f
            for f in to_convert
        }

        for i, future in enumerate(as_completed(futures), 1):
            original = futures[future]
            try:
                xml_path = future.result()
                if xml_path:
                    results[original] = xml_path
                else:
                    failed += 1
            except Exception as e:
                print(f"  [WARN] Error converting {os.path.basename(original)}: {e}")
                failed += 1

            if i % 50 == 0:
                print(f"  Converted {i}/{len(to_convert)}...")

    elapsed = time.time() - start
    print(f"  Converted {len(to_convert) - failed}/{len(to_convert)} files in {elapsed:.1f}s")
    if failed > 0:
        print(f"  [WARN] {failed} files failed to convert")

    return results
