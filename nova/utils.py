"""Shared utility functions."""

import os
import re


NULL_GUID = "00000000-0000-0000-0000-000000000000"


def parse_localization(ini_path):
    """Parse global.ini localization file into a dict.

    Format: key=value (one per line), with optional BOM.
    """
    translations = {}
    if not ini_path or not os.path.isfile(ini_path):
        return translations

    with open(ini_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\r\n")
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                # Preserve trailing whitespace in value but strip trailing newline only
                translations[key.strip()] = value

    return translations


# "Grade: C" line in an item description. global.ini separates lines with
# a literal backslash-n, not a newline character.
_DESC_GRADE_RE = re.compile(r"(?:^|\\n)Grade:\s*([A-D])\s*(?:\\n|$)")


def apply_description_grades(items_by_class, translations):
    """Make attachDef.grade agree with the grade the item's description shows.

    CIG states an item's grade twice: AttachDef Grade="N" (1-4) and a
    "Grade: X" line in the localized description, which is what the game
    shows the player. Where both exist and disagree, the description wins:
    the disagreements look like a numeric field left at a default while
    sibling items line up 1-4 with A-D. Items whose description states no
    grade keep the numeric field.

    Mutates items_by_class in place. Returns [(className, old, new)].
    """
    changed = []
    for cls, rec in items_by_class.items():
        ad = rec.get("attachDef") if isinstance(rec, dict) else None
        if not ad:
            continue
        desc_key = ad.get("description") or ""
        if not desc_key.startswith("@"):
            continue
        text = translations.get(desc_key[1:]) or ""
        m = _DESC_GRADE_RE.search(text)
        if not m:
            continue
        grade = "ABCD".index(m.group(1)) + 1
        if ad.get("grade") != grade:
            changed.append((cls, ad.get("grade"), grade))
            ad["grade"] = grade
    return changed


def resolve_name(raw_name, translations):
    """Resolve a localization key like '@item_NameFoo' to its display name."""
    if not raw_name:
        return raw_name
    if raw_name.startswith("@"):
        key = raw_name[1:]  # Remove leading @
        # Try exact key, then with ,P suffix (CIG's property variant)
        resolved = translations.get(key, translations.get(key + ",P",
                   translations.get(raw_name, raw_name)))
        # Keep raw @key if resolved to empty string
        if not resolved:
            return raw_name
        # CIG sometimes stores trailing literal '\n' / '\r' escape sequences
        # in name strings (e.g. "Argo CSV-SM\n"). Strip them — a Name/Display
        # field never ends with a line-break.
        while resolved.endswith(("\\n", "\\r")):
            resolved = resolved[:-2]
        return resolved
    return raw_name


def safe_float(value, default=0.0):
    """Safely parse a float from string."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Safely parse an int from string."""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def safe_bool(value, default=False):
    """Parse a boolean from string ('0'/'1', 'true'/'false')."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    v = str(value).lower().strip()
    return v in ("1", "true", "yes")
