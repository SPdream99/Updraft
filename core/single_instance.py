import ctypes
import hashlib
import os
import sys
from typing import Optional

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


def bring_existing_window_to_front(window_title_hint: Optional[str] = None) -> bool:
    """
    Searches for an existing top-level window matching the title hint
    and brings it to the foreground, restoring it if minimized.
    """
    if sys.platform != "win32" or not window_title_hint:
        return False

    try:
        user32 = ctypes.windll.user32
        target_lower = window_title_hint.lower()
        found_hwnds = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_windows_callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if target_lower in title.lower():
                        found_hwnds.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

        if found_hwnds:
            hwnd = found_hwnds[0]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass

    return False


class SingleInstanceLock:
    """
    Ensures only a single instance of an application or a project updater runs at any given time.
    Uses native Windows Named Mutex on Windows for robust lifecycle management and automatic
    cleanup on abnormal exit.
    """

    def __init__(self, key: str, window_title_hint: Optional[str] = None):
        self.key = key
        self.window_title_hint = window_title_hint
        self.mutex = None
        self.already_running = False
        self._lock_file = None

    def acquire(self) -> bool:
        """
        Attempts to acquire the single-instance lock.
        Returns True if this is the only instance running.
        Returns False if another instance is already running (and brings that instance to front).
        """
        if sys.platform == "win32":
            try:
                # Create a unique, valid Win32 mutex name
                safe_hash = hashlib.sha256(self.key.encode("utf-8")).hexdigest()[:32]
                mutex_name = f"Local\\Updraft_{safe_hash}"

                kernel32 = ctypes.windll.kernel32
                self.mutex = kernel32.CreateMutexW(None, True, mutex_name)
                last_error = kernel32.GetLastError()

                if last_error == ERROR_ALREADY_EXISTS:
                    self.already_running = True
                    if self.mutex:
                        kernel32.CloseHandle(self.mutex)
                        self.mutex = None
                    if self.window_title_hint:
                        bring_existing_window_to_front(self.window_title_hint)
                    return False

                self.already_running = False
                return True
            except Exception:
                # If Win32 API fails for any reason, allow startup
                return True
        else:
            # Fallback for non-Windows platforms
            import tempfile
            lock_path = os.path.join(tempfile.gettempdir(), f"updraft_{hashlib.md5(self.key.encode()).hexdigest()}.lock")
            try:
                self._lock_file = open(lock_path, "w")
                return True
            except Exception:
                return False

    def release(self):
        """Releases the mutex handle."""
        if sys.platform == "win32" and self.mutex:
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex)
            except Exception:
                pass
            self.mutex = None

        if self._lock_file:
            try:
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
