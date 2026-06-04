from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import sys

from .cleaner import (
    DeleteStats,
    clean_folder_contents,
    filter_nonzero_review_results,
    is_deletion_allowed,
    review_zero_byte_skipped_count,
    safe_cleanable_results,
    safety_skipped_results,
)
from .paths import root_diagnostics
from .scanner import REVIEW, SAFE, ScanProgress, ScanResult, scan
from .utils import format_size


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        custom_roots = [Path(root).expanduser() for root in args.root]
        if args.show_roots:
            print_roots(custom_roots)
            return
        progress = ProgressPrinter()
        if args.deep:
            print("Deep scan may take several minutes because it searches large folders.")
            print()
            try:
                results = scan(
                    custom_roots,
                    deep=True,
                    max_depth=args.max_depth,
                    review_limit=args.limit,
                    progress=progress.update,
                )
            finally:
                progress.finish()
        else:
            print("Running fast scan. Use `gameclean scan --deep` to search more aggressively.")
            print()
            try:
                results = scan(custom_roots, review_limit=args.limit, progress=progress.update)
            finally:
                progress.finish()
        print_scan_report(results, show_empty=args.show_empty)
        return

    if args.command == "clean":
        custom_roots = [Path(root).expanduser() for root in args.root]
        print_clean_header()
        progress = ProgressPrinter(icon="🔍")
        print("🔍 Scanning for cleanup targets...")
        try:
            results = scan(custom_roots, review_limit=args.limit, progress=progress.update)
        finally:
            progress.finish()
        if args.dry_run:
            print_clean_dry_run(results)
            return
        if args.safe:
            print_final_clean_report(clean_selected_targets(collect_safe_cleanup_targets(results)))
            return
        try:
            selection = collect_review_cleanup_targets(results)
        except KeyboardInterrupt:
            print()
            print("Cleanup cancelled before deletion. No files were deleted.")
            return
        print_final_clean_report(clean_selected_targets(selection))
        return

    parser.print_help()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gameclean",
        description="GameClean: a read-only Windows gaming storage analyzer.",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser(
        "scan",
        help="quickly scan known gaming cache locations without deleting anything",
    )
    scan_parser.add_argument(
        "--show-roots",
        action="store_true",
        help="show existing scan roots and important missing Windows roots, then exit",
    )
    scan_parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="PATH",
        help="scan a custom Windows-like root for demo/testing; can be passed more than once",
    )
    scan_parser.add_argument(
        "--deep",
        action="store_true",
        help="recursively search likely gaming roots for hidden cache-like folders",
    )
    scan_parser.add_argument(
        "--max-depth",
        type=positive_int,
        default=5,
        metavar="N",
        help="maximum directory depth for --deep discovery (default: 5)",
    )
    scan_parser.add_argument(
        "--limit",
        type=non_negative_int,
        default=100,
        metavar="N",
        help="maximum number of review-only results to report (default: 100)",
    )
    scan_parser.add_argument(
        "--show-empty",
        action="store_true",
        help="accepted for compatibility; 0 B folders are shown by default",
    )
    scan_parser.set_defaults(command="scan")

    clean_parser = subparsers.add_parser(
        "clean",
        help="scan, review, then clean selected cache folders",
    )
    clean_mode = clean_parser.add_mutually_exclusive_group()
    clean_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="preview cleanable folders without deleting anything",
    )
    clean_mode.add_argument(
        "--safe",
        action="store_true",
        help="delete contents of SAFE folders only",
    )
    clean_mode.add_argument(
        "--review",
        action="store_true",
        help="same as the default: scan, review REVIEW folders, then clean selected folders",
    )
    clean_parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="PATH",
        help="scan a custom Windows-like root for demo/testing; can be passed more than once",
    )
    clean_parser.add_argument(
        "--limit",
        type=non_negative_int,
        default=100,
        metavar="N",
        help="maximum number of review-only results to report (default: 100)",
    )
    clean_parser.set_defaults(command="clean")

    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


