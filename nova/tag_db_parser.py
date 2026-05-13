"""Parse TagDatabase.TagDatabase.xml into a flat GUID-keyed map.

The file is a deeply hierarchical tree of <Record __type="Tag"
tagName=... __guid=...> nodes. Most tag references in mission
contracts point into this tree, so downstream consumers need a flat
{guid: {tagName, path, description?}} lookup. Path is the ` > `-joined
ancestor chain (e.g. "System > Pyro > Pyro5 > Pyro5a") because
tagName alone is not unique — "Pyro1" appears twice (top-level Pyro
subnode and under LagrangePoints).

Parser strategy: CIG ships this file with intentionally broken outer
XML wrapping (`</TagDatabase.TagDatabase></Record>` appearing on the
same line, with closing tags that have no matching opens). ET.parse
chokes immediately. We sidestep the problem by reading line-by-line
and treating each `<Record __type="Tag" ...>` line independently —
indentation columns give us the hierarchy. This is robust to the
malformed wrapping and only ~30 lines of code.
"""

import json
import os
import re
import time


# A Record opening tag is always on a single line; tagName/__guid/
# description attributes can appear in any order, so we don't rely on
# ordering — just extract whichever attrs are present.
_RECORD_LINE_RE = re.compile(r'<Record\s+__type="Tag"')
_TAGNAME_RE = re.compile(r'tagName="([^"]*)"')
_GUID_RE = re.compile(r'__guid="([^"]+)"')
_DESC_RE = re.compile(r'description="([^"]*)"')


def parse_tag_database(cache_dir, channel_cache_dir=None):
    """Parse the standalone TagDatabase XML file.

    Args:
        cache_dir: per-channel cache dir (where parsed_tags.json lives).
        channel_cache_dir: root cache dir containing Data/Libs/...
            If None, defaults to `cache_dir` (the per-channel cache).

    Returns:
        dict[str, dict] keyed by tag GUID with TagName / Path /
        (optional) Description.
    """
    if channel_cache_dir is None:
        channel_cache_dir = cache_dir

    cache_file = os.path.join(cache_dir, "parsed_tags.json")
    if os.path.isfile(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            tags = json.load(f)
        print(f"  Loaded {len(tags)} tags (cached)")
        return tags

    xml_path = os.path.join(
        channel_cache_dir, "Data", "Libs", "Foundry", "Records",
        "TagDatabase", "TagDatabase.TagDatabase.xml",
    )
    if not os.path.isfile(xml_path):
        print(f"  [WARN] TagDatabase not found at {xml_path}")
        return {}

    start = time.time()
    out = {}
    # Stack of (indent_column, tagName) representing the ancestor chain.
    stack = []
    with open(xml_path, "r", encoding="utf-8") as f:
        for line in f:
            if "<Record" not in line:
                continue
            if not _RECORD_LINE_RE.search(line):
                continue

            indent = len(line) - len(line.lstrip(" "))

            gu_match = _GUID_RE.search(line)
            if not gu_match:
                continue
            guid = gu_match.group(1)

            tn_match = _TAGNAME_RE.search(line)
            tag_name = tn_match.group(1) if tn_match else ""

            # Pop ancestors whose indent is >= current — we left their scope.
            while stack and stack[-1][0] >= indent:
                stack.pop()

            ancestors = [t for _, t in stack]
            path = " > ".join(ancestors + [tag_name]) if tag_name else " > ".join(ancestors)
            entry = {"TagName": tag_name, "Path": path}

            desc_match = _DESC_RE.search(line)
            if desc_match:
                desc = desc_match.group(1)
                if desc:
                    entry["Description"] = desc

            out[guid] = entry
            stack.append((indent, tag_name))

    elapsed = time.time() - start
    print(f"  Parsed {len(out)} tags from TagDatabase in {elapsed:.1f}s")

    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out
