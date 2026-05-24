import json
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
                ScriptEntry("a.ks:1", "source one", "speaker", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "source two", None, "a.ks", 2, "candidate_dialogue"),
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

    def test_next_batch_can_scope_to_allowed_entry_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("base:1", "base source", None, "base", 1, "clipboard_capture"),
                ScriptEntry("misses:1", "miss source", None, "misses", 1, "clipboard_capture"),
            ]
            tracker = TranslationProgressTracker.initialize(project, entries)
            translator = CodexBatchTranslator(tracker.state_path)

            batch = translator.next_batch(batch_size=10, allowed_entry_ids=["misses:1"])

            self.assertEqual([item.entry_id for item in batch], ["misses:1"])

    def test_apply_result_updates_translation_progress(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("a.ks:1", "source one", "speaker", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "source two", None, "a.ks", 2, "candidate_dialogue"),
            ]
            tracker = TranslationProgressTracker.initialize(project, entries)
            translator = CodexBatchTranslator(tracker.state_path)

            apply_summary = translator.apply_result(
                {
                    "items": [
                        {
                            "id": "a.ks:1",
                            "translation": "translated one",
                        }
                    ]
                }
            )

            summary = tracker.summary()
            self.assertEqual(apply_summary.applied_ids, ("a.ks:1",))
            self.assertEqual(summary.translated, 1)
            self.assertEqual(summary.pending, 1)
            self.assertEqual(summary.percent, 50.0)

    def test_apply_result_reports_empty_unknown_duplicate_and_missing_items(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("a.ks:1", "source one", "speaker", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "source two", None, "a.ks", 2, "candidate_dialogue"),
                ScriptEntry("a.ks:3", "source three", None, "a.ks", 3, "candidate_dialogue"),
            ]
            tracker = TranslationProgressTracker.initialize(project, entries)
            translator = CodexBatchTranslator(tracker.state_path)

            apply_summary = translator.apply_result(
                {
                    "items": [
                        {"id": "a.ks:1", "translation": "translated one"},
                        {"id": "a.ks:1", "translation": "duplicate one"},
                        {"id": "a.ks:2", "translation": ""},
                        {"id": "missing.ks:1", "translation": "unknown"},
                        {"translation": "missing id"},
                    ]
                },
                expected_ids=["a.ks:1", "a.ks:2", "a.ks:3"],
            )

            self.assertEqual(apply_summary.applied_ids, ("a.ks:1",))
            self.assertEqual(apply_summary.failed_ids, ("a.ks:2", "a.ks:3"))
            self.assertEqual(apply_summary.empty_ids, ("a.ks:2",))
            self.assertEqual(apply_summary.missing_ids, ("a.ks:3",))
            self.assertEqual(apply_summary.unknown_ids, ("missing.ks:1",))
            self.assertEqual(apply_summary.duplicate_ids, ("a.ks:1",))
            self.assertEqual(apply_summary.invalid_item_count, 1)
            summary = tracker.summary()
            self.assertEqual(summary.translated, 1)
            self.assertEqual(summary.failed, 2)
            self.assertEqual(summary.pending, 0)

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
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"])
            self.assertFalse(schema["properties"]["items"]["items"]["additionalProperties"])
            self.assertEqual(schema["properties"]["items"]["items"]["required"], ["id", "translation", "notes"])
            self.assertEqual(schema["properties"]["items"]["items"]["properties"]["notes"]["type"], ["string", "null"])
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
