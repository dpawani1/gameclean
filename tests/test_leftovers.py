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


if __name__ == "__main__":
    unittest.main()
