import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, Optional, Callable
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
        self.geometry("780x520")
        self.minsize(650, 420)
        self.transient(parent)
        self.grab_set()

        # In-memory working copy of excluded files
        # Dict[rel_path_norm: {'version_name': str, 'version_date': str}]
        self.excluded_map: Dict[str, Dict[str, str]] = self.config.get_excluded_files().copy()

        # Map tree item ID to relative path (forward slashes) and is_folder
        self.item_meta: Dict[str, Dict[str, Any]] = {}
        self.currently_selected_rel_path: Optional[str] = None

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        self.configure(bg=BG_COLOR)

        create_win7_header(
            self,
            "Exclude Files from Updates",
            "Checked files will not be replaced during automatic project updates"
        )

        # Paned Window (Left: File Explorer Tree; Right: File Details)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=14, pady=10)

        # Left Frame: Explorer with TreeView
        left_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=3)

        lbl_tree_title = ttk.Label(left_frame, text="Files in main/ directory:", style="Bold.TLabel")
        lbl_tree_title.pack(anchor="w", pady=(0, 4))

        tree_scroll_y = ttk.Scrollbar(left_frame, orient="vertical")
        tree_scroll_x = ttk.Scrollbar(left_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            left_frame,
            columns=("status",),
            selectmode="browse",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
        )
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)

        self.tree.heading("#0", text="File / Folder", anchor="w")
        self.tree.heading("status", text="Excluded?", anchor="center")
        self.tree.column("#0", width=280, stretch=True)
        self.tree.column("status", width=80, anchor="center", stretch=False)

        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", self._on_tree_space)

        # Right Frame: File details & manual update button
        right_frame = ttk.Frame(paned, padding=8)
        paned.add(right_frame, weight=2)

        right_group = ttk.LabelFrame(right_frame, text="File Information", padding=(12, 10))
        right_group.pack(fill="both", expand=True)

        ttk.Label(right_group, text="File Path:", style="Bold.TLabel").pack(anchor="w", pady=(4, 1))
        self.lbl_file_path = ttk.Label(right_group, text="(Select a file on the left)", wraplength=220)
        self.lbl_file_path.pack(anchor="w", pady=(0, 8))

        ttk.Label(right_group, text="Status:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_status = ttk.Label(right_group, text="-")
        self.lbl_status.pack(anchor="w", pady=(0, 8))

        ttk.Label(right_group, text="Version Name:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_ver_name = ttk.Label(right_group, text="-")
        self.lbl_ver_name.pack(anchor="w", pady=(0, 8))

        ttk.Label(right_group, text="Version Date:", style="Bold.TLabel").pack(anchor="w", pady=(2, 1))
        self.lbl_ver_date = ttk.Label(right_group, text="-")
        self.lbl_ver_date.pack(anchor="w", pady=(0, 14))

        # Update button for single excluded file
        self.btn_update_file = ttk.Button(
            right_group,
            text="Update This File",
            style="Accent.TButton",
            command=self._on_update_single_file,
            state="disabled"
        )
        self.btn_update_file.pack(fill="x", pady=(8, 4))

        self.lbl_update_hint = ttk.Label(
            right_group,
            text="Only available if excluded file version is older than project version.",
            font=("Segoe UI", 8),
            foreground=MUTED_TEXT,
            wraplength=220
        )
        self.lbl_update_hint.pack(anchor="w", pady=(2, 0))

        # Bottom buttons bar
        bottom_frame = ttk.Frame(self, padding=(16, 10))
        bottom_frame.pack(fill="x", side="bottom")

        sep = tk.Frame(self, height=1, bg=LIGHT_BORDER)
        sep.pack(fill="x", side="bottom")

        btn_close = ttk.Button(bottom_frame, text="Close", width=12, command=self.destroy)
        btn_close.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(bottom_frame, text="Save and Close", width=14, command=self._save_and_close)
        btn_save.pack(side="right")

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_meta.clear()

        if not os.path.exists(self.main_dir):
            return

        # Build directory hierarchy recursively
        def add_node(parent_item_id: str, current_dir: str):
            try:
                entries = sorted(os.scandir(current_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                return

            for entry in entries:
                rel_path = os.path.relpath(entry.path, self.main_dir).replace("\\", "/")
                is_dir = entry.is_dir()
                
                if is_dir:
                    item_id = self.tree.insert(
                        parent_item_id,
                        "end",
                        text=f"📁 {entry.name}",
                        values=("",),
                        open=True
                    )
                    self.item_meta[item_id] = {"rel_path": rel_path, "is_dir": True}
                    add_node(item_id, entry.path)
                else:
                    is_ex = rel_path in self.excluded_map
                    check_icon = "[✓] Excluded" if is_ex else "[  ]"
                    item_id = self.tree.insert(
                        parent_item_id,
                        "end",
                        text=f"📄 {entry.name}",
                        values=(check_icon,)
                    )
                    self.item_meta[item_id] = {"rel_path": rel_path, "is_dir": False}

        add_node("", self.main_dir)

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id or item_id not in self.item_meta:
            return

        # If user clicks on column #1 (status) or on item
        if column == "#1" or event.x < 30:
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
            self.tree.item(item_id, values=("[  ]",))
        else:
            # When newly excluded, initial version name and date match the project
            self.excluded_map[rel_path] = {
                "version_name": self.config.version_name,
                "version_date": self.config.version_date,
            }
            self.tree.item(item_id, values=("[✓] Excluded",))

        self._refresh_details_panel(rel_path)

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
            self.lbl_status.config(text="Folder (Cannot be excluded directly)")
            self.lbl_ver_name.config(text="-")
            self.lbl_ver_date.config(text="-")
            self.btn_update_file.config(state="disabled")
        else:
            self.currently_selected_rel_path = rel_path
            self._refresh_details_panel(rel_path)

    def _refresh_details_panel(self, rel_path: str):
        is_ex = rel_path in self.excluded_map
        self.lbl_file_path.config(text=rel_path)

        if is_ex:
            info = self.excluded_map[rel_path]
            ver_name = info.get("version_name") or self.config.version_name or "N/A"
            ver_date = info.get("version_date") or self.config.version_date or "N/A"

            self.lbl_status.config(text="Excluded (Will not be replaced on update)", foreground="#D83B01")
            self.lbl_ver_name.config(text=ver_name)
            self.lbl_ver_date.config(text=ver_date)

            # Check if this excluded file's version is older than project version
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
                text="Check the box to exclude this file from updates.",
                foreground=MUTED_TEXT
            )

    def _is_file_older_than_project(self, file_ver_name: str, file_ver_date: str) -> bool:
        proj_ver_name = self.config.version_name
        proj_ver_date = self.config.version_date

        if not proj_ver_name:
            return False

        # If versions are identical, it's not older
        if file_ver_name == proj_ver_name:
            return False

        # Compare dates if available
        if file_ver_date and proj_ver_date:
            try:
                # ISO date string comparison works lexicographically
                return file_ver_date < proj_ver_date
            except Exception:
                pass

        # If names differ and date isn't comparable, treat differing version as eligible
        return file_ver_name != proj_ver_name

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
                    # Update working map
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
        self._refresh_details_panel(rel_path)

    def _save_and_close(self):
        self.config.update_excluded_files_batch(self.excluded_map)
        self.config.save()

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
