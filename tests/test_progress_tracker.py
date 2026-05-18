from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
