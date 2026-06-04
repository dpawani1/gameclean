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
            small = local / "Minecraft"
            large = local / "EA SPORTS FC 25"
            largest = local / "Hogwarts Legacy"
            for path in (small, large, largest):
                path.mkdir(parents=True)
            (small / "data.bin").write_bytes(b"a" * 10)
            (large / "data.bin").write_bytes(b"a" * 20)
            (largest / "data.bin").write_bytes(b"a" * 30)

            results = scan_leftovers([root], min_size=20, include_save_risk=True)

            self.assertEqual([result.name for result in results], ["Hogwarts Legacy", "EA SPORTS FC 25"])
            self.assertTrue(all(result.category == "REVIEW" for result in results))

    def test_scan_leftovers_skips_safety_and_launcher_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for name in ("OldGame Saves", "OldGame Mods", "EpicGamesLauncher", "WindowsApps"):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)
            known_game = local / "Hogwarts Legacy"
            known_game.mkdir(parents=True)
            (known_game / "data.bin").write_bytes(b"a" * 20)

            results = scan_leftovers([root], min_size=1)

            self.assertEqual([result.name for result in results], ["Hogwarts Legacy"])

    def test_default_scan_does_not_report_grandchildren_but_deep_can_find_known_games(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            nested = local / "Vendor" / "Hogwarts Legacy"
            nested.mkdir(parents=True)
            (nested / "data.bin").write_bytes(b"a" * 20)

            default_results = scan_leftovers([root], min_size=1)
            deep_results = scan_leftovers([root], min_size=1, deep=True, max_depth=2)

            self.assertEqual([result.name for result in default_results], ["Vendor"])
            self.assertIn("Hogwarts Legacy", [result.name for result in deep_results])

    def test_scan_leftovers_keeps_broad_non_allowlisted_game_candidates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for name in ("Trackmania", "MultiVersus", "Pokemon Showdown", "curseforge-updater", "FACEIT"):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)

            results = scan_leftovers([root], min_size=1)

            self.assertEqual(
                {result.name for result in results},
                {"Trackmania", "MultiVersus", "Pokemon Showdown", "curseforge-updater", "FACEIT"},
            )
            self.assertTrue(
                all(
                    result.reason == "Large AppData/ProgramData folder that may be leftover; review before deleting."
                    for result in results
                )
            )

    def test_scan_leftovers_applies_limit_after_sorting_by_size(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for name, size in (("Counter-Strike 2", 20), ("Hogwarts Legacy", 30), ("EA SPORTS FC 25", 10)):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * size)

            results = scan_leftovers([root], min_size=1, limit=2)

            self.assertEqual([result.name for result in results], ["Hogwarts Legacy", "Counter-Strike 2"])

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
            game = root / "Users" / "Darsh" / "AppData" / "Local" / "Hogwarts Legacy"
            game.mkdir(parents=True)
            (game / "data.bin").write_bytes(b"a" * 20)

            results = scan_leftovers([root], min_size=1)

            self.assertEqual(results[0].install_status, "UNKNOWN")

    def test_scan_leftovers_excludes_common_software_and_system_false_positives(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh 2" / "AppData" / "Local"
            roaming = root / "Users" / "Darsh 2" / "AppData" / "Roaming"
            programdata = root / "ProgramData"
            false_positives = [
                local / "Programs",
                programdata / "Darsh 2",
                local / "Discord",
                roaming / "com.adobe.dunamis",
                programdata / "Mozilla-1de4eec8-1241-4177-a864-e594e8d1fb38",
                local / "Mozilla-1de4eec8-1241-4177-a864-e594e8d1fb38",
                local / "arduino-ide-updater",
                local / "Google",
                local / "Mozilla",
                local / "Mozilla Firefox",
                local / "BraveSoftware",
                local / "WSL",
                local / "MATLAB",
                local / "miniforge3",
                local / "JetBrains",
                local / "MySQL",
                local / "Raspberry Pi",
                local / "Lenovo",
                local / "Docker",
                local / "OneDrive",
                local / "Code",
                local / "pip",
                local / "Python",
                local / "Sublime Text",
                local / "Fusion360",
                local / "balenaEtcher",
                local / "winutil",
            ]
            for path in false_positives:
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)
            known_game = local / "Hogwarts Legacy"
            known_game.mkdir(parents=True)
            (known_game / "data.bin").write_bytes(b"a" * 20)

            results = scan_leftovers([root], min_size=1)

            self.assertEqual([result.name for result in results], ["Hogwarts Legacy"])

    def test_scan_leftovers_can_show_excluded_without_returning_them_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            discord = local / "Discord"
            game = local / "Hogwarts Legacy"
            for path in (discord, game):
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)

            default_results = scan_leftovers([root], min_size=1)
            shown_results = scan_leftovers([root], min_size=1, include_excluded=True)

            self.assertEqual([result.name for result in default_results], ["Hogwarts Legacy"])
            excluded = [result for result in shown_results if result.name == "Discord"]
            self.assertEqual(len(excluded), 1)
            self.assertEqual(excluded[0].install_status, "EXCLUDED")

    def test_scan_leftovers_excludes_save_risk_games_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "Users" / "Darsh" / "AppData" / "Local"
            for name in ("EldenRing", "Citra", ".minecraft", "Hogwarts Legacy"):
                path = local / name
                path.mkdir(parents=True)
                (path / "data.bin").write_bytes(b"a" * 20)

            default_results = scan_leftovers([root], min_size=1)
            save_risk_results = scan_leftovers([root], min_size=1, include_save_risk=True)

            self.assertEqual(
                {result.name for result in save_risk_results},
                {"EldenRing", "Citra", "minecraft", "Hogwarts Legacy"},
            )
            self.assertEqual({result.name for result in default_results}, {result.name for result in save_risk_results})


if __name__ == "__main__":
    unittest.main()
