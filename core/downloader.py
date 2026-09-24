import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from typing import Callable, List, Optional, Tuple, Dict, Any
from core.config import UpdaterConfig, DEFAULT_SHORTCUT_EXCLUDED_DIRS
from core.git_client import USER_AGENT, GitHubClient, GitRepoInfo


def is_archive(filename: str) -> bool:
    lower = filename.lower()
    return lower.endswith(".zip") or lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar")


BINARY_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".vbs",
    ".vbe",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".msc",
}

PYTHON_EXTENSIONS = {
    ".py",
    ".pyw",
}

DOC_EXTENSIONS = {
    ".html",
    ".htm",
    ".url",
}

EXECUTABLE_EXTENSIONS = BINARY_EXTENSIONS | PYTHON_EXTENSIONS | DOC_EXTENSIONS


def is_executable(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in EXECUTABLE_EXTENSIONS


def create_python_bat_launcher(target_py_path: str, bat_path: str, rel_dir: Optional[str] = None):
    """
    Creates a .bat launcher in the project root to run a Python script (.py/.pyw) with Python.
    """
    py_filename = os.path.basename(target_py_path)
    if rel_dir and rel_dir != ".":
        win_rel_dir = rel_dir.replace("/", "\\")
        cd_line = f'cd /d "%~dp0{win_rel_dir}"'
    else:
        cd_line = 'cd /d "%~dp0"'

    bat_content = f"""@echo off
chcp 65001 >nul
{cd_line}
where python >nul 2>nul
if %errorlevel% equ 0 (
    python "{py_filename}" %*
) else (
    py "{py_filename}" %*
)
if errorlevel 1 pause
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except Exception as e:
        print(f"Warning: Failed to create python bat launcher for {target_py_path}: {e}")


def create_windows_shortcut(target_path: str, shortcut_path: str, working_dir: Optional[str] = None):
    """
    Creates a Windows .lnk shortcut using WScript.Shell via PowerShell.
    Special handling for .ps1 scripts ensures they execute with PowerShell rather than opening in a text editor.
    Folders are linked natively to open in Windows Explorer.
    """
    if sys.platform != "win32":
        return
    if working_dir is None:
        if os.path.isdir(target_path):
            working_dir = target_path
        else:
            working_dir = os.path.dirname(target_path)
    
    target_path = os.path.abspath(target_path)
    shortcut_path = os.path.abspath(shortcut_path)
    working_dir = os.path.abspath(working_dir)

    ext = os.path.splitext(target_path)[1].lower()
    if ext == ".ps1":
        target_exe = "powershell.exe"
        arguments = f'-NoProfile -ExecutionPolicy Bypass -File "{target_path}"'
    else:
        target_exe = target_path
        arguments = ""

    target_exe_esc = target_exe.replace("'", "''")
    shortcut_path_esc = shortcut_path.replace("'", "''")
    working_dir_esc = working_dir.replace("'", "''")
    arguments_esc = arguments.replace("'", "''")

    ps_script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{shortcut_path_esc}'); "
        f"$s.TargetPath = '{target_exe_esc}'; "
        f"$s.Arguments = '{arguments_esc}'; "
        f"$s.WorkingDirectory = '{working_dir_esc}'; "
        f"$s.Save();"
    )

    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            creationflags=flags,
            check=False,
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Failed to create shortcut for {target_path}: {e}")


def discover_project_shortcuts(
    project_dir: str,
    config: Optional[UpdaterConfig] = None
) -> List[Dict[str, Any]]:
    """
    Scans the project's main/ folder for shortcut candidates:
    - Executables (.exe, .bat, .cmd, .ps1, etc.)
    - Python scripts (.py, .pyw)
    - Web links and documents (.html, .htm, .url)
    - Subfolders up to configured level (if enabled)

    Applies per-project rules and customization settings from config:
    - shortcut_folder_level
    - create_folder_shortcuts
    - shortcut_include_executables
    - shortcut_include_python
    - shortcut_include_docs
    - shortcut_prefix
    - [ShortcutRules] overrides in updater-info.ini
    """
    project_dir = os.path.abspath(project_dir)
    main_dir = os.path.join(project_dir, "main")
    if not os.path.exists(main_dir):
        return []

    if config is None:
        config = UpdaterConfig(project_dir)

    max_depth = getattr(config, "shortcut_folder_level", 1)
    allow_folders = getattr(config, "create_folder_shortcuts", True)
    inc_executables = getattr(config, "shortcut_include_executables", True)
    inc_python = getattr(config, "shortcut_include_python", True)
    inc_docs = getattr(config, "shortcut_include_docs", True)
    prefix = getattr(config, "shortcut_prefix", "").strip()
    rules = config.get_shortcut_rules()

    candidates: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(main_dir):
        # Exclude hidden directories, python cache, and noise directories
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d.lower() not in DEFAULT_SHORTCUT_EXCLUDED_DIRS
        ]

        rel = os.path.relpath(root, main_dir)
        if rel == ".":
            current_level = 0
        else:
            current_level = len(rel.replace("\\", "/").split("/"))

        # Discover subdirectories as folder shortcut candidates
        if allow_folders:
            for d in list(dirs):
                folder_level = current_level + 1
                if max_depth >= 0 and folder_level > max_depth:
                    continue
                folder_full_path = os.path.join(root, d)
                folder_rel_path = os.path.relpath(folder_full_path, project_dir).replace("\\", "/")
                rule = rules.get(folder_rel_path, {})
                custom_name = rule.get("custom_name", "")
                enabled = rule.get("enabled", True) if "enabled" in rule else True

                base_name = d
                if custom_name:
                    display_name = custom_name
                elif prefix:
                    sep = "" if prefix[-1] in (" ", "-", "_") else " "
                    display_name = f"{prefix}{sep}{base_name}"
                else:
                    display_name = base_name

                candidates.append({
                    "target_path": folder_full_path,
                    "rel_path": folder_rel_path,
                    "type": "folder",
                    "base_name": base_name,
                    "custom_name": custom_name,
                    "effective_name": display_name,
                    "output_filename": f"{display_name}.lnk",
                    "enabled": enabled,
                    "level": folder_level,
                })

        # Stop descending deeper if max_depth reached
        if max_depth >= 0 and current_level >= max_depth:
            dirs.clear()

        # Skip files if beyond max_depth
        if max_depth >= 0 and current_level > max_depth:
            continue

        for file in sorted(files):
            if file.startswith("__") or file.startswith("."):
                continue

            full_path = os.path.join(root, file)
            base_name, ext = os.path.splitext(file)
            ext_lower = ext.lower()

            item_type = None
            cat_default_enabled = True

            if ext_lower in PYTHON_EXTENSIONS:
                item_type = "python"
                cat_default_enabled = inc_python
            elif ext_lower in BINARY_EXTENSIONS:
                item_type = "binary"
                cat_default_enabled = inc_executables
            elif ext_lower in DOC_EXTENSIONS:
                item_type = "doc"
                cat_default_enabled = inc_docs

            if not item_type:
                continue

            rel_path = os.path.relpath(full_path, project_dir).replace("\\", "/")
            rule = rules.get(rel_path, {})
            custom_name = rule.get("custom_name", "")
            enabled = rule.get("enabled", cat_default_enabled) if "enabled" in rule else cat_default_enabled

            if custom_name:
                display_name = custom_name
            elif prefix:
                sep = "" if prefix[-1] in (" ", "-", "_") else " "
                display_name = f"{prefix}{sep}{base_name}"
            else:
                display_name = base_name

            out_ext = ".bat" if item_type == "python" else ".lnk"
            candidates.append({
                "target_path": full_path,
                "rel_path": rel_path,
                "type": item_type,
                "base_name": base_name,
                "custom_name": custom_name,
                "effective_name": display_name,
                "output_filename": f"{display_name}{out_ext}",
                "enabled": enabled,
                "level": current_level,
            })

    return candidates


class UpdateEngine:
    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.update_files_dir = os.path.join(self.project_dir, "update-files")
        self.main_dir = os.path.join(self.project_dir, "main")
        self.config = UpdaterConfig(self.project_dir)

    def prepare_directories(self):
        os.makedirs(self.update_files_dir, exist_ok=True)
        os.makedirs(self.main_dir, exist_ok=True)

    def download_file(
        self,
        url: str,
        dest_filename: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """
        Downloads a file from url to update-files/dest_filename with progress.
        """
        self.prepare_directories()
        dest_path = os.path.join(self.update_files_dir, dest_filename)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out_file:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            block_size = 64 * 1024  # 64 KB chunks

            while True:
                chunk = resp.read(block_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size, dest_filename)

        return dest_path

    def extract_archive(self, archive_path: str, extract_to_dir: str):
        """
        Extracts archive (zip or tar) into extract_to_dir.
        If the archive contains a single top-level directory (e.g. GitHub repo-sha/),
        it extracts the contents directly without nesting.
        """
        temp_extract_dir = os.path.join(self.update_files_dir, "_unpacked_temp")
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        os.makedirs(temp_extract_dir, exist_ok=True)

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(temp_extract_dir)
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as tf:
                tf.extractall(temp_extract_dir)
        else:
            raise ValueError(f"Unknown archive format: {archive_path}")

        # Check if there is only a single top-level directory inside
        items = os.listdir(temp_extract_dir)
        source_dir = temp_extract_dir
        if len(items) == 1:
            single_item = os.path.join(temp_extract_dir, items[0])
            if os.path.isdir(single_item):
                source_dir = single_item

        return source_dir, temp_extract_dir

    def install_or_update(
        self,
        downloaded_files: List[str],
        is_update: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[str]:
        """
        Processes downloaded files in update-files/:
        - Unpacks archives and moves files to main/, skipping excluded files if is_update is True.
        - Moves executable/standalone files to main/, respecting exclusions.
        - Deletes compressed archives if delete_compressed is True.
        - Cleans up temporary files in update-files/.
        - Creates shortcuts in project_dir for all executables/bats in main/.
        """
        self.prepare_directories()
        self.config.load()
        excluded_files = self.config.get_excluded_files() if is_update else {}
        installed_items = []

        for fpath in downloaded_files:
            fname = os.path.basename(fpath)
            if progress_callback:
                progress_callback(f"Processing {fname}...")

            if is_archive(fname):
                source_dir, temp_wrapper = self.extract_archive(fpath, self.main_dir)
                
                # Copy files recursively to main/ respecting exclusions
                for root, dirs, files in os.walk(source_dir):
                    rel_dir = os.path.relpath(root, source_dir)
                    target_dir = self.main_dir if rel_dir == "." else os.path.join(self.main_dir, rel_dir)
                    os.makedirs(target_dir, exist_ok=True)

                    for file in files:
                        src_file = os.path.join(root, file)
                        rel_file = file if rel_dir == "." else os.path.join(rel_dir, file)
                        rel_file_norm = rel_file.replace("\\", "/").strip()
                        target_file = os.path.join(target_dir, file)

                        if is_update and rel_file_norm in excluded_files:
                            if progress_callback:
                                progress_callback(f"Skipping excluded file: {rel_file_norm}")
                            continue

                        shutil.copy2(src_file, target_file)
                        installed_items.append(rel_file_norm)

                # Clean up temporary unpack directory
                shutil.rmtree(temp_wrapper, ignore_errors=True)

                # Delete compressed file if setting enabled
                if self.config.delete_compressed:
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
            else:
                # Standalone file (exe, bat, script, doc, etc.)
                rel_file_norm = fname.replace("\\", "/").strip()
                target_file = os.path.join(self.main_dir, fname)

                if is_update and rel_file_norm in excluded_files:
                    if progress_callback:
                        progress_callback(f"Skipping excluded file: {rel_file_norm}")
                else:
                    shutil.copy2(fpath, target_file)
                    installed_items.append(rel_file_norm)

                # Remove original from update-files
                try:
                    os.remove(fpath)
                except OSError:
                    pass

        # Clean any remaining unused files in update-files
        self.cleanup_update_files()

        # Create Windows shortcuts for executables and scripts in main/
        self.create_shortcuts()

        # If open_when_done is enabled, launch explorer on main/
        if self.config.open_when_done:
            self.open_main_folder()

        return installed_items

    def cleanup_update_files(self):
        """Removes all unused/residual files in update-files/."""
        if not os.path.exists(self.update_files_dir):
            return
        for item in os.listdir(self.update_files_dir):
            p = os.path.join(self.update_files_dir, item)
            try:
                if os.path.isfile(p) or os.path.islink(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass

    def create_shortcuts(self) -> List[str]:
        """
        Creates Windows shortcuts (.lnk) or .bat launchers in the project directory
        or dedicated Shortcuts folder for discovered items.
        Respects self.config.create_shortcuts, layout, prefix, and per-project rules.
        """
        self.config.load()
        if not getattr(self.config, "create_shortcuts", True):
            return []

        candidates = discover_project_shortcuts(self.project_dir, self.config)
        if not candidates:
            return []

        layout = getattr(self.config, "shortcut_layout", "root")
        if layout == "shortcuts_folder":
            dest_dir = os.path.join(self.project_dir, "Shortcuts")
            os.makedirs(dest_dir, exist_ok=True)
        else:
            dest_dir = self.project_dir

        created = []
        used_names = set()

        for item in candidates:
            if not item["enabled"]:
                continue

            target_path = item["target_path"]
            item_type = item["type"]

            # Handle duplicate file names in destination
            candidate_name = item["output_filename"]
            out_base, out_ext = os.path.splitext(candidate_name)
            counter = 2
            while candidate_name in used_names:
                candidate_name = f"{out_base} ({counter}){out_ext}"
                counter += 1
            used_names.add(candidate_name)

            dest_file_path = os.path.join(dest_dir, candidate_name)

            if item_type == "python":
                rel_dir = os.path.relpath(os.path.dirname(target_path), dest_dir)
                create_python_bat_launcher(target_path, dest_file_path, rel_dir)
                created.append(dest_file_path)
            else:
                create_windows_shortcut(target_path, dest_file_path)
                created.append(dest_file_path)

        return created

    def open_main_folder(self):
        """Opens the main folder in Windows Explorer."""
        if os.path.exists(self.main_dir):
            try:
                os.startfile(self.main_dir)
            except Exception as e:
                print(f"Failed to open main folder: {e}")

    def update_single_excluded_file(
        self,
        rel_file_norm: str,
        git_client: GitHubClient,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Updates an individual excluded file to the latest project version.
        Downloads the source/asset archive or queries GitHub, extracts just that file,
        places it in main/, and updates its entry in updater-info.ini.
        """
        self.prepare_directories()
        target_file = os.path.join(self.main_dir, os.path.normpath(rel_file_norm))
        rel_file_norm = rel_file_norm.replace("\\", "/").strip()

        if progress_callback:
            progress_callback(f"Fetching {rel_file_norm}...")

        updated = False

        if self.config.update_type == "source":
            # Fetch latest commit archive, unpack only the target file
            commit_info = git_client.get_latest_commit()
            archive_path = self.download_file(commit_info["zip_url"], "temp_source.zip")
            
            source_dir, temp_wrapper = self.extract_archive(archive_path, self.main_dir)
            source_file = os.path.join(source_dir, os.path.normpath(rel_file_norm))
            
            if os.path.exists(source_file):
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                shutil.copy2(source_file, target_file)
                updated = True

            shutil.rmtree(temp_wrapper, ignore_errors=True)
            if os.path.exists(archive_path):
                os.remove(archive_path)

        else:
            # Release update type: check selected assets
            release_info = git_client.get_latest_release()
            if not release_info:
                return False

            assets = release_info.get("assets", [])
            selected_asset_names = self.config.selected_assets

            for asset in assets:
                asset_name = asset["name"]
                if selected_asset_names and asset_name not in selected_asset_names:
                    continue

                if is_archive(asset_name):
                    archive_path = self.download_file(asset["download_url"], asset_name)
                    source_dir, temp_wrapper = self.extract_archive(archive_path, self.main_dir)
                    source_file = os.path.join(source_dir, os.path.normpath(rel_file_norm))
                    
                    if os.path.exists(source_file):
                        os.makedirs(os.path.dirname(target_file), exist_ok=True)
                        shutil.copy2(source_file, target_file)
                        updated = True

                    shutil.rmtree(temp_wrapper, ignore_errors=True)
                    if os.path.exists(archive_path):
                        os.remove(archive_path)
                    if updated:
                        break
                elif asset_name == os.path.basename(rel_file_norm):
                    # Standalone asset matches file
                    downloaded_path = self.download_file(asset["download_url"], asset_name)
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    shutil.copy2(downloaded_path, target_file)
                    os.remove(downloaded_path)
                    updated = True
                    break

        if updated:
            # Update the recorded version for this excluded file to match project version
            self.config.set_excluded_file(
                rel_file_norm,
                self.config.version_name,
                self.config.version_date
            )
            self.config.save()
            if progress_callback:
                progress_callback(f"Successfully updated {rel_file_norm} to {self.config.version_name}")

        self.cleanup_update_files()
        return updated
