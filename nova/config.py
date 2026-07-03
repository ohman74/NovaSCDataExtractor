"""Configuration management for Nova extractor."""

import json
import os
import re
import sys


class Config:
    def __init__(self, config_path=None, channel_override=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nova_config.json")

        with open(config_path, "r") as f:
            data = json.load(f)

        configured_path = os.path.normpath(data["sc_live_path"])
        if channel_override:
            self.sc_live_path = os.path.join(
                os.path.dirname(configured_path), channel_override
            )
        else:
            self.sc_live_path = configured_path

        # Channel name = SC install dir basename (e.g. "Live", "PTU", "EPTU").
        # Used to scope cache + output to per-channel subdirectories so a
        # Live run and a PTU run don't trample each other.
        self.channel = os.path.basename(self.sc_live_path)

        base_dir = os.path.dirname(config_path)
        self.tools_dir = os.path.normpath(os.path.join(base_dir, data.get("tools_dir", "./tools")))

        # Roots are the un-channelled locations. Per-channel subdirs hang
        # off these. cache_dir / output_dir always point at the active
        # channel's subdir so existing builders Just Work.
        self.cache_root = os.path.normpath(os.path.join(base_dir, data.get("cache_dir", "./cache")))
        self.output_root = os.path.normpath(os.path.join(base_dir, data.get("output_dir", "./output")))
        self.cache_dir = os.path.join(self.cache_root, self.channel)
        self.output_dir = os.path.join(self.output_root, self.channel)

        self.p4k_path = os.path.join(self.sc_live_path, "Data.p4k")
        self.unp4k_path = os.path.join(self.tools_dir, "unp4k.exe")
        self.unforge_path = os.path.join(self.tools_dir, "unforge.exe")

    def validate(self):
        errors = []
        if not os.path.isfile(self.p4k_path):
            errors.append(f"Data.p4k not found at: {self.p4k_path}")
        if not os.path.isfile(self.unp4k_path):
            errors.append(f"unp4k.exe not found at: {self.unp4k_path}")
        if not os.path.isfile(self.unforge_path):
            errors.append(f"unforge.exe not found at: {self.unforge_path}")
        return errors

    def get_version_info(self):
        """Full build manifest snapshot: branch, build version, p4 change, build date.

        Branch alone (e.g. "sc-alpha-4.7.0") is ambiguous — PTU and Live often share
        the same branch string while pointing at completely different p4 changelists.
        The "Version" field (e.g. "4.7.178.8917") is the unambiguous build identifier.
        """
        info = {"branch": "unknown", "version": None, "p4_change": None, "build_date": None}
        manifest_path = os.path.join(self.sc_live_path, "build_manifest.id")
        if not os.path.isfile(manifest_path):
            return info
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f).get("Data", {})
            info["branch"] = manifest.get("Branch") or info["branch"]
            info["version"] = manifest.get("Version") or None
            info["p4_change"] = manifest.get("RequestedP4ChangeNum") or None
            info["build_date"] = manifest.get("BuildDateStamp") or None
        except (json.JSONDecodeError, OSError):
            pass
        return info

    def get_launcher_patch(self):
        """Look up the public patch version (e.g. "4.7.2") for this channel
        from the RSI launcher log.

        The build_manifest's `Branch` field stays at the major patch series
        (e.g. "sc-alpha-4.7.0") across every 4.7.x patch, so it can't tell
        us whether we're on 4.7.0, 4.7.1, or 4.7.2. The launcher logs every
        install/update with the marketing patch version
        (`4.7.2-live.11715810`); we cross-reference the current build's
        p4 changelist to find the matching entry.

        Returns the patch string ("4.7.2") or None if the launcher log
        isn't available, the channel doesn't match, or the changelist
        isn't in the log.
        """
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        log_path = os.path.join(appdata, "rsilauncher", "logs", "log.log")
        if not os.path.isfile(log_path):
            return None
        info = self.get_version_info()
        p4 = info.get("p4_change")
        if not p4:
            return None
        pattern = re.compile(
            r"\bSC\s+" + re.escape(self.channel.upper())
            + r"\s+(\d+\.\d+\.\d+)-"
            + re.escape(self.channel.lower())
            + r"\." + re.escape(p4) + r"\b"
        )
        last_match = None
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = pattern.search(line)
                    if m:
                        last_match = m.group(1)
        except OSError:
            return None
        return last_match

    def is_cache_stale(self):
        """Check whether the cached Game2.xml is older than the live Data.p4k.

        Returns a dict with `stale` (bool), `cache_mtime`, `p4k_mtime`. When
        `stale=True` the cache was extracted from a different p4k than the
        one currently on disk and should be invalidated with --force.
        """
        cache_xml = os.path.join(self.cache_dir, "Data", "Game2.xml")
        result = {"stale": False, "cache_mtime": None, "p4k_mtime": None}
        if not os.path.isfile(cache_xml) or not os.path.isfile(self.p4k_path):
            return result
        result["cache_mtime"] = os.path.getmtime(cache_xml)
        result["p4k_mtime"] = os.path.getmtime(self.p4k_path)
        result["stale"] = result["cache_mtime"] < result["p4k_mtime"]
        return result

    def ensure_dirs(self):
        os.makedirs(self.tools_dir, exist_ok=True)
        os.makedirs(self.cache_root, exist_ok=True)
        os.makedirs(self.output_root, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
