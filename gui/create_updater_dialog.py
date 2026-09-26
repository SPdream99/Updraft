import os
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Optional, Callable

from core.theme import (
    apply_win7_theme,
    create_win7_header,
    FONT_NORMAL,
    FONT_BOLD,
    PANEL_BG,
    LIGHT_BORDER,
    MUTED_TEXT,
    SUCCESS_GREEN,
    ACCENT_BLUE,
)
from core.self_updater import check_updater_conflict


class CreateUpdaterDialog(tk.Toplevel):
    """
    Dialog allowing the user to select a folder for deploying a new ManagedUpdater.exe.
    Performs real-time conflict checking and notifies user before launching.
    """
    def __init__(
        self,
        parent: tk.Tk,
        registry: Optional[object] = None,
        on_create_callback: Optional[Callable[[str], None]] = None
    ):
        super().__init__(parent)
        self.registry = registry
        self.on_create_callback = on_create_callback

        self.title("Create Managed Updater")
        self.geometry("660x420")
        self.minsize(580, 380)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        apply_win7_theme(self)

        # Center on parent window
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.folder_var = tk.StringVar()
        self.folder_var.trace_add("write", lambda *args: self._validate_path())

        self._build_ui()
        self._validate_path()

    def _build_ui(self):
        create_win7_header(
            self,
            "Create Managed Updater",
            "Deploy a managed updater into a project folder and configure updates"
        )

        # Bottom buttons (packed first)
        bottom_bar = ttk.Frame(self, padding=(20, 12))
        bottom_bar.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        self.btn_cancel = ttk.Button(bottom_bar, text="Cancel", command=self.destroy)
        self.btn_cancel.pack(side="right", padx=(6, 0))

        self.btn_create = ttk.Button(
            bottom_bar,
            text="Create & Launch",
            style="Accent.TButton",
            command=self._on_confirm,
            state="disabled"
        )
        self.btn_create.pack(side="right")

        # Main content
        content = ttk.Frame(self, padding=(24, 16))
        content.pack(fill="both", expand=True)

        lbl_instruct = ttk.Label(
            content,
            text="Select the project directory where you want to create a Managed Updater:",
            font=FONT_NORMAL
        )
        lbl_instruct.pack(anchor="w", pady=(0, 8))

        # Folder selector row
        row = ttk.Frame(content)
        row.pack(fill="x", pady=(0, 16))

        self.entry_folder = ttk.Entry(row, textvariable=self.folder_var, font=FONT_NORMAL)
        self.entry_folder.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ttk.Button(row, text="Browse...", command=self._on_browse)
        btn_browse.pack(side="right")

        # Conflict & Validation Status Box
        status_box = ttk.LabelFrame(content, text="Conflict & Validation Status", padding=(14, 12))
        status_box.pack(fill="both", expand=True, pady=(0, 10))

        self.lbl_status = ttk.Label(
            status_box,
            text="Please select a target project folder.",
            font=FONT_NORMAL,
            foreground=MUTED_TEXT,
            wraplength=500,
            justify="left"
        )
        self.lbl_status.pack(anchor="w", fill="x", pady=(2, 8))

        # Informative note
        lbl_info = ttk.Label(
            content,
            text="ManagedUpdater.exe will be copied into the folder and executed. "
                 "If project setup is completed, it will be registered automatically. "
                 "If setup is cancelled or fails, the executable will be removed.",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT,
            wraplength=520,
            justify="left"
        )
        lbl_info.pack(anchor="w", fill="x")

    def _on_browse(self):
        folder = filedialog.askdirectory(title="Select Target Project Folder", parent=self)
        if folder:
            self.folder_var.set(os.path.normpath(folder))

    def _validate_path(self):
        path = self.folder_var.get().strip()
        if not path:
            self.lbl_status.config(
                text="Please select or browse to a target folder.",
                foreground=MUTED_TEXT
            )
            self.btn_create.config(state="disabled")
            return

        has_conflict, reason = check_updater_conflict(path, self.registry)
        if has_conflict:
            self.lbl_status.config(
                text=f"{reason}",
                foreground="#D83B01"
            )
            self.btn_create.config(state="disabled")
        else:
            self.lbl_status.config(
                text="No conflicts detected. Folder is ready for updater deployment.",
                foreground=SUCCESS_GREEN
            )
            self.btn_create.config(state="normal")

    def _on_confirm(self):
        path = self.folder_var.get().strip()
        has_conflict, reason = check_updater_conflict(path, self.registry)
        if has_conflict:
            self._validate_path()
            return

        target_folder = os.path.normpath(os.path.abspath(path))
        self.destroy()
        if self.on_create_callback:
            self.on_create_callback(target_folder)
