from __future__ import annotations

import os
import re
from pathlib import Path

from .utils import get_env_path, path_exists_dir


def env_join(env_name: str, *parts: str) -> Path | None:
    root = get_env_path(env_name)
    if root is None:
        return None
    return root.joinpath(*parts)


def first_existing(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path_exists_dir(path)]


def common_windows_roots() -> list[Path]:
    roots = [
        Path("C:/Games"),
        Path("D:/Games"),
        Path("E:/Games"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("C:/XboxGames"),
        Path("D:/XboxGames"),
        Path("D:/SteamLibrary"),
        Path("E:/SteamLibrary"),
    ]

    system_drive = os.environ.get("SystemDrive")
    if system_drive:
        roots.extend(
            [
                Path(f"{system_drive}/Games"),
                Path(f"{system_drive}/Program Files"),
                Path(f"{system_drive}/Program Files (x86)"),
                Path(f"{system_drive}/XboxGames"),
            ]
        )

    return first_existing(dedupe_paths(roots))


def common_game_roots() -> list[Path]:
    candidates: list[Path | None] = [
        get_env_path("LOCALAPPDATA"),
        get_env_path("APPDATA"),
        env_join("USERPROFILE", "Documents"),
        env_join("USERPROFILE", "Documents", "My Games"),
        env_join("USERPROFILE", "Saved Games"),
        get_env_path("PROGRAMDATA"),
        env_join("LOCALAPPDATA", "Packages"),
        *common_windows_roots(),
    ]
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def steam_roots() -> list[Path]:
    roots = [
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Program Files/Steam"),
    ]

    program_files_x86 = get_env_path("PROGRAMFILES(X86)")
    if program_files_x86:
        roots.append(program_files_x86 / "Steam")
    program_files = get_env_path("PROGRAMFILES")
    if program_files:
        roots.append(program_files / "Steam")

    registry_root = steam_root_from_registry()
    if registry_root:
        roots.append(registry_root)

    return first_existing(dedupe_paths(roots))


def steam_libraries(steam_root: Path) -> list[Path]:
    libraries = [steam_root]
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return first_existing(dedupe_paths(libraries))

    for match in re.finditer(r'"path"\s+"([^"]+)"', text):
        raw = match.group(1).replace("\\\\", "\\")
        libraries.append(Path(raw))

    # Older libraryfolders.vdf versions used numeric keys directly.
    for match in re.finditer(r'"\d+"\s+"([^"]+)"', text):
        raw = match.group(1).replace("\\\\", "\\")
        libraries.append(Path(raw))

    return first_existing(dedupe_paths(libraries))


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def steam_root_from_registry() -> Path | None:
    try:
        import winreg
    except ImportError:
        return None

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    ]
    for hive, key_name in keys:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                value, _ = winreg.QueryValueEx(key, "SteamPath")
                return Path(value)
        except OSError:
            continue
    return None
