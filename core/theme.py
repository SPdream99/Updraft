import sys
import tkinter as tk
from tkinter import ttk

# Windows 7 Aero Inspired Color Palette
BG_COLOR = "#F0F0F0"
PANEL_BG = "#FFFFFF"
HEADER_BG = "#F5F8FC"
HEADER_BORDER = "#D4E1F0"
TEXT_COLOR = "#000000"
MUTED_TEXT = "#555555"
ACCENT_BLUE = "#0066CC"
ACCENT_BLUE_HOVER = "#1B7FE0"
BORDER_COLOR = "#A0A0A0"
LIGHT_BORDER = "#D9D9D9"
LIST_SELECT_BG = "#CCE8FF"
LIST_HOVER_BG = "#E5F3FF"
SUCCESS_GREEN = "#107C41"
WARNING_ORANGE = "#D83B01"

FONT_FAMILY = "Segoe UI"
FONT_NORMAL = (FONT_FAMILY, 9)
FONT_BOLD = (FONT_FAMILY, 9, "bold")
FONT_TITLE = (FONT_FAMILY, 12, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 9)
FONT_LARGE_BUTTON = (FONT_FAMILY, 10)
FONT_CODE = ("Consolas", 9)

# Register process with Windows taskbar so taskbar uses the app's logo icon
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Updraft.SimpleUpdater")
    except Exception:
        pass


