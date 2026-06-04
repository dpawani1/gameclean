from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gameclean.installers import scan_installers


class InstallerScanTests(unittest.TestCase):
    def test_scan_installers_finds_supported_extensions_and_sorts_with_limit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            downloads = root / "Users" / "Darsh" / "Downloads"
            downloads.mkdir(parents=True)
            files = [
                ("small_setup.exe", 10),
                ("medium_patch.zip", 20),
                ("large_driver.iso", 30),
                ("notes.txt", 100),
            ]
            for name, size in files:
                (downloads / name).write_bytes(b"a" * size)

            results = scan_installers([root], min_size=1, limit=2)

            self.assertEqual([result.name for result in results], ["large_driver.iso", "medium_patch.zip"])
            self.assertTrue(all(result.category == "REVIEW" for result in results))

    def test_default_game_root_scan_is_shallow(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_root = root / "Games"
            shallow = game_root / "OldGame"
            deep = game_root / "OldGame" / "Nested" / "TooDeep"
            shallow.mkdir(parents=True)
            deep.mkdir(parents=True)
            (shallow / "setup.exe").write_bytes(b"a" * 10)
            (deep / "deep_setup.exe").write_bytes(b"a" * 10)

            results = scan_installers([root], min_size=1)

            self.assertEqual([result.name for result in results], ["setup.exe"])

    def test_deep_scan_can_find_deeper_game_root_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            deep = root / "Games" / "OldGame" / "Nested" / "TooDeep"
            deep.mkdir(parents=True)
            (deep / "deep_setup.exe").write_bytes(b"a" * 10)

            results = scan_installers([root], min_size=1, deep=True, max_depth=4)

            self.assertIn("deep_setup.exe", [result.name for result in results])

    def test_scan_installers_skips_risky_folders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            downloads = root / "Users" / "Darsh" / "Downloads"
            good = downloads / "old_setup.exe"
            skipped = downloads / "node_modules" / "bad_setup.exe"
            skipped.parent.mkdir(parents=True)
            good.parent.mkdir(parents=True, exist_ok=True)
            good.write_bytes(b"a" * 10)
            skipped.write_bytes(b"a" * 100)

            results = scan_installers([root], min_size=1)

            self.assertEqual([result.name for result in results], ["old_setup.exe"])


if __name__ == "__main__":
    unittest.main()