class ProgressPrinter:
    width = 24

    def __init__(self, icon: str = "") -> None:
        self._icon = icon
        self._interactive = sys.stdout.isatty()
        self._line_open = False

    def update(self, progress: ScanProgress) -> None:
        if progress.total <= 0:
            return
        if progress.label == "Scanning root":
            self._print_root_progress(progress)
            return
        self._print_progress(progress, always=progress.current == progress.total)

    def finish(self) -> None:
        if self._line_open:
            print()
            self._line_open = False

    def _print_root_progress(self, progress: ScanProgress) -> None:
        if self._line_open:
            print()
            self._line_open = False
        print(f"Scanning root: {progress.path}")
        self._print_progress(progress, always=True)

    def _print_progress(self, progress: ScanProgress, *, always: bool) -> None:
        if not self._interactive and not always:
            return
        label = f"{self._icon} {progress.label}" if self._icon else progress.label
        line = f"{label}: {progress_bar(progress.current, progress.total)} {progress.current}/{progress.total}"
        if self._interactive:
            print(f"\r{line}", end="", flush=True)
            self._line_open = True
            if progress.current >= progress.total:
                print()
                self._line_open = False
            return
        print(line)


def progress_bar(current: int, total: int, width: int = ProgressPrinter.width) -> str:
    filled = round(width * min(current, total) / total)
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def print_roots(custom_roots: list[Path] | None = None) -> None:
    diagnostics = root_diagnostics(custom_roots or [])

    print(f"Detected OS mode: {diagnostics.os_mode}")
    print()

    print("Detected Windows user profiles:")
    print()
    print_path_list(diagnostics.windows_user_profiles, "* None")
    print()

    print("Detected AppData roots:")
    print()
    print_path_list([*diagnostics.local_appdata_roots, *diagnostics.roaming_appdata_roots, *diagnostics.programdata_roots], "* None")
    print()

    print("Detected USERPROFILE equivalents:")
    print()
    print_path_list(diagnostics.userprofile_roots, "* None")
    print()

    print("Detected Steam roots:")
    print()
    print_path_list(diagnostics.steam_roots, "* None")
    print()

    print("Detected Steam library roots:")
    print()
    print_path_list(diagnostics.steam_library_roots, "* None")
    print()

    print("Existing scan roots:")
    print()
    print_path_list(diagnostics.existing_roots, "* No existing scan roots found.")

    print()
    print("Missing important roots:")
    print()
    print_text_list(diagnostics.missing_windows_roots, "* None")


def print_path_list(paths: list[Path], empty: str) -> None:
    if paths:
        for path in paths:
            print(f"* {path}")
    else:
        print(empty)


def print_text_list(values: list[str], empty: str) -> None:
    if values:
        for value in values:
            print(f"* {value}")
    else:
        print(empty)


def print_scan_report(results: list[ScanResult], *, show_empty: bool = False) -> None:
    del show_empty
    visible_results = results
    safe_results = [result for result in visible_results if result.category == SAFE]
    review_results = [result for result in visible_results if result.category == REVIEW]

    print("GameClean scan report")
    print("---------------------")
    print()

    for group_name, group_results in grouped_results(visible_results):
        print_section(group_name, group_results)

    safe_total = sum(result.size_bytes for result in safe_results)
    review_total = sum(result.size_bytes for result in review_results)

    print("Totals:")
    print(f"Safe cleanable: {format_size(safe_total)} across {len(safe_results)} folders")
    print(f"Review-only: {format_size(review_total)} across {len(review_results)} folders")
    print()
    if not visible_results:
        print_empty_scan_note()
        print()
    print("This scan is read-only. GameClean did not delete or modify any files.")


@dataclass
class CleanedItem:
    name: str
    bytes_deleted: int


@dataclass
class CleanupSelection:
    selected: list[ScanResult]
    safe_selected: list[ScanResult]
    review_selected: list[ScanResult]
    review_skipped: int
    review_zero_byte_skipped: int
    safety_skipped: list[ScanResult]
    safe_zero_byte_skipped: int = 0


@dataclass
class CleanReport:
    selection: CleanupSelection
    stats: DeleteStats
    cleaned_items: list[CleanedItem]


def print_clean_header() -> None:
    print("GameClean clean")
    print("---------------")
    print()


