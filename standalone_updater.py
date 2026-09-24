import os
import sys

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.config import UpdaterConfig
from gui.install_wizard import InstallWizard
from gui.updater_window import UpdaterMainWindow


def main():
    # If running as compiled exe, sys.executable is the updater exe
    # If running as script, use sys.argv[0]
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        app_dir = os.path.dirname(exe_path)
    else:
        exe_path = os.path.abspath(__file__)
        app_dir = os.path.abspath(os.getcwd())

    config = UpdaterConfig(app_dir)

    if "--startup" in sys.argv or "--silent" in sys.argv:
        if config.exists():
            from core.startup import run_silent_single_update
            run_silent_single_update(app_dir)
        sys.exit(0)

    # Standalone check: If there is no updater-info.ini in the same folder, proceed to install phase
    if not config.exists():
        def on_installed(target_project_dir: str):
            # After installation, open the main updater dashboard in the new project directory
            target_exe = os.path.join(target_project_dir, os.path.basename(exe_path))
            app = UpdaterMainWindow(target_project_dir, target_exe, is_managed=False)
            app.mainloop()

        wizard = InstallWizard(
            current_dir=app_dir,
            updater_exe_path=exe_path,
            is_managed=False,
            on_install_complete=on_installed
        )
        wizard.mainloop()
    else:
        app = UpdaterMainWindow(app_dir, exe_path, is_managed=False)
        app.mainloop()


if __name__ == "__main__":
    main()
