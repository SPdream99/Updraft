import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any, List

from core.config import UpdaterConfig, ManagedRegistry, run_done_script
from core.downloader import UpdateEngine, is_archive
from core.git_client import GitHubClient, parse_git_url
from core.theme import (
    apply_win7_theme,
    create_win7_header,
    FONT_NORMAL,
    FONT_BOLD,
    FONT_TITLE,
    FONT_LARGE_BUTTON,
    BG_COLOR,
    PANEL_BG,
    LIGHT_BORDER,
    MUTED_TEXT,
    SUCCESS_GREEN,
    ACCENT_BLUE,
)
from gui.exclude_window import ExcludeFilesDialog
from gui.settings_window import SettingsDialog


class UpdaterMainWindow(tk.Tk):
    def __init__(
        self,
        project_dir: str,
        updater_exe_path: str,
        is_managed: bool = False
    ):
        super().__init__()
        self.project_dir = os.path.abspath(project_dir)
        self.updater_exe_path = os.path.abspath(updater_exe_path)
        self.is_managed = is_managed

        self.config = UpdaterConfig(self.project_dir)
        self.config.ensure_done_script()
        self.engine = UpdateEngine(self.project_dir)

        # If managed, ensure location is synchronized in AppData
        if self.is_managed:
            registry = ManagedRegistry()
            registry.update_instance_location(self.project_dir, self.updater_exe_path)

        proj_title = self.config.project_name or os.path.basename(self.project_dir)
        mode_str = "Managed" if self.is_managed else "Standalone"
        self.title(f"{proj_title} - Updater ({mode_str})")
        self.geometry("520x510")
        self.minsize(480, 470)
        self.resizable(False, False)

        apply_win7_theme(self)

        # Center window
        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
            y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self._build_ui()

    def _build_ui(self):
        proj_name = self.config.project_name or os.path.basename(self.project_dir)
        create_win7_header(
            self,
            f"{proj_name} Updater",
            "Keep your project files, executables, and dependencies up to date"
        )

        main_frame = ttk.Frame(self, padding=(24, 16))
        main_frame.pack(fill="both", expand=True)

        # Status & Version Information Box
        info_group = ttk.LabelFrame(main_frame, text="Current Project Details", padding=(16, 12))
        info_group.pack(fill="x", pady=(0, 16))

        grid_frame = ttk.Frame(info_group)
        grid_frame.pack(fill="x")

        ttk.Label(grid_frame, text="Project Name:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_info_name = ttk.Label(grid_frame, text=proj_name)
        self.lbl_info_name.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=2)

        ttk.Label(grid_frame, text="Current Version:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=2)
        self.lbl_info_ver = ttk.Label(grid_frame, text=self.config.version_name or "Unknown")
        self.lbl_info_ver.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=2)

        ttk.Label(grid_frame, text="Version Date:", style="Bold.TLabel").grid(row=2, column=0, sticky="w", pady=2)
        self.lbl_info_date = ttk.Label(grid_frame, text=self.config.version_date or "Unknown")
        self.lbl_info_date.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=2)

        ttk.Label(grid_frame, text="Update Source:", style="Bold.TLabel").grid(row=3, column=0, sticky="w", pady=2)
        src_label = f"{self.config.update_type.capitalize()} ({self.config.git_url})"
        self.lbl_info_src = ttk.Label(grid_frame, text=src_label, wraplength=280)
        self.lbl_info_src.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=2)

        # Four Buttons Container
        btn_group = ttk.Frame(main_frame)
        btn_group.pack(fill="x", pady=(8, 12))

        # Button 1: Check for Update
        self.btn_check_update = ttk.Button(
            btn_group,
            text="Check for Update",
            style="Large.TButton",
            command=self._on_check_update
        )
        self.btn_check_update.pack(fill="x", pady=4, ipady=3)

        # Button 2: Exclude-File
        self.btn_exclude_file = ttk.Button(
            btn_group,
            text="Exclude-File",
            style="Large.TButton",
            command=self._on_exclude_file
        )
        self.btn_exclude_file.pack(fill="x", pady=4, ipady=3)

        # Button 3: Setting
        self.btn_settings = ttk.Button(
            btn_group,
            text="Setting",
            style="Large.TButton",
            command=self._on_settings
        )
        self.btn_settings.pack(fill="x", pady=4, ipady=3)

        # Button 4: Run bat script
        self.btn_run_script = ttk.Button(
            btn_group,
            text="Run bat script",
            style="Large.TButton",
            command=self._on_run_bat_script
        )
        self.btn_run_script.pack(fill="x", pady=4, ipady=3)

        # Button 5: Close
        self.btn_close = ttk.Button(
            btn_group,
            text="Close",
            style="Large.TButton",
            command=self.destroy
        )
        self.btn_close.pack(fill="x", pady=4, ipady=3)

        # Progress bar & Status text area at bottom
        status_frame = ttk.Frame(self, padding=(20, 8))
        status_frame.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        self.progress_bar = ttk.Progressbar(status_frame, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 4))

        self.lbl_status = ttk.Label(status_frame, text="Ready", font=("Segoe UI", 8), foreground=MUTED_TEXT)
        self.lbl_status.pack(anchor="w")

    def _refresh_info_labels(self):
        self.config.load()
        proj_name = self.config.project_name or os.path.basename(self.project_dir)
        self.lbl_info_name.config(text=proj_name)
        self.lbl_info_ver.config(text=self.config.version_name or "Unknown")
        self.lbl_info_date.config(text=self.config.version_date or "Unknown")
        src_label = f"{self.config.update_type.capitalize()} ({self.config.git_url})"
        self.lbl_info_src.config(text=src_label)

    # --- Button Actions ---
    def _on_check_update(self):
        self.btn_check_update.config(state="disabled")
        self.lbl_status.config(text="Checking for updates...", foreground=ACCENT_BLUE)
        self.progress_bar["value"] = 0

        def check_thread():
            try:
                repo_info = parse_git_url(self.config.git_url)
                if not repo_info:
                    self.after(0, lambda: messagebox.showerror("Error", "Invalid Git URL configured.", parent=self))
                    return

                client = GitHubClient(repo_info)
                is_update_available = False
                remote_version_name = ""
                remote_version_date = ""
                remote_download_urls: List[tuple] = []

                if self.config.update_type == "source":
                    latest_commit = client.get_latest_commit()
                    remote_version_name = latest_commit.get("name", latest_commit.get("short_sha"))
                    remote_version_date = latest_commit.get("date", "")
                    
                    if (remote_version_name != self.config.version_name) or (remote_version_date > self.config.version_date):
                        is_update_available = True
                        remote_download_urls = [(latest_commit["zip_url"], f"{self.config.project_name}-source.zip")]

                else:
                    latest_release = client.get_latest_release()
                    if latest_release:
                        remote_version_name = latest_release.get("name") or latest_release.get("tag_name")
                        remote_version_date = latest_release.get("published_at", "")
                        
                        if (remote_version_name != self.config.version_name) or (remote_version_date > self.config.version_date):
                            is_update_available = True
                            selected_assets = self.config.selected_assets
                            for a in latest_release.get("assets", []):
                                if not selected_assets or a["name"] in selected_assets:
                                    remote_download_urls.append((a["download_url"], a["name"]))

                if is_update_available:
                    self.after(0, lambda: self._prompt_and_perform_update(
                        remote_version_name,
                        remote_version_date,
                        remote_download_urls
                    ))
                else:
                    self.after(0, lambda: self._show_up_to_date(self.config.version_name))

            except Exception as e:
                self.after(0, lambda err=str(e): self._show_check_error(err))
            finally:
                self.after(0, lambda: self.btn_check_update.config(state="normal"))

        threading.Thread(target=check_thread, daemon=True).start()

    def _show_up_to_date(self, current_ver: str):
        self.lbl_status.config(text="You are on the latest version.", foreground=SUCCESS_GREEN)
        messagebox.showinfo(
            "Check for Update",
            f"Your project is up to date!\n\nCurrent Version: {current_ver}",
            parent=self
        )

    def _show_check_error(self, err: str):
        self.lbl_status.config(text="Failed to check for updates.", foreground="#D83B01")
        messagebox.showerror("Update Check Error", f"Unable to check for updates:\n{err}", parent=self)

    def _prompt_and_perform_update(
        self,
        new_version_name: str,
        new_version_date: str,
        download_urls: List[tuple]
    ):
        self.lbl_status.config(text="Update available!", foreground=ACCENT_BLUE)

        msg = (
            f"A new update is available for {self.config.project_name}!\n\n"
            f"Current Version: {self.config.version_name} ({self.config.version_date})\n"
            f"New Version:     {new_version_name} ({new_version_date})\n\n"
            f"Files excluded via 'Exclude-File' will be preserved.\n"
            f"Do you want to download and install this update now?"
        )

        confirm = messagebox.askyesno("Update Available", msg, parent=self)
        if not confirm:
            self.lbl_status.config(text="Update cancelled by user.", foreground=MUTED_TEXT)
            return

        # Disable buttons during update
        self._set_buttons_state("disabled")
        self.lbl_status.config(text="Starting update...")

        def update_worker():
            try:
                downloaded_paths = []
                for idx, (url, fname) in enumerate(download_urls):
                    self.after(0, lambda f=fname: self.lbl_status.config(text=f"Downloading {f}..."))

                    def on_dl_progress(done, total, filename):
                        if total > 0:
                            pct = int((done / total) * 100)
                            self.after(0, lambda p=pct: self.progress_bar.config(value=p))

                    fpath = self.engine.download_file(url, fname, progress_callback=on_dl_progress)
                    downloaded_paths.append(fpath)

                self.after(0, lambda: self.lbl_status.config(text="Applying update & preserving excluded files..."))

                # Perform installation with is_update=True
                self.engine.install_or_update(
                    downloaded_paths,
                    is_update=True,
                    progress_callback=lambda m: self.after(0, lambda msg=m: self.lbl_status.config(text=msg))
                )

                # Update config with new version info
                self.config.version_name = new_version_name
                self.config.version_date = new_version_date
                self.config.save()

                # If managed, update registry
                if self.is_managed:
                    registry = ManagedRegistry()
                    registry.register_instance(
                        project_dir=self.project_dir,
                        updater_path=self.updater_exe_path,
                        project_name=self.config.project_name,
                        git_url=self.config.git_url,
                        version_name=new_version_name,
                        version_date=new_version_date,
                        update_type=self.config.update_type
                    )

                self.after(0, lambda: self._on_update_success(new_version_name))

            except Exception as e:
                self.after(0, lambda err=str(e): self._on_update_failed(err))
            finally:
                self.after(0, lambda: self._set_buttons_state("normal"))

        threading.Thread(target=update_worker, daemon=True).start()

    def _set_buttons_state(self, state: str):
        self.btn_check_update.config(state=state)
        self.btn_exclude_file.config(state=state)
        self.btn_settings.config(state=state)
        self.btn_run_script.config(state=state)
        self.btn_close.config(state=state)

    def _on_update_success(self, version_name: str):
        self.lbl_status.config(text=f"Successfully updated to {version_name}!", foreground=SUCCESS_GREEN)
        self.progress_bar["value"] = 100
        self._refresh_info_labels()

        # If option is enabled, run update-done.bat in the terminal
        if self.config.run_script_after_update:
            run_done_script(self.project_dir)

        messagebox.showinfo(
            "Update Complete",
            f"Successfully updated {self.config.project_name} to {version_name}!",
            parent=self
        )

    def _on_update_failed(self, error_msg: str):
        self.lbl_status.config(text="Update failed.", foreground="#D83B01")
        messagebox.showerror("Update Error", f"An error occurred while updating:\n{error_msg}", parent=self)

    def _on_run_bat_script(self):
        run_done_script(self.project_dir)

    def _on_exclude_file(self):
        ExcludeFilesDialog(self, self.config, on_save_callback=self._refresh_info_labels)

    def _on_settings(self):
        SettingsDialog(self, self.config, on_save_callback=self._refresh_info_labels)
