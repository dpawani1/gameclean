from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import os
from pathlib import Path
import re

from .paths import (
    common_game_roots,
    custom_scan_roots,
    env_join,
    local_appdata_roots,
    my_games_roots,
    programdata_roots,
    roaming_appdata_roots,
    saved_games_roots,
    steam_libraries,
    steam_roots,
)
from .utils import (
    folder_size,
    is_cache_like_dir,
    is_dangerous_path,
    path_exists_dir,
    resolved_key,
    safe_walk_dirs,
)

SAFE = "SAFE"
REVIEW = "REVIEW"
SKIP = "SKIP"


@dataclass(frozen=True)
class ScanResult:
    name: str
    path: Path
    size_bytes: int
    category: str
    reason: str
    source: str
    install_status: str = "UNKNOWN"
    installed_match: str | None = None


@dataclass(frozen=True)
class ScanTarget:
    name: str
    path: Path
    category: str
    reason: str
    source: str


@dataclass(frozen=True)
class ScanProgress:
    label: str
    current: int
    total: int
    path: Path


ProgressCallback = Callable[[ScanProgress], None]


def scan(
    custom_roots: list[Path] | None = None,
    *,
    deep: bool = False,
    max_depth: int = 5,
    review_limit: int = 100,
    progress: ProgressCallback | None = None,
) -> list[ScanResult]:
    custom_roots = custom_roots or []
    results: list[ScanResult] = []
    seen: set[str] = set()
    review_count = 0

    direct_targets = [*known_targets(custom_roots), *steam_targets(custom_roots), *game_specific_targets(custom_roots)]
    for index, target in enumerate(direct_targets, start=1):
        review_count += add_result(results, seen, target, review_count, review_limit)
        if progress is not None:
            progress(ScanProgress("Checking known paths", index, len(direct_targets), target.path))

    if deep and review_count < review_limit:
        roots = deep_discovery_roots(custom_roots)
        for index, root in enumerate(roots, start=1):
            if progress is not None:
                progress(ScanProgress("Scanning root", index, len(roots), root))
            for target in deep_discovery_targets_for_root(root, seen, max_depth=max_depth):
                if target.category == REVIEW and review_count >= review_limit:
                    break
                review_count += add_result(results, seen, target, review_count, review_limit)
            if review_count >= review_limit:
                break

    return sorted(results, key=lambda result: result.size_bytes, reverse=True)


def add_result(
    results: list[ScanResult],
    seen: set[str],
    target: ScanTarget,
    review_count: int,
    review_limit: int,
) -> int:
    if target.category == SKIP or not path_exists_dir(target.path):
        return 0

    if target.category == REVIEW and review_count >= review_limit:
        return 0

    key = resolved_key(target.path)
    if key in seen:
        return 0
    seen.add(key)

    results.append(
        ScanResult(
            name=target.name,
            path=target.path,
            size_bytes=folder_size(target.path),
            category=target.category,
            reason=target.reason,
            source=target.source,
        )
    )
    return 1 if target.category == REVIEW else 0


