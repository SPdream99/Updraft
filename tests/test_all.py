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
from core.git_client import parse_git_url, GitRepoInfo, GitHubClient
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
        cfg.create_shortcuts = False
        cfg.shortcut_folder_level = 2
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
        self.assertFalse(cfg2.create_shortcuts)
        self.assertEqual(cfg2.shortcut_folder_level, 2)

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

    def test_github_client_repo_details(self):
        info = parse_git_url("https://github.com/Genymobile/scrcpy")
        client = GitHubClient(info)
        try:
            details = client.get_repo_details()
            self.assertEqual(details["name"].lower(), "scrcpy")
            self.assertIn("scrcpy", details["html_url"].lower())
        except RuntimeError as e:
            if "403" in str(e) or "rate limit" in str(e).lower():
                self.skipTest("GitHub API rate limit reached")
            raise


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
        self.assertTrue(is_executable("index.html"))
        self.assertTrue(is_executable("page.htm"))
        self.assertTrue(is_executable("app.py"))
        self.assertTrue(is_executable("gui.pyw"))
        self.assertFalse(is_executable("data.json"))
        self.assertFalse(is_executable("readme.md"))

    def test_create_shortcuts_with_python_bat(self):
        # Create dummy python files and __init__.py in main
        os.makedirs(self.engine.main_dir, exist_ok=True)
        py_file = os.path.join(self.engine.main_dir, "launcher.py")
        init_file = os.path.join(self.engine.main_dir, "__init__.py")
        with open(py_file, "w") as f:
            f.write("print('hello')\n")
        with open(init_file, "w") as f:
            f.write("# init\n")

        self.engine.create_shortcuts()

        # Should generate launcher.bat in project root
        bat_file = os.path.join(self.engine.project_dir, "launcher.bat")
        self.assertTrue(os.path.exists(bat_file))
        with open(bat_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('python "launcher.py"', content)
        self.assertIn('cd /d "%~dp0main"', content)

        # __init__.py should NOT get a bat file
        init_bat = os.path.join(self.engine.project_dir, "__init__.bat")
        self.assertFalse(os.path.exists(init_bat))

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
        self.registry.save_global_settings(
            open_when_done=False,
            delete_compressed=True,
            run_script_after_update=True,
            create_shortcuts=False,
            shortcut_folder_level=1
        )
        g = self.registry.get_global_settings()
        self.assertFalse(g["open_when_done"])
        self.assertTrue(g["delete_compressed"])
        self.assertTrue(g["run_script_after_update"])
        self.assertFalse(g["create_shortcuts"])
        self.assertEqual(g["shortcut_folder_level"], 1)

        # Test removal
        self.registry.remove_instance(proj_dir)
        self.assertFalse(self.registry.has_instance(proj_dir))


class TestAssetMatcher(unittest.TestCase):
    def test_exact_match(self):
        from core.asset_matcher import match_release_assets
        available = [
            {"name": "setup.exe", "download_url": "http://example.com/setup.exe"},
            {"name": "setup.zip", "download_url": "http://example.com/setup.zip"}
        ]
        matched, unresolved = match_release_assets(["setup.exe"], available)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "setup.exe")
        self.assertEqual(unresolved, [])

    def test_tag_replacement(self):
        from core.asset_matcher import match_release_assets
        available = [
            {"name": "scrcpy-win64-v4.2.zip", "download_url": "http://example.com/win64.zip"},
            {"name": "scrcpy-linux-v4.2.tar.gz", "download_url": "http://example.com/linux.tar.gz"}
        ]
        # Previous version was v4.1, new version is v4.2
        matched, unresolved = match_release_assets(
            ["scrcpy-win64-v4.1.zip"],
            available,
            old_tag="v4.1",
            new_tag="v4.2"
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "scrcpy-win64-v4.2.zip")
        self.assertEqual(unresolved, [])

    def test_regex_version_masking(self):
        from core.asset_matcher import match_release_assets
        available = [
            {"name": "mytool-2.5.1-x86_64.zip", "download_url": "http://example.com/win.zip"},
            {"name": "mytool-2.5.1-arm64.tar.gz", "download_url": "http://example.com/arm.tar.gz"}
        ]
        # Without tags provided, regex masks 1.0.0 and matches 2.5.1
        matched, unresolved = match_release_assets(
            ["mytool-1.0.0-x86_64.zip"],
            available
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "mytool-2.5.1-x86_64.zip")
        self.assertEqual(unresolved, [])

    def test_unresolved_renamed_detection(self):
        from core.asset_matcher import match_release_assets
        available = [
            {"name": "completely-renamed-package.zip", "download_url": "http://example.com/pkg.zip"}
        ]
        # Target has no resemblance or version match
        matched, unresolved = match_release_assets(
            ["old-software-win64.zip"],
            available,
            old_tag="v1.0",
            new_tag="v2.0"
        )
        self.assertEqual(len(matched), 0)
        self.assertEqual(unresolved, ["old-software-win64.zip"])


