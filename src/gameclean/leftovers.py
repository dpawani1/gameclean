from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from .cleaner import is_deletion_allowed
from .paths import (
    detected_windows_user_profiles,
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
NOT_INSTALLED = "NOT_INSTALLED"
INSTALLED = "INSTALLED"
UNKNOWN = "UNKNOWN"
EXCLUDED = "EXCLUDED"
LEFTOVER_REASON_BROAD_CANDIDATE = "Large AppData/ProgramData folder that may be leftover; review before deleting."
LEFTOVER_REASON_INSTALLED = "Large AppData/ProgramData folder found, but the game/app appears to still be installed"
LEFTOVER_SAVE_RISK_REASON = (
    "HIGH RISK: known game folder may contain saves, configs, settings, or mods"
)

SKIP_FOLDER_NAMES = {
    "$recycle.bin",
    ".git",
    ".venv",
    "adobe",
    "amd",
    "arduino",
    "arduino-ide-updater",
    "balenaetcher",
    "battle.net",
    "blizzard entertainment",
    "bravesoftware",
    "code",
    "discord",
    "docker",
    "ea desktop",
    "electronic arts",
    "easyanticheat",
    "epic games",
    "epic games store",
    "epicgameslauncher",
    "fusion360",
    "google",
    "intel",
    "jetbrains",
    "lenovo",
    "matlab",
    "microsoft",
    "miniforge3",
    "mozilla",
    "mozilla firefox",
    "mysql",
    "my games",
    "node_modules",
    "nvidia",
    "nvidia corporation",
    "onedrive",
    "origin",
    "package cache",
    "packages",
    "pip",
    "programs",
    "python",
    "sublime text",
    "riot client",
    "riot games",
    "raspberry pi",
    "site-packages",
    "steam",
    "steamlibrary",
    "steamapps",
    "temp",
    "ubisoft",
    "ubisoft game launcher",
    "windowsapps",
    "wsl",
    "winutil",
    "xboxgames",
    "zoom",
}

SKIP_NAME_PREFIXES = {
    "com.adobe.",
    "mozilla-",
}

SKIP_PATH_TERMS = {
    "appdata/local/programs",
    "appdata/roaming/com.adobe.",
    "battle.net/cache",
    "ea desktop/cache",
    "epicgameslauncher/saved",
    "origin/cache",
    "steam/steamapps",
    "steamapps/common",
    "windowsapps",
}

SAVE_RISK_GAME_NAMES: set[str] = set()


ProgressCallback = Callable[[ScanProgress], None]


@dataclass(frozen=True)
class InstalledApp:
    name: str
    path: Path | None = None
    source: str = "generic"
    appid: str | None = None


@dataclass(frozen=True)
class InstallIndex:
    apps: tuple[InstalledApp, ...]
    has_sources: bool


def scan_leftovers(
    custom_roots: list[Path] | None = None,
    *,
    min_size: int = DEFAULT_MIN_SIZE,
    deep: bool = False,
    max_depth: int = 3,
    limit: int = 100,
    include_installed: bool = False,
    include_save_risk: bool = False,
    include_excluded: bool = False,
    progress: ProgressCallback | None = None,
) -> list[ScanResult]:
    roots = leftover_roots(custom_roots or [])
    skipped_roots = launcher_install_roots(custom_roots or [])
    install_index = build_install_index(custom_roots or [])
    user_names = detected_windows_user_names(custom_roots or [])
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
            excluded_reason = leftover_exclusion_reason(candidate, skipped_roots, user_names)
            if excluded_reason is not None:
                if include_excluded:
                    size = leftover_folder_size(candidate, skipped_roots)
                    if size >= min_size:
                        results.append(
                            ScanResult(
                                likely_app_name(candidate),
                                candidate,
                                size,
                                EXCLUDED,
                                excluded_reason,
                                "Leftover",
                                EXCLUDED,
                            )
                        )
                continue
            size = leftover_folder_size(candidate, skipped_roots)
            if size < min_size:
                continue
            app_name = likely_app_name(candidate)
            save_risk = is_save_risk_game(app_name)
            if save_risk and not include_save_risk:
                continue
            status, match = detect_install_status(app_name, install_index)
            if status == INSTALLED and not include_installed:
                continue
            result = ScanResult(
                app_name,
                candidate,
                size,
                REVIEW,
                leftover_reason(status, match, save_risk=save_risk),
                "Leftover",
                status,
                match.name if match else None,
            )
            if not is_deletion_allowed(result):
                continue
            results.append(result)
        if progress is not None:
            progress(ScanProgress("Checking leftover roots", index, len(roots), root))

    sorted_results = sorted(results, key=lambda result: result.size_bytes, reverse=True)
    if limit <= 0:
        return []
    return sorted_results[:limit]


def likely_app_name(path: Path) -> str:
    name = path.name.strip()
    if name.startswith("."):
        name = name[1:]
    return name or path.name


def leftover_reason(status: str, match: InstalledApp | None, *, save_risk: bool = False) -> str:
    if save_risk:
        return LEFTOVER_SAVE_RISK_REASON
    if status == INSTALLED:
        if match is not None:
            return f"{LEFTOVER_REASON_INSTALLED}: {match.name}"
        return LEFTOVER_REASON_INSTALLED
    return LEFTOVER_REASON_BROAD_CANDIDATE


def is_known_game_related(app_name: str) -> bool:
    return leftover_exclusion_reason(Path(app_name), [], set()) is None


def is_save_risk_game(app_name: str) -> bool:
    return normalize_name(app_name) in SAVE_RISK_GAME_NAMES


def detect_install_status(app_name: str, install_index: InstallIndex) -> tuple[str, InstalledApp | None]:
    match = find_installed_match(app_name, install_index.apps)
    if match is not None:
        return INSTALLED, match
    if install_index.has_sources:
        return NOT_INSTALLED, None
    return UNKNOWN, None


def find_installed_match(app_name: str, installed_apps: tuple[InstalledApp, ...]) -> InstalledApp | None:
    for app in installed_apps:
        if names_match(app_name, app.name):
            return app
        if app.path is not None and names_match(app_name, app.path.name):
            return app
    return None


def names_match(left: str, right: str) -> bool:
    left_tokens = normalized_tokens(left)
    right_tokens = normalized_tokens(right)
    if not left_tokens or not right_tokens:
        return False

    left_joined = "".join(left_tokens)
    right_joined = "".join(right_tokens)
    if left_joined == right_joined:
        return True
    if len(left_joined) >= 5 and left_joined in right_joined:
        return True
    if len(right_joined) >= 5 and right_joined in left_joined:
        return True

    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if left_set <= right_set or right_set <= left_set:
        return True

    overlap = left_set & right_set
    return bool(overlap) and len(overlap) >= min(len(left_set), len(right_set), 2)


def normalized_tokens(name: str) -> list[str]:
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in {"the", "game", "games", "launcher"}]
    if tokens[:2] == ["ea", "sports"]:
        tokens = tokens[2:]
    return tokens


