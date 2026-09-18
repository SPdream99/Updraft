import os
import shutil
import sys
import tempfile
import unittest
import zipfile

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config import UpdaterConfig, ManagedRegistry
from core.git_client import parse_git_url, GitRepoInfo
from core.downloader import UpdateEngine, is_archive, is_executable


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_updater_config_defaults_and_save(self):
        cfg = UpdaterConfig(self.test_dir)
        self.assertFalse(cfg.exists())

        cfg.project_name = "DemoApp"
        cfg.git_url = "https://github.com/test/demo"
        cfg.update_type = "release"
        cfg.version_name = "v1.0.0"
        cfg.version_date = "2026-09-18T10:00:00Z"
        cfg.selected_assets = ["app.zip", "data.pak"]
        cfg.open_when_done = True
        cfg.delete_compressed = False
        cfg.run_script_after_update = True
        cfg.save()

        self.assertTrue(cfg.exists())

        # Check update-done.bat was created and is blank
        bat_file = os.path.join(self.test_dir, "update-done.bat")
        self.assertTrue(os.path.exists(bat_file))
        with open(bat_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "")

        # Reload from disk
        cfg2 = UpdaterConfig(self.test_dir)
        self.assertEqual(cfg2.project_name, "DemoApp")
        self.assertEqual(cfg2.git_url, "https://github.com/test/demo")
        self.assertEqual(cfg2.update_type, "release")
        self.assertEqual(cfg2.version_name, "v1.0.0")
        self.assertEqual(cfg2.version_date, "2026-09-18T10:00:00Z")
        self.assertEqual(cfg2.selected_assets, ["app.zip", "data.pak"])
        self.assertTrue(cfg2.open_when_done)
        self.assertFalse(cfg2.delete_compressed)
        self.assertTrue(cfg2.run_script_after_update)

    def test_excluded_files(self):
        cfg = UpdaterConfig(self.test_dir)
        cfg.set_excluded_file("config/user.json", "v1.0.0", "2026-01-01T00:00:00Z")
        cfg.set_excluded_file("save.dat", "v0.9.0", "2025-12-01T00:00:00Z")
        cfg.save()

        cfg2 = UpdaterConfig(self.test_dir)
        self.assertTrue(cfg2.is_excluded("config/user.json"))
        self.assertTrue(cfg2.is_excluded("save.dat"))
        self.assertFalse(cfg2.is_excluded("main.exe"))

        ex_map = cfg2.get_excluded_files()
        self.assertEqual(ex_map["config/user.json"]["version_name"], "v1.0.0")
        self.assertEqual(ex_map["config/user.json"]["version_date"], "2026-01-01T00:00:00Z")
        self.assertEqual(ex_map["save.dat"]["version_name"], "v0.9.0")

        # Test remove
        cfg2.remove_excluded_file("save.dat")
        cfg2.save()

        cfg3 = UpdaterConfig(self.test_dir)
        self.assertFalse(cfg3.is_excluded("save.dat"))
        self.assertTrue(cfg3.is_excluded("config/user.json"))


class TestGitParser(unittest.TestCase):
    def test_parse_urls(self):
        cases = [
            ("https://github.com/torvalds/linux", "torvalds", "linux"),
            ("https://github.com/octocat/Hello-World.git", "octocat", "Hello-World"),
            ("git@github.com:rust-lang/rust.git", "rust-lang", "rust"),
            ("pallets/flask", "pallets", "flask"),
        ]
        for url, exp_owner, exp_repo in cases:
            res = parse_git_url(url)
            self.assertIsNotNone(res, f"Failed to parse {url}")
            self.assertEqual(res.owner, exp_owner)
            self.assertEqual(res.repo, exp_repo)


class TestDownloaderAndEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.engine = UpdateEngine(self.test_dir)
        self.engine.prepare_directories()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_file_type_helpers(self):
        self.assertTrue(is_archive("test.zip"))
        self.assertTrue(is_archive("archive.tar.gz"))
        self.assertFalse(is_archive("binary.exe"))

        self.assertTrue(is_executable("app.exe"))
        self.assertTrue(is_executable("run.bat"))
        self.assertTrue(is_executable("start.cmd"))
        self.assertTrue(is_executable("script.ps1"))
        self.assertTrue(is_executable("launcher.vbs"))
        self.assertTrue(is_executable("worker.js"))
        self.assertTrue(is_executable("job.wsf"))
        self.assertFalse(is_executable("data.json"))
        self.assertFalse(is_executable("readme.md"))

    def test_archive_extraction_and_install_with_exclusions(self):
        # Create a mock zip archive
        zip_path = os.path.join(self.engine.update_files_dir, "test_update.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Add nested root folder like GitHub zip
            zf.writestr("repo-main/app.exe", "binary content v2")
            zf.writestr("repo-main/config/settings.json", '{"version": 2}')
            zf.writestr("repo-main/notes.txt", "notes v2")

        # Set up an existing main folder with excluded settings.json
        cfg = UpdaterConfig(self.test_dir)
        cfg.delete_compressed = True
        cfg.open_when_done = False
        cfg.set_excluded_file("config/settings.json", "v1.0.0", "2026-01-01T00:00:00Z")
        cfg.save()

        # Existing files in main
        main_config_dir = os.path.join(self.engine.main_dir, "config")
        os.makedirs(main_config_dir, exist_ok=True)
        main_config_file = os.path.join(main_config_dir, "settings.json")
        with open(main_config_file, "w") as f:
            f.write('{"version": 1, "custom_user_setting": "keep_me"}')

        # Run install_or_update with is_update=True
        installed = self.engine.install_or_update([zip_path], is_update=True)

        # Check that app.exe and notes.txt were installed
        main_app_exe = os.path.join(self.engine.main_dir, "app.exe")
        main_notes = os.path.join(self.engine.main_dir, "notes.txt")
        self.assertTrue(os.path.exists(main_app_exe))
        self.assertTrue(os.path.exists(main_notes))

        # Crucial: verify excluded config file was NOT overwritten!
        with open(main_config_file, "r") as f:
            content = f.read()
        self.assertIn("keep_me", content)

        # Verify zip archive was deleted per delete_compressed=True
        self.assertFalse(os.path.exists(zip_path))


class TestManagedRegistry(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.registry = ManagedRegistry()
        # Override registry path to temp file for isolated testing
        self.registry.registry_path = os.path.join(self.test_dir, "test_managed.json")
        self.registry.data = {"instances": {}, "global_settings": {"open_when_done": True, "delete_compressed": True}}

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_register_and_retrieve(self):
        proj_dir = os.path.join(self.test_dir, "MyGame")
        os.makedirs(proj_dir, exist_ok=True)
        exe_path = os.path.join(proj_dir, "ManagedUpdater.exe")

        self.registry.register_instance(
            project_dir=proj_dir,
            updater_path=exe_path,
            project_name="MyGame",
            git_url="https://github.com/test/mygame",
            version_name="v1.0",
            version_date="2026-09-01"
        )

        self.assertTrue(self.registry.has_instance(proj_dir))
        inst = self.registry.get_instance(proj_dir)
        self.assertEqual(inst["project_name"], "MyGame")
        self.assertEqual(inst["version_name"], "v1.0")

        # Test global settings
        self.registry.save_global_settings(open_when_done=False, delete_compressed=True, run_script_after_update=True)
        g = self.registry.get_global_settings()
        self.assertFalse(g["open_when_done"])
        self.assertTrue(g["delete_compressed"])
        self.assertTrue(g["run_script_after_update"])

        # Test removal
        self.registry.remove_instance(proj_dir)
        self.assertFalse(self.registry.has_instance(proj_dir))


if __name__ == "__main__":
    unittest.main()