def apply_win7_theme(root: tk.Tk):
    """
    Applies Windows 7 clean Aero style to the Tkinter application.
    """
    root.configure(bg=BG_COLOR)

    # Enable native Windows DPI awareness & taskbar app ID if on Windows
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Updraft.SimpleUpdater")
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    style = ttk.Style(root)
    available_themes = style.theme_names()

    # Prefer 'vista' or 'winnative' if available on Windows
    if "vista" in available_themes:
        style.theme_use("vista")
    elif "winnative" in available_themes:
        style.theme_use("winnative")
    elif "clam" in available_themes:
        style.theme_use("clam")

    # Configure base font
    style.configure(".", font=FONT_NORMAL, background=BG_COLOR, foreground=TEXT_COLOR)

    # Frames
    style.configure("TFrame", background=BG_COLOR)
    style.configure("White.TFrame", background=PANEL_BG)
    style.configure("Header.TFrame", background=HEADER_BG)

    # Labels
    style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=FONT_NORMAL)
    style.configure("HeaderTitle.TLabel", background=HEADER_BG, foreground="#003366", font=FONT_TITLE)
    style.configure("HeaderSub.TLabel", background=HEADER_BG, foreground=MUTED_TEXT, font=FONT_SUBTITLE)
    style.configure("Bold.TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=FONT_BOLD)
    style.configure("White.TLabel", background=PANEL_BG, foreground=TEXT_COLOR, font=FONT_NORMAL)
    style.configure("Muted.TLabel", background=BG_COLOR, foreground=MUTED_TEXT, font=FONT_NORMAL)

    # Buttons (Windows 7 Aero style)
    style.configure(
        "TButton",
        font=FONT_NORMAL,
        padding=(8, 4),
        relief="raised",
    )
    style.configure(
        "Large.TButton",
        font=FONT_LARGE_BUTTON,
        padding=(12, 6),
    )
    style.configure(
        "Accent.TButton",
        font=FONT_BOLD,
        padding=(10, 5),
        foreground="#003366",
    )

    # Entry & Combobox
    style.configure("TEntry", padding=3, font=FONT_NORMAL)
    style.configure("TCombobox", padding=3, font=FONT_NORMAL)

    # Checkbuttons
    style.configure("TCheckbutton", background=BG_COLOR, font=FONT_NORMAL)
    style.configure("White.TCheckbutton", background=PANEL_BG, font=FONT_NORMAL)

    # Labelframe (GroupBox)
    style.configure("TLabelframe", background=BG_COLOR)
    style.configure("TLabelframe.Label", background=BG_COLOR, foreground="#003366", font=FONT_BOLD)

    # Treeview (Explorer style)
    style.configure(
        "Treeview",
        background=PANEL_BG,
        foreground=TEXT_COLOR,
        fieldbackground=PANEL_BG,
        rowheight=24,
        font=FONT_NORMAL,
    )
    style.map(
        "Treeview",
        background=[("selected", LIST_SELECT_BG)],
        foreground=[("selected", TEXT_COLOR)],
    )
    style.configure(
        "Treeview.Heading",
        font=FONT_BOLD,
        padding=4,
        background=BG_COLOR,
    )

    # Progress bar (Classic smooth style)
    style.configure(
        "TProgressbar",
        thickness=18,
    )

    # Automatically set window icon
    apply_window_icon(root)


def get_asset_path(filename: str) -> str:
    """Returns absolute path to an asset, supporting PyInstaller bundles and development environments."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "assets", filename)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "assets", filename)


_cached_icon_images: list = []
_cached_header_logo = None


def apply_window_icon(window: tk.Widget):
    """Sets the Updraft application icon on any Tk or Toplevel window for title bar, Alt-Tab, and taskbar."""
    global _cached_icon_images

    # 1. Windows native iconbitmap (.ico with multi-resolution 16..256)
    ico_path = get_asset_path("icon.ico")
    if sys.platform == "win32" and os.path.exists(ico_path):
        try:
            if hasattr(window, "iconbitmap"):
                # default=ico_path sets for root and future child toplevel windows
                window.iconbitmap(default=ico_path)
        except Exception:
            try:
                window.iconbitmap(ico_path)
            except Exception:
                pass

    # 2. Tkinter iconphoto with multi-resolution PNGs (16, 24, 32, 48, 64, 128, 256)
    # Tkinter selects the best matching size for taskbar (32/48) and titlebar (16)
    try:
        if not _cached_icon_images:
            for s in [16, 24, 32, 48, 64, 128, 256]:
                p = get_asset_path(f"icon_{s}.png")
                if os.path.exists(p):
                    try:
                        _cached_icon_images.append(tk.PhotoImage(file=p))
                    except Exception:
                        pass
            if not _cached_icon_images:
                p = get_asset_path("icon.png")
                if os.path.exists(p):
                    _cached_icon_images.append(tk.PhotoImage(file=p))

        if _cached_icon_images and hasattr(window, "iconphoto"):
            window.iconphoto(True, *_cached_icon_images)
    except Exception:
        pass


def create_win7_header(parent: tk.Widget, title: str, subtitle: str, show_logo: bool = True) -> tk.Widget:
    """
    Creates a clean Windows 7 Aero wizard / dialog header banner with the Updraft logo.
    """
    global _cached_header_logo
    header_frame = ttk.Frame(parent, style="Header.TFrame")
    header_frame.pack(fill="x", side="top")

    content_frame = ttk.Frame(header_frame, style="Header.TFrame", padding=(16, 10))
    content_frame.pack(fill="x")

    if show_logo:
        try:
            logo_path = get_asset_path("header_logo.png")
            if os.path.exists(logo_path):
                if _cached_header_logo is None:
                    _cached_header_logo = tk.PhotoImage(file=logo_path)
                lbl_icon = ttk.Label(content_frame, image=_cached_header_logo, background=HEADER_BG)
                lbl_icon.image = _cached_header_logo
                lbl_icon.pack(side="right", padx=(10, 4))
        except Exception:
            pass

    text_box = ttk.Frame(content_frame, style="Header.TFrame")
    text_box.pack(side="left", fill="both", expand=True)

    lbl_title = ttk.Label(text_box, text=title, style="HeaderTitle.TLabel")
    lbl_title.pack(anchor="w")

    lbl_sub = ttk.Label(text_box, text=subtitle, style="HeaderSub.TLabel")
    lbl_sub.pack(anchor="w", pady=(2, 0))

    # Divider line beneath header
    divider = tk.Frame(header_frame, height=1, bg=HEADER_BORDER)
    divider.pack(fill="x", side="bottom")

    return header_frame
