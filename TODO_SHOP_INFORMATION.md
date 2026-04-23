# Shop Information — UEX Integration Plan

Add crowdsourced shop location and pricing data from [UEX API 2.0](https://uexcorp.space/api/documentation/) to the extractor pipeline. Fetch runs once per game-version update, alongside the existing `ships.json` / `ship_equipment.json` / `fps_*.json` refresh.

## Goal

Three new output files in `output/`:

| File | Contents |
|---|---|
| `shop_ship_equipment.json` | Ship components and weapons with shop locations + prices |
| `shop_fps_weapons.json` | FPS personal weapons and attachments |
| `shop_fps_equipment.json` | FPS armor, clothing, consumables, gadgets |

Keyed by Star Citizen entity UUID (same UUIDs already present in our `ship_equipment.json` / `fps_weapons.json` via `reference` field) so consumers can join without name matching.

## UEX category mapping

Complete UEX `type=item` category list (verified 2026-04-23) and how each bucket maps to our output files.

### → `shop_ship_equipment.json`

| Cat ID | UEX Name | Section | Notes |
|---|---|---|---|
| 19 | Coolers | Systems | |
| 21 | Power Plants | Systems | |
| 22 | Quantum Drives | Systems | |
| 23 | Shield Generators | Systems | |
| 81 | Batteries | Systems | Include (ship-related) |
| 82 | Flight Blade | Avionics | |
| 83 | Radar | Avionics | |
| 86 | Jump Modules | Propulsion | These are what user calls "Jump Drives" |
| 32 | Guns | Vehicle Weapons | Ship guns (Omnisky, repeaters, etc.) |
| 33 | Missile Racks | Vehicle Weapons | |
| 34 | Missiles | Vehicle Weapons | |
| 35 | Turrets | Vehicle Weapons | **Includes gimbal mounts** (VariPuck S1–S6, Buccaneer Spinal Mount, etc.) — verified via item sample. No separate Gimbals category exists. |
| 70 | Bombs | Vehicle Weapons | |
| 79 | Point Defense Cannon | Vehicle Weapons | |
| 80 | Torpedo Tubes | Vehicle Weapons | |
| 90 | Bomb Racks | Vehicle Weapons | |
| 25 | Docking Collars | Utility | |
| 26 | External Fuel Tanks | Utility | |
| 29 | Mining Laser Heads | Utility | |
| 30 | Mining Modules | Utility | |
| 31 | Scraper Beams | Utility | |
| 67 | Tractor Beams | Utility | Contains ship-mounted SureGrip beams only (verified) |
| 109 | Fabricator | Utility | |
| 110 | Salvage Beams | Utility | |
| 74 | Module | Module | Ship cargo / utility modules |

### → `shop_fps_weapons.json`

| Cat ID | UEX Name | Section |
|---|---|---|
| 17 | Attachments | Personal Weapons |
| 18 | Personal Weapons | Personal Weapons |

### → `shop_fps_equipment.json`

| Cat ID | UEX Name | Section |
|---|---|---|
| 1 | Arms | Armor |
| 2 | Backpacks | Armor |
| 3 | Helmets | Armor |
| 4 | Legs | Armor |
| 5 | Torso | Armor |
| 7 | Full Set | Armor |
| 8 | Footwear | Clothing |
| 9 | Gloves | Clothing |
| 10 | Hats | Clothing |
| 11 | Jackets | Clothing |
| 12 | Jumpsuits | Clothing |
| 13 | Legwear | Clothing |
| 14 | Shirts | Clothing |
| 15 | Full Set | Clothing |
| 68 | Eyeware | Clothing |
| 72 | Dresses | Clothing |
| 24 | Undersuits | Undersuits |
| 28 | Gadgets | Utility |
| 69 | Consumable | Consumable |
| 16 | Consumables | Miscellaneous |
| 62 | Drinks | Miscellaneous |
| 63 | Foods | Miscellaneous |

### Deliberately skipped

| Cat ID | Name | Why |
|---|---|---|
| 36, 87 | Commodities, Harvestables | Trade goods, not equipment |
| 102 | Vehicles | Whole ships — already covered by our vehicle data |
| 20, 75, 107 | Liveries, Decorations, Flair | Cosmetic; low value for tooling |
| 37 | Points of Interest | Location data, not equipment |
| 38, 61 | Other, Miscellaneous | Too generic; re-evaluate if needed |
| 65, 64 | Container (Misc / Utility) | Unclear scope — re-evaluate |
| 73 | Mobiglas | Single item, not core to any consumer |
| 27 | Fuel Nozzle | Ambiguous ship/FPS scope |
| 84, 103 | Gravity Generator, Life Support Generator | Not user-swappable components; skip unless a consumer asks |

## API workflow

**Auth**: Register an app at UEX's [My Apps page](https://uexcorp.space/api/apps) (requires a UEX account; login link is in the site header). The form asks for an app name, description, and optional client version lock. On submit it issues a bearer token that you pass as `Authorization: Bearer <token>` on every request. Store the token in `nova_config.json` under `uex.api_token` or via env var `UEX_API_TOKEN` — **do not commit the token** (add the config key to `.gitignore` or split the token into a local-only file). Anonymous reads work for most GET endpoints but a registered token gives the full 120 req/min budget, is required for `/data_submit`, and lets UEX contact the app owner if it misbehaves.

**Endpoints**:
```
GET https://api.uexcorp.space/2.0/items?id_category={N}       # catalog
GET https://api.uexcorp.space/2.0/items_prices?id_category={N} # all shop listings for that category
```

**Rate limit**: 120 req/min, 172,800/day. With ~45 categories across all three files, that's ≤ 90 calls per refresh — trivially under the limit. No throttling needed beyond a conservative 0.5s sleep between calls.

**Fetch strategy**: two calls per category (items + items_prices), merge in-memory by `id_item`, group by target output file. One pass, no pagination needed (biggest category is ~150 items).

## Matching to Nova-extracted data

UEX's `items.uuid` field matches the Star Citizen entity UUID used in our `ship_equipment.json` `reference` field (and FPS equivalents). UEX keeps its catalog current with live patch cycles, so UUID is a reliable primary join key.

**Join key**: `uuid`. Log (don't fuzzy-match) any UEX record missing a UUID so it surfaces as a data-quality signal rather than silently fanning out into slug/name heuristics.

## Proposed output schema

```json
{
  "_metadata": {
    "source": "uexcorp.space API 2.0",
    "fetched_at": "2026-04-23T22:30:00Z",
    "game_version": "4.7.1",
    "item_count": 1234,
    "listing_count": 5678
  },
  "items": {
    "<uuid>": {
      "uex_id": 140,
      "name": "LumaCore",
      "slug": "lumacore",
      "category": "Power Plants",
      "section": "Systems",
      "company": "Roberts Space Industries",
      "listings": [
        {
          "terminal": "Dumper's Depot - Area 18",
          "star_system": "Stanton",
          "planet": "ArcCorp",
          "price_buy": 69300,
          "price_sell": 0,
          "price_buy_min_month": 69300,
          "price_buy_max_month": 69300
        }
      ]
    }
  }
}
```

Drop UEX's per-listing `id_*` fields in favor of resolved names (terminal, star_system, planet) to keep files self-contained. Preserve the month min/max/avg since prices do fluctuate.

## Pipeline integration

1. New module `nova/uex_fetcher.py` — pure fetch + merge, no game-file logic.
2. New builder `nova/builders/shop.py` — maps UEX data to the three output files.
3. Called from the main extractor after game data is built (so we know the game version for metadata).
4. Add `--skip-shop` flag to `run.bat` / entry point for local iteration when shop data isn't needed.
5. Cache raw UEX responses at `cache/uex/items_{cat}.json` and `cache/uex/items_prices_{cat}.json`, keyed by game version — so re-runs don't hit the API unnecessarily.

## Attribution

Not strictly required by UEX terms (Section 5 is silent on attribution), but customary and the right thing to do — the data is contributed by UEX's volunteer Data Runner community.

**Badge**: Consumers of these output files (e.g. NovaTools) should display the official "Powered by UEX" badge wherever shop prices are shown, linked to https://uexcorp.space.

- Badge asset: `https://uexcorp.space/img/api/uex-api-badge-powered.png` (verified 2026-04-23, 120 KB PNG)
- Recommended markup:
  ```html
  <a href="https://uexcorp.space" target="_blank" rel="noopener">
    <img src="https://uexcorp.space/img/api/uex-api-badge-powered.png" alt="Powered by UEX" />
  </a>
  ```
- Downstream apps may mirror the badge locally (e.g. copy into NovaTools `img/`) to avoid hotlinking, but the `<a href>` should still point to uexcorp.space.

**Metadata provenance**: record the source in `_metadata.source` (`"uexcorp.space API 2.0"`) of each `shop_*.json` file so this stays discoverable downstream and consumers can display attribution even when they load the files without other context.

## Open questions / TODO

- [ ] Decide handling for items present in UEX but missing from our extracted data, and vice versa — log at extract time, keep both sides for auditability.
- [ ] Register UEX app and add token to `nova_config.json` schema (+ gitignore for tokens).
- [ ] Revisit skipped categories (38 Other, 61 Miscellaneous, 65/64 Container) once the first extract is reviewed — some may contain items a consumer needs.
- [ ] Decide whether to include Gravity Generator (84) / Life Support Generator (103) / Batteries (81) — currently included Batteries only, since those are the least clearly user-swappable but appear in some ship loadouts.
- [ ] Once `shop_*.json` files exist, update `DATA_SOURCES.md` with the UEX pipeline.
