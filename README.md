# GameClean

GameClean finds Windows gaming cache folders, leftover game folders, and old installer/package files so you can review what is using storage.

## Quick Start

Quick install:

```bash
uv tool install "git+https://github.com/dpawani1/gameclean.git"
```

Run:

```bash
gameclean scan
gameclean clean
```

Other commands:

```bash
gameclean leftovers
gameclean installers
```

GameClean works best from Windows Terminal, PowerShell, or WSL with access to `/mnt/c`.

## Windows Install

Recommended with uv:

```bash
uv tool install "git+https://github.com/dpawani1/gameclean.git"
```

Or with pipx:

```bash
pipx install "git+https://github.com/dpawani1/gameclean.git"
```

Then open any terminal and run:

```bash
gameclean scan
gameclean clean
gameclean leftovers
gameclean installers
```

If `gameclean` is not found, restart the terminal or make sure the uv/pipx scripts directory is on `PATH`.

## Development Usage

From inside the repository:

```bash
uv run gameclean scan
```

## Grading-Style Install

This project also supports installing into another uv project:

```bash
mkdir /tmp/gameclean-test
cd /tmp/gameclean-test
uv init
uv add "git+https://github.com/dpawani1/gameclean.git"
uv run gameclean --help
```