def print_clean_dry_run(results: list[ScanResult]) -> None:
    safe_results = safe_cleanable_results(results)
    review_results = filter_nonzero_review_results(results)
    zero_review_count = review_zero_byte_skipped_count(results)
    safety_skipped = safety_skipped_results(results)

    print_clean_preview_section("SAFE folders that would be cleaned", safe_results)
    print_clean_preview_section("REVIEW folders available for interactive review", review_results)

    if safety_skipped:
        print("Skipped for safety:")
        for result in safety_skipped:
            print(f"* {result.name} ({result.category})")
            print(f"  Path: {result.path}")
        print()

    safe_total = sum(result.size_bytes for result in safe_results)
    review_total = sum(result.size_bytes for result in review_results)
    print("Totals:")
    print(f"SAFE cleanable total: {format_size(safe_total)} across {len(safe_results)} folders")
    print(f"REVIEW nonzero total: {format_size(review_total)} across {len(review_results)} folders")
    print(f"REVIEW 0 B skipped count: {zero_review_count}")
    if safety_skipped:
        print(f"Safety skipped count: {len(safety_skipped)}")
    print()
    print("Dry run only. No files were deleted.")


def print_clean_preview_section(title: str, results: list[ScanResult]) -> None:
    print(f"{title}:")
    if not results:
        print("No folders found.")
        print()
        return
    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.name}")
        print(f"   Source: {result.source}")
        print(f"   Path: {result.path}")
        print(f"   Size: {format_size(result.size_bytes)}")
        print(f"   Reason: {result.reason}")
        print()


def collect_safe_cleanup_targets(results: list[ScanResult]) -> CleanupSelection:
    safe_results = safe_cleanable_results(results)
    return CleanupSelection(
        selected=safe_results,
        safe_selected=safe_results,
        review_selected=[],
        review_skipped=0,
        review_zero_byte_skipped=review_zero_byte_skipped_count(results),
        safety_skipped=safety_skipped_results(results),
        safe_zero_byte_skipped=sum(1 for result in results if result.category == SAFE and result.size_bytes == 0),
    )


def collect_review_cleanup_targets(results: list[ScanResult]) -> CleanupSelection:
    safe_results = safe_cleanable_results(results)
    review_results = [result for result in results if result.category == REVIEW]
    prompt_results = filter_nonzero_review_results(results)
    zero_review_count = review_zero_byte_skipped_count(results)
    safety_skipped = safety_skipped_results(results)
    review_selected: list[ScanResult] = []
    review_skipped = 0

    print_safe_auto_selection(safe_results)
    print("Now reviewing REVIEW items one by one.")
    print("0 B REVIEW items will be skipped.")
    print()

    prompt_number = 0
    for result in review_results:
        if result.size_bytes == 0:
            continue
        if not is_deletion_allowed(result):
            continue

        prompt_number += 1
        print(f"Review item {prompt_number}/{len(prompt_results)}")
        print(f"Name: {result.name}")
        print(f"Source: {result.source}")
        print(f"Path: {result.path}")
        print(f"Size: {format_size(result.size_bytes)}")
        print(f"Reason: {result.reason}")
        answer = input("Delete? [y/N]: ").strip().lower()
        print()

        if answer in {"q", "quit"}:
            review_skipped += len(prompt_results) - prompt_number + 1
            break
        if answer in {"y", "yes"}:
            review_selected.append(result)
        else:
            review_skipped += 1

    selected = [*safe_results, *review_selected]
    return CleanupSelection(
        selected=selected,
        safe_selected=safe_results,
        review_selected=review_selected,
        review_skipped=review_skipped,
        review_zero_byte_skipped=zero_review_count,
        safety_skipped=safety_skipped,
        safe_zero_byte_skipped=sum(1 for result in results if result.category == SAFE and result.size_bytes == 0),
    )


def print_safe_auto_selection(safe_results: list[ScanResult]) -> None:
    print("SAFE items selected automatically:")
    if not safe_results:
        print("- None")
        print()
        return
    for result in safe_results:
        print(f"- {result.name} - {format_size(result.size_bytes)}")
    print()


