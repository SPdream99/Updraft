import os
import sys
import shutil
import tempfile
import unittest

from core.config import ManagedRegistry, UpdaterConfig
from core.self_updater import check_updater_conflict, get_managed_updater_template


class TestCreateUpdater(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = tempfile.mkdtemp()
        # Mock registry
        self.orig_registry_path = ManagedRegistry.__init__
        self.registry_file = os.path.join(self.registry_dir, "managed_instances.json")

        def mock_init(reg_self):
            reg_self.registry_path = self.registry_file
            reg_self.data = {"instances": {}, "global_settings": {}}
            reg_self.load()

        ManagedRegistry.__init__ = mock_init
        self.registry = ManagedRegistry()

    def tearDown(self):
        ManagedRegistry.__init__ = self.orig_registry_path
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        if os.path.exists(self.registry_dir):
            shutil.rmtree(self.registry_dir, ignore_errors=True)

    def test_check_updater_conflict_empty(self):
        has_conflict, reason = check_updater_conflict("", self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("No folder", reason)

    def test_check_updater_conflict_non_existent(self):
        fake_path = os.path.join(self.test_dir, "non_existent_folder")
        has_conflict, reason = check_updater_conflict(fake_path, self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("does not exist", reason)

    def test_check_updater_conflict_file_not_dir(self):
        file_path = os.path.join(self.test_dir, "some_file.txt")
        with open(file_path, "w") as f:
            f.write("test")
        has_conflict, reason = check_updater_conflict(file_path, self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("not a directory", reason)

    def test_check_updater_conflict_clean_dir(self):
        clean_dir = os.path.join(self.test_dir, "clean_project")
        os.makedirs(clean_dir, exist_ok=True)
        has_conflict, reason = check_updater_conflict(clean_dir, self.registry)
        self.assertFalse(has_conflict)
        self.assertEqual(reason, "")

    def test_check_updater_conflict_with_managed_exe(self):
        target = os.path.join(self.test_dir, "proj_with_exe")
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "ManagedUpdater.exe"), "w") as f:
            f.write("dummy")
        has_conflict, reason = check_updater_conflict(target, self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("ManagedUpdater.exe", reason)

    def test_check_updater_conflict_with_simple_exe(self):
        target = os.path.join(self.test_dir, "proj_with_simple")
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "SimpleUpdater.exe"), "w") as f:
            f.write("dummy")
        has_conflict, reason = check_updater_conflict(target, self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("SimpleUpdater.exe", reason)

    def test_check_updater_conflict_with_ini_file(self):
        target = os.path.join(self.test_dir, "proj_with_ini")
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "updater-info.ini"), "w") as f:
            f.write("[Project]\nproject_name=test")
        has_conflict, reason = check_updater_conflict(target, self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("updater-info.ini", reason)

    def test_check_updater_conflict_already_registered(self):
        target = os.path.join(self.test_dir, "proj_registered")
        os.makedirs(target, exist_ok=True)
        self.registry.register_instance(
            project_dir=target,
            updater_path=os.path.join(target, "ManagedUpdater.exe"),
            project_name="proj_registered"
        )
        has_conflict, reason = check_updater_conflict(target, self.registry)
        self.assertTrue(has_conflict)
        self.assertIn("already registered", reason)

    def test_get_managed_updater_template(self):
        template = get_managed_updater_template()
        # In this workspace, dist/ManagedUpdater.exe exists
        if template:
            self.assertTrue(os.path.exists(template))
            self.assertTrue(os.path.isfile(template))
            self.assertTrue(template.lower().endswith(".exe"))


if __name__ == "__main__":
    unittest.main()
