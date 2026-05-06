"""Cosmetic-variant detection.

Two items are cosmetic variants of each other if they share a className
prefix AND their gameplay-relevant stdItem fields are identical. Differences
in Name / Description / Tags / Manufacturer.Name (the cosmetic shell) are
ignored. Manufacturer.Code is kept in the comparison since it identifies
the maker, not the variant.

Used by fps_weapons.py, fps_attachments.py, and ship_equipment.py to flag
duplicate variants without dropping them from the catalogue. Replaces the
older name-substring filters (`_01_<suffix>`, `_LowPoly`, etc.) which
silently filtered cosmetic variants out.
"""
import json


# Fields excluded from the gameplay signature.
#
# Pure cosmetic shell:
# - ClassName / Name / Description / Tags / Classification
# - Manufacturer.Name (Code is kept; see _strip_cosmetic)
#
# Editorial-only fields (do not change in-game combat behavior):
# - Class: editorial label, occasionally inconsistent between base
#   (which lives in _FPS_CLASS_OMIT) and its variants.
# - Crafting: each variant has its own CraftingBlueprintRecord targeting
#   it, but the recipe content is the same gameplay-wise — and many
#   variants have no blueprint at all (which would falsely flag them
#   different from their base).
_COSMETIC_FIELDS = frozenset({
    "ClassName",
    "Name",
    "Description",
    "Tags",
    "Classification",
    "Class",
    "Crafting",
    # CosmeticVariant flags themselves should never be in a signature
    "CosmeticVariant",
    "CosmeticVariantOf",
})


def _strip_cosmetic(value, key=None):
    """Recursively strip cosmetic fields from a stdItem-shaped value.

    For Manufacturer dict, keep Code (identity) but drop Name (cosmetic).
    """
    if isinstance(value, dict):
        if key == "Manufacturer":
            # Keep only Code — Name is cosmetic
            code = value.get("Code", "")
            return {"Code": code} if code else {}
        return {k: _strip_cosmetic(v, k) for k, v in value.items()
                if k not in _COSMETIC_FIELDS}
    if isinstance(value, list):
        return [_strip_cosmetic(v) for v in value]
    return value


def gameplay_signature(std_item):
    """Return a JSON-canonical string of all gameplay-relevant fields.

    Returns None for empty/missing stdItem so callers can skip comparison.
    """
    if not std_item:
        return None
    stripped = _strip_cosmetic(std_item)
    if not stripped:
        return None
    return json.dumps(stripped, sort_keys=True, default=str)


def find_prefix_base(class_name, all_class_names):
    """Find a base item via progressive className-prefix stripping.

    Returns the longest existing prefix that is shorter than class_name,
    or None. Used to identify "<base>_<variantSuffix>" naming conventions
    where <base> is itself an emitted item.
    """
    parts = class_name.split("_")
    for i in range(len(parts) - 1, 1, -1):
        candidate = "_".join(parts[:i])
        if candidate != class_name and candidate in all_class_names:
            return candidate
    # Numeric-suffix fallback: foo_02/foo_03/foo_04 → foo_01
    if parts and parts[-1].isdigit() and parts[-1] != "01":
        candidate = "_".join(parts[:-1] + ["01"])
        if candidate != class_name and candidate in all_class_names:
            return candidate
    return None


_POSITIONAL_TOKENS = frozenset({
    "top", "bottom", "front", "rear", "back",
    "left", "right", "side", "port", "starboard",
    "center", "centre", "aft", "fore",
    "upper", "lower", "mid", "middle", "main",
    "inner", "outer", "inside", "outside",
    "tail", "nose", "head",
})


