from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .paths import root_diagnostics
from .scanner import REVIEW, SAFE, ScanResult, scan
from .utils import format_size


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        custom_roots = [Path(root).expanduser() for root in args.root]
        if args.show_roots:
            print_roots(custom_roots)
            return
        print_scan_report(scan(custom_roots))
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
        help="scan known and likely gaming cache locations without deleting anything",
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
    scan_parser.set_defaults(command="scan")

    return parser


def print_roots(custom_roots: list[Path] | None = None) -> None:
    diagnostics = root_diagnostics(custom_roots or [])

    print("Existing scan roots:")
    print()
    if diagnostics.existing_roots:
        for root in diagnostics.existing_roots:
            print(f"* {root}")
    else:
        print("* No existing scan roots found.")

    print()
    print("Missing Windows roots:")
    print()
    if diagnostics.missing_windows_roots:
        for missing in diagnostics.missing_windows_roots:
            print(f"* {missing}")
    else:
        print("* None")


def print_scan_report(results: list[ScanResult]) -> None:
    safe_results = [result for result in results if result.category == SAFE]
    review_results = [result for result in results if result.category == REVIEW]

    print("GameClean scan report")
    print("---------------------")
    print()

    print_section(SAFE, safe_results)
    print_section(REVIEW, review_results)

    safe_total = sum(result.size_bytes for result in safe_results)
    review_total = sum(result.size_bytes for result in review_results)

    print("Totals:")
    print(f"Safe cleanable: {format_size(safe_total)} across {len(safe_results)} folders")
    print(f"Review-only: {format_size(review_total)} across {len(review_results)} folders")
    print()
    if not safe_results and not review_results:
        print_empty_scan_note()
        print()
    print("This scan is read-only. GameClean did not delete or modify any files.")


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