def known_targets(custom_roots: list[Path] | None = None) -> list[ScanTarget]:
    targets: list[ScanTarget] = []

    def add(name: str, path: Path | None, category: str, reason: str, source: str) -> None:
        if path is not None:
            targets.append(ScanTarget(name, path, category, reason, source))

    for target in gpu_targets(custom_roots):
        targets.append(target)

    launcher_reason = LAUNCHER_REASON

    add(
        "Epic Games Launcher webcache",
        env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved", "webcache"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    epic_saved = env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved")
    if epic_saved and path_exists_dir(epic_saved):
        for path in safe_glob(epic_saved, "webcache_*"):
            add("Epic Games Launcher webcache", path, REVIEW, launcher_reason, "Launcher")
    add(
        "Epic Games Launcher Logs",
        env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved", "Logs"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )

    add("EA App Cache", env_join("LOCALAPPDATA", "Electronic Arts", "EA Desktop", "Cache"), REVIEW, launcher_reason, "Launcher")
    add(
        "EA App Logs",
        env_join("LOCALAPPDATA", "Electronic Arts", "EA Desktop", "Logs"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    add("Origin Cache", env_join("LOCALAPPDATA", "Origin", "Cache"), REVIEW, launcher_reason, "Launcher")
    add(
        "Origin DownloadCache",
        env_join("PROGRAMDATA", "Origin", "DownloadCache"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    add("Origin Roaming Cache", env_join("APPDATA", "Origin", "Cache"), REVIEW, launcher_reason, "Launcher")
    add(
        "EA Services License",
        env_join("PROGRAMDATA", "Electronic Arts", "EA Services", "License"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )

    add("Battle.net Cache", env_join("PROGRAMDATA", "Battle.net", "Cache"), REVIEW, launcher_reason, "Launcher")
    add(
        "Blizzard Battle.net Cache",
        env_join("PROGRAMDATA", "Blizzard Entertainment", "Battle.net", "Cache"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    add("Local Battle.net Cache", env_join("LOCALAPPDATA", "Battle.net", "Cache"), REVIEW, launcher_reason, "Launcher")
    add("Roaming Battle.net Cache", env_join("APPDATA", "Battle.net", "Cache"), REVIEW, launcher_reason, "Launcher")
    add(
        "Battle.net Logs",
        env_join("PROGRAMDATA", "Battle.net", "Logs"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )

    add(
        "Riot Client Cache",
        env_join("LOCALAPPDATA", "Riot Games", "Riot Client", "Cache"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    add(
        "Riot Client Logs",
        env_join("LOCALAPPDATA", "Riot Games", "Riot Client", "Logs"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    add(
        "Riot Metadata",
        env_join("PROGRAMDATA", "Riot Games", "Metadata"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )

    add(
        "Ubisoft Connect cache",
        env_join("LOCALAPPDATA", "Ubisoft Game Launcher", "cache"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )
    for program_env in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        add(
            "Ubisoft Connect install cache",
            env_join(program_env, "Ubisoft", "Ubisoft Game Launcher", "cache"),
            REVIEW,
            launcher_reason,
            "Launcher",
        )
        add(
            "Ubisoft Connect logs",
            env_join(program_env, "Ubisoft", "Ubisoft Game Launcher", "logs"),
            REVIEW,
            launcher_reason,
            "Launcher",
        )

    add("GOG Galaxy webcache", env_join("PROGRAMDATA", "GOG.com", "Galaxy", "webcache"), REVIEW, launcher_reason, "Launcher")
    add("GOG Galaxy local webcache", env_join("LOCALAPPDATA", "GOG.com", "Galaxy", "webcache"), REVIEW, launcher_reason, "Launcher")
    add(
        "GOG Galaxy Logs",
        env_join("LOCALAPPDATA", "GOG.com", "Galaxy", "Logs"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )

    game_reason = GAME_SPECIFIC_REASON

    add("Minecraft logs", env_join("APPDATA", ".minecraft", "logs"), REVIEW, game_reason, "Game-specific")
    add(
        "Minecraft crash reports",
        env_join("APPDATA", ".minecraft", "crash-reports"),
        REVIEW,
        game_reason,
        "Game-specific",
    )
    add(
        "Minecraft assets",
        env_join("APPDATA", ".minecraft", "assets"),
        REVIEW,
        game_reason,
        "Game-specific",
    )

    add("Roblox logs", env_join("LOCALAPPDATA", "Roblox", "logs"), REVIEW, launcher_reason, "Launcher")
    add(
        "Roblox Downloads",
        env_join("LOCALAPPDATA", "Roblox", "Downloads"),
        REVIEW,
        launcher_reason,
        "Launcher",
    )

    for discord in ("discord", "Discord", "discordcanary", "discordptb"):
        add(f"{discord} Cache", env_join("APPDATA", discord, "Cache"), REVIEW, OTHER_APP_REASON, "Other app")
        add(
            f"{discord} Code Cache",
            env_join("APPDATA", discord, "Code Cache"),
            REVIEW,
            OTHER_APP_REASON,
            "Other app",
        )
        add(
            f"{discord} GPUCache",
            env_join("APPDATA", discord, "GPUCache"),
            REVIEW,
            OTHER_APP_REASON,
            "Other app",
        )

    for root in custom_roots or []:
        targets.extend(custom_known_targets(root))

    return targets


def custom_known_targets(root: Path) -> list[ScanTarget]:
    targets: list[ScanTarget] = []
    for local in local_appdata_roots([root]):
        targets.append(
            ScanTarget(
                "Epic Games Launcher webcache",
                local / "EpicGamesLauncher" / "Saved" / "webcache",
                REVIEW,
                LAUNCHER_REASON,
                "Launcher",
            )
        )
        epic_saved = local / "EpicGamesLauncher" / "Saved"
        if path_exists_dir(epic_saved):
            for path in safe_glob(epic_saved, "webcache_*"):
                targets.append(
                    ScanTarget(
                        "Epic Games Launcher webcache",
                        path,
                        REVIEW,
                        LAUNCHER_REASON,
                        "Launcher",
                    )
                )
    for programdata in programdata_roots([root]):
        targets.append(
            ScanTarget(
                "Battle.net Cache",
                programdata / "Battle.net" / "Cache",
                REVIEW,
                LAUNCHER_REASON,
                "Launcher",
            )
        )
    return targets


def gpu_targets(custom_roots: list[Path] | None = None) -> list[ScanTarget]:
    targets: list[ScanTarget] = []
    known_gpu_reason = "Known GPU shader cache"
    local_paths = [
        ("NVIDIA DXCache", "NVIDIA/DXCache", SAFE),
        ("NVIDIA GLCache", "NVIDIA/GLCache", SAFE),
        ("NVIDIA NV_Cache", "NVIDIA Corporation/NV_Cache", SAFE),
        ("AMD DxCache", "AMD/DxCache", SAFE),
        ("AMD GLCache", "AMD/GLCache", SAFE),
        ("AMD VkCache", "AMD/VkCache", SAFE),
        ("Intel ShaderCache", "Intel/ShaderCache", SAFE),
        ("Intel ComputeCache", "Intel/ComputeCache", SAFE),
    ]
    for root in local_appdata_roots(custom_roots):
        for name, relative, category in local_paths:
            targets.append(ScanTarget(name, root / Path(relative), category, known_gpu_reason, "GPU"))

    for root in programdata_roots(custom_roots):
        targets.append(
            ScanTarget(
                "NVIDIA ProgramData NV_Cache",
                root / "NVIDIA Corporation" / "NV_Cache",
                SAFE,
                known_gpu_reason,
                "GPU",
            )
        )
        targets.append(
            ScanTarget(
                "NVIDIA Downloader",
                root / "NVIDIA Corporation" / "Downloader",
                REVIEW,
                "NVIDIA driver download cache; review before deleting",
                "GPU",
            )
        )
        amd_root = root / "AMD"
        if path_exists_dir(amd_root):
            for child in safe_glob(amd_root, "*"):
                if child.is_dir() and is_cache_like_dir(child):
                    targets.append(ScanTarget(f"AMD ProgramData {child.name}", child, REVIEW, "AMD cache-like ProgramData folder; review only", "GPU"))

    return targets


def steam_targets(custom_roots: list[Path] | None = None) -> list[ScanTarget]:
    targets: list[ScanTarget] = []
    roots = [*steam_roots(), *[custom_root / "Steam" for custom_root in custom_roots or []]]
    for root in roots:
        # Steam's htmlcache lives below config, but the leaf is a documented cache folder.
        explicit = [
            ("Steam appcache", root / "appcache", SAFE, "Known Steam app cache"),
            ("Steam depotcache", root / "depotcache", SAFE, "Known Steam depot cache"),
            ("Steam htmlcache", root / "config" / "htmlcache", SAFE, "Known Steam browser html cache"),
            ("Steam logs", root / "logs", REVIEW, "Steam logs; review before deleting"),
        ]
        for name, path, category, reason in explicit:
            targets.append(ScanTarget(name, path, category, reason, "Steam"))

        for library in steam_libraries(root):
            targets.extend(steam_shadercache_targets(library))
            library_targets = [
                ("Steam downloading", library / "steamapps" / "downloading", REVIEW, "Steam download staging folder; review only"),
                ("Steam temp", library / "steamapps" / "temp", REVIEW, "Steam temporary folder; review only"),
                (
                    "Steam Workshop downloads",
                    library / "steamapps" / "workshop" / "downloads",
                    REVIEW,
                    "Steam Workshop download staging folder; review only",
                ),
                (
                    "Steam Workshop temp",
                    library / "steamapps" / "workshop" / "temp",
                    REVIEW,
                    "Steam Workshop temporary folder; review only",
                ),
            ]
            for name, path, category, reason in library_targets:
                targets.append(ScanTarget(name, path, category, reason, "Steam"))

    return targets


def steam_shadercache_targets(library: Path) -> list[ScanTarget]:
    shadercache = library / "steamapps" / "shadercache"
    app_names = steam_app_names(library)
    targets: list[ScanTarget] = []
    if path_exists_dir(shadercache):
        try:
            children = sorted(shadercache.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            children = []
        for child in children:
            if not path_exists_dir(child):
                continue
            appid = child.name
            name = app_names.get(appid, f"Steam app {appid}")
            targets.append(
                ScanTarget(
                    f"{name} shadercache",
                    child,
                    SAFE,
                    "Steam per-game shader cache",
                    "Steam",
                )
            )
        if not targets:
            targets.append(ScanTarget("Steam shadercache", shadercache, SAFE, "Known Steam shader cache", "Steam"))
    return targets


def steam_app_names(library: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    steamapps = library / "steamapps"
    try:
        manifests = list(steamapps.glob("appmanifest_*.acf"))
    except OSError:
        return names
    for manifest in manifests:
        try:
            text = manifest.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        appid_match = re.search(r'"appid"\s+"([^"]+)"', text)
        name_match = re.search(r'"name"\s+"([^"]+)"', text)
        fallback = manifest.stem.replace("appmanifest_", "")
        appid = appid_match.group(1) if appid_match else fallback
        if name_match:
            names[appid] = name_match.group(1)
    return names


GAME_CACHE_SUBPATHS = (
    ("Cache",),
    ("cache",),
    ("Caches",),
    ("Code Cache",),
    ("ShaderCache",),
    ("shadercache",),
    ("Saved", "DerivedDataCache"),
    ("Saved", "Logs"),
    ("Saved", "Crashes"),
    ("Saved", "CrashDumps"),
    ("Logs",),
    ("logs",),
    ("CrashDumps",),
    ("crashdumps",),
    ("Temp",),
    ("temp",),
)

LAUNCHER_APPDATA_NAMES = {
    "battle.net",
    "blizzard entertainment",
    "curseforge",
    "ea",
    "electronic arts",
    "epicgameslauncher",
    "faceit",
    "gog.com",
    "minecraft launcher",
    "modrinth",
    "origin",
    "riot games",
    "riot-client-ux",
    "roblox",
    "ubisoft game launcher",
}

GAME_APPDATA_NAMES = {
    ".minecraft",
    "cassettebeasts",
    "dungeons",
    "ea sports fc 25",
    "fortnitegame",
    "hogwarts legacy",
    "marvel",
    "marvelrivals_launcher",
    "multiversus",
    "pioneergame",
    "slaythespire2",
    "valorant",
}

GAME_SPECIFIC_REASON = "Game cache/log/crash folder found by bounded scan; review before deleting."
LAUNCHER_REASON = "Gaming launcher cache/log folder; review before deleting unless later confirmed safe."
OTHER_APP_REASON = "Cache/log folder found in AppData; not clearly gaming-related, review before deleting."


def game_specific_targets(custom_roots: list[Path] | None = None) -> list[ScanTarget]:
    targets: list[ScanTarget] = []
    roots = [
        *local_appdata_roots(custom_roots),
        *roaming_appdata_roots(custom_roots),
        *my_games_roots(custom_roots),
        *saved_games_roots(custom_roots),
    ]
    for root in roots:
        if not path_exists_dir(root):
            continue
        try:
            children = sorted(root.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for game_dir in children:
            if not path_exists_dir(game_dir):
                continue
            if is_dangerous_path(game_dir):
                continue
            source = review_source_for_root_child(root, game_dir)
            reason = review_reason_for_source(source)
            for parts in GAME_CACHE_SUBPATHS:
                path = game_dir.joinpath(*parts)
                if is_dangerous_path(path):
                    continue
                targets.append(
                    ScanTarget(
                        f"{game_dir.name} {'/'.join(parts)}",
                        path,
                        REVIEW,
                        reason,
                        source,
                    )
                )
    return targets


def review_source_for_root_child(root: Path, child: Path) -> str:
    if is_appdata_root(root):
        return appdata_source_for_dir(child)
    return "Game-specific"


def is_appdata_root(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return len(parts) >= 2 and parts[-2:] in (["appdata", "local"], ["appdata", "roaming"])


def appdata_source_for_dir(path: Path) -> str:
    name = path.name.lower()
    if name in LAUNCHER_APPDATA_NAMES:
        return "Launcher"
    if name in GAME_APPDATA_NAMES or looks_like_game_appdata_dir(path):
        return "Game-specific"
    return "Other app"


def looks_like_game_appdata_dir(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith("game"):
        return True
    saved = path / "Saved"
    if not path_exists_dir(saved):
        return False
    unreal_cache_names = {"DerivedDataCache", "Logs", "Crashes"}
    return any(path_exists_dir(saved / cache_name) for cache_name in unreal_cache_names)


def review_reason_for_source(source: str) -> str:
    if source == "Game-specific":
        return GAME_SPECIFIC_REASON
    if source == "Launcher":
        return LAUNCHER_REASON
    return OTHER_APP_REASON


def deep_discovery_targets(
    existing_keys: set[str],
    custom_roots: list[Path] | None = None,
    *,
    max_depth: int = 5,
) -> Iterator[ScanTarget]:
    for root in deep_discovery_roots(custom_roots):
        yield from deep_discovery_targets_for_root(root, existing_keys, max_depth=max_depth)


def deep_discovery_roots(custom_roots: list[Path] | None = None) -> list[Path]:
    return [*common_game_roots(), *custom_scan_roots(custom_roots or [])]


def deep_discovery_targets_for_root(root: Path, existing_keys: set[str], *, max_depth: int = 5) -> Iterator[ScanTarget]:
    root_max_depth = max_depth
    if root.name.lower() in {"programdata", "games", "xboxgames"}:
        root_max_depth = min(root_max_depth, 4)
    for path in safe_walk_dirs(root, max_depth=root_max_depth):
        if resolved_key(path) in existing_keys:
            continue
        if has_reported_descendant(path, existing_keys):
            continue
        category, reason = classify_candidate(path)
        if category == SKIP:
            continue
        source = discovery_source_for_path(path)
        if source in {"Game-specific", "Launcher", "Other app"}:
            reason = review_reason_for_source(source)
        yield ScanTarget(candidate_name(path), path, category, reason, source)


def has_reported_descendant(path: Path, existing_keys: set[str]) -> bool:
    prefix = resolved_key(path).rstrip(os.sep) + os.sep
    return any(key.startswith(prefix) for key in existing_keys)


def classify_candidate(path: Path) -> tuple[str, str]:
    if not is_cache_like_dir(path):
        return SKIP, ""

    # Deep discovery is intentionally conservative: saves, configs, mods,
    # installs, and protected app data are not cleanable candidates.
    if is_dangerous_path(path):
        return SKIP, ""

    parts = [part.lower() for part in path.parts]
    if "saved" in parts and path.name.lower() in {"deriveddatacache", "logs", "crashes"}:
        return REVIEW, "Unreal-style cache/log folder found in game data; review before deleting"
    if "packages" in parts:
        return REVIEW, "Microsoft Store/Xbox package cache-like folder; review only"
    return REVIEW, "Cache-like folder found in gaming/user data; review before deleting"


def discovery_source_for_path(path: Path) -> str:
    owner = appdata_owner_dir(path)
    if owner is not None:
        return appdata_source_for_dir(owner)
    return "Game-specific"


def appdata_owner_dir(path: Path) -> Path | None:
    parts = path.parts
    lowered = [part.lower() for part in parts]
    for index in range(len(parts) - 2):
        if lowered[index] == "appdata" and lowered[index + 1] in {"local", "roaming"}:
            return Path(*parts[: index + 3])
    return None


def candidate_name(path: Path) -> str:
    parent = path.parent.name
    if parent and parent.lower() not in {"saved", "appdata", "local", "roaming", "programdata"}:
        return f"{parent} {path.name}"
    return path.name


def safe_glob(root: Path, pattern: str) -> Iterator[Path]:
    try:
        yield from root.glob(pattern)
    except OSError:
        return
