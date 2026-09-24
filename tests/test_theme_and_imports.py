import ast
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class ImportAndUndefinedCheck(unittest.TestCase):
    def test_all_modules_compile_and_import(self):
        modules = [
            "core.theme",
            "core.config",
            "core.downloader",
            "core.asset_matcher",
            "core.version",
            "core.git_client",
            "core.self_updater",
            "core.startup",
            "gui.shortcut_dialog",
            "gui.exclude_window",
            "gui.asset_picker_dialog",
            "gui.settings_window",
            "gui.install_wizard",
            "gui.updater_window",
            "gui.manager_window",
            "standalone_updater",
            "managed_updater",
            "update_manager",
        ]
        for mod in modules:
            with self.subTest(module=mod):
                __import__(mod)

    def test_theme_apply_window_icon_runs(self):
        import tkinter as tk
        from core.theme import apply_win7_theme, apply_window_icon, get_asset_path
        
        ico = get_asset_path("icon.ico")
        self.assertTrue(os.path.exists(ico), f"icon.ico should exist at {ico}")
        
        root = tk.Tk()
        root.withdraw()
        try:
            apply_win7_theme(root)
            apply_window_icon(root)
        finally:
            root.destroy()

    def test_no_undefined_variables_in_codebase(self):
        import builtins
        builtin_names = set(dir(builtins))

        for root, dirs, files in os.walk(ROOT_DIR):
            if any(skip in root for skip in [".git", "__pycache__", "dist", "build", ".pytest_cache"]):
                continue
            for file in files:
                if file.endswith(".py") and not file.startswith("temp_"):
                    filepath = os.path.join(root, file)
                    with open(filepath, "r", encoding="utf-8") as f:
                        code = f.read()
                    try:
                        compile(code, filepath, "exec")
                    except Exception as e:
                        self.fail(f"Failed to compile {filepath}: {e}")

if __name__ == "__main__":
    unittest.main()
