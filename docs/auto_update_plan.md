# Plan: unattended Star Citizen patch acquisition + extraction

**Status: plan only. Nothing implemented.**

Goal: when CIG ships a new LIVE or PTU build, the machine picks it up, downloads it,
re-extracts, packages, and writes a diff report, with no human in the loop.

Today the chain is broken in exactly one place. Detection is solvable locally,
extraction and reporting are already automated by
[`update_live_zip_runbook.md`](./update_live_zip_runbook.md). The only manual step
left is clicking **UPDATE** in the RSI Launcher.

This document plans two ways to close that gap:

- **Alternative A** — drive the official launcher's own UI. Buildable today.
- **Alternative B** — call the launcher API / patcher CDN directly. Blocked on
  express written approval from RSI, and even then far more work than it looks.

Both share the same skeleton, so the choice is a swappable backend rather than two
codebases. A third degraded mode (acquisition disabled, notify only) falls out of the
same design for free and is documented at the end.

---

## 1. Findings that constrain the design

All verified locally on 2026-08-07 against RSI Launcher 2.15.4.

### 1.1 The launcher offers no sanctioned non-GUI trigger

Searched `C:\Program Files\Roberts Space Industries\RSI Launcher\resources\app.asar`
(331 MB):

| Looked for | Result |
| --- | --- |
| `autoDownload`, `autoInstallOnAppQuit` | Present, but they belong to **electron-updater** and govern the launcher's own self-update. Confirmed by surrounding code and by the i18n block `auto_update_dialog_title: "App Update Available"`. |
| Deep-link routes (`rsilauncher://...`) | Only `setAsDefaultProtocolClient("rsilauncher", ...)` inside electron-builder dev scaffolding, keyed off a `.js` entry point. No shipped route table. |
| CLI flags for install/update | None. The only `commandLine` parsing found belongs to a bundled config library. |
| Button state strings | Discrete states exist (`UPDATE`, `INSTALL`, `RESUME`, `VERIFY`), which is what makes state-gated clicking feasible. |

Conclusion: there is no supported headless way to start a game download. The button
is the only trigger.

### 1.2 The launcher log is a reliable machine-readable status source

`%APPDATA%\rsilauncher\logs\log.log`. Real lines:

```
{ "t":"2026-08-02 22:06:52.896", "[main][info] ": "[PatcherPhase] Starting delta update (SC PTU 4.10.0-ptu.12368639) in D:\\Games\\Roberts Space Industries\\StarCitizen (statistics enabled: false)"  },
{ "t":"2026-08-07 18:46:49.240", "[main][info] ": "[PatcherPhase] Delta update completed (SC PTU 4.10.0-ptu.12399239) in D:\\Games\\Roberts Space Industries\\StarCitizen\\PTU"  },
```

That yields channel, marketing version, changelist, target directory, and start/end
timestamps. Progress phases are logged too:

```
installer@open-p4k-start / -end
installer@retrieve-local-file-list-start / -end
installer@retrieve-remote-file-list-start / -end
installer@compute-file-list-difference-start / -end
installer@update-loose-files-start / -end
installer@update-p4k-structure-start / -end
installer@update-files-inside-p4k-start / -end
```

**Format caveat:** the file is *not* valid JSON. Each line is a JSON object followed by
a trailing comma, with no array wrapper, and the log key is the literal string
`"[main][info] "` (trailing space included). Parse line-by-line with a regex, never
`json.load`. Rotation exists (`log.old.log`), so a tailer must handle truncation and
file replacement.

`nova/config.py::get_launcher_patch()` already parses this file for the marketing
patch string, so the precedent and the path handling exist in-repo.

### 1.3 Rule boundaries

RSI Terms of Service, Section IV:

- Prohibits automated measures ("bots", "spiders", "scrapers") while using RSI
  Services, naming F5 abuse, automated refreshing, and data harvesting.
- Prohibits any connection "using programs or tools not expressly approved by RSI".

RSI EULA prohibits automation software designed to modify the game experience or give
an advantage over other players.

Which maps to:

