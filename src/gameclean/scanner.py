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

    add(
        "Epic Games Launcher webcache",
        env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved", "webcache"),
        SAFE,
        "Known Epic Games Launcher web cache",
        "Epic",
    )
    epic_saved = env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved")
    if epic_saved and path_exists_dir(epic_saved):
        for path in safe_glob(epic_saved, "webcache_*"):
            add("Epic Games Launcher webcache", path, SAFE, "Known Epic Games Launcher web cache", "Epic")
    add(
        "Epic Games Launcher Logs",
        env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved", "Logs"),
        REVIEW,
        "Launcher logs; review before deleting",
        "Epic",
    )

    add("EA App Cache", env_join("LOCALAPPDATA", "Electronic Arts", "EA Desktop", "Cache"), SAFE, "Known EA App cache", "EA")
    add(
        "EA App Logs",
        env_join("LOCALAPPDATA", "Electronic Arts", "EA Desktop", "Logs"),
        REVIEW,
        "Launcher logs; review before deleting",
        "EA",
    )
    add("Origin Cache", env_join("LOCALAPPDATA", "Origin", "Cache"), SAFE, "Known Origin launcher cache", "EA")
    add(
        "Origin DownloadCache",
        env_join("PROGRAMDATA", "Origin", "DownloadCache"),
        SAFE,
        "Known Origin download cache",
        "EA",
    )
    add("Origin Roaming Cache", env_join("APPDATA", "Origin", "Cache"), SAFE, "Known Origin launcher cache", "EA")
    add(
        "EA Services License",
        env_join("PROGRAMDATA", "Electronic Arts", "EA Services", "License"),
        REVIEW,
        "License/session-related data; review only",
        "EA",
    )

    add("Battle.net Cache", env_join("PROGRAMDATA", "Battle.net", "Cache"), SAFE, "Known Battle.net cache", "Battle.net")
    add(
        "Blizzard Battle.net Cache",
        env_join("PROGRAMDATA", "Blizzard Entertainment", "Battle.net", "Cache"),
        SAFE,
        "Known Battle.net cache",
        "Battle.net",
    )
    add("Local Battle.net Cache", env_join("LOCALAPPDATA", "Battle.net", "Cache"), SAFE, "Known Battle.net cache", "Battle.net")
    add("Roaming Battle.net Cache", env_join("APPDATA", "Battle.net", "Cache"), SAFE, "Known Battle.net cache", "Battle.net")
    add(
        "Battle.net Logs",
        env_join("PROGRAMDATA", "Battle.net", "Logs"),
        REVIEW,
        "Launcher logs; review before deleting",
        "Battle.net",
    )

    add(
        "Riot Client Cache",
        env_join("LOCALAPPDATA", "Riot Games", "Riot Client", "Cache"),
        SAFE,
        "Known Riot Client cache",
        "Riot",
    )
    add(
        "Riot Client Logs",
        env_join("LOCALAPPDATA", "Riot Games", "Riot Client", "Logs"),
        REVIEW,
        "Launcher logs; review before deleting",
        "Riot",
    )
    add(
        "Riot Metadata",
        env_join("PROGRAMDATA", "Riot Games", "Metadata"),
        REVIEW,
        "Launcher metadata; review only",
        "Riot",
    )

    add(
        "Ubisoft Connect cache",
        env_join("LOCALAPPDATA", "Ubisoft Game Launcher", "cache"),
        SAFE,
        "Known Ubisoft Connect launcher cache",
        "Ubisoft",
    )
    for program_env in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        add(
            "Ubisoft Connect install cache",
            env_join(program_env, "Ubisoft", "Ubisoft Game Launcher", "cache"),
            SAFE,
            "Known Ubisoft Connect launcher cache",
            "Ubisoft",
        )
        add(
            "Ubisoft Connect logs",
            env_join(program_env, "Ubisoft", "Ubisoft Game Launcher", "logs"),
            REVIEW,
            "Launcher logs; review before deleting",
            "Ubisoft",
        )

    add("GOG Galaxy webcache", env_join("PROGRAMDATA", "GOG.com", "Galaxy", "webcache"), SAFE, "Known GOG Galaxy web cache", "GOG")
    add("GOG Galaxy local webcache", env_join("LOCALAPPDATA", "GOG.com", "Galaxy", "webcache"), SAFE, "Known GOG Galaxy web cache", "GOG")
    add(
        "GOG Galaxy Logs",
        env_join("LOCALAPPDATA", "GOG.com", "Galaxy", "Logs"),
        REVIEW,
        "Launcher logs; review before deleting",
        "GOG",
    )

    add("Minecraft logs", env_join("APPDATA", ".minecraft", "logs"), REVIEW, "Minecraft logs; review before deleting", "Minecraft")
    add(
        "Minecraft crash reports",
        env_join("APPDATA", ".minecraft", "crash-reports"),
        REVIEW,
        "Minecraft crash reports; review before deleting",
        "Minecraft",
    )
    add(
        "Minecraft assets",
        env_join("APPDATA", ".minecraft", "assets"),
        REVIEW,
        "Minecraft asset cache can be large; review only",
        "Minecraft",
    )

    add("Roblox logs", env_join("LOCALAPPDATA", "Roblox", "logs"), REVIEW, "Roblox logs; review before deleting", "Roblox")
    add(
        "Roblox Downloads",
        env_join("LOCALAPPDATA", "Roblox", "Downloads"),
        REVIEW,
        "Roblox downloads; review before deleting",
        "Roblox",
    )

    for discord in ("discord", "Discord", "discordcanary", "discordptb"):
        add(f"{discord} Cache", env_join("APPDATA", discord, "Cache"), REVIEW, "Gaming-adjacent overlay/app cache; review only", "Discord")
        add(
            f"{discord} Code Cache",
            env_join("APPDATA", discord, "Code Cache"),
            REVIEW,
            "Gaming-adjacent overlay/app cache; review only",
            "Discord",
        )
        add(
            f"{discord} GPUCache",
            env_join("APPDATA", discord, "GPUCache"),
            REVIEW,
            "Gaming-adjacent overlay/app cache; review only",
            "Discord",
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
                SAFE,
                "Known Epic Games Launcher web cache",
                "Epic",
            )
        )
        epic_saved = local / "EpicGamesLauncher" / "Saved"
        if path_exists_dir(epic_saved):
            for path in safe_glob(epic_saved, "webcache_*"):
                targets.append(ScanTarget("Epic Games Launcher webcache", path, SAFE, "Known Epic Games Launcher web cache", "Epic"))
    for programdata in programdata_roots([root]):
        targets.append(ScanTarget("Battle.net Cache", programdata / "Battle.net" / "Cache", SAFE, "Known Battle.net cache", "Battle.net"))
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
            for parts in GAME_CACHE_SUBPATHS:
                path = game_dir.joinpath(*parts)
                if is_dangerous_path(path):
                    continue
                targets.append(
                    ScanTarget(
                        f"{game_dir.name} {'/'.join(parts)}",
                        path,
                        REVIEW,
                        "Game cache/log/crash folder found by bounded fast scan; review before deleting",
                        "Game-specific",
                    )
                )
    return targets


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
        yield ScanTarget(candidate_name(path), path, category, reason, "Discovery")


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
