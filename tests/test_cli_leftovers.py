from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from gameclean.cli import (
    LEFTOVER_DELETION_WARNING,
    LEFTOVER_FINAL_WARNING,
    CleanupSelection,
    collect_leftover_cleanup_targets,
    delete_selected_leftovers,
)
from gameclean.scanner import REVIEW, ScanResult


class LeftoverCliTests(unittest.TestCase):
    def test_leftover_review_prints_dangerous_warning(self) -> None:
        result = ScanResult(
            "Hogwarts Legacy",
            Path("Hogwarts Legacy"),
            10,
            REVIEW,
            "Possible leftover",
            "Leftovers",
            "NOT_INSTALLED",
        )

        output = StringIO()
        with patch("builtins.input", return_value="n"), redirect_stdout(output):
            selection = collect_leftover_cleanup_targets([result])

        self.assertIn(LEFTOVER_DELETION_WARNING, output.getvalue())
        self.assertEqual(selection.selected, [])
        self.assertEqual(selection.review_skipped, 1)

    def test_leftover_review_prompts_broad_unknown_folders(self) -> None:
        result = ScanResult("Trackmania", Path("Trackmania"), 10, REVIEW, "Possible leftover", "Leftovers")

        output = StringIO()
        with patch("builtins.input", return_value="n") as mocked_input, redirect_stdout(output):
            selection = collect_leftover_cleanup_targets([result])

        mocked_input.assert_called_once()
        self.assertEqual(selection.selected, [])
        self.assertEqual(selection.review_skipped, 1)

    def test_leftover_review_does_not_prompt_excluded_folders(self) -> None:
        result = ScanResult("Discord", Path("Discord"), 10, "EXCLUDED", "Excluded", "Leftovers", "EXCLUDED")

        output = StringIO()
        with patch("builtins.input") as mocked_input, redirect_stdout(output):
            selection = collect_leftover_cleanup_targets([result])

        mocked_input.assert_not_called()
        self.assertEqual(selection.selected, [])

    def test_leftover_delete_requires_final_confirmation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            leftover = Path(temp_dir) / "OldGame"
            leftover.mkdir()
            (leftover / "data.bin").write_text("leftover", encoding="utf-8")
            result = ScanResult("OldGame", leftover, 8, REVIEW, "Possible leftover", "Leftovers")
            selection = CleanupSelection(
                selected=[result],
                safe_selected=[],
                review_selected=[result],
                review_skipped=0,
                review_zero_byte_skipped=0,
                safety_skipped=[],
            )

            output = StringIO()
            with patch("builtins.input", return_value="n"), redirect_stdout(output):
                report = delete_selected_leftovers(selection)

            self.assertTrue(leftover.exists())
            self.assertEqual(report.stats.files_deleted, 0)
            self.assertIn("Cleanup selection summary:", output.getvalue())
            self.assertIn(LEFTOVER_FINAL_WARNING, output.getvalue())
            self.assertIn("Leftover cleanup cancelled before deletion.", output.getvalue())

    def test_leftover_delete_runs_after_final_confirmation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            leftover = Path(temp_dir) / "OldGame"
            leftover.mkdir()
            (leftover / "data.bin").write_text("leftover", encoding="utf-8")
            result = ScanResult("OldGame", leftover, 8, REVIEW, "Possible leftover", "Leftovers")
            selection = CleanupSelection(
                selected=[result],
                safe_selected=[],
                review_selected=[result],
                review_skipped=0,
                review_zero_byte_skipped=0,
                safety_skipped=[],
            )

            with patch("builtins.input", return_value="yes"), redirect_stdout(StringIO()):
                report = delete_selected_leftovers(selection)

            self.assertFalse(leftover.exists())
            self.assertEqual(report.stats.files_deleted, 1)


if __name__ == "__main__":
    unittest.main()
