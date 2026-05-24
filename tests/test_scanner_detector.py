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

    def test_scanner_reports_pf8_archive_diagnostics_and_detector_prefers_ast_package(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game.exe").write_bytes(b"MZ")
            (root / "patch.xp3").write_bytes(b"XP3\r\n \n\x1a")
            (root / "game.pfs").write_bytes(
                b"pf83"
                + _pf8_entry("font\\sourcehansans-bold.otf", 128, 20)
                + _pf8_entry("system\\adv\\mainloop.lua", 148, 10)
                + _pf8_entry("script\\scene01.ast", 158, 30)
                + _pf8_entry("script\\scene02.ast", 188, 40)
                + b"x" * 256
            )

            report = GameScanner().scan(root / "game.exe")
            candidates = EngineDetector().detect(report)

        self.assertEqual(len(report.archive_diagnostics), 1)
        diagnostic = report.archive_diagnostics[0]
        self.assertEqual(diagnostic.format_id, "pf8_pfs")
        self.assertEqual(diagnostic.structured_entry_count, 4)
        self.assertEqual(diagnostic.visible_extension_counts[".ast"], 2)
        self.assertIn("script\\scene01.ast", diagnostic.visible_script_paths)
        self.assertEqual(candidates[0].engine_id, "pf8_pfs_ast")
        self.assertIn("visible .ast script entries", candidates[0].reasons[1])


def _pf8_entry(path: str, offset: int, size: int) -> bytes:
    raw_path = path.encode("utf-8")
    return (
        offset.to_bytes(4, "little")
        + size.to_bytes(4, "little")
        + len(raw_path).to_bytes(4, "little")
        + raw_path
        + b"\x00\x00\x00\x00"
    )


if __name__ == "__main__":
    unittest.main()