| Zone | Activity | Assessment |
| --- | --- | --- |
| Green | Reading `build_manifest.id`, `Data.p4k` mtime, the launcher log; running `nova`; writing reports | Zero network contact with RSI. Outside the ToS entirely. |
| Green | Extracting ship/vehicle/FPS statistics from the local `Data.p4k` for loadout planning | Same category as Erkul, SPViewer, scunpacked, Star Citizen Wiki. Does not modify the game, does not touch the running client, no competitive advantage. Not the subject of any concern in this document. |
| Amber | Driving the **official** launcher's UI locally | All network traffic is still performed by the approved client. No auth bypass, no token reuse, no protocol reimplementation. No clause lands squarely, but it is formally automation, so not risk-free. |
| Red | Own code calling `api/launcher/v3/games/release` or the patcher CDN | Squarely "connection using programs or tools not expressly approved", plus "automated refreshing". Off the table unless RSI approves in writing. |

Note the amber/red split is about **how bits reach the disk**, not about what the data
is used for.

### 1.4 What RSI approval would and would not buy

A yes on `games/release` buys **detection only**, which is already solved for free in
the green zone by `build_manifest.id` plus the launcher log.

The valuable half is the download, and that runs over an undocumented delta format
that patches **inside** a 154 GB p4k container (see the `installer@update-p4k-structure`
and `installer@update-files-inside-p4k` phases above). Permission to connect does not
hand over the format specification, and the format changes when CIG wants it to.

So Alternative B, even fully approved, is more work and more fragile than Alternative
A, which inherits correctness across format changes for free because CIG's own patcher
does the work. **Plan around A. Treat B as an upgrade path that probably never opens.**

---

## 2. Shared architecture

```
scripts/auto_update/
├── __main__.py           orchestration, guards, kill switch, run log
├── config.py             loads auto_update_config.json, merges nova_config.json
├── build_state.py        per-channel installed-build tracking -> cache/build_state.json
├── launcher_log.py       tolerant tail/parse of %APPDATA%\rsilauncher\logs\log.log
├── acquire/
│   ├── base.py           Acquirer interface
│   ├── manual.py         no-op backend (degraded mode, section 5)
│   ├── launcher_ui.py    Alternative A
│   └── direct_api.py     Alternative B  [placeholder until RSI approves]
└── pipeline.py           snapshot -> nova -> package -> patch_diff -> dcb hash
scripts/install_task.ps1  registers the Windows scheduled task
docs/auto_update_plan.md  this file
```

### 2.1 Acquirer interface

```python
class Acquirer:
    def available(self, channel: str) -> AvailableBuild | None:
        """Is a newer build available for this channel? None = up to date."""

    def fetch(self, channel: str, target: AvailableBuild) -> FetchResult:
        """Bring the local install up to `target`. Blocks until done or fails."""
```

Everything upstream and downstream of these two calls is backend-agnostic. Swapping
`launcher_ui` for `direct_api` is a config value, not a refactor.

### 2.2 Run sequence

```
1. acquire lock (single instance) + check kill switch
2. guard: abort if StarCitizen.exe or StarCitizen_Launcher.exe is running
3. guard: abort if free disk < threshold
4. for channel in (LIVE, PTU):
     a. record installed build from build_manifest.id
     b. acquirer.available(channel)      -> skip channel if None
     c. acquirer.fetch(channel, target)  -> blocks
     d. re-read build_manifest.id, assert it advanced
     e. pipeline.run(channel, old_build, new_build)
5. write summary to logs/auto_update.log
6. release lock
```

Channels are processed sequentially, never in parallel. Two concurrent 150 GB delta
patches plus a 154 GB unpack would thrash the disk, and the launcher only patches one
channel at a time anyway.

### 2.3 Build state

`build_state.py` reads `<install>/build_manifest.id` and returns
`Version` / `RequestedP4ChangeNum` / `BuildDateStamp`, matching
`nova/config.py::get_version_info()`. Reuse that function rather than reimplementing it;
it already handles the missing-file and malformed-JSON cases.

Persist to `cache/build_state.json`:

```json
{
  "LIVE": {"version": "4.10.189.12935", "p4_change": "12399239",
           "extracted": true, "last_run": "2026-08-07T04:12:33"},
  "PTU":  {"version": "4.10.189.2187",  "p4_change": "12368639",
           "extracted": false, "last_run": null}
}
```

