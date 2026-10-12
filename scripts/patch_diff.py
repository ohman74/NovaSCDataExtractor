"""Generate an HTML diff report between two Nova output snapshots.

Usage:
    py scripts/patch_diff.py <prev_dir> <new_dir> <out.html> [--max N]

Example (after a patch re-extract, with the pre-patch output snapshotted):
    py scripts/patch_diff.py output/_prev_4.9.188.5236 output/LIVE         reports/patch_diff_4.9.188.5236_to_23497.html

Cross-channel comparison (LIVE vs PTU) works the same way and re-words itself:
    py scripts/patch_diff.py output/LIVE output/PTU         reports/channel_diff_LIVE_x_to_PTU_y.html

Datasets are keyed GUID-first (reference / GUID / TargetGUID / Id), falling back to
ClassName and then to a composite key, so records are matched by identity rather than
by list position. Files whose SHA-256 matches are reported as byte-identical and skipped.

Nothing is truncated by default: every added / removed / modified record and every
changed field is rendered. `--max N` caps per-category record lists if that is ever
wanted. Categories are collapsible <details> blocks so the page stays navigable.

Quantum travel components (QuantumDrive / JumpDrive / QuantumInterdictionGenerator) get
their own spotlight section: a ship's quantum performance is a property of the drive it
has equipped, so the component diff is the authoritative view and the ship-side rows only
matter when a default loadout swaps to a different drive.

That same principle is generalised in two further sections:
  * "Components" - every changed ship component grouped by component type, each with the
    ships it is fitted to.
  * "Ships - what changed on the hull" - each changed ship field is attributed either to a
    component (the port's component stats moved while the component itself stayed the same)
    or to the ship (loadout swap, port structure, hull/flight values). Component-caused ship
    rows are folded away and pointed at the component instead of being repeated per ship.
"""
import json, os, sys, hashlib, datetime, html

argv = [a for a in sys.argv[1:]]
MAXL = 0  # 0 = unlimited
if "--max" in argv:
    i = argv.index("--max")
    MAXL = int(argv[i + 1])
    del argv[i:i + 2]
if len(argv) != 3:
    sys.exit(__doc__)
PREV, NEW, OUT = argv

_CSS = r"""
:root{--bg:#0f1216;--card:#181d24;--edge:#262d38;--txt:#e6e9ee;--mut:#96a0b0;--acc:#4da3ff;--pos:#4ade80;--neg:#f87171;--mod:#fbbf24;--qd:#a78bfa;}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--txt)}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 4px}
.sub{color:var(--mut);margin:0 0 24px;font-size:14px}
.hero{display:flex;gap:16px;flex-wrap:wrap;margin:0 0 28px}
.hcard{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:14px 18px;flex:1;min-width:200px}
.hcard .lab{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.hcard .big{font-size:20px;font-weight:600;margin-top:4px}
.arrow{color:var(--acc)}
table.sum{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--edge);border-radius:12px;overflow:hidden;margin-bottom:16px}
table.sum th,table.sum td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--edge)}
table.sum th{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em;background:#141a21}
table.sum td.num{text-align:right;font-variant-numeric:tabular-nums}
table.sum a{color:var(--txt);text-decoration:none;border-bottom:1px dotted var(--mut)}
table.sum a:hover{color:var(--acc);border-bottom-color:var(--acc)}
td.add{color:var(--pos)} td.rem{color:var(--neg)} td.mod{color:var(--mod)}
.pos{color:var(--pos)} .neg{color:var(--neg)} .zero{color:var(--mut)} .num{font-variant-numeric:tabular-nums}
.verdict{border-radius:12px;padding:14px 18px;margin:0 0 24px;border:1px solid var(--edge);line-height:1.5}
.verdict.ok{background:rgba(74,222,128,.08);border-color:rgba(74,222,128,.35)}
.verdict.ok strong{color:var(--pos)}
.verdict.chg{background:rgba(251,191,36,.08);border-color:rgba(251,191,36,.4)}
.verdict.chg strong{color:var(--mod)}
.note{background:var(--card);border:1px solid var(--edge);border-radius:12px;padding:14px 18px;margin:0 0 24px;color:var(--mut);font-size:14px;line-height:1.6}
.note code{color:var(--txt);background:#141a21;padding:1px 5px;border-radius:5px;font-size:13px}
.note b{color:var(--txt)}
h2.sec{font-size:18px;margin:32px 0 12px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 18px}
.btn{background:#141a21;border:1px solid var(--edge);color:var(--txt);border-radius:8px;padding:6px 12px;font-size:13px;cursor:pointer}
.btn:hover{border-color:var(--acc);color:var(--acc)}
a.btn{text-decoration:none;display:inline-block}
.bar input{background:#141a21;border:1px solid var(--edge);color:var(--txt);border-radius:8px;padding:6px 12px;font-size:13px;min-width:260px}
.bar input:focus{outline:none;border-color:var(--acc)}
.bar .hint{color:var(--mut);font-size:12.5px}
.dcard{background:var(--card);border:1px solid var(--edge);border-radius:12px;margin:0 0 14px;overflow:hidden}
details>summary{cursor:pointer;list-style:none;user-select:none}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"\25B8";display:inline-block;width:1em;color:var(--mut);transition:transform .12s}
details[open]>summary::before{transform:rotate(90deg)}
.dcard>summary{padding:13px 18px;font-size:16px;font-weight:600}
.dcard>summary:hover{background:#1c222b}
.dcard>summary .muted{font-weight:400}
.dbody{padding:2px 18px 16px}
.grp{margin:10px 0 0;border-left:2px solid var(--edge);padding-left:12px}
.grp>summary{font-size:12px;text-transform:uppercase;letter-spacing:.03em;font-weight:600;padding:4px 0}
.grp.add>summary{color:var(--pos)} .grp.rem>summary{color:var(--neg)} .grp.mod>summary{color:var(--mod)}
.grp.add{border-left-color:rgba(74,222,128,.4)} .grp.rem{border-left-color:rgba(248,113,113,.4)} .grp.mod{border-left-color:rgba(251,191,36,.4)}
.dcard ul{margin:4px 0 8px;padding-left:20px}
.dcard li{font-size:13.5px;margin:1px 0}
code{background:#141a21;padding:1px 5px;border-radius:5px;font-size:12.5px;color:var(--acc)}
.muted{color:var(--mut)}
.rec{margin:2px 0;padding-left:10px;border-left:1px solid var(--edge)}
.rec>summary{padding:3px 0;font-size:13.5px}
.rec>summary b{font-weight:600}
table.mtab{width:100%;border-collapse:collapse;margin:2px 0 8px}
table.mtab td{padding:4px 8px;border-bottom:1px solid var(--edge);font-size:13px;vertical-align:top}
table.mtab td.k{font-weight:600;white-space:nowrap;width:1%;padding-right:16px}
table.mtab td.v{white-space:nowrap;font-variant-numeric:tabular-nums}
table.mtab td.w{white-space:pre-wrap;overflow-wrap:anywhere;max-width:40%}
.old{color:var(--neg)} .new{color:var(--pos)}
.qd{border-color:rgba(167,139,250,.45)}
.qd>summary{color:var(--qd)}
.qdname{font-size:15px;font-weight:600;margin:14px 0 2px;color:var(--txt)}
.qdmeta{color:var(--mut);font-size:12.5px;margin:0 0 4px}
.chip{display:inline-block;background:#141a21;border:1px solid var(--edge);border-radius:999px;padding:1px 9px;font-size:12px;color:var(--mut);margin-left:6px}
.delta{font-size:12px;color:var(--mut);margin-left:6px}
.delta.up{color:var(--pos)} .delta.down{color:var(--neg)}
"""

