import os
import sys
import re
import time
import subprocess
import urllib.request
from typing import Dict, Any, Optional, Callable

from core.version import APP_NAME, APP_VERSION, APP_REPO_OWNER, APP_REPO_NAME, APP_REPO_URL
from core.git_client import GitHubClient, GitRepoInfo


def parse_version_tuple(v_str: str):
    """
    Parses a version tag like 'v1.2.3' or '1.0' into a comparable tuple of integers.
    """
    clean = re.sub(r'^[vV]', '', v_str.strip())
    # Extract digit sequences
    parts = []
    for seg in clean.split('.'):
        digits = re.findall(r'\d+', seg)
        if digits:
            parts.append(int(digits[0]))
        else:
            parts.append(0)
    return tuple(parts)


def is_newer_version(remote_tag: str, current_tag: str) -> bool:
    """
    Returns True if remote_tag is strictly newer than current_tag.
    """
    if not remote_tag:
        return False
    if not current_tag or current_tag.lower() == "unknown":
        return True

    try:
        t_remote = parse_version_tuple(remote_tag)
        t_current = parse_version_tuple(current_tag)
        return t_remote > t_current
    except Exception:
        return remote_tag != current_tag


def check_app_update(target_binary_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Checks GitHub releases for the latest version of Updraft.
    """
    repo_info = GitRepoInfo(APP_REPO_OWNER, APP_REPO_NAME, APP_REPO_URL)
    client = GitHubClient(repo_info)

    try:
        rel = client.get_latest_release()
        if not rel:
            return {"has_update": False, "latest_version": APP_VERSION, "error": "No releases found"}

        remote_tag = rel.get("tag_name") or rel.get("name", "")
        published_at = rel.get("published_at", "")
        body = rel.get("body", "")
        assets = rel.get("assets", [])

        if not is_newer_version(remote_tag, APP_VERSION):
            return {
                "has_update": False,
                "latest_version": remote_tag or APP_VERSION,
                "current_version": APP_VERSION,
                "published_at": published_at,
            }

        # Locate matching binary asset if target_binary_name is given
        matched_asset = None
        if target_binary_name:
            target_lower = target_binary_name.lower()
            for a in assets:
                if a.get("name", "").lower() == target_lower:
                    matched_asset = a
                    break

        # Fallback to any .exe asset if exact match not found
        if not matched_asset and assets:
            for a in assets:
                if a.get("name", "").lower().endswith(".exe"):
                    matched_asset = a
                    break

        return {
            "has_update": True,
            "latest_version": remote_tag,
            "current_version": APP_VERSION,
            "published_at": published_at,
            "body": body,
            "asset_url": matched_asset.get("download_url") if matched_asset else None,
            "asset_name": matched_asset.get("name") if matched_asset else None,
            "asset_size": matched_asset.get("size", 0) if matched_asset else 0,
            "all_assets": assets,
        }
    except Exception as e:
        return {"has_update": False, "latest_version": APP_VERSION, "error": str(e)}


def perform_app_self_update(
    download_url: str,
    current_exe_path: str,
    progress_callback: Optional[Callable[[float], None]] = None
) -> None:
    """
    Downloads the new executable to a temporary file, sets up a detached replacement script,
    and terminates the current process so the replacement can execute cleanly on Windows.
    """
    current_exe_path = os.path.abspath(current_exe_path)
    new_exe_path = current_exe_path + ".new"

    # Download new file
    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": "Updraft-SelfUpdater"}
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 64 * 1024

        with open(new_exe_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total_size > 0:
                    progress_callback(min(1.0, downloaded / total_size))

    if progress_callback:
        progress_callback(1.0)

    # If running from source (development), don't replace python.exe
    if not getattr(sys, "frozen", False):
        print(f"Downloaded new version to {new_exe_path}. (Running in dev mode, skipping binary overwrite).")
        return

    # Create detached replacement batch script
    batch_script_path = os.path.join(os.path.dirname(current_exe_path), "updraft-replace.bat")
    batch_content = f"""@echo off
chcp 65001 >nul
ping 127.0.0.1 -n 2 >nul
:retry
move /y "{new_exe_path}" "{current_exe_path}" >nul 2>&1
if errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto retry
)
start "" "{current_exe_path}"
del "%~f0"
"""
    with open(batch_script_path, "w", encoding="utf-8") as f:
        f.write(batch_content)

    # Launch detached script and exit immediately to release file lock
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS

    subprocess.Popen(
        f'cmd.exe /c "{batch_script_path}"',
        shell=True,
        creationflags=flags,
        cwd=os.path.dirname(current_exe_path)
    )

    # Terminate old instance
    os._exit(0)
