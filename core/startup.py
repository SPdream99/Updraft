import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from core.config import ManagedRegistry, UpdaterConfig, run_done_script, get_appdata_dir
from core.downloader import UpdateEngine
from core.git_client import GitHubClient, parse_git_url
from core.asset_matcher import match_release_assets

# Windows Registry Run Key for current user (no administrator privileges needed)
RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_STARTUP_NAME = "UpdraftUpdateManager"


def is_startup_enabled(entry_name: str = DEFAULT_STARTUP_NAME) -> bool:
    """
    Checks if a startup entry exists in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, entry_name)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def get_startup_command(entry_name: str = DEFAULT_STARTUP_NAME) -> Optional[str]:
    """
    Retrieves the command line currently registered in HKCU Run.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, entry_name)
            return val
    except Exception:
        return None


def set_startup_enabled(enabled: bool, entry_name: str = DEFAULT_STARTUP_NAME, custom_command: Optional[str] = None) -> bool:
    """
    Enables or disables automatic startup for Updraft in Windows Registry Run key.
    """
    if sys.platform != "win32":
        return False

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                if custom_command:
                    cmd = custom_command
                else:
                    # Determine executable or script path
                    if getattr(sys, "frozen", False):
                        # Running as packaged PyInstaller executable (e.g. UpdateManager.exe)
                        exe_path = os.path.abspath(sys.executable)
                        cmd = f'"{exe_path}" --startup'
                    else:
                        # Running from Python source
                        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        mgr_py = os.path.join(base_dir, "update_manager.py")
                        py_exe = os.path.abspath(sys.executable)
                        cmd = f'"{py_exe}" "{mgr_py}" --startup'
                winreg.SetValueEx(key, entry_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, entry_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Error updating Windows startup registry: {e}")
        return False


def show_system_notification(title: str, message: str):
    """
    Displays a non-intrusive Windows desktop notification.
    Falls back gracefully if notification APIs are unavailable.
    """
    if sys.platform == "win32":
        try:
            # Use PowerShell to trigger a Windows native toast notification
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastText02">
                        <text id="1">{title}</text>
                        <text id="2">{message}</text>
                    </binding>
                </visual>
            </toast>
"@
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Updraft")
            $notifier.Show($toast)
            """
            import subprocess
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                             creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
            return
        except Exception:
            pass


def run_startup_update_all(registry: Optional[ManagedRegistry] = None, log_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Headless background updater executed on machine startup.
    Iterates through all managed projects in the registry, checks for updates,
    downloads and installs matched assets silently, and records a log.
    """
    if registry is None:
        registry = ManagedRegistry()

    if log_file is None:
        log_file = os.path.join(get_appdata_dir(), "startup_update.log")

    results = {
        "timestamp": datetime.now().isoformat(),
        "checked_count": 0,
        "updated_projects": [],
        "errors": [],
        "unresolved_assets": [],
    }

    log_lines = [
        f"\n{'=' * 60}",
        f"Updraft Startup Auto-Update Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"{'=' * 60}",
    ]

    instances = registry.get_all_instances()
    if not instances:
        log_lines.append("No managed projects found in registry. Exiting.")
        _write_log(log_file, log_lines)
        return results

    for path, meta in instances.items():
        if not os.path.exists(path):
            continue

        results["checked_count"] += 1
        cfg = UpdaterConfig(path)
        if not cfg.exists() or not cfg.git_url:
            continue

        # Check if project has opted out of startup updates
        if not cfg.auto_update_on_startup:
            log_lines.append(f"Skipping {cfg.project_name}: auto_update_on_startup is disabled.")
            continue

        repo_info = parse_git_url(cfg.git_url)
        if not repo_info:
            continue

        client = GitHubClient(repo_info)
        p_name = cfg.project_name or os.path.basename(path)

        try:
            if cfg.update_type == "source":
                commit = client.get_latest_commit()
                remote_name = commit.get("name", commit.get("short_sha"))
                remote_date = commit.get("date", "")
                if (remote_name != cfg.version_name) or (remote_date > cfg.version_date):
                    log_lines.append(f"Updating {p_name} to commit {remote_name}...")
                    engine = UpdateEngine(path)
                    fpath = engine.download_file(commit["zip_url"], f"{p_name}-source.zip")
                    engine.install_or_update([fpath], is_update=True)
                    cfg.version_name = remote_name
                    cfg.version_date = remote_date
                    cfg.save()
                    results["updated_projects"].append(f"{p_name} ({remote_name})")
                    if cfg.run_script_after_update:
                        run_done_script(path)
            else:
                rel = client.get_latest_release()
                if rel:
                    remote_name = rel.get("name") or rel.get("tag_name")
                    remote_date = rel.get("published_at", "")
                    remote_tag = rel.get("tag_name", "")
                    if (remote_name != cfg.version_name) or (remote_date > cfg.version_date):
                        all_assets = rel.get("assets", [])
                        matched, unresolved = match_release_assets(
                            selected_asset_names=cfg.selected_assets,
                            available_assets=all_assets,
                            old_tag=cfg.version_name,
                            new_tag=remote_tag or remote_name
                        )

                        if unresolved:
                            log_lines.append(f"Notice: {p_name} has unresolved assets {unresolved}. Skipping silent update.")
                            results["unresolved_assets"].append({"project": p_name, "unresolved": unresolved})
                            continue

                        if matched:
                            log_lines.append(f"Updating {p_name} to release {remote_name} ({len(matched)} assets)...")
                            engine = UpdateEngine(path)
                            downloaded = []
                            for a in matched:
                                fpath = engine.download_file(a["download_url"], a["name"])
                                downloaded.append(fpath)

                            engine.install_or_update(downloaded, is_update=True)
                            cfg.version_name = remote_name
                            cfg.version_date = remote_date
                            cfg.selected_assets = [a["name"] for a in matched]
                            cfg.save()

                            # Refresh registry entry
                            registry.register_instance(
                                project_dir=path,
                                updater_path=meta.get("updater_path", os.path.join(path, "ManagedUpdater.exe")),
                                project_name=p_name,
                                git_url=cfg.git_url,
                                version_name=cfg.version_name,
                                version_date=cfg.version_date,
                                update_type=cfg.update_type
                            )

                            results["updated_projects"].append(f"{p_name} ({remote_name})")
                            log_lines.append(f"Successfully updated {p_name} to {remote_name}.")

                            if cfg.run_script_after_update:
                                run_done_script(path)
        except Exception as e:
            err_msg = f"Failed to update {p_name}: {e}"
            log_lines.append(err_msg)
            results["errors"].append(err_msg)

    log_lines.append(f"Startup check complete. {len(results['updated_projects'])} project(s) updated.")
    _write_log(log_file, log_lines)

    # Show notification if any project was updated
    if results["updated_projects"]:
        summary_text = ", ".join(results["updated_projects"])
        show_system_notification("Updraft Auto-Update", f"Updated {len(results['updated_projects'])} project(s): {summary_text}")
    elif results["unresolved_assets"]:
        p_names = ", ".join([item["project"] for item in results["unresolved_assets"]])
        show_system_notification("Updraft Notice", f"New version available for {p_names}. Open Update Manager to confirm file selections.")

    return results


def run_silent_single_update(project_dir: str) -> bool:
    """
    Performs a silent check and update for a single project (used by standalone updater on startup).
    """
    norm_dir = os.path.abspath(project_dir)
    cfg = UpdaterConfig(norm_dir)
    if not cfg.exists() or not cfg.git_url or not cfg.auto_update_on_startup:
        return False

    repo_info = parse_git_url(cfg.git_url)
    if not repo_info:
        return False

    client = GitHubClient(repo_info)
    p_name = cfg.project_name or os.path.basename(norm_dir)

    try:
        if cfg.update_type == "source":
            commit = client.get_latest_commit()
            remote_name = commit.get("name", commit.get("short_sha"))
            remote_date = commit.get("date", "")
            if (remote_name != cfg.version_name) or (remote_date > cfg.version_date):
                engine = UpdateEngine(norm_dir)
                fpath = engine.download_file(commit["zip_url"], f"{p_name}-source.zip")
                engine.install_or_update([fpath], is_update=True)
                cfg.version_name = remote_name
                cfg.version_date = remote_date
                cfg.save()
                if cfg.run_script_after_update:
                    run_done_script(norm_dir)
                show_system_notification("Updraft Auto-Update", f"Updated {p_name} to commit {remote_name}")
                return True
        else:
            rel = client.get_latest_release()
            if rel:
                remote_name = rel.get("name") or rel.get("tag_name")
                remote_date = rel.get("published_at", "")
                remote_tag = rel.get("tag_name", "")
                if (remote_name != cfg.version_name) or (remote_date > cfg.version_date):
                    all_assets = rel.get("assets", [])
                    matched, unresolved = match_release_assets(
                        selected_asset_names=cfg.selected_assets,
                        available_assets=all_assets,
                        old_tag=cfg.version_name,
                        new_tag=remote_tag or remote_name
                    )
                    if matched and not unresolved:
                        engine = UpdateEngine(norm_dir)
                        downloaded = [engine.download_file(a["download_url"], a["name"]) for a in matched]
                        engine.install_or_update(downloaded, is_update=True)
                        cfg.version_name = remote_name
                        cfg.version_date = remote_date
                        cfg.selected_assets = [a["name"] for a in matched]
                        cfg.save()
                        if cfg.run_script_after_update:
                            run_done_script(norm_dir)
                        show_system_notification("Updraft Auto-Update", f"Updated {p_name} to release {remote_name}")
                        return True
    except Exception as e:
        print(f"Silent single update error for {p_name}: {e}")

    return False


def _write_log(log_path: str, lines: List[str]):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
    except Exception as e:
        print(f"Error writing startup update log: {e}")