def normalize_name(name: str) -> str:
    return "".join(normalized_tokens(name))


def build_install_index(custom_roots: list[Path] | None = None) -> InstallIndex:
    custom_roots = custom_roots or []
    apps: list[InstalledApp] = []
    source_paths: list[Path] = []

    steam_apps, steam_sources = steam_installed_apps(custom_roots)
    apps.extend(steam_apps)
    source_paths.extend(steam_sources)

    epic_apps, epic_sources = epic_installed_apps(custom_roots)
    apps.extend(epic_apps)
    source_paths.extend(epic_sources)

    folder_apps, folder_sources = folder_installed_apps(custom_roots)
    apps.extend(folder_apps)
    source_paths.extend(folder_sources)

    deduped: list[InstalledApp] = []
    seen: set[tuple[str, str]] = set()
    for app in apps:
        key = (normalize_name(app.name), app.path.as_posix().lower() if app.path else "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(app)
    return InstallIndex(tuple(deduped), bool(source_paths))


def steam_installed_apps(custom_roots: list[Path]) -> tuple[list[InstalledApp], list[Path]]:
    roots = [*steam_roots(), *[root / "Steam" for root in custom_roots]]
    libraries: list[Path] = []
    for root in roots:
        libraries.extend(steam_libraries(root))
    libraries = [path for path in dedupe_paths(libraries) if path_exists_dir(path)]

    apps: list[InstalledApp] = []
    sources: list[Path] = []
    for library in libraries:
        steamapps = library / "steamapps"
        if not path_exists_dir(steamapps):
            continue
        sources.append(steamapps)
        for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
            app = parse_steam_manifest(manifest, library)
            if app is not None:
                apps.append(app)
    return apps, sources


def parse_steam_manifest(path: Path, library: Path) -> InstalledApp | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    name_match = re.search(r'"name"\s+"([^"]+)"', text)
    appid_match = re.search(r'"appid"\s+"([^"]+)"', text)
    installdir_match = re.search(r'"installdir"\s+"([^"]+)"', text)
    name = name_match.group(1).strip() if name_match else ""
    appid = appid_match.group(1).strip() if appid_match else path.stem.replace("appmanifest_", "")
    install_path = library / "steamapps" / "common" / installdir_match.group(1).strip() if installdir_match else None
    if not name:
        name = install_path.name if install_path else appid
    return InstalledApp(name, install_path, "Steam", appid)


def epic_installed_apps(custom_roots: list[Path]) -> tuple[list[InstalledApp], list[Path]]:
    apps: list[InstalledApp] = []
    sources: list[Path] = []
    manifest_roots = [
        Path("C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests"),
        Path("/mnt/c/ProgramData/Epic/EpicGamesLauncher/Data/Manifests"),
    ]
    manifest_roots.extend(root / "ProgramData" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests" for root in custom_roots)
    for manifest_root in dedupe_paths(manifest_roots):
        if not path_exists_dir(manifest_root):
            continue
        sources.append(manifest_root)
        manifests = [*sorted(manifest_root.glob("*.item")), *sorted(manifest_root.glob("*.manifest"))]
        for manifest in manifests:
            app = parse_epic_manifest(manifest)
            if app is not None:
                apps.append(app)
    return apps, sources


def parse_epic_manifest(path: Path) -> InstalledApp | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return None
    name = str(data.get("DisplayName") or data.get("AppName") or data.get("CatalogItemId") or "").strip()
    install_location = str(data.get("InstallLocation") or "").strip()
    if not name and not install_location:
        return None
    return InstalledApp(name or Path(install_location).name, Path(install_location) if install_location else None, "Epic")


def folder_installed_apps(custom_roots: list[Path]) -> tuple[list[InstalledApp], list[Path]]:
    roots = generic_install_roots(custom_roots)
    apps: list[InstalledApp] = []
    sources: list[Path] = []
    for root in roots:
        if not path_exists_dir(root):
            continue
        sources.append(root)
        try:
            children = sorted(root.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for child in children:
            if path_exists_dir(child) and not should_skip_install_folder(child):
                apps.append(InstalledApp(child.name, child, "folder"))
    return apps, sources


def generic_install_roots(custom_roots: list[Path]) -> list[Path]:
    candidates = [
        Path("C:/Games"),
        Path("D:/Games"),
        Path("E:/Games"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("C:/XboxGames"),
        Path("D:/XboxGames"),
        Path("C:/Program Files/Epic Games"),
        Path("D:/Epic Games"),
        Path("C:/Program Files/EA Games"),
        Path("C:/Program Files/Electronic Arts"),
        Path("C:/Program Files (x86)/Origin Games"),
        Path("C:/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/games"),
        Path("C:/Program Files/Ubisoft"),
        Path("/mnt/c/Games"),
        Path("/mnt/c/Program Files"),
        Path("/mnt/c/Program Files (x86)"),
        Path("/mnt/c/XboxGames"),
        Path("/mnt/d/Games"),
        Path("/mnt/e/Games"),
        Path("/mnt/d/XboxGames"),
        Path("/mnt/d/SteamLibrary"),
        Path("/mnt/e/SteamLibrary"),
        Path("/mnt/c/Program Files/Epic Games"),
    ]
    for steam_root in steam_roots():
        candidates.extend(steam_libraries(steam_root))
    for root in custom_roots:
        candidates.extend(
            [
                root / "Games",
                root / "D" / "Games",
                root / "E" / "Games",
                root / "Program Files",
                root / "Program Files (x86)",
                root / "XboxGames",
                root / "Steam" / "steamapps" / "common",
                root / "Epic Games",
                root / "EA Games",
                root / "Program Files" / "EA Games",
                root / "Program Files" / "Electronic Arts",
                root / "Program Files (x86)" / "Origin Games",
                root / "Program Files (x86)" / "Ubisoft" / "Ubisoft Game Launcher" / "games",
            ]
        )
    return dedupe_paths(candidates)


def should_skip_install_folder(path: Path) -> bool:
    name = path.name.lower()
    if name in SKIP_FOLDER_NAMES:
        return True
    return "windowsapps" in path.as_posix().lower()


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
                if is_skipped_leftover_root(child, skipped_roots):
                    continue
                yield child
                if leftover_exclusion_reason(child, skipped_roots, set()) is not None:
                    continue
                stack.append((child, depth + 1))
            except OSError:
                continue


def should_skip_leftover_candidate(path: Path, skipped_roots: list[Path]) -> bool:
    return is_skipped_leftover_root(path, skipped_roots)


def is_skipped_leftover_root(path: Path, skipped_roots: list[Path]) -> bool:
    return any(path_is_or_under(path, skipped_root) for skipped_root in skipped_roots)


def leftover_exclusion_reason(path: Path, skipped_roots: list[Path], user_names: set[str]) -> str | None:
    if is_dangerous_path(path):
        return "Excluded by safety rule for save/config/mod/session/anti-cheat or protected install paths."
    name = path.name.lower()
    if name in SKIP_FOLDER_NAMES:
        return "Excluded known non-game software/system folder name."
    if any(name.startswith(prefix) for prefix in SKIP_NAME_PREFIXES):
        return "Excluded known non-game software/system folder pattern."
    text = path.as_posix().lower()
    if any(term in text for term in SKIP_PATH_TERMS):
        return "Excluded known non-game software/system path."
    if is_programdata_user_folder(path, user_names):
        return "Excluded ProgramData folder matching a Windows user profile name."
    return None


def detected_windows_user_names(custom_roots: list[Path]) -> set[str]:
    names = {profile.name.lower() for profile in detected_windows_user_profiles(custom_roots)}
    for env_name in ("USERNAME", "USER"):
        value = os.environ.get(env_name)
        if value:
            names.add(value.lower())
    return names


def is_programdata_user_folder(path: Path, user_names: set[str]) -> bool:
    if path.name.lower() not in user_names:
        return False
    parts = [part.lower() for part in path.parts]
    return len(parts) >= 2 and parts[-2] == "programdata"


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
    if any(name.startswith(prefix) for prefix in SKIP_NAME_PREFIXES):
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
