import os
import sys

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.config import UpdaterConfig, ManagedRegistry
from gui.install_wizard import InstallWizard
from gui.updater_window import UpdaterMainWindow


def main():
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        app_dir = os.path.dirname(exe_path)
    else:
        exe_path = os.path.abspath(__file__)
        app_dir = os.path.abspath(os.getcwd())

    registry = ManagedRegistry()
    config = UpdaterConfig(app_dir)

    # In appdata the manager will know where all the managed updater are;
    # updater first open or later open will all update its current location to the manager.
    registry.update_instance_location(app_dir, exe_path)

    if "--startup" in sys.argv or "--silent" in sys.argv:
        if config.exists():
            from core.startup import run_silent_single_update
            run_silent_single_update(app_dir)
        sys.exit(0)

    # Managed check:
    # "An instance of this app, if managed type and there are no info data for the current
    # location of this instance store in the same folder in appdata and updater-info.ini
    # of this project in the current folder then proceed to install phase."
    has_appdata_info = registry.has_instance(app_dir)
    has_ini_file = config.exists()

    if not has_appdata_info or not has_ini_file:
        def on_installed(target_project_dir: str):
            target_exe = os.path.join(target_project_dir, os.path.basename(exe_path))
            app = UpdaterMainWindow(target_project_dir, target_exe, is_managed=True)
            app.mainloop()

        wizard = InstallWizard(
            current_dir=app_dir,
            updater_exe_path=exe_path,
            is_managed=True,
            on_install_complete=on_installed
        )
        wizard.mainloop()
    else:
        app = UpdaterMainWindow(app_dir, exe_path, is_managed=True)
        app.mainloop()


if __name__ == "__main__":
    main()
