from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import os
from pathlib import Path

from .paths import (
    dedupe_paths,
    detected_windows_user_profiles,
    env_join,
    local_appdata_roots,
    programdata_roots,
    roaming_appdata_roots,
    steam_libraries,
    steam_roots,
    userprofile_roots,
)
from .scanner import REVIEW, ScanProgress
from .utils import is_unsafe_link, path_exists_dir, resolved_key

DEFAULT_INSTALLER_MIN_SIZE = 500 * 1024 * 1024

USER_INSTALLER_REASON = "Large installer/archive/package file found in user folder; review before deleting"
DRIVER_INSTALLER_REASON = "Large driver/update package found; review before deleting"
GAMING_INSTALLER_REASON = "Large installer/archive/package file found in gaming folder; review before deleting"

INSTALLER_EXTENSIONS = {
    ".exe",
    ".msi",
    ".zip",
    ".7z",
    ".rar",
    ".iso",
    ".patch",
    ".cab",
    ".tmp",
    ".dmg",
    ".tar",
    ".gz",
    ".xz",
}

DRIVER_UPDATE_TERMS = {
    "amd",
    "driver",
    "intel",
    "nvidia",
    "patch",
    "update",
}

SKIP_FOLDER_NAMES = {
    "$recycle.bin",
    ".git",
    ".venv",
    "__pycache__",
    "anti-cheat",
    "battleye",
    "captures",
    "config",
    "easyanticheat",
    "license",
    "login",
    "manifests",
    "mods",
    "node_modules",
    "profiles",
    "replays",
    "riot vanguard",
    "saved games",
    "savedata",
    "savegames",
    "saves",
    "screenshots",
    "session",
    "settings",
    "site-packages",
    "system volume information",
    "venv",
    "windowsapps",
}

SKIP_PATH_TERMS = {
    "/mnt/c/windows",
    "c:/windows",
    "anti-cheat",
    "appdata/local/packages",
    "battleye",
    "easyanticheat",
    "riot vanguard",
    "steamapps/common",
}


@dataclass(frozen=True)
class InstallerResult:
    name: str
    path: Path
    size_bytes: int
    extension: str
    reason: str
    category: str = REVIEW


@dataclass(frozen=True)
class InstallerRoot:
    path: Path
    source: str
    max_depth: int


ProgressCallback = Callable[[ScanProgress], None]


def scan_installers(
    custom_roots: list[Path] | None = None,
    *,
    min_size: int = DEFAULT_INSTALLER_MIN_SIZE,
    deep: bool = False,
    max_depth: int = 3,
    limit: int = 100,
    progress: ProgressCallback | None = None,
) -> list[InstallerResult]:
    roots = installer_roots(custom_roots or [], deep=deep, max_depth=max_depth)
    results: list[InstallerResult] = []
    seen: set[str] = set()

    if not roots and progress is not None:
        progress(ScanProgress("Checking installer roots", 0, 0, Path()))

    for index, root in enumerate(roots, start=1):
        for path in iter_installer_files(root.path, max_depth=root.max_depth, deep=deep):
            key = resolved_key(path)
            if key in seen:
                continue
            seen.add(key)
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size < min_size:
                continue
            result = installer_result(path, stat.st_size, root.source)
            if not is_installer_deletion_allowed(result):
                continue
            results.append(result)
        if progress is not None:
            progress(ScanProgress("Checking installer roots", index, len(roots), root.path))

    sorted_results = sorted(results, key=lambda result: result.size_bytes, reverse=True)
    if limit <= 0:
        return []
    return sorted_results[:limit]


def installer_roots(custom_roots: list[Path], *, deep: bool, max_depth: int) -> list[InstallerRoot]:
    roots: list[InstallerRoot] = []
    for root in user_installer_roots(custom_roots):
        roots.append(InstallerRoot(root, "user", 5))
    for root in gaming_installer_roots(custom_roots):
        roots.append(InstallerRoot(root, "gaming", 2))

    if deep:
        for root in deep_installer_roots(custom_roots):
            roots.append(InstallerRoot(root, "user", max_depth))

    by_path: dict[str, InstallerRoot] = {}
    for root in roots:
        if not path_exists_dir(root.path):
            continue
        key = str(root.path).lower()
        existing = by_path.get(key)
        if existing is not None and existing.max_depth >= root.max_depth:
            continue
        by_path[key] = root
    return list(by_path.values())


