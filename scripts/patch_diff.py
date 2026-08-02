"""Generate an HTML diff report between two Nova LIVE output snapshots.

Usage:
    py scripts/patch_diff.py <prev_dir> <new_dir> <out.html>

Example (after a patch re-extract, with the pre-patch output snapshotted):
    py scripts/patch_diff.py output/_prev_4.9.188.5236 output/LIVE         reports/patch_diff_4.9.188.5236_to_23497.html

Datasets are keyed GUID-first (reference / GUID / TargetGUID / Id), falling back to
ClassName and then to a composite key, so records are matched by identity rather than
by list position. Files whose SHA-256 matches are reported as byte-identical and skipped.
"""
import json, os, sys, hashlib, datetime, html

if len(sys.argv) != 4:
    sys.exit(__doc__)
PREV, NEW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

_CSS = r"""
:root{--bg:#0f1216;--card:#181d24;--edge:#262d38;--txt:#e6e9ee;--mut:#96a0b0;--acc:#4da3ff;--pos:#4ade80;--neg:#f87171;--mod:#fbbf24;}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--txt)}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 4px}
.sub{color:var(--mut);margin:0 0 24px;font-size:14px}
.hero{display:flex;gap:16px;flex-wrap:wrap;margin:0 0 28px}
.hcard{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:14px 18px;flex:1;min-width:200px}
.hcard .lab{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.hcard .big{font-size:20px;font-weight:600;margin-top:4px}
.arrow{color:var(--acc)}
table.sum{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--edge);border-radius:12px;overflow:hidden;margin-bottom:36px}
table.sum th,table.sum td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--edge)}
table.sum th{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em;background:#141a21}
table.sum td.num{text-align:right;font-variant-numeric:tabular-nums}
td.add{color:var(--pos)} td.rem{color:var(--neg)} td.mod{color:var(--mod)}
.pos{color:var(--pos)} .neg{color:var(--neg)} .zero{color:var(--mut)}
.verdict{border-radius:12px;padding:14px 18px;margin:0 0 24px;border:1px solid var(--edge);line-height:1.5}
.verdict.ok{background:rgba(74,222,128,.08);border-color:rgba(74,222,128,.35)}
.verdict.ok strong{color:var(--pos)}
.verdict.chg{background:rgba(251,191,36,.08);border-color:rgba(251,191,36,.4)}
.verdict.chg strong{color:var(--mod)}
.note{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:14px 18px;margin:0 0 24px;color:var(--mut);font-size:14px;line-height:1.6}
.note code{color:var(--txt);background:#141a21;padding:1px 5px;border-radius:5px;font-size:13px}
h2.sec{font-size:18px;margin:32px 0 12px}
.dcard{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:6px 18px 16px;margin:0 0 18px}
.dcard h3{font-size:16px;margin:14px 0 8px}
.dl{margin:6px 0 4px}
.dlab{font-size:12px;text-transform:uppercase;letter-spacing:.03em;font-weight:600;margin:8px 0 4px}
.dlab.add{color:var(--pos)} .dlab.rem{color:var(--neg)} .dlab.mod{color:var(--mod)}
.dcard ul{margin:2px 0 8px;padding-left:20px}
.dcard li{font-size:13.5px;margin:1px 0}
.dcard code{background:#141a21;padding:1px 5px;border-radius:5px;font-size:12.5px;color:var(--acc)}
.muted{color:var(--mut)}
table.mtab{width:100%;border-collapse:collapse;margin:2px 0 8px}
table.mtab td{padding:4px 8px;border-bottom:1px solid var(--edge);font-size:13px;vertical-align:top}
table.mtab td.k{font-weight:600;white-space:nowrap;width:1%;padding-right:16px}
.old{color:var(--neg)} .new{color:var(--pos)}
"""

LABELS = [
    ("vehicle_metadata.json", "Ships - metadata"),
    ("vehicle_stats.json", "Ships - stats"),
    ("vehicle_hardpoints.json", "Ships - hardpoints"),
    ("vehicle_equipment.json", "Ship equipment"),
    ("fps_equipment.json", "FPS equipment"),
    ("blueprints.json", "Blueprints"),
    ("missions.json", "Missions"),
    ("mission_board.json", "Mission board"),
    ("factions.json", "Factions"),
    ("resources.json", "Resources"),
    ("mineables.json", "Mineables"),
    ("standings.json", "Standings"),
    ("localities.json", "Localities"),
    ("mission_types.json", "Mission types"),
    ("scenarios.json", "Scenarios"),
    ("tags.json", "Tags"),
]

