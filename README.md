# GameClean

## Quick Install

Install GameClean directly from GitHub:

```bash
uv tool install "git+https://github.com/dpawani1/gameclean.git"
```

Then run it from anywhere:

```bash
gameclean
```

If `gameclean` is not found after installing, restart your terminal or make sure your `uv` tools directory is on your PATH.

## What GameClean Does

GameClean is a Windows gaming storage cleanup CLI. I originally created it for personal use, but wanted to share it because cache buildup after game updates can seriously affect performance.

GameClean scans and deletes cache across all games and software on your PC. It can find GPU shader caches, Steam per-game shader caches like CS2 app ID `730`, launcher caches, logs, crash dumps, leftover game folders, and old installer/package files.

In my own use, cleaning old cache files improved my CS2 performance from about 120 FPS to around 180 FPS. GameClean turns that manual cleanup process into a simple command-line tool with a safety system: SAFE items can be cleaned automatically, while REVIEW items require `y/n` confirmation.

## Quick Start

Run the main interactive menu:

```bash
gameclean
```

You will see:

```txt
GameClean
---------
What would you like to clean?

1. Shader/cache files
2. Leftover game files
3. Old installer/package files
4. Exit
```

For most users, this is the easiest way to use the tool. Pick an option, review what GameClean finds, and confirm what you want to delete.

## Usage

Scan for cleanup targets without deleting anything:

```bash
gameclean scan
```

Clean shader/cache files with the default review workflow:

```bash
gameclean clean
```

Preview cache cleanup only:

```bash
gameclean clean --dry-run
```

Find possible leftover game folders:

```bash
gameclean leftovers
```

Review and delete selected leftover game folders:

```bash
gameclean leftovers --review
```

Find old installer, archive, patch, and package files:

```bash
gameclean installers
```

Review and delete selected installer/package files:

```bash
gameclean installers --review
```

Useful options:

```bash
gameclean leftovers --min 500MB
gameclean installers --min 1GB
gameclean scan --show-roots
```

## Commands

### `gameclean`

Opens the beginner-friendly interactive menu.

```bash
gameclean
```

This is the easiest way to use the tool.

### `gameclean scan`

Scans for SAFE and REVIEW cleanup targets.

```bash
gameclean scan
```

This command is read-only. It does not delete anything.

### `gameclean clean`

Runs the main shader/cache cleanup workflow.

```bash
gameclean clean
```

Default flow:

1. Scans for cleanup targets.
2. Selects SAFE cache folders automatically.
3. Reviews nonzero REVIEW items one by one with `y/n`.
4. Deletes SAFE items and approved REVIEW items together.
5. Shows a cleanup report.

### `gameclean clean --dry-run`

Shows what would be cleaned without deleting anything.

```bash
gameclean clean --dry-run
```

### `gameclean leftovers`

Finds possible leftover game folders from uninstalled games.

```bash
gameclean leftovers
```

This is report-only by default.

### `gameclean leftovers --review`

Lets the user review possible leftover folders one by one and delete selected folders.

```bash
gameclean leftovers --review
```

Leftover folders are never deleted automatically. The user must type `y` or `yes`.

### `gameclean installers`

Finds large old installer, archive, patch, driver, and package files.

```bash
gameclean installers
```

This is report-only by default.

### `gameclean installers --review`

Lets the user review old installer/package files one by one and delete selected files.

```bash
gameclean installers --review
```

## Safety Model

GameClean uses two main categories:

```txt
SAFE
```

Known cache folders that can usually be cleaned automatically, such as GPU shader caches or Steam cache folders.

```txt
REVIEW
```

Folders or files that may be safe to remove, but should be confirmed by the user first.

GameClean does **not** blindly delete important game or system data. It avoids deleting:

- saves
- configs
- mods
- screenshots
- replays
- Steam game install folders
- WindowsApps
- anti-cheat folders
- licenses
- manifests
- session/login data

Review items require confirmation. If the user presses Enter, the default answer is No.

GameClean may show `0 B` folders in scan output, but it skips `0 B` items during deletion prompts.

## Development Usage

Clone the project and install dependencies:

```bash
uv sync
```

Run the tool during development:

```bash
uv run gameclean --help
uv run gameclean
uv run gameclean scan
```

Test fake demo data safely:

```bash
uv run gameclean clean --dry-run --root examples/fake_windows
uv run gameclean leftovers --dry-run --root examples/fake_windows --min 1B
uv run gameclean installers --dry-run --root examples/fake_windows --min 1B
```

Install from GitHub inside another `uv` project:

```bash
uv add "git+https://github.com/dpawani1/gameclean.git"
uv run gameclean --help
```

## DSC 190 Project Notes

GameClean is a Python command-line tool managed with `uv`. It solves a real personal problem: gaming and software cache files, leftover folders, logs, crash dumps, and old installers build up over time and can waste storage or affect performance.

The project is designed to be useful beyond the class. It has an interactive workflow for normal users, direct commands for power users, and a safety model that separates automatic cleanup from review-based deletion.