def user_installer_roots(custom_roots: list[Path]) -> list[Path]:
    candidates: list[Path | None] = [
        env_join("USERPROFILE", "Downloads"),
        env_join("USERPROFILE", "Desktop"),
        env_join("USERPROFILE", "Documents"),
        env_join("USERPROFILE", "Videos"),
        env_join("USERPROFILE", "OneDrive", "Desktop"),
        env_join("USERPROFILE", "OneDrive", "Documents"),
    ]
    for profile in detected_windows_user_profiles(custom_roots):
        candidates.extend(
            [
                profile / "Downloads",
                profile / "Desktop",
                profile / "Documents",
                profile / "Videos",
                profile / "OneDrive" / "Desktop",
                profile / "OneDrive" / "Documents",
            ]
        )
    return [path for path in dedupe_paths([path for path in candidates if path is not None]) if path_exists_dir(path)]


def gaming_installer_roots(custom_roots: list[Path]) -> list[Path]:
    candidates = [
        Path("C:/Games"),
        Path("D:/Games"),
        Path("E:/Games"),
        Path("D:/SteamLibrary"),
        Path("E:/SteamLibrary"),
        Path("/mnt/d/Games"),
        Path("/mnt/e/Games"),
        Path("/mnt/d/SteamLibrary"),
        Path("/mnt/e/SteamLibrary"),
    ]
    for root in custom_roots:
        candidates.extend(
            [
                root / "Games",
                root / "D" / "Games",
                root / "E" / "Games",
                root / "D" / "SteamLibrary",
                root / "E" / "SteamLibrary",
            ]
        )
    return [path for path in dedupe_paths(candidates) if path_exists_dir(path)]


def deep_installer_roots(custom_roots: list[Path]) -> list[Path]:
    candidates: list[Path] = [
        *local_appdata_roots(custom_roots),
        *roaming_appdata_roots(custom_roots),
        *programdata_roots(custom_roots),
        Path("C:/Games"),
        Path("D:/Games"),
        Path("E:/Games"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("/mnt/c/ProgramData"),
        Path("/mnt/c/Program Files"),
        Path("/mnt/c/Program Files (x86)"),
    ]
    for steam_root in steam_roots():
        candidates.extend(steam_libraries(steam_root))
    for root in userprofile_roots(custom_roots):
        candidates.extend([root / "AppData" / "Local", root / "AppData" / "Roaming"])
    for root in custom_roots:
        candidates.extend(
            [
                root / "ProgramData",
                root / "Program Files",
                root / "Program Files (x86)",
                root / "Games",
                root / "Steam",
            ]
        )
    return [path for path in dedupe_paths(candidates) if path_exists_dir(path)]


def iter_installer_files(root: Path, *, max_depth: int, deep: bool) -> Iterator[Path]:
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

        try:
            children = sorted(os.scandir(current), key=lambda entry: entry.name.lower())
        except OSError:
            continue

        for entry in children:
            try:
                child = Path(entry.path)
                if entry.is_symlink() or is_unsafe_link(child):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth and not should_skip_installer_dir(child, deep=deep):
                        stack.append((child, depth + 1))
                    continue
                if entry.is_file(follow_symlinks=False) and is_installer_file(child):
                    yield child
            except OSError:
                continue


def is_installer_file(path: Path) -> bool:
    return installer_extension(path) in INSTALLER_EXTENSIONS


def installer_extension(path: Path) -> str:
    return path.suffix.lower()


def installer_result(path: Path, size: int, source: str) -> InstallerResult:
    name_text = path.name.lower()
    reason = GAMING_INSTALLER_REASON if source == "gaming" else USER_INSTALLER_REASON
    if any(term in name_text for term in DRIVER_UPDATE_TERMS):
        reason = DRIVER_INSTALLER_REASON
    return InstallerResult(path.name, path, size, installer_extension(path), reason)


def should_skip_installer_dir(path: Path, *, deep: bool) -> bool:
    name = path.name.lower()
    if name in SKIP_FOLDER_NAMES:
        return True

    text = path.as_posix().lower()
    if not deep and "steamapps/common" in text:
        return True
    for term in SKIP_PATH_TERMS:
        if term == "appdata/local/packages" and deep:
            continue
        if term == "steamapps/common" and deep:
            continue
        if term in text:
            return True
    return False


def is_installer_deletion_allowed(result: InstallerResult) -> bool:
    if result.category != REVIEW:
        return False
    if result.size_bytes <= 0:
        return False
    if not result.path.is_file():
        return False
    return not should_skip_installer_delete_path(result.path)


def should_skip_installer_delete_path(path: Path) -> bool:
    text = path.as_posix().lower()
    if "/mnt/c/windows" in text or "c:/windows" in text:
        return True
    parts = {part.lower() for part in path.parts}
    dangerous_names = SKIP_FOLDER_NAMES - {"windowsapps"}
    return bool(parts & dangerous_names) or "windowsapps" in text
