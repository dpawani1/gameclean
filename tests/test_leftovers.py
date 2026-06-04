from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gameclean.leftovers import scan_leftovers


class LeftoverScanTests(unittest.TestCase):
    def test_scan_leftovers_finds_large_appdata_folder_and_sorts_by_size(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            small = local / "SmallOldGame"
            large = local / "LargeOldGame"
            largest = local / "LargestOldGame"
            for path in (small, large, largest):
                path.mkdir(parents=True)
            (small / "data.bin").write_bytes(b"a" * 10)
            (large / "data.bin").write_bytes(b"a" * 20)
            (largest / "data.bin").write_bytes(b"a" * 30)

            results = scan_leftovers([root], min_size=20)

            self.assertEqual([result.name for result in results], ["LargestOldGame", "LargeOldGame"])
            self.assertTrue(all(result.category == "REVIEW" for result in results))

    def test_scan_leftovers_skips_safety_and_launcher_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for name in ("OldGame Saves", "OldGame Mods", "EpicGamesLauncher", "WindowsApps"):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)
            old_game = local / "OldGame"
            old_game.mkdir(parents=True)
            (old_game / "data.bin").write_bytes(b"a" * 20)

            results = scan_leftovers([root], min_size=1)

            self.assertEqual([result.name for result in results], ["OldGame"])

    def test_default_scan_does_not_report_grandchildren_but_deep_can(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            nested = local / "Vendor" / "NestedOldGame"
            nested.mkdir(parents=True)
            (nested / "data.bin").write_bytes(b"a" * 20)

            default_results = scan_leftovers([root], min_size=1)
            deep_results = scan_leftovers([root], min_size=1, deep=True, max_depth=2)

            self.assertEqual([result.name for result in default_results], ["Vendor"])
            self.assertIn("NestedOldGame", [result.name for result in deep_results])

    def test_scan_leftovers_applies_limit_after_sorting_by_size(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for name, size in (("MediumOldGame", 20), ("LargestOldGame", 30), ("SmallOldGame", 10)):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * size)

            results = scan_leftovers([root], min_size=1, limit=2)

            self.assertEqual([result.name for result in results], ["LargestOldGame", "MediumOldGame"])

    def test_scan_leftovers_marks_steam_manifest_match_as_installed_and_hides_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            steamapps = root / "Steam" / "steamapps"
            for name in ("Hogwarts Legacy", "EA SPORTS FC 25", "Counter-Strike 2"):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)
            steamapps.mkdir(parents=True)
            (steamapps / "appmanifest_730.acf").write_text(
                '"AppState"\n{\n    "appid" "730"\n    "name" "Counter-Strike 2"\n}\n',
                encoding="utf-8",
            )

            default_results = scan_leftovers([root], min_size=1)
            all_results = scan_leftovers([root], min_size=1, include_installed=True)

            default_statuses = {result.name: result.install_status for result in default_results}
            all_statuses = {result.name: result.install_status for result in all_results}
            self.assertEqual(default_statuses["Hogwarts Legacy"], "NOT_INSTALLED")
            self.assertEqual(default_statuses["EA SPORTS FC 25"], "NOT_INSTALLED")
            self.assertNotIn("Counter-Strike 2", default_statuses)
            self.assertEqual(all_statuses["Counter-Strike 2"], "INSTALLED")

    def test_scan_leftovers_marks_unknown_when_no_install_sources_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_game = root / "Users" / "Darsh" / "AppData" / "Local" / "OldGame"
            old_game.mkdir(parents=True)
            (old_game / "data.bin").write_bytes(b"a" * 20)

            results = scan_leftovers([root], min_size=1)

            self.assertEqual(results[0].install_status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
