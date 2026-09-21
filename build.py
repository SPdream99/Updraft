import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")

APPS = [
    {
        "name": "SimpleUpdater",
        "entry": os.path.join(BASE_DIR, "standalone_updater.py"),
        "description": "Simple Git Project Updater (Standalone)",
    },
    {
        "name": "ManagedUpdater",
        "entry": os.path.join(BASE_DIR, "managed_updater.py"),
        "description": "Simple Git Project Updater (Managed)",
    },
    {
        "name": "UpdateManager",
        "entry": os.path.join(BASE_DIR, "update_manager.py"),
        "description": "Update Manager Dashboard",
    },
]


def build_all():
    print("=" * 60)
    print("Building Simple Updater Suite (.exe binaries)")
    print("=" * 60)

    os.makedirs(DIST_DIR, exist_ok=True)

    for app in APPS:
        name = app["name"]
        entry = app["entry"]
        print(f"\n---> Building {name}.exe from {entry}...")

        icon_path = os.path.join(BASE_DIR, "assets", "icon.ico")
        assets_dir = os.path.join(BASE_DIR, "assets")

        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            name,
            f"--icon={icon_path}",
            f"--add-data={assets_dir};assets",
            f"--paths={BASE_DIR}",
            entry,
        ]

        result = subprocess.run(cmd, cwd=BASE_DIR)
        if result.returncode != 0:
            print(f"Error: Failed to build {name}.exe (exit code {result.returncode})")
            sys.exit(result.returncode)

        target_exe = os.path.join(DIST_DIR, f"{name}.exe")
        if os.path.exists(target_exe):
            size_mb = os.path.getsize(target_exe) / (1024 * 1024)
            print(f"SUCCESS: Built {target_exe} ({size_mb:.2f} MB)")
        else:
            print(f"Warning: {target_exe} not found in dist directory.")

    print("\n" + "=" * 60)
    print("Build finished successfully!")
    print(f"Binaries available in: {DIST_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    build_all()