class TestStartup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_auto_update_on_startup(self):
        cfg = UpdaterConfig(self.temp_dir)
        # Default should be True
        self.assertTrue(cfg.auto_update_on_startup)
        cfg.auto_update_on_startup = False
        cfg.save()

        # Reload
        cfg2 = UpdaterConfig(self.temp_dir)
        self.assertFalse(cfg2.auto_update_on_startup)

    def test_managed_registry_startup_setting(self):
        reg = ManagedRegistry()
        reg.registry_path = os.path.join(self.temp_dir, "test_managed.json")
        reg.save_global_settings(True, True, True, auto_update_on_startup=True)

        loaded = reg.get_global_settings()
        self.assertTrue(loaded.get("auto_update_on_startup"))

    def test_registry_startup_enable_disable(self):
        import sys
        if sys.platform != "win32":
            self.skipTest("Windows-only startup registry test")

        from core.startup import is_startup_enabled, set_startup_enabled, get_startup_command
        test_key = "UpdraftTestEntry_UnitTest"

        try:
            # Enable with custom command
            res = set_startup_enabled(True, entry_name=test_key, custom_command='"C:\\dummy.exe" --startup')
            self.assertTrue(res)
            self.assertTrue(is_startup_enabled(entry_name=test_key))
            cmd = get_startup_command(entry_name=test_key)
            self.assertEqual(cmd, '"C:\\dummy.exe" --startup')

            # Disable
            res = set_startup_enabled(False, entry_name=test_key)
            self.assertTrue(res)
            self.assertFalse(is_startup_enabled(entry_name=test_key))
        finally:
            # Cleanup
            set_startup_enabled(False, entry_name=test_key)

    def test_run_startup_update_all_empty(self):
        from core.startup import run_startup_update_all
        reg = ManagedRegistry()
        reg.registry_path = os.path.join(self.temp_dir, "test_managed.json")
        reg.data = {"instances": {}, "global_settings": {}}
        reg.save()

        log_path = os.path.join(self.temp_dir, "test_startup.log")
        results = run_startup_update_all(registry=reg, log_file=log_path)
        self.assertEqual(results["checked_count"], 0)
        self.assertTrue(os.path.exists(log_path))


