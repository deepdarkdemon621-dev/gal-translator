from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gal_translator.parser import ScriptEntry
from gal_translator.progress import TranslationProgressTracker
from gal_translator.project import TranslationProjectManager
from gal_translator.translator import CodexBatchTranslator, CodexCliInvocation


class TranslatorTests(unittest.TestCase):
    def test_next_batch_uses_pending_items_and_prompt_preserves_gal_style(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("a.ks:1", "おはよう、先輩", "美咲", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "行こう", None, "a.ks", 2, "candidate_dialogue"),
            ]
            tracker = TranslationProgressTracker.initialize(project, entries)
            translator = CodexBatchTranslator(tracker.state_path)

            batch = translator.next_batch(batch_size=1)
            prompt = translator.build_prompt(batch)

            self.assertEqual([item.entry_id for item in batch], ["a.ks:1"])
            self.assertIn("Japanese", prompt)
            self.assertIn("Simplified Chinese", prompt)
            self.assertIn("preserve the original Galgame style", prompt)
            self.assertIn('"id": "a.ks:1"', prompt)

    def test_apply_result_updates_translation_progress(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("a.ks:1", "おはよう、先輩", "美咲", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "行こう", None, "a.ks", 2, "candidate_dialogue"),
            ]
            tracker = TranslationProgressTracker.initialize(project, entries)
            translator = CodexBatchTranslator(tracker.state_path)

            translator.apply_result(
                {
                    "items": [
                        {
                            "id": "a.ks:1",
                            "translation": "早上好，前辈。",
                        }
                    ]
                }
            )

            summary = tracker.summary()
            self.assertEqual(summary.translated, 1)
            self.assertEqual(summary.pending, 1)
            self.assertEqual(summary.percent, 50.0)

    def test_codex_cli_invocation_writes_schema_and_builds_command(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_path = root / "schema.json"
            prompt_path = root / "prompt.txt"
            output_path = root / "result.json"

            invocation = CodexCliInvocation(model="gpt-5.5")
            invocation.write_output_schema(schema_path)
            command = invocation.command(prompt_path, schema_path, output_path)

            self.assertTrue(schema_path.is_file())
            self.assertEqual(
                command,
                [
                    "codex",
                    "exec",
                    "--ephemeral",
                    "-m",
                    "gpt-5.5",
                    "--output-schema",
                    str(schema_path),
                    "-o",
                    str(output_path),
                    "-",
                ],
            )


if __name__ == "__main__":
    unittest.main()