def _is_positional_copy(class_name, base_class_name):
    """Return True if `class_name` is a positional/locational copy of `base_class_name`.

    Positional copies are byte-identical to a base item but placed at a
    different physical location on the ship (e.g.
    `AEGS_Idris_SCItem_AI_Turret_Top_Left` vs `AEGS_Idris_SCItem_AI_Turret`).
    They share the base's gameplay signature like cosmetic skins, but they
    are NOT cosmetic — both the base and each positional copy are real
    installed items on the ship.

    The structural difference between a positional copy and a paint skin
    is invisible (CIG ships them with byte-identical components), so this
    is a name-suffix heuristic. Confined to suffixes that are unambiguously
    positional words; safe against color/edition tokens which never appear
    in this list.
    """
    if not class_name.startswith(base_class_name + "_"):
        return False
    suffix = class_name[len(base_class_name) + 1:]
    if not suffix:
        return False
    suffix_parts = suffix.lower().split("_")
    return all(p in _POSITIONAL_TOKENS for p in suffix_parts)


def _find_base_via_skin_suffix(class_name, skin_tag, all_class_names):
    """Strip a skin-tag suffix (case-insensitive) from class_name.

    For `apar_special_ballistic_01_black02` + skin_tag="Black02" returns
    `apar_special_ballistic_01` if it exists in the catalogue.
    """
    if not skin_tag:
        return None
    suffix = "_" + skin_tag.lower()
    cn_l = class_name.lower()
    if not cn_l.endswith(suffix):
        return None
    base_l = cn_l[: -len(suffix)]
    # Find original-case className
    for c in all_class_names:
        if c.lower() == base_l and c != class_name:
            return c
    return None


def detect_cosmetic_variants(all_items_by_classname, get_std_item,
                              get_skin_tag=None):
    """Identify cosmetic variants in a collection.

    Args:
        all_items_by_classname: dict className -> opaque item record
        get_std_item: callable item -> stdItem dict
        get_skin_tag: optional callable item -> skin/livery tag string.
            When non-empty, marks the item as cosmetic regardless of
            signature comparison. Used when CIG provides an explicit
            visual-variant identifier (e.g. SCItemWeaponComponentParams
            `geometryTags` for FPS weapons).

    Returns:
        dict className -> base_classname for items that are cosmetic
        variants. Items not in the dict are not cosmetic variants
        (either base items or have real gameplay differences).
    """
    sigs = {}
    for cn, item in all_items_by_classname.items():
        std = get_std_item(item)
        sig = gameplay_signature(std)
        if sig is not None:
            sigs[cn] = sig

    cosmetic = {}

    # Primary signal: explicit skin/livery tag (when caller provides one).
    # This catches CIG-marked variants where the gameplay signature might
    # differ for incidental reasons (e.g. each variant has its own
    # Crafting blueprint; Class label inconsistencies).
    if get_skin_tag is not None:
        for cn, item in all_items_by_classname.items():
            tag = get_skin_tag(item)
            if not tag:
                continue
            base = _find_base_via_skin_suffix(cn, tag, all_items_by_classname)
            if base is None:
                base = find_prefix_base(cn, all_items_by_classname)
            if base and not _is_positional_copy(cn, base):
                cosmetic[cn] = base

    # Secondary signal: gameplay-signature equivalence with a prefix-base.
    # Catches items without an explicit skin tag (e.g. melee weapons that
    # use SCItemMeleeWeaponParams instead of SCItemWeaponComponentParams,
    # numbered duplicates like banu_melee_02 sharing stats with _01).
    for cn in all_items_by_classname:
        if cn in cosmetic:
            continue
        base_cn = find_prefix_base(cn, all_items_by_classname)
        if not base_cn:
            continue
        # Positional copies (e.g. AEGS_Idris_SCItem_AI_Turret_Top_Left) are
        # byte-identical to their base but represent real installed items
        # at distinct physical locations — not cosmetic skin variants.
        if _is_positional_copy(cn, base_cn):
            continue
        sig_self = sigs.get(cn)
        sig_base = sigs.get(base_cn)
        if sig_self is not None and sig_self == sig_base:
            cosmetic[cn] = base_cn

    return cosmetic
