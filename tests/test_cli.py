import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class CliTests(unittest.TestCase):
    def test_scan_command_outputs_json_diagnostic_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game.exe").write_bytes(b"MZ")
            (root / "data.xp3").write_bytes(b"xp3")
            (root / "scenario").mkdir()
            (root / "scenario" / "opening.ks").write_text("[cm]", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "-m", "gal_translator", "scan", str(root / "game.exe")],
                check=False,
                capture_output=True,
            )

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["gameRoot"], str(root))
        self.assertTrue(payload["inputWasExe"])
        self.assertEqual(payload["extensionCounts"][".xp3"], 1)
        self.assertIn("scenario", payload["directories"])
        self.assertEqual(payload["engineCandidates"][0]["engineId"], "kirikiri_kag")
        self.assertIn("data.xp3", [file["relativePath"] for file in payload["files"]])

    def test_init_command_creates_project_workspace_and_reports_profile_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Games" / "SampleGame"
            game_dir.mkdir(parents=True)
            (game_dir / "game.exe").write_bytes(b"MZ")
            (game_dir / "script.rpy").write_text('e "おはよう"', encoding="utf-8")
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "init",
                    str(game_dir / "game.exe"),
                    "--workspace",
                    str(workspace),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sourceLang"], "ja")
            self.assertEqual(payload["targetLang"], "zh-Hans")
            self.assertEqual(payload["status"], "scanned")
            self.assertEqual(payload["matchedProfiles"][0]["profileId"], "direct_script")
            self.assertTrue(Path(payload["projectRoot"]).is_dir())

    def test_import_command_writes_story_entries_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            (game_dir / "scenario").mkdir(parents=True)
            (game_dir / "scenario" / "opening.ks").write_text(
                "\n".join(["[cm]", "美咲「行こう、先輩」", "@bg storage=room"]),
                encoding="utf-8",
            )
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "import",
                    str(game_dir),
                    "--workspace",
                    str(workspace),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            entries_path = Path(payload["storyEntriesPath"])
            self.assertEqual(payload["importedScriptCount"], 1)
            self.assertEqual(payload["storyEntryCount"], 1)
            self.assertEqual(payload["progress"]["total"], 1)
            self.assertEqual(payload["progress"]["pending"], 1)
            self.assertEqual(payload["progress"]["status"], "pending")
            self.assertTrue(entries_path.is_file())
            self.assertTrue(Path(payload["translationStatePath"]).is_file())
            entries = json.loads(entries_path.read_text(encoding="utf-8"))
            self.assertEqual(entries[0]["source"], "行こう、先輩")
            self.assertEqual(entries[0]["speaker"], "美咲")

            progress_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "progress",
                    payload["projectRoot"],
                ],
                check=False,
                capture_output=True,
            )
            progress_stdout = progress_result.stdout.decode("utf-8", errors="replace")
            progress_stderr = progress_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(progress_result.returncode, 0, progress_stderr)
            progress_payload = json.loads(progress_stdout)
            self.assertEqual(progress_payload["total"], 1)
            self.assertEqual(progress_payload["pending"], 1)

            batch_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "batch",
                    payload["projectRoot"],
                    "--size",
                    "1",
                ],
                check=False,
                capture_output=True,
            )
            batch_stdout = batch_result.stdout.decode("utf-8", errors="replace")
            batch_stderr = batch_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(batch_result.returncode, 0, batch_stderr)
            self.assertIn("Japanese to Simplified Chinese", batch_stdout)
            self.assertIn('"id": "scenario/opening.ks:2"', batch_stdout)

            result_path = root / "result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "scenario/opening.ks:2",
                                "translation": "走吧，前辈。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            apply_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "apply-result",
                    payload["projectRoot"],
                    str(result_path),
                ],
                check=False,
                capture_output=True,
            )
            apply_stdout = apply_result.stdout.decode("utf-8", errors="replace")
            apply_stderr = apply_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(apply_result.returncode, 0, apply_stderr)
            apply_payload = json.loads(apply_stdout)
            self.assertEqual(apply_payload["translated"], 1)
            self.assertEqual(apply_payload["status"], "ready")

            lookup_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "lookup",
                    payload["projectRoot"],
                    "行こう、先輩",
                ],
                check=False,
                capture_output=True,
            )
            lookup_stdout = lookup_result.stdout.decode("utf-8", errors="replace")
            lookup_stderr = lookup_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(lookup_result.returncode, 0, lookup_stderr)
            lookup_payload = json.loads(lookup_stdout)
            self.assertEqual(lookup_payload["text"], "走吧，前辈。")
            self.assertFalse(lookup_payload["showSource"])


if __name__ == "__main__":
    unittest.main()
