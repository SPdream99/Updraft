import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, Any, List, Optional

from core.config import ManagedRegistry, UpdaterConfig, run_done_script
from core.downloader import UpdateEngine
from core.git_client import GitHubClient, parse_git_url
from core.theme import (
    apply_win7_theme,
    create_win7_header,
    FONT_NORMAL,
    FONT_BOLD,
    FONT_TITLE,
    BG_COLOR,
    PANEL_BG,
    LIGHT_BORDER,
    MUTED_TEXT,
    SUCCESS_GREEN,
    ACCENT_BLUE,
)
from core.asset_matcher import match_release_assets
from core.version import APP_VERSION, APP_NAME
from core.self_updater import check_app_update, perform_app_self_update, update_all_managed_instances
from gui.asset_picker_dialog import AssetPickerDialog
from gui.exclude_window import ExcludeFilesDialog
from gui.settings_window import SettingsDialog


class UpdateManagerWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.registry = ManagedRegistry()

        self.title("Update Manager")
        self.geometry("980x600")
        self.minsize(860, 500)

        apply_win7_theme(self)

        # Center on screen
        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
            y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.instances: Dict[str, Dict[str, Any]] = {}
        self.remote_status: Dict[str, Dict[str, Any]] = {}

        if getattr(sys, "frozen", False):
            self.updater_exe_path = os.path.abspath(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.updater_exe_path = os.path.join(base_dir, "dist", "UpdateManager.exe")

        self._build_ui()
        self._refresh_list()

        # Check for Updraft self-update if auto_update_self is enabled
        if self.registry.get_global_settings().get("auto_update_self", True):
            self.after(1500, lambda: self._on_update_app(silent=True))

    def _build_ui(self):
        create_win7_header(
            self,
            "Update Manager",
            "Monitor, check, and update all managed git project installations across your system"
        )

        # Top Command Bar / Toolbar (Windows 7 Aero style)
        toolbar = ttk.Frame(self, padding=(12, 8))
        toolbar.pack(fill="x")

        btn_check_all = ttk.Button(toolbar, text="Check All Updates", command=self._on_check_all)
        btn_check_all.pack(side="left", padx=(0, 6))

        btn_update_all = ttk.Button(toolbar, text="Update All", style="Accent.TButton", command=self._on_update_all)
        btn_update_all.pack(side="left", padx=(0, 6))

        btn_refresh = ttk.Button(toolbar, text="Refresh List", command=self._refresh_list)
        btn_refresh.pack(side="left", padx=(0, 6))

        btn_add = ttk.Button(toolbar, text="+ Add Existing Folder...", command=self._on_add_folder)
        btn_add.pack(side="left", padx=(0, 6))

        btn_update_app = ttk.Button(toolbar, text=f"Update Updraft ({APP_VERSION})", command=lambda: self._on_update_app(silent=False))
        btn_update_app.pack(side="left", padx=(0, 6))

        btn_global_settings = ttk.Button(toolbar, text="Global Settings", command=self._on_global_settings)
        btn_global_settings.pack(side="right")

        from core.startup import is_startup_enabled
        startup_active = is_startup_enabled()
        self.lbl_startup_status = ttk.Label(
            toolbar,
            text=f"Startup Auto-Update: {'Enabled' if startup_active else 'Disabled'}",
            font=("Segoe UI", 8),
            foreground=SUCCESS_GREEN if startup_active else MUTED_TEXT
        )
        self.lbl_startup_status.pack(side="right", padx=(0, 12))

        sep_top = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep_top.pack(fill="x")

        # Bottom Status Bar (docked first to bottom)
        status_bar = ttk.Frame(self, padding=(14, 4))
        status_bar.pack(fill="x", side="bottom")

        sep_bot = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep_bot.pack(fill="x", side="bottom")

        self.lbl_status = ttk.Label(status_bar, text="Ready", font=("Segoe UI", 8), foreground=MUTED_TEXT)
        self.lbl_status.pack(side="left")

        self.lbl_count = ttk.Label(status_bar, text="0 instances managed", font=("Segoe UI", 8), foreground=MUTED_TEXT)
        self.lbl_count.pack(side="right")

        # Selected Project Actions Panel (docked right above status bar)
        action_box = ttk.LabelFrame(self, text="Selected Project Actions", padding=(12, 8))
        action_box.pack(fill="x", padx=14, pady=(4, 8), side="bottom")

        btn_box = ttk.Frame(action_box)
        btn_box.pack(fill="x")

        self.btn_check_sel = ttk.Button(btn_box, text="Check Update", command=self._on_check_selected, state="disabled")
        self.btn_check_sel.pack(side="left", padx=(0, 6))

        self.btn_update_sel = ttk.Button(btn_box, text="Update Project", style="Accent.TButton", command=self._on_update_selected, state="disabled")
        self.btn_update_sel.pack(side="left", padx=(0, 6))

        self.btn_exclude_sel = ttk.Button(btn_box, text="Exclude Files...", command=self._on_exclude_selected, state="disabled")
        self.btn_exclude_sel.pack(side="left", padx=(0, 6))

        self.btn_settings_sel = ttk.Button(btn_box, text="Settings...", command=self._on_settings_selected, state="disabled")
        self.btn_settings_sel.pack(side="left", padx=(0, 6))

        self.btn_run_script_sel = ttk.Button(btn_box, text="Run Bat Script", command=self._on_run_script_selected, state="disabled")
        self.btn_run_script_sel.pack(side="left", padx=(0, 6))

        self.btn_shortcuts_sel = ttk.Button(btn_box, text="Create Shortcuts", command=self._on_shortcuts_selected, state="disabled")
        self.btn_shortcuts_sel.pack(side="left", padx=(0, 6))

        self.btn_open_folder = ttk.Button(btn_box, text="Open Folder", command=self._on_open_folder, state="disabled")
        self.btn_open_folder.pack(side="left", padx=(0, 6))

        self.btn_remove_sel = ttk.Button(btn_box, text="Remove from List", command=self._on_remove_selected, state="disabled")
        self.btn_remove_sel.pack(side="right")

        # Main Content: TreeView Table of Projects (takes all remaining space)
        content_frame = ttk.Frame(self, padding=(14, 10))
        content_frame.pack(fill="both", expand=True, side="top")

        scroll_y = ttk.Scrollbar(content_frame, orient="vertical")
        scroll_x = ttk.Scrollbar(content_frame, orient="horizontal")

        cols = ("project", "version", "date", "latest", "status", "location")
        self.tree = ttk.Treeview(
            content_frame,
            columns=cols,
            show="headings",
            selectmode="browse",
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set
        )

        scroll_y.config(command=self.tree.yview)
        scroll_x.config(command=self.tree.xview)

        self.tree.heading("project", text="Project Name")
        self.tree.heading("version", text="Current Version")
        self.tree.heading("date", text="Version Date")
        self.tree.heading("latest", text="Latest Available")
        self.tree.heading("status", text="Status")
        self.tree.heading("location", text="Location")

        self.tree.column("project", width=140, anchor="w")
        self.tree.column("version", width=110, anchor="w")
        self.tree.column("date", width=120, anchor="w")
        self.tree.column("latest", width=110, anchor="w")
        self.tree.column("status", width=130, anchor="w")
        self.tree.column("location", width=240, anchor="w")

        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_select_item)
        self.tree.bind("<Double-1>", lambda e: self._on_open_folder())

    def _refresh_list(self):
        self.registry.load()
        self.instances = self.registry.get_all_instances()

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        count = 0
        for path, info in self.instances.items():
            count += 1
            # Verify folder exists
            exists = os.path.exists(path)
            status = "Ready" if exists else "Missing Folder"

            # Check if we already have remote check status
            rem = self.remote_status.get(path, {})
            latest_str = rem.get("latest_version", "-")
            if rem.get("has_update"):
                status = "Update Available"
            elif rem.get("checked"):
                status = "Up to date"

            name = info.get("project_name") or os.path.basename(path)
            ver = info.get("version_name") or "-"
            date = info.get("version_date") or "-"
            if len(date) > 10:
                date = date[:10]  # Just YYYY-MM-DD for table readability

            self.tree.insert(
                "",
                "end",
                iid=path,
                values=(name, ver, date, latest_str, status, path)
            )

        self.lbl_count.config(text=f"{count} project(s) managed")
        if hasattr(self, "lbl_startup_status"):
            from core.startup import is_startup_enabled
            startup_active = is_startup_enabled()
            self.lbl_startup_status.config(
                text=f"Startup Auto-Update: {'Enabled' if startup_active else 'Disabled'}",
                foreground=SUCCESS_GREEN if startup_active else MUTED_TEXT
            )
        self._on_select_item(None)

    def _get_selected_path(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _on_select_item(self, event):
        path = self._get_selected_path()
        has_sel = path is not None and os.path.exists(path)
        state = "normal" if has_sel else "disabled"

        self.btn_check_sel.config(state=state)
        self.btn_exclude_sel.config(state=state)
        self.btn_settings_sel.config(state=state)
        self.btn_run_script_sel.config(state=state)
        self.btn_shortcuts_sel.config(state=state)
        self.btn_open_folder.config(state="normal" if path else "disabled")
        self.btn_remove_sel.config(state="normal" if path else "disabled")

        # Update button enabled if update is available
        rem = self.remote_status.get(path, {}) if path else {}
        if rem.get("has_update") and has_sel:
            self.btn_update_sel.config(state="normal")
        else:
            self.btn_update_sel.config(state="disabled")

    def _on_open_folder(self):
        path = self._get_selected_path()
        if not path:
            return
        main_dir = os.path.join(path, "main")
        target = main_dir if os.path.exists(main_dir) else path
        try:
            os.startfile(target)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder:\n{e}", parent=self)

    def _on_remove_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        confirm = messagebox.askyesno(
            "Remove Managed Project",
            f"Remove '{path}' from the Update Manager?\n\n(This will not delete the project files from your disk).",
            parent=self
        )
        if confirm:
            self.registry.remove_instance(path)
            self._refresh_list()

    def _on_add_folder(self):
        folder = filedialog.askdirectory(title="Select Project Folder containing updater-info.ini", parent=self)
        if not folder:
            return
        config = UpdaterConfig(folder)
        if not config.exists():
            messagebox.showwarning(
                "Not an Updater Project",
                f"The selected folder does not contain 'updater-info.ini'.\n\nPlease run the updater executable inside that folder to set it up first.",
                parent=self
            )
            return

        self.registry.register_instance(
            project_dir=folder,
            updater_path=os.path.join(folder, "ManagedUpdater.exe"),
            project_name=config.project_name or os.path.basename(folder),
            git_url=config.git_url,
            version_name=config.version_name,
            version_date=config.version_date,
            update_type=config.update_type
        )
        self._refresh_list()

    def _on_exclude_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        config = UpdaterConfig(path)
        ExcludeFilesDialog(self, config, on_save_callback=self._refresh_list)

    def _on_settings_selected(self):
        path = self._get_selected_path()
        if not path:
            return
        config = UpdaterConfig(path)
        SettingsDialog(self, config, on_save_callback=self._refresh_list)

    def _on_run_script_selected(self):
        path = self._get_selected_path()
        if path and os.path.exists(path):
            run_done_script(path)

    def _on_shortcuts_selected(self):
        path = self._get_selected_path()
        if not path or not os.path.exists(path):
            return
        config = UpdaterConfig(path)
        if not getattr(config, "create_shortcuts", True):
            enable = messagebox.askyesno(
                "Shortcut Creation Disabled",
                f"Shortcut creation is currently disabled in Settings for '{config.project_name or os.path.basename(path)}'.\n\n"
                "Would you like to enable it and create shortcuts now?",
                parent=self
            )
            if not enable:
                return
            config.create_shortcuts = True
            config.save()

        try:
            engine = UpdateEngine(path)
            created = engine.create_shortcuts()
            if created:
                count = len(created)
                msg = f"Successfully created {count} shortcut/launcher file(s) for '{config.project_name or os.path.basename(path)}':\n\n"
                sample = "\n".join(f"• {os.path.basename(p)}" for p in created[:8])
                if count > 8:
                    sample += f"\n...and {count - 8} more."
                msg += sample
                messagebox.showinfo("Shortcuts Created", msg, parent=self)
            else:
                messagebox.showinfo(
                    "No Shortcuts Created",
                    f"No matching executable, HTML, or Python files were found to create shortcuts for in '{config.project_name or os.path.basename(path)}' within the configured subfolder depth.",
                    parent=self
                )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create shortcuts:\n{e}", parent=self)

    def _on_global_settings(self):
        g_settings = self.registry.get_global_settings()
        
        # Create a mock config to edit global settings
        class MockGlobalConfig:
            def __init__(self, reg):
                self.reg = reg
                s = reg.get_global_settings()
                self.open_when_done = s.get("open_when_done", True)
                self.delete_compressed = s.get("delete_compressed", True)
                self.run_script_after_update = s.get("run_script_after_update", False)
                self.auto_update_on_startup = s.get("auto_update_on_startup", False)
                self.auto_update_self = s.get("auto_update_self", True)
                self.create_shortcuts = s.get("create_shortcuts", True)
                self.shortcut_folder_level = s.get("shortcut_folder_level", -1)
                self.project_name = "Global Settings"

            def save(self):
                self.reg.save_global_settings(
                    self.open_when_done,
                    self.delete_compressed,
                    self.run_script_after_update,
                    self.auto_update_on_startup,
                    self.auto_update_self,
                    self.create_shortcuts,
                    self.shortcut_folder_level
                )

        mock = MockGlobalConfig(self.registry)
        SettingsDialog(self, mock, on_save_callback=self._refresh_list, is_global=True)

    # --- Update Checking & Performing ---
    def _check_project_update(self, path: str) -> Dict[str, Any]:
        config = UpdaterConfig(path)
        if not config.exists() or not config.git_url:
            return {"error": "Missing config or git_url"}

        repo_info = parse_git_url(config.git_url)
        if not repo_info:
            return {"error": "Invalid git_url"}

        client = GitHubClient(repo_info)
        is_available = False
        remote_name = ""
        remote_date = ""
        download_urls = []

        if config.update_type == "source":
            commit = client.get_latest_commit()
            remote_name = commit.get("name", commit.get("short_sha"))
            remote_date = commit.get("date", "")
            if (remote_name != config.version_name) or (remote_date > config.version_date):
                is_available = True
                download_urls = [(commit["zip_url"], f"{config.project_name}-source.zip")]
        else:
            rel = client.get_latest_release()
            if rel:
                remote_name = rel.get("name") or rel.get("tag_name")
                remote_date = rel.get("published_at", "")
                remote_tag = rel.get("tag_name", "")
                all_assets = rel.get("assets", [])
                unresolved = []
                matched_assets = []
                if (remote_name != config.version_name) or (remote_date > config.version_date):
                    is_available = True
                    matched_assets, unresolved = match_release_assets(
                        selected_asset_names=config.selected_assets,
                        available_assets=all_assets,
                        old_tag=config.version_name,
                        new_tag=remote_tag or remote_name
                    )
                    download_urls = [(a["download_url"], a["name"]) for a in matched_assets]

        return {
            "checked": True,
            "has_update": is_available,
            "latest_version": remote_name,
            "latest_date": remote_date,
            "download_urls": download_urls,
            "all_assets": all_assets if config.update_type == "release" else [],
            "matched_assets": matched_assets if config.update_type == "release" else [],
            "unresolved": unresolved if config.update_type == "release" else [],
            "config": config,
        }

    def _on_check_selected(self):
        path = self._get_selected_path()
        if not path:
            return

        self.lbl_status.config(text=f"Checking update for {os.path.basename(path)}...", foreground=ACCENT_BLUE)

        def worker():
            try:
                res = self._check_project_update(path)
                self.remote_status[path] = res
                self.after(0, self._refresh_list)
                if res.get("has_update"):
                    self.after(0, lambda: messagebox.showinfo(
                        "Update Available",
                        f"An update is available for {os.path.basename(path)}!\n\nNew Version: {res['latest_version']}",
                        parent=self
                    ))
                else:
                    self.after(0, lambda: messagebox.showinfo(
                        "Up to Date",
                        f"{os.path.basename(path)} is currently up to date.",
                        parent=self
                    ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Check Error", f"Failed: {e}", parent=self))
            finally:
                self.after(0, lambda: self.lbl_status.config(text="Ready", foreground=MUTED_TEXT))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_all(self):
        self.lbl_status.config(text="Checking updates for all projects...", foreground=ACCENT_BLUE)

        def worker():
            for path in list(self.instances.keys()):
                if os.path.exists(path):
                    try:
                        res = self._check_project_update(path)
                        self.remote_status[path] = res
                    except Exception:
                        pass
            self.after(0, self._refresh_list)
            self.after(0, lambda: self.lbl_status.config(text="Finished checking all projects.", foreground=SUCCESS_GREEN))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_selected(self):
        path = self._get_selected_path()
        if not path or path not in self.remote_status:
            return

        rem = self.remote_status[path]
        if not rem.get("has_update"):
            return

        confirm = messagebox.askyesno(
            "Confirm Update",
            f"Update {os.path.basename(path)} to {rem['latest_version']} now?",
            parent=self
        )
        if not confirm:
            return

        # If release update has unresolved assets or no matches found while assets exist:
        if rem["config"].update_type == "release" and rem.get("all_assets"):
            if rem.get("unresolved") or not rem.get("download_urls"):
                def on_assets_chosen(chosen_names: List[str]):
                    config = rem["config"]
                    config.selected_assets = chosen_names
                    config.save()
                    rem["download_urls"] = [(a["download_url"], a["name"]) for a in rem["all_assets"] if a["name"] in chosen_names]
                    self._perform_update_for_path(path, rem)

                preselected = [a["name"] for a in rem.get("matched_assets", [])]
                AssetPickerDialog(
                    self,
                    project_name=rem["config"].project_name,
                    release_tag=rem["latest_version"],
                    available_assets=rem["all_assets"],
                    preselected_names=preselected,
                    unresolved_names=rem.get("unresolved", []),
                    on_confirm=on_assets_chosen
                )
                return
            else:
                # Update selected_assets in config to new matched asset names
                config = rem["config"]
                config.selected_assets = [a["name"] for a in rem.get("matched_assets", [])]
                config.save()

        self._perform_update_for_path(path, rem)

    def _perform_update_for_path(self, path: str, rem: Dict[str, Any]):
        self.lbl_status.config(text=f"Updating {os.path.basename(path)}...", foreground=ACCENT_BLUE)

        def worker():
            try:
                engine = UpdateEngine(path)
                config = rem["config"]
                downloaded = []

                for url, fname in rem["download_urls"]:
                    p = engine.download_file(url, fname)
                    downloaded.append(p)

                engine.install_or_update(downloaded, is_update=True)

                config.version_name = rem["latest_version"]
                config.version_date = rem["latest_date"]
                config.save()

                self.registry.register_instance(
                    project_dir=path,
                    updater_path=os.path.join(path, "ManagedUpdater.exe"),
                    project_name=config.project_name,
                    git_url=config.git_url,
                    version_name=config.version_name,
                    version_date=config.version_date,
                    update_type=config.update_type
                )

                rem["has_update"] = False
                rem["latest_version"] = "-"

                if config.run_script_after_update:
                    run_done_script(path)

                self.after(0, self._refresh_list)
                self.after(0, lambda: messagebox.showinfo(
                    "Update Complete",
                    f"Successfully updated {config.project_name}!",
                    parent=self
                ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Update Error", f"Failed to update {os.path.basename(path)}:\n{e}", parent=self))
            finally:
                self.after(0, lambda: self.lbl_status.config(text="Ready", foreground=MUTED_TEXT))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_all(self):
        available_updates = [p for p, rem in self.remote_status.items() if rem.get("has_update")]
        if not available_updates:
            messagebox.showinfo("Update All", "No pending updates found. Run 'Check All Updates' first.", parent=self)
            return

        confirm = messagebox.askyesno(
            "Update All",
            f"There are {len(available_updates)} project(s) with available updates.\n\nDo you want to update all of them now?",
            parent=self
        )
        if not confirm:
            return

        self.lbl_status.config(text="Updating all projects...", foreground=ACCENT_BLUE)

        def worker():
            successes = 0
            for path in available_updates:
                rem = self.remote_status.get(path)
                if not rem:
                    continue
                try:
                    engine = UpdateEngine(path)
                    config = rem["config"]
                    downloaded = []

                    for url, fname in rem["download_urls"]:
                        p = engine.download_file(url, fname)
                        downloaded.append(p)

                    engine.install_or_update(downloaded, is_update=True)

                    config.version_name = rem["latest_version"]
                    config.version_date = rem["latest_date"]
                    config.save()

                    self.registry.register_instance(
                        project_dir=path,
                        updater_path=os.path.join(path, "ManagedUpdater.exe"),
                        project_name=config.project_name,
                        git_url=config.git_url,
                        version_name=config.version_name,
                        version_date=config.version_date,
                        update_type=config.update_type
                    )

                    rem["has_update"] = False
                    successes += 1

                    if config.run_script_after_update:
                        run_done_script(path)
                except Exception as e:
                    print(f"Error updating {path}: {e}")

            self.after(0, self._refresh_list)
            self.after(0, lambda: messagebox.showinfo("Update All", f"Completed updating {successes} project(s)!", parent=self))
            self.after(0, lambda: self.lbl_status.config(text="Finished batch update.", foreground=SUCCESS_GREEN))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_app(self, silent: bool = False):
        if not silent:
            self.lbl_status.config(text="Checking for Updraft updates...", foreground=ACCENT_BLUE)

        def worker():
            try:
                res = check_app_update("UpdateManager.exe")
                if res.get("has_update"):
                    latest = res["latest_version"]
                    url = res.get("asset_url")
                    all_assets = res.get("all_assets", [])
                    inst_count = len(self.registry.get_all_instances())

                    def prompt_and_update():
                        if inst_count > 0:
                            msg = (
                                f"A new version of Updraft is available!\n\n"
                                f"Current Version: {APP_VERSION}\n"
                                f"Latest Version:  {latest}\n\n"
                                f"This will update UpdateManager and all {inst_count} managed updater instance(s) across your projects.\n\n"
                                f"Do you want to download and install this update now?"
                            )
                        else:
                            msg = (
                                f"A new version of Updraft is available!\n\n"
                                f"Current Version: {APP_VERSION}\n"
                                f"Latest Version:  {latest}\n\n"
                                f"Do you want to download and install this update now?"
                            )

                        confirm = messagebox.askyesno("Updraft Update Available", msg, parent=self)
                        if confirm:
                            if not url:
                                messagebox.showwarning(
                                    "Update Notice",
                                    f"No precompiled binary asset found for UpdateManager.exe in release {latest}.\nPlease visit GitHub to download manually.",
                                    parent=self
                                )
                                return
                            self._start_app_update(all_assets, url, latest)

                    self.after(0, prompt_and_update)
                else:
                    if not silent:
                        msg = f"Updraft and all managed instances are currently up to date ({APP_VERSION})."
                        self.after(0, lambda: messagebox.showinfo("Updraft Up to Date", msg, parent=self))
            except Exception as e:
                if not silent:
                    self.after(0, lambda: messagebox.showerror("Check Failed", f"Could not check for Updraft update: {e}", parent=self))
            finally:
                self.after(0, lambda: self.lbl_status.config(text="Ready", foreground=MUTED_TEXT))

        threading.Thread(target=worker, daemon=True).start()

    def _start_app_update(self, all_assets: list, manager_url: str, latest_version: str):
        self.lbl_status.config(text="Updating Updraft suite...", foreground=ACCENT_BLUE)

        def worker():
            try:
                # 1. Update all ManagedUpdater instances
                inst_count = len(self.registry.get_all_instances())
                updated_inst = 0
                if inst_count > 0:
                    self.after(0, lambda: self.lbl_status.config(text="Updating managed project instances...", foreground=ACCENT_BLUE))
                    inst_res = update_all_managed_instances(all_assets, registry=self.registry)
                    updated_inst = inst_res.get("updated_count", 0)

                # 2. Download and self-update UpdateManager.exe
                def prog(pct):
                    self.after(0, lambda: self.lbl_status.config(text=f"Downloading UpdateManager.exe... {int(pct * 100)}%", foreground=ACCENT_BLUE))

                perform_app_self_update(manager_url, self.updater_exe_path, progress_callback=prog, restart=True)

                # If running in development (not frozen), perform_app_self_update returns cleanly
                self.after(0, lambda: messagebox.showinfo(
                    "Update Complete",
                    f"Updraft update complete!\n\nUpdated {updated_inst} managed project instance(s) and staged {latest_version}.",
                    parent=self
                ))
                self.after(0, lambda: self.lbl_status.config(text="Ready", foreground=MUTED_TEXT))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Self-Update Error", f"Failed to perform self-update:\n{e}", parent=self))
                self.after(0, lambda: self.lbl_status.config(text="Ready", foreground=MUTED_TEXT))

        threading.Thread(target=worker, daemon=True).start()
