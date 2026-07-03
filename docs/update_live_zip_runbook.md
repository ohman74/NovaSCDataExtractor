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

## Notes
- `--channel LIVE` is deliberate: the bare `py -m nova` would also extract PTU if a newer
  PTU build exists. The user asked only for Live.
- A **code-only** change (no new game patch) does NOT need `--force`; instead delete
  `cache/LIVE/parsed_*.json` (keep `Data/`) and run without `--force` (~4 min). That is a
  different scenario from a game patch — see memory `feedback_full_extract_monitor`.