_JS = r"""
function setAll(o){document.querySelectorAll('details').forEach(function(d){d.open=o;});}
function filterRecs(q){
  q=q.trim().toLowerCase();
  document.querySelectorAll('.rec,.dcard li,.qdrec').forEach(function(el){
    el.style.display=(!q||el.textContent.toLowerCase().indexOf(q)>=0)?'':'none';
  });
  if(q){document.querySelectorAll('details').forEach(function(d){d.open=true;});}
}
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
    ("loot_locations.json", "Loot locations"),
]

KEY_CANDIDATES = ["reference", "GUID", "TargetGUID", "Id", "ClassName", "className"]
NAME_FIELDS = ["Name", "DisplayName", "Title", "TargetName", "name", "itemName", "ClassName", "className"]
# Identity fields used to key list elements when flattening, so a reordered or
# newly-inserted array element does not shift every following index and fake a diff.
LIST_ID_FIELDS = ["PortName", "reference", "GUID", "ClassName", "className", "Name", "Id"]

# Components that determine quantum travel. A ship's quantum speed / range / spool
# is a property of the drive fitted to it, so these get their own section.
QUANTUM_TYPES = {"QuantumDrive", "JumpDrive", "QuantumInterdictionGenerator"}


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


def list_tags(lst):
    """Index labels for a list: an identity field's values if unique, else positions."""
    if lst and all(isinstance(x, dict) for x in lst):
        for f in LIST_ID_FIELDS:
            if all(f in x and isinstance(x[f], (str, int)) for x in lst):
                vals = [str(x[f]) for x in lst]
                if len(set(vals)) == len(vals) and all(v and "]" not in v for v in vals):
                    return vals
    return [str(i) for i in range(len(lst))]


def flat(o, prefix=""):
    """Flatten nested dict/list into dotted paths for field-level diffing."""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flat(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(o, list):
        if not o:
            out[prefix] = "[]"
        for tag, v in zip(list_tags(o), o):
            out.update(flat(v, f"{prefix}[{tag}]"))
    else:
        out[prefix] = o
    return out


_MISS = object()


def pair_tags(a, b):
    """One tagging scheme for both sides of a list, so the same element lines up.

    Tagging each side on its own goes wrong when an identity field exists on one side only:
    the old list keys by position, the new one by name, and every element then reads as
    removed-and-added. The chosen field must therefore be usable on both sides.
    """
    for f in LIST_ID_FIELDS:
        if all(isinstance(x, dict) and isinstance(x.get(f), (str, int)) for x in a + b):
            va, vb = [str(x[f]) for x in a], [str(x[f]) for x in b]
            if (len(set(va)) == len(va) and len(set(vb)) == len(vb)
                    and all(v and "]" not in v for v in va + vb)):
                return va, vb
    return [str(i) for i in range(len(a))], [str(i) for i in range(len(b))]


def flat2(a, b, prefix=""):
    """Flatten two structures in lockstep, keying list elements identically on both sides."""
    fa, fb = {}, {}
    if isinstance(a, dict) and isinstance(b, dict):
        for k in dict.fromkeys(list(a) + list(b)):
            sa, sb = flat2(a.get(k, _MISS), b.get(k, _MISS), f"{prefix}.{k}" if prefix else str(k))
            fa.update(sa)
            fb.update(sb)
        return fa, fb
    if isinstance(a, list) and isinstance(b, list):
        ta, tb = pair_tags(a, b)
        ma, mb = dict(zip(ta, a)), dict(zip(tb, b))
        if not a:
            fa[prefix] = "[]"
        if not b:
            fb[prefix] = "[]"
        for t in dict.fromkeys(ta + tb):
            sa, sb = flat2(ma.get(t, _MISS), mb.get(t, _MISS), f"{prefix}[{t}]")
            fa.update(sa)
            fb.update(sb)
        return fa, fb
    if a is not _MISS:
        fa.update(flat(a, prefix))
    if b is not _MISS:
        fb.update(flat(b, prefix))
    return fa, fb


def diff_fields(a, b, limit=0):
    fa, fb = flat2(a, b)
    keys = sorted(set(fa) | set(fb))
    ch = []
    for k in keys:
        va, vb = fa.get(k, "<absent>"), fb.get(k, "<absent>")
        if va != vb:
            ch.append((k, va, vb))
    return (ch[:limit] if limit else ch), len(ch)


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
                res["modified"].append((k, label_of(new[k], k) if isinstance(new[k], dict) else k, ch, tot, prev[k], new[k]))
        return res
    prev, new = prev or [], new or []
    res["prev_n"], res["new_n"] = len(prev), len(new)
    kp, kn = pick_key(prev), pick_key(new)
    kf = (kn or kp)
    if not kf:
        return res
    res["key"] = kf[0]
    fn = kf[1]
    mp_ = {fn(i): i for i in prev}
    mn_ = {fn(i): i for i in new}
    for k, v in mn_.items():
        if k not in mp_:
            res["added"].append((k, label_of(v, k), v))
    for k, v in mp_.items():
        if k not in mn_:
            res["removed"].append((k, label_of(v, k), v))
    for k, v in mn_.items():
        if k in mp_ and mp_[k] != v:
            ch, tot = diff_fields(mp_[k], v)
            res["modified"].append((k, label_of(v, k), ch, tot, mp_[k], v))
    return res


def esc(x):
    return html.escape(str(x))


def numfmt(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    av = abs(v)
    if av >= 1e12 or (av < 1e-4 and av > 0):
        return f"{v:.4g}"
    if isinstance(v, int) or float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.4g}"


def fmtval(v):
    n = numfmt(v)
    if n is not None:
        return esc(n)
    return esc(v)


def delta_span(a, b):
    """Percent/absolute delta chip for a numeric before/after pair."""
    if isinstance(a, bool) or isinstance(b, bool):
        return ""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return ""
    try:
        d = b - a
    except Exception:
        return ""
    if d == 0:
        return ""
    cls = "up" if d > 0 else "down"
    if a:
        pct = 100.0 * d / abs(a)
        if abs(pct) >= 1000:
            return f'<span class="delta {cls}">&times;{b / a:,.1f}</span>' if a else ""
        return f'<span class="delta {cls}">{pct:+.1f}%</span>'
    return f'<span class="delta {cls}">{numfmt(d) or d}</span>'


def field_table(changes):
    out = ['<table class="mtab">']
    for f_, a, b in changes:
        # Numbers stay on one tabular line; free text (descriptions, tag lists) wraps
        # rather than being cut off, since the whole point here is to skip nothing.
        cls = "v" if (numfmt(a) is not None or numfmt(b) is not None) else "w"
        out.append(f'<tr><td class="k"><code>{esc(f_)}</code></td><td class="{cls} neg">{fmtval(a)}</td>'
                   f'<td class="muted">&rarr;</td><td class="{cls} pos">{fmtval(b)}{delta_span(a, b)}</td></tr>')
    out.append('</table>')
    return "".join(out)


def anchor(fname):
    return "ds-" + fname.replace(".json", "").replace("_", "-")


# ---------------- build ----------------
mp = load(PREV, "metadata.json")
mn = load(NEW, "metadata.json")

results = []
for fname, lab in LABELS:
    pp, np_ = os.path.join(PREV, fname), os.path.join(NEW, fname)
    if not os.path.exists(pp) or not os.path.exists(np_):
        results.append((fname, lab, None))
        continue
    if sha(pp) == sha(np_):
        o = load(NEW, fname)
        n = len(o) if o is not None else 0
        results.append((fname, lab, {"key": None, "added": [], "removed": [], "modified": [],
                                     "prev_n": n, "new_n": n, "identical": True}))
    else:
        d = diff_dataset(load(PREV, fname), load(NEW, fname))
        d["identical"] = False
        results.append((fname, lab, d))

by_file = {f: d for f, _l, d in results}
any_change = any(r[2] and not r[2].get("identical") for r in results)

generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
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
            f"Star Citizen {nc} data extraction &ndash; changes between two builds.")
