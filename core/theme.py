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


def apply_win7_theme(root: tk.Tk):
    """
    Applies Windows 7 clean Aero style to the Tkinter application.
    """
    root.configure(bg=BG_COLOR)

    # Enable native Windows DPI awareness if on Windows
    if sys.platform == "win32":
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


def create_win7_header(parent: tk.Widget, title: str, subtitle: str) -> tk.Widget:
    """
    Creates a clean Windows 7 Aero wizard / dialog header banner.
    """
    header_frame = ttk.Frame(parent, style="Header.TFrame")
    header_frame.pack(fill="x", side="top")

    content_frame = ttk.Frame(header_frame, style="Header.TFrame", padding=(16, 12))
    content_frame.pack(fill="x")

    lbl_title = ttk.Label(content_frame, text=title, style="HeaderTitle.TLabel")
    lbl_title.pack(anchor="w")

    lbl_sub = ttk.Label(content_frame, text=subtitle, style="HeaderSub.TLabel")
    lbl_sub.pack(anchor="w", pady=(2, 0))

    # Divider line beneath header
    divider = tk.Frame(header_frame, height=1, bg=HEADER_BORDER)
    divider.pack(fill="x", side="bottom")

    return header_frame
