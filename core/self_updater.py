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
    progress_callback: Optional[Callable[[float], None]] = None,
    restart: bool = True
) -> None:
    """
    Downloads the new executable to a temporary file, sets up a detached replacement script,
    and terminates the current process so the replacement can execute cleanly on Windows.
    If restart is False (e.g. during headless startup), the binary is replaced without relaunching.
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
    start_cmd = f'start "" "{current_exe_path}"\n' if restart else ""
    batch_content = f"""@echo off
chcp 65001 >nul
ping 127.0.0.1 -n 2 >nul
:retry
move /y "{new_exe_path}" "{current_exe_path}" >nul 2>&1
if errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto retry
)
{start_cmd}del "%~f0"
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


def update_all_managed_instances(
    assets: Any,
    registry: Optional[Any] = None,
    progress_callback: Optional[Callable[[float], None]] = None
) -> Dict[str, Any]:
    """
    Downloads ManagedUpdater.exe (and/or SimpleUpdater.exe) from release assets or zip bundle
    and updates all registered updater binaries across managed project instances in ManagedRegistry.
    """
    import shutil
    import zipfile
    from core.config import ManagedRegistry, get_appdata_dir

    if registry is None:
        registry = ManagedRegistry()

    instances = registry.get_all_instances()
    if not instances:
        return {"updated_count": 0, "total": 0, "errors": []}

    cache_dir = os.path.join(get_appdata_dir(), "temp_update")
    os.makedirs(cache_dir, exist_ok=True)

    managed_asset = None
    simple_asset = None
    zip_asset = None

    for a in assets:
        name = a.get("name", "").lower()
        if name == "managedupdater.exe":
            managed_asset = a
        elif name == "simpleupdater.exe":
            simple_asset = a
        elif name.endswith(".zip"):
            if not zip_asset or "simple-updater" in name or "updraft" in name:
                zip_asset = a

    staged_managed = None
    staged_simple = None

    # 1. Try to download standalone .exe assets
    target_exe_asset = managed_asset or simple_asset
    if target_exe_asset and target_exe_asset.get("download_url"):
        download_url = target_exe_asset["download_url"]
        dest_name = target_exe_asset.get("name", "ManagedUpdater.exe")
        staged_binary = os.path.join(cache_dir, dest_name)

        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Updraft-SelfUpdater"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024
            with open(staged_binary, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(min(1.0, downloaded / total_size))

        if dest_name.lower() == "managedupdater.exe":
            staged_managed = staged_binary
        else:
            staged_simple = staged_binary

    # 2. If managed or simple binary not directly found, try to extract from zip asset
    if (not staged_managed or not staged_simple) and zip_asset and zip_asset.get("download_url"):
        zip_path = os.path.join(cache_dir, zip_asset.get("name", "bundle.zip"))
        req = urllib.request.Request(
            zip_asset["download_url"],
            headers={"User-Agent": "Updraft-SelfUpdater"}
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024
            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(min(1.0, downloaded / total_size))

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    m_lower = member.lower()
                    if m_lower.endswith("managedupdater.exe") and not staged_managed:
                        extracted = zf.extract(member, cache_dir)
                        staged_managed = extracted
                    elif m_lower.endswith("simpleupdater.exe") and not staged_simple:
                        extracted = zf.extract(member, cache_dir)
                        staged_simple = extracted
        except Exception as e:
            print(f"Warning: Failed to extract updaters from zip: {e}")

    default_staged = staged_managed or staged_simple
    if not default_staged:
        return {
            "updated_count": 0,
            "total": len(instances),
            "errors": ["No updater binary or zip asset found in release."],
        }

    if progress_callback:
        progress_callback(1.0)

    # Distribute to each registered project instance
    updated_count = 0
    errors = []
    for proj_dir, meta in instances.items():
        updater_path = meta.get("updater_path")
        if not updater_path:
            updater_path = os.path.join(proj_dir, "ManagedUpdater.exe")

        is_standalone = os.path.basename(updater_path).lower() == "simpleupdater.exe"
        chosen_binary = (staged_simple if is_standalone and staged_simple else None) or default_staged

        try:
            dest_dir = os.path.dirname(updater_path)
            if os.path.exists(dest_dir):
                shutil.copy2(chosen_binary, updater_path)
                updated_count += 1
        except Exception as e:
            errors.append(f"Failed to update {updater_path}: {e}")

    return {
        "updated_count": updated_count,
        "total": len(instances),
        "errors": errors,
        "staged_binary": default_staged,
    }


def check_and_update_project_updaters(
    registry: Optional[Any] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Checks for the latest release and updates all project updater executables
    across all registered project folders.
    If force is True, updates even if version tag matches current.
    """
    from core.config import ManagedRegistry
    if registry is None:
        registry = ManagedRegistry()

    instances = registry.get_all_instances()
    if not instances:
        return {
            "has_update": False,
            "updated_count": 0,
            "total": 0,
            "message": "No managed project instances found."
        }

    repo_info = GitRepoInfo(APP_REPO_OWNER, APP_REPO_NAME, APP_REPO_URL)
    client = GitHubClient(repo_info)
    try:
        rel = client.get_latest_release()
        if not rel:
            return {
                "has_update": False,
                "updated_count": 0,
                "total": len(instances),
                "error": "No releases found on GitHub."
            }

        remote_tag = rel.get("tag_name") or rel.get("name", "")
        has_update = is_newer_version(remote_tag, APP_VERSION)
        if not has_update and not force:
            return {
                "has_update": False,
                "latest_version": remote_tag or APP_VERSION,
                "current_version": APP_VERSION,
                "updated_count": 0,
                "total": len(instances)
            }

        assets = rel.get("assets", [])

        def _prog(pct):
            if progress_callback:
                progress_callback(pct, f"Downloading updater components... {int(pct * 100)}%")

        res = update_all_managed_instances(assets, registry=registry, progress_callback=_prog)
        res["has_update"] = has_update
        res["latest_version"] = remote_tag or APP_VERSION
        return res
    except Exception as e:
        return {
            "has_update": False,
            "updated_count": 0,
            "total": len(instances),
            "error": str(e)
        }


def get_managed_updater_template() -> Optional[str]:
    """
    Locates an available ManagedUpdater.exe binary to use as a deployment template.
    Searches next to the executable, in dist/, in AppData temp_update cache,
    or extracts from a local zip bundle if present.
    """
    candidates = []

    # 1. Next to current executable (frozen) or repo dist (unfrozen)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "ManagedUpdater.exe"))
        candidates.append(os.path.join(exe_dir, "dist", "ManagedUpdater.exe"))
    else:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(repo_root, "dist", "ManagedUpdater.exe"))
        candidates.append(os.path.join(repo_root, "ManagedUpdater.exe"))

    # 2. AppData cache
    from core.config import get_appdata_dir
    cache_dir = os.path.join(get_appdata_dir(), "temp_update")
    candidates.append(os.path.join(cache_dir, "ManagedUpdater.exe"))

    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 0:
            return os.path.abspath(c)

    # 3. Check for local zip bundle and extract ManagedUpdater.exe
    zip_candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        zip_candidates.append(os.path.join(exe_dir, "simple-updater-win.zip"))
        zip_candidates.append(os.path.join(exe_dir, "dist", "simple-updater-win.zip"))
    else:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        zip_candidates.append(os.path.join(repo_root, "dist", "simple-updater-win.zip"))
        zip_candidates.append(os.path.join(repo_root, "simple-updater-win.zip"))

    import zipfile
    for zp in zip_candidates:
        if os.path.isfile(zp):
            try:
                os.makedirs(cache_dir, exist_ok=True)
                with zipfile.ZipFile(zp, "r") as zf:
                    for member in zf.namelist():
                        if member.lower().endswith("managedupdater.exe"):
                            extracted = zf.extract(member, cache_dir)
                            if os.path.isfile(extracted) and os.path.getsize(extracted) > 0:
                                return os.path.abspath(extracted)
            except Exception as e:
                print(f"Warning: Failed to extract ManagedUpdater from {zp}: {e}")

    return None


def check_updater_conflict(target_folder: str, registry: Optional[Any] = None) -> tuple[bool, str]:
    """
    Checks if creating an updater in target_folder would result in a conflict.
    Returns (has_conflict: bool, reason: str).
    """
    if not target_folder or not target_folder.strip():
        return True, "No folder selected."

    norm_folder = os.path.normpath(os.path.abspath(target_folder.strip()))

    if not os.path.exists(norm_folder):
        return True, f"The selected folder does not exist:\n{norm_folder}"

    if not os.path.isdir(norm_folder):
        return True, f"The selected path is not a directory:\n{norm_folder}"

    # Check if target folder is Update Manager's own directory
    if getattr(sys, "frozen", False):
        mgr_dir = os.path.normpath(os.path.abspath(os.path.dirname(sys.executable)))
    else:
        mgr_dir = os.path.normpath(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

    if norm_folder.lower() == mgr_dir.lower():
        return True, "Cannot create an updater inside the Update Manager application directory."

    # Check for existing updater executables
    managed_exe = os.path.join(norm_folder, "ManagedUpdater.exe")
    if os.path.exists(managed_exe):
        return True, f"An updater already exists in this folder:\n'{managed_exe}'"

    simple_exe = os.path.join(norm_folder, "SimpleUpdater.exe")
    if os.path.exists(simple_exe):
        return True, f"An updater already exists in this folder:\n'{simple_exe}'"

    # Check for existing updater-info.ini
    ini_file = os.path.join(norm_folder, "updater-info.ini")
    if os.path.exists(ini_file):
        return True, f"A project configuration already exists in this folder:\n'{ini_file}'"

    # Check if already registered in ManagedRegistry
    if registry is None:
        from core.config import ManagedRegistry
        registry = ManagedRegistry()

    if registry.has_instance(norm_folder):
        return True, "This folder is already registered in Update Manager."

    return False, ""


