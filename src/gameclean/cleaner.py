from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .scanner import REVIEW, SAFE, ScanResult
from .utils import is_dangerous_path


SAFETY_BLOCKLIST = (
    "saves",
    "savegames",
    "saved games",
    "savedata",
    "profiles",
    "config",
    "settings",
    "mods",
    "screenshots",
    "captures",
    "replays",
    "steamapps/common",
    "windowsapps",
    "anti-cheat",
    "battleye",
    "easyanticheat",
    "riot vanguard",
    "license",
    "manifest",
    "session",
    "login",
)


@dataclass
class DeleteStats:
    files_deleted: int = 0
    folders_deleted: int = 0
    failed_items: int = 0
    bytes_deleted: int = 0

    def add(self, other: "DeleteStats") -> None:
        self.files_deleted += other.files_deleted
        self.folders_deleted += other.folders_deleted
        self.failed_items += other.failed_items
        self.bytes_deleted += other.bytes_deleted


def is_deletion_allowed(result: ScanResult) -> bool:
    if result.category not in {SAFE, REVIEW}:
        return False
    return not path_matches_safety_blocklist(result.path) and not is_dangerous_path(result.path)


def filter_nonzero_review_results(results: list[ScanResult]) -> list[ScanResult]:
    return [
        result
        for result in results
        if result.category == REVIEW and result.size_bytes > 0 and is_deletion_allowed(result)
    ]


def review_zero_byte_skipped_count(results: list[ScanResult]) -> int:
    return sum(1 for result in results if result.category == REVIEW and result.size_bytes == 0)


def safe_cleanable_results(results: list[ScanResult]) -> list[ScanResult]:
    return [
        result
        for result in results
        if result.category == SAFE and result.size_bytes > 0 and is_deletion_allowed(result)
    ]


def safety_skipped_results(results: list[ScanResult]) -> list[ScanResult]:
    return [
        result
        for result in results
        if result.category in {SAFE, REVIEW} and result.size_bytes > 0 and not is_deletion_allowed(result)
    ]


def clean_folder_contents(path: Path) -> DeleteStats:
    stats = DeleteStats()
    try:
        children = list(path.iterdir())
    except OSError:
        stats.failed_items += 1
        return stats

    for child in children:
        _delete_child(child, stats)

    return stats


def delete_folder(path: Path) -> DeleteStats:
    stats = DeleteStats()
    try:
        is_junction = getattr(path, "is_junction", lambda: False)
        if path.is_symlink() or is_junction() or not path.is_dir():
            stats.failed_items += 1
            return stats
    except OSError:
        stats.failed_items += 1
        return stats

    _delete_directory(path, stats)
    return stats


def path_matches_safety_blocklist(path: Path) -> bool:
    text = path.as_posix().lower()
    return any(term in text for term in SAFETY_BLOCKLIST)


def _delete_child(path: Path, stats: DeleteStats) -> None:
    try:
        is_junction = getattr(path, "is_junction", lambda: False)
        if path.is_symlink():
            _unlink_file_like(path, stats)
            return
        if is_junction():
            stats.failed_items += 1
            return
        if path.is_dir():
            _delete_directory(path, stats)
            return
        _unlink_file_like(path, stats)
    except OSError:
        stats.failed_items += 1


def _delete_directory(path: Path, stats: DeleteStats) -> None:
    try:
        with os.scandir(path) as entries:
            children = [Path(entry.path) for entry in entries]
    except OSError:
        stats.failed_items += 1
        return

    for child in children:
        _delete_child(child, stats)

    try:
        path.rmdir()
        stats.folders_deleted += 1
    except OSError:
        stats.failed_items += 1


def _unlink_file_like(path: Path, stats: DeleteStats) -> None:
    try:
        try:
            size = path.stat(follow_symlinks=False).st_size
        except OSError:
            size = 0
        path.unlink()
        stats.files_deleted += 1
        stats.bytes_deleted += size
    except OSError:
        stats.failed_items += 1
