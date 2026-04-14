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
        manifest_path = os.path.join(self.sc_live_path, "build_manifest.id")
        if os.path.isfile(manifest_path):
            with open(manifest_path, "r") as f:
                content = f.read().strip()
            for line in content.splitlines():
                if '"RequestedP4kVersion"' in line:
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[3]
                if '"Branch"' in line:
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[3]
        return "unknown"

    def ensure_dirs(self):
        os.makedirs(self.tools_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
