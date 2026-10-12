# Runbook: "new patch, please update live.zip"

When the user says a **new patch** dropped and asks to **update `live.zip`**, they mean:
the local Star Citizen Live install was updated by the launcher, and `output/LIVE.zip`
must be re-generated from the new `Data.p4k`.

## 1. Confirm a new build is actually installed

Compare the installed game build against the last extract:

- **Installed build** — `D:/Games/Roberts Space Industries/StarCitizen/Live/build_manifest.id`
  (JSON; read `.Data.Version`, `.Data.BuildDateStamp`, `.Data.RequestedP4ChangeNum`).
- **Last extract** — `output/LIVE/metadata.json` (`buildVersion`, `p4Change`, `buildDate`).

If `buildVersion` already matches, there is nothing to do. Otherwise proceed.

## 1b. Snapshot the pre-patch output (required for the diff report)

`--force` overwrites `output/LIVE` in place, so copy it aside **before** extracting or the
old data is gone and no diff is possible:

```
cp -r output/LIVE output/_prev_<old buildVersion>
```

## 2. Re-extract (forced, Live-pinned)

A patch changes `Data.p4k`, so the unpacked cache under `cache/LIVE/Data` is stale and
**must** be re-unpacked. Use `--force` (wipes the channel cache + re-unpacks) and pin the
channel so PTU auto-detection doesn't tag along:

```
py -m nova --channel LIVE --force
```

Packaging to `output/LIVE.zip` happens automatically at the end (unless `--no-package`).
No separate zip step is needed — `package_output()` runs after the build
(`nova/__main__.py:447`, terminal line `Packaged N files -> ...LIVE.zip`).

### Timing & how to wait
- A forced extract re-unpacks the ~154 GB `Data.p4k`: roughly **5–25 min** end to end.
- Run it backgrounded to a log, then watch with **Monitor** (1 h cap), not plain Bash
  `run_in_background` (10 min cap — see memory `feedback_full_extract_monitor`).
- Terminal success marker in the log: `=== Done! Total time: ...`
  Packaging marker: `[PACKAGE] Zipping LIVE output...` then `Packaged ... -> ...LIVE.zip`.
- Failure markers to watch for: `Traceback`, `[ERROR]`, `MemoryError`.

## 3. Verify

After `=== Done!`:
- `output/LIVE/metadata.json` → `buildVersion` / `p4Change` now match the install.
- `output/LIVE.zip` mtime is fresh and size is sane (~3–4 MB).
- Sanity-check `counts` in metadata against the previous run for large unexpected drops.

## 4. Generate the change report

The user normally wants a report of what changed versus the previous build:

```
py scripts/patch_diff.py output/_prev_<old> output/LIVE \
    reports/patch_diff_<old>_to_<new short>.html
```

Self-contained HTML (CSS inlined), written to `reports/`. It hashes every dataset file,
lists added / removed / modified records per dataset, and shows field-level before/after
for modified ones. Records are keyed GUID-first (`reference`, `GUID`, `TargetGUID`, `Id`),
falling back to `ClassName` then a composite key, so matching is by identity, not list
position (see memory `feedback_identifier_hierarchy`).

### If the diff comes back empty
Empty diffs are common here: every LIVE patch from 4.9.186.42610 through 4.9.188.23497 left
all 16 datasets byte-identical, changing only engine/binary content. Before reporting "no
changes", confirm the run was not a silent no-op:
- `cache/LIVE` was wiped and re-created (directory mtime = run start), and every
  `parsed_*.json` was regenerated;
- the run took roughly 5–25 min, not seconds;
- `gameVersion` in `metadata.json` advanced (that value is read out of the game data).

`logs/dataforge_hashes.json` records a SHA-256 of the DataForge blob
`cache/LIVE/Data/Game2.dcb` per build. If the blob hash is unchanged from the previous
build, an empty diff is provably correct rather than merely plausible. Append to it after
each extract:

```
py -c "import hashlib,os,json;p='cache/LIVE/Data/Game2.dcb';h=hashlib.sha256(open(p,'rb').read()).hexdigest();m=json.load(open('output/LIVE/metadata.json'));d=json.load(open('logs/dataforge_hashes.json'));d[m['buildVersion']]={'p4Change':m['p4Change'],'buildDate':m['buildDate'],'game2_dcb_sha256':h,'size':os.path.getsize(p)};json.dump(d,open('logs/dataforge_hashes.json','w'),indent=2)"
```

## Notes
- `--channel LIVE` is deliberate: the bare `py -m nova` would also extract PTU if a newer
  PTU build exists. The user asked only for Live.
- A **code-only** change (no new game patch) does NOT need `--force`; instead delete
  `cache/LIVE/parsed_*.json` (keep `Data/`) and run without `--force` (~4 min). That is a
  different scenario from a game patch — see memory `feedback_full_extract_monitor`.
