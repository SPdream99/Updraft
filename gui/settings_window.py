import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from core.config import UpdaterConfig
from core.theme import (
    apply_win7_theme,
    create_win7_header,
    FONT_NORMAL,
    FONT_BOLD,
    BG_COLOR,
    LIGHT_BORDER,
)


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
        self.geometry("460x320")
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

        body_frame = ttk.Frame(self, padding=(20, 16))
        body_frame.pack(fill="both", expand=True)

        group = ttk.LabelFrame(body_frame, text="Completion Options", padding=(15, 12))
        group.pack(fill="both", expand=True)

        self.var_open = tk.BooleanVar(value=self.config.open_when_done)
        self.chk_open = ttk.Checkbutton(
            group,
            text="Open it when done (Open 'main' folder after completion)",
            variable=self.var_open
        )
        self.chk_open.pack(anchor="w", pady=(4, 6))

        self.var_delete = tk.BooleanVar(value=self.config.delete_compressed)
        self.chk_delete = ttk.Checkbutton(
            group,
            text="Delete the compressed file when done? (Removes downloaded zip/tar)",
            variable=self.var_delete
        )
        self.chk_delete.pack(anchor="w", pady=(4, 6))

        self.var_run_script = tk.BooleanVar(value=getattr(self.config, "run_script_after_update", False))
        self.chk_run_script = ttk.Checkbutton(
            group,
            text="Run script after update complete (Runs update-done.bat in terminal)",
            variable=self.var_run_script
        )
        self.chk_run_script.pack(anchor="w", pady=(4, 4))

        # Bottom buttons bar
        bottom_frame = ttk.Frame(self, padding=(16, 12))
        bottom_frame.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        btn_close = ttk.Button(bottom_frame, text="Close", width=12, command=self.destroy)
        btn_close.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(bottom_frame, text="Save and Close", width=14, command=self._save_and_close)
        btn_save.pack(side="right")

    def _save_and_close(self):
        self.config.open_when_done = self.var_open.get()
        self.config.delete_compressed = self.var_delete.get()
        self.config.run_script_after_update = self.var_run_script.get()
        self.config.save()

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
