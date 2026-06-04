from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gameclean.cleaner import (
    clean_folder_contents,
    filter_nonzero_review_results,
    is_deletion_allowed,
)
from gameclean.scanner import REVIEW, SAFE, ScanResult


class CleanerTests(unittest.TestCase):
    def test_clean_folder_contents_deletes_children_but_not_selected_folder(self) -> None:
        with TemporaryDirectory() as temp_dir:
            selected = Path(temp_dir) / "Cache"
            nested = selected / "nested"
            nested.mkdir(parents=True)
            file_path = selected / "cache.bin"
            nested_file_path = nested / "nested.bin"
            file_path.write_text("cache", encoding="utf-8")
            nested_file_path.write_text("nested", encoding="utf-8")

            stats = clean_folder_contents(selected)

            self.assertTrue(selected.exists())
            self.assertEqual(list(selected.iterdir()), [])
            self.assertEqual(stats.files_deleted, 2)
            self.assertEqual(stats.folders_deleted, 1)
            self.assertEqual(stats.failed_items, 0)

    def test_clean_folder_contents_unlinks_symlink_without_following_it(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = root / "Cache"
            selected.mkdir()
            outside = root / "outside.txt"
            outside.write_text("keep", encoding="utf-8")
            link = selected / "outside-link.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlinks are not available in this environment")

            stats = clean_folder_contents(selected)

            self.assertTrue(outside.exists())
            self.assertFalse(link.exists())
            self.assertEqual(stats.files_deleted, 1)
            self.assertEqual(stats.failed_items, 0)

    def test_deletion_safety_blocks_requested_terms(self) -> None:
        blocked = ScanResult(
            name="Steam htmlcache",
            path=Path("Steam") / "config" / "htmlcache",
            size_bytes=100,
            category=SAFE,
            reason="Known Steam browser html cache",
            source="Steam",
        )
        allowed = ScanResult(
            name="NVIDIA DXCache",
            path=Path("AppData") / "Local" / "NVIDIA" / "DXCache",
            size_bytes=100,
            category=SAFE,
            reason="Known GPU shader cache",
            source="GPU",
        )

        self.assertFalse(is_deletion_allowed(blocked))
        self.assertTrue(is_deletion_allowed(allowed))

    def test_filter_nonzero_review_results_excludes_empty_and_blocked_paths(self) -> None:
        allowed = ScanResult("Logs", Path("Game") / "Logs", 10, REVIEW, "review", "Game-specific")
        empty = ScanResult("Empty", Path("Game") / "Temp", 0, REVIEW, "review", "Game-specific")
        blocked = ScanResult("Config logs", Path("Game") / "Config" / "Logs", 10, REVIEW, "review", "Game-specific")

        self.assertEqual(filter_nonzero_review_results([allowed, empty, blocked]), [allowed])


if __name__ == "__main__":
    unittest.main()
