"""Look up where an item can be looted.

    py -m nova.loot_query "Stoic Suppressor"
    py -m nova.loot_query arma_barrel_supp_s2_03 --channel PTU
    py -m nova.loot_query 4ef9f8dd-6229-4c86-bc8e-025c6cc87c2c --verbose

Reads output/<channel>/loot_locations.json. Shops are not covered here; buying
an item is a separate question with a separate source (UEX).
"""

import argparse
import collections
import json
import os
import sys


def _load(output_dir, channel):
    path = os.path.join(output_dir, channel, "loot_locations.json")
    if not os.path.isfile(path):
        sys.exit(f"No loot data at {path}. Run: py -m nova --only loot_locations")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find(data, needle):
    """Match on GUID, exact className, then case-insensitive substring."""
    items = data["items"]
    if needle in items:
        return [(needle, items[needle])]
    low = needle.lower()
    exact = [(g, v) for g, v in items.items() if v["className"].lower() == low]
    if exact:
        return exact
    return [(g, v) for g, v in items.items()
            if low in v["className"].lower() or low in (v["name"] or "").lower()]


def _report(data, guid, item, verbose):
    print(f"\n{item['name']}  ({item['className']})")
    print(f"  {guid}")
    for tag in item["lootTags"]:
        print(f"  tag: {tag}")

    observed = item.get("observedSourceSet")
    if not item["reachable"]:
        print(f"  By design: not in any loot pool. {item.get('blockedBy', 'no source found')}")
        if observed is None:
            return
        # The Event tag is documented as keeping items out of generic loot, but
        # observed play shows event-tagged attachments dropping loose from
        # generic containers anyway. Report where they actually turn up.
        print("  Event-gated by design, but observed dropping in generic loot."
              " Showing pools that match when the gate is ignored:")

    sources = data["sourceSets"][observed if not item["reachable"] and observed is not None
                                else item["sourceSet"]]
    presets = data["presets"]

    # Collapse to bodies, since that is the answer to "where in the universe".
    by_body = collections.defaultdict(lambda: {"containers": 0, "presets": set()})
    unplaced = set()
    actors = [s["actor"] for s in sources if s.get("kind") == "actor"]
    for src in sources:
        if src.get("kind") == "actor":
            continue
        meta = presets.get(src["preset"])
        if not meta or not meta["totalContainers"]:
            unplaced.add(src["preset"])
            continue
        for place in meta["placements"]:
            if not place["locations"]:
                unplaced.add(src["preset"])
                continue
            for loc in place["locations"]:
                # An unresolved body still has a system and a container key;
                # marking it beats hiding it behind a bare "?".
                body = loc["body"] if loc["resolved"] else f"{loc['body']} (unnamed)"
                slot = by_body[(loc["system"] or "?", body)]
                slot["containers"] += loc["containers"]
                slot["presets"].add(src["preset"])

    if by_body:
        ranked = sorted(by_body.items(), key=lambda kv: (-kv[1]["containers"], kv[0]))
        shown = ranked if verbose else ranked[:15]
        print(f"\n  Lootable at {len(ranked)} locations"
              + ("" if len(shown) == len(ranked) else f" (top {len(shown)}, -v for all)") + ":")
        for (system, body), slot in shown:
            print(f"    {system} / {body}: {slot['containers']} containers, "
                  f"{len(slot['presets'])} loot presets")
            if verbose:
                for p in sorted(slot["presets"]):
                    cfgs = next((s["configs"] for s in sources if s["preset"] == p), [])
                    print(f"      {p}: {', '.join(cfgs[:6])}"
                          + (" ..." if len(cfgs) > 6 else ""))
    if actors:
        print(f"\n  Also carried by {len(actors)} lootable NPC/corpse types"
              " (location depends on where they spawn):")
        for a in (sorted(actors) if verbose else sorted(actors)[:8]):
            print(f"    {a}")
        if not verbose and len(actors) > 8:
            print(f"    ... and {len(actors) - 8} more (-v for all)")

    if unplaced:
        print(f"\n  Matched but unplaced presets (dev content): {len(unplaced)}")
        if verbose:
            for p in sorted(unplaced):
                print(f"    {p}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find where an item can be looted.")
    ap.add_argument("query", help="GUID, className, or part of a display name")
    ap.add_argument("--channel", default="LIVE")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="List the loot presets and container configs behind each location")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)

    data = _load(args.output_dir, args.channel)
    hits = _find(data, args.query)
    if not hits:
        sys.exit(f"No lootable item matches {args.query!r}")
    if len(hits) > args.limit:
        print(f"{len(hits)} matches, showing {args.limit}. Narrow the query to see the rest.")
        hits = hits[:args.limit]
    for guid, item in sorted(hits, key=lambda kv: kv[1]["className"]):
        _report(data, guid, item, args.verbose)


if __name__ == "__main__":
    main()
