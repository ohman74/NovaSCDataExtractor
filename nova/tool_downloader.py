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


def _flatten_publish_layout(tools_dir):
    """v4.0.83+ ships a `publish/` subdirectory with the binaries inside.

    Move them to `tools_dir` root so the rest of the codebase can find
    them at the expected paths.
    """
    publish_dir = os.path.join(tools_dir, "publish")
    if not os.path.isdir(publish_dir):
        return
    import shutil
    for name in os.listdir(publish_dir):
        src = os.path.join(publish_dir, name)
        dst = os.path.join(tools_dir, name)
        if os.path.exists(dst):
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            else:
                os.remove(dst)
        shutil.move(src, dst)
    os.rmdir(publish_dir)


def _alias_unforge_cli(tools_dir):
    """v4.0.83+ ships `unforge.cli.exe` instead of `unforge.exe`.

    Copy it to `unforge.exe` so legacy callers keep working.
    """
    cli = os.path.join(tools_dir, "unforge.cli.exe")
    legacy = os.path.join(tools_dir, "unforge.exe")
    if os.path.isfile(cli) and not os.path.isfile(legacy):
        import shutil
        shutil.copy2(cli, legacy)


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

    # The suite contains both unp4k and unforge.
    download_and_extract(assets["unp4k"]["url"], tools_dir)

    # v4.0.83+ packs the binaries inside a `publish/` subdirectory and
    # renames `unforge.exe` to `unforge.cli.exe`. Normalise to the
    # legacy layout so the rest of the codebase keeps working.
    _flatten_publish_layout(tools_dir)
    _alias_unforge_cli(tools_dir)

    if not os.path.isfile(unp4k_exe) or not os.path.isfile(unforge_exe):
        print("[ERROR] Expected executables not found after extraction")
        return False

    print(f"[OK] Tools downloaded ({tag})")
    return True
