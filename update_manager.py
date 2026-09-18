import os
import sys

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from gui.manager_window import UpdateManagerWindow


def main():
    app = UpdateManagerWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
