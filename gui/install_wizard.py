import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, List, Dict, Any

from core.config import (
    UpdaterConfig,
    ManagedRegistry,
    SHORTCUT_DEPTH_OPTIONS,
    SHORTCUT_DEPTH_MAP,
    get_depth_label_from_level,
)
from core.downloader import UpdateEngine, is_archive
from core.git_client import GitHubClient, parse_git_url, GitRepoInfo
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


class InstallWizard(tk.Tk):
    def __init__(
        self,
        current_dir: str,
        updater_exe_path: str,
        is_managed: bool = False,
        on_install_complete: Optional[Callable[[str], None]] = None
    ):
        super().__init__()
        self.current_dir = os.path.abspath(current_dir)
        self.updater_exe_path = os.path.abspath(updater_exe_path)
        self.is_managed = is_managed
        self.on_install_complete = on_install_complete

        mode_label = "Managed Updater" if is_managed else "Simple Updater"
        self.title(f"{mode_label} - Setup & Installation Wizard")
        self.geometry("680x640")
        self.minsize(600, 520)

        apply_win7_theme(self)

        # Center on screen
        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
            y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        # Wizard state
        self.current_step = 1
        self.repo_info: Optional[GitRepoInfo] = None
        self.git_client: Optional[GitHubClient] = None
        self.repo_details: Dict[str, Any] = {}
        self.latest_release: Optional[Dict[str, Any]] = None
        self.latest_commit: Optional[Dict[str, Any]] = None

        self.var_update_type = tk.StringVar(value="release")
        self.asset_check_vars: Dict[str, tk.BooleanVar] = {}

        self.var_open_done = tk.BooleanVar(value=True)
        self.var_delete_compressed = tk.BooleanVar(value=True)
        self.var_run_script = tk.BooleanVar(value=False)
        self.var_create_shortcuts = tk.BooleanVar(value=True)
        self.var_create_folders = tk.BooleanVar(value=True)
        self.var_shortcut_depth = tk.StringVar(value=SHORTCUT_DEPTH_OPTIONS[1])

        self._build_ui()
        self._show_step(1)

    def _build_ui(self):
        # Header banner
        self.header_frame = create_win7_header(
            self,
            "Install Project Updater",
            "Set up automatic updates from a Git or GitHub repository"
        )

        # Bottom navigation bar (packed side="bottom" FIRST so it is NEVER hidden)
        self.bottom_bar = ttk.Frame(self, padding=(20, 12))
        self.bottom_bar.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        # Main container for steps (fills remaining space in the middle)
        self.container = ttk.Frame(self, padding=(24, 16))
        self.container.pack(fill="both", expand=True, side="top")

        self.btn_cancel = ttk.Button(self.bottom_bar, text="Cancel", width=12, command=self.destroy)
        self.btn_cancel.pack(side="right", padx=(8, 0))

        self.btn_next = ttk.Button(self.bottom_bar, text="Next >", width=14, command=self._on_next)
        self.btn_next.pack(side="right")

        self.btn_back = ttk.Button(self.bottom_bar, text="< Back", width=12, command=self._on_back)
        self.btn_back.pack(side="right", padx=(0, 8))

    def _clear_container(self):
        for child in self.container.winfo_children():
            child.destroy()

    def _show_step(self, step: int):
        self.current_step = step
        self._clear_container()

        if step == 1:
            self.btn_back.config(state="disabled")
            self.btn_next.config(text="Next >", state="normal")
            self._render_step_1_git_link()
        elif step == 2:
            self.btn_back.config(state="normal")
            self.btn_next.config(text="Next >", state="normal")
            self._render_step_2_type_selection()
        elif step == 3:
            self.btn_back.config(state="normal")
            self.btn_next.config(text="Install", state="normal")
            self._render_step_3_options()
        elif step == 4:
            self.btn_back.config(state="disabled")
            self.btn_next.config(state="disabled")
            self.btn_cancel.config(state="disabled")
            self._render_step_4_progress()

    # --- STEP 1: Git Link ---
    def _render_step_1_git_link(self):
        ttk.Label(
            self.container,
            text="Enter the Git Repository URL:",
            style="Bold.TLabel"
        ).pack(anchor="w", pady=(4, 6))

        self.entry_git = ttk.Entry(self.container, font=FONT_NORMAL)
        self.entry_git.pack(fill="x", pady=(0, 4))
        self.entry_git.focus_set()

        hint = ttk.Label(
            self.container,
            text="Examples: https://github.com/owner/repo or owner/repo",
            foreground=MUTED_TEXT,
            font=("Segoe UI", 8)
        )
        hint.pack(anchor="w", pady=(0, 16))

        self.lbl_step1_status = ttk.Label(self.container, text="", foreground=ACCENT_BLUE)
        self.lbl_step1_status.pack(anchor="w", pady=(8, 0))

    # --- STEP 2: Update Type & Asset Selection ---
    def _render_step_2_type_selection(self):
        repo_name = self.repo_details.get("name", "Repository")
        ttk.Label(
            self.container,
            text=f"Repository: {self.repo_info.full_name}",
            style="Bold.TLabel"
        ).pack(anchor="w", pady=(0, 8))

        group_type = ttk.LabelFrame(self.container, text="Choose Update Source", padding=12)
        group_type.pack(fill="x", pady=(0, 12))

        has_releases = bool(self.latest_release and self.latest_release.get("assets"))

        # Radio: Release page
        rad_release = ttk.Checkbutton(
            group_type,
            text="Release Page (Download compiled binaries or release assets)",
            variable=self.var_update_type,
            onvalue="release",
            offvalue="source",
            command=self._on_update_type_changed
        )
        rad_release.pack(anchor="w", pady=(0, 4))

        # Radio: Source code
        rad_source = ttk.Checkbutton(
            group_type,
            text="Source Code (Download latest repository source code archive)",
            variable=self.var_update_type,
            onvalue="source",
            offvalue="release",
            command=self._on_update_type_changed
        )
        rad_source.pack(anchor="w", pady=(4, 4))

        if not has_releases:
            self.var_update_type.set("source")
            rad_release.config(state="disabled")
            ttk.Label(
                group_type,
                text="* Note: No published release assets found for this repository. Source code mode selected.",
                font=("Segoe UI", 8),
                foreground=MUTED_TEXT
            ).pack(anchor="w", pady=(4, 0))
        else:
            self.var_update_type.set("release")

        # Container for asset checklist (if release mode)
        self.asset_frame = ttk.LabelFrame(self.container, text="Select Assets to Download", padding=10)
        self.asset_frame.pack(fill="both", expand=True)

        self._refresh_asset_list()

    def _on_update_type_changed(self):
        self._refresh_asset_list()

    def _refresh_asset_list(self):
        for w in self.asset_frame.winfo_children():
            w.destroy()

        if self.var_update_type.get() == "source":
            commit_text = "Latest Commit: " + (self.latest_commit.get("name", "Latest commit") if self.latest_commit else "Loading...")
            date_text = "Commit Date: " + (self.latest_commit.get("date", "") if self.latest_commit else "")
            ttk.Label(self.asset_frame, text=commit_text, style="Bold.TLabel").pack(anchor="w", pady=(4, 2))
            ttk.Label(self.asset_frame, text=date_text, foreground=MUTED_TEXT).pack(anchor="w")
            ttk.Label(
                self.asset_frame,
                text="The entire project source code will be downloaded and extracted directly into 'main/'.",
                wraplength=480,
                pady=10
            ).pack(anchor="w")
            return

        # Release mode
        rel_tag = self.latest_release.get("tag_name", "") if self.latest_release else "Release"
        rel_date = self.latest_release.get("published_at", "") if self.latest_release else ""
        ttk.Label(self.asset_frame, text=f"Latest Release: {rel_tag} ({rel_date})", style="Bold.TLabel").pack(anchor="w", pady=(0, 8))

        assets = self.latest_release.get("assets", []) if self.latest_release else []
        if not assets:
            ttk.Label(self.asset_frame, text="No assets attached to this release.").pack(anchor="w")
            return

        canvas = tk.Canvas(self.asset_frame, bg=PANEL_BG, highlightthickness=1, highlightbackground=LIGHT_BORDER)
        scrollbar = ttk.Scrollbar(self.asset_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="White.TFrame", padding=6)

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.asset_check_vars.clear()
        for asset in assets:
            name = asset["name"]
            size_mb = f"({asset['size'] / (1024*1024):.1f} MB)" if asset.get("size") else ""
            var = tk.BooleanVar(value=True)  # Default all checked
            self.asset_check_vars[name] = var

            chk = ttk.Checkbutton(
                scrollable_frame,
                text=f"{name} {size_mb}",
                variable=var,
                style="White.TCheckbutton"
            )
            chk.pack(anchor="w", pady=2)

    # --- STEP 3: Options ---
    def _render_step_3_options(self):
        ttk.Label(
            self.container,
            text="Configure Completion Options:",
            style="Bold.TLabel"
        ).pack(anchor="w", pady=(0, 10))

        group = ttk.LabelFrame(self.container, text="Post-Download Settings", padding=(16, 14))
        group.pack(fill="x", pady=(0, 16))

        chk_open = ttk.Checkbutton(
            group,
            text="Open it when done (Open 'main' folder in Windows Explorer)",
            variable=self.var_open_done
        )
        chk_open.pack(anchor="w", pady=(4, 6))

        chk_del = ttk.Checkbutton(
            group,
            text="Delete the compressed file when done? (Removes temporary downloaded archives)",
            variable=self.var_delete_compressed
        )
        chk_del.pack(anchor="w", pady=(4, 6))

        chk_script = ttk.Checkbutton(
            group,
            text="Run script after update complete (Runs update-done.bat in terminal)",
            variable=self.var_run_script
        )
        chk_script.pack(anchor="w", pady=(4, 6))

        chk_shortcuts = ttk.Checkbutton(
            group,
            text="Create shortcuts for executables, links, and Python scripts",
            variable=self.var_create_shortcuts,
            command=self._toggle_shortcut_options
        )
        chk_shortcuts.pack(anchor="w", pady=(4, 2))

        self.chk_create_folders = ttk.Checkbutton(
            group,
            text="Include shortcuts to subfolders (e.g. saves, docs, tools)",
            variable=self.var_create_folders,
            state="normal" if self.var_create_shortcuts.get() else "disabled"
        )
        self.chk_create_folders.pack(anchor="w", padx=(24, 0), pady=(0, 2))

        depth_frame = ttk.Frame(group)
        depth_frame.pack(fill="x", padx=(24, 0), pady=(0, 4))

        ttk.Label(depth_frame, text="Subfolder depth:").pack(side="left", padx=(0, 8))
        self.cbo_shortcut_depth = ttk.Combobox(
            depth_frame,
            textvariable=self.var_shortcut_depth,
            values=SHORTCUT_DEPTH_OPTIONS,
            state="readonly" if self.var_create_shortcuts.get() else "disabled",
            width=32
        )
        self.cbo_shortcut_depth.pack(side="left")

        summary_group = ttk.LabelFrame(self.container, text="Installation Summary", padding=(16, 12))
        summary_group.pack(fill="both", expand=True)

        proj_folder_name = self.repo_details.get("name", self.repo_info.repo)
        ttk.Label(summary_group, text=f"Target Folder: {proj_folder_name}").pack(anchor="w", pady=2)
        ttk.Label(summary_group, text=f"Source Type: {self.var_update_type.get().capitalize()}").pack(anchor="w", pady=2)

        ver = self.latest_release.get("tag_name") if self.var_update_type.get() == "release" else self.latest_commit.get("short_sha")
        ttk.Label(summary_group, text=f"Initial Version: {ver}").pack(anchor="w", pady=2)

        shortcut_info = self.var_shortcut_depth.get() if self.var_create_shortcuts.get() else "Disabled"
        ttk.Label(summary_group, text=f"Shortcuts: {shortcut_info}").pack(anchor="w", pady=2)

    def _toggle_shortcut_options(self):
        state = "normal" if self.var_create_shortcuts.get() else "disabled"
        cbo_state = "readonly" if self.var_create_shortcuts.get() else "disabled"
        if hasattr(self, "chk_create_folders"):
            self.chk_create_folders.config(state=state)
        if hasattr(self, "cbo_shortcut_depth"):
            self.cbo_shortcut_depth.config(state=cbo_state)

    # --- STEP 4: Progress ---
    def _render_step_4_progress(self):
        ttk.Label(self.container, text="Installing project...", style="Bold.TLabel").pack(anchor="w", pady=(4, 8))

        self.progress_bar = ttk.Progressbar(self.container, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(8, 8))

        self.lbl_progress_status = ttk.Label(self.container, text="Preparing folders...", foreground=ACCENT_BLUE)
        self.lbl_progress_status.pack(anchor="w", pady=(4, 0))

        # Start background installation thread
        threading.Thread(target=self._run_installation, daemon=True).start()

    # --- Actions & Navigation ---
    def _on_next(self):
        if self.current_step == 1:
            git_url = self.entry_git.get().strip()
            if not git_url:
                messagebox.showwarning("Input Required", "Please enter a Git repository URL.", parent=self)
                return

            repo_info = parse_git_url(git_url)
            if not repo_info:
                messagebox.showerror("Invalid URL", "Could not parse repository URL. Please enter a valid GitHub URL.", parent=self)
                return

            self.repo_info = repo_info
            self.git_client = GitHubClient(repo_info)
            self.lbl_step1_status.config(text="Connecting to repository...")
            self.btn_next.config(state="disabled")

            def query_repo():
                try:
                    self.repo_details = self.git_client.get_repo_details()
                    self.latest_release = self.git_client.get_latest_release()
                    try:
                        self.latest_commit = self.git_client.get_latest_commit()
                    except Exception:
                        self.latest_commit = {"sha": "latest", "short_sha": "latest", "name": "Latest commit", "date": ""}
                    self.after(0, lambda: self._show_step(2))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Connection Error", f"Failed to fetch repository information:\n{str(e)}", parent=self))
                    self.after(0, lambda: self.lbl_step1_status.config(text=""))
                    self.after(0, lambda: self.btn_next.config(state="normal"))

            threading.Thread(target=query_repo, daemon=True).start()

        elif self.current_step == 2:
            if self.var_update_type.get() == "release":
                selected = [name for name, var in self.asset_check_vars.items() if var.get()]
                if not selected and self.latest_release and self.latest_release.get("assets"):
                    messagebox.showwarning("Selection Required", "Please select at least one asset to download.", parent=self)
                    return
            self._show_step(3)

        elif self.current_step == 3:
            self._show_step(4)

    def _on_back(self):
        if self.current_step > 1:
            self._show_step(self.current_step - 1)

    def _run_installation(self):
        try:
            repo_name = self.repo_details.get("name", self.repo_info.repo)
            
            # Determine destination project folder:
            # If current directory basename matches repo_name, use current directory.
            # Otherwise, create folder named after the project in current directory.
            current_base = os.path.basename(self.current_dir)
            if current_base.lower() == repo_name.lower():
                project_dir = self.current_dir
            else:
                project_dir = os.path.join(self.current_dir, repo_name)
                os.makedirs(project_dir, exist_ok=True)

            self.after(0, lambda: self.lbl_progress_status.config(text="Setting up project directories..."))

            # Move or copy updater executable to project directory if not already there
            target_exe = os.path.join(project_dir, os.path.basename(self.updater_exe_path))
            if os.path.abspath(self.updater_exe_path) != os.path.abspath(target_exe):
                try:
                    shutil.copy2(self.updater_exe_path, target_exe)
                except Exception as e:
                    print(f"Note: Could not copy executable: {e}")

            # Initialize config in project_dir
            config = UpdaterConfig(project_dir)
            config.project_name = repo_name
            config.git_url = self.repo_details.get("html_url", self.repo_info.original_url)
            config.update_type = self.var_update_type.get()
            config.open_when_done = self.var_open_done.get()
            config.delete_compressed = self.var_delete_compressed.get()
            config.run_script_after_update = self.var_run_script.get()
            config.create_shortcuts = self.var_create_shortcuts.get()
            config.create_folder_shortcuts = self.var_create_folders.get()
            config.shortcut_folder_level = SHORTCUT_DEPTH_MAP.get(self.var_shortcut_depth.get(), 1)

            # Record version information
            if config.update_type == "source":
                config.version_name = self.latest_commit.get("name", self.latest_commit.get("short_sha", "latest"))
                config.version_date = self.latest_commit.get("date", "")
                download_urls = [(self.latest_commit.get("zip_url"), f"{repo_name}-source.zip")]
            else:
                config.version_name = self.latest_release.get("name") or self.latest_release.get("tag_name", "Release")
                config.version_date = self.latest_release.get("published_at", "")
                selected_names = [name for name, var in self.asset_check_vars.items() if var.get()]
                config.selected_assets = selected_names

                download_urls = []
                for a in self.latest_release.get("assets", []):
                    if a["name"] in selected_names:
                        download_urls.append((a["download_url"], a["name"]))

            config.save()

            # Managed registration
            if self.is_managed:
                registry = ManagedRegistry()
                registry.register_instance(
                    project_dir=project_dir,
                    updater_path=target_exe,
                    project_name=repo_name,
                    git_url=config.git_url,
                    version_name=config.version_name,
                    version_date=config.version_date,
                    update_type=config.update_type
                )

            # Download files
            engine = UpdateEngine(project_dir)
            downloaded_paths = []
            total_items = len(download_urls)

            for idx, (url, fname) in enumerate(download_urls):
                self.after(0, lambda f=fname: self.lbl_progress_status.config(text=f"Downloading {f}..."))
                
                def on_progress(done, total, filename):
                    if total > 0:
                        pct = int((done / total) * 100)
                        self.after(0, lambda p=pct, fn=filename: self._update_download_progress(p, fn))

                fpath = engine.download_file(url, fname, progress_callback=on_progress)
                downloaded_paths.append(fpath)

            # Extract and install
            self.after(0, lambda: self.lbl_progress_status.config(text="Extracting and organizing files..."))
            engine.install_or_update(
                downloaded_paths,
                is_update=False,
                progress_callback=lambda msg: self.after(0, lambda m=msg: self.lbl_progress_status.config(text=m))
            )

            self.after(0, lambda: self._on_install_finished(project_dir))

        except Exception as e:
            self.after(0, lambda err=str(e): self._on_install_error(err))

    def _update_download_progress(self, pct: int, filename: str):
        self.progress_bar["value"] = pct
        self.lbl_progress_status.config(text=f"Downloading {filename} ({pct}%)")

    def _on_install_finished(self, project_dir: str):
        messagebox.showinfo(
            "Installation Complete",
            f"Project successfully installed in:\n{project_dir}\n\nShortcuts have been created in the project folder.",
            parent=self
        )
        self.destroy()
        if self.on_install_complete:
            self.on_install_complete(project_dir)

    def _on_install_error(self, error_msg: str):
        messagebox.showerror(
            "Installation Failed",
            f"An error occurred during installation:\n{error_msg}",
            parent=self
        )
        self.btn_cancel.config(state="normal")
        self.lbl_progress_status.config(text="Installation failed.", foreground="#D83B01")