noun = "comparison" if cross else "patch"

P = []
P.append(f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nova SC data diff: {esc(pv)} &rarr; {esc(nv)}</title>
<style>{_CSS}</style><script>{_JS}</script></head><body><div class="wrap">
<h1>Nova SC data diff</h1>
<p class="sub">{subtitle} Generated {generated}.</p>
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
    nfld = sum(t for r in results if r[2] for _k, _n, _c, t, _a, _b in r[2]["modified"])
    changed_sets = [r[1] for r in results if r[2] and not r[2].get("identical")]
    P.append(f'''<div class="verdict chg"><strong>Data changed.</strong> {len(changed_sets)} of {len(LABELS)} datasets differ:
{esc(", ".join(changed_sets))}. In total <span class="pos">{nadd} added</span>, <span class="neg">{nrem} removed</span>,
<span class="mod">{nmod} modified</span> records, covering {nfld:,} changed fields. Everything is listed below &ndash;
nothing is truncated.</div>''')
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
    name_cell = esc(lab) if d.get("identical") else f'<a href="#{anchor(fname)}">{esc(lab)}</a>'
    P.append(f'<tr><td>{name_cell}</td><td class="num">{d["prev_n"]}</td><td class="num">{d["new_n"]}</td>'
             f'<td class="num {dcls}">{ds}</td>{cell(len(d["added"]), "add")}{cell(len(d["removed"]), "rem")}{cell(len(d["modified"]), "mod")}</tr>')
P.append('</table>')
P.append('<div class="bar"><span class="hint">Jump to:</span>'
         '<a class="btn" href="#quantum">Quantum travel</a>'
         '<a class="btn" href="#components">Components</a>'
         '<a class="btn" href="#ships">Ships</a>'
         '<a class="btn" href="#detail">Item-level detail</a></div>')

# ---------------- quantum travel spotlight ----------------
eq = by_file.get("vehicle_equipment.json")


def is_quantum(obj):
    if not isinstance(obj, dict):
        return False
    if obj.get("type") in QUANTUM_TYPES:
        return True
    std = obj.get("stdItem") or {}
    return str(std.get("Type", "")).split(".")[0] in QUANTUM_TYPES


q_added, q_removed, q_mod = [], [], []
if eq and not eq.get("identical"):
    q_added = [r for r in eq["added"] if is_quantum(r[2])]
    q_removed = [r for r in eq["removed"] if is_quantum(r[2])]
    q_mod = [r for r in eq["modified"] if is_quantum(r[5]) or is_quantum(r[4])]

# Ships whose *default* quantum drive changed. That is the only ship-side quantum
# fact that is not simply a consequence of which drive happens to be equipped.
hp = by_file.get("vehicle_hardpoints.json")
qd_swaps = []
if hp and not hp.get("identical"):
    for k, name, ch, _tot, _a, _b in hp["modified"]:
        rows = [(f_, a, b) for f_, a, b in ch
                if "QuantumDrives" in f_ and f_.endswith(("BaseLoadout.ClassName", "BaseLoadout.Name"))]
        if rows:
            qd_swaps.append((k, name, rows))


def qd_summary_rows(std):
    """Headline drive stats, for the added/removed listings."""
    q = (std or {}).get("QuantumDrive") or {}
    sj = q.get("StandardJump") or {}
    out = []
    for lab_, v in [("Speed", sj.get("Speed")), ("Cooldown", sj.get("Cooldown")),
                    ("Spool-up", sj.get("SpoolUpTime")), ("Fuel rate", q.get("FuelRate")),
                    ("Disconnect range", q.get("DisconnectRange"))]:
        if v is not None:
            out.append(f'{esc(lab_)} <b>{fmtval(v)}</b>')
    return " &middot; ".join(out)


if q_added or q_removed or q_mod or qd_swaps:
    P.append('<h2 class="sec" id="quantum">Quantum travel</h2>')
    P.append('''<div class="note"><b>Why this section exists.</b> A ship's quantum speed, spool-up, cooldown
and range are properties of the <b>quantum drive component</b> fitted to it, not of the hull. The component
diff below is therefore the authoritative view of what changed for quantum travel; the ship-level datasets
only reflect it through whichever drive sits in their default loadout. Ship rows worth caring about are the
ones where the default drive was <i>swapped</i> for a different one &ndash; those are listed separately.
Every one of these entries also appears in its own dataset section further down.</div>''')
    P.append(f'<details class="dcard qd" open><summary>Quantum drive components '
             f'<span class="muted">&middot; {len(q_added)} added, {len(q_removed)} removed, {len(q_mod)} modified</span></summary><div class="dbody">')
    for rows, cls, title in [(q_added, "add", "Added drives"), (q_removed, "rem", "Removed drives")]:
        if not rows:
            continue
        P.append(f'<details class="grp {cls}" open><summary>{title} ({len(rows)})</summary>')
        for k, name, obj in rows:
            std = obj.get("stdItem") or {}
            meta = f'{obj.get("type", "")} &middot; size {obj.get("size", "?")} &middot; grade {obj.get("grade", "?")} &middot; {obj.get("manufacturer", "")}'
            P.append(f'<div class="qdrec"><div class="qdname">{esc(std.get("Name") or name)} '
                     f'<span class="chip">{esc(obj.get("className", ""))}</span></div>'
                     f'<div class="qdmeta">{meta}</div><div class="qdmeta">{qd_summary_rows(std)}</div></div>')
        P.append('</details>')
    if q_mod:
        # Scannable matrix first: 57 collapsed drives are hard to compare, one table
        # of the headline numbers side by side is not.
        P.append('<details class="grp mod" open><summary>Overview &ndash; headline drive stats</summary>')
        P.append('<table class="mtab"><tr><td class="k muted">Drive</td><td class="muted">Size</td>'
                 '<td class="muted">Speed (Mm/s)</td><td class="muted">Cooldown (s)</td>'
                 '<td class="muted">Spool-up (s)</td><td class="muted">Fuel rate</td>'
                 '<td class="muted">Interdiction (s)</td></tr>')
        q_tbl = [r for r in q_mod if r[5].get("type") == "QuantumDrive"]
        for k, name, ch, tot, old, new in sorted(
                q_tbl, key=lambda r: ((r[5].get("size") or 0), str(r[5].get("stdItem", {}).get("Name") or r[1]))):
            fo, fn_ = flat2(old, new)

            def cellq(path, scale=1.0):
                a, b = fo.get(path), fn_.get(path)
                if a is None and b is None:
                    return '<td class="muted">&ndash;</td>'
                if isinstance(a, (int, float)) and not isinstance(a, bool) and scale != 1.0:
                    a = a / scale
                if isinstance(b, (int, float)) and not isinstance(b, bool) and scale != 1.0:
                    b = b / scale
                if a == b:
                    return f'<td class="v muted">{fmtval(b)}</td>'
                return f'<td class="v"><span class="neg">{fmtval(a)}</span> <span class="muted">&rarr;</span> ' \
                       f'<span class="pos">{fmtval(b)}</span>{delta_span(a, b)}</td>'
            std = new.get("stdItem") or {}
            P.append(f'<tr><td class="k">{esc(std.get("Name") or name)}</td>'
                     f'<td class="v muted">S{esc(new.get("size", "?"))}/G{esc(new.get("grade", "?"))}</td>'
                     + cellq("stdItem.QuantumDrive.StandardJump.Speed", 1e6)
                     + cellq("stdItem.QuantumDrive.StandardJump.Cooldown")
                     + cellq("stdItem.QuantumDrive.StandardJump.SpoolUpTime")
                     + cellq("stdItem.QuantumDrive.FuelRate")
                     + cellq("stdItem.QuantumDrive.InterdictionEffectTime")
                     + '</tr>')
        P.append('</table></details>')
        P.append(f'<details class="grp mod"><summary>Modified drives &ndash; every changed field ({len(q_mod)})</summary>')
        for k, name, ch, tot, old, new in q_mod:
            std = (new.get("stdItem") or {})
            disp = std.get("Name") or name
            qrows = [c for c in ch if c[0].startswith("stdItem.QuantumDrive")]
            others = [c for c in ch if not c[0].startswith("stdItem.QuantumDrive")]
            P.append(f'<details class="rec qdrec"><summary><b>{esc(disp)}</b> '
                     f'<code>{esc(new.get("className", k))}</code>'
                     f'<span class="muted"> &middot; {tot} field{"s" if tot != 1 else ""}'
                     f'{" &middot; " + str(len(qrows)) + " on the drive block" if qrows else ""}</span></summary>')
            if qrows:
                P.append('<div class="qdmeta">Quantum drive characteristics</div>')
                P.append(field_table([(c[0].replace("stdItem.QuantumDrive.", ""), c[1], c[2]) for c in qrows]))
            if others:
                P.append(f'<details class="grp"><summary>Other fields ({len(others)})</summary>')
                P.append(field_table(others))
                P.append('</details>')
            P.append('</details>')
        P.append('</details>')
    if not (q_added or q_removed or q_mod):
        P.append('<p class="muted">No quantum-travel component changed.</p>')
    P.append('</div></details>')

    if qd_swaps:
        P.append(f'<details class="dcard qd"><summary>Ships whose default quantum drive changed '
                 f'<span class="muted">&middot; {len(qd_swaps)} ship{"s" if len(qd_swaps) != 1 else ""}</span></summary><div class="dbody">')
        P.append('<table class="mtab">')
        for k, name, rows in qd_swaps:
            for f_, a, b in rows:
                P.append(f'<tr><td class="k">{esc(name)}</td><td class="v neg">{fmtval(a)}</td>'
                         f'<td class="muted">&rarr;</td><td class="v pos">{fmtval(b)}</td></tr>')
        P.append('</table></div></details>')
    elif hp and not hp.get("identical"):
        P.append('<div class="note">No ship changed which quantum drive it ships with by default.</div>')

# ---------------- component attribution ----------------
# A ship is mostly a rack of components. When a ship's numbers move, the cause is usually a
# component whose own stats moved, not the hull. So every changed ship field is attributed to
# either a component or the ship, components are reported once on their own terms, and the
# ship section keeps only what the components cannot explain.

def comp_type(obj):
    """Component family: the item's declared type, falling back to stdItem.Type's head."""
    if not isinstance(obj, dict):
        return "Other"
    t = obj.get("type")
    if not t or t == "UNDEFINED":
        t = str(((obj.get("stdItem") or {}).get("Type") or "")).split(".")[0]
    return t or "Other"


def comp_label(obj, fallback):
    std = (obj or {}).get("stdItem") or {}
    for v in (std.get("Name"), (obj or {}).get("name"), (obj or {}).get("className")):
        if isinstance(v, str) and v.strip() and not v.startswith("@"):
            return v
    return fallback


def comp_meta(obj):
    bits = []
    st = obj.get("subType")
    if st and st != "UNDEFINED":
        bits.append(str(st))
    if obj.get("size") is not None:
        bits.append(f'size {obj["size"]}')
    if obj.get("grade"):
        bits.append(f'grade {obj["grade"]}')
    if obj.get("classification"):
        bits.append(str(obj["classification"]))
    if obj.get("manufacturer"):
        bits.append(str(obj["manufacturer"]))
    return " &middot; ".join(esc(b) for b in bits)


def scan_installed(o, out, inside=False):
    """Every component ClassName in a ship's default loadout, at any depth.

    Ports carry their pick in `BaseLoadout.ClassName`; built-in items (flight controllers,
    fuel tanks) sit directly in an `InstalledItems` / `Ports` list with their own ClassName.
    The `inside` flag keeps the ship's own ClassName out of the result.
    """
    if isinstance(o, dict):
        bl = o.get("BaseLoadout")
        if isinstance(bl, dict) and bl.get("ClassName"):
            out.add(str(bl["ClassName"]))
        if inside and isinstance(o.get("ClassName"), str) and o["ClassName"]:
            out.add(str(o["ClassName"]))
        for k, v in o.items():
            scan_installed(v, out, k in ("InstalledItems", "Ports"))
    elif isinstance(o, list):
        for v in o:
            scan_installed(v, out, inside)


# ship ClassName -> the components it carries by default (both sides, so removed items count)
hp_prev_raw = load(PREV, "vehicle_hardpoints.json") or []
hp_new_raw = load(NEW, "vehicle_hardpoints.json") or []
ship_comps, ship_names, usage = {}, {}, {}
for side in (hp_prev_raw, hp_new_raw):
    for shp in side:
        if not isinstance(shp, dict):
            continue
        scn = str(shp.get("ClassName"))
        scan_installed(shp, ship_comps.setdefault(scn, set()))
        ship_names[scn] = shp.get("Name") or scn
for scn, comps in ship_comps.items():
    for c in comps:
        usage.setdefault(c, set()).add(scn)


def ships_using(class_name):
    return sorted(ship_names.get(s, s) for s in usage.get(class_name, ()))


def carried_changed(ship_class):
    """Changed components this ship carries by default, whatever its own record says."""
    return sorted(c for c in ship_comps.get(ship_class, ()) if c in comp_by_class)


# group the ship-equipment diff by component type
groups = {}
comp_by_class = {}    # className -> (kind, row)
if eq and not eq.get("identical"):
    for kind in ("added", "removed", "modified"):
        for row in eq[kind]:
            obj = row[2] if kind != "modified" else row[5]
            groups.setdefault(comp_type(obj), {"added": [], "removed": [], "modified": []})[kind].append(row)
            cls = obj.get("className") if isinstance(obj, dict) else None
            if cls:
                comp_by_class[str(cls)] = (kind, row)

fps = by_file.get("fps_equipment.json")
fps_groups = {}
if fps and not fps.get("identical"):
    for kind in ("added", "removed", "modified"):
        for row in fps[kind]:
            obj = row[2] if kind != "modified" else row[5]
            fps_groups.setdefault(comp_type(obj), {"added": [], "removed": [], "modified": []})[kind].append(row)


def comp_display(class_name):
    """Human label for a component ClassName that appears in the equipment diff."""
    ent = comp_by_class.get(class_name)
    if not ent:
        return class_name
    kind, row = ent
    obj = row[5] if kind == "modified" else row[2]
    return comp_label(obj if isinstance(obj, dict) else {}, class_name)


def group_anchor(prefix, name):
    return prefix + "-" + "".join(ch if ch.isalnum() else "-" for ch in str(name).lower())


def freq_table(mods, top=12):
    """Which fields moved across a set of modified records, and on how many of them."""
    freq = {}
    for _k, _n, ch, _t, _a, _b in mods:
        for f_, _a2, _b2 in ch:
            freq[collapse_idx(f_)] = freq.get(collapse_idx(f_), 0) + 1
    rows = sorted(freq.items(), key=lambda x: -x[1])[:top]
    out = ['<table class="mtab">']
    for f_, n in rows:
        out.append(f'<tr><td class="k"><code>{esc(f_)}</code></td><td class="num">{n}</td>'
                   f'<td class="muted">{100.0 * n / max(1, len(mods)):.0f}% of modified items</td></tr>')
    out.append('</table>')
    return "".join(out)


def collapse_idx(path):
    """Foo[a].Bar and Foo[b].Bar collapse to Foo[].Bar so they can be counted together."""
    if "[" not in path:
        return path
    return "".join(("[]" + p.split("]", 1)[1]) if "]" in p else "[" + p for p in path.split("["))


# --- attribution of ship-side fields -------------------------------------------------
# Ship records embed their installed components: weapon ports carry a BaseLoadout block,
# while thrusters, fuel tanks and flight controllers are inlined with their stats directly
# on the installed item. Both are components, so both are attributed away from the hull.
def node_prefix(path):
    """Longest prefix of a flattened path identifying the installed item / port it sits in."""
    best = -1
    for m in ("InstalledItems[", "Ports["):
        i = path.rfind(m)
        if i < 0:
            continue
        j = path.find("]", i)
        if j > best:
            best = j
    return path[:best + 1] if best > 0 else None


def node_ident(fmap, node):
    """The component identity of an installed node: its loadout class, else its own class."""
    for suffix in (".BaseLoadout.ClassName", ".ClassName"):
        v = fmap.get(node + suffix)
        if isinstance(v, str) and v:
            return v
    return None


# Every FuelManagement value follows from fitted parts: capacity from the fuel tanks, burn
# rates and usage from the thrusters, intake ratios from the fuel intakes. Same for thrust
# capacity, quantum spool time and the BaseLoadout totals.
DERIVED_STAT_PREFIXES = (
    "ComponentsMass", "BaseLoadout.", "ResourceNetwork.", "FuelManagement.",
    "FlightCharacteristics.ThrustCapacity", "FlightCharacteristics.MasterModes.QuantumDriveSpoolTime",
)

ships = {}
builtin = {}   # (group path, field) -> {(old, new): [(ship name, port)]}


def ship_entry(cn, name):
    return ships.setdefault(cn, {"name": name, "echo": {}, "swap": [], "port": [], "override": [],
                                 "schema": [], "guid": [], "derived": [], "hull": [], "builtin": 0})


def attribute_hardpoints(rec):
    k, name, ch, _tot, old, new = rec
    cn = str(new.get("ClassName", k))
    e = ship_entry(cn, new.get("Name") or name)
    fo, fnw = flat2(old, new)
    nodes_o = {node_prefix(p) for p in fo}
    nodes_n = {node_prefix(p) for p in fnw}
    for f_, a, b in ch:
        node = node_prefix(f_)
        absent = "<absent>" in (str(a), str(b))
        if node is None:
            # ship-level rollups inside the hardpoints tree (totals, quantities) vs real structure
            leaf = f_.rsplit(".", 1)[-1]
            if leaf.startswith("Total") or leaf == "ItemsQuantity":
                e["derived"].append((f_, a, b))
            elif f_.startswith("Hull.") or not f_.startswith("Hardpoints."):
                e["hull"].append((f_, a, b))
            else:
                e["port"].append((f_, a, b))
            continue
        if absent and (node not in nodes_o or node not in nodes_n):
            e["port"].append((f_, a, b))          # the whole port/item appeared or disappeared
            continue
        io, in_ = node_ident(fo, node), node_ident(fnw, node)
        if io and in_ and io != in_:
            e["swap"].append((f_, a, b))          # this port now holds a different component
            continue
        ident = in_ or io
        if f_.endswith(".Loadout") and ident:
            e["guid"].append((f_, a, b))          # loadout-entry GUID, same component
            continue
        if absent:
            e["schema"].append((f_, a, b))        # a single field appeared/disappeared
            continue
        if ident:
            if ident in comp_by_class:
                e["echo"].setdefault(ident, []).append((f_, a, b))
            else:
                e["override"].append((f_, a, b))  # installed copy differs, component record did not
            continue
        # inline built-in component (thruster, fuel tank, ...): roll up across all ships
        rel = f_[len(node) + 1:] if len(f_) > len(node) else f_
        port = node[node.rfind("[") + 1:-1]
        gp = "".join(("[]" + p.split("]", 1)[1]) if "]" in p else "[" + p for p in node.split("["))
        builtin.setdefault((gp, rel), {}).setdefault((a, b), []).append((e["name"], port))
        e["builtin"] += 1


def attribute_stats(rec):
    k, name, ch, _tot, _old, new = rec
    e = ship_entry(str(new.get("ClassName", k)), new.get("Name") or name)
    for f_, a, b in ch:
        (e["derived"] if f_.startswith(DERIVED_STAT_PREFIXES) else e["hull"]).append((f_, a, b))


def attribute_meta(rec):
    k, name, ch, _tot, _old, new = rec
    ship_entry(str(new.get("ClassName", k)), new.get("Name") or name)["hull"].extend(ch)


def dedupe(rows):
    """The Hull block lives in both the stats and the hardpoints file, so a hull change
    arrives twice. Same field, same before and after: report it once."""
    seen, out = set(), []
    for r in rows:
        key = (r[0], str(r[1]), str(r[2]))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


for _ds, _fn in (("vehicle_hardpoints.json", attribute_hardpoints),
                 ("vehicle_stats.json", attribute_stats),
                 ("vehicle_metadata.json", attribute_meta)):
    _d = by_file.get(_ds)
    if _d and not _d.get("identical"):
        for _rec in _d["modified"]:
            _fn(_rec)

for _e in ships.values():
    for _b in ("swap", "port", "override", "schema", "guid", "derived", "hull"):
        _e[_b] = dedupe(_e[_b])
    for _c in _e["echo"]:
        _e["echo"][_c] = dedupe(_e["echo"][_c])


# ---------------- components section ----------------
def render_comp_group(gname, g, prefix, with_ships):
    n_a, n_r, n_m = len(g["added"]), len(g["removed"]), len(g["modified"])
    P.append(f'<details class="dcard" id="{group_anchor(prefix, gname)}"><summary>{esc(gname)} '
             f'<span class="muted">&middot; <span class="pos">+{n_a}</span> <span class="neg">-{n_r}</span> '
             f'<span class="mod">~{n_m}</span></span></summary><div class="dbody">')
    for kind, cls, title in [("added", "add", "Added"), ("removed", "rem", "Removed")]:
        if not g[kind]:
            continue
        P.append(f'<details class="grp {cls}"><summary>{title} ({len(g[kind])})</summary><ul>')
        for k, name, obj in g[kind]:
            used = ships_using(str(obj.get("className"))) if with_ships else []
            u = f' <span class="chip">{len(used)} ship{"s" if len(used) != 1 else ""}</span>' if used else ""
            P.append(f'<li>{esc(comp_label(obj, name))} <code>{esc(obj.get("className", k))}</code> '
                     f'<span class="muted">{comp_meta(obj)}</span>{u}</li>')
        P.append('</ul></details>')
    if g["modified"]:
        P.append(f'<details class="grp mod" open><summary>Most-changed fields on this component type</summary>'
                 f'{freq_table(g["modified"])}</details>')
        P.append(f'<details class="grp mod"><summary>Modified &ndash; every changed field ({n_m})</summary>')
        for k, name, ch, tot, _old, new in sorted(g["modified"], key=lambda r: str(comp_label(r[5], r[1])).lower()):
            used = ships_using(str(new.get("className"))) if with_ships else []
            chip = (f'<span class="chip">on {len(used)} ship{"s" if len(used) != 1 else ""}</span>'
                    if with_ships and used else "")
            P.append(f'<details class="rec"><summary><b>{esc(comp_label(new, name))}</b> '
                     f'<code>{esc(new.get("className", k))}</code>'
                     f'<span class="muted"> &middot; {tot} field{"s" if tot != 1 else ""}</span>{chip}</summary>')
            P.append(f'<div class="qdmeta">{comp_meta(new)}</div>')
            P.append(field_table(ch))
            if used:
                P.append(f'<details class="grp"><summary>Fitted by default on ({len(used)})</summary>'
                         f'<p class="muted" style="font-size:13px">{esc(", ".join(used))}</p></details>')
            P.append('</details>')
        P.append('</details>')
    P.append('</div></details>')


if groups or fps_groups or builtin:
    P.append('<h2 class="sec" id="components">Components</h2>')
    P.append('''<div class="note"><b>Read this before the ship section.</b> Ship performance numbers &ndash; shield HP,
DPS, quantum speed, thrust, cooling, power &ndash; are properties of the <b>components</b> fitted to the hull. Every
changed component is listed here once, under its component type, together with the ships that carry it by default.
The ship section below deliberately does <i>not</i> repeat those numbers: a ship whose only difference is that its
shield generator got stronger is reported as a shield change, not as a ship change.</div>''')

    order = sorted(groups.items(), key=lambda kv: -sum(len(v) for v in kv[1].values()))
    if order:
        P.append('<table class="sum"><tr><th>Component type</th><th>Added</th><th>Removed</th><th>Modified</th>'
                 '<th>Changed fields</th><th>Ships affected</th></tr>')
        for gname, g in order:
            nf = sum(t for _k, _n, _c, t, _a, _b in g["modified"])
            touched = set()
            for row in g["added"] + g["removed"]:
                touched |= usage.get(str(row[2].get("className")), set())
            for row in g["modified"]:
                touched |= usage.get(str(row[5].get("className")), set())
            P.append(f'<tr><td><a href="#{group_anchor("cmp", gname)}">{esc(gname)}</a></td>'
                     f'<td class="num add">{len(g["added"])}</td><td class="num rem">{len(g["removed"])}</td>'
                     f'<td class="num mod">{len(g["modified"])}</td><td class="num">{nf:,}</td>'
                     f'<td class="num">{len(touched)}</td></tr>')
        P.append('</table>')
    for gname, g in order:
        render_comp_group(gname, g, "cmp", True)

    # Built-in components (thrusters, fuel tanks, ...) have no separate item record: they are
    # inlined on every ship. Reported as one cross-ship rebalance table instead of N ship rows.
    if builtin:
        n_rows = sum(len(v) for pairs in builtin.values() for v in pairs.values())
        P.append(f'<details class="dcard" id="cmp-builtin"><summary>Built-in ship components '
                 f'<span class="muted">&middot; thrusters, fuel tanks and other items with no separate item record '
                 f'&middot; {len(builtin)} field{"s" if len(builtin) != 1 else ""}, {n_rows:,} instances</span>'
                 f'</summary><div class="dbody">')
        P.append('<p class="muted">These components exist only inside the ship record, so the same value change shows '
                 'up once per ship that has one. Grouped by component slot, then by field: each row inside a field is '
                 'one value transition and the ship-mounted instances it covers.</p>')
        bygrp = {}
        for (gp, rel), pairs in builtin.items():
            bygrp.setdefault(gp, []).append((rel, pairs))
        for gp, fields in sorted(bygrp.items(), key=lambda kv: -sum(len(p) for _r, p in kv[1])):
            short = gp.replace("Hardpoints.Components.", "").replace(".InstalledItems[]", "")
            n_inst = sum(len(v) for _r, pairs in fields for v in pairs.values())
            P.append(f'<details class="grp mod" open><summary>{esc(short)} '
                     f'<span class="muted">({len(fields)} field{"s" if len(fields) != 1 else ""}, '
                     f'{n_inst:,} instances)</span></summary>')
            for rel, pairs in sorted(fields, key=lambda x: -sum(len(v) for v in x[1].values())):
                rows = sorted(pairs.items(), key=lambda kv: -len(kv[1]))
                inst = sum(len(v) for v in pairs.values())
                allships = {s for hits in pairs.values() for s, _p in hits}
                news = [b for (_a, b) in pairs if isinstance(b, (int, float)) and not isinstance(b, bool)]
                span = (f' &middot; new value {fmtval(min(news))} &ndash; {fmtval(max(news))}'
                        if len(set(news)) > 1 else "")
                P.append(f'<details class="rec"><summary><code>{esc(rel)}</code>'
                         f'<span class="muted"> &middot; {len(rows)} distinct change{"s" if len(rows) != 1 else ""}'
                         f' &middot; {inst:,} instances on {len(allships)} ships{span}</span></summary>'
                         f'<table class="mtab">')
                for (a, b), hits in rows:
                    shipset = sorted({s for s, _p in hits})
                    P.append(f'<tr><td class="v neg">{fmtval(a)}</td><td class="muted">&rarr;</td>'
                             f'<td class="v pos">{fmtval(b)}{delta_span(a, b)}</td>'
                             f'<td class="muted">{len(hits):,} instance{"s" if len(hits) != 1 else ""} on '
                             f'{len(shipset)} ship{"s" if len(shipset) != 1 else ""}</td>'
                             f'<td class="w muted">{esc(", ".join(shipset[:6]))}'
                             f'{"&hellip;" if len(shipset) > 6 else ""}</td></tr>')
                P.append('</table></details>')
            P.append('</details>')
        P.append('</div></details>')

    if fps_groups:
        P.append('<h2 class="sec" id="fps-components">FPS equipment, by type</h2>')
        for gname, g in sorted(fps_groups.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
            render_comp_group(gname, g, "fps", False)

# ---------------- ships: what the components cannot explain ----------------
if ships:
    REAL = ("swap", "port", "override", "hull")
    real = {c: e for c, e in ships.items() if any(e[b] for b in REAL)}
    only_comp = {c: e for c, e in ships.items()
                 if c not in real and (e["echo"] or e["derived"] or e["builtin"])}
    only_noise = {c: e for c, e in ships.items() if c not in real and c not in only_comp}
    n_echo = sum(len(v) for e in ships.values() for v in e["echo"].values())
    n_builtin = sum(e["builtin"] for e in ships.values())
    n_real = sum(len(e[b]) for e in ships.values() for b in REAL)
    n_der = sum(len(e["derived"]) for e in ships.values())
    n_noise = sum(len(e["guid"]) + len(e["schema"]) for e in ships.values())
    echo_comps = sorted({c for e in ships.values() for c in e["echo"]})

    P.append('<h2 class="sec" id="ships">Ships &ndash; what changed on the hull</h2>')
    P.append(f'''<div class="note"><b>How each ship field was attributed.</b> A value that moved on a fitted
component while the component in that port stayed the same is credited to the <b>component</b> and shown above, not
here. A changed component class in a port is a real ship decision (loadout swap). Ports added, removed, resized or
retagged, plus hull, armour, flight and fuel values, are <b>ship</b> changes. Values inlined for built-in components
(thrusters, fuel tanks) are rolled up once in <a href="#cmp-builtin">Built-in ship components</a> rather than repeated
per ship. Ship-level totals derived from the loadout (<code>ComponentsMass</code>,
<code>BaseLoadout.TotalShieldHP</code>, DPS, thrust and fuel-usage totals) follow from the components and are kept
separate. Loadout-entry GUIDs and single fields that only appeared or disappeared are noise.
<br><br>Of the changed ship fields: <b class="mod">{n_echo:,}</b> echo {len(echo_comps)} changed components,
<b class="mod">{n_builtin:,}</b> are built-in component values, <b class="mod">{n_der:,}</b> are loadout-derived
totals, <b class="muted">{n_noise:,}</b> are noise, and <b class="pos">{n_real:,}</b> are genuine ship-side changes
on <b>{len(real)}</b> of {len(ships)} changed ships.</div>''')

    if real:
        P.append(f'<details class="dcard" open><summary>Ships with genuine hull / loadout changes '
                 f'<span class="muted">&middot; {len(real)}</span></summary><div class="dbody">')
        for cn, e in sorted(real.items(), key=lambda kv: str(kv[1]["name"]).lower()):
            bits = [f'{len(e[b])} {lab_}' for b, lab_ in
                    (("swap", "loadout swaps"), ("port", "port changes"),
                     ("override", "instance overrides"), ("hull", "hull/flight")) if e[b]]
            P.append(f'<details class="rec"><summary><b>{esc(e["name"])}</b> <code>{esc(cn)}</code>'
                     f'<span class="muted"> &middot; {esc(", ".join(bits))}</span></summary>')
            for lab_, key, cls in (("Loadout swaps &ndash; this port now holds a different component", "swap", "add"),
                                   ("Port / hardpoint structure", "port", "mod"),
                                   ("Installed-component values whose item record did not change", "override", "mod"),
                                   ("Hull, armour, flight &amp; fuel", "hull", "mod")):
                if not e[key]:
                    continue
                P.append(f'<details class="grp {cls}" open><summary>{lab_} ({len(e[key])})</summary>'
                         f'{field_table(e[key])}</details>')
            carried = carried_changed(cn)
            if carried or e["derived"] or e["builtin"]:
                names = ", ".join(comp_display(c) for c in carried) or "-"
                P.append(f'<details class="grp"><summary class="muted">Also differs through its components '
                         f'({len(carried)} changed component{"s" if len(carried) != 1 else ""} fitted, '
                         f'{e["builtin"]} built-in values, {len(e["derived"])} derived totals)</summary>'
                         f'<p class="muted" style="font-size:13px">{esc(names)}</p>'
                         f'{field_table(e["derived"]) if e["derived"] else ""}</details>')
            if e["guid"] or e["schema"]:
                P.append(f'<details class="grp"><summary class="muted">Noise '
                         f'({len(e["guid"])} loadout GUIDs, {len(e["schema"])} appeared/disappeared fields)</summary>'
                         f'{field_table(e["guid"] + e["schema"])}</details>')
            P.append('</details>')
        P.append('</div></details>')

    if only_comp:
        P.append(f'<details class="dcard"><summary>Ships that differ only through their components '
                 f'<span class="muted">&middot; {len(only_comp)} &middot; nothing changed on the hull</span>'
                 f'</summary><div class="dbody">')
        P.append('<p class="muted">These hulls are untouched. Their numbers moved because a fitted component moved; '
                 'the differences themselves are in the Components section above.</p>')
        for cn, e in sorted(only_comp.items(), key=lambda kv: str(kv[1]["name"]).lower()):
            carried = carried_changed(cn)
            labels = [comp_display(c) for c in carried]
            P.append(f'<details class="rec"><summary><b>{esc(e["name"])}</b> <code>{esc(cn)}</code>'
                     f'<span class="muted"> &middot; {len(carried)} changed component'
                     f'{"s" if len(carried) != 1 else ""} fitted, '
                     f'{e["builtin"]} built-in values, {len(e["derived"])} derived totals</span></summary>'
                     f'<p class="muted" style="font-size:13px">{esc(", ".join(labels)) or "&ndash;"}</p>')
            if e["derived"]:
                P.append(f'<details class="grp"><summary>Loadout-derived ship totals ({len(e["derived"])})</summary>'
                         f'{field_table(e["derived"])}</details>')
            P.append('</details>')
        P.append('</div></details>')

    # A ship whose own record is byte-identical still flies differently if a component it
    # carries was rebalanced. That is invisible in the ship datasets, so it is spelled out here.
    untouched = {}
    for scn, nm in ship_names.items():
        if scn in ships:
            continue
        cc = carried_changed(scn)
        if cc:
            untouched[scn] = (nm, cc)
    if untouched:
        P.append(f'<details class="dcard"><summary>Ships with an unchanged record that still fly differently '
                 f'<span class="muted">&middot; {len(untouched)} &middot; a component they carry was changed</span>'
                 f'</summary><div class="dbody">')
        P.append('<p class="muted">Nothing in these ship records moved. They are listed because a component in '
                 'their default loadout was changed, so their in-game numbers move with it.</p>')
        for scn, (nm, cc) in sorted(untouched.items(), key=lambda kv: str(kv[1][0]).lower()):
            P.append(f'<details class="rec"><summary><b>{esc(nm)}</b> <code>{esc(scn)}</code>'
                     f'<span class="muted"> &middot; {len(cc)} changed component{"s" if len(cc) != 1 else ""}</span>'
                     f'</summary><p class="muted" style="font-size:13px">'
                     f'{esc(", ".join(comp_display(c) for c in cc))}</p></details>')
        P.append('</div></details>')

    if only_noise:
        P.append(f'<details class="dcard"><summary>Ships differing only in loadout GUIDs / field presence '
                 f'<span class="muted">&middot; {len(only_noise)} &middot; no functional change</span></summary>'
                 f'<div class="dbody"><p class="muted">'
                 f'{esc(", ".join(sorted(str(e["name"]) for e in only_noise.values())))}</p></div></details>')

# ---------------- per-dataset detail ----------------
P.append('<h2 class="sec" id="detail">Item-level detail</h2>')
P.append('<div class="bar"><button class="btn" onclick="setAll(true)">Expand all</button>'
         '<button class="btn" onclick="setAll(false)">Collapse all</button>'
         '<input type="search" placeholder="Filter records by name / class&hellip;" oninput="filterRecs(this.value)">'
         '<span class="hint">Every change is listed &ndash; nothing truncated.</span></div>')

for fname, lab, d in results:
    if d is None:
        continue
    delta = d["new_n"] - d["prev_n"]
    ds = f"+{delta}" if delta > 0 else str(delta)
    dcls = "pos" if delta > 0 else ("neg" if delta < 0 else "zero")
    changed = d["added"] or d["removed"] or d["modified"]
    counts = ""
    if changed:
        counts = (f' &middot; <span class="pos">+{len(d["added"])}</span> '
                  f'<span class="neg">-{len(d["removed"])}</span> '
                  f'<span class="mod">~{len(d["modified"])}</span>')
    P.append(f'<details class="dcard" id="{anchor(fname)}"><summary>{esc(lab)} '
             f'<span class="muted">{d["prev_n"]} &rarr; {d["new_n"]} (<span class="{dcls}">{ds}</span>)'
             f'{counts}</span></summary><div class="dbody">')
    if d.get("identical"):
        P.append('<p class="muted">Byte-identical &ndash; no changes.</p></div></details>')
        continue
    if not changed:
        P.append('<p class="muted">File bytes differ but no keyed record changes were detected (ordering/formatting only).</p></div></details>')
        continue
    for kind, cls, title in [("added", "add", "Added"), ("removed", "rem", "Removed")]:
        rows = d[kind]
        if not rows:
            continue
        shown = rows[:MAXL] if MAXL else rows
        P.append(f'<details class="grp {cls}"><summary>{title} ({len(rows)})</summary><ul>')
        for k, name, obj in shown:
            extra = ""
            if isinstance(obj, dict):
                bits = [str(obj[f]) for f in ("type", "subType", "Kind") if obj.get(f) and obj.get(f) != "UNDEFINED"]
                if bits:
                    extra = f' <span class="muted">{esc(" / ".join(bits))}</span>'
            P.append(f'<li>{esc(name)} <code>{esc(k)}</code>{extra}</li>')
        if MAXL and len(rows) > MAXL:
            P.append(f'<li class="muted">&hellip; and {len(rows) - MAXL} more</li>')
        P.append('</ul></details>')
    if d["modified"]:
        # Which fields moved, and on how many records. A field touched on most of
        # the dataset is a system-wide rebalance rather than per-record tuning, and
        # that reads far better here than in 200 individual before/after tables.
        freq = {}
        for _k, _n, ch, _t, _a, _b in d["modified"]:
            for f_, _a2, _b2 in ch:
                # collapse list indices so Foo[a].Bar and Foo[b].Bar count together
                g = "".join(("[]" + p.split("]", 1)[1]) if "]" in p else "[" + p
                            for p in f_.split("[")) if "[" in f_ else f_
                freq[g] = freq.get(g, 0) + 1
        top = sorted(freq.items(), key=lambda x: -x[1])
        nmod = len(d["modified"])
        P.append(f'<details class="grp mod" open><summary>Most-changed fields '
                 f'<span class="muted">(of {nmod} modified record{"s" if nmod != 1 else ""})</span></summary>')
        P.append('<table class="mtab">')
        for f_, n in top:
            pct = 100.0 * n / nmod
            P.append(f'<tr><td class="k"><code>{esc(f_)}</code></td>'
                     f'<td class="num">{n}</td><td class="muted">{pct:.0f}% of modified records</td></tr>')
        P.append('</table></details>')
        rows = d["modified"]
        shown = rows[:MAXL] if MAXL else rows
        P.append(f'<details class="grp mod"><summary>Modified ({len(rows)})</summary>')
        for k, name, ch, tot, _old, _new in shown:
            P.append(f'<details class="rec"><summary><b>{esc(name)}</b> <code>{esc(k)}</code>'
                     f'<span class="muted"> &middot; {tot} field{"s" if tot != 1 else ""}</span></summary>')
            P.append(field_table(ch))
            P.append('</details>')
        if MAXL and len(rows) > MAXL:
            P.append(f'<p class="muted">&hellip; and {len(rows) - MAXL} more modified records</p>')
        P.append('</details>')
    P.append('</div></details>')

# footer note
zipp = os.path.join(os.path.dirname(NEW.rstrip("/\\")), f"{nc}.zip")
zinfo = ""
if os.path.exists(zipp):
    import zipfile
    z = zipfile.ZipFile(zipp)
    zinfo = f'{os.path.getsize(zipp) / 1048576:.1f} MB, {len(z.namelist())} files'
baseline = f"the {pc} output" if cross else "the pre-patch output"
P.append(f'''<div class="note"><b>Verification.</b> Every dataset file was compared by SHA-256 hash against {baseline}.
The regenerated <code>output/{esc(nc)}.zip</code> ({zinfo}) carries the new build identity: buildVersion
<code>{esc(pv)} &rarr; {esc(nv)}</code>, p4Change <code>{esc(mp["p4Change"])} &rarr; {esc(mn["p4Change"])}</code>,
buildDate <code>{esc(mp["buildDate"])} &rarr; {esc(mn["buildDate"])}</code>.
List elements are keyed by identity (port name, class name, GUID) rather than array position, so a reordered
or inserted element does not shift every following index into a false change.</div>''')
P.append('</div></body></html>')

open(OUT, "w", encoding="utf-8").write("\n".join(P))
print("wrote", OUT, f"({os.path.getsize(OUT) / 1048576:.1f} MB)")

# console summary
for fname, lab, d in results:
    if d and not d.get("identical"):
        nf = sum(t for _k, _n, _c, t, _a, _b in d["modified"])
        print(f"{lab}: +{len(d['added'])} -{len(d['removed'])} ~{len(d['modified'])} ({nf} fields, key={d['key']})")
