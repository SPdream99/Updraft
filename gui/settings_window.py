import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from core.config import (
    UpdaterConfig,
    SHORTCUT_DEPTH_OPTIONS,
    SHORTCUT_DEPTH_MAP,
    SHORTCUT_LAYOUT_OPTIONS,
    SHORTCUT_LAYOUT_MAP,
    get_depth_label_from_level,
    get_layout_label_from_id,
)
from core.theme import (
    apply_win7_theme,
    create_win7_header,
    FONT_NORMAL,
    FONT_BOLD,
    BG_COLOR,
    LIGHT_BORDER,
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
        self.geometry("520x480")
        self.minsize(460, 420)
        self.resizable(False, False)
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

        self._build_ui()

    def _build_ui(self):
        self.configure(bg=BG_COLOR)

        sub = "Configure global defaults for all managed projects" if self.is_global else "Configure actions performed after updating or installing"
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

        body_frame = ttk.Frame(self, padding=(20, 16))
        body_frame.pack(fill="both", expand=True, side="top")

        group = ttk.LabelFrame(body_frame, text="Options & Startup", padding=(15, 12))
        group.pack(fill="both", expand=True)

        self.var_open = tk.BooleanVar(value=self.config.open_when_done)
        self.chk_open = ttk.Checkbutton(
            group,
            text="Open it when done (Open 'main' folder after completion)",
            variable=self.var_open
        )
        self.chk_open.pack(anchor="w", pady=(3, 4))

        self.var_delete = tk.BooleanVar(value=self.config.delete_compressed)
        self.chk_delete = ttk.Checkbutton(
            group,
            text="Delete the compressed file when done? (Removes downloaded zip/tar)",
            variable=self.var_delete
        )
        self.chk_delete.pack(anchor="w", pady=(3, 4))

        self.var_run_script = tk.BooleanVar(value=getattr(self.config, "run_script_after_update", False))
        self.chk_run_script = ttk.Checkbutton(
            group,
            text="Run script after update complete (Runs update-done.bat in terminal)",
            variable=self.var_run_script
        )
        self.chk_run_script.pack(anchor="w", pady=(3, 4))

        self.var_create_shortcuts = tk.BooleanVar(value=getattr(self.config, "create_shortcuts", True))
        self.chk_create_shortcuts = ttk.Checkbutton(
            group,
            text="Create shortcuts for executables, links, and Python scripts",
            variable=self.var_create_shortcuts,
            command=self._toggle_shortcut_options
        )
        self.chk_create_shortcuts.pack(anchor="w", pady=(3, 2))

        self.var_create_folders = tk.BooleanVar(value=getattr(self.config, "create_folder_shortcuts", True))
        self.chk_create_folders = ttk.Checkbutton(
            group,
            text="Include shortcuts to subfolders (e.g. saves, docs, tools)",
            variable=self.var_create_folders,
            state="normal" if self.var_create_shortcuts.get() else "disabled"
        )
        self.chk_create_folders.pack(anchor="w", padx=(20, 0), pady=(0, 2))

        depth_frame = ttk.Frame(group)
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

        startup_val = getattr(self.config, "auto_update_on_startup", False if self.is_global else True)
        self.var_startup = tk.BooleanVar(value=startup_val)
        startup_text = (
            "Check and update all managed projects on Windows startup"
            if self.is_global
            else "Include this project in startup auto-updates"
        )
        self.chk_startup = ttk.Checkbutton(
            group,
            text=startup_text,
            variable=self.var_startup
        )
        self.chk_startup.pack(anchor="w", pady=(3, 4))

        self.var_self_update = tk.BooleanVar(value=getattr(self.config, "auto_update_self", True))
        self_update_text = (
            "Auto-update Updraft and all managed instances when a new release is available"
            if self.is_global
            else "Auto-update Updraft app when a new release is available"
        )
        self.chk_self_update = ttk.Checkbutton(
            group,
            text=self_update_text,
            variable=self.var_self_update
        )
        self.chk_self_update.pack(anchor="w", pady=(3, 3))

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