class TestSelfUpdater(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_version_tuple_parsing(self):
        from core.self_updater import parse_version_tuple
        self.assertEqual(parse_version_tuple("v1.0.0"), (1, 0, 0))
        self.assertEqual(parse_version_tuple("1.2.3.4"), (1, 2, 3, 4))
        self.assertEqual(parse_version_tuple("v2.1-rc1"), (2, 1))
        self.assertEqual(parse_version_tuple("invalid"), (0,))

    def test_is_newer_version(self):
        from core.self_updater import is_newer_version
        self.assertTrue(is_newer_version("v1.0.1", "v1.0.0"))
        self.assertTrue(is_newer_version("v1.10.0", "v1.9.0"))
        self.assertTrue(is_newer_version("v2.0.0", "v1.9.9"))
        self.assertFalse(is_newer_version("v1.0.0", "v1.0.0"))
        self.assertFalse(is_newer_version("v0.9.0", "v1.0.0"))
        self.assertFalse(is_newer_version("v1.0.0", "v1.0.1"))

    def test_config_auto_update_self(self):
        cfg = UpdaterConfig(self.temp_dir)
        self.assertTrue(cfg.auto_update_self)
        cfg.auto_update_self = False
        cfg.save()

        cfg2 = UpdaterConfig(self.temp_dir)
        self.assertFalse(cfg2.auto_update_self)

    def test_managed_registry_auto_update_self(self):
        reg = ManagedRegistry()
        reg.registry_path = os.path.join(self.temp_dir, "test_managed.json")
        reg.save_global_settings(True, True, True, auto_update_on_startup=True, auto_update_self=False)

        loaded = reg.get_global_settings()
        self.assertFalse(loaded.get("auto_update_self"))

    def test_check_app_update_has_newer(self):
        import json
        from unittest.mock import patch, MagicMock
        from core.self_updater import check_app_update

        fake_response_data = {
            "tag_name": "v9.9.9",
            "assets": [
                {
                    "name": "SimpleUpdater.exe",
                    "browser_download_url": "https://github.com/SPdream99/Updraft/releases/download/v9.9.9/SimpleUpdater.exe"
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_response_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("core.git_client.urllib.request.urlopen", return_value=mock_resp):
            res = check_app_update(target_binary_name="SimpleUpdater.exe")
            self.assertTrue(res.get("has_update"))
            self.assertEqual(res.get("latest_version"), "v9.9.9")
            self.assertEqual(res.get("asset_url"), "https://github.com/SPdream99/Updraft/releases/download/v9.9.9/SimpleUpdater.exe")

    def test_update_all_managed_instances(self):
        from core.self_updater import update_all_managed_instances
        from unittest.mock import patch, MagicMock

        # Create 2 mock project directories
        proj1 = os.path.join(self.temp_dir, "proj1")
        proj2 = os.path.join(self.temp_dir, "proj2")
        os.makedirs(proj1)
        os.makedirs(proj2)

        exe1 = os.path.join(proj1, "ManagedUpdater.exe")
        exe2 = os.path.join(proj2, "ManagedUpdater.exe")
        with open(exe1, "w") as f:
            f.write("old_binary_1")
        with open(exe2, "w") as f:
            f.write("old_binary_2")

        reg = ManagedRegistry()
        reg.registry_path = os.path.join(self.temp_dir, "test_managed.json")
        reg.data = {"instances": {}, "global_settings": {}}
        reg.register_instance(proj1, exe1, "Project1")
        reg.register_instance(proj2, exe2, "Project2")

        fake_assets = [
            {
                "name": "ManagedUpdater.exe",
                "download_url": "https://fake.url/ManagedUpdater.exe"
            }
        ]

        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "10"}
        mock_resp.read.side_effect = [b"new_binary", b""]
        mock_resp.__enter__.return_value = mock_resp

        with patch("core.self_updater.urllib.request.urlopen", return_value=mock_resp):
            res = update_all_managed_instances(fake_assets, registry=reg)
            self.assertEqual(res["updated_count"], 2)
            self.assertEqual(res["total"], 2)
            self.assertEqual(len(res["errors"]), 0)

            with open(exe1, "rb") as f:
                self.assertEqual(f.read(), b"new_binary")
            with open(exe2, "rb") as f:
                self.assertEqual(f.read(), b"new_binary")

    def test_startup_with_self_update_enabled(self):
        from core.startup import run_startup_update_all
        from unittest.mock import patch

        reg = ManagedRegistry()
        reg.registry_path = os.path.join(self.temp_dir, "test_managed.json")
        reg.save_global_settings(True, True, True, auto_update_on_startup=True, auto_update_self=True)

        fake_upd_res = {
            "has_update": True,
            "latest_version": "v2.0.0",
            "asset_url": "https://fake.url/UpdateManager.exe",
            "all_assets": [
                {"name": "ManagedUpdater.exe", "download_url": "https://fake.url/ManagedUpdater.exe"}
            ]
        }

        log_path = os.path.join(self.temp_dir, "startup.log")
        with patch("core.self_updater.check_app_update", return_value=fake_upd_res), \
             patch("core.self_updater.update_all_managed_instances", return_value={"updated_count": 0, "total": 0, "errors": []}):
            results = run_startup_update_all(registry=reg, log_file=log_path)
            self.assertEqual(results.get("updated_updraft"), "v2.0.0")
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
                self.assertIn("New Updraft release detected: v2.0.0", log_content)


class TestShortcutCreation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.engine = UpdateEngine(self.test_dir)
        self.cfg = UpdaterConfig(self.test_dir)
        self.cfg.save()

        # Create nested file structure inside main/
        # main/
        #   root_app.py
        #   root_doc.html
        #   level1/
        #     sub1_app.py
        #     sub1_doc.html
        #     level2/
        #       sub2_app.py
        #       sub2_doc.html
        main_dir = os.path.join(self.test_dir, "main")
        l1_dir = os.path.join(main_dir, "level1")
        l2_dir = os.path.join(l1_dir, "level2")
        os.makedirs(l2_dir, exist_ok=True)

        with open(os.path.join(main_dir, "root_app.py"), "w") as f:
            f.write("print('root')")
        with open(os.path.join(main_dir, "root_doc.html"), "w") as f:
            f.write("<html>root</html>")

        with open(os.path.join(l1_dir, "sub1_app.py"), "w") as f:
            f.write("print('level1')")
        with open(os.path.join(l1_dir, "sub1_doc.html"), "w") as f:
            f.write("<html>sub1</html>")

        with open(os.path.join(l2_dir, "sub2_app.py"), "w") as f:
            f.write("print('level2')")
        with open(os.path.join(l2_dir, "sub2_doc.html"), "w") as f:
            f.write("<html>sub2</html>")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_shortcut_disabled(self):
        self.cfg.create_shortcuts = False
        self.cfg.save()

        shortcuts = self.engine.create_shortcuts()
        self.assertEqual(len(shortcuts), 0)
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "root_app.bat")))

    def test_shortcut_depth_0_root_only(self):
        self.cfg.create_shortcuts = True
        self.cfg.shortcut_folder_level = 0
        self.cfg.save()

        shortcuts = self.engine.create_shortcuts()
        # Should only contain root items (root_app.bat)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "root_app.bat")))
        # Level 1 and 2 items should NOT exist
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "sub1_app.bat")))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "sub2_app.bat")))

    def test_shortcut_depth_1(self):
        self.cfg.create_shortcuts = True
        self.cfg.shortcut_folder_level = 1
        self.cfg.save()

        shortcuts = self.engine.create_shortcuts()
        # Level 0 and Level 1 items should exist
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "root_app.bat")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "sub1_app.bat")))
        # Level 2 items should NOT exist
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "sub2_app.bat")))

    def test_shortcut_depth_unlimited(self):
        self.cfg.create_shortcuts = True
        self.cfg.shortcut_folder_level = -1
        self.cfg.save()

        shortcuts = self.engine.create_shortcuts()
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "root_app.bat")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "sub1_app.bat")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "sub2_app.bat")))


    def test_subfolder_shortcut_discovery(self):
        from core.downloader import discover_project_shortcuts
        self.cfg.create_folder_shortcuts = True
        self.cfg.shortcut_folder_level = 1
        self.cfg.save()

        candidates = discover_project_shortcuts(self.test_dir, self.cfg)
        folder_candidates = [c for c in candidates if c["type"] == "folder"]
        self.assertTrue(any(c["base_name"] == "level1" for c in folder_candidates))
        # level2 is at level 2, so should not be included when max_depth is 1
        self.assertFalse(any(c["base_name"] == "level2" for c in folder_candidates))

    def test_shortcut_custom_rules_and_prefix(self):
        from core.downloader import discover_project_shortcuts
        self.cfg.shortcut_prefix = "Run "
        self.cfg.set_shortcut_rule("main/root_app.py", enabled=True, custom_name="Launch Master App")
        self.cfg.set_shortcut_rule("main/level1", enabled=False)
        self.cfg.save()

        candidates = discover_project_shortcuts(self.test_dir, self.cfg)
        app_cand = next((c for c in candidates if "root_app.py" in c["rel_path"]), None)
        self.assertIsNotNone(app_cand)
        self.assertEqual(app_cand["effective_name"], "Launch Master App")
        self.assertEqual(app_cand["output_filename"], "Launch Master App.bat")

        level1_cand = next((c for c in candidates if c["base_name"] == "level1"), None)
        self.assertIsNotNone(level1_cand)
        self.assertFalse(level1_cand["enabled"])

    def test_shortcut_layout_folder(self):
        self.cfg.create_shortcuts = True
        self.cfg.shortcut_layout = "shortcuts_folder"
        self.cfg.save()

        shortcuts = self.engine.create_shortcuts()
        self.assertTrue(len(shortcuts) > 0)
        shortcuts_dir = os.path.join(self.test_dir, "Shortcuts")
        self.assertTrue(os.path.exists(shortcuts_dir))
        for p in shortcuts:
            self.assertTrue(p.startswith(shortcuts_dir))


