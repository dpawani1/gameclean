from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import re
from pathlib import Path

from .utils import get_env_path, path_exists_dir

IMPORTANT_WINDOWS_ROOTS = ("LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "USERPROFILE")

SKIP_WINDOWS_USER_DIRS = {
    "all users",
    "default",
    "default user",
    "public",
}

WSL_WINDOWS_ROOT_CANDIDATES = [
    Path("/mnt/c/Users"),
    Path("/mnt/c/ProgramData"),
    Path("/mnt/c/Program Files"),
    Path("/mnt/c/Program Files (x86)"),
    Path("/mnt/c/XboxGames"),
    Path("/mnt/d/Games"),
    Path("/mnt/d/SteamLibrary"),
    Path("/mnt/d/Games/SteamLibrary"),
    Path("/mnt/e/Games"),
    Path("/mnt/e/SteamLibrary"),
    Path("/mnt/e/Games/SteamLibrary"),
]


@dataclass(frozen=True)
class RootDiagnostics:
    os_mode: str
    windows_user_profiles: list[Path]
    local_appdata_roots: list[Path]
    roaming_appdata_roots: list[Path]
    programdata_roots: list[Path]
    userprofile_roots: list[Path]
    steam_roots: list[Path]
    steam_library_roots: list[Path]
    existing_roots: list[Path]
    missing_windows_roots: list[str]


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
        *local_appdata_roots(),
        *roaming_appdata_roots(),
        *documents_roots(),
        *my_games_roots(),
        *saved_games_roots(),
        *programdata_roots(),
        env_join("LOCALAPPDATA", "Packages"),
        *common_windows_roots(),
        *wsl_non_user_windows_roots(),
    ]
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def root_diagnostics(custom_roots: list[Path] | None = None) -> RootDiagnostics:
    custom_roots = custom_roots or []
    steam = [*steam_roots(), *[root / "Steam" for root in custom_roots]]
    libraries: list[Path] = []
    for root in steam:
        libraries.extend(steam_libraries(root))
    roots = [
        *common_game_roots(),
        *steam,
        *libraries,
        *(custom_scan_roots(custom_roots)),
    ]
    missing = missing_important_windows_roots()
    return RootDiagnostics(
        detect_os_mode(),
        detected_windows_user_profiles(custom_roots),
        local_appdata_roots(custom_roots),
        roaming_appdata_roots(custom_roots),
        programdata_roots(custom_roots),
        userprofile_roots(custom_roots),
        first_existing(dedupe_paths(steam)),
        first_existing(dedupe_paths(libraries)),
        first_existing(dedupe_paths(roots)),
        missing,
    )


def detect_os_mode() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "Windows"
    if system == "linux":
        try:
            version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            version = ""
        if "microsoft" in version or "wsl" in version:
            return "WSL"
        return "Linux"
    return "unknown"


def missing_important_windows_roots() -> list[str]:
    missing: list[str] = []
    for env_name in IMPORTANT_WINDOWS_ROOTS:
        root = get_env_path(env_name)
        if root is None:
            missing.append(f"{env_name} not set")
        elif not path_exists_dir(root):
            missing.append(f"{env_name} missing: {root}")
    return missing


def wsl_windows_roots() -> list[Path]:
    return first_existing(dedupe_paths(WSL_WINDOWS_ROOT_CANDIDATES))


def wsl_non_user_windows_roots() -> list[Path]:
    return first_existing([path for path in WSL_WINDOWS_ROOT_CANDIDATES if path != Path("/mnt/c/Users")])


def wsl_user_roots() -> list[Path]:
    users_root = Path("/mnt/c/Users")
    if not path_exists_dir(users_root):
        return []
    return windows_user_scan_roots(users_root)


