import os
import sys

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Updraft.SimpleUpdater")
        except Exception:
            pass

    if "--startup" in sys.argv or "--silent" in sys.argv:
        from core.startup import run_startup_update_all
        run_startup_update_all()
        sys.exit(0)

    from gui.manager_window import UpdateManagerWindow
    app = UpdateManagerWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
