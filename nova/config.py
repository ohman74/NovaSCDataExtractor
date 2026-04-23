"""Configuration management for Nova extractor."""

import json
import os
import sys


class Config:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nova_config.json")

        with open(config_path, "r") as f:
            data = json.load(f)

        self.sc_live_path = os.path.normpath(data["sc_live_path"])

        base_dir = os.path.dirname(config_path)
        self.tools_dir = os.path.normpath(os.path.join(base_dir, data.get("tools_dir", "./tools")))
        self.cache_dir = os.path.normpath(os.path.join(base_dir, data.get("cache_dir", "./cache")))
        self.output_dir = os.path.normpath(os.path.join(base_dir, data.get("output_dir", "./output")))

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

    def get_game_version(self):
        return self.get_version_info().get("branch", "unknown")

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
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
