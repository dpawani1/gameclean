from __future__ import annotations

from collections.abc import Callable, Iterator
import os
from pathlib import Path

from .cleaner import is_deletion_allowed
from .paths import (
    dedupe_paths,
    local_appdata_roots,
    my_games_roots,
    programdata_roots,
    roaming_appdata_roots,
    saved_games_roots,
    steam_libraries,
    steam_roots,
)
from .scanner import REVIEW, ScanProgress, ScanResult
from .utils import is_dangerous_path, is_unsafe_link, path_exists_dir, resolved_key

DEFAULT_MIN_SIZE = 100 * 1024 * 1024
LEFTOVER_REASON = "Large game-related AppData folder that may remain after uninstall"

SKIP_FOLDER_NAMES = {
    "$recycle.bin",
    ".git",
    ".venv",
    "adobe",
    "amd",
    "battle.net",
    "blizzard entertainment",
    "code",
    "docker",
    "ea desktop",
    "electronic arts",
    "easyanticheat",
    "epic games",
    "epic games store",
    "epicgameslauncher",
    "intel",
    "microsoft",
    "my games",
    "node_modules",
    "nvidia",
    "nvidia corporation",
    "onedrive",
    "origin",
    "package cache",
    "packages",
    "pip",
    "riot client",
    "riot games",
    "site-packages",
    "steam",
    "steamlibrary",
    "steamapps",
    "temp",
    "ubisoft",
    "ubisoft game launcher",
    "windowsapps",
    "xboxgames",
    "zoom",
}

SKIP_PATH_TERMS = {
    "battle.net/cache",
    "ea desktop/cache",
    "epicgameslauncher/saved",
    "origin/cache",
    "steam/steamapps",
    "steamapps/common",
    "windowsapps",
}


ProgressCallback = Callable[[ScanProgress], None]


def scan_leftovers(
    custom_roots: list[Path] | None = None,
    *,
    min_size: int = DEFAULT_MIN_SIZE,
    deep: bool = False,
    max_depth: int = 3,
    limit: int = 100,
    progress: ProgressCallback | None = None,
) -> list[ScanResult]:
    roots = leftover_roots(custom_roots or [])
    skipped_roots = launcher_install_roots(custom_roots or [])
    results: list[ScanResult] = []
    seen: set[str] = set()

    if not roots and progress is not None:
        progress(ScanProgress("Checking leftover roots", 0, 0, Path()))

    for index, root in enumerate(roots, start=1):
        candidates = leftover_candidates_for_root(root, skipped_roots, deep=deep, max_depth=max_depth)
        for child_index, candidate in enumerate(candidates, start=1):
            if progress is not None:
                progress(ScanProgress(f"Checking {root}", child_index, len(candidates), candidate))
            key = resolved_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            size = leftover_folder_size(candidate, skipped_roots)
            if size < min_size:
                continue
            result = ScanResult(candidate.name, candidate, size, REVIEW, LEFTOVER_REASON, "Leftover")
            if not is_deletion_allowed(result):
                continue
            results.append(result)
        if progress is not None:
            progress(ScanProgress("Checking leftover roots", index, len(roots), root))

    sorted_results = sorted(results, key=lambda result: result.size_bytes, reverse=True)
    if limit <= 0:
        return []
    return sorted_results[:limit]


def leftover_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    custom_roots = custom_roots or []
    candidates = [
        *local_appdata_roots(custom_roots),
        *roaming_appdata_roots(custom_roots),
        *programdata_roots(custom_roots),
        *my_games_roots(custom_roots),
        *saved_games_roots(custom_roots),
        Path("C:/Games"),
        Path("D:/Games"),
        Path("E:/Games"),
        Path("/mnt/c/ProgramData"),
        Path("/mnt/d/Games"),
        Path("/mnt/e/Games"),
    ]
    for root in custom_roots:
        candidates.extend([root / "Games", root / "D" / "Games", root / "E" / "Games"])
    return [path for path in dedupe_paths(candidates) if path_exists_dir(path)]


def launcher_install_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    roots = [*steam_roots()]
    for steam_root in roots[:]:
        roots.extend(steam_libraries(steam_root))
    for root in custom_roots or []:
        roots.extend([root / "Steam", root / "Epic Games", root / "EA Games", root / "Battle.net"])
    return [path for path in dedupe_paths(roots) if path_exists_dir(path)]


def leftover_candidates_for_root(
    root: Path,
    skipped_roots: list[Path],
    *,
    deep: bool = False,
    max_depth: int = 3,
) -> list[Path]:
    if deep:
        return list(leftover_walk_dirs(root, skipped_roots, max_depth=max_depth))

    try:
        children = sorted(root.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return []

    candidates: list[Path] = []
    for child in children:
        if not path_exists_dir(child):
            continue
        if should_skip_leftover_candidate(child, skipped_roots):
            continue
        candidates.append(child)
    return candidates


def leftover_walk_dirs(root: Path, skipped_roots: list[Path], *, max_depth: int) -> Iterator[Path]:
    if not path_exists_dir(root):
        return

    stack: list[tuple[Path, int]] = [(root, 0)]
    seen: set[tuple[int, int]] = set()

    while stack:
        current, depth = stack.pop()
        try:
            stat = current.stat()
        except OSError:
            continue

        marker = (stat.st_dev, stat.st_ino)
        if marker in seen:
            continue
        seen.add(marker)

        if depth > 0:
            yield current

        if depth >= max_depth:
            continue

        try:
            children = sorted(os.scandir(current), key=lambda entry: entry.name.lower())
        except OSError:
            continue

        for entry in children:
            try:
                child = Path(entry.path)
                if not entry.is_dir(follow_symlinks=False) or entry.is_symlink() or is_unsafe_link(child):
                    continue
                if should_skip_leftover_candidate(child, skipped_roots):
                    continue
                stack.append((child, depth + 1))
            except OSError:
                continue


def should_skip_leftover_candidate(path: Path, skipped_roots: list[Path]) -> bool:
    if is_dangerous_path(path):
        return True
    name = path.name.lower()
    if name in SKIP_FOLDER_NAMES:
        return True
    text = path.as_posix().lower()
    if any(term in text for term in SKIP_PATH_TERMS):
        return True
    return any(path_is_or_under(path, skipped_root) for skipped_root in skipped_roots)


def leftover_folder_size(path: Path, skipped_roots: list[Path]) -> int:
    total = 0
    stack = [path]
    seen: set[tuple[int, int]] = set()

    while stack:
        current = stack.pop()
        try:
            stat = current.stat()
        except OSError:
            continue

        marker = (stat.st_dev, stat.st_ino)
        if marker in seen:
            continue
        seen.add(marker)

        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        entry_path = Path(entry.path)
                        if entry.is_symlink() or is_unsafe_link(entry_path):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if should_skip_leftover_size_dir(entry_path, skipped_roots):
                                continue
                            stack.append(entry_path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue

    return total


def should_skip_leftover_size_dir(path: Path, skipped_roots: list[Path]) -> bool:
    name = path.name.lower()
    if name in SKIP_FOLDER_NAMES:
        return True
    text = path.as_posix().lower()
    if any(term in text for term in SKIP_PATH_TERMS):
        return True
    return any(path_is_or_under(path, skipped_root) for skipped_root in skipped_roots)


def path_is_or_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False
