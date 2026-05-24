import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gal_translator.profiles import ExtractorProfileRegistry
from gal_translator.project import TranslationProjectManager


class ProjectProfileTests(unittest.TestCase):
    def test_project_manager_creates_isolated_project_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "GalTranslator"
            game_dir = Path(tmp) / "Games" / "SampleGame"
            game_dir.mkdir(parents=True)
            (game_dir / "game.exe").write_bytes(b"MZ")

            project = TranslationProjectManager(base_dir).create_project(game_dir / "game.exe")

            self.assertTrue(project.project_root.is_dir())
            self.assertTrue((project.project_root / "extracted").is_dir())
            self.assertTrue((project.project_root / "scripts").is_dir())
            self.assertTrue((project.project_root / "db").is_dir())
            self.assertTrue((project.project_root / "logs").is_dir())
            self.assertNotEqual(project.project_root, game_dir)
            self.assertFalse((game_dir / "project.json").exists())

            payload = json.loads((project.project_root / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["sourceLang"], "ja")
            self.assertEqual(payload["targetLang"], "zh-Hans")
            self.assertEqual(payload["gameRoot"], str(game_dir.resolve()))
            self.assertEqual(payload["status"], "scanned")

    def test_profile_registry_matches_direct_script_profile_from_scan_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scenario").mkdir()
            (root / "scenario" / "opening.ks").write_text("美咲「おはよう」", encoding="utf-8")
            project = TranslationProjectManager(root / "workspace").create_project(root)

            profiles = ExtractorProfileRegistry.default().match(project.scan_report)

            self.assertGreaterEqual(len(profiles), 1)
            self.assertEqual(profiles[0].profile_id, "direct_script")
            self.assertEqual(profiles[0].source_lang, "ja")
            self.assertEqual(profiles[0].target_lang, "zh-Hans")
            self.assertIn("**/*.ks", profiles[0].script_globs)

    def test_profile_registry_does_not_match_root_readme_text_as_direct_script(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game.exe").write_bytes(b"MZ")
            (root / "readme.txt").write_text("not story", encoding="utf-8")
            (root / "patch_append1.txt").write_text("patch notes", encoding="utf-8")
            project = TranslationProjectManager(root / "workspace").create_project(root)

            profiles = ExtractorProfileRegistry.default().match(project.scan_report)

            self.assertEqual(profiles, [])

    def test_profile_registry_loads_user_json_profiles(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_dir = root / "extractor-profiles"
            profile_dir.mkdir()
            (profile_dir / "custom.json").write_text(
                json.dumps(
                    {
                        "profileId": "custom_old_gal",
                        "label": "Custom old Gal profile",
                        "sourceLang": "ja",
                        "targetLang": "zh-Hans",
                        "extensions": [".dat"],
                        "directories": ["scenario"],
                        "scriptGlobs": ["scenario/**/*.txt"],
                        "encoding": "cp932",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "archive.dat").write_bytes(b"data")
            project = TranslationProjectManager(root / "workspace").create_project(game_dir)

            profiles = ExtractorProfileRegistry.from_directories([profile_dir]).match(project.scan_report)

            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0].profile_id, "custom_old_gal")
            self.assertEqual(profiles[0].encoding, "cp932")


if __name__ == "__main__":
    unittest.main()
