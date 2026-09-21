import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Any, Callable, Optional, Set
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


class AssetPickerDialog(tk.Toplevel):
    """
    Dialog prompted when release assets cannot be automatically matched across versions
    or when repository maintainers rename their release files.
    Allows user to select which file(s) to download for this and future updates.
    """
    def __init__(
        self,
        parent: tk.Widget,
        project_name: str,
        release_tag: str,
        available_assets: List[Dict[str, Any]],
        preselected_names: Optional[List[str]] = None,
        unresolved_names: Optional[List[str]] = None,
        on_confirm: Optional[Callable[[List[str]], None]] = None
    ):
        super().__init__(parent)
        self.project_name = project_name
        self.release_tag = release_tag
        self.available_assets = available_assets
        self.preselected_names = set(preselected_names or [])
        self.unresolved_names = unresolved_names or []
        self.on_confirm = on_confirm

        self.title(f"Select Assets - {self.project_name} ({self.release_tag})")
        self.geometry("640x500")
        self.minsize(560, 420)
        self.transient(parent)
        self.grab_set()

        apply_win7_theme(self)

        # Center on screen
        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
            y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.asset_vars: Dict[str, tk.BooleanVar] = {}
        self.confirmed = False

        self._build_ui()

    def _build_ui(self):
        # Header banner
        create_win7_header(
            self,
            f"Select Assets for {self.project_name}",
            f"Release {self.release_tag} contains new or renamed files. Choose which to download."
        )

        # Bottom navigation bar (docked first so it is never hidden)
        bottom_bar = ttk.Frame(self, padding=(18, 12))
        bottom_bar.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        self.btn_cancel = ttk.Button(bottom_bar, text="Cancel", width=12, command=self.destroy)
        self.btn_cancel.pack(side="right", padx=(8, 0))

        self.btn_ok = ttk.Button(bottom_bar, text="Download Selected", width=18, style="Accent.TButton", command=self._on_ok)
        self.btn_ok.pack(side="right")

        # Main content
        container = ttk.Frame(self, padding=(20, 14))
        container.pack(fill="both", expand=True, side="top")

        if self.unresolved_names:
            unresolved_str = ", ".join(self.unresolved_names)
            warn_lbl = ttk.Label(
                container,
                text=f"Note: Previously selected file '{unresolved_str}' could not be matched automatically. Please select the replacement file below:",
                foreground="#D83B01",
                font=("Segoe UI", 9, "bold"),
                wraplength=580
            )
            warn_lbl.pack(anchor="w", pady=(0, 8))

        # Convenience toolbar
        tools_frame = ttk.Frame(container)
        tools_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(tools_frame, text=f"Available Files in {self.release_tag}:", style="Bold.TLabel").pack(side="left")

        btn_none = ttk.Button(tools_frame, text="Deselect All", command=self._deselect_all)
        btn_none.pack(side="right")

        btn_all = ttk.Button(tools_frame, text="Select All", command=self._select_all)
        btn_all.pack(side="right", padx=(0, 6))

        # Scrollable checklist box
        list_frame = ttk.Frame(container)
        list_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_frame, bg=PANEL_BG, highlightthickness=1, highlightbackground=LIGHT_BORDER)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner_frame = ttk.Frame(canvas, style="White.TFrame", padding=6)

        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", _on_inner_configure)
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel support
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Populate asset checkboxes
        for asset in self.available_assets:
            name = asset["name"]
            size_mb = f"({asset['size'] / (1024*1024):.1f} MB)" if asset.get("size") else ""
            
            # Default checked if in preselected or if only 1 asset available
            is_checked = (name in self.preselected_names) or (len(self.available_assets) == 1)
            var = tk.BooleanVar(value=is_checked)
            self.asset_vars[name] = var

            chk = ttk.Checkbutton(
                inner_frame,
                text=f"{name} {size_mb}",
                variable=var,
                style="White.TCheckbutton"
            )
            chk.pack(anchor="w", pady=2)

    def _select_all(self):
        for v in self.asset_vars.values():
            v.set(True)

    def _deselect_all(self):
        for v in self.asset_vars.values():
            v.set(False)

    def _on_ok(self):
        selected = [name for name, var in self.asset_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("Selection Required", "Please select at least one asset to download.", parent=self)
            return

        self.confirmed = True
        self.destroy()

        if self.on_confirm:
            self.on_confirm(selected)
