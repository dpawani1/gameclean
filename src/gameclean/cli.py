from __future__ import annotations

import argparse
from collections.abc import Sequence

from .scanner import REVIEW, SAFE, ScanResult, scan
from .utils import format_size


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        print_scan_report(scan())
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
    scan_parser.set_defaults(command="scan")

    return parser


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
    print("This scan is read-only. GameClean did not delete or modify any files.")


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
