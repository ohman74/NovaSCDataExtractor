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


def diff_fields(a, b, limit=0):
    fa, fb = flat(a), flat(b)
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
    P.append('<h2 class="sec">Quantum travel</h2>')
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
            fo, fn_ = flat(old), flat(new)

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

# ---------------- per-dataset detail ----------------
P.append('<h2 class="sec">Item-level detail</h2>')
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
