from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gameclean.scanner import REVIEW, SAFE, scan


class ScanDemoTests(unittest.TestCase):
    def test_fast_scan_fake_windows_root_finds_known_safe_results(self) -> None:
        root = Path("examples/fake_windows")

        results = scan([root])
        safe_paths = {result.path.as_posix() for result in results if result.category == SAFE}
        review_paths = {result.path.as_posix() for result in results if result.category == REVIEW}

        self.assertIn(
            "examples/fake_windows/Users/Darsh/AppData/Local/NVIDIA/DXCache",
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
        self.assertIn(
            "examples/fake_windows/Steam/steamapps/shadercache/12345",
            safe_paths,
        )
        self.assertNotIn(
            "examples/fake_windows/Steam/steamapps/shadercache",
            safe_paths,
        )
        steam_names = {result.name for result in results if result.source == "Steam"}
        self.assertIn("Fixture Game shadercache", steam_names)
        launcher_paths = {result.path.as_posix() for result in results if result.source == "Launcher"}
        self.assertIn(
            "examples/fake_windows/ProgramData/Battle.net/Cache",
            launcher_paths,
        )
        self.assertGreater(sum(result.size_bytes for result in results), 0)

    def test_deep_scan_fake_windows_root_finds_hidden_review_results(self) -> None:
        root = Path("examples/fake_windows")

        results = scan([root], deep=True, max_depth=4, review_limit=50)
        review_paths = {result.path.as_posix() for result in results if result.category == REVIEW}

        self.assertIn(
            "examples/fake_windows/Users/Darsh/AppData/Local/SomeGame/Saved/DerivedDataCache",
            review_paths,
        )
        self.assertIn(
            "examples/fake_windows/Users/Darsh/AppData/Local/SomeGame/Saved/Logs",
            review_paths,
        )
        self.assertGreater(sum(result.size_bytes for result in results), 0)

    def test_appdata_cache_folders_are_not_all_game_specific(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for app_name in (
                "pip",
                "Code",
                "Zoom",
                "Adobe",
                "Docker Desktop",
                "Sublime Text",
                "OneDrive",
                "Fusion360",
                "balenaEtcher",
                "winutil",
            ):
                (local / app_name / "Cache").mkdir(parents=True)
            (local / "SomeGame" / "Saved" / "Logs").mkdir(parents=True)

            results = scan([root])
            sources_by_parent = {result.path.parent.name: result.source for result in results}

            for app_name in (
                "pip",
                "Code",
                "Zoom",
                "Adobe",
                "Docker Desktop",
                "Sublime Text",
                "OneDrive",
                "Fusion360",
                "balenaEtcher",
                "winutil",
            ):
                self.assertEqual(sources_by_parent[app_name], "Other app")
            self.assertEqual(sources_by_parent["Saved"], "Game-specific")


if __name__ == "__main__":
    unittest.main()
