import os
import subprocess
import time
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "dist")

class TestBuiltBinaries(unittest.TestCase):
    def test_binaries_exist(self):
        for name in ["SimpleUpdater.exe", "ManagedUpdater.exe", "UpdateManager.exe"]:
            p = os.path.join(DIST_DIR, name)
            self.assertTrue(os.path.exists(p), f"Binary {name} does not exist in dist/")
            self.assertGreater(os.path.getsize(p), 5 * 1024 * 1024)

    def test_zip_exists_and_valid(self):
        import zipfile
        zip_path = os.path.join(DIST_DIR, "simple-updater-win.zip")
        self.assertTrue(os.path.exists(zip_path), "simple-updater-win.zip does not exist")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("SimpleUpdater.exe", names)
            self.assertIn("ManagedUpdater.exe", names)
            self.assertIn("UpdateManager.exe", names)

    def test_binaries_launch_without_crash(self):
        for exe_name in ["SimpleUpdater.exe", "ManagedUpdater.exe", "UpdateManager.exe"]:
            exe_path = os.path.join(DIST_DIR, exe_name)
            # Launch binary as a subprocess
            proc = subprocess.Popen([exe_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # Give it 3 seconds to initialize Tkinter and run apply_win7_theme / apply_window_icon
            time.sleep(3)
            # Check if it crashed prematurely
            poll = proc.poll()
            if poll is not None:
                out, err = proc.communicate()
                self.fail(f"{exe_name} crashed immediately with return code {poll}. Stderr: {err.decode('utf-8', errors='ignore')}")
            # Process is running cleanly! Terminate it.
            proc.terminate()
            proc.wait(timeout=5)

if __name__ == "__main__":
    unittest.main()
