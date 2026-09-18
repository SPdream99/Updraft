import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from typing import Callable, List, Optional, Tuple, Dict
from core.config import UpdaterConfig
from core.git_client import USER_AGENT, GitHubClient, GitRepoInfo


def is_archive(filename: str) -> bool:
    lower = filename.lower()
    return lower.endswith(".zip") or lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar")


EXECUTABLE_EXTENSIONS = {
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


def is_executable(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in EXECUTABLE_EXTENSIONS


def create_windows_shortcut(target_path: str, shortcut_path: str, working_dir: Optional[str] = None):
    """
    Creates a Windows .lnk shortcut using WScript.Shell via PowerShell.
    Special handling for .ps1 scripts ensures they execute with PowerShell rather than opening in a text editor.
    """
    if sys.platform != "win32":
        return
    if working_dir is None:
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

    def create_shortcuts(self):
        """
        Creates Windows shortcuts (.lnk) in the project directory for any
        executables or scripts (.exe, .bat, .cmd, .ps1, .vbs, etc.) found inside main/.
        """
        if not os.path.exists(self.main_dir):
            return

        for root, _, files in os.walk(self.main_dir):
            for file in files:
                if is_executable(file):
                    target_file = os.path.join(root, file)
                    base_name, ext = os.path.splitext(file)
                    shortcut_name = f"{base_name}.lnk"
                    shortcut_path = os.path.join(self.project_dir, shortcut_name)

                    # If multiple files share the same base name, prevent overwrite by appending extension
                    if os.path.exists(shortcut_path):
                        shortcut_name = f"{base_name} ({ext.lstrip('.')}).lnk"
                        shortcut_path = os.path.join(self.project_dir, shortcut_name)

                    create_windows_shortcut(target_file, shortcut_path, working_dir=os.path.dirname(target_file))

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