class TestExcludeFilterSortSearch(unittest.TestCase):
    def test_format_size(self):
        from gui.exclude_window import format_size
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(1024 * 1024 * 3), "3.0 MB")
        self.assertEqual(format_size(1024 * 1024 * 1024 * 2), "2.0 GB")

    def test_matches_search(self):
        from gui.exclude_window import matches_search
        item = {"name": "config.json", "rel_path": "settings/config.json"}
        self.assertTrue(matches_search(item, ""))
        self.assertTrue(matches_search(item, "config"))
        self.assertTrue(matches_search(item, "settings"))
        self.assertTrue(matches_search(item, "JSON"))
        self.assertFalse(matches_search(item, "missing"))

    def test_matches_filter(self):
        from gui.exclude_window import matches_filter

        item_ex = {"name": "save.dat", "rel_path": "saves/save.dat", "ext": ".dat"}
        item_inc = {"name": "app.exe", "rel_path": "bin/app.exe", "ext": ".exe"}
        item_cfg = {"name": "settings.ini", "rel_path": "config/settings.ini", "ext": ".ini"}
        item_py = {"name": "script.py", "rel_path": "scripts/script.py", "ext": ".py"}

        excluded_map = {
            "saves/save.dat": {"version_name": "v1.0.0", "version_date": "2026-01-01"},
        }

        # All Files
        self.assertTrue(matches_filter(item_ex, "All Files", excluded_map, lambda v, d: False))
        self.assertTrue(matches_filter(item_inc, "All Files", excluded_map, lambda v, d: False))

        # Excluded Only
        self.assertTrue(matches_filter(item_ex, "Excluded Only", excluded_map, lambda v, d: False))
        self.assertFalse(matches_filter(item_inc, "Excluded Only", excluded_map, lambda v, d: False))

        # Included Only
        self.assertFalse(matches_filter(item_ex, "Included Only", excluded_map, lambda v, d: False))
        self.assertTrue(matches_filter(item_inc, "Included Only", excluded_map, lambda v, d: False))

        # Update Available
        self.assertTrue(matches_filter(item_ex, "Update Available", excluded_map, lambda v, d: True))
        self.assertFalse(matches_filter(item_ex, "Update Available", excluded_map, lambda v, d: False))

        # Type Filters
        self.assertTrue(matches_filter(item_inc, "Executables (*.exe, *.bat, *.cmd)", excluded_map, lambda v, d: False))
        self.assertFalse(matches_filter(item_cfg, "Executables (*.exe, *.bat, *.cmd)", excluded_map, lambda v, d: False))

        self.assertTrue(matches_filter(item_cfg, "Config & Data (*.ini, *.json, *.xml, *.cfg)", excluded_map, lambda v, d: False))
        self.assertFalse(matches_filter(item_inc, "Config & Data (*.ini, *.json, *.xml, *.cfg)", excluded_map, lambda v, d: False))

        self.assertTrue(matches_filter(item_py, "Python & Scripts (*.py, *.ps1, *.js)", excluded_map, lambda v, d: False))
        self.assertFalse(matches_filter(item_cfg, "Python & Scripts (*.py, *.ps1, *.js)", excluded_map, lambda v, d: False))

    def test_get_sort_key(self):
        from gui.exclude_window import get_sort_key
        item1 = {"name": "Beta.txt", "rel_path": "b/Beta.txt", "rel_dir": "b", "size_bytes": 100, "ext": ".txt"}
        item2 = {"name": "alpha.txt", "rel_path": "a/alpha.txt", "rel_dir": "a", "size_bytes": 500, "ext": ".txt"}
        excluded_map = {"b/Beta.txt": {}}

        self.assertEqual(get_sort_key(item1, "name", excluded_map), "beta.txt")
        self.assertEqual(get_sort_key(item1, "folder", excluded_map), "b")
        self.assertEqual(get_sort_key(item1, "status", excluded_map), 0)
        self.assertEqual(get_sort_key(item2, "status", excluded_map), 1)
        self.assertEqual(get_sort_key(item1, "size", excluded_map), 100)


if __name__ == "__main__":
    unittest.main()




