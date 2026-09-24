import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, Optional, Callable, List
from core.config import UpdaterConfig
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


def format_size(size_bytes: int) -> str:
    """Format bytes into human readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


FILTER_OPTIONS = [
    "All Files",
    "Excluded Only",
    "Included Only",
    "Update Available",
    "Executables (*.exe, *.bat, *.cmd)",
    "Config & Data (*.ini, *.json, *.xml, *.cfg)",
    "Python & Scripts (*.py, *.ps1, *.js)",
]

SORT_OPTIONS = [
    "Name (A to Z)",
    "Name (Z to A)",
    "Folder (A to Z)",
    "Folder (Z to A)",
    "Status (Excluded First)",
    "Status (Included First)",
    "Size (Smallest First)",
    "Size (Largest First)",
]

VIEW_OPTIONS = [
    "Hierarchical (Folder Tree)",
    "Flat List (All Files)",
]

EXECUTABLE_EXTS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".com", ".wsf"}
CONFIG_EXTS = {".ini", ".json", ".xml", ".cfg", ".yaml", ".yml", ".txt", ".conf", ".toml", ".properties"}
SCRIPT_EXTS = {".py", ".pyw", ".ps1", ".js", ".sh", ".bash", ".bat", ".cmd", ".vbs"}


def matches_filter(
    item: Dict[str, Any],
    filter_mode: str,
    excluded_map: Dict[str, Any],
    is_older_fn: Callable[[str, str], bool]
) -> bool:
    """Check if file matches the chosen filter criteria."""
    rel_path = item["rel_path"]
    is_ex = rel_path in excluded_map

    if filter_mode == "Excluded Only":
        return is_ex
    elif filter_mode == "Included Only":
        return not is_ex
    elif filter_mode == "Update Available":
        if not is_ex:
            return False
        info = excluded_map[rel_path]
        return is_older_fn(info.get("version_name", ""), info.get("version_date", ""))
    elif "Executables" in filter_mode:
        return item["ext"] in EXECUTABLE_EXTS
    elif "Config" in filter_mode:
        return item["ext"] in CONFIG_EXTS
    elif "Scripts" in filter_mode:
        return item["ext"] in SCRIPT_EXTS
    return True


def matches_search(item: Dict[str, Any], query: str) -> bool:
    """Check if query is in file name or relative path."""
    if not query:
        return True
    q = query.lower().strip()
    return q in item["name"].lower() or q in item["rel_path"].lower()


def get_sort_key(item: Dict[str, Any], sort_key: str, excluded_map: Dict[str, Any]):
    """Returns a comparable key for sorting file dicts."""
    if sort_key == "name":
        return item["name"].lower()
    elif sort_key == "folder":
        return item["rel_dir"].lower()
    elif sort_key == "status":
        # Excluded first: 0, Included: 1
        return 0 if item["rel_path"] in excluded_map else 1
    elif sort_key == "size":
        return item["size_bytes"]
    elif sort_key == "ext":
        return item["ext"].lower()
    return item["name"].lower()


class ExcludeFilesDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        config: UpdaterConfig,
        on_save_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.config = config
        self.on_save_callback = on_save_callback
        self.project_dir = config.directory
        self.main_dir = os.path.join(self.project_dir, "main")
        self.engine = UpdateEngine(self.project_dir)

        self.title(f"Exclude Files from Updates - {config.project_name or 'Simple Updater'}")
        self.geometry("900x600")
        self.minsize(780, 500)
        self.transient(parent)
        self.grab_set()

        # In-memory working copy of excluded files:
        # Dict[rel_path_norm: {'version_name': str, 'version_date': str}]
        self.excluded_map: Dict[str, Dict[str, str]] = self.config.get_excluded_files().copy()

        # All discovered physical files in main/: List[Dict[str, Any]]
        self.all_files: List[Dict[str, Any]] = []

        # Filter, Search, Sort state
        self.var_search = tk.StringVar()
        self.var_filter = tk.StringVar(value=FILTER_OPTIONS[0])
        self.var_sort = tk.StringVar(value=SORT_OPTIONS[0])
        self.var_view = tk.StringVar(value=VIEW_OPTIONS[0])

        self.sort_column = "name"
        self.sort_asc = True

        # Map tree item ID to item metadata
        self.item_meta: Dict[str, Dict[str, Any]] = {}
        self.currently_selected_rel_path: Optional[str] = None

        self._scan_all_files()
        self._build_ui()
        self._apply_filters_and_render()

    def _scan_all_files(self):
        """Scans all files within self.main_dir and populates self.all_files."""
        self.all_files.clear()
        if not os.path.exists(self.main_dir):
            return

        for root, dirs, filenames in os.walk(self.main_dir):
            # Exclude standard hidden files like .git
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                full_path = os.path.join(root, fn)
                rel_path = os.path.relpath(full_path, self.main_dir).replace("\\", "/")
                rel_dir = os.path.relpath(root, self.main_dir).replace("\\", "/")
                if rel_dir == ".":
                    rel_dir = "(root)"

                try:
                    stat = os.stat(full_path)
                    size_bytes = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    size_bytes = 0
                    mtime = 0

                _, ext = os.path.splitext(fn)
                ext = ext.lower()

                self.all_files.append({
                    "name": fn,
                    "rel_path": rel_path,
                    "full_path": full_path,
                    "rel_dir": rel_dir,
                    "ext": ext,
                    "size_bytes": size_bytes,
                    "size_str": format_size(size_bytes),
                    "mtime": mtime,
                })

    def _build_ui(self):
        self.configure(bg=BG_COLOR)

        create_win7_header(
            self,
            "Exclude Files from Updates",
            "Search, filter, and choose files to protect from being overwritten during project updates"
        )

        # Bottom buttons bar (docked first to bottom so it is NEVER hidden)
        bottom_frame = ttk.Frame(self, padding=(16, 10))
        bottom_frame.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        btn_close = ttk.Button(bottom_frame, text="Close", width=12, command=self.destroy)
        btn_close.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(bottom_frame, text="Save and Close", width=14, command=self._save_and_close)
        btn_save.pack(side="right")

        # Paned Window (Left: File Explorer Tree & Controls; Right: File Details & Batch Actions)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=14, pady=10)

        # Left Frame: Search, Filter, Sort toolbar + TreeView
        left_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=3)

        # Toolbar Frame
        toolbar_frame = ttk.Frame(left_frame)
        toolbar_frame.pack(fill="x", pady=(0, 6))

        # Row 1: Search bar
        search_row = ttk.Frame(toolbar_frame)
        search_row.pack(fill="x", pady=(0, 4))

        ttk.Label(search_row, text="Search:", style="Bold.TLabel").pack(side="left", padx=(0, 6))
        self.txt_search = ttk.Entry(search_row, textvariable=self.var_search)
        self.txt_search.pack(side="left", fill="x", expand=True)
        self.txt_search.bind("<KeyRelease>", lambda e: self._apply_filters_and_render())

        btn_clear = ttk.Button(search_row, text="✕ Clear", width=7, command=self._clear_search)
        btn_clear.pack(side="left", padx=(4, 0))

        # Row 2: Filter, Sort & View controls
        ctrl_row = ttk.Frame(toolbar_frame)
        ctrl_row.pack(fill="x", pady=(2, 2))

        ttk.Label(ctrl_row, text="Filter:").pack(side="left", padx=(0, 4))
        self.cbo_filter = ttk.Combobox(
            ctrl_row,
            textvariable=self.var_filter,
            values=FILTER_OPTIONS,
            state="readonly",
            width=16
        )
        self.cbo_filter.pack(side="left", padx=(0, 8))
        self.cbo_filter.bind("<<ComboboxSelected>>", lambda e: self._apply_filters_and_render())

        ttk.Label(ctrl_row, text="Sort:").pack(side="left", padx=(0, 4))
        self.cbo_sort = ttk.Combobox(
            ctrl_row,
            textvariable=self.var_sort,
            values=SORT_OPTIONS,
            state="readonly",
            width=18
        )
        self.cbo_sort.pack(side="left", padx=(0, 8))
        self.cbo_sort.bind("<<ComboboxSelected>>", self._on_sort_combobox_changed)

        ttk.Label(ctrl_row, text="View:").pack(side="left", padx=(0, 4))
        self.cbo_view = ttk.Combobox(
            ctrl_row,
            textvariable=self.var_view,
            values=VIEW_OPTIONS,
            state="readonly",
            width=15
        )
        self.cbo_view.pack(side="left")
        self.cbo_view.bind("<<ComboboxSelected>>", lambda e: self._apply_filters_and_render())

        # Treeview + Scrollbars
        tree_container = ttk.Frame(left_frame)
        tree_container.pack(fill="both", expand=True)

        tree_scroll_y = ttk.Scrollbar(tree_container, orient="vertical")
        tree_scroll_x = ttk.Scrollbar(tree_container, orient="horizontal")

        self.tree = ttk.Treeview(
            tree_container,
            columns=("folder", "status", "size"),
            selectmode="browse",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
        )
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)

        self._update_column_headers()

        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<space>", self._on_tree_space)

        # Summary Bar under tree
        self.lbl_summary = ttk.Label(
            left_frame,
            text="Loading files...",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT
        )
        self.lbl_summary.pack(anchor="w", pady=(4, 0))

        # Right Frame: File details & Batch actions
        right_frame = ttk.Frame(paned, padding=8)
        paned.add(right_frame, weight=2)

        # Details Box
        right_group = ttk.LabelFrame(right_frame, text="File Information", padding=(12, 10))
        right_group.pack(fill="x", pady=(0, 10))

        ttk.Label(right_group, text="File Path:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_file_path = ttk.Label(right_group, text="(Select a file on the left)", wraplength=230)
        self.lbl_file_path.pack(anchor="w", pady=(0, 6))

        ttk.Label(right_group, text="Folder:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_file_folder = ttk.Label(right_group, text="-", wraplength=230)
        self.lbl_file_folder.pack(anchor="w", pady=(0, 6))

        ttk.Label(right_group, text="File Size:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_file_size = ttk.Label(right_group, text="-")
        self.lbl_file_size.pack(anchor="w", pady=(0, 6))

        ttk.Label(right_group, text="Status:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_status = ttk.Label(right_group, text="-")
        self.lbl_status.pack(anchor="w", pady=(0, 6))

        ttk.Label(right_group, text="Version Name:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_ver_name = ttk.Label(right_group, text="-")
        self.lbl_ver_name.pack(anchor="w", pady=(0, 6))

        ttk.Label(right_group, text="Version Date:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_ver_date = ttk.Label(right_group, text="-")
        self.lbl_ver_date.pack(anchor="w", pady=(0, 10))

        # Update button for single excluded file
        self.btn_update_file = ttk.Button(
            right_group,
            text="Update This File",
            style="Accent.TButton",
            command=self._on_update_single_file,
            state="disabled"
        )
        self.btn_update_file.pack(fill="x", pady=(4, 4))

        self.lbl_update_hint = ttk.Label(
            right_group,
            text="Only available if excluded file version is older than project version.",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT,
            wraplength=230
        )
        self.lbl_update_hint.pack(anchor="w", pady=(2, 0))

        # Batch Operations Box
        batch_group = ttk.LabelFrame(right_frame, text="Batch Actions", padding=(12, 10))
        batch_group.pack(fill="both", expand=True)

        ttk.Label(
            batch_group,
            text="Apply exclusion actions to all files matching current search and filter:",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT,
            wraplength=230
        ).pack(anchor="w", pady=(0, 8))

        btn_exclude_all = ttk.Button(
            batch_group,
            text="Exclude All Filtered [✓]",
            command=self._on_exclude_all_visible
        )
        btn_exclude_all.pack(fill="x", pady=2)

        btn_include_all = ttk.Button(
            batch_group,
            text="Include All Filtered [  ]",
            command=self._on_include_all_visible
        )
        btn_include_all.pack(fill="x", pady=2)

        btn_invert = ttk.Button(
            batch_group,
            text="Invert Filtered Selection",
            command=self._on_invert_visible
        )
        btn_invert.pack(fill="x", pady=2)

    def _clear_search(self):
        self.var_search.set("")
        self._apply_filters_and_render()

    def _update_column_headers(self):
        """Updates tree column headings with sort indicators (▲ / ▼)."""
        def arrow(col_name: str) -> str:
            if self.sort_column == col_name:
                return " ▲" if self.sort_asc else " ▼"
            return ""

        self.tree.heading("#0", text=f"File Name{arrow('name')}", anchor="w", command=lambda: self._on_header_click("name"))
        self.tree.heading("folder", text=f"Folder{arrow('folder')}", anchor="w", command=lambda: self._on_header_click("folder"))
        self.tree.heading("status", text=f"Excluded?{arrow('status')}", anchor="center", command=lambda: self._on_header_click("status"))
        self.tree.heading("size", text=f"Size{arrow('size')}", anchor="e", command=lambda: self._on_header_click("size"))

        self.tree.column("#0", width=220, stretch=True)
        self.tree.column("folder", width=140, stretch=True)
        self.tree.column("status", width=95, anchor="center", stretch=False)
        self.tree.column("size", width=70, anchor="e", stretch=False)

    def _on_header_click(self, col: str):
        """Toggle sort order when a column header is clicked."""
        if self.sort_column == col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_column = col
            self.sort_asc = True

        # Sync sort combobox
        if col == "name":
            self.var_sort.set("Name (A to Z)" if self.sort_asc else "Name (Z to A)")
        elif col == "folder":
            self.var_sort.set("Folder (A to Z)" if self.sort_asc else "Folder (Z to A)")
        elif col == "status":
            self.var_sort.set("Status (Excluded First)" if self.sort_asc else "Status (Included First)")
        elif col == "size":
            self.var_sort.set("Size (Smallest First)" if self.sort_asc else "Size (Largest First)")

        self._update_column_headers()
        self._apply_filters_and_render()

    def _on_sort_combobox_changed(self, event=None):
        val = self.var_sort.get()
        if val == "Name (A to Z)":
            self.sort_column, self.sort_asc = "name", True
        elif val == "Name (Z to A)":
            self.sort_column, self.sort_asc = "name", False
        elif val == "Folder (A to Z)":
            self.sort_column, self.sort_asc = "folder", True
        elif val == "Folder (Z to A)":
            self.sort_column, self.sort_asc = "folder", False
        elif val == "Status (Excluded First)":
            self.sort_column, self.sort_asc = "status", True
        elif val == "Status (Included First)":
            self.sort_column, self.sort_asc = "status", False
        elif val == "Size (Smallest First)":
            self.sort_column, self.sort_asc = "size", True
        elif val == "Size (Largest First)":
            self.sort_column, self.sort_asc = "size", False

        self._update_column_headers()
        self._apply_filters_and_render()

    def _get_visible_files(self) -> List[Dict[str, Any]]:
        """Filters and sorts self.all_files based on current controls."""
        query = self.var_search.get()
        filter_mode = self.var_filter.get()

        visible = []
        for item in self.all_files:
            if not matches_search(item, query):
                continue
            if not matches_filter(item, filter_mode, self.excluded_map, self._is_file_older_than_project):
                continue
            visible.append(item)

        # Sort visible items
        reverse = not self.sort_asc
        visible.sort(
            key=lambda item: get_sort_key(item, self.sort_column, self.excluded_map),
            reverse=reverse
        )
        return visible

    def _apply_filters_and_render(self):
        """Re-renders the tree view with current search, filter, sort, and view mode."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_meta.clear()

        visible_files = self._get_visible_files()
        view_mode = self.var_view.get()
        is_hierarchical = "Hierarchical" in view_mode

        # Configure displaycolumns
        if is_hierarchical:
            self.tree.config(displaycolumns=("status", "size"))
        else:
            self.tree.config(displaycolumns=("folder", "status", "size"))

        if not is_hierarchical:
            # Flat list view
            for f in visible_files:
                rel_path = f["rel_path"]
                is_ex = rel_path in self.excluded_map
                check_icon = "[✓] Excluded" if is_ex else "[  ]"

                item_id = self.tree.insert(
                    "",
                    "end",
                    text=f"📄 {f['name']}",
                    values=(f["rel_dir"], check_icon, f["size_str"])
                )
                self.item_meta[item_id] = {
                    "rel_path": rel_path,
                    "is_dir": False,
                    "name": f["name"],
                    "rel_dir": f["rel_dir"],
                    "size_str": f["size_str"],
                }
        else:
            # Hierarchical Folder Tree view
            # Build set of matching relative paths
            matching_paths = {f["rel_path"] for f in visible_files}
            files_by_dir: Dict[str, List[Dict[str, Any]]] = {}
            for f in visible_files:
                parent_dir = os.path.dirname(f["rel_path"]).replace("\\", "/")
                files_by_dir.setdefault(parent_dir, []).append(f)

            # Insert hierarchy recursively
            def add_tree_level(parent_tree_id: str, current_fs_dir: str, current_rel_dir: str):
                try:
                    entries = sorted(os.scandir(current_fs_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
                except OSError:
                    return

                # First add matching subdirectories
                for entry in entries:
                    if entry.is_dir() and not entry.name.startswith("."):
                        sub_rel = os.path.relpath(entry.path, self.main_dir).replace("\\", "/")
                        # Check if any matching file lives inside this directory
                        has_matching_children = any(
                            p == sub_rel or p.startswith(sub_rel + "/")
                            for p in matching_paths
                        )
                        if has_matching_children:
                            # Auto-expand if searching/filtering or at root
                            should_open = bool(self.var_search.get() or self.var_filter.get() != "All Files" or current_rel_dir == "")
                            dir_id = self.tree.insert(
                                parent_tree_id,
                                "end",
                                text=f"📁 {entry.name}",
                                values=("", ""),
                                open=should_open
                            )
                            self.item_meta[dir_id] = {
                                "rel_path": sub_rel,
                                "is_dir": True,
                                "name": entry.name,
                                "rel_dir": current_rel_dir or "(root)",
                                "size_str": "",
                            }
                            add_tree_level(dir_id, entry.path, sub_rel)

                # Then add files at this level that match
                level_files = files_by_dir.get(current_rel_dir, [])
                for f in level_files:
                    rel_path = f["rel_path"]
                    is_ex = rel_path in self.excluded_map
                    check_icon = "[✓] Excluded" if is_ex else "[  ]"

                    item_id = self.tree.insert(
                        parent_tree_id,
                        "end",
                        text=f"📄 {f['name']}",
                        values=(check_icon, f["size_str"])
                    )
                    self.item_meta[item_id] = {
                        "rel_path": rel_path,
                        "is_dir": False,
                        "name": f["name"],
                        "rel_dir": f["rel_dir"],
                        "size_str": f["size_str"],
                    }

            if os.path.exists(self.main_dir):
                add_tree_level("", self.main_dir, "")

        # Update Summary
        total_files = len(self.all_files)
        vis_count = len(visible_files)
        total_ex = sum(1 for f in self.all_files if f["rel_path"] in self.excluded_map)
        updates_avail = sum(
            1 for f in self.all_files
            if f["rel_path"] in self.excluded_map and self._is_file_older_than_project(
                self.excluded_map[f["rel_path"]].get("version_name", ""),
                self.excluded_map[f["rel_path"]].get("version_date", "")
            )
        )
        self.lbl_summary.config(
            text=f"Showing {vis_count} of {total_files} files ({total_ex} excluded, {updates_avail} updates available)"
        )

        # Restore details panel if selected item is still visible
        if self.currently_selected_rel_path:
            self._refresh_details_panel(self.currently_selected_rel_path)

    def _on_tree_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id or item_id not in self.item_meta:
            return

        disp_cols = self.tree.cget("displaycolumns")
        if disp_cols == "#all" or not disp_cols:
            disp_cols = ("folder", "status", "size")

        col_id = self.tree.identify_column(event.x)
        # Check if user clicked directly on the status column or near the checkbox area (< 28px)
        if col_id and col_id != "#0":
            try:
                idx = int(col_id.lstrip("#")) - 1
                if 0 <= idx < len(disp_cols) and disp_cols[idx] == "status":
                    self._toggle_exclusion(item_id)
                    return
            except Exception:
                pass
        elif event.x < 28:
            self._toggle_exclusion(item_id)

    def _on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.item_meta:
            self._toggle_exclusion(item_id)

    def _on_tree_space(self, event):
        sel = self.tree.selection()
        if sel and sel[0] in self.item_meta:
            self._toggle_exclusion(sel[0])

    def _toggle_exclusion(self, item_id: str):
        meta = self.item_meta.get(item_id)
        if not meta or meta["is_dir"]:
            return

        rel_path = meta["rel_path"]
        if rel_path in self.excluded_map:
            del self.excluded_map[rel_path]
            new_check = "[  ]"
        else:
            self.excluded_map[rel_path] = {
                "version_name": self.config.version_name,
                "version_date": self.config.version_date,
            }
            new_check = "[✓] Excluded"

        # Update tree item value in place
        cur_values = list(self.tree.item(item_id, "values"))
        disp_cols = self.tree.cget("displaycolumns")
        if disp_cols == "#all" or not disp_cols:
            disp_cols = ("folder", "status", "size")

        for idx, col_name in enumerate(disp_cols):
            if col_name == "status" and idx < len(cur_values):
                cur_values[idx] = new_check

        self.tree.item(item_id, values=cur_values)
        self._refresh_details_panel(rel_path)

        # Update summary counts
        total_files = len(self.all_files)
        visible_files = self._get_visible_files()
        total_ex = sum(1 for f in self.all_files if f["rel_path"] in self.excluded_map)
        updates_avail = sum(
            1 for f in self.all_files
            if f["rel_path"] in self.excluded_map and self._is_file_older_than_project(
                self.excluded_map[f["rel_path"]].get("version_name", ""),
                self.excluded_map[f["rel_path"]].get("version_date", "")
            )
        )
        self.lbl_summary.config(
            text=f"Showing {len(visible_files)} of {total_files} files ({total_ex} excluded, {updates_avail} updates available)"
        )

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item_id = sel[0]
        meta = self.item_meta.get(item_id)
        if not meta:
            return

        rel_path = meta["rel_path"]
        is_dir = meta["is_dir"]

        if is_dir:
            self.currently_selected_rel_path = None
            self.lbl_file_path.config(text=f"Folder: {rel_path}")
            self.lbl_file_folder.config(text=meta.get("rel_dir", "-"))
            self.lbl_file_size.config(text="-")
            self.lbl_status.config(text="Folder (Cannot be excluded directly)", foreground=MUTED_TEXT)
            self.lbl_ver_name.config(text="-")
            self.lbl_ver_date.config(text="-")
            self.btn_update_file.config(state="disabled")
            self.lbl_update_hint.config(text="Folders cannot be excluded; select a file inside to exclude.", foreground=MUTED_TEXT)
        else:
            self.currently_selected_rel_path = rel_path
            self._refresh_details_panel(rel_path)

    def _refresh_details_panel(self, rel_path: str):
        is_ex = rel_path in self.excluded_map
        self.lbl_file_path.config(text=rel_path)

        # Find file in all_files for size & dir info
        found = next((f for f in self.all_files if f["rel_path"] == rel_path), None)
        if found:
            self.lbl_file_folder.config(text=found["rel_dir"])
            self.lbl_file_size.config(text=found["size_str"])
        else:
            self.lbl_file_folder.config(text="-")
            self.lbl_file_size.config(text="-")

        if is_ex:
            info = self.excluded_map[rel_path]
            ver_name = info.get("version_name") or self.config.version_name or "N/A"
            ver_date = info.get("version_date") or self.config.version_date or "N/A"

            self.lbl_status.config(text="Excluded (Protected from updates)", foreground="#D83B01")
            self.lbl_ver_name.config(text=ver_name)
            self.lbl_ver_date.config(text=ver_date)

            can_update = self._is_file_older_than_project(ver_name, ver_date)
            if can_update:
                self.btn_update_file.config(state="normal")
                self.lbl_update_hint.config(
                    text="Update available! File is older than current project version.",
                    foreground=SUCCESS_GREEN
                )
            else:
                self.btn_update_file.config(state="disabled")
                self.lbl_update_hint.config(
                    text="File is already at the current project version.",
                    foreground=MUTED_TEXT
                )
        else:
            self.lbl_status.config(text="Included (Replaced during update)", foreground=SUCCESS_GREEN)
            self.lbl_ver_name.config(text=self.config.version_name or "N/A")
            self.lbl_ver_date.config(text=self.config.version_date or "N/A")
            self.btn_update_file.config(state="disabled")
            self.lbl_update_hint.config(
                text="Check the box to exclude this file from automatic updates.",
                foreground=MUTED_TEXT
            )

    def _is_file_older_than_project(self, file_ver_name: str, file_ver_date: str) -> bool:
        proj_ver_name = self.config.version_name
        proj_ver_date = self.config.version_date

        if not proj_ver_name:
            return False

        if file_ver_name == proj_ver_name:
            return False

        if file_ver_date and proj_ver_date:
            try:
                return file_ver_date < proj_ver_date
            except Exception:
                pass

        return file_ver_name != proj_ver_name

    # --- Batch Actions ---
    def _on_exclude_all_visible(self):
        visible = self._get_visible_files()
        for f in visible:
            rel = f["rel_path"]
            if rel not in self.excluded_map:
                self.excluded_map[rel] = {
                    "version_name": self.config.version_name,
                    "version_date": self.config.version_date,
                }
        self._apply_filters_and_render()

    def _on_include_all_visible(self):
        visible = self._get_visible_files()
        for f in visible:
            rel = f["rel_path"]
            if rel in self.excluded_map:
                del self.excluded_map[rel]
        self._apply_filters_and_render()

    def _on_invert_visible(self):
        visible = self._get_visible_files()
        for f in visible:
            rel = f["rel_path"]
            if rel in self.excluded_map:
                del self.excluded_map[rel]
            else:
                self.excluded_map[rel] = {
                    "version_name": self.config.version_name,
                    "version_date": self.config.version_date,
                }
        self._apply_filters_and_render()

    # --- Single File Update ---
    def _on_update_single_file(self):
        rel_path = self.currently_selected_rel_path
        if not rel_path or rel_path not in self.excluded_map:
            return

        confirm = messagebox.askyesno(
            "Update File",
            f"Are you sure you want to update '{rel_path}' to the project's current version ({self.config.version_name})?\n\nThis will replace your local file with the version from the repository.",
            parent=self
        )
        if not confirm:
            return

        self.btn_update_file.config(state="disabled")
        self.lbl_update_hint.config(text="Updating file...", foreground=ACCENT_BLUE)

        def do_update():
            repo_info = parse_git_url(self.config.git_url)
            if not repo_info:
                self.after(0, lambda: messagebox.showerror("Error", "Invalid Git URL in configuration.", parent=self))
                return

            client = GitHubClient(repo_info)
            try:
                success = self.engine.update_single_excluded_file(
                    rel_path,
                    client,
                    progress_callback=lambda msg: self.after(0, lambda: self.lbl_update_hint.config(text=msg))
                )
                if success:
                    self.excluded_map[rel_path] = {
                        "version_name": self.config.version_name,
                        "version_date": self.config.version_date,
                    }
                    self.after(0, lambda: self._on_single_file_updated(rel_path))
                else:
                    self.after(0, lambda: messagebox.showwarning("Update Warning", f"Could not locate '{rel_path}' in the repository release or source.", parent=self))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Update Error", f"Failed to update file:\n{str(e)}", parent=self))
            finally:
                self.after(0, lambda: self._refresh_details_panel(rel_path))

        threading.Thread(target=do_update, daemon=True).start()

    def _on_single_file_updated(self, rel_path: str):
        messagebox.showinfo("Success", f"File '{rel_path}' was updated to {self.config.version_name}!", parent=self)
        self._apply_filters_and_render()

    def _save_and_close(self):
        self.config.update_excluded_files_batch(self.excluded_map)
        self.config.save()

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
