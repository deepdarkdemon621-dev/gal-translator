from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gal_translator.importer import DirectScriptImporter
from gal_translator.parser import ScriptParser
from gal_translator.profiles import ExtractorProfileRegistry
from gal_translator.project import TranslationProjectManager
from gal_translator.story_filter import StoryTextFilter


class DirectImportTests(unittest.TestCase):
    def test_importer_copies_direct_scripts_into_project_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            (game_dir / "scenario").mkdir(parents=True)
            (game_dir / "scenario" / "opening.ks").write_text(
                "美咲「おはよう、先輩」\n",
                encoding="utf-8",
            )
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            profile = ExtractorProfileRegistry.default().match(project.scan_report)[0]

            imported = DirectScriptImporter().import_scripts(project, profile)

            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].relative_path, "scenario/opening.ks")
            self.assertTrue((project.project_root / "scripts" / "scenario" / "opening.ks").is_file())
            self.assertFalse((game_dir / "scripts").exists())

    def test_importer_does_not_copy_root_readme_text_for_direct_script_profile(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            (game_dir / "scenario").mkdir(parents=True)
            (game_dir / "readme.txt").write_text("not story", encoding="utf-8")
            (game_dir / "scenario" / "opening.txt").write_text("opening story", encoding="utf-8")
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            profile = ExtractorProfileRegistry.default().match(project.scan_report)[0]

            imported = DirectScriptImporter().import_scripts(project, profile)

            self.assertEqual([script.relative_path for script in imported], ["scenario/opening.txt"])
            self.assertFalse((project.project_root / "scripts" / "readme.txt").exists())

    def test_parser_and_filter_keep_story_japanese_and_skip_system_text(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            (game_dir / "scenario").mkdir(parents=True)
            (game_dir / "system").mkdir()
            (game_dir / "scenario" / "opening.ks").write_text(
                "\n".join(
                    [
                        "[cm]",
                        "美咲「おはよう、先輩」",
                        "@bg storage=room",
                        "……また会えたね。",
                    ]
                ),
                encoding="utf-8",
            )
            (game_dir / "script.rpy").write_text(
                "\n".join(
                    [
                        'define e = Character("エリカ")',
                        'e "今日はいい天気だね。"',
                        'screen preferences():',
                        '    text "音量"',
                    ]
                ),
                encoding="utf-8",
            )
            (game_dir / "system" / "config.txt").write_text("音量\n設定\n", encoding="utf-8")
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            profile = ExtractorProfileRegistry.default().match(project.scan_report)[0]
            imported = DirectScriptImporter().import_scripts(project, profile)

            parsed_entries = []
            for script in imported:
                parsed_entries.extend(ScriptParser().parse(script.project_path, script.relative_path))
            story_entries = StoryTextFilter().keep_story_entries(parsed_entries)

            sources = [entry.source for entry in story_entries]
            self.assertEqual(
                sources,
                [
                    "おはよう、先輩",
                    "……また会えたね。",
                    "今日はいい天気だね。",
                ],
            )
            self.assertEqual(story_entries[0].speaker, "美咲")
            self.assertEqual(story_entries[2].speaker, "e")


if __name__ == "__main__":
    unittest.main()