def clean_selected_targets(selection: CleanupSelection) -> CleanReport:
    print_cleanup_selection_summary(selection)
    stats = DeleteStats()
    cleaned_items: list[CleanedItem] = []
    progress = ProgressPrinter(icon="🧹")

    print("🧹 Deleting selected cleanup targets...")
    if not selection.selected:
        progress.update(ScanProgress("Deleting", 0, 1, Path()))
        progress.finish()
        return CleanReport(selection, stats, cleaned_items)

    try:
        for index, result in enumerate(selection.selected, start=1):
            result_stats = clean_folder_contents(result.path)
            stats.add(result_stats)
            cleaned_items.append(CleanedItem(result.name, result_stats.bytes_deleted))
            progress.update(ScanProgress("Deleting", index, len(selection.selected), result.path))
    finally:
        progress.finish()

    return CleanReport(selection, stats, cleaned_items)


def print_cleanup_selection_summary(selection: CleanupSelection) -> None:
    print("Cleanup selection summary:")
    safe_total = sum(result.size_bytes for result in selection.safe_selected)
    review_total = sum(result.size_bytes for result in selection.review_selected)
    print(f"SAFE selected automatically: {len(selection.safe_selected)} folders, {format_size(safe_total)}")
    print(f"REVIEW selected by user: {len(selection.review_selected)} folders, {format_size(review_total)}")
    print(f"REVIEW skipped by user: {selection.review_skipped} folders")
    print(f"REVIEW skipped because 0 B: {selection.review_zero_byte_skipped} folders")
    if selection.safety_skipped:
        print(f"Skipped for safety: {len(selection.safety_skipped)} folders")
    print()


def print_final_clean_report(report: CleanReport) -> None:
    print()
    print("Final report:")
    print(f"Folders selected: {len(report.selection.selected)}")
    print(f"Files deleted: {report.stats.files_deleted}")
    print(f"Folders deleted: {report.stats.folders_deleted}")
    skipped = report.stats.failed_items + len(report.selection.safety_skipped) + report.selection.safe_zero_byte_skipped
    print(f"Skipped/failed items: {skipped}")
    print(f"Estimated space cleaned: {format_size(report.stats.bytes_deleted)}")
    print_cleaned_items(report.cleaned_items)


def print_cleaned_items(items: list[CleanedItem]) -> None:
    print()
    print("Cleaned:")
    if not items:
        print("No folders cleaned.")
        return
    for item in items:
        print(f"* {item.name}: {format_size(item.bytes_deleted)}")


def grouped_results(results: list[ScanResult]) -> list[tuple[str, list[ScanResult]]]:
    groups = [
        ("GPU caches", lambda result: result.source == "GPU"),
        ("Steam caches", lambda result: result.source == "Steam"),
        ("Launcher caches", lambda result: result.source == "Launcher"),
        ("Game-specific review folders", lambda result: result.source == "Game-specific"),
        ("Other app review folders", lambda result: result.source == "Other app"),
    ]
    grouped: list[tuple[str, list[ScanResult]]] = []
    for name, predicate in groups:
        group_results = [result for result in results if predicate(result)]
        grouped.append((name, group_results))
    return grouped


def print_empty_scan_note() -> None:
    print("Note:")
    print("No known Windows gaming cache folders were found.")
    print("This may happen if running on Linux/WSL/DSMLP or on a machine without those launchers installed.")
    print("Use `gameclean scan --show-roots` to see which roots were checked.")
    print("Use `gameclean scan --root PATH` to scan a custom folder for demo/testing.")


def print_section(title: str, results: list[ScanResult]) -> None:
    print(f"{title}:")
    if not results:
        print("No folders found.")
        print()
        return

    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.name}")
        print(f"   Category: {result.category}")
        print(f"   Source: {result.source}")
        print(f"   Path: {result.path}")
        print(f"   Size: {format_size(result.size_bytes)}")
        print(f"   Reason: {result.reason}")
        print()
    total = sum(result.size_bytes for result in results)
    print(f"Subtotal: {format_size(total)} across {len(results)} folders")
    print()
