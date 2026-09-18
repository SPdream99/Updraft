# Simple Git Project Updater

A lightweight, standalone and managed updater suite for any Git/GitHub project, styled with an authentic, clean **Windows 7 Aero GUI**.

---

## 🌟 Overview

The project provides three standalone executables:

1. **`SimpleUpdater.exe` (Standalone)**:
   - Self-contained updater designed to live directly inside your project folder.
   - Saves project configuration in a local `updater-info.ini`.
   - If `updater-info.ini` is missing, it automatically launches the **Install Phase** to set up the project.

2. **`ManagedUpdater.exe` (Managed)**:
   - Synchronizes with `%APPDATA%\SimpleUpdater\managed_instances.json`.
   - Automatically registers or updates its location whenever launched, allowing the central **Update Manager** to track it.
   - If not registered and no `updater-info.ini` exists, it initiates the **Install Phase**.

3. **`UpdateManager.exe` (Update Manager)**:
   - A central dashboard to monitor and manage all managed updaters on your system.
   - Displays project version, release date, status, and local paths.
   - Supports **Check All Updates**, **Update All**, individual checks, single-project updates, file exclusion management, and global defaults.

---

## 🚀 Installation & First Run Flow

When launched for the first time in an unconfigured directory:
1. **Repository Link**: Enter any GitHub repository URL (e.g., `https://github.com/owner/repo` or shorthand `owner/repo`).
2. **Update Type Selection**:
   - **Release Page**: Select specific binary/asset files attached to the latest release (multi-select supported).
   - **Source Code**: Downloads the latest source code archive (commit hash & date recorded).
3. **Completion Settings**:
   - *Open it when done*: Automatically opens the `main` folder in Windows Explorer upon completion.
   - *Delete the compressed file when done?*: Deletes downloaded `.zip` or `.tar.gz` archives after extraction.
   - *Run script after update complete*: Runs `update-done.bat` in a terminal after updating.
4. **Automatic Layout**:
   - Creates a folder with the Git project name.
   - Moves the updater executable, generated `updater-info.ini`, and a blank `update-done.bat` inside.
   - Downloads files into an `update-files/` directory.
   - Extracts archives directly into `main/` without creating redundant nested folders.
   - Cleans up `update-files/` and removes archives if option is enabled.
   - Scans `main/` for executables and scripts (`.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.wsf`, `.js`, etc.) and automatically creates Windows `.lnk` shortcuts in the root project directory (with PowerShell execution bypass configured for `.ps1`).

---

## 🎛️ Main Dashboard Interface

When an installed updater is opened:
- **Check for update**: Queries the repository for new releases/commits. If an update is available, prompts you with a comparison of current vs. new versions before downloading and applying. If *Run script after update complete* is enabled, it automatically executes `update-done.bat` in a terminal redirected to start in `main/`.
- **Exclude-file**: Opens a split-view window:
  - *Left*: Windows Explorer TreeView with checkboxes for all files and subfolders in `main/`. Checked files are excluded from being replaced during updates.
  - *Right*: Details of selected file. If the file is excluded and older than the current project version, an **Update This File** button is enabled to let you update just that specific file.
- **Setting**: Dialog with three options:
  - *Open it when done*
  - *Delete the compressed file when done?*
  - *Run script after update complete* (executes `update-done.bat` in a terminal)
- **Run bat script**: Instantly launches `update-done.bat` in a visible terminal window starting in the `main/` folder, displaying command output and exit status (`[SUCCESS]` or `[FAILED]`).
- **Close**: Exits the updater.

---

## 🛠️ Project Structure

```
Simple Updater/
├── core/
│   ├── config.py         # Handles updater-info.ini and AppData registry
│   ├── downloader.py     # Download, extraction, exclusion, and shortcut logic
│   ├── git_client.py     # GitHub API client for releases, commits, and assets
│   └── theme.py          # Windows 7 Aero styling (Segoe UI, Vista/Win7 theme)
├── gui/
│   ├── exclude_window.py # Split-view explorer tree with checkboxes & file update
│   ├── install_wizard.py # Multi-step install dialog
│   ├── manager_window.py # Update Manager central dashboard
│   ├── settings_window.py# Settings dialog
│   └── updater_window.py # 4-button main updater dashboard
├── tests/
│   └── test_all.py       # Unit and integration test suite
├── build.py              # PyInstaller build automation script
├── standalone_updater.py # Entry point for SimpleUpdater.exe
├── managed_updater.py    # Entry point for ManagedUpdater.exe
└── update_manager.py     # Entry point for UpdateManager.exe
```

---

## 📦 Building Standalone Executables

To build all 3 binaries into the `dist/` directory:
```bash
python build.py
```
This produces:
- `dist/SimpleUpdater.exe`
- `dist/ManagedUpdater.exe`
- `dist/UpdateManager.exe`