def windows_user_scan_roots(users_root: Path) -> list[Path]:
    candidates: list[Path] = []
    try:
        users = sorted(users_root.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return []

    for user_root in users:
        if not path_exists_dir(user_root):
            continue
        if user_root.name.lower() in SKIP_WINDOWS_USER_DIRS:
            continue
        candidates.extend(
            [
                user_root / "AppData" / "Local",
                user_root / "AppData" / "Roaming",
                user_root / "Documents",
                user_root / "Documents" / "My Games",
                user_root / "Saved Games",
                user_root / "Videos" / "Captures",
            ]
        )
    return first_existing(dedupe_paths(candidates))


def detected_windows_user_profiles(custom_roots: list[Path] | None = None) -> list[Path]:
    users_roots = [Path("/mnt/c/Users"), *[root / "Users" for root in custom_roots or []]]
    profiles: list[Path] = []
    for users_root in users_roots:
        if not path_exists_dir(users_root):
            continue
        try:
            children = sorted(users_root.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for child in children:
            if not path_exists_dir(child):
                continue
            if child.name.lower() in {"all users", "default", "default user"}:
                continue
            profiles.append(child)
    return first_existing(dedupe_paths(profiles))


def scan_windows_user_profiles(custom_roots: list[Path] | None = None) -> list[Path]:
    return [
        profile
        for profile in detected_windows_user_profiles(custom_roots)
        if profile.name.lower() not in SKIP_WINDOWS_USER_DIRS
    ]


def local_appdata_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [get_env_path("LOCALAPPDATA")]
    candidates.extend(profile / "AppData" / "Local" for profile in scan_windows_user_profiles(custom_roots))
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def roaming_appdata_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [get_env_path("APPDATA")]
    candidates.extend(profile / "AppData" / "Roaming" for profile in scan_windows_user_profiles(custom_roots))
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def programdata_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [get_env_path("PROGRAMDATA"), Path("/mnt/c/ProgramData")]
    candidates.extend(root / "ProgramData" for root in custom_roots or [])
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def userprofile_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [get_env_path("USERPROFILE")]
    candidates.extend(scan_windows_user_profiles(custom_roots))
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def documents_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [env_join("USERPROFILE", "Documents")]
    candidates.extend(profile / "Documents" for profile in scan_windows_user_profiles(custom_roots))
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def my_games_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [env_join("USERPROFILE", "Documents", "My Games")]
    candidates.extend(profile / "Documents" / "My Games" for profile in scan_windows_user_profiles(custom_roots))
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def saved_games_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    candidates = [env_join("USERPROFILE", "Saved Games")]
    candidates.extend(profile / "Saved Games" for profile in scan_windows_user_profiles(custom_roots))
    return first_existing(dedupe_paths([path for path in candidates if path is not None]))


def custom_scan_roots(custom_roots: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    for root in custom_roots:
        candidates.append(root)
        candidates.extend(
            [
                root / "ProgramData",
                root / "Program Files",
                root / "Program Files (x86)",
                root / "XboxGames",
                root / "Steam",
            ]
        )
        candidates.extend(windows_user_scan_roots(root / "Users"))
    return first_existing(dedupe_paths(candidates))


def steam_roots() -> list[Path]:
    roots = [
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Program Files/Steam"),
        Path("/mnt/c/Program Files (x86)/Steam"),
        Path("/mnt/c/Program Files/Steam"),
        Path("/mnt/d/SteamLibrary"),
        Path("/mnt/e/SteamLibrary"),
        Path("/mnt/d/Games/SteamLibrary"),
        Path("/mnt/e/Games/SteamLibrary"),
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
        libraries.extend(steam_vdf_paths(raw))

    # Older libraryfolders.vdf versions used numeric keys directly.
    for match in re.finditer(r'"\d+"\s+"([^"]+)"', text):
        raw = match.group(1).replace("\\\\", "\\")
        libraries.extend(steam_vdf_paths(raw))

    return first_existing(dedupe_paths(libraries))


def steam_vdf_paths(raw: str) -> list[Path]:
    normalized = raw.replace("\\", "/")
    paths = [Path(normalized)]
    drive_match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    if drive_match:
        drive = drive_match.group(1).lower()
        rest = drive_match.group(2)
        paths.append(Path("/mnt") / drive / rest)
    return paths


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