`extracted: false` lets a failed or interrupted pipeline be retried on the next tick
without re-downloading anything.

### 2.4 Configuration

`auto_update_config.json` (gitignored, sits next to `nova_config.json`):

```json
{
  "acquirer": "launcher_ui",
  "channels": ["LIVE", "PTU"],
  "launcher_exe": "C:/Program Files/Roberts Space Industries/RSI Launcher/RSI Launcher.exe",
  "launcher_log": "%APPDATA%/rsilauncher/logs/log.log",
  "min_free_gb": 250,
  "max_runtime_minutes": 240,
  "patch_stall_timeout_minutes": 30,
  "kill_switch_file": "./STOP_AUTO_UPDATE",
  "log_file": "./logs/auto_update.log",
  "dry_run": false
}
```

Per the chosen operating mode: no toast, no webhook, no email. Everything lands in
`logs/auto_update.log`. No per-run confirmation prompt.

### 2.5 Guard rails (both alternatives)

These are not optional. They are what keeps the amber zone amber.

| Guard | Behaviour |
| --- | --- |
| Never click LAUNCH / PLAY | Only act on a button whose state reads `UPDATE` or `INSTALL`. Any other state is a no-op. |
| Never type credentials | Entering passwords is out of scope, permanently. A login screen means abort and log. |
| Never accept EULA / ToS dialogs | An unrecognised modal means screenshot to `logs/`, abort, log. |
| Never patch under a running game | Abort if `StarCitizen.exe` is alive. `Data.p4k` must also be free for extraction. |
| Kill switch | Presence of `STOP_AUTO_UPDATE` in the repo root aborts before anything happens. |
| Max runtime | Hard wall-clock cap. Exceeded means kill launcher, log, exit non-zero. |
| Stall detection | No new `installer@*` phase line for N minutes means the patch is stuck. Abort. |
| Single instance | Lock file, so an overlapping schedule tick cannot double-run. |
| Dry run | `dry_run: true` walks the whole flow, logs every decision, clicks nothing and extracts nothing. |

---

## 3. Alternative A — drive the official launcher UI

Default. Buildable now. No dependency on any answer from RSI.

### 3.1 How it works

The launcher is Electron, so Chromium exposes a UI Automation tree to any UIA client.
Match elements by name and automation id, **not** by pixel coordinates, so a window
resize or a UI restyle degrades into a clean "element not found" abort rather than a
misplaced click.

Progress and completion are read from the launcher log (section 1.2), not from the UI.
The log is stable, timestamped and unambiguous; the UI is neither.

### 3.2 Implementation steps

**A0. Feasibility probe (do this first, before writing anything else).**
Read-only dump of the launcher's UIA tree with the launcher open and idle. Capture the
control types, names and automation ids for: the LIVE game card, the PTU game card, the
primary action button and its state text, the channel selector, and the settings entry.
Save to `docs/launcher_uia_tree.txt`. Everything downstream depends on what this shows.
If the tree turns out to be opaque (Chromium accessibility not exposed), Alternative A
is dead in its current form and the fallback is section 5.

Must be run when the user is not in-game.

**A1. Dependencies.** Add `pywinauto` and `psutil` to `requirements.txt`.
`pywinauto`'s `uia` backend pulls `comtypes`. Verify no conflict with the existing
`requests>=2.28.0` pin.

**A2. `launcher_log.py`.** Tolerant tail. Handles rotation, truncation, and the
non-JSON line format. Public API:

```python
wait_for(pattern, timeout, since_offset) -> Match | None
current_phase() -> str | None          # e.g. "update-files-inside-p4k"
last_completed(channel) -> BuildRef | None
```

Anchor on `[PatcherPhase] Starting delta update (SC {CHANNEL} {version})` and
`[PatcherPhase] Delta update completed (SC {CHANNEL} {version}) in {path}`, asserting
that `{path}` ends with the expected channel directory.

**A3. `acquire/launcher_ui.py`.**

