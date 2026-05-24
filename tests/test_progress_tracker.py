from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

from gal_translator.parser import ScriptEntry
from gal_translator.progress import TranslationProgressTracker
from gal_translator.project import TranslationProjectManager


class ProgressTrackerTests(unittest.TestCase):
    def test_tracker_initializes_pending_items_and_reports_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("a.ks:1", "おはよう", "美咲", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "行こう", None, "a.ks", 2, "candidate_dialogue"),
            ]

            tracker = TranslationProgressTracker.initialize(project, entries)

            self.assertTrue((project.project_root / "translation-state.json").is_file())
            self.assertEqual(tracker.summary().total, 2)
            self.assertEqual(tracker.summary().pending, 2)
            self.assertEqual(tracker.summary().translated, 0)
            self.assertEqual(tracker.summary().status, "pending")

    def test_tracker_updates_translated_and_failed_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            entries = [
                ScriptEntry("a.ks:1", "おはよう", "美咲", "a.ks", 1, "candidate_dialogue"),
                ScriptEntry("a.ks:2", "行こう", None, "a.ks", 2, "candidate_dialogue"),
            ]
            tracker = TranslationProgressTracker.initialize(project, entries)

            tracker.mark_translated("a.ks:1", "早上好。")
            tracker.mark_failed("a.ks:2", "Codex output missing id")
            summary = tracker.summary()

            self.assertEqual(summary.total, 2)
            self.assertEqual(summary.translated, 1)
            self.assertEqual(summary.failed, 1)
            self.assertEqual(summary.pending, 0)
            self.assertEqual(summary.status, "partial")
            self.assertEqual(summary.percent, 50.0)

    def test_tracker_appends_new_entries_without_overwriting_existing_translations(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "おはよう。", None, "cap", 1, "clipboard_capture")],
            )
            tracker.mark_translated("cap:1", "早上好。")

            added = tracker.append_entries(
                [
                    ScriptEntry("cap:1", "おはよう。", None, "cap", 1, "clipboard_capture"),
                    ScriptEntry("cap:2", "また会えた。", None, "cap", 2, "clipboard_capture"),
                ]
            )

            self.assertEqual(added, 1)
            summary = tracker.summary()
            self.assertEqual(summary.total, 2)
            self.assertEqual(summary.translated, 1)
            self.assertEqual(summary.pending, 1)

    def test_tracker_resets_failed_items_to_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("cap:1", "おはよう。", None, "cap", 1, "clipboard_capture"),
                    ScriptEntry("cap:2", "また会えた。", None, "cap", 2, "clipboard_capture"),
                ],
            )
            tracker.mark_failed("cap:1", "bad json")

            reset_count = tracker.reset_failed()

            self.assertEqual(reset_count, 1)
            summary = tracker.summary()
            self.assertEqual(summary.failed, 0)
            self.assertEqual(summary.pending, 2)

    def test_tracker_limits_failed_item_retries_to_three(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "おはよう", None, "cap", 1, "clipboard_capture")],
            )

            for attempt in range(3):
                tracker.mark_failed("cap:1", f"failure {attempt}")
                retry_summary = tracker.reset_failed_summary()
                self.assertEqual(retry_summary.reset_count, 1)
                self.assertEqual(retry_summary.skipped_count, 0)

            tracker.mark_failed("cap:1", "still failing")
            retry_summary = tracker.reset_failed_summary()

            self.assertEqual(retry_summary.reset_count, 0)
            self.assertEqual(retry_summary.skipped_count, 1)
            self.assertEqual(retry_summary.skipped_ids, ("cap:1",))
            self.assertIn("abandon", retry_summary.next_actions[0])
            state = json.loads((project.project_root / "translation-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["items"][0]["retryCount"], 3)
            self.assertTrue(state["items"][0]["maxRetryReached"])
            self.assertEqual(tracker.summary().failed, 1)


if __name__ == "__main__":
    unittest.main()