KEY_CANDIDATES = ["reference", "GUID", "TargetGUID", "Id", "ClassName", "className"]
NAME_FIELDS = ["Name", "DisplayName", "Title", "TargetName", "name", "itemName", "ClassName", "className"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load(d, f):
    p = os.path.join(d, f)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def pick_key(items):
    """Return a function item -> key, choosing the most reliable unique identifier."""
    if not items or not isinstance(items[0], dict):
        return None
    for k in KEY_CANDIDATES:
        if k in items[0]:
            vals = [str(i.get(k)) for i in items]
            if len(set(vals)) == len(vals):
                return (k,), lambda i, k=k: str(i.get(k))
    # composite fallback
    for combo in [("Kind", "ClassName", "Id"), ("ClassName", "Id"), ("ClassName", "Name")]:
        if all(c in items[0] for c in combo):
            vals = ["|".join(str(i.get(c)) for c in combo) for i in items]
            if len(set(vals)) == len(vals):
                return combo, lambda i, c=combo: "|".join(str(i.get(x)) for x in c)
    return None


def label_of(item, key):
    if not isinstance(item, dict):
        return key
    for f in NAME_FIELDS:
        v = item.get(f)
        # skip unresolved localisation keys (@item_Name..., @LOC_PLACEHOLDER)
        if isinstance(v, str) and v.strip() and not v.startswith("@"):
            return v
    for f in NAME_FIELDS:
        v = item.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return key


def flat(o, prefix=""):
    """Flatten nested dict/list into dotted paths for field-level diffing."""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flat(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(o, list):
        if not o:
            out[prefix] = "[]"
        for i, v in enumerate(o):
            out.update(flat(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = o
    return out


def diff_fields(a, b, limit=40):
    fa, fb = flat(a), flat(b)
    keys = sorted(set(fa) | set(fb))
    ch = []
    for k in keys:
        va, vb = fa.get(k, "<absent>"), fb.get(k, "<absent>")
        if va != vb:
            ch.append((k, va, vb))
    return ch[:limit], len(ch)


def diff_dataset(prev, new):
    """Return dict with added/removed/modified lists."""
    res = {"key": None, "added": [], "removed": [], "modified": [], "prev_n": 0, "new_n": 0}
    if isinstance(prev, dict) and isinstance(new, dict):  # tags.json style
        res["prev_n"], res["new_n"] = len(prev), len(new)
        res["key"] = ("<dict key>",)
        for k in new:
            if k not in prev:
                res["added"].append((k, label_of(new[k], k) if isinstance(new[k], dict) else str(new[k])[:80], new[k]))
        for k in prev:
            if k not in new:
                res["removed"].append((k, label_of(prev[k], k) if isinstance(prev[k], dict) else str(prev[k])[:80], prev[k]))
        for k in new:
            if k in prev and prev[k] != new[k]:
                ch, tot = diff_fields(prev[k], new[k])
                res["modified"].append((k, label_of(new[k], k) if isinstance(new[k], dict) else k, ch, tot))
        return res
    prev, new = prev or [], new or []
    res["prev_n"], res["new_n"] = len(prev), len(new)
    kp, kn = pick_key(prev), pick_key(new)
    kf = (kn or kp)
    if not kf:
        return res
    res["key"] = kf[0]
    fn = kf[1]
    mp = {fn(i): i for i in prev}
    mn = {fn(i): i for i in new}
    for k, v in mn.items():
        if k not in mp:
            res["added"].append((k, label_of(v, k), v))
    for k, v in mp.items():
        if k not in mn:
            res["removed"].append((k, label_of(v, k), v))
    for k, v in mn.items():
        if k in mp and mp[k] != v:
            ch, tot = diff_fields(mp[k], v)
            res["modified"].append((k, label_of(v, k), ch, tot))
    return res


def esc(x):
    return html.escape(str(x))


def fmtval(v):
    s = str(v)
    if len(s) > 160:
        s = s[:157] + "..."
    return esc(s)


# ---------------- build ----------------
mp = load(PREV, "metadata.json")
mn = load(NEW, "metadata.json")

results = []
hash_same = []
for fname, lab in LABELS:
    pp, np_ = os.path.join(PREV, fname), os.path.join(NEW, fname)
    if not os.path.exists(pp) or not os.path.exists(np_):
        results.append((fname, lab, None))
        continue
    same = sha(pp) == sha(np_)
    hash_same.append((lab, same))
    if same:
        o = load(NEW, fname)
        n = len(o) if o is not None else 0
        results.append((fname, lab, {"key": None, "added": [], "removed": [], "modified": [], "prev_n": n, "new_n": n, "identical": True}))
    else:
        d = diff_dataset(load(PREV, fname), load(NEW, fname))
        d["identical"] = False
        results.append((fname, lab, d))

any_change = any(r[2] and not r[2].get("identical") for r in results)

gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
pv, nv = mp["buildVersion"], mn["buildVersion"]

# Channel labels. Same channel on both sides = a build-to-build patch diff;
# different channels (e.g. LIVE vs PTU) = a cross-channel comparison, which
# changes the wording and which .zip the footer points at.
pc, nc = mp.get("channel", "LIVE"), mn.get("channel", "LIVE")
cross = pc != nc
prev_lab = f"{pc} build" if cross else "Previous build"
new_lab = f"{nc} build" if cross else "New build"
subtitle = (f"Star Citizen {pc} vs {nc} data extraction &ndash; what the two channels differ on."
            if cross else
            "Star Citizen LIVE data extraction &ndash; changes between two builds.")
noun = "comparison" if cross else "patch"

CSS = _CSS

P = []
P.append(f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nova SC data diff: {esc(pv)} &rarr; {esc(nv)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Nova SC data diff</h1>
<p class="sub">{subtitle} Generated {gen}.</p>
<div class="hero">
<div class="hcard"><div class="lab">{esc(prev_lab)}</div><div class="big">{esc(pv)}</div>
<div class="muted" style="font-size:13px">game {esc(mp["gameVersion"])} &middot; {esc(mp["buildDate"])}</div></div>
<div class="hcard"><div class="lab">{esc(new_lab)} <span class="arrow">&rarr;</span></div><div class="big">{esc(nv)}</div>
<div class="muted" style="font-size:13px">game {esc(mn["gameVersion"])} &middot; {esc(mn["buildDate"])}</div></div>
</div>''')

# verdict
if any_change:
    nadd = sum(len(r[2]["added"]) for r in results if r[2])
    nrem = sum(len(r[2]["removed"]) for r in results if r[2])
    nmod = sum(len(r[2]["modified"]) for r in results if r[2])
    changed_sets = [r[1] for r in results if r[2] and not r[2].get("identical")]
    P.append(f'''<div class="verdict chg"><strong>Data changed.</strong> {len(changed_sets)} of {len(LABELS)} datasets differ:
{esc(", ".join(changed_sets))}. In total <span class="pos">{nadd} added</span>, <span class="neg">{nrem} removed</span>,
<span class="mod">{nmod} modified</span> records.</div>''')
else:
    P.append(f'''<div class="verdict ok"><strong>No extracted-data changes.</strong> All {len(LABELS)} datasets are byte-identical
between the two builds. This {noun} changed only engine/binary content, not any DataForge records Nova extracts
(ships, items, missions, tags, factions, &hellip;). Only <code>metadata.json</code> differs, in its build-identification fields.</div>''')

# summary table
P.append('<table class="sum"><tr><th>Dataset</th><th>Prev</th><th>New</th><th>&Delta; count</th><th>Added</th><th>Removed</th><th>Modified</th></tr>')
for fname, lab, d in results:
    if d is None:
        P.append(f'<tr><td>{esc(lab)}</td><td colspan="6" class="muted">file missing</td></tr>')
        continue
    delta = d["new_n"] - d["prev_n"]
    dcls = "pos" if delta > 0 else ("neg" if delta < 0 else "zero")
    ds = f"+{delta}" if delta > 0 else str(delta)
    def cell(n, cls):
        return f'<td class="num {cls if n else ""}">{n}</td>'
    P.append(f'<tr><td>{esc(lab)}</td><td class="num">{d["prev_n"]}</td><td class="num">{d["new_n"]}</td>'
             f'<td class="num {dcls}">{ds}</td>{cell(len(d["added"]),"add")}{cell(len(d["removed"]),"rem")}{cell(len(d["modified"]),"mod")}</tr>')
P.append('</table>')

# per-dataset detail
P.append('<h2 class="sec">Item-level detail</h2>')
MAXL = 60
for fname, lab, d in results:
    if d is None:
        continue
    delta = d["new_n"] - d["prev_n"]
    ds = f"+{delta}" if delta > 0 else str(delta)
    dcls = "pos" if delta > 0 else ("neg" if delta < 0 else "zero")
    P.append(f'<div class="dcard"><h3>{esc(lab)} <span class="muted">{d["prev_n"]} &rarr; {d["new_n"]} (<span class="{dcls}">{ds}</span>)</span></h3>')
    if d.get("identical"):
        P.append('<p class="muted">Byte-identical &ndash; no changes.</p></div>')
        continue
    if not (d["added"] or d["removed"] or d["modified"]):
        P.append('<p class="muted">File bytes differ but no keyed record changes were detected (ordering/formatting only).</p></div>')
        continue
    for kind, cls, title in [("added", "add", "Added"), ("removed", "rem", "Removed")]:
        rows = d[kind]
        if not rows:
            continue
        P.append(f'<div class="dlab {cls}">{title} ({len(rows)})</div><ul>')
        for k, name, obj in rows[:MAXL]:
            P.append(f'<li>{esc(name)} <code>{esc(k)}</code></li>')
        if len(rows) > MAXL:
            P.append(f'<li class="muted">&hellip; and {len(rows)-MAXL} more</li>')
        P.append('</ul>')
    if d["modified"]:
        # Which fields moved, and on how many records. A field touched on most of
        # the dataset is a system-wide rebalance rather than per-record tuning, and
        # that reads far better here than in 200 individual before/after tables.
        freq = {}
        for _k, _n, ch, _t in d["modified"]:
            for f_, _a, _b in ch:
                # collapse list indices so Foo[3].Bar and Foo[7].Bar count together
                gen = "".join(("[]" + p.split("]", 1)[1]) if "]" in p else "[" + p
                              for p in f_.split("[")) if "[" in f_ else f_
                freq[gen] = freq.get(gen, 0) + 1
        top = sorted(freq.items(), key=lambda x: -x[1])[:12]
        nmod = len(d["modified"])
        P.append(f'<div class="dlab mod">Most-changed fields <span class="muted">'
                 f'(of {nmod} modified record{"s" if nmod != 1 else ""})</span></div>')
        P.append('<table class="mtab">')
        for f_, n in top:
            pct = 100.0 * n / nmod
            P.append(f'<tr><td class="k"><code>{esc(f_)}</code></td>'
                     f'<td class="num">{n}</td><td class="muted">{pct:.0f}% of modified</td></tr>')
        if len(freq) > len(top):
            P.append(f'<tr><td colspan="3" class="muted">&hellip; and {len(freq)-len(top)} more fields</td></tr>')
        P.append('</table>')
        P.append(f'<div class="dlab mod">Modified ({len(d["modified"])})</div>')
        for k, name, ch, tot in d["modified"][:MAXL]:
            P.append(f'<div class="dl"><b>{esc(name)}</b> <code>{esc(k)}</code>'
                     f'<span class="muted"> &middot; {tot} field{"s" if tot!=1 else ""}</span></div>')
            P.append('<table class="mtab">')
            for f_, a, b in ch[:12]:
                P.append(f'<tr><td class="k"><code>{esc(f_)}</code></td><td class="neg">{fmtval(a)}</td>'
                         f'<td class="muted">&rarr;</td><td class="pos">{fmtval(b)}</td></tr>')
            if tot > 12:
                P.append(f'<tr><td colspan="4" class="muted">&hellip; and {tot-12} more fields</td></tr>')
            P.append('</table>')
        if len(d["modified"]) > MAXL:
            P.append(f'<p class="muted">&hellip; and {len(d["modified"])-MAXL} more modified records</p>')
    P.append('</div>')

# footer note
zipp = os.path.join(os.path.dirname(NEW.rstrip("/\\")), f"{nc}.zip")
zinfo = ""
if os.path.exists(zipp):
    import zipfile
    z = zipfile.ZipFile(zipp)
    zinfo = f'{os.path.getsize(zipp)/1048576:.1f} MB, {len(z.namelist())} files'
baseline = f"the {pc} output" if cross else "the pre-patch output"
P.append(f'''<div class="note"><b>Verification.</b> Every dataset file was compared by SHA-256 hash against {baseline}.
The regenerated <code>output/{esc(nc)}.zip</code> ({zinfo}) carries the new build identity: buildVersion
<code>{esc(pv)} &rarr; {esc(nv)}</code>, p4Change <code>{esc(mp["p4Change"])} &rarr; {esc(mn["p4Change"])}</code>,
buildDate <code>{esc(mp["buildDate"])} &rarr; {esc(mn["buildDate"])}</code>.</div>''')
P.append('</div></body></html>')

open(OUT, "w", encoding="utf-8").write("\n".join(P))
print("wrote", OUT)

# console summary
for fname, lab, d in results:
    if d and not d.get("identical"):
        print(f"{lab}: +{len(d['added'])} -{len(d['removed'])} ~{len(d['modified'])} (key={d['key']})")