```
start_launcher()        launch exe if not running; wait for main window;
                        absorb a launcher self-update if one triggers
                        (electron-updater may request elevation via
                        resources\elevate.exe -> UAC cannot be automated,
                        so detect, log and abort cleanly)
ensure_logged_in()      if a login view is present -> abort, log
select_channel(ch)      LIVE / PTU via the channel selector
read_button_state()     -> UPDATE | INSTALL | LAUNCH | RESUME | VERIFY | UNKNOWN
available(ch)           UPDATE or INSTALL -> a build is waiting
fetch(ch, target)       click, then follow the log to completion,
                        with stall detection
quit_launcher()         graceful close, then hard kill after grace period
```

**A4. `pipeline.py`.** Straight translation of the existing runbook:

```
cp -r output/<CH> output/_prev_<old buildVersion>
py -m nova --channel <CH> --force
py scripts/patch_diff.py output/_prev_<old> output/<CH> \
       reports/patch_diff_<old>_to_<new short>.html
append Game2.dcb sha256 to logs/dataforge_hashes.json
```

Packaging to `output/<CH>.zip` is automatic inside `nova` unless `--no-package`, so
there is no separate zip step. Success marker in nova's output is
`=== Done! Total time:`; failure markers are `Traceback`, `[ERROR]`, `MemoryError`.
Snapshot before extract is mandatory, because `--force` overwrites `output/<CH>` in
place and there is no diff without the old copy.

Add a retention sweep: `output/_prev_*` currently holds six snapshots and grows without
bound. Keep the last N (suggest 3) and delete the rest.

**A5. `__main__.py`.** Orchestration, guards, lock, kill switch, run log.

**A6. `install_task.ps1`.** Registers the scheduled task.

**Critical scheduling constraint:** the task must be
"Run only when the user is logged on". The "whether the user is logged on or not"
option runs in session 0 with no interactive desktop, and there is no UI to automate
there. Practical consequence: schedule it at night or on idle, with the desktop session
alive. `-WakeToRun` and "Start only if idle" are worth setting.

**A7. Dry-run validation.** Full pass with `dry_run: true` on a build that is already
current, then on a real pending patch, watching `logs/auto_update.log`.

### 3.3 Failure modes

| Mode | Frequency | Handling |
| --- | --- | --- |
| Session expired / 2FA challenge | Every few weeks. The main recurring failure. | Abort, log clearly. Human logs in once, next tick proceeds. Never attempt automated login. |
| Launcher self-update on start, with UAC | Occasional | Detect elevation prompt, abort, log. Human runs the launcher once manually. |
| PTU closed | Common between waves | Card missing or has no build. Skip channel silently. |
| UI restructured by a launcher release | A few times a year | Element not found means abort with the failing selector logged. Re-run A0, update selectors. |
| Patch stalls / CDN slow | Occasional | Stall timeout aborts. Next tick retries from scratch; the launcher resumes partial downloads on its own. |
| Disk full mid-patch | Rare | Pre-flight `min_free_gb` check. LIVE and PTU are 150 GB+ each, plus ~154 GB unpacked cache per channel. |
| Game running | User-dependent | Pre-flight process guard. |

### 3.4 Effort estimate

A0 probe half a day; A2 log tailer half a day; A3 UI driver 1 to 2 days, dominated by
selector discovery and timing; A4 pipeline half a day since the runbook already
specifies it; A5 to A7 one day. Roughly **3 to 4 days**, plus a few weeks of calendar
time to see it survive real patches on both channels.

---

## 4. Alternative B — direct launcher API / patcher CDN

**Gated on express written approval from RSI. Do not build any part of this before an
answer arrives, including exploratory requests against the endpoints.**

### 4.1 Approval request

Sent to `support@cloudimperiumgames.com`, copy to `legal_notices@cloudimperiumgames.com`
(both from ToS Section XXIII / XXII(A)). The request asks two things deliberately, so
that a no on the first still yields something usable:

1. Express approval for read-only `GET /api/launcher/v3/games/release`, own account
   only, capped at 4 requests per day from one machine, build-availability detection
   only, no game assets redistributed.
2. Failing that, confirmation on whether locally automating the official launcher's own
   UI is acceptable, given that all network traffic remains the launcher's.

Realistic expectation: CIG has no developer programme, no API terms and no partner
channel. First-line support has neither mandate nor template for this. Silence or a
canned "third-party tools are not supported" is the likely outcome. Asking costs
nothing, since it is a question asked in advance rather than a disclosure of anything
done.

