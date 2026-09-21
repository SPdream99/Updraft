# Updraft - Git Project Updater Control

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build](https://github.com/SPdream99/updraft/actions/workflows/build.yml/badge.svg)](https://github.com/SPdream99/updraft/actions/workflows/build.yml)
[![Releases](https://img.shields.io/github/v/release/SPdream99/updraft)](https://github.com/SPdream99/updraft/releases)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)](https://github.com/SPdream99/updraft/releases)

A standalone updater suite for any GitHub project. Drop it in any folder, point it at a repository, and it handles downloading, extracting, and keeping your project up to date — automatically.

---


## What it does

Updraft ships as three separate executables:

**SimpleUpdater.exe** — The standalone version. It lives inside your project folder and reads its configuration from a local `updater-info.ini` file. No installation required, no external dependencies.

**ManagedUpdater.exe** — The managed version. It works identically to the standalone version but also registers itself with a central registry in `%APPDATA%\Updraft`. This allows the Update Manager to track and manage it.

**UpdateManager.exe** — A central dashboard for all managed instances. From a single window, you can check for updates, update all projects at once, manage file exclusions, and adjust per-project or global settings.

---

## Getting started

**First run — Install phase**

When launched in a folder without an existing configuration, the updater opens a setup wizard:

1. Enter a GitHub repository URL (`https://github.com/owner/repo` or just `owner/repo`).
2. Choose an update source:
   - **Release Page** — select one or more release asset files to download.
   - **Source Code** — download the latest commit as a zip archive.
3. Set completion options (open folder when done, delete archives, run a script on completion).

The updater then:
- Creates a project folder named after the repository.
- Downloads and extracts files into a `main/` subdirectory with no extra nesting.
- Generates a blank `update-done.bat` for post-update automation.
- Creates Windows shortcuts (`.lnk`) for all executables and scripts found in `main/`.
- Saves configuration to `updater-info.ini`.

**Subsequent runs — Update phase**

The updater opens directly to the dashboard and shows the current version. From here:

- **Check for Update** — queries GitHub for a newer release or commit. Shows a comparison before downloading. Preserves excluded files.
- **Exclude-File** — browse files in `main/` and mark any file to be skipped during updates. Excluded files can also be updated individually.
- **Setting** — toggle post-download options.
- **Run bat script** — execute `update-done.bat` in a visible terminal, starting in `main/`.

---

## Smart asset matching

When a new release is published, asset file names often change (e.g., `app-win64-v1.0.zip` becomes `app-win64-v1.1.zip`). Updraft resolves this automatically using a three-tier matching algorithm:

1. **Exact match** — filename is identical.
2. **Tag substitution** — replaces the old version tag with the new one.
3. **Version pattern masking** — strips version segments using regex and matches by structure (prefix, suffix, extension).

If no match can be found — for example, when a maintainer completely renames a file — a dialog appears listing the new release assets so you can pick a replacement. Your selection is saved and used for future updates.

---

## Project structure

```
updraft/
├── core/
│   ├── asset_matcher.py    # Smart release asset matching algorithm
│   ├── config.py           # updater-info.ini and AppData registry
│   ├── downloader.py       # Download, extraction, exclusion, and shortcut logic
│   ├── git_client.py       # GitHub API client (releases, commits, assets)
│   └── theme.py            # Windows 7 Aero GUI styling
├── gui/
│   ├── asset_picker_dialog.py  # Fallback asset picker when filenames change
│   ├── exclude_window.py       # File exclusion tree view
│   ├── install_wizard.py       # First-run setup wizard
│   ├── manager_window.py       # Update Manager central dashboard
│   ├── settings_window.py      # Settings dialog
│   └── updater_window.py       # Main updater dashboard
├── tests/
│   └── test_all.py         # Unit and integration tests
├── build.py                # PyInstaller build script
├── standalone_updater.py   # Entry point: SimpleUpdater.exe
├── managed_updater.py      # Entry point: ManagedUpdater.exe
└── update_manager.py       # Entry point: UpdateManager.exe
```

---

## Building from source

Requires Python 3.13+ and PyInstaller.

Install dependencies:
```
pip install requests pyinstaller pywin32
```

Build all three executables:
```
python build.py
```

Output goes to `dist/`:
- `dist/SimpleUpdater.exe`
- `dist/ManagedUpdater.exe`
- `dist/UpdateManager.exe`

Run tests:
```
python -m unittest discover -s tests
```

---

## Requirements

- Windows 7 or later (tested on Windows 10 and 11)
- GitHub repository (public or with token for private)
- Internet access for update checks

---

## Notes

- Antigravity contributed to the development of this app.
- The `update-done.bat` file is created blank on first install. Edit it to run any post-update commands (rebuild steps, restart scripts, etc.).
- The `main/` folder and `updater-info.ini` are excluded from version control by default. Do not delete `updater-info.ini` unless you want to re-run the setup wizard.
- Shortcuts are created in the project root folder for each `.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.wsf`, and `.js` file found in `main/`. PowerShell shortcuts include an execution policy bypass.

---

## License

MIT
