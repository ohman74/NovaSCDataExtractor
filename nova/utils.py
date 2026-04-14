"""Shared utility functions."""

import os


def parse_localization(ini_path):
    """Parse global.ini localization file into a dict.

    Format: key=value (one per line), with optional BOM.
    """
    translations = {}
    if not ini_path or not os.path.isfile(ini_path):
        return translations

    with open(ini_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                translations[key.strip()] = value.strip()

    return translations


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
