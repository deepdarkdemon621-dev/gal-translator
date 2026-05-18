from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gal_translator.detector import EngineDetector
from gal_translator.scanner import GameScanner


class ScannerDetectorTests(unittest.TestCase):
    def test_scanner_uses_exe_parent_as_game_root_and_reports_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "game.exe"
            exe.write_bytes(b"MZ")
            (root / "data.xp3").write_bytes(b"xp3")
            (root / "scenario").mkdir()
            (root / "scenario" / "opening.ks").write_text("美咲「……あんた、本気？」", encoding="utf-8")

            report = GameScanner().scan(exe)

        self.assertEqual(report.game_root, root)
        self.assertTrue(report.input_was_exe)
        self.assertIn(".xp3", report.extensions)
        self.assertIn(".ks", report.extensions)
        self.assertIn("scenario", report.directories)
        self.assertEqual(report.files_by_extension[".xp3"][0].relative_path, "data.xp3")

    def test_detector_reports_ranked_engine_candidates_from_scan_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.xp3").write_bytes(b"xp3")
            (root / "script.rpy").write_text("e \"hello\"", encoding="utf-8")
            (root / "0.txt").write_text("*define", encoding="utf-8")
            (root / "scenario").mkdir()
            (root / "scenario" / "opening.ks").write_text("[cm]", encoding="utf-8")
            report = GameScanner().scan(root)

            candidates = EngineDetector().detect(report)

        candidate_ids = [candidate.engine_id for candidate in candidates]
        self.assertIn("kirikiri_kag", candidate_ids)
        self.assertIn("renpy", candidate_ids)
        self.assertIn("nscripter", candidate_ids)
        self.assertGreaterEqual(candidates[0].confidence, candidates[-1].confidence)
        self.assertTrue(any(".xp3" in reason for reason in candidates[0].reasons))


if __name__ == "__main__":
    unittest.main()
