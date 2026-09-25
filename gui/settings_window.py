import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any, List

from core.config import (
    UpdaterConfig,
    SHORTCUT_DEPTH_OPTIONS,
    SHORTCUT_DEPTH_MAP,
    SHORTCUT_LAYOUT_OPTIONS,
    SHORTCUT_LAYOUT_MAP,
    get_depth_label_from_level,
    get_layout_label_from_id,
)
from core.git_client import parse_git_url, GitHubClient
from core.theme import (
    apply_win7_theme,
    create_win7_header,
    FONT_NORMAL,
    FONT_BOLD,
    BG_COLOR,
    PANEL_BG,
    LIGHT_BORDER,
    MUTED_TEXT,
    ACCENT_BLUE,
)
from gui.shortcut_dialog import ShortcutCustomizerDialog


class SettingsDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        config: UpdaterConfig,
        on_save_callback: Optional[Callable[[], None]] = None,
        is_global: bool = False
    ):
        super().__init__(parent)
        self.config = config
        self.on_save_callback = on_save_callback
        self.is_global = is_global

        title_text = "Global Updater Settings" if is_global else f"Settings - {config.project_name or 'Simple Updater'}"
        self.title(title_text)
        self.geometry("600x560")
        self.minsize(540, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # Center dialog relative to parent
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.asset_check_vars: Dict[str, tk.BooleanVar] = {}
        self.cached_release_info: Optional[Dict[str, Any]] = None

        self._build_ui()

    def _build_ui(self):
        self.configure(bg=BG_COLOR)

        sub = "Configure global defaults for all managed projects" if self.is_global else "Configure project options, shortcuts, and release files"
        create_win7_header(self, "Updater Settings", sub)

        # Bottom buttons bar (docked first so it is never hidden)
        bottom_frame = ttk.Frame(self, padding=(16, 12))
        bottom_frame.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        btn_close = ttk.Button(bottom_frame, text="Close", width=12, command=self.destroy)
        btn_close.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(bottom_frame, text="Save and Close", width=14, command=self._save_and_close)
        btn_save.pack(side="right")

        body_frame = ttk.Frame(self, padding=(16, 12))
        body_frame.pack(fill="both", expand=True, side="top")

        if self.is_global:
            # Global settings: just options & startup
            group = ttk.LabelFrame(body_frame, text="Global Options & Startup", padding=(15, 12))
            group.pack(fill="both", expand=True)
            self._build_general_options(group)
        else:
            # Per-project settings: Notebook with General & Release Files tabs
            self.notebook = ttk.Notebook(body_frame)
            self.notebook.pack(fill="both", expand=True)

            self.tab_general = ttk.Frame(self.notebook, padding=(14, 12))
            self.tab_release = ttk.Frame(self.notebook, padding=(14, 12))

            self.notebook.add(self.tab_general, text="Options & Automation")
            self.notebook.add(self.tab_release, text="Release Files")

            self._build_general_options(self.tab_general)
            self._build_release_files_tab(self.tab_release)

    def _build_general_options(self, parent: ttk.Frame):
        # Post-download options
        group = ttk.LabelFrame(parent, text="Post-Download Settings", padding=(14, 10))
        group.pack(fill="x", pady=(0, 10))

        self.var_open = tk.BooleanVar(value=self.config.open_when_done)
        self.chk_open = ttk.Checkbutton(
            group,
            text="Open it when done (Open 'main' folder after completion)",
            variable=self.var_open
        )
        self.chk_open.pack(anchor="w", pady=(2, 3))

        self.var_delete = tk.BooleanVar(value=self.config.delete_compressed)
        self.chk_delete = ttk.Checkbutton(
            group,
            text="Delete the compressed file when done? (Removes downloaded zip/tar)",
            variable=self.var_delete
        )
        self.chk_delete.pack(anchor="w", pady=(2, 3))

        self.var_run_script = tk.BooleanVar(value=getattr(self.config, "run_script_after_update", False))
        self.chk_run_script = ttk.Checkbutton(
            group,
            text="Run script after update complete (Runs update-done.bat in terminal)",
            variable=self.var_run_script
        )
        self.chk_run_script.pack(anchor="w", pady=(2, 3))

        # Shortcuts options
        grp_shortcuts = ttk.LabelFrame(parent, text="Shortcut Settings", padding=(14, 10))
        grp_shortcuts.pack(fill="x", pady=(0, 10))

        self.var_create_shortcuts = tk.BooleanVar(value=getattr(self.config, "create_shortcuts", True))
        self.chk_create_shortcuts = ttk.Checkbutton(
            grp_shortcuts,
            text="Create shortcuts for executables, links, and Python scripts",
            variable=self.var_create_shortcuts,
            command=self._toggle_shortcut_options
        )
        self.chk_create_shortcuts.pack(anchor="w", pady=(2, 2))

        self.var_create_folders = tk.BooleanVar(value=getattr(self.config, "create_folder_shortcuts", True))
        self.chk_create_folders = ttk.Checkbutton(
            grp_shortcuts,
            text="Include shortcuts to subfolders (e.g. saves, docs, tools)",
            variable=self.var_create_folders,
            state="normal" if self.var_create_shortcuts.get() else "disabled"
        )
        self.chk_create_folders.pack(anchor="w", padx=(20, 0), pady=(0, 2))

        depth_frame = ttk.Frame(grp_shortcuts)
        depth_frame.pack(fill="x", padx=(20, 0), pady=(0, 4))

        ttk.Label(depth_frame, text="Subfolder depth:").pack(side="left", padx=(0, 6))
        current_level = getattr(self.config, "shortcut_folder_level", 1)
        self.var_shortcut_depth = tk.StringVar(value=get_depth_label_from_level(current_level))
        self.cbo_shortcut_depth = ttk.Combobox(
            depth_frame,
            textvariable=self.var_shortcut_depth,
            values=SHORTCUT_DEPTH_OPTIONS,
            state="readonly" if self.var_create_shortcuts.get() else "disabled",
            width=28
        )
        self.cbo_shortcut_depth.pack(side="left", padx=(0, 8))

        if not self.is_global:
            btn_custom_shortcuts = ttk.Button(
                depth_frame,
                text="Customize...",
                command=self._open_shortcut_customizer
            )
            btn_custom_shortcuts.pack(side="left")

        # Startup and auto-update
        grp_system = ttk.LabelFrame(parent, text="Updates & System", padding=(14, 10))
        grp_system.pack(fill="x", pady=(0, 10))

        startup_val = getattr(self.config, "auto_update_on_startup", False if self.is_global else True)
        self.var_startup = tk.BooleanVar(value=startup_val)
        startup_text = (
            "Check and update all managed projects on Windows startup"
            if self.is_global
            else "Include this project in startup auto-updates"
        )
        self.chk_startup = ttk.Checkbutton(
            grp_system,
            text=startup_text,
            variable=self.var_startup
        )
        self.chk_startup.pack(anchor="w", pady=(2, 3))

        self.var_self_update = tk.BooleanVar(value=getattr(self.config, "auto_update_self", True))
        self_update_text = (
            "Auto-update Updraft and all managed instances when a new release is available"
            if self.is_global
            else "Auto-update Updraft app when a new release is available"
        )
        self.chk_self_update = ttk.Checkbutton(
            grp_system,
            text=self_update_text,
            variable=self.var_self_update
        )
        self.chk_self_update.pack(anchor="w", pady=(2, 2))

        # Quick link to Release Files tab if in project mode
        if not self.is_global:
            summary_frame = ttk.Frame(parent)
            summary_frame.pack(fill="x", pady=(4, 0))

            cur_type = getattr(self.config, "update_type", "release")
            cur_assets = getattr(self.config, "selected_assets", [])
            if cur_type == "source":
                summary_text = "Update Source: Source Code (Entire repository archive)"
            else:
                count_str = f"{len(cur_assets)} files selected" if cur_assets else "All files selected"
                summary_text = f"Update Source: Release Page ({count_str})"

            self.lbl_src_summary = ttk.Label(summary_frame, text=summary_text, foreground=MUTED_TEXT, font=("Segoe UI", 9))
            self.lbl_src_summary.pack(side="left", padx=(4, 8))

            btn_switch_tab = ttk.Button(
                summary_frame,
                text="Choose Release Files...",
                command=lambda: self.notebook.select(self.tab_release)
            )
            btn_switch_tab.pack(side="left")

    def _build_release_files_tab(self, parent: ttk.Frame):
        # 1. Update Source Selector
        grp_source = ttk.LabelFrame(parent, text="Choose Update Source", padding=(12, 10))
        grp_source.pack(fill="x", pady=(0, 10))

        current_type = getattr(self.config, "update_type", "release")
        self.var_update_type = tk.StringVar(value=current_type)

        rad_release = ttk.Radiobutton(
            grp_source,
            text="Release Page (Download compiled binaries or release assets)",
            value="release",
            variable=self.var_update_type,
            command=self._on_update_type_changed
        )
        rad_release.pack(anchor="w", pady=(2, 3))

        rad_source = ttk.Radiobutton(
            grp_source,
            text="Source Code (Download latest repository source code archive)",
            value="source",
            variable=self.var_update_type,
            command=self._on_update_type_changed
        )
        rad_source.pack(anchor="w", pady=(2, 2))

        # 2. Container for Asset Checklist
        self.grp_assets = ttk.LabelFrame(parent, text="Release Files to Download", padding=(12, 10))
        self.grp_assets.pack(fill="both", expand=True)

        # Header info inside grp_assets
        header_bar = ttk.Frame(self.grp_assets)
        header_bar.pack(fill="x", pady=(0, 6))

        self.lbl_release_info = ttk.Label(header_bar, text="Release: Loading...", style="Bold.TLabel")
        self.lbl_release_info.pack(side="left", padx=(0, 8))

        btn_refresh = ttk.Button(header_bar, text="Refresh from GitHub", width=18, command=self._fetch_release_assets_thread)
        btn_refresh.pack(side="right")

        # Action toolbar: Select All / Deselect All
        self.action_toolbar = ttk.Frame(self.grp_assets)
        self.action_toolbar.pack(fill="x", pady=(0, 6))

        btn_select_all = ttk.Button(
            self.action_toolbar,
            text="Select All",
            width=12,
            command=self._select_all_assets
        )
        btn_select_all.pack(side="left", padx=(0, 6))

        btn_deselect_all = ttk.Button(
            self.action_toolbar,
            text="Deselect All",
            width=12,
            command=self._deselect_all_assets
        )
        btn_deselect_all.pack(side="left", padx=(0, 8))

        self.lbl_asset_count = ttk.Label(
            self.action_toolbar,
            text="",
            foreground=MUTED_TEXT,
            font=("Segoe UI", 9)
        )
        self.lbl_asset_count.pack(side="left")

        # Scrollable asset list container
        self.list_container = ttk.Frame(self.grp_assets)
        self.list_container.pack(fill="both", expand=True)

        self.source_info_frame = ttk.Frame(self.grp_assets)
        ttk.Label(
            self.source_info_frame,
            text="Source Code mode selected.\n\nThe full project repository archive will be downloaded and extracted directly into 'main/'.\nNo specific release assets are required.",
            wraplength=480,
            foreground=MUTED_TEXT
        ).pack(anchor="w", pady=10)

        # Populate initial assets from config or start fetch
        self._populate_initial_assets()
        self._on_update_type_changed()
        self._fetch_release_assets_thread()

    def _populate_initial_assets(self):
        """Displays currently saved selected assets immediately before GitHub response arrives."""
        saved_assets = getattr(self.config, "selected_assets", [])
        if saved_assets:
            assets_list = [{"name": name, "size": 0} for name in saved_assets]
            tag = getattr(self.config, "version_name", "Current")
            date = getattr(self.config, "version_date", "")
            self._render_assets_checklist(tag, date, assets_list, preselected=set(saved_assets))

    def _on_update_type_changed(self):
        if self.var_update_type.get() == "source":
            self.action_toolbar.pack_forget()
            self.list_container.pack_forget()
            self.source_info_frame.pack(fill="both", expand=True)
            self.lbl_release_info.config(text="Source Code Mode (Latest Commit)")
        else:
            self.source_info_frame.pack_forget()
            self.action_toolbar.pack(fill="x", pady=(0, 6))
            self.list_container.pack(fill="both", expand=True)
            if self.cached_release_info:
                tag = self.cached_release_info.get("tag_name", "Latest")
                date = self.cached_release_info.get("published_at", "")
                self.lbl_release_info.config(text=f"Latest Release: {tag} ({date})")
            else:
                self.lbl_release_info.config(text=f"Release: {self.config.version_name or 'Loading...'}")

    def _fetch_release_assets_thread(self):
        self.lbl_release_info.config(text="Connecting to GitHub...")
        threading.Thread(target=self._fetch_release_worker, daemon=True).start()

    def _fetch_release_worker(self):
        git_url = getattr(self.config, "git_url", "")
        repo_info = parse_git_url(git_url)
        if not repo_info:
            self.after(0, lambda: self.lbl_release_info.config(text="Invalid Git repository URL"))
            return

        client = GitHubClient(repo_info)
        try:
            rel = client.get_latest_release()
            self.after(0, lambda: self._on_release_fetched(rel))
        except Exception as e:
            self.after(0, lambda: self.lbl_release_info.config(text=f"GitHub connection failed: {e}"))

    def _on_release_fetched(self, release: Optional[Dict[str, Any]]):
        if not release:
            self.lbl_release_info.config(text="No releases found for this repository.")
            return

        self.cached_release_info = release
        tag = release.get("tag_name", "Release")
        date = release.get("published_at", "")
        assets = release.get("assets", [])

        saved_selected = set(getattr(self.config, "selected_assets", []))
        self._render_assets_checklist(tag, date, assets, preselected=saved_selected)

    def _render_assets_checklist(self, tag: str, date: str, assets: List[Dict[str, Any]], preselected: set):
        self.lbl_release_info.config(text=f"Latest Release: {tag} ({date})" if date else f"Latest Release: {tag}")

        for w in self.list_container.winfo_children():
            w.destroy()

        if not assets:
            ttk.Label(self.list_container, text="No downloadable assets attached to this release.").pack(anchor="w", pady=10)
            self.asset_check_vars.clear()
            self._update_asset_count()
            return

        canvas = tk.Canvas(self.list_container, bg=PANEL_BG, highlightthickness=1, highlightbackground=LIGHT_BORDER)
        scrollbar = ttk.Scrollbar(self.list_container, orient="vertical", command=canvas.yview)
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

            # If preselected is non-empty, match it; if preselected was empty, default checked
            is_checked = (name in preselected) if preselected else True
            var = tk.BooleanVar(value=is_checked)
            self.asset_check_vars[name] = var

            chk = ttk.Checkbutton(
                scrollable_frame,
                text=f"{name} {size_mb}",
                variable=var,
                command=self._update_asset_count,
                style="White.TCheckbutton"
            )
            chk.pack(anchor="w", pady=2)

        self._update_asset_count()

    def _select_all_assets(self):
        for v in self.asset_check_vars.values():
            v.set(True)
        self._update_asset_count()

    def _deselect_all_assets(self):
        for v in self.asset_check_vars.values():
            v.set(False)
        self._update_asset_count()

    def _update_asset_count(self):
        if hasattr(self, "lbl_asset_count") and self.lbl_asset_count.winfo_exists():
            total = len(self.asset_check_vars)
            selected = sum(1 for v in self.asset_check_vars.values() if v.get())
            self.lbl_asset_count.config(text=f"({selected} of {total} selected)")

    def _toggle_shortcut_options(self):
        state = "normal" if self.var_create_shortcuts.get() else "disabled"
        cbo_state = "readonly" if self.var_create_shortcuts.get() else "disabled"
        if hasattr(self, "chk_create_folders"):
            self.chk_create_folders.config(state=state)
        if hasattr(self, "cbo_shortcut_depth"):
            self.cbo_shortcut_depth.config(state=cbo_state)

    def _open_shortcut_customizer(self):
        # Save current options to config first
        self.config.create_shortcuts = self.var_create_shortcuts.get()
        self.config.create_folder_shortcuts = self.var_create_folders.get()
        self.config.shortcut_folder_level = SHORTCUT_DEPTH_MAP.get(self.var_shortcut_depth.get(), 1)
        ShortcutCustomizerDialog(self, self.config, on_saved_callback=self._on_customizer_saved)

    def _on_customizer_saved(self):
        self.var_create_folders.set(self.config.create_folder_shortcuts)
        self.var_shortcut_depth.set(get_depth_label_from_level(self.config.shortcut_folder_level))

    def _save_and_close(self):
        if not self.is_global:
            up_type = self.var_update_type.get()
            self.config.update_type = up_type
            if up_type == "release":
                selected = [name for name, var in self.asset_check_vars.items() if var.get()]
                if self.asset_check_vars and not selected:
                    messagebox.showwarning(
                        "Selection Required",
                        "Please select at least one release file to download, or select Source Code mode.",
                        parent=self
                    )
                    return
                if selected:
                    self.config.selected_assets = selected

        self.config.open_when_done = self.var_open.get()
        self.config.delete_compressed = self.var_delete.get()
        self.config.run_script_after_update = self.var_run_script.get()
        self.config.create_shortcuts = self.var_create_shortcuts.get()
        self.config.create_folder_shortcuts = self.var_create_folders.get()
        self.config.shortcut_folder_level = SHORTCUT_DEPTH_MAP.get(self.var_shortcut_depth.get(), 1)
        self.config.auto_update_on_startup = self.var_startup.get()
        self.config.auto_update_self = self.var_self_update.get()
        self.config.save()

        if self.is_global:
            from core.startup import set_startup_enabled
            set_startup_enabled(self.var_startup.get())

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
