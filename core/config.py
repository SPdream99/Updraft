import configparser
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List

CONFIG_FILENAME = "updater-info.ini"
DONE_BAT_FILENAME = "update-done.bat"
APPDATA_DIR_NAME = "SimpleUpdater"
MANAGED_REGISTRY_FILENAME = "managed_instances.json"


def get_appdata_dir() -> str:
    """Get the SimpleUpdater AppData directory path (%APPDATA%/SimpleUpdater)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")
    target_dir = os.path.join(appdata, APPDATA_DIR_NAME)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def get_managed_registry_path() -> str:
    """Get the path to managed_instances.json in AppData."""
    return os.path.join(get_appdata_dir(), MANAGED_REGISTRY_FILENAME)


class UpdaterConfig:
    """
    Manages reading and writing updater-info.ini for a project.
    """
    def __init__(self, directory: str):
        self.directory = os.path.abspath(directory)
        self.ini_path = os.path.join(self.directory, CONFIG_FILENAME)
        self.config = configparser.ConfigParser()
        self.load()

    def exists(self) -> bool:
        return os.path.exists(self.ini_path)

    def load(self):
        if self.exists():
            self.config.read(self.ini_path, encoding="utf-8")
        else:
            self._init_defaults()

    def _init_defaults(self):
        self.config["Project"] = {
            "project_name": "",
            "git_url": "",
            "update_type": "release",  # 'release' or 'source'
            "version_name": "",
            "version_date": "",
            "selected_assets": "",      # comma-separated asset names
        }
        self.config["Settings"] = {
            "open_when_done": "true",
            "delete_compressed": "true",
            "run_script_after_update": "false",
            "auto_update_on_startup": "true",
        }
        self.config["ExcludedFiles"] = {}

    def ensure_done_script(self):
        """Creates update-done.bat in project folder if it does not already exist."""
        bat_path = os.path.join(self.directory, DONE_BAT_FILENAME)
        if not os.path.exists(bat_path):
            try:
                with open(bat_path, "w", encoding="utf-8") as f:
                    pass  # blank file as requested
            except Exception as e:
                print(f"Warning: Could not create {DONE_BAT_FILENAME}: {e}")

    def save(self):
        self.ensure_done_script()
        with open(self.ini_path, "w", encoding="utf-8") as f:
            self.config.write(f)

    # --- Project Properties ---
    @property
    def project_name(self) -> str:
        return self.config.get("Project", "project_name", fallback="")

    @project_name.setter
    def project_name(self, value: str):
        self.config.set("Project", "project_name", value)

    @property
    def git_url(self) -> str:
        return self.config.get("Project", "git_url", fallback="")

    @git_url.setter
    def git_url(self, value: str):
        self.config.set("Project", "git_url", value)

    @property
    def update_type(self) -> str:
        return self.config.get("Project", "update_type", fallback="release")

    @update_type.setter
    def update_type(self, value: str):
        self.config.set("Project", "update_type", value)

    @property
    def version_name(self) -> str:
        return self.config.get("Project", "version_name", fallback="")

    @version_name.setter
    def version_name(self, value: str):
        self.config.set("Project", "version_name", value)

    @property
    def version_date(self) -> str:
        return self.config.get("Project", "version_date", fallback="")

    @version_date.setter
    def version_date(self, value: str):
        self.config.set("Project", "version_date", value)

    @property
    def selected_assets(self) -> List[str]:
        raw = self.config.get("Project", "selected_assets", fallback="")
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @selected_assets.setter
    def selected_assets(self, assets: List[str]):
        self.config.set("Project", "selected_assets", ", ".join(assets))

    # --- Settings Properties ---
    @property
    def open_when_done(self) -> bool:
        return self.config.getboolean("Settings", "open_when_done", fallback=True)

    @open_when_done.setter
    def open_when_done(self, value: bool):
        self.config.set("Settings", "open_when_done", "true" if value else "false")

    @property
    def delete_compressed(self) -> bool:
        return self.config.getboolean("Settings", "delete_compressed", fallback=True)

    @delete_compressed.setter
    def delete_compressed(self, value: bool):
        self.config.set("Settings", "delete_compressed", "true" if value else "false")

    @property
    def run_script_after_update(self) -> bool:
        return self.config.getboolean("Settings", "run_script_after_update", fallback=False)

    @run_script_after_update.setter
    def run_script_after_update(self, value: bool):
        self.config.set("Settings", "run_script_after_update", "true" if value else "false")

    @property
    def auto_update_on_startup(self) -> bool:
        return self.config.getboolean("Settings", "auto_update_on_startup", fallback=True)

    @auto_update_on_startup.setter
    def auto_update_on_startup(self, value: bool):
        self.config.set("Settings", "auto_update_on_startup", "true" if value else "false")

    # --- Excluded Files ---
    def get_excluded_files(self) -> Dict[str, Dict[str, str]]:
        """
        Returns a dict mapping normalized relative file path (forward slashes)
        to {'version_name': str, 'version_date': str}.
        """
        if "ExcludedFiles" not in self.config:
            return {}
        result = {}
        for rel_path, val in self.config["ExcludedFiles"].items():
            norm_path = rel_path.replace("\\", "/").strip()
            # value format: version_name|version_date
            parts = val.split("|", 1)
            ver_name = parts[0].strip() if len(parts) > 0 else ""
            ver_date = parts[1].strip() if len(parts) > 1 else ""
            result[norm_path] = {
                "version_name": ver_name,
                "version_date": ver_date,
            }
        return result

    def is_excluded(self, rel_path: str) -> bool:
        norm_path = rel_path.replace("\\", "/").strip()
        excluded = self.get_excluded_files()
        return norm_path in excluded

    def set_excluded_file(self, rel_path: str, version_name: str, version_date: str):
        norm_path = rel_path.replace("\\", "/").strip()
        if "ExcludedFiles" not in self.config:
            self.config["ExcludedFiles"] = {}
        self.config["ExcludedFiles"][norm_path] = f"{version_name}|{version_date}"

    def remove_excluded_file(self, rel_path: str):
        norm_path = rel_path.replace("\\", "/").strip()
        if "ExcludedFiles" in self.config and norm_path in self.config["ExcludedFiles"]:
            del self.config["ExcludedFiles"][norm_path]

    def update_excluded_files_batch(self, excluded_dict: Dict[str, Dict[str, str]]):
        """
        Replaces the ExcludedFiles section with the given dict.
        """
        self.config["ExcludedFiles"] = {}
        for rel_path, meta in excluded_dict.items():
            norm_path = rel_path.replace("\\", "/").strip()
            v_name = meta.get("version_name", "")
            v_date = meta.get("version_date", "")
            self.config["ExcludedFiles"][norm_path] = f"{v_name}|{v_date}"


class ManagedRegistry:
    """
    Central registry in AppData for all ManagedUpdater instances.
    """
    def __init__(self):
        self.registry_path = get_managed_registry_path()
        self.data: Dict[str, Any] = {
            "instances": {},
            "global_settings": {
                "open_when_done": True,
                "delete_compressed": True,
                "run_script_after_update": False,
                "auto_update_on_startup": False,
            }
        }
        self.load()

    def load(self):
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if "instances" not in self.data:
                    self.data["instances"] = {}
                if "global_settings" not in self.data:
                    self.data["global_settings"] = {
                        "open_when_done": True,
                        "delete_compressed": True,
                        "run_script_after_update": False,
                        "auto_update_on_startup": False,
                    }
                elif "auto_update_on_startup" not in self.data["global_settings"]:
                    self.data["global_settings"]["auto_update_on_startup"] = False
            except Exception:
                self.data = {
                    "instances": {},
                    "global_settings": {
                        "open_when_done": True,
                        "delete_compressed": True,
                        "run_script_after_update": False,
                        "auto_update_on_startup": False,
                    }
                }

    def save(self):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def register_instance(self, project_dir: str, updater_path: str, project_name: str,
                          git_url: str = "", version_name: str = "", version_date: str = "",
                          update_type: str = "release") -> None:
        norm_dir = os.path.abspath(project_dir)
        self.data["instances"][norm_dir] = {
            "project_name": project_name,
            "updater_path": os.path.abspath(updater_path),
            "ini_path": os.path.join(norm_dir, CONFIG_FILENAME),
            "project_dir": norm_dir,
            "git_url": git_url,
            "version_name": version_name,
            "version_date": version_date,
            "update_type": update_type,
            "last_seen": datetime.now().isoformat(),
        }
        self.save()

    def update_instance_location(self, current_dir: str, current_updater_path: str) -> None:
        """
        Called when ManagedUpdater starts to ensure its location is kept fresh in AppData.
        """
        norm_dir = os.path.abspath(current_dir)
        ini = UpdaterConfig(norm_dir)
        if ini.exists():
            self.register_instance(
                project_dir=norm_dir,
                updater_path=current_updater_path,
                project_name=ini.project_name or os.path.basename(norm_dir),
                git_url=ini.git_url,
                version_name=ini.version_name,
                version_date=ini.version_date,
                update_type=ini.update_type,
            )
        elif norm_dir in self.data["instances"]:
            self.data["instances"][norm_dir]["updater_path"] = os.path.abspath(current_updater_path)
            self.data["instances"][norm_dir]["last_seen"] = datetime.now().isoformat()
            self.save()

    def has_instance(self, project_dir: str) -> bool:
        norm_dir = os.path.abspath(project_dir)
        return norm_dir in self.data["instances"]

    def get_instance(self, project_dir: str) -> Optional[Dict[str, Any]]:
        norm_dir = os.path.abspath(project_dir)
        return self.data["instances"].get(norm_dir)

    def get_all_instances(self) -> Dict[str, Dict[str, Any]]:
        return self.data.get("instances", {})

    def remove_instance(self, project_dir: str) -> None:
        norm_dir = os.path.abspath(project_dir)
        if norm_dir in self.data["instances"]:
            del self.data["instances"][norm_dir]
            self.save()

    def get_global_settings(self) -> Dict[str, bool]:
        return self.data.get("global_settings", {
            "open_when_done": True,
            "delete_compressed": True,
            "run_script_after_update": False,
            "auto_update_on_startup": False,
        })

    def save_global_settings(self, open_when_done: bool, delete_compressed: bool, run_script_after_update: bool = False, auto_update_on_startup: bool = False):
        self.data["global_settings"] = {
            "open_when_done": open_when_done,
            "delete_compressed": delete_compressed,
            "run_script_after_update": run_script_after_update,
            "auto_update_on_startup": auto_update_on_startup,
        }
        self.save()


def run_done_script(project_dir: str):
    """
    Executes update-done.bat in a visible terminal window.
    The terminal environment is redirected to start in the 'main' directory.
    Shows the terminal window so user can inspect output and success/failure state.
    """
    bat_path = os.path.join(project_dir, DONE_BAT_FILENAME)
    main_dir = os.path.join(project_dir, "main")

    # Ensure update-done.bat exists
    if not os.path.exists(bat_path):
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                pass
        except Exception:
            pass

    os.makedirs(main_dir, exist_ok=True)

    if sys.platform == "win32":
        # Launch cmd.exe keeping window open so user sees stdout, stderr, and exit status
        # Working directory is redirected to main_dir
        cmd_str = (
            f'title {DONE_BAT_FILENAME} Execution & '
            f'cd /d "{main_dir}" && '
            f'echo ======================================================== & '
            f'echo Running: {bat_path} & '
            f'echo Starting Directory: %CD% & '
            f'echo ======================================================== & echo. & '
            f'call "{bat_path}" & '
            f'if %ERRORLEVEL% EQU 0 (echo. & echo [SUCCESS] Script finished successfully with exit code 0.) '
            f'else (echo. & echo [FAILED] Script finished with error code %ERRORLEVEL%.) & '
            f'echo. & echo Press any key to close this terminal... & pause >nul'
        )
        subprocess.Popen(f'start "" cmd.exe /c "{cmd_str}"', shell=True, cwd=main_dir)
    else:
        subprocess.Popen(f'cd "{main_dir}" && bash "{bat_path}"', shell=True)
