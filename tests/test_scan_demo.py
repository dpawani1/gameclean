from __future__ import annotations

from pathlib import Path
import unittest

from gameclean.scanner import REVIEW, SAFE, scan


class ScanDemoTests(unittest.TestCase):
    def test_fake_windows_root_finds_safe_and_review_results(self) -> None:
        root = Path("examples/fake_windows")

        results = scan([root])
        safe_paths = {result.path.as_posix() for result in results if result.category == SAFE}
        review_paths = {result.path.as_posix() for result in results if result.category == REVIEW}

        self.assertIn(
            "examples/fake_windows/Users/Darsh/AppData/Local/NVIDIA/DXCache",
            safe_paths,
        )
        self.assertIn(
            "examples/fake_windows/ProgramData/Battle.net/Cache",
            safe_paths,
        )
        self.assertIn(
            "examples/fake_windows/Users/Darsh/AppData/Local/SomeGame/Saved/DerivedDataCache",
            review_paths,
        )
        self.assertIn(
            "examples/fake_windows/Users/Darsh/AppData/Local/SomeGame/Saved/Logs",
            review_paths,
        )
        self.assertGreater(sum(result.size_bytes for result in results), 0)


if __name__ == "__main__":
    unittest.main()
