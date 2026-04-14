"""Download unp4k and unforge from GitHub releases."""

import io
import os
import zipfile

import requests

GITHUB_API_URL = "https://api.github.com/repos/dolkensp/unp4k/releases/latest"

REQUIRED_FILES = {
    "unp4k": "unp4k-suite",
    "unforge": "unforge",
}


def get_latest_release_assets():
    resp = requests.get(GITHUB_API_URL, timeout=30)
    resp.raise_for_status()
    release = resp.json()

    assets = {}
    for asset in release.get("assets", []):
        name = asset["name"]
        for key, prefix in REQUIRED_FILES.items():
            if name.startswith(prefix) and name.endswith(".zip"):
                assets[key] = {
                    "name": name,
                    "url": asset["browser_download_url"],
                    "size": asset["size"],
                }
    return release["tag_name"], assets


def download_and_extract(url, dest_dir):
    print(f"  Downloading {url}...")
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()

    content = io.BytesIO()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    for chunk in resp.iter_content(chunk_size=8192):
        content.write(chunk)
        downloaded += len(chunk)
        if total > 0:
            pct = downloaded * 100 // total
            print(f"\r  Progress: {pct}% ({downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB)", end="", flush=True)
    print()

    content.seek(0)
    with zipfile.ZipFile(content) as zf:
        zf.extractall(dest_dir)
    print(f"  Extracted to {dest_dir}")


def ensure_tools(tools_dir):
    unp4k_exe = os.path.join(tools_dir, "unp4k.exe")
    unforge_exe = os.path.join(tools_dir, "unforge.exe")

    if os.path.isfile(unp4k_exe) and os.path.isfile(unforge_exe):
        print("[OK] Tools already present")
        return True

    print("[SETUP] Downloading unp4k and unforge tools...")
    os.makedirs(tools_dir, exist_ok=True)

    tag, assets = get_latest_release_assets()
    print(f"  Latest release: {tag}")

    if "unp4k" not in assets:
        print("[ERROR] Could not find unp4k-suite download in release")
        return False

    # The suite contains both unp4k and unforge
    download_and_extract(assets["unp4k"]["url"], tools_dir)

    if not os.path.isfile(unp4k_exe) or not os.path.isfile(unforge_exe):
        print("[ERROR] Expected executables not found after extraction")
        return False

    print(f"[OK] Tools downloaded ({tag})")
    return True
