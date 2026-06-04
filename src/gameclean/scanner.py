from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import common_game_roots, env_join, steam_libraries, steam_roots
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


def scan() -> list[ScanResult]:
    results: list[ScanResult] = []
    seen: set[str] = set()

    for target in known_targets():
        add_result(results, seen, target)

    for target in steam_targets():
        add_result(results, seen, target)

    for target in broad_discovery_targets(seen):
        add_result(results, seen, target)

    return sorted(results, key=lambda result: result.size_bytes, reverse=True)


def add_result(results: list[ScanResult], seen: set[str], target: ScanTarget) -> None:
    if target.category == SKIP or not path_exists_dir(target.path):
        return

    key = resolved_key(target.path)
    if key in seen:
        return
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


def known_targets() -> list[ScanTarget]:
    targets: list[ScanTarget] = []

    def add(name: str, path: Path | None, category: str, reason: str, source: str) -> None:
        if path is not None:
            targets.append(ScanTarget(name, path, category, reason, source))

    known_gpu_reason = "Known GPU shader cache"
    add("NVIDIA DXCache", env_join("LOCALAPPDATA", "NVIDIA", "DXCache"), SAFE, known_gpu_reason, "GPU")
    add("NVIDIA GLCache", env_join("LOCALAPPDATA", "NVIDIA", "GLCache"), SAFE, known_gpu_reason, "GPU")
    add(
        "NVIDIA NV_Cache",
        env_join("LOCALAPPDATA", "NVIDIA Corporation", "NV_Cache"),
        SAFE,
        known_gpu_reason,
        "GPU",
    )
    add(
        "NVIDIA ProgramData NV_Cache",
        env_join("PROGRAMDATA", "NVIDIA Corporation", "NV_Cache"),
        SAFE,
        known_gpu_reason,
        "GPU",
    )
    add("AMD DxCache", env_join("LOCALAPPDATA", "AMD", "DxCache"), SAFE, known_gpu_reason, "GPU")
    add("AMD GLCache", env_join("LOCALAPPDATA", "AMD", "GLCache"), SAFE, known_gpu_reason, "GPU")
    add("AMD VkCache", env_join("LOCALAPPDATA", "AMD", "VkCache"), SAFE, known_gpu_reason, "GPU")
    add("Intel ShaderCache", env_join("LOCALAPPDATA", "Intel", "ShaderCache"), SAFE, known_gpu_reason, "GPU")
    add("Intel ComputeCache", env_join("LOCALAPPDATA", "Intel", "ComputeCache"), SAFE, known_gpu_reason, "GPU")

    add(
        "Epic Games Launcher webcache",
        env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved", "webcache"),
        SAFE,
        "Known Epic Games Launcher web cache",
        "Epic",
    )
    epic_saved = env_join("LOCALAPPDATA", "EpicGamesLauncher", "Saved")
    if epic_saved and path_exists_dir(epic_saved):
        for path in epic_saved.glob("webcache_*"):
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

    return targets


def steam_targets() -> list[ScanTarget]:
    targets: list[ScanTarget] = []
    for root in steam_roots():
        # Steam's htmlcache lives below config, but the leaf is a documented cache folder.
        explicit = [
            ("Steam appcache", root / "appcache", SAFE, "Known Steam app cache"),
            ("Steam depotcache", root / "depotcache", SAFE, "Known Steam depot cache"),
            ("Steam htmlcache", root / "config" / "htmlcache", SAFE, "Known Steam browser html cache"),
            ("Steam shadercache", root / "steamapps" / "shadercache", SAFE, "Known Steam shader cache"),
            ("Steam logs", root / "logs", REVIEW, "Steam logs; review before deleting"),
        ]
        for name, path, category, reason in explicit:
            targets.append(ScanTarget(name, path, category, reason, "Steam"))

        for library in steam_libraries(root):
            library_targets = [
                ("Steam library shadercache", library / "steamapps" / "shadercache", SAFE, "Known Steam shader cache"),
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


def broad_discovery_targets(existing_keys: set[str]) -> list[ScanTarget]:
    targets: list[ScanTarget] = []
    for root in common_game_roots():
        max_depth = 4 if root.name.lower() in {"programdata", "games", "xboxgames"} else 5
        for path in safe_walk_dirs(root, max_depth=max_depth):
            if resolved_key(path) in existing_keys:
                continue
            category, reason = classify_candidate(path)
            if category == SKIP:
                continue
            targets.append(ScanTarget(candidate_name(path), path, category, reason, "Discovery"))
    return targets


def classify_candidate(path: Path) -> tuple[str, str]:
    if not is_cache_like_dir(path):
        return SKIP, ""

    # Broad discovery is intentionally conservative: saves, configs, mods,
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
