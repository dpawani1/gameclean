from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

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

    def __init__(self) -> None:
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
        line = f"{progress.label}: {progress_bar(progress.current, progress.total)} {progress.current}/{progress.total}"
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
