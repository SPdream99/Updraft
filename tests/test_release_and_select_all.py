import os
import shutil
import tempfile
import tkinter as tk
import unittest
from unittest.mock import MagicMock, patch

from core.config import UpdaterConfig
from gui.exclude_window import ExcludeFilesDialog
from gui.install_wizard import InstallWizard
from gui.settings_window import SettingsDialog


class TestReleaseAndSelectAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.main_dir = os.path.join(self.test_dir, "main")
        os.makedirs(self.main_dir, exist_ok=True)

        # Create dummy project files
        with open(os.path.join(self.main_dir, "app.exe"), "w") as f:
            f.write("bin")
        with open(os.path.join(self.main_dir, "config.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.main_dir, "script.py"), "w") as f:
            f.write("print(1)")

        self.config = UpdaterConfig(self.test_dir)
        self.config.project_name = "TestProject"
        self.config.git_url = "https://github.com/owner/repo"
        self.config.update_type = "release"
        self.config.version_name = "v1.0.0"
        self.config.selected_assets = ["app-win.zip"]
        self.config.save()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_exclude_dialog_select_all_and_deselect_all(self):
        dialog = ExcludeFilesDialog(self.root, self.config)
        try:
            # 1. Select All (marks all visible files as excluded)
            dialog._on_exclude_all_visible()
            self.assertEqual(len(dialog.excluded_map), 3)

            # 2. Deselect All (marks all visible files as included / not excluded)
            dialog._on_include_all_visible()
            self.assertEqual(len(dialog.excluded_map), 0)

            # 3. Invert
            dialog._on_invert_visible()
            self.assertEqual(len(dialog.excluded_map), 3)
        finally:
            dialog.destroy()

    def test_install_wizard_asset_select_all_and_deselect_all(self):
        wizard = InstallWizard(self.test_dir, os.path.join(self.test_dir, "SimpleUpdater.exe"))
        wizard.withdraw()
        try:
            wizard.latest_release = {
                "tag_name": "v2.0.0",
                "published_at": "2026-09-25",
                "assets": [
                    {"name": "app.zip", "size": 1024 * 1024},
                    {"name": "installer.exe", "size": 2048 * 1024},
                    {"name": "data.tar.gz", "size": 512 * 1024},
                ]
            }
            wizard.var_update_type.set("release")
            wizard.asset_frame = tk.Frame(wizard)
            wizard._refresh_asset_list()

            self.assertEqual(len(wizard.asset_check_vars), 3)

            # Test Deselect All
            wizard._deselect_all_assets()
            for v in wizard.asset_check_vars.values():
                self.assertFalse(v.get())
            self.assertEqual(wizard.lbl_asset_count.cget("text"), "(0 of 3 selected)")

            # Test Select All
            wizard._select_all_assets()
            for v in wizard.asset_check_vars.values():
                self.assertTrue(v.get())
            self.assertEqual(wizard.lbl_asset_count.cget("text"), "(3 of 3 selected)")
        finally:
            wizard.destroy()

    def test_settings_dialog_release_choose_menu(self):
        settings = SettingsDialog(self.root, self.config)
        try:
            # Verify notebook and tabs exist
            self.assertTrue(hasattr(settings, "notebook"))
            self.assertTrue(hasattr(settings, "tab_general"))
            self.assertTrue(hasattr(settings, "tab_release"))

            # Simulate release assets fetched
            dummy_release = {
                "tag_name": "v1.1.0",
                "published_at": "2026-09-25",
                "assets": [
                    {"name": "app-win.zip", "size": 1000},
                    {"name": "app-linux.tar.gz", "size": 2000},
                    {"name": "docs.pdf", "size": 3000},
                ]
            }
            settings._on_release_fetched(dummy_release)

            # Verify assets rendered
            self.assertEqual(len(settings.asset_check_vars), 3)
            # app-win.zip was preselected in config
            self.assertTrue(settings.asset_check_vars["app-win.zip"].get())
            self.assertFalse(settings.asset_check_vars["app-linux.tar.gz"].get())

            # Test Select All
            settings._select_all_assets()
            for v in settings.asset_check_vars.values():
                self.assertTrue(v.get())
            self.assertEqual(settings.lbl_asset_count.cget("text"), "(3 of 3 selected)")

            # Test Deselect All
            settings._deselect_all_assets()
            for v in settings.asset_check_vars.values():
                self.assertFalse(v.get())
            self.assertEqual(settings.lbl_asset_count.cget("text"), "(0 of 3 selected)")

            # Select 1 asset and save
            settings.asset_check_vars["docs.pdf"].set(True)
            settings.var_update_type.set("release")
            settings._save_and_close()

            # Verify saved to config
            reloaded = UpdaterConfig(self.test_dir)
            self.assertEqual(reloaded.update_type, "release")
            self.assertEqual(reloaded.selected_assets, ["docs.pdf"])
        except Exception:
            try:
                settings.destroy()
            except Exception:
                pass
            raise


if __name__ == "__main__":
    unittest.main()
