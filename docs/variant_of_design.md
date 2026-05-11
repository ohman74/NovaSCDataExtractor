# `VariantOf` field — design notes (in-progress)

Status: **design only, not implemented**. Captures the discussion 2026-05-11 on
how to express ship-variant relationships in `vehicle_metadata.json`.

## Problem

`CosmeticVariantOf` (existing) is too strict — only ships with **zero** gameplay
diffs from a base get tagged. We want a looser `VariantOf` field that captures
"same chassis, same defensive tier, different default loadout" — e.g. Sabre
Comet should be filterable as a variant of Sabre in a UI.

## Proposed rule

Two ships are `VariantOf` siblings iff **all three** match:

1. Same `vehicleDefinition` (impl XML).
2. Same armor className (resolved from `hardpoint_armor` / `hardpoint_armour`
   loadout port).
3. Same **structural-modification signature** — hash of port-affecting Elems
   in the ship's `modification` block. Port-affecting means Elems with name in
   `{minSize, maxSize, flags, skipPart, types, requiredTags, portTags}`. Mass
   and damageMax tweaks alone are NOT structural and don't break the match.

Within each group, the **base** is the shortest className (alphabetical
tiebreak). Other members get `VariantOf: <base_className>`. Singletons get no
tag. Ships without an armor port (e.g. Idris_P_TSG) are skipped from grouping
— see TODO #1.

Field is **one-way only** (variant → base). UI builds inverse map if needed.
`CosmeticVariantOf` ⊂ `VariantOf` — paint-only variants get both tags.

## Verified outcomes (PTU 2026-05-10)

| Family | Result |
|---|---|
| **Sabre** | Sabre ← Comet; Firebird ← Collector_Milt; Peregrine ← Collector_Competition; Raven (singleton) |
| **Gladius** | Gladius ← Dunlevy + PIR + Valiant (all variants — none has a structural mod) |
| **Vanguard** | Warden / Harbinger / Hoplite / Sentinel — all 4 singletons (each has unique armor + structural mod) |
| **Polaris** | Polaris ← Collector_Military |
| **Idris** | Idris_M ← Idris_M_PU; Idris_P ← Idris_P_Collector_Military; FW_25 (singleton, separate impl) |
| **Hornet** | F7C ← Wildfire; F7CM ← Heartseeker; F7A_Mk2 ← Exec_Stealth + Exec_Military; F7CM_Mk2 ← Heartseeker + Collector_Mod. **F7C_Mk2 separated as singleton** (its mod resizes power-port S2→S1). F7CR / F7CS / F7CR_Mk2 / F7CS_Mk2 all singletons (own structural mods). |

## Key worked examples

### Sabre Comet vs Sabre — variant ✓
- Mod `Comet`: 0 elems (empty placeholder).
- Loadout diff: 1 weapon swap (KLWE_LaserRepeater_S3 → AMRS_LaserCannon_S3).
- Same impl + armor + (no structural mod) → variant.

### F7C_Mk2 vs F7A_Mk2 — separated ✓
- Both share `anvl_hornet_f7a.xml` impl + `ARMR_ANVL_Hornet_F7A` armor.
- F7C_Mk2 mod has 11 structural elems including:
  - `modPortPowerPlant01 minSize=1, maxSize=1` ← downgrades S2 port to S1
  - `modPartPowerPlant02 skipPart=0` ← enables 2nd power port
- Effect: F7A_Mk2 has 1×S2 + 1×S1 power; F7C_Mk2 has 1×S1 + 1×S1.
- F7A's S2 power plant cannot mount on F7C_Mk2 → genuinely different chassis.

### Vanguard Hoplite vs Warden — separated ✓
- Different armor className (`ARMR_AEGS_Vanguard_Hoplite` vs `ARMR_AEGS_Vanguard`).
- Hoplite mod also has structural changes (enables 2 missilerack ports, FC tag swaps).
- Either signal alone is enough; both fire here.

### Gladius PIR/Valiant vs Gladius — variant ✓ (despite loadout diffs)
- `Valiant` mod: 1 elem, just a mass change. No port changes.
- `PIR` ship has empty mod string.
- All Gladius variants share impl + armor + (no structural mod).
- They differ only in default-loadout (more missiles, different cooler/shield/
  power-plant brands at same sizes). User intent: that's player choice, not
  chassis difference.

## Open questions / unverified

1. **F7CR (Mk1) — possibly should be VariantOf F7C.** Current rule classifies
   F7CR as singleton because it has its own structural mod (probably altering
   a sensor/scanner port for the Recon role). User suspects the recon radar can
   actually be mounted on regular F7C if the player has one — meaning the port
   constraints might NOT actually differ. Need to:
   - Inspect what F7CR's mod modifies (port resize? port-tag change?).
   - Verify whether F7C's nose / scanner port can accept the recon radar item.
   - If yes: relax the rule, OR add a sub-rule that ignores certain port-tag-only
     mods (since tags can be permissive).

2. **Bidirectional `Variants: [...]` field on bases?** Currently proposing one-
   way (variant → base). Reasonable to skip — UI can build the inverse trivially.

3. **`AEGS_Idris_P_TSG`** — leaks into `vehicle_metadata.json` with no armor port,
   duplicate name "Aegis Idris-P". Tracked as session task #1 (Filter
   AEGS_Idris_P_TSG from vehicle_metadata). Until filtered upstream, the
   VariantOf logic will skip it because of missing armor — acceptable workaround.

4. **Armor className vs armor stat-signature.** F7C and F7A armors have IDENTICAL
   stats (HP=6600, same multipliers) but different classNames (CIG aliasing).
   Doesn't affect F7C-vs-F7A_Mk2 grouping (different impls anyway), but if CIG
   aliasing becomes more common, may want to switch from className to stat-hash.

## Implementation outline (TODO)

In `nova/cosmetic_classifier.py` (or new module):

```python
PORT_AFFECTING_ELEMS = {
    "minSize", "maxSize", "flags", "skipPart",
    "types", "requiredTags", "portTags",
}

def structural_mod_signature(impl_basename, mod_name, impl_modifications):
    """Hash of port-affecting Elems in mod. Empty/missing → ''. Stable across runs."""
    if not mod_name:
        return ""
    elems = impl_modifications.get(impl_basename.lower(), {}).get(mod_name, [])
    structural = sorted((idr, name, val) for idr, name, val in elems
                        if name in PORT_AFFECTING_ELEMS)
    if not structural:
        return ""
    return hashlib.sha1(repr(structural).encode()).hexdigest()[:12]

def identify_variants(vehicles_by_class, entity_xml_by_class, items_db,
                      impl_modifications, kept_class_names=None):
    """Returns {variant_classname: base_classname}. Group by
    (impl_basename, armor_className, structural_mod_sig); base = shortest member."""
    # ...
```

Then add `VariantOf` field at emit time in `nova/builders/slices.py` /
`nova/builders/ships.py` parallel to existing `CosmeticVariantOf` plumbing
(see `__main__.py:512` for cosmetic_variants integration pattern).
