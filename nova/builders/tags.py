"""tags.json — flat TagDatabase catalog, GUID-keyed object map.

Output is a single object (not a list) keyed by tag GUID. TagName alone
is not unique — same name reappears in different tree positions (e.g.
"Pyro1" appears 4× across System / Station / LagrangePoints / AISpawn).
Consumers MUST join via GUID; Path is exposed for human-readable
disambiguation.
"""


def build_tags(ctx) -> dict:
    # Already in the right shape (parse_tag_database produces TagName /
    # Path / Description). Pass through with stable key ordering.
    return {guid: ctx.tags[guid] for guid in sorted(ctx.tags.keys())}
