import os
import sys
import unittest
import tkinter as tk

from core.single_instance import SingleInstanceLock
from gui.exclude_window import ExcludeFilesDialog
from gui.manager_window import UpdateManagerWindow
from core.config import UpdaterConfig


class TestSingleInstance(unittest.TestCase):
    def test_acquire_and_duplicate_detection(self):
        key = "test_updraft_unique_key_12345"
        lock1 = SingleInstanceLock(key)
        lock2 = SingleInstanceLock(key)

        try:
            acquired1 = lock1.acquire()
            self.assertTrue(acquired1, "First instance should acquire lock successfully")
            self.assertFalse(lock1.already_running)

            acquired2 = lock2.acquire()
            self.assertFalse(acquired2, "Second instance with same key should fail to acquire lock")
            self.assertTrue(lock2.already_running)
        finally:
            lock1.release()
            lock2.release()

    def test_release_and_reacquire(self):
        key = "test_updraft_reacquire_key_67890"
        lock1 = SingleInstanceLock(key)
        lock2 = SingleInstanceLock(key)

        try:
            self.assertTrue(lock1.acquire())
            lock1.release()

            # Now lock2 should be able to acquire
            self.assertTrue(lock2.acquire())
        finally:
            lock1.release()
            lock2.release()

    def test_different_keys_concurrent(self):
        key1 = "test_updraft_diff_key_A"
        key2 = "test_updraft_diff_key_B"
        lock1 = SingleInstanceLock(key1)
        lock2 = SingleInstanceLock(key2)

        try:
            self.assertTrue(lock1.acquire())
            self.assertTrue(lock2.acquire())
        finally:
            lock1.release()
            lock2.release()


class TestExcludeMenuColumns(unittest.TestCase):
    def test_exclude_dialog_column_structure(self):
        root = tk.Tk()
        root.withdraw()
        try:
            config = UpdaterConfig(os.getcwd())
            dlg = ExcludeFilesDialog(root, config)
            # Verify status is the first data column so positional tuples map to status
            cols = dlg.tree.cget("columns")
            # In Tkinter, cget("columns") can be string or tuple
            cols_list = dlg.tree["columns"]
            self.assertEqual(cols_list[0], "status", "First data column must be 'status' to match check_icon")
            dlg.destroy()
        finally:
            root.destroy()


class TestManagerBusyState(unittest.TestCase):
    def test_busy_lock_and_unlock(self):
        app = UpdateManagerWindow()
        app.withdraw()
        try:
            self.assertFalse(app._is_busy)
            self.assertEqual(app._block_event(None), "break")

            # Enable busy mode
            app._set_busy(True, "Updating test project...")
            self.assertTrue(app._is_busy)
            self.assertEqual(str(app.btn_check_all["state"]), "disabled")
            self.assertEqual(str(app.btn_update_all["state"]), "disabled")
            self.assertEqual(str(app.btn_refresh["state"]), "disabled")
            self.assertEqual(str(app.btn_add["state"]), "disabled")
            self.assertEqual(str(app.btn_update_app["state"]), "disabled")
            self.assertEqual(str(app.btn_global_settings["state"]), "disabled")
            self.assertEqual(str(app.btn_check_sel["state"]), "disabled")
            self.assertEqual(str(app.btn_update_sel["state"]), "disabled")

            # Selection should not re-enable buttons when busy
            app._on_select_item(None)
            self.assertEqual(str(app.btn_update_sel["state"]), "disabled")

            # Disable busy mode
            app._set_busy(False, "Ready")
            self.assertFalse(app._is_busy)
            self.assertEqual(str(app.btn_check_all["state"]), "normal")
            self.assertEqual(str(app.btn_update_all["state"]), "normal")
            self.assertEqual(str(app.btn_refresh["state"]), "normal")
            self.assertEqual(str(app.btn_add["state"]), "normal")
            self.assertEqual(str(app.btn_update_app["state"]), "normal")
            self.assertEqual(str(app.btn_global_settings["state"]), "normal")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
