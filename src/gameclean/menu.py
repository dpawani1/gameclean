from __future__ import annotations

import argparse

from .installers import DEFAULT_INSTALLER_MIN_SIZE
from .leftovers import DEFAULT_MIN_SIZE


def interactive_menu() -> None:
    while True:
        print()
        print("GameClean")
        print("---------")
        print("What would you like to clean?")
        print()
        print("1. Shader/cache files")
        print("2. Leftover game files")
        print("3. Old installer/package files")
        print("4. Exit")
        print()

        try:
            choice = input("Choose an option [1-4]: ").strip().lower()
        except KeyboardInterrupt:
            print()
            print("Exiting. No files were deleted.")
            return

        if choice == "":
            choice = "1"
        if choice in {"q", "quit", "exit", "4"}:
            print("Exiting.")
            return
        if choice == "1":
            from .cli import handle_clean

            handle_clean(clean_args())
            return
        if choice == "2":
            from .cli import handle_leftovers

            handle_leftovers(leftovers_args())
            return
        if choice == "3":
            from .cli import handle_installers

            handle_installers(installers_args())
            return

        print("Please choose 1, 2, 3, or 4.")


def clean_args() -> argparse.Namespace:
    return argparse.Namespace(
        command="clean",
        root=[],
        limit=100,
        dry_run=False,
        safe=False,
        review=True,
    )


def leftovers_args() -> argparse.Namespace:
    return argparse.Namespace(
        command="leftovers",
        min=DEFAULT_MIN_SIZE,
        root=[],
        deep=False,
        max_depth=3,
        limit=100,
        include_installed=False,
        show_status=False,
        include_save_risk=False,
        dry_run=False,
        review=True,
    )


def installers_args() -> argparse.Namespace:
    return argparse.Namespace(
        command="installers",
        min=DEFAULT_INSTALLER_MIN_SIZE,
        root=[],
        deep=False,
        max_depth=3,
        limit=100,
        dry_run=False,
        review=True,
    )
