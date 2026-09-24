import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Dict, Any, Optional, Callable, List
from core.config import (
    UpdaterConfig,
    SHORTCUT_DEPTH_OPTIONS,
    SHORTCUT_DEPTH_MAP,
    SHORTCUT_LAYOUT_OPTIONS,
    SHORTCUT_LAYOUT_MAP,
    get_depth_label_from_level,
    get_layout_label_from_id,
)
from core.downloader import discover_project_shortcuts, UpdateEngine
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


class ShortcutCustomizerDialog(tk.Toplevel):
    """
    Dialog allowing per-project customization of shortcuts:
    - Enable/disable categories (executables, python scripts, web/docs, subfolders)
    - Subfolder depth level
    - Prefix and output folder layout
    - Per-item toggles and custom shortcut names
    """
    def __init__(
        self,
        parent: tk.Widget,
        config: UpdaterConfig,
        on_saved_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.config = config
        self.on_saved_callback = on_saved_callback
        self.project_dir = config.directory
        self.engine = UpdateEngine(self.project_dir)

        proj_title = config.project_name or os.path.basename(self.project_dir)
        self.title(f"Customize Shortcuts - {proj_title}")
        self.geometry("820x620")
        self.minsize(720, 520)
        self.transient(parent)
        self.grab_set()

        # Temporary working config variables
        self.var_inc_exe = tk.BooleanVar(value=getattr(self.config, "shortcut_include_executables", True))
        self.var_inc_py = tk.BooleanVar(value=getattr(self.config, "shortcut_include_python", True))
        self.var_inc_doc = tk.BooleanVar(value=getattr(self.config, "shortcut_include_docs", True))
        self.var_inc_folder = tk.BooleanVar(value=getattr(self.config, "create_folder_shortcuts", True))

        current_depth = getattr(self.config, "shortcut_folder_level", 1)
        self.var_depth = tk.StringVar(value=get_depth_label_from_level(current_depth))

        current_layout = getattr(self.config, "shortcut_layout", "root")
        self.var_layout = tk.StringVar(value=get_layout_label_from_id(current_layout))

        self.var_prefix = tk.StringVar(value=getattr(self.config, "shortcut_prefix", ""))

        # Working copy of shortcut rules: Dict[rel_path, {'enabled': bool, 'custom_name': str}]
        self.rules_copy: Dict[str, Dict[str, Any]] = self.config.get_shortcut_rules().copy()

        # Discovered items cache: List[Dict[str, Any]]
        self.discovered_items: List[Dict[str, Any]] = []
        self.item_tree_map: Dict[str, Dict[str, Any]] = {}

        self._build_ui()
        self._refresh_candidates()

    def _build_ui(self):
        self.configure(bg=BG_COLOR)

        create_win7_header(
            self,
            "Customize Project Shortcuts",
            "Configure categories, subfolder depth, custom names, and layout for this project"
        )

        # Bottom buttons bar
        bottom_frame = ttk.Frame(self, padding=(16, 10))
        bottom_frame.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        btn_cancel = ttk.Button(bottom_frame, text="Cancel", width=10, command=self.destroy)
        btn_cancel.pack(side="right", padx=(6, 0))

        btn_save = ttk.Button(bottom_frame, text="Save Settings", width=14, command=self._save_and_close)
        btn_save.pack(side="right", padx=(6, 0))

        btn_create = ttk.Button(
            bottom_frame,
            text="Create Shortcuts Now",
            style="Accent.TButton",
            command=self._on_create_now
        )
        btn_create.pack(side="left")

        # Main scrollable or structured content
        main_frame = ttk.Frame(self, padding=(14, 10))
        main_frame.pack(fill="both", expand=True)

        # Group 1: General Options (Categories, Depth, Prefix, Layout)
        opt_group = ttk.LabelFrame(main_frame, text="Shortcut Rules & Categories", padding=(12, 10))
        opt_group.pack(fill="x", pady=(0, 10))

        # Checkboxes row
        chk_row = ttk.Frame(opt_group)
        chk_row.pack(fill="x", pady=(0, 8))

        ttk.Checkbutton(
            chk_row,
            text="Executables (.exe, .bat)",
            variable=self.var_inc_exe,
            command=self._refresh_candidates
        ).pack(side="left", padx=(0, 14))

        ttk.Checkbutton(
            chk_row,
            text="Python (.py launchers)",
            variable=self.var_inc_py,
            command=self._refresh_candidates
        ).pack(side="left", padx=(0, 14))

        ttk.Checkbutton(
            chk_row,
            text="Web & Docs (.html, .url)",
            variable=self.var_inc_doc,
            command=self._refresh_candidates
        ).pack(side="left", padx=(0, 14))

        ttk.Checkbutton(
            chk_row,
            text="Subfolders (.lnk)",
            variable=self.var_inc_folder,
            command=self._refresh_candidates
        ).pack(side="left")

        # Configuration Grid (Depth, Layout, Prefix)
        grid_frame = ttk.Frame(opt_group)
        grid_frame.pack(fill="x")

        # Depth
        ttk.Label(grid_frame, text="Subfolder Depth:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        cbo_depth = ttk.Combobox(
            grid_frame,
            textvariable=self.var_depth,
            values=SHORTCUT_DEPTH_OPTIONS,
            state="readonly",
            width=36
        )
        cbo_depth.grid(row=0, column=1, sticky="w", padx=(8, 16), pady=4)
        cbo_depth.bind("<<ComboboxSelected>>", lambda e: self._refresh_candidates())

        # Layout
        ttk.Label(grid_frame, text="Shortcut Location:", style="Bold.TLabel").grid(row=0, column=2, sticky="w", pady=4)
        cbo_layout = ttk.Combobox(
            grid_frame,
            textvariable=self.var_layout,
            values=SHORTCUT_LAYOUT_OPTIONS,
            state="readonly",
            width=26
        )
        cbo_layout.grid(row=0, column=3, sticky="w", padx=(8, 0), pady=4)

        # Prefix
        ttk.Label(grid_frame, text="Name Prefix:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        txt_prefix = ttk.Entry(grid_frame, textvariable=self.var_prefix, width=38)
        txt_prefix.grid(row=1, column=1, sticky="w", padx=(8, 16), pady=4)
        txt_prefix.bind("<KeyRelease>", lambda e: self._refresh_candidates())

        ttk.Label(
            grid_frame,
            text="(Optional prefix for generated shortcuts, e.g. 'Run ')",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT
        ).grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=4)

        # Group 2: Discovered Candidates Preview & Individual Rules
        items_group = ttk.LabelFrame(main_frame, text="Discovered Shortcuts Preview & Overrides", padding=(12, 10))
        items_group.pack(fill="both", expand=True)

        toolbar = ttk.Frame(items_group)
        toolbar.pack(fill="x", pady=(0, 6))

        ttk.Label(
            toolbar,
            text="Double-click or press Space on an item to toggle it. Use 'Rename' to assign a custom shortcut name.",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT
        ).pack(side="left")

        btn_reset_rules = ttk.Button(toolbar, text="Reset to Defaults", command=self._reset_rules)
        btn_reset_rules.pack(side="right")

        btn_rename = ttk.Button(toolbar, text="Rename...", command=self._on_rename_selected)
        btn_rename.pack(side="right", padx=(0, 6))

        # Treeview
        tree_frame = ttk.Frame(items_group)
        tree_frame.pack(fill="both", expand=True)

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("type", "enabled", "output"),
            selectmode="browse",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
        )
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)

        self.tree.heading("#0", text="Target Item (in main/)", anchor="w")
        self.tree.heading("type", text="Type", anchor="center")
        self.tree.heading("enabled", text="Create?", anchor="center")
        self.tree.heading("output", text="Generated Shortcut / Launcher Name", anchor="w")

        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("type", width=90, anchor="center", stretch=False)
        self.tree.column("enabled", width=90, anchor="center", stretch=False)
        self.tree.column("output", width=240, stretch=True)

        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<space>", self._on_tree_space)

        # Status label
        self.lbl_status = ttk.Label(items_group, text="", font=("Segoe UI", 8), foreground=MUTED_TEXT)
        self.lbl_status.pack(anchor="w", pady=(4, 0))

    def _sync_temp_config(self):
        """Temporarily sets properties on self.config for candidate discovery."""
        self.config.create_folder_shortcuts = self.var_inc_folder.get()
        self.config.shortcut_folder_level = SHORTCUT_DEPTH_MAP.get(self.var_depth.get(), 1)
        self.config.shortcut_include_executables = self.var_inc_exe.get()
        self.config.shortcut_include_python = self.var_inc_py.get()
        self.config.shortcut_include_docs = self.var_inc_doc.get()
        self.config.shortcut_prefix = self.var_prefix.get()

        # Update in-memory rules
        if "ShortcutRules" not in self.config.config:
            self.config.config.add_section("ShortcutRules")
        else:
            self.config.config["ShortcutRules"].clear()

        for rel, data in self.rules_copy.items():
            en_val = "1" if data.get("enabled", True) else "0"
            c_name = data.get("custom_name", "")
            self.config.config["ShortcutRules"][rel] = f"{en_val}|{c_name}"

    def _refresh_candidates(self):
        self._sync_temp_config()
        self.discovered_items = discover_project_shortcuts(self.project_dir, self.config)

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_tree_map.clear()

        type_icons = {
            "folder": "📁",
            "binary": "⚙️",
            "python": "🐍",
            "doc": "🌐",
        }

        type_labels = {
            "folder": "Folder",
            "binary": "Executable",
            "python": "Python Bat",
            "doc": "Web/Doc",
        }

        enabled_count = 0
        for item in self.discovered_items:
            rel = item["rel_path"]
            icon = type_icons.get(item["type"], "📄")
            t_label = type_labels.get(item["type"], item["type"].capitalize())
            check = "[✓] Yes" if item["enabled"] else "[  ] No"
            if item["enabled"]:
                enabled_count += 1

            display_target = f"{icon} {rel}"
            tree_id = self.tree.insert(
                "",
                "end",
                text=display_target,
                values=(t_label, check, item["output_filename"])
            )
            self.item_tree_map[tree_id] = item

        self.lbl_status.config(
            text=f"Total Candidates: {len(self.discovered_items)} | Enabled Shortcuts: {enabled_count}"
        )

    def _on_tree_click(self, event):
        tree_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if tree_id and col == "#2":  # Enabled column
            self._toggle_item(tree_id)

    def _on_tree_double_click(self, event):
        tree_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not tree_id:
            return
        if col == "#3":  # Output name column
            self._on_rename_selected()
        else:
            self._toggle_item(tree_id)

    def _on_tree_space(self, event):
        sel = self.tree.selection()
        if sel:
            self._toggle_item(sel[0])

    def _toggle_item(self, tree_id: str):
        item = self.item_tree_map.get(tree_id)
        if not item:
            return

        rel = item["rel_path"]
        current_en = item["enabled"]
        new_en = not current_en

        # Update in rules copy
        rule = self.rules_copy.get(rel, {"custom_name": item["custom_name"]})
        rule["enabled"] = new_en
        self.rules_copy[rel] = rule

        self._refresh_candidates()

        # Re-select the item
        for tid, itm in self.item_tree_map.items():
            if itm["rel_path"] == rel:
                self.tree.selection_set(tid)
                self.tree.see(tid)
                break

    def _on_rename_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Rename", "Please select a shortcut to rename.", parent=self)
            return

        item = self.item_tree_map.get(sel[0])
        if not item:
            return

        rel = item["rel_path"]
        cur_name = item["effective_name"]

        new_name = simpledialog.askstring(
            "Custom Shortcut Name",
            f"Enter custom name for:\n{rel}\n\n(Leave empty to reset to default prefix/name):",
            initialvalue=cur_name,
            parent=self
        )

        if new_name is not None:
            new_name = new_name.strip()
            rule = self.rules_copy.get(rel, {"enabled": item["enabled"]})
            rule["custom_name"] = new_name
            self.rules_copy[rel] = rule

            self._refresh_candidates()

            for tid, itm in self.item_tree_map.items():
                if itm["rel_path"] == rel:
                    self.tree.selection_set(tid)
                    self.tree.see(tid)
                    break

    def _reset_rules(self):
        confirm = messagebox.askyesno(
            "Reset Defaults",
            "Reset all individual shortcut overrides back to defaults?",
            parent=self
        )
        if confirm:
            self.rules_copy.clear()
            self._refresh_candidates()

    def _save_settings(self):
        self.config.create_folder_shortcuts = self.var_inc_folder.get()
        self.config.shortcut_folder_level = SHORTCUT_DEPTH_MAP.get(self.var_depth.get(), 1)
        self.config.shortcut_include_executables = self.var_inc_exe.get()
        self.config.shortcut_include_python = self.var_inc_py.get()
        self.config.shortcut_include_docs = self.var_inc_doc.get()
        self.config.shortcut_layout = SHORTCUT_LAYOUT_MAP.get(self.var_layout.get(), "root")
        self.config.shortcut_prefix = self.var_prefix.get().strip()

        # Save rules to config
        if "ShortcutRules" not in self.config.config:
            self.config.config.add_section("ShortcutRules")
        else:
            self.config.config["ShortcutRules"].clear()

        for rel, data in self.rules_copy.items():
            en_val = "1" if data.get("enabled", True) else "0"
            c_name = data.get("custom_name", "")
            self.config.config["ShortcutRules"][rel] = f"{en_val}|{c_name}"

        self.config.save()

    def _save_and_close(self):
        self._save_settings()
        if self.on_saved_callback:
            self.on_saved_callback()
        self.destroy()

    def _on_create_now(self):
        self._save_settings()
        try:
            created = self.engine.create_shortcuts()
            count = len(created)
            dest_desc = "Shortcuts folder" if self.config.shortcut_layout == "shortcuts_folder" else "project root"
            if count > 0:
                names = "\n".join(f"• {os.path.basename(p)}" for p in created[:12])
                if count > 12:
                    names += f"\n...and {count - 12} more"
                msg = f"Successfully created {count} shortcut/launcher file(s) in {dest_desc}:\n\n{names}"
                messagebox.showinfo("Shortcuts Created", msg, parent=self)
            else:
                messagebox.showinfo(
                    "No Shortcuts Created",
                    f"No matching files or folders were found or enabled to create shortcuts for.",
                    parent=self
                )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create shortcuts:\n{e}", parent=self)