**Log the outcome in section 7 of this document when it arrives.**

### 4.2 B1 — detection only (small, if approved)

`acquire/direct_api.py` implements `available()` against `games/release` and delegates
`fetch()` to the `launcher_ui` backend.

Honest assessment: this replaces a local file read with a network call and gains
essentially nothing. Local detection via `build_manifest.id` and the launcher log
already answers "is a new build installed", and the launcher log answers "is a new
build available" whenever the launcher has run. B1 exists only to know about a build
without starting the launcher at all. Perhaps half a day of work for a marginal gain.

### 4.3 B2 — full download (large, not recommended)

Requires reimplementing `CigDataPatcher`:

- authenticate and obtain a game token (`games/token`)
- fetch the remote file manifest for the target build
- diff against the local p4k contents (`open-p4k`, `retrieve-local-file-list`)
- download deltas
- apply them to the p4k structure and to files inside the container
  (`update-p4k-structure`, `update-files-inside-p4k`)
- update loose files, then write `build_manifest.id`

None of this is documented. All of it is reverse engineering of a proprietary
container-delta format, and a corrupted p4k means a full 154 GB redownload. Approval to
*connect* does not include the format specification, and CIG changes the format at
will, so every change breaks the implementation with no notice.

Cost: weeks, plus permanent maintenance. Benefit over Alternative A: the launcher
window never opens, and the scheduled task could run in session 0. That is not worth
it. **Recommendation: do not build B2 even if approval arrives.**

---

## 5. Degraded mode — acquisition disabled

Falls out of the architecture for free: set `"acquirer": "manual"`.

`manual.available()` compares the installed build against `cache/build_state.json` and
returns None if unchanged; `manual.fetch()` is a no-op that returns "not acquired".
The scheduled task then does nothing until a human clicks UPDATE in the launcher, and
the very next tick sees the changed `build_manifest.id` and runs the full pipeline
unattended.

This is the zero-amber-zone configuration. It keeps roughly 95% of the value, since the
30 seconds of clicking is dwarfed by the 25 to 50 minutes of extraction, packaging and
reporting that it automates. It is also the correct fallback if A0 shows the UIA tree
is unusable, and the correct posture while waiting for an answer from RSI.

Because it shares every other component, building A means building this on the way.

---

## 6. Build order

1. **A0 probe** and `docs/launcher_uia_tree.txt`. Decides whether A is viable at all.
2. `build_state.py`, `launcher_log.py`, `pipeline.py`, `acquire/manual.py`,
   `__main__.py`, `install_task.ps1`. This is section 5 working end to end, all green
   zone, and it is the foundation either way.
3. Run it against one real patch cycle in manual mode. Confirm the pipeline is correct
   before adding UI automation on top.
4. `acquire/launcher_ui.py`. Flip `"acquirer"` in config.
5. `acquire/direct_api.py` only if RSI approves, and only B1.

Steps 2 and 3 are worth doing regardless of the answers to any of the open questions
below.

---

## 7. Open questions and decision log

| Date | Item | Status |
| --- | --- | --- |
| 2026-08-07 | Does the launcher expose a usable UIA tree? | **Open.** Resolved by A0. |
| 2026-08-07 | Will RSI expressly approve read-only `games/release`? | **Open.** Draft written, not yet sent. |
| 2026-08-07 | Will RSI comment on local UI automation of their own client? | **Open.** Same request. |
| 2026-08-07 | Operating mode: full automation, log file only, no per-run confirmation | **Decided.** |
| 2026-08-07 | B2 (own patcher implementation) | **Rejected.** Reverse engineering cost and fragility outweigh any benefit, independent of approval. |
| 2026-08-07 | Session 0 / headless scheduling | **Rejected for A.** UI automation requires an interactive desktop. |

## 8. Related documents

- [`update_live_zip_runbook.md`](./update_live_zip_runbook.md) — the manual procedure
  this automates. `pipeline.py` must stay in sync with it.
- `nova/config.py` — `get_version_info()`, `get_launcher_patch()`, `is_cache_stale()`
  are all reusable here.
- `scripts/patch_diff.py` — report generator, called by `pipeline.py`.
