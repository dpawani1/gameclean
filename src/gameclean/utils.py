from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path


SKIP_DIR_NAMES = {
    "$recycle.bin",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "site-packages",
    "venv",
}

SKIP_PATH_PARTS = {
    "$recycle.bin",
    "program files/windowsapps",
    "windows",
    "windowsapps",
}

DANGEROUS_TERMS = {
    "battleye",
    "captures",
    "config",
    "easyanticheat",
    "game installation root",
    "license",
    "login",
    "manifest",
    "manifests",
    "mod",
    "mods",
    "profiles",
    "replays",
    "riot vanguard",
    "savegames",
    "saved games",
    "savedata",
    "saves",
    "screenshots",
    "session",
    "settings",
    "steamapps/common",
    "user data",
    "windowsapps",
    "workshop/content",
}

CACHE_LIKE_NAMES = {
    "cache",
    "caches",
    "code cache",
    "crashes",
    "crash-reports",
    "crashdumps",
    "deriveddatacache",
    "downloads",
    "dxcache",
    "glcache",
    "gpucache",
    "logs",
    "pipelinecache",
    "pso",
    "shadercache",
    "temp",
    "tmp",
    "vkcache",
    "webcache",
}


def get_env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser()


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def normalize_path_text(path: Path) -> str:
    return path.as_posix().lower()


def path_exists_dir(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and not is_unsafe_link(path)
    except OSError:
        return False


def is_unsafe_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", lambda: False)
        return path.is_symlink() or is_junction()
    except OSError:
        return True


def folder_size(path: Path) -> int:
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
                            if should_skip_dir(entry.name, entry_path):
                                continue
                            stack.append(entry_path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue

    return total


def should_skip_dir(name: str, path: Path) -> bool:
    lowered_name = name.lower()
    if lowered_name in SKIP_DIR_NAMES:
        return True
    parts = [part.lower() for part in path.parts]
    joined = "/".join(parts)
    for skipped in SKIP_PATH_PARTS:
        if "/" in skipped:
            if skipped in joined:
                return True
        elif skipped in parts:
            return True
    return False


def safe_walk_dirs(root: Path, max_depth: int = 5) -> Iterator[Path]:
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
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        child = Path(entry.path)
                        if (
                            not entry.is_dir(follow_symlinks=False)
                            or entry.is_symlink()
                            or is_unsafe_link(child)
                        ):
                            continue
                        if should_skip_dir(entry.name, child):
                            continue
                        stack.append((child, depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue


def is_cache_like_dir(path: Path) -> bool:
    name = path.name.lower()
    if name in CACHE_LIKE_NAMES:
        return True
    return (
        name.startswith("webcache_")
        or name.endswith("cache")
        or name.endswith("logs")
        or name.endswith("crashdumps")
    )


def is_dangerous_path(path: Path) -> bool:
    text = normalize_path_text(path)
    parts = {part.lower() for part in path.parts}
    if "saved" in parts and path.name.lower() not in {"logs", "crashes", "deriveddatacache"}:
        return True
    return any(term in text for term in DANGEROUS_TERMS)


def resolved_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=True)).lower()
    except OSError:
        return str(path.absolute()).lower()
