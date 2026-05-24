import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from gal_translator.cli import _play_session_next_actions, _play_session_record_duration, _session_status
from gal_translator.parser import ScriptEntry
from gal_translator.progress import TranslationProgressTracker
from gal_translator.project import TranslationProjectManager


class CliTests(unittest.TestCase):
    def test_doctor_command_outputs_environment_checks(self) -> None:
        with TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "doctor",
                    "--workspace",
                    str(Path(tmp) / "workspace"),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(payload["status"], {"ready", "partial"})
            self.assertTrue(payload["checks"]["workspaceWritable"])
            self.assertIn("pythonVersion", payload["checks"])

    def test_smoke_test_runs_synthetic_end_to_end_workflow(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "SmokeWorkspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "smoke-test",
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
            self.assertEqual(payload["status"], "passed")
            self.assertTrue(all(payload["checks"].values()))
            self.assertFalse(payload["openSubtitle"])
            self.assertEqual(payload["inspectLog"]["captureStats"]["importedEntryCount"], 2)
            self.assertEqual(payload["playSession"]["translateAll"]["status"], "ready")
            self.assertEqual(payload["playSession"]["replay"]["matched"], 2)
            self.assertEqual(payload["playSession"]["sessionSummary"]["status"], "subtitle_ready")
            self.assertEqual(payload["playSession"]["subtitleWindow"]["preview"]["matchType"], "exact")
            self.assertEqual(payload["sessionInfo"]["reportType"], "play-session")
            self.assertTrue(payload["checks"]["sessionInfoResumeCommand"])
            self.assertEqual(payload["sessionInfo"]["commands"]["resumeSessionCommand"][2:4], ["gal_translator", "resume-session"])
            self.assertIn("--open-subtitle", payload["sessionInfo"]["commands"]["resumeSessionCommand"])
            self.assertEqual(payload["resumeSession"]["status"], "subtitle_planned")
            self.assertTrue(payload["checks"]["savedResumeCommandExecutable"])
            self.assertTrue(payload["checks"]["savedResumeCommandMatchesSessionInfo"])
            self.assertTrue(payload["checks"]["savedResumeCommandPlansWatchers"])
            self.assertEqual(payload["savedResumeCommand"]["status"], "subtitle_planned")
            self.assertEqual(payload["savedResumeCommand"]["command"], payload["resumeSession"]["command"])
            self.assertIn("translate-log", payload["savedResumeCommand"]["missWatcher"]["command"])
            self.assertIn("translate-log", payload["savedResumeCommand"]["sessionLogWatcher"]["command"])
            self.assertEqual(payload["resumeSubtitleWindow"]["status"], "skipped")
            self.assertTrue(payload["checks"]["resumeSubtitleWindowStarted"])
            self.assertEqual(payload["subtitleAutoClose"]["status"], "skipped")
            self.assertTrue(payload["checks"]["subtitleWindowAutoClosed"])
            self.assertTrue(payload["checks"]["resumeSubtitleWindowAutoClosed"])
            self.assertTrue(payload["checks"]["sourceLogFeedbackTranslated"])
            self.assertEqual(payload["sourceLogFeedback"]["status"], "passed")
            self.assertEqual(payload["sourceLogFeedback"]["watch"]["lastEvent"]["status"], "processed")
            self.assertEqual(payload["sourceLogFeedback"]["watch"]["lastEvent"]["result"]["append"]["addedEntryCount"], 1)
            self.assertEqual(payload["sourceLogFeedback"]["lookup"]["matchType"], "exact")
            self.assertFalse(payload["sourceLogFeedback"]["lookup"]["showSource"])
            self.assertTrue(payload["checks"]["sourceLogSubtitleWindowDisplayed"])
            self.assertEqual(payload["sourceLogSubtitleWindow"]["status"], "skipped")
            self.assertTrue(payload["checks"]["sourceLogLiveRefreshDisplayed"])
            self.assertEqual(payload["sourceLogLiveRefresh"]["status"], "skipped")
            self.assertTrue(payload["checks"]["liveSessionCompleted"])
            self.assertTrue(payload["checks"]["liveSessionReportRecoverable"])
            self.assertTrue(payload["checks"]["liveSessionResumeExecutable"])
            self.assertEqual(payload["liveSession"]["status"], "passed")
            self.assertEqual(payload["liveSession"]["liveSession"]["status"], "completed")
            self.assertEqual(
                payload["liveSession"]["liveSession"]["session"]["sessionSummary"]["status"],
                "translation_planned",
            )
            self.assertEqual(payload["liveSession"]["sessionInfo"]["reportType"], "live-session")
            self.assertEqual(payload["liveSession"]["resumeSession"]["status"], "translation_planned")
            self.assertEqual(
                payload["liveSession"]["sessionInfo"]["commands"]["watchMissLogCommand"],
                payload["liveSession"]["liveSession"]["missWatcher"]["command"],
            )
            self.assertEqual(
                payload["liveSession"]["sessionInfo"]["commands"]["watchSessionLogCommand"],
                payload["liveSession"]["liveSession"]["sessionLogWatcher"]["command"],
            )
            self.assertTrue(payload["checks"]["retryFailedResumeRecovered"])
            self.assertEqual(payload["retryFailedResume"]["status"], "passed")
            self.assertEqual(payload["retryFailedResume"]["dryRun"]["status"], "retry_failed_planned")
            self.assertEqual(payload["retryFailedResume"]["resumeSession"]["retryFailed"]["resetCount"], 1)
            self.assertEqual(payload["retryFailedResume"]["resumeSession"]["translateAll"]["status"], "ready")
            self.assertEqual(payload["retryFailedResume"]["projectInfo"]["progress"]["status"], "ready")
            self.assertTrue(Path(payload["sessionReportPath"]).is_file())
            self.assertFalse(payload["fakeCodexKept"])
            self.assertFalse(Path(payload["fakeCodexPath"]).exists())

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
        self.assertTrue(payload["nextActions"])
        self.assertIn("data.xp3", [file["relativePath"] for file in payload["files"]])

    def test_luna_hook_bridge_dry_run_plans_source_log_capture(self) -> None:
        with TemporaryDirectory() as tmp:
            source_log = Path(tmp) / "lunahook-source.txt"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "luna-hook-bridge",
                    "1234",
                    str(source_log),
                    "--luna-root",
                    str(Path(tmp) / "Luna"),
                    "--hook-code",
                    "HVXN-4C@1971E0:selectoblige.exe",
                    "--duration",
                    "1",
                    "--status-log",
                    str(Path(tmp) / "bridge-status.jsonl"),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["mode"], "lunahook_bridge")
            self.assertEqual(payload["gamePid"], 1234)
            self.assertEqual(payload["sourceLog"], str(source_log))
            self.assertIn("HVXN-4C@1971E0:selectoblige.exe", payload["hookCodes"])
            self.assertEqual(payload["statusLog"], str(Path(tmp) / "bridge-status.jsonl"))
            self.assertIn("translate-all", " ".join(payload["nextActions"]))

    def test_init_command_creates_project_workspace_and_reports_profile_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Games" / "SampleGame"
            game_dir.mkdir(parents=True)
            (game_dir / "game.exe").write_bytes(b"MZ")
            (game_dir / "script.rpy").write_text('e "縺翫・繧医≧"', encoding="utf-8")
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
                "\n".join(["[cm]", "\u7f8e\u54b2\u300c\u884c\u3053\u3046\u3001\u5148\u8f29\u300d", "@bg storage=room"]),
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
            self.assertEqual(entries[0]["source"], "\u884c\u3053\u3046\u3001\u5148\u8f29")
            self.assertEqual(entries[0]["speaker"], "\u7f8e\u54b2")

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
                "\ufeff"
                + json.dumps(
                    {
                        "items": [
                            {
                                "id": "scenario/opening.ks:2",
                                "translation": "translated opening",
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
                    "\u884c\u3053\u3046\u3001\u5148\u8f29",
                ],
                check=False,
                capture_output=True,
            )
            lookup_stdout = lookup_result.stdout.decode("utf-8", errors="replace")
            lookup_stderr = lookup_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(lookup_result.returncode, 0, lookup_stderr)
            lookup_payload = json.loads(lookup_stdout)
            self.assertEqual(lookup_payload["text"], "translated opening")
            self.assertFalse(lookup_payload["showSource"])

            info_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    payload["projectRoot"],
                ],
                check=False,
                capture_output=True,
            )
            info_stdout = info_result.stdout.decode("utf-8", errors="replace")
            info_stderr = info_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(info_result.returncode, 0, info_stderr)
            info_payload = json.loads(info_stdout)
            self.assertEqual(info_payload["storyEntryCount"], 1)
            self.assertEqual(info_payload["progress"]["status"], "ready")
            self.assertIn("lookup", " ".join(info_payload["nextActions"]))

    def test_import_command_writes_empty_state_when_no_profile_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            (game_dir / "readme.txt").write_text("not story", encoding="utf-8")
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
            self.assertEqual(payload["importedScriptCount"], 0)
            self.assertEqual(payload["storyEntryCount"], 0)
            self.assertEqual(payload["progress"]["status"], "empty")
            self.assertTrue(Path(payload["storyEntriesPath"]).is_file())
            self.assertTrue(Path(payload["translationStatePath"]).is_file())

    def test_archive_list_command_outputs_limited_script_entries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "game.pfs"
            archive_path.write_bytes(
                b"pf83"
                + _pf8_entry("image\\bg\\bg001a.png", 128, 20)
                + _pf8_entry("script\\scene01.ast", 148, 30)
                + _pf8_entry("script\\scene02.ast", 178, 40)
                + b"x" * 256
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "archive-list",
                    str(archive_path),
                    "--scripts-only",
                    "--limit",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(len(payload["archives"]), 1)
            archive = payload["archives"][0]
            self.assertEqual(archive["structuredEntryCount"], 3)
            self.assertEqual(archive["returnedEntryCount"], 1)
            self.assertEqual(archive["entries"][0]["path"], "script\\scene01.ast")

    def test_capture_log_command_creates_translation_state_from_clipboard_log(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text(
                "\n".join(["[hook] \u304a\u306f\u3088\u3046\u3001\u5148\u8f29", "[hook] \u304a\u306f\u3088\u3046\u3001\u5148\u8f29", "\u2026\u2026\u307e\u305f\u4f1a\u3048\u305f"]),
                encoding="utf-8",
            )
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir / "game.exe"),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["captureSource"], "textractor")
            self.assertEqual(payload["storyEntryCount"], 2)
            self.assertEqual(payload["progress"]["pending"], 2)
            self.assertEqual(payload["captureStats"]["rawLineCount"], 3)
            self.assertEqual(payload["captureStats"]["duplicateLineCount"], 1)
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 2)
            self.assertEqual(payload["captureStats"]["uniqueImportedEntryCount"], 2)
            self.assertEqual(payload["captureStats"]["repeatedSourceCount"], 0)
            entries = json.loads(Path(payload["storyEntriesPath"]).read_text(encoding="utf-8"))
            self.assertEqual(entries[0]["id"], "textractor:1")
            self.assertEqual(entries[0]["source"], "\u304a\u306f\u3088\u3046\u3001\u5148\u8f29")

    def test_inspect_log_command_reports_capture_stats_without_project(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "capture.txt"
            log_path.write_text(
                "\n".join(["[hook] 縺翫・繧医≧", "[hook] 縺翫・繧医≧", "WINDOW: Config", "縺ｾ縺溘・"]),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "inspect-log",
                    str(log_path),
                    "--source-name",
                    "textractor",
                    "--limit",
                    "1",
                    "--include-source",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["captureSource"], "textractor")
            self.assertEqual(payload["captureStats"]["rawLineCount"], 4)
            self.assertEqual(payload["captureStats"]["duplicateLineCount"], 1)
            self.assertEqual(payload["captureStats"]["nonJapaneseLineCount"], 1)
            self.assertEqual(payload["captureStats"]["controlLineCount"], 0)
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 2)
            self.assertEqual(payload["captureStats"]["uniqueImportedEntryCount"], 2)
            self.assertEqual(payload["captureStats"]["repeatedSourceCount"], 0)
            self.assertEqual(payload["status"], "ready_to_import")
            self.assertEqual(payload["previewCount"], 1)
            self.assertEqual(payload["preview"][0]["source"], "縺翫・繧医≧")

    def test_inspect_log_command_reports_repeated_source_diagnostics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "capture.txt"
            log_path.write_text(
                "\n".join(
                    [
                        "[hook] おはよう、先輩",
                        "[hook] ……また会えた",
                        "[hook] おはよう、先輩",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "inspect-log",
                    str(log_path),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ready_with_repeated_sources")
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 3)
            self.assertEqual(payload["captureStats"]["uniqueImportedEntryCount"], 2)
            self.assertEqual(payload["captureStats"]["repeatedSourceCount"], 1)
            self.assertIn("uniqueImportedEntryCount", " ".join(payload["nextActions"]))

    def test_inspect_log_command_reports_no_japanese_diagnostics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "capture.txt"
            log_path.write_text("WINDOW: Config\n12345\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "inspect-log",
                    str(log_path),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "no_japanese_text")
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 0)
            self.assertEqual(payload["captureStats"]["uniqueImportedEntryCount"], 0)
            self.assertEqual(payload["preview"], [])
            self.assertIn("--encoding", " ".join(payload["nextActions"]))

    def test_capture_log_append_keeps_existing_state_and_adds_new_entries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            first_log = root / "capture1.txt"
            first_log.write_text("\u304a\u306f\u3088\u3046\u3001\u5148\u8f29", encoding="utf-8")
            first = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(first_log),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )
            first_payload = json.loads(first.stdout.decode("utf-8", errors="replace"))
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps({"items": [{"id": "textractor:1", "translation": "translated hello"}]}),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "apply-result",
                    first_payload["projectRoot"],
                    str(result_path),
                ],
                check=False,
                capture_output=True,
            )
            second_log = root / "capture2.txt"
            second_log.write_text("\u304a\u306f\u3088\u3046\u3001\u5148\u8f29\n\u2026\u2026\u307e\u305f\u4f1a\u3048\u305f", encoding="utf-8")

            second = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(second_log),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                    "--append",
                ],
                check=False,
                capture_output=True,
            )

            payload = json.loads(second.stdout.decode("utf-8", errors="replace"))
            self.assertEqual(payload["addedEntryCount"], 1)
            self.assertEqual(payload["storyEntryCount"], 2)
            self.assertEqual(payload["progress"]["translated"], 1)
            self.assertEqual(payload["progress"]["pending"], 1)

    def test_capture_log_keeps_one_translation_entry_per_repeated_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text(
                "\n".join(["おはよう、先輩", "……また会えた", "おはよう、先輩"]),
                encoding="utf-8",
            )
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 3)
            self.assertEqual(payload["addedEntryCount"], 2)
            self.assertEqual(payload["storyEntryCount"], 2)
            self.assertEqual(payload["progress"]["total"], 2)
            entries = json.loads(Path(payload["storyEntriesPath"]).read_text(encoding="utf-8"))
            self.assertEqual([entry["source"] for entry in entries], ["おはよう、先輩", "……また会えた"])

    def test_append_log_uses_existing_project_without_game_rescan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            first_log = root / "capture1.txt"
            first_log.write_text("\u304a\u306f\u3088\u3046\u3001\u5148\u8f29", encoding="utf-8")
            first = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(first_log),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )
            first_payload = json.loads(first.stdout.decode("utf-8", errors="replace"))
            second_log = root / "capture2.txt"
            second_log.write_text("\u304a\u306f\u3088\u3046\u3001\u5148\u8f29\n\u2026\u2026\u307e\u305f\u4f1a\u3048\u305f", encoding="utf-8")

            second = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "append-log",
                    first_payload["projectRoot"],
                    str(second_log),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = second.stdout.decode("utf-8", errors="replace")
            stderr = second.stderr.decode("utf-8", errors="replace")
            self.assertEqual(second.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["addedEntryCount"], 1)
            self.assertEqual(payload["storyEntryCount"], 2)
            self.assertEqual(payload["progress"]["pending"], 2)

    def test_append_log_preserves_new_text_when_line_ids_collide(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            first_log = root / "capture1.txt"
            first_log.write_text("縺翫・繧医≧", encoding="utf-8")
            first = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(first_log),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )
            first_payload = json.loads(first.stdout.decode("utf-8", errors="replace"))
            second_log = root / "capture2.txt"
            second_log.write_text("縺ｾ縺溘・", encoding="utf-8")

            second = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "append-log",
                    first_payload["projectRoot"],
                    str(second_log),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = second.stdout.decode("utf-8", errors="replace")
            stderr = second.stderr.decode("utf-8", errors="replace")
            self.assertEqual(second.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["addedEntryCount"], 1)
            self.assertEqual(payload["storyEntryCount"], 2)
            entries = json.loads(Path(payload["storyEntriesPath"]).read_text(encoding="utf-8"))
            self.assertEqual(entries[0]["id"], "textractor:1")
            self.assertTrue(entries[1]["id"].startswith("textractor:1#"))
            self.assertEqual(entries[1]["source"], "縺ｾ縺溘・")

    def test_append_log_skips_existing_source_even_when_line_id_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            first_log = root / "capture1.txt"
            first_log.write_text("おはよう、先輩", encoding="utf-8")
            first = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(first_log),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )
            first_stdout = first.stdout.decode("utf-8", errors="replace")
            first_stderr = first.stderr.decode("utf-8", errors="replace")
            self.assertEqual(first.returncode, 0, first_stderr)
            first_payload = json.loads(first_stdout)
            second_log = root / "capture2.txt"
            second_log.write_text("WINDOW: Config\nおはよう、先輩", encoding="utf-8")

            second = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "append-log",
                    first_payload["projectRoot"],
                    str(second_log),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )

            stdout = second.stdout.decode("utf-8", errors="replace")
            stderr = second.stderr.decode("utf-8", errors="replace")
            self.assertEqual(second.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 1)
            self.assertEqual(payload["addedEntryCount"], 0)
            self.assertEqual(payload["storyEntryCount"], 1)
            self.assertEqual(payload["progress"]["total"], 1)

    def test_prepare_codex_command_writes_prompt_schema_and_command(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            (game_dir / "scenario").mkdir(parents=True)
            (game_dir / "scenario" / "opening.ks").write_text("\u7f8e\u54b2\u300c\u304a\u306f\u3088\u3046\u3001\u5148\u8f29\u300d", encoding="utf-8")
            workspace = root / "Workspace"
            import_result = subprocess.run(
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
            import_payload = json.loads(import_result.stdout.decode("utf-8", errors="replace"))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "prepare-codex",
                    import_payload["projectRoot"],
                    "--size",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["batchSize"], 1)
            self.assertTrue(Path(payload["promptPath"]).is_file())
            self.assertTrue(Path(payload["schemaPath"]).is_file())
            self.assertTrue(Path(payload["commandPath"]).is_file())
            self.assertTrue(Path(payload["batchPath"]).is_file())
            self.assertEqual(len(payload["entryIds"]), 1)
            self.assertIn("codex", payload["command"])

            info_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    import_payload["projectRoot"],
                ],
                check=False,
                capture_output=True,
            )
            info_stdout = info_result.stdout.decode("utf-8", errors="replace")
            info_stderr = info_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(info_result.returncode, 0, info_stderr)
            info_payload = json.loads(info_stdout)
            self.assertEqual(info_payload["latestCodexBatch"]["entryCount"], 1)
            self.assertFalse(info_payload["runtime"]["runtimeEventLogExists"])

    def test_run_codex_dry_run_prepares_files_without_execution(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            (game_dir / "scenario").mkdir(parents=True)
            (game_dir / "scenario" / "opening.ks").write_text("\u7f8e\u54b2\u300c\u304a\u306f\u3088\u3046\u3001\u5148\u8f29\u300d", encoding="utf-8")
            workspace = root / "Workspace"
            import_result = subprocess.run(
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
            import_payload = json.loads(import_result.stdout.decode("utf-8", errors="replace"))
            out_dir = root / "batch"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "run-codex",
                    import_payload["projectRoot"],
                    "--size",
                    "1",
                    "--out-dir",
                    str(out_dir),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "prepared")
            self.assertEqual(payload["batchSize"], 1)
            self.assertTrue(Path(payload["promptPath"]).is_file())
            self.assertFalse(Path(payload["stdoutPath"]).exists())

    def test_translate_all_dry_run_reports_plan_and_prepares_first_batch(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture"),
                    ScriptEntry("cap:2", "source two", None, "cap", 2, "clipboard_capture"),
                    ScriptEntry("cap:3", "source three", None, "cap", 3, "clipboard_capture"),
                ],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-all",
                    str(project.project_root),
                    "--size",
                    "2",
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["plannedBatchCount"], 2)
            self.assertEqual(payload["executedBatchCount"], 0)
            self.assertEqual(payload["initialProgress"]["pending"], 3)
            self.assertEqual(payload["firstBatch"]["batchSize"], 2)
            self.assertTrue(Path(payload["firstBatch"]["promptPath"]).is_file())

    def test_translate_all_reports_active_translation_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text("locked", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-all",
                    str(project.project_root),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "translation_locked")
            self.assertEqual(payload["lockPath"], str(lock_path))

    def test_translate_all_runs_fake_codex_until_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture"),
                    ScriptEntry("cap:2", "source two", None, "cap", 2, "clipboard_capture"),
                ],
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {
                    "items": [
                        {"id": "cap:1", "translation": "translated one"},
                        {"id": "cap:2", "translation": "translated two"},
                    ]
                },
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-all",
                    str(project.project_root),
                    "--size",
                    "2",
                    "--timeout",
                    "30",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["executedBatchCount"], 1)
            self.assertEqual(payload["finalProgress"]["translated"], 2)
            self.assertEqual(payload["finalProgress"]["status"], "ready")
            self.assertEqual(payload["batches"][0]["applyResult"]["appliedCount"], 2)

    def test_translate_all_can_retry_failed_entries_before_running_batches(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture"),
                    ScriptEntry("cap:2", "source two", None, "cap", 2, "clipboard_capture"),
                ],
            )
            tracker.mark_failed("cap:1", "previous failure")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {
                    "items": [
                        {"id": "cap:1", "translation": "translated one"},
                        {"id": "cap:2", "translation": "translated two"},
                    ]
                },
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-all",
                    str(project.project_root),
                    "--size",
                    "2",
                    "--timeout",
                    "30",
                    "--retry-failed",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ready")
            self.assertTrue(payload["retryFailed"]["requested"])
            self.assertEqual(payload["retryFailed"]["resetCount"], 1)
            self.assertEqual(payload["initialProgress"]["failed"], 1)
            self.assertEqual(payload["progressAfterRetryFailed"]["pending"], 2)
            self.assertEqual(payload["finalProgress"]["translated"], 2)
            self.assertEqual(payload["finalProgress"]["failed"], 0)

    def test_translate_all_failure_reports_batch_log_tails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_failing_codex_cmd(bin_dir / "codex.cmd")
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-all",
                    str(project.project_root),
                    "--size",
                    "1",
                    "--timeout",
                    "30",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["batches"][0]["returnCode"], 9)
            self.assertEqual(payload["batches"][0]["stdout"]["lastLine"], "fake codex stdout 2")
            self.assertEqual(payload["batches"][0]["stdout"]["tailLines"], ["fake codex stdout 1", "fake codex stdout 2"])
            self.assertEqual(payload["batches"][0]["stderr"]["lastLine"], "fake codex stderr 2")
            self.assertEqual(payload["batches"][0]["stderr"]["tailLines"], ["fake codex stderr 1", "fake codex stderr 2"])
            self.assertFalse(payload["batches"][0]["result"]["exists"])

            info_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )
            info_stdout = info_result.stdout.decode("utf-8", errors="replace")
            info_stderr = info_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(info_result.returncode, 0, info_stderr)
            info_payload = json.loads(info_stdout)
            latest = info_payload["latestCodexBatch"]
            self.assertEqual(latest["stdout"]["lastLine"], "fake codex stdout 2")
            self.assertEqual(latest["stdout"]["tailLines"], ["fake codex stdout 1", "fake codex stdout 2"])
            self.assertEqual(latest["stderr"]["lastLine"], "fake codex stderr 2")
            self.assertEqual(latest["stderr"]["tailLines"], ["fake codex stderr 1", "fake codex stderr 2"])
            self.assertTrue(latest["command"]["valid"])
            self.assertIn("command", latest["command"]["keys"])
            self.assertFalse(latest["result"]["exists"])

    def test_translate_all_applies_valid_result_written_before_timeout(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_slow_codex_cmd(
                bin_dir / "codex.cmd",
                {"items": [{"id": "cap:1", "translation": "translated before timeout"}]},
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-all",
                    str(project.project_root),
                    "--size",
                    "1",
                    "--timeout",
                    "1",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["batches"][0]["status"], "result_ready_process_stopped")
            self.assertTrue(payload["batches"][0]["earlyResultReady"])
            self.assertEqual(payload["batches"][0]["applyResult"]["appliedCount"], 1)
            self.assertEqual(payload["finalProgress"]["translated"], 1)
            state = json.loads((project.project_root / "translation-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["items"][0]["translation"], "translated before timeout")

    def test_apply_result_command_uses_batch_file_and_reports_failures(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture"),
                    ScriptEntry("cap:2", "source two", None, "cap", 2, "clipboard_capture"),
                    ScriptEntry("cap:3", "source three", None, "cap", 3, "clipboard_capture"),
                ],
            )
            batch_dir = root / "batch"
            batch_dir.mkdir()
            (batch_dir / "batch.json").write_text(
                json.dumps({"entryIds": ["cap:1", "cap:2", "cap:3"]}),
                encoding="utf-8",
            )
            result_path = batch_dir / "result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"id": "cap:1", "translation": "translated one"},
                            {"id": "cap:2", "translation": ""},
                            {"id": "unknown:1", "translation": "unknown"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "apply-result",
                    str(project.project_root),
                    str(result_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["translated"], 1)
            self.assertEqual(payload["failed"], 2)
            self.assertEqual(payload["applyResult"]["appliedIds"], ["cap:1"])
            self.assertEqual(payload["applyResult"]["failedIds"], ["cap:2", "cap:3"])
            self.assertEqual(payload["applyResult"]["unknownIds"], ["unknown:1"])
            self.assertEqual(payload["applyResult"]["missingIds"], ["cap:3"])
            self.assertEqual(tracker.summary().failed, 2)

    def test_apply_result_command_returns_json_error_for_invalid_result_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            result_path = root / "bad-result.json"
            result_path.write_text("{bad json", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "apply-result",
                    str(project.project_root),
                    str(result_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["code"], "result_json_invalid")

    def test_apply_result_reports_active_translation_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps({"items": [{"id": "cap:1", "translation": "translated one"}]}),
                encoding="utf-8",
            )
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text("locked", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "apply-result",
                    str(project.project_root),
                    str(result_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "translation_locked")
            self.assertEqual(payload["lockPath"], str(lock_path))

    def test_progress_command_returns_json_error_when_state_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "missing-project"
            project_root.mkdir()

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "progress",
                    str(project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["code"], "translation_state_missing")
            self.assertTrue(payload["nextActions"])

    def test_project_info_reports_corrupt_metadata_without_traceback(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            (project.project_root / "project.json").write_text("{bad json", encoding="utf-8")
            (project.project_root / "story-entries.json").write_text("{bad json", encoding="utf-8")
            batch_dir = project.project_root / "logs" / "codex-batches" / "20260520T000000000000Z"
            batch_dir.mkdir(parents=True)
            (batch_dir / "batch.json").write_text("{bad json", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["project"], {})
            self.assertEqual(payload["storyEntryCount"], 0)
            self.assertEqual(payload["progress"]["total"], 1)
            self.assertFalse(payload["latestCodexBatch"]["batchJsonValid"])
            diagnostic_labels = {item["label"] for item in payload["diagnostics"]}
            self.assertIn("project", diagnostic_labels)
            self.assertIn("storyEntries", diagnostic_labels)
            self.assertIn("latestCodexBatch", diagnostic_labels)

    def test_project_info_reports_corrupt_translation_state_without_traceback(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            state_path = project.project_root / "translation-state.json"
            state_path.write_text("{bad json", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertIsNone(payload["progress"])
            self.assertIn("Repair or regenerate", payload["nextActions"][0])
            self.assertEqual(payload["diagnostics"][0]["label"], "translationState")

    def test_project_info_reports_translation_lock_and_recovery_hint(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text(
                json.dumps({"pid": 999999999, "createdAt": "2026-05-21T00:00:00Z"}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["translationLock"]["exists"])
            self.assertTrue(payload["translationLock"]["valid"])
            self.assertEqual(payload["translationLock"]["pid"], 999999999)
            self.assertFalse(payload["translationLock"]["processActive"])
            self.assertIn("clear-lock", payload["nextActions"][0])

    def test_clear_lock_removes_stale_translation_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text(
                json.dumps({"pid": 999999999, "createdAt": "2026-05-21T00:00:00Z"}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "clear-lock",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "cleared")
            self.assertFalse(lock_path.exists())

    def test_clear_lock_refuses_active_translation_lock_without_force(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text(
                json.dumps({"pid": os.getpid(), "createdAt": "2026-05-21T00:00:00Z"}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "clear-lock",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "active")
            self.assertTrue(payload["translationLock"]["processActive"])
            self.assertTrue(lock_path.exists())

    def test_clear_lock_force_removes_active_translation_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text(
                json.dumps({"pid": os.getpid(), "createdAt": "2026-05-21T00:00:00Z"}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "clear-lock",
                    str(project.project_root),
                    "--force",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "cleared")
            self.assertTrue(payload["translationLock"]["processActive"])
            self.assertFalse(lock_path.exists())

    def test_capture_log_command_returns_json_error_when_log_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(root / "missing-log.txt"),
                    "--workspace",
                    str(root / "Workspace"),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["code"], "capture_log_unreadable")

    def test_apply_result_command_returns_json_error_for_invalid_batch_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            batch_dir = root / "batch"
            batch_dir.mkdir()
            (batch_dir / "batch.json").write_text("{bad json", encoding="utf-8")
            result_path = batch_dir / "result.json"
            result_path.write_text(
                json.dumps({"items": [{"id": "cap:1", "translation": "translated one"}]}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "apply-result",
                    str(project.project_root),
                    str(result_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["code"], "batch_json_invalid")

    def test_subtitle_window_dry_run_reports_config_without_opening_window(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            tracker.mark_translated("cap:1", "translated one")
            source_log = root / "textractor.txt"
            source_log.write_text("HOOK: source one\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "subtitle-window",
                    str(project.project_root),
                    "--dry-run",
                    "--x",
                    "120",
                    "--y",
                    "760",
                    "--width",
                    "1200",
                    "--height",
                    "120",
                    "--opacity",
                    "2",
                    "--clear-after",
                    "4",
                    "--exit-after",
                    "1.5",
                    "--preview-source",
                    "source one",
                    "--source-log",
                    str(source_log),
                    "--source-log-name",
                    "textractor",
                    "--source-log-from-start",
                    "--include-source",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["recordCount"], 1)
            self.assertEqual(payload["config"]["geometry"], "1200x120+120+760")
            self.assertEqual(payload["config"]["opacity"], 1.0)
            self.assertEqual(payload["config"]["clearAfterMs"], 4000)
            self.assertEqual(payload["config"]["exitAfterMs"], 1500)
            self.assertTrue(payload["reloadEnabled"])
            self.assertEqual(payload["preview"]["text"], "translated one")
            self.assertEqual(payload["preview"]["matchType"], "exact")
            self.assertEqual(payload["preview"]["rawText"], "source one")
            self.assertEqual(payload["input"]["mode"], "source_log")
            self.assertEqual(payload["input"]["sourceLogPath"], str(source_log))
            self.assertTrue(payload["input"]["sourceLogExists"])
            self.assertEqual(payload["input"]["sourceLogName"], "textractor")
            self.assertTrue(payload["input"]["sourceLogFromStart"])

    def test_subtitle_window_can_load_and_save_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "source one", None, "cap", 1, "clipboard_capture")],
            )
            tracker.mark_translated("cap:1", "translated one")
            config_path = root / "subtitle-config.json"
            saved_config_path = root / "saved-subtitle-config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "intervalMs": 300,
                        "fontSize": 36,
                        "opacity": 0.7,
                        "width": 1110,
                        "height": 130,
                        "x": 30,
                        "y": 700,
                        "fontFamily": "Configured Font",
                        "background": "#111111",
                        "foreground": "#eeeeee",
                        "clearAfterMs": 2500,
                        "exitAfterMs": 1500,
                        "topmost": False,
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "subtitle-window",
                    str(project.project_root),
                    "--dry-run",
                    "--config",
                    str(config_path),
                    "--save-config",
                    str(saved_config_path),
                    "--font-size",
                    "40",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["configPath"], str(config_path))
            self.assertEqual(payload["savedConfigPath"], str(saved_config_path))
            self.assertEqual(payload["config"]["geometry"], "1110x130+30+700")
            self.assertEqual(payload["config"]["fontSize"], 40)
            self.assertEqual(payload["config"]["opacity"], 0.7)
            self.assertFalse(payload["config"]["topmost"])
            saved_payload = json.loads(saved_config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["fontSize"], 40)
            self.assertEqual(saved_payload["width"], 1110)
            self.assertFalse(saved_payload["topmost"])

    def test_replay_log_command_reports_runtime_match_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("textractor:1", "縺翫・繧医≧", None, "textractor", 1, "clipboard_capture"),
                    ScriptEntry("textractor:2", "縺ｾ縺溘・", None, "textractor", 2, "clipboard_capture"),
                ],
            )
            tracker.mark_translated("textractor:1", "譌ｩ荳雁･ｽ")
            log_path = root / "textractor-log.txt"
            log_path.write_text(
                "\n".join(["[hook] 縺翫・繧医≧", "[hook] 縺ｾ縺溘・"]),
                encoding="utf-8",
            )
            event_log_path = root / "replay-events.jsonl"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "replay-log",
                    str(project.project_root),
                    str(log_path),
                    "--source-name",
                    "textractor",
                    "--include-source",
                    "--event-log",
                    str(event_log_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["total"], 2)
            self.assertEqual(payload["matched"], 1)
            self.assertEqual(payload["unmatched"], 1)
            self.assertEqual(payload["captureStats"]["rawLineCount"], 2)
            self.assertEqual(payload["captureStats"]["importedEntryCount"], 2)
            self.assertEqual(payload["events"][0]["text"], "譌ｩ荳雁･ｽ")
            self.assertEqual(payload["events"][0]["source"], "縺翫・繧医≧")
            self.assertFalse(payload["events"][0]["showSource"])
            self.assertEqual(payload["eventLogPath"], str(event_log_path))
            event_lines = event_log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(event_lines), 2)
            self.assertEqual(json.loads(event_lines[0])["text"], "譌ｩ荳雁･ｽ")

    def test_retry_failed_command_moves_failed_items_back_to_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text("\u304a\u306f\u3088\u3046\u3001\u5148\u8f29", encoding="utf-8")
            workspace = root / "Workspace"
            capture = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "capture-log",
                    str(game_dir),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--source-name",
                    "textractor",
                ],
                check=False,
                capture_output=True,
            )
            capture_payload = json.loads(capture.stdout.decode("utf-8", errors="replace"))
            tracker = TranslationProgressTracker(Path(capture_payload["translationStatePath"]))
            tracker.mark_failed("textractor:1", "bad json")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "retry-failed",
                    capture_payload["projectRoot"],
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["resetCount"], 1)
            self.assertEqual(payload["progress"]["failed"], 0)
            self.assertEqual(payload["progress"]["pending"], 1)

    def test_retry_failed_command_warns_after_retry_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("cap:1", "おはよう", None, "cap", 1, "clipboard_capture")],
            )
            for index in range(3):
                tracker.mark_failed("cap:1", f"failure {index}")
                tracker.reset_failed_summary()
            tracker.mark_failed("cap:1", "still failing")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "retry-failed",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["resetCount"], 0)
            self.assertEqual(payload["skippedCount"], 1)
            self.assertEqual(payload["retryLimit"], 3)
            self.assertEqual(payload["skippedIds"], ["cap:1"])
            self.assertIn("abandon", payload["nextActions"][0])
            self.assertEqual(payload["progress"]["failed"], 1)

            project_info = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "project-info",
                    str(project.project_root),
                ],
                check=False,
                capture_output=True,
            )
            project_payload = json.loads(project_info.stdout.decode("utf-8", errors="replace"))
            self.assertEqual(project_payload["failedRetry"]["skippedCount"], 1)
            self.assertIn("3-retry limit", project_payload["nextActions"][0])

    def test_workflow_fallback_runs_scan_capture_and_prepare(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text("\u304a\u306f\u3088\u3046\u3001\u5148\u8f29", encoding="utf-8")
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "workflow-fallback",
                    str(game_dir / "game.exe"),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--prepare-size",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(payload["doctor"]["status"], {"ready", "partial"})
            self.assertEqual(payload["capture"]["storyEntryCount"], 1)
            self.assertEqual(payload["preparedCodex"]["batchSize"], 1)
            self.assertTrue(Path(payload["preparedCodex"]["promptPath"]).is_file())

    def test_workflow_fallback_can_translate_all_and_replay(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text("\n".join(["縺翫・繧医≧", "縺ｾ縺溘・"]), encoding="utf-8")
            workspace = root / "Workspace"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {
                    "items": [
                        {"id": "textractor:1", "translation": "translated one"},
                        {"id": "textractor:2", "translation": "translated two"},
                    ]
                },
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            event_log_path = root / "replay-events.jsonl"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "workflow-fallback",
                    str(game_dir / "game.exe"),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--prepare-size",
                    "2",
                    "--translate-all",
                    "--translate-timeout",
                    "30",
                    "--replay-event-log",
                    str(event_log_path),
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertIsNone(payload["preparedCodex"])
            self.assertEqual(payload["capture"]["storyEntryCount"], 2)
            self.assertEqual(payload["translateAll"]["status"], "ready")
            self.assertEqual(payload["projectInfo"]["progress"]["status"], "ready")
            self.assertEqual(payload["replay"]["matched"], 2)
            self.assertEqual(payload["replay"]["eventLogPath"], str(event_log_path))
            self.assertEqual(len(event_log_path.read_text(encoding="utf-8").splitlines()), 2)

    def test_play_session_can_translate_replay_and_prepare_subtitle(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text("\n".join(["縺翫・繧医≧", "縺ｾ縺溘・"]), encoding="utf-8")
            workspace = root / "Workspace"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {
                    "items": [
                        {"id": "textractor:1", "translation": "translated one"},
                        {"id": "textractor:2", "translation": "translated two"},
                    ]
                },
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            replay_log_path = root / "replay-events.jsonl"
            runtime_log_path = root / "runtime-events.jsonl"
            miss_log_path = root / "misses.txt"
            session_report_path = root / "play-session-report.json"
            subtitle_config_path = root / "subtitle-config.json"
            saved_subtitle_config_path = root / "saved-subtitle-config.json"
            subtitle_config_path.write_text(
                json.dumps(
                    {
                        "fontSize": 34,
                        "opacity": 0.72,
                        "width": 1110,
                        "height": 130,
                        "x": 25,
                        "y": 710,
                        "clearAfterMs": 2500,
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "play-session",
                    str(game_dir / "game.exe"),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--batch-size",
                    "2",
                    "--translate-timeout",
                    "30",
                    "--translate-retry-failed",
                    "--replay-event-log",
                    str(replay_log_path),
                    "--subtitle-dry-run",
                    "--subtitle-preview-first-match",
                    "--subtitle-source-log",
                    "--subtitle-exit-after",
                    "1.5",
                    "--subtitle-event-log",
                    str(runtime_log_path),
                    "--subtitle-miss-log",
                    str(miss_log_path),
                    "--session-report",
                    str(session_report_path),
                    "--subtitle-config",
                    str(subtitle_config_path),
                    "--subtitle-save-config",
                    str(saved_subtitle_config_path),
                    "--font-size",
                    "38",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertIsNone(payload["launchGame"])
            self.assertIsNone(payload["recordClipboard"])
            self.assertEqual(payload["capture"]["storyEntryCount"], 2)
            self.assertEqual(payload["translateAll"]["status"], "ready")
            self.assertEqual(payload["projectInfo"]["progress"]["status"], "ready")
            self.assertEqual(payload["replay"]["matched"], 2)
            self.assertEqual(payload["subtitleWindow"]["dryRun"], True)
            self.assertEqual(payload["subtitleWindow"]["eventLogPath"], str(runtime_log_path))
            self.assertEqual(payload["subtitleWindow"]["missLogPath"], str(miss_log_path))
            self.assertEqual(payload["subtitleWindow"]["recordCount"], 2)
            self.assertEqual(payload["subtitleWindow"]["preview"]["text"], "translated one")
            self.assertEqual(payload["subtitleWindow"]["preview"]["matchType"], "exact")
            self.assertIn("--preview-source", payload["subtitleWindow"]["command"])
            self.assertEqual(payload["subtitleWindow"]["input"]["mode"], "source_log")
            self.assertEqual(payload["subtitleWindow"]["input"]["sourceLogPath"], str(log_path))
            self.assertIn("--source-log", payload["subtitleWindow"]["command"])
            self.assertIn(str(log_path), payload["subtitleWindow"]["command"])
            self.assertEqual(payload["subtitleWindow"]["config"]["exitAfterMs"], 1500)
            self.assertEqual(payload["subtitleWindow"]["configPath"], str(subtitle_config_path))
            self.assertEqual(payload["subtitleWindow"]["savedConfigPath"], str(saved_subtitle_config_path))
            self.assertEqual(payload["subtitleWindow"]["config"]["geometry"], "1110x130+25+710")
            self.assertEqual(payload["subtitleWindow"]["config"]["fontSize"], 38)
            self.assertEqual(payload["subtitleWindow"]["config"]["opacity"], 0.72)
            saved_config = json.loads(saved_subtitle_config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_config["fontSize"], 38)
            self.assertEqual(saved_config["width"], 1110)
            self.assertIn("--exit-after", payload["subtitleWindow"]["command"])
            self.assertEqual(payload["sessionSummary"]["status"], "subtitle_ready")
            self.assertEqual(payload["sessionSummary"]["capturedEntryCount"], 2)
            self.assertEqual(payload["sessionSummary"]["translatedCount"], 2)
            self.assertTrue(payload["sessionSummary"]["translateRetryFailed"])
            self.assertIn("--retry-failed", payload["resumeCommand"])
            self.assertEqual(payload["sessionSummary"]["replayUnmatched"], 0)
            self.assertIn("subtitle", " ".join(payload["nextActions"]))
            self.assertEqual(payload["subtitleWindow"]["command"][2:4], ["gal_translator", "subtitle-window"])
            self.assertIn(str(project_path := Path(payload["projectInfo"]["projectRoot"])), payload["subtitleWindow"]["command"])
            self.assertIn(str(miss_log_path), payload["sessionSummary"]["translateMissLogCommand"])
            self.assertIn(str(project_path), payload["sessionSummary"]["translateMissLogCommand"])
            self.assertIn("--size", payload["sessionSummary"]["translateMissLogCommand"])
            self.assertIn("2", payload["sessionSummary"]["translateMissLogCommand"])
            self.assertIn("--timeout", payload["sessionSummary"]["translateMissLogCommand"])
            self.assertIn("30", payload["sessionSummary"]["translateMissLogCommand"])
            self.assertIn(str(miss_log_path), payload["sessionSummary"]["watchMissLogCommand"])
            self.assertIn(str(project_path), payload["sessionSummary"]["watchMissLogCommand"])
            self.assertIn("--watch", payload["sessionSummary"]["watchMissLogCommand"])
            self.assertIn("--watch-require-ready", payload["sessionSummary"]["watchMissLogCommand"])
            self.assertIn(str(log_path), payload["sessionSummary"]["translateSessionLogCommand"])
            self.assertIn("textractor", payload["sessionSummary"]["translateSessionLogCommand"])
            self.assertIn(str(log_path), payload["sessionSummary"]["watchSessionLogCommand"])
            self.assertIn("--watch", payload["sessionSummary"]["watchSessionLogCommand"])
            self.assertIn("--watch-require-ready", payload["sessionSummary"]["watchSessionLogCommand"])

    def test_play_session_uses_default_capture_log_when_log_path_is_omitted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            workspace = root / "Workspace"
            default_log = workspace / "captures" / "game-live-capture.txt"
            default_log.parent.mkdir(parents=True)
            default_log.write_text("\n".join(["邵ｺ鄙ｫ繝ｻ郢ｧ蛹ｻ竕ｧ", "邵ｺ・ｾ邵ｺ貅倥・"]), encoding="utf-8")
            report_path = root / "play-session-report.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "play-session",
                    str(game_path),
                    "--workspace",
                    str(workspace),
                    "--translate-dry-run",
                    "--no-subtitle",
                    "--session-report",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sessionLogPath"], str(default_log))
            self.assertEqual(payload["sessionReportPath"], str(report_path))
            self.assertEqual(payload["resumeCommand"][2:4], ["gal_translator", "resume-session"])
            self.assertIn(str(report_path), payload["resumeCommand"])
            self.assertIn("--open-subtitle", payload["resumeCommand"])
            self.assertIn("--start-session-log-watcher", payload["resumeCommand"])
            self.assertTrue(report_path.is_file())
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report_payload["sessionSummary"]["status"], "translation_planned")
            self.assertEqual(report_payload["resumeCommand"], payload["resumeCommand"])
            self.assertEqual(payload["capture"]["captureStats"]["importedEntryCount"], 2)
            self.assertEqual(payload["sessionSummary"]["status"], "translation_planned")

    def test_session_info_reads_play_session_report_and_returns_resume_commands(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            workspace = root / "Workspace"
            default_log = workspace / "captures" / "game-live-capture.txt"
            default_log.parent.mkdir(parents=True)
            default_log.write_text("\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002", encoding="utf-8")
            report_path = root / "play-session-report.json"

            session_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "play-session",
                    str(game_path),
                    "--workspace",
                    str(workspace),
                    "--translate-dry-run",
                    "--no-subtitle",
                    "--session-report",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )
            self.assertEqual(session_result.returncode, 0, session_result.stderr.decode("utf-8", errors="replace"))

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["reportType"], "play-session")
            self.assertEqual(payload["sessionLogPath"], str(default_log))
            self.assertTrue(payload["sessionLogExists"])
            self.assertEqual(payload["sessionLogInspection"]["status"], "has_source")
            self.assertEqual(payload["sessionLogInspection"]["captureStats"]["importedEntryCount"], 1)
            self.assertEqual(payload["currentProjectInfo"]["progress"]["pending"], 1)
            self.assertEqual(payload["commands"]["inspectLogCommand"][2:4], ["gal_translator", "inspect-log"])
            self.assertIn("--source-name", payload["commands"]["inspectLogCommand"])
            self.assertIn("--encoding", payload["commands"]["inspectLogCommand"])
            self.assertEqual(payload["commands"]["appendSessionLogCommand"][2:4], ["gal_translator", "append-log"])
            self.assertIn(str(default_log), payload["commands"]["appendSessionLogCommand"])
            self.assertEqual(payload["commands"]["resumeSessionCommand"][2:4], ["gal_translator", "resume-session"])
            self.assertIn(str(report_path), payload["commands"]["resumeSessionCommand"])
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report_payload["resumeCommand"], payload["commands"]["resumeSessionCommand"])
            self.assertEqual(payload["commands"]["translateAllCommand"][2:4], ["gal_translator", "translate-all"])
            self.assertIn("translateAllCommand", payload["nextActions"][0])

    def test_session_info_reads_live_session_report_and_returns_runtime_commands(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            log_path = root / "capture.txt"
            log_path.write_text("\u304a\u306f\u3088\u3046", encoding="utf-8")
            watcher_stdout = root / "miss-watch.jsonl"
            watcher_stderr = root / "miss-watch-stderr.txt"
            session_log_watcher_stdout = root / "session-log-watch.jsonl"
            session_log_watcher_stderr = root / "session-log-watch-stderr.txt"
            watcher_stdout.write_text(
                json.dumps(
                    {
                        "status": "idle",
                        "reason": "translation_not_ready",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "status": "idle",
                        "reason": "log_unchanged",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            watcher_stderr.write_text("", encoding="utf-8")
            session_log_watcher_stdout.write_text(
                json.dumps(
                    {
                        "status": "idle",
                        "reason": "translation_locked",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "status": "processed",
                        "cycle": 1,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            session_log_watcher_stderr.write_text("", encoding="utf-8")
            report_path = root / "live-session-report.json"
            subtitle_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "subtitle-window",
                str(project.project_root),
            ]
            watch_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(root / "misses.txt"),
                "--watch",
                "--watch-require-ready",
            ]
            watch_session_log_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(log_path),
                "--source-name",
                "textractor",
                "--watch",
                "--watch-require-ready",
            ]
            report_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "projectRoot": str(project.project_root),
                        "sessionLogPath": str(log_path),
                        "sessionReportPath": str(report_path),
                        "missWatcher": {
                            "running": True,
                            "pid": 999999999,
                            "stdoutPath": str(watcher_stdout),
                            "stderrPath": str(watcher_stderr),
                        },
                        "sessionLogWatcher": {
                            "running": True,
                            "pid": 999999999,
                            "stdoutPath": str(session_log_watcher_stdout),
                            "stderrPath": str(session_log_watcher_stderr),
                        },
                        "session": {
                            "sessionSummary": {
                                "status": "subtitle_ready",
                                "projectRoot": str(project.project_root),
                                "subtitleCommand": subtitle_command,
                                "watchMissLogCommand": watch_command,
                                "watchSessionLogCommand": watch_session_log_command,
                            },
                            "projectInfo": {"projectRoot": str(project.project_root)},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["reportType"], "live-session")
            self.assertEqual(payload["currentProjectInfo"]["progress"]["status"], "ready")
            self.assertEqual(payload["commands"]["subtitleWindowCommand"], subtitle_command)
            self.assertEqual(payload["commands"]["watchMissLogCommand"], watch_command)
            self.assertEqual(payload["commands"]["watchSessionLogCommand"], watch_session_log_command)
            self.assertEqual(payload["sessionLogInspection"]["status"], "has_source")
            self.assertEqual(payload["sessionLogInspection"]["sourceName"], "textractor")
            self.assertEqual(payload["sessionLogInspection"]["captureStats"]["importedEntryCount"], 1)
            self.assertFalse(payload["missWatcher"]["currentProcessActive"])
            self.assertEqual(payload["missWatcher"]["stdout"]["lastEvent"]["reason"], "log_unchanged")
            self.assertEqual(len(payload["missWatcher"]["stdout"]["tailLines"]), 2)
            self.assertIn("translation_not_ready", payload["missWatcher"]["stdout"]["tailLines"][0])
            self.assertIn("log_unchanged", payload["missWatcher"]["stdout"]["tailLines"][1])
            self.assertEqual(payload["missWatcher"]["statusSummary"]["lastReason"], "log_unchanged")
            self.assertTrue(payload["missWatcher"]["stderr"]["exists"])
            self.assertFalse(payload["sessionLogWatcher"]["currentProcessActive"])
            self.assertEqual(payload["sessionLogWatcher"]["stdout"]["lastEvent"]["status"], "processed")
            self.assertEqual(len(payload["sessionLogWatcher"]["stdout"]["tailLines"]), 2)
            self.assertIn("translation_locked", payload["sessionLogWatcher"]["stdout"]["tailLines"][0])
            self.assertIn("processed", payload["sessionLogWatcher"]["stdout"]["tailLines"][1])
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastStatus"], "processed")
            self.assertTrue(payload["sessionLogWatcher"]["stderr"]["exists"])
            self.assertIn("subtitleWindowCommand", payload["nextActions"][0])
            self.assertIn("no longer running", payload["nextActions"][1])
            self.assertIn("session-log watcher", payload["nextActions"][-1])

    def test_session_info_summarizes_active_watcher_wait_reason(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            watcher_stdout = root / "miss-watch.jsonl"
            watcher_stderr = root / "miss-watch-stderr.txt"
            watcher_stdout.write_text(
                json.dumps(
                    {
                        "status": "idle",
                        "reason": "translation_not_ready",
                        "cycle": 3,
                        "idleCount": 2,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            watcher_stderr.write_text("", encoding="utf-8")
            report_path = root / "live-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "projectRoot": str(project.project_root),
                        "sessionReportPath": str(report_path),
                        "missWatcher": {
                            "running": True,
                            "pid": os.getpid(),
                            "stdoutPath": str(watcher_stdout),
                            "stderrPath": str(watcher_stderr),
                        },
                        "session": {
                            "sessionSummary": {
                                "status": "subtitle_ready",
                                "projectRoot": str(project.project_root),
                                "watchMissLogCommand": [
                                    sys.executable,
                                    "-m",
                                    "gal_translator",
                                    "translate-log",
                                    str(project.project_root),
                                    str(root / "misses.txt"),
                                    "--watch",
                                ],
                            },
                            "projectInfo": {"projectRoot": str(project.project_root)},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["missWatcher"]["currentProcessActive"])
            self.assertEqual(payload["missWatcher"]["statusSummary"]["lastReason"], "translation_not_ready")
            self.assertEqual(payload["missWatcher"]["statusSummary"]["lastCycle"], 3)
            self.assertIn("waiting for the primary project translation", " ".join(payload["nextActions"]))

    def test_session_info_reads_source_log_session_report_without_recommending_global_translation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "artemis_ast"),
                    ScriptEntry("base:2", "\u3055\u3088\u3046\u306a\u3089", None, "base", 2, "artemis_ast"),
                ],
            )
            tracker.mark_translated("base:1", "translated base")
            source_log = root / "lunahook-source.txt"
            source_log.write_text("HOOK: \u3055\u3088\u3046\u306a\u3089\n", encoding="utf-8")
            watcher_stdout = root / "source-log-watch.jsonl"
            watcher_stderr = root / "source-log-watch-stderr.txt"
            watcher_stdout.write_text(
                json.dumps(
                    {
                        "status": "processed",
                        "cycle": 2,
                        "result": {
                            "sessionSummary": {
                                "status": "translated",
                                "addedEntryCount": 0,
                                "pendingCount": 1,
                                "scopedTranslatedCount": 1,
                            },
                            "append": {
                                "logEntryIds": ["base:2"],
                            }
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "status": "idle",
                        "cycle": 3,
                        "reason": "log_unchanged",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            watcher_stderr.write_text("", encoding="utf-8")
            report_path = root / "source-log-session-report.json"
            restart_command = [
                "powershell",
                "-File",
                str(Path("scripts") / "source-log-session.ps1"),
                "-ProjectRoot",
                str(project.project_root),
                "-SourceLog",
                str(source_log),
                "-NoWatcher",
                "-NoSubtitle",
            ]
            watch_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(source_log),
                "--source-name",
                "lunahook",
                "--watch",
                "--only-new-log-entries",
            ]
            subtitle_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "subtitle-window",
                str(project.project_root),
                "--source-log",
                str(source_log),
                "--source-log-name",
                "lunahook",
            ]
            subtitle_event_log = root / "subtitle-events.jsonl"
            subtitle_event_log.write_text(
                json.dumps(
                    {
                        "text": "\u7ffb\u8a33\u6e08\u307f",
                        "matchType": "exact",
                        "visible": True,
                        "missLogged": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            clipboard_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "record-clipboard",
                str(source_log),
            ]
            luna_hook_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "luna-hook-bridge",
                "1234",
                str(source_log),
            ]
            luna_hook_status = root / "lunahook-status.jsonl"
            luna_hook_status.write_text(
                json.dumps({"status": "captured", "capturedCount": 1, "text": "\u3055\u3088\u3046\u306a\u3089"}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            report_path.write_text(
                json.dumps(
                    {
                        "status": "started",
                        "projectRoot": str(project.project_root),
                        "sessionReportPath": str(report_path),
                        "restartCommand": restart_command,
                        "sourceLog": str(source_log),
                        "sourceName": "lunahook",
                        "missLog": str(root / "misses.txt"),
                        "eventLog": str(subtitle_event_log),
                        "watcher": {
                            "started": True,
                            "pid": 999999,
                            "stdoutPath": str(watcher_stdout),
                            "stderrPath": str(watcher_stderr),
                            "command": watch_command,
                        },
                        "subtitleWindow": {
                            "started": True,
                            "pid": 999998,
                            "stdoutPath": str(root / "subtitle-stdout.txt"),
                            "stderrPath": str(root / "subtitle-stderr.txt"),
                            "command": subtitle_command,
                        },
                        "clipboardBridge": {
                            "started": True,
                            "enabled": True,
                            "pid": os.getpid(),
                            "stdoutPath": str(root / "clipboard-stdout.json"),
                            "stderrPath": str(root / "clipboard-stderr.txt"),
                            "command": clipboard_command,
                        },
                        "lunaHookBridge": {
                            "started": True,
                            "enabled": True,
                            "pid": os.getpid(),
                            "gamePid": 1234,
                            "stdoutPath": str(root / "lunahook-stdout.json"),
                            "stderrPath": str(root / "lunahook-stderr.txt"),
                            "statusLogPath": str(luna_hook_status),
                            "command": luna_hook_command,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["reportType"], "source-log-session")
            self.assertEqual(payload["sessionLogPath"], str(source_log))
            self.assertEqual(payload["sessionLogInspection"]["sourceName"], "lunahook")
            self.assertEqual(payload["sessionLogInspection"]["status"], "has_source")
            self.assertEqual(payload["commands"]["sourceLogSessionRestartCommand"], restart_command)
            self.assertNotIn("-NoWatcher", payload["commands"]["sourceLogSessionCommand"])
            self.assertNotIn("-NoSubtitle", payload["commands"]["sourceLogSessionCommand"])
            self.assertEqual(payload["commands"]["watchSessionLogCommand"], watch_command)
            self.assertEqual(payload["commands"]["subtitleWindowCommand"], subtitle_command)
            self.assertEqual(payload["commands"]["clipboardBridgeCommand"], clipboard_command)
            self.assertEqual(payload["commands"]["lunaHookBridgeCommand"], luna_hook_command)
            self.assertTrue(payload["clipboardBridge"]["currentProcessActive"])
            self.assertTrue(payload["clipboardBridge"]["enabled"])
            self.assertTrue(payload["lunaHookBridge"]["currentProcessActive"])
            self.assertTrue(payload["lunaHookBridge"]["enabled"])
            self.assertEqual(payload["lunaHookBridge"]["statusLog"]["lastEvent"]["status"], "captured")
            self.assertEqual(payload["subtitleWindow"]["eventLog"]["lastEvent"]["matchType"], "exact")
            self.assertTrue(payload["subtitleWindow"]["eventLog"]["lastEvent"]["visible"])
            self.assertEqual(payload["sessionLogWatcher"]["stdout"]["lastEvent"]["status"], "idle")
            self.assertEqual(payload["sessionLogWatcher"]["stdout"]["lastProcessedEvent"]["status"], "processed")
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastStatus"], "idle")
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastProcessedStatus"], "processed")
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastProcessedCycle"], 2)
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastProcessedSessionStatus"], "translated")
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastProcessedScopedTranslatedCount"], 1)
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastProcessedLogEntryIds"], ["base:2"])
            self.assertEqual(payload["subtitleWindow"]["currentProcessActive"], False)
            actions_text = " ".join(payload["nextActions"])
            self.assertIn("sourceLogSessionCommand", actions_text)
            self.assertIn("scoped source-log translation", actions_text)
            self.assertIn("clipboard bridge is running", actions_text)
            self.assertIn("LunaHook bridge is running", actions_text)
            self.assertIn("Do not run translateAllCommand", actions_text)
            self.assertNotEqual(payload["nextActions"][0], "Run translateAllCommand to translate and apply all pending entries, then rerun session-info.")

    def test_source_log_status_reports_paused_scoped_loop(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "artemis_ast"),
                    ScriptEntry("base:2", "\u3055\u3088\u3046\u306a\u3089", None, "base", 2, "artemis_ast"),
                ],
            )
            tracker.mark_translated("base:1", "translated base")
            source_log = root / "lunahook-source.txt"
            source_log.write_text("\u3055\u3088\u3046\u306a\u3089\n", encoding="utf-8")
            watcher_stdout = root / "source-log-watch.jsonl"
            watcher_stdout.write_text(
                json.dumps(
                    {
                        "status": "processed",
                        "cycle": 1,
                        "result": {
                            "sessionSummary": {
                                "status": "translation_ready",
                                "addedEntryCount": 0,
                                "scopedTranslatedCount": 1,
                            },
                            "append": {"logEntryIds": ["base:2"]},
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            report_path = root / "source-log-session-report.json"
            subtitle_event_log = root / "subtitle-events.jsonl"
            luna_hook_status_log = root / "lunahook-status.jsonl"
            subtitle_event_log.write_text(
                json.dumps(
                    {
                        "text": "translated base",
                        "matchType": "exact",
                        "visible": True,
                        "missLogged": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            luna_hook_status_log.write_text(
                json.dumps(
                    {
                        "status": "captured",
                        "capturedCount": 1,
                        "text": "\u3055\u3088\u3046\u306a\u3089",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            report_path.write_text(
                json.dumps(
                    {
                        "projectRoot": str(project.project_root),
                        "sessionReportPath": str(report_path),
                        "sourceLog": str(source_log),
                        "sourceName": "lunahook",
                        "eventLog": str(subtitle_event_log),
                        "watcher": {
                            "started": True,
                            "pid": os.getpid(),
                            "stdoutPath": str(watcher_stdout),
                            "command": [sys.executable, "-m", "gal_translator", "translate-log"],
                        },
                        "subtitleWindow": {
                            "started": True,
                            "pid": os.getpid(),
                            "command": [sys.executable, "-m", "gal_translator", "subtitle-window"],
                        },
                        "clipboardBridge": {
                            "started": True,
                            "enabled": True,
                            "pid": os.getpid(),
                            "command": [sys.executable, "-m", "gal_translator", "record-clipboard", str(source_log)],
                        },
                        "lunaHookBridge": {
                            "started": True,
                            "enabled": True,
                            "pid": os.getpid(),
                            "gamePid": os.getpid(),
                            "statusLogPath": str(luna_hook_status_log),
                            "command": [sys.executable, "-m", "gal_translator", "luna-hook-bridge", str(os.getpid()), str(source_log)],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "source-log-status",
                    str(project.project_root),
                    str(source_log),
                    "--session-report",
                    str(report_path),
                    "--hook-process",
                    "definitely-not-a-real-hook.exe",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "watching_source_log")
            self.assertTrue(payload["pausedFullArchive"])
            self.assertEqual(payload["mode"], "paused_full_archive_scoped_source_log")
            self.assertEqual(payload["progress"]["translated"], 1)
            self.assertEqual(payload["progress"]["pending"], 1)
            self.assertEqual(payload["sourceLogInspection"]["status"], "has_source")
            self.assertTrue(payload["sourceLogWatcher"]["currentProcessActive"])
            self.assertTrue(payload["subtitleWindow"]["currentProcessActive"])
            self.assertEqual(payload["subtitleWindow"]["eventLog"]["lastEvent"]["text"], "translated base")
            self.assertEqual(payload["subtitleWindow"]["eventLog"]["lastEvent"]["matchType"], "exact")
            self.assertEqual(payload["closedLoopProof"]["status"], "closed_loop_displayed")
            self.assertEqual(payload["closedLoopProof"]["latestSourceText"], "\u3055\u3088\u3046\u306a\u3089")
            self.assertTrue(payload["closedLoopProof"]["sourceLogContainsLatestHook"])
            self.assertEqual(payload["closedLoopProof"]["latestMatchedEntryIds"], ["base:2"])
            self.assertEqual(payload["closedLoopProof"]["subtitleText"], "translated base")
            self.assertTrue(payload["clipboardBridge"]["currentProcessActive"])
            self.assertTrue(payload["lunaHookBridge"]["currentProcessActive"])
            self.assertTrue(payload["lunaHookBridge"]["gameProcessActive"])
            self.assertTrue(payload["closedLoopProof"]["lunaHookGameProcessActive"])
            self.assertFalse(payload["processChecks"]["hook"][0]["running"])
            actions_text = " ".join(payload["nextActions"])
            self.assertIn("Full archive translation remains paused", actions_text)
            self.assertIn("--only-new-log-entries", actions_text)
            self.assertIn("clipboard bridge is active", actions_text)
            self.assertIn("LunaHook bridge is active", actions_text)
            self.assertIn("Do not run translate-all", actions_text)

    def test_source_log_status_reports_stale_lunahook_game_pid(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "artemis_ast"),
                ],
            )
            tracker.mark_translated("base:1", "translated base")
            source_log = root / "lunahook-source.txt"
            source_log.write_text("\u304a\u306f\u3088\u3046\n", encoding="utf-8")
            watcher_stdout = root / "source-log-watch.jsonl"
            watcher_stdout.write_text(
                json.dumps(
                    {
                        "status": "processed",
                        "cycle": 1,
                        "result": {
                            "sessionSummary": {"status": "translation_ready", "scopedTranslatedCount": 1},
                            "append": {"logEntryIds": ["base:1"]},
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            subtitle_event_log = root / "subtitle-events.jsonl"
            subtitle_event_log.write_text(
                json.dumps(
                    {
                        "text": "translated base",
                        "matchType": "exact",
                        "visible": True,
                        "missLogged": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            luna_hook_status_log = root / "lunahook-status.jsonl"
            luna_hook_status_log.write_text(
                json.dumps(
                    {
                        "status": "captured",
                        "capturedCount": 1,
                        "text": "\u304a\u306f\u3088\u3046",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            stale_game_pid = 99999999
            report_path = root / "source-log-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "projectRoot": str(project.project_root),
                        "sessionReportPath": str(report_path),
                        "sourceLog": str(source_log),
                        "sourceName": "lunahook",
                        "eventLog": str(subtitle_event_log),
                        "watcher": {
                            "started": True,
                            "pid": os.getpid(),
                            "stdoutPath": str(watcher_stdout),
                            "command": [sys.executable, "-m", "gal_translator", "translate-log"],
                        },
                        "subtitleWindow": {
                            "started": True,
                            "pid": os.getpid(),
                            "command": [sys.executable, "-m", "gal_translator", "subtitle-window"],
                        },
                        "lunaHookBridge": {
                            "started": True,
                            "enabled": True,
                            "pid": os.getpid(),
                            "gamePid": stale_game_pid,
                            "statusLogPath": str(luna_hook_status_log),
                            "command": [sys.executable, "-m", "gal_translator", "luna-hook-bridge", str(stale_game_pid), str(source_log)],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "source-log-status",
                    str(project.project_root),
                    str(source_log),
                    "--session-report",
                    str(report_path),
                    "--game-process",
                    "definitely-not-a-real-game.exe",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["lunaHookBridge"]["currentProcessActive"])
            self.assertFalse(payload["lunaHookBridge"]["gameProcessActive"])
            self.assertEqual(payload["closedLoopProof"]["status"], "hook_game_inactive")
            self.assertFalse(payload["closedLoopProof"]["lunaHookGameProcessActive"])
            actions_text = " ".join(payload["nextActions"])
            self.assertIn("Game process is not running", actions_text)
            self.assertIn("target game pid is no longer active", actions_text)
            self.assertIn("-StartLunaHookBridge", actions_text)
            self.assertNotIn("The LunaHook bridge is active; hooked game text will be appended", actions_text)

    def test_session_info_reports_saved_log_with_no_importable_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            TranslationProgressTracker.initialize(project, [])
            log_path = root / "capture.txt"
            log_path.write_text("WINDOW: Config\nSettings\n", encoding="utf-8")
            report_path = root / "play-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "sessionLogPath": str(log_path),
                        "sessionSummary": {
                            "status": "no_source_text",
                            "projectRoot": str(project.project_root),
                        },
                        "projectInfo": {"projectRoot": str(project.project_root)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sessionLogInspection"]["status"], "no_source_text")
            self.assertEqual(payload["sessionLogInspection"]["captureStats"]["importedEntryCount"], 0)
            self.assertIn("no imported Japanese source lines", payload["nextActions"][0])

    def test_session_info_points_empty_project_with_source_log_at_resume_session(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            TranslationProgressTracker.initialize(project, [])
            log_path = root / "capture.txt"
            log_path.write_text("\u304a\u306f\u3088\u3046", encoding="utf-8")
            report_path = root / "play-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "sessionLogPath": str(log_path),
                        "sessionSummary": {
                            "status": "no_source_text",
                            "projectRoot": str(project.project_root),
                        },
                        "projectInfo": {"projectRoot": str(project.project_root)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sessionLogInspection"]["status"], "has_source")
            self.assertEqual(payload["commands"]["resumeSessionCommand"][2:4], ["gal_translator", "resume-session"])
            self.assertEqual(payload["commands"]["appendSessionLogCommand"][2:4], ["gal_translator", "append-log"])
            self.assertIn("resumeSessionCommand", payload["nextActions"][0])

    def test_resume_session_appends_saved_session_log_before_translation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            TranslationProgressTracker.initialize(project, [])
            log_path = root / "textractor-log.txt"
            log_path.write_text("\u304a\u306f\u3088\u3046", encoding="utf-8")
            report_path = root / "play-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "sessionLogPath": str(log_path),
                        "sessionSummary": {
                            "status": "no_source_text",
                            "projectRoot": str(project.project_root),
                            "batchSize": 2,
                            "model": "gpt-5.5",
                            "translateTimeout": 30,
                            "translateMaxBatches": 0,
                        },
                        "projectInfo": {"projectRoot": str(project.project_root)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            dry_run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            dry_stdout = dry_run.stdout.decode("utf-8", errors="replace")
            dry_stderr = dry_run.stderr.decode("utf-8", errors="replace")
            self.assertEqual(dry_run.returncode, 0, dry_stderr)
            dry_payload = json.loads(dry_stdout)
            self.assertEqual(dry_payload["status"], "append_log_planned")
            self.assertEqual(dry_payload["action"], "append-log")
            self.assertIn("append-log", dry_payload["command"])
            self.assertEqual(TranslationProgressTracker(project.project_root / "translation-state.json").summary().total, 0)

            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {"items": [{"id": "textractor:1", "translation": "translated from saved log"}]},
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "subtitle_ready")
            self.assertEqual(payload["action"], "translate-all")
            self.assertIn("subtitle-window", payload["sessionInfo"]["commands"]["subtitleWindowCommand"])
            self.assertEqual(payload["appendLog"]["addedEntryCount"], 1)
            self.assertEqual(payload["translateAll"]["status"], "ready")
            summary = TranslationProgressTracker(project.project_root / "translation-state.json").summary()
            self.assertEqual(summary.total, 1)
            self.assertEqual(summary.status, "ready")

    def test_resume_session_translates_pending_entries_from_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            report_path = root / "play-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "sessionSummary": {
                            "status": "translation_planned",
                            "projectRoot": str(project.project_root),
                            "batchSize": 2,
                            "model": "gpt-5.5",
                            "translateTimeout": 30,
                            "translateMaxBatches": 0,
                        },
                        "projectInfo": {"projectRoot": str(project.project_root)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {"items": [{"id": "base:1", "translation": "translated one"}]},
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["action"], "translate-all")
            self.assertEqual(payload["status"], "subtitle_ready")
            self.assertEqual(payload["translateAll"]["status"], "ready")
            self.assertIn("subtitle-window", payload["sessionInfo"]["commands"]["subtitleWindowCommand"])
            subtitle_command = payload["sessionInfo"]["commands"]["subtitleWindowCommand"]
            self.assertNotIn("None", subtitle_command)
            self.assertNotIn("--x", subtitle_command)
            self.assertNotIn("--y", subtitle_command)
            self.assertIn("Rerun resume-session with --open-subtitle", payload["nextActions"][0])
            self.assertIn("--size", payload["command"])
            self.assertIn("2", payload["command"])
            project_root = Path(payload["sessionInfo"]["projectRoot"])
            self.assertEqual(TranslationProgressTracker(project_root / "translation-state.json").summary().status, "ready")

    def test_resume_session_can_retry_failed_entries_before_translation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_failed("base:1", "missing translation")
            report_path = root / "play-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "sessionSummary": {
                            "status": "translation_needs_attention",
                            "projectRoot": str(project.project_root),
                            "batchSize": 2,
                            "model": "gpt-5.5",
                            "translateTimeout": 30,
                            "translateMaxBatches": 0,
                        },
                        "projectInfo": {"projectRoot": str(project.project_root)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {"items": [{"id": "base:1", "translation": "translated retry"}]},
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            dry_run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                    "--retry-failed",
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                env=env,
            )
            dry_run_stdout = dry_run_result.stdout.decode("utf-8", errors="replace")
            dry_run_stderr = dry_run_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(dry_run_result.returncode, 0, dry_run_stderr)
            dry_run_payload = json.loads(dry_run_stdout)
            self.assertEqual(dry_run_payload["status"], "retry_failed_planned")
            self.assertEqual(dry_run_payload["command"][2:4], ["gal_translator", "retry-failed"])
            self.assertEqual(TranslationProgressTracker(project.project_root / "translation-state.json").summary().failed, 1)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                    "--retry-failed",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "subtitle_ready")
            self.assertEqual(payload["retryFailed"]["resetCount"], 1)
            self.assertEqual(payload["retryFailed"]["progress"]["pending"], 1)
            self.assertEqual(payload["translateAll"]["status"], "ready")
            self.assertEqual(payload["translateAll"]["finalProgress"]["translated"], 1)
            self.assertEqual(TranslationProgressTracker(project.project_root / "translation-state.json").summary().status, "ready")

    def test_resume_session_plans_default_subtitle_when_saved_command_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("textractor:1", "\u304a\u306f\u3088\u3046", None, "textractor", 1, "clipboard_capture")],
            )
            tracker.mark_translated("textractor:1", "translated one")
            log_path = root / "textractor-log.txt"
            log_path.write_text("\u304a\u306f\u3088\u3046", encoding="utf-8")
            miss_log_path = root / "misses.txt"
            miss_log_path.write_text("", encoding="utf-8")
            report_path = root / "play-session-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "sessionLogPath": str(log_path),
                        "sessionSummary": {
                            "status": "translation_ready",
                            "projectRoot": str(project.project_root),
                            "missLogPath": str(miss_log_path),
                        },
                        "projectInfo": {"projectRoot": str(project.project_root)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                    "--dry-run",
                    "--open-subtitle",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "subtitle_planned")
            self.assertEqual(payload["action"], "subtitle-window")
            self.assertIn("subtitle-window", payload["command"])
            self.assertIn("--source-log", payload["command"])
            self.assertIn(str(log_path), payload["command"])

            info_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
            )
            info_stdout = info_result.stdout.decode("utf-8", errors="replace")
            info_stderr = info_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(info_result.returncode, 0, info_stderr)
            info_payload = json.loads(info_stdout)
            self.assertIn("--open-subtitle", info_payload["commands"]["resumeSessionCommand"])
            self.assertIn("--start-miss-watcher", info_payload["commands"]["resumeSessionCommand"])
            self.assertIn("--start-session-log-watcher", info_payload["commands"]["resumeSessionCommand"])
            self.assertIn("subtitle-window", info_payload["commands"]["subtitleWindowCommand"])
            self.assertIn("translate-log", info_payload["commands"]["translateMissLogCommand"])
            self.assertIn("translate-log", info_payload["commands"]["watchMissLogCommand"])
            self.assertIn("--watch", info_payload["commands"]["watchMissLogCommand"])
            self.assertIn("--watch-require-ready", info_payload["commands"]["watchMissLogCommand"])
            self.assertIn(str(miss_log_path), info_payload["commands"]["watchMissLogCommand"])
            self.assertIn("translate-log", info_payload["commands"]["translateSessionLogCommand"])
            self.assertIn("translate-log", info_payload["commands"]["watchSessionLogCommand"])
            self.assertIn("--watch", info_payload["commands"]["watchSessionLogCommand"])
            self.assertIn("--watch-require-ready", info_payload["commands"]["watchSessionLogCommand"])
            self.assertIn(str(log_path), info_payload["commands"]["watchSessionLogCommand"])

            command_result = subprocess.run(
                [str(part) for part in info_payload["commands"]["resumeSessionCommand"] + ["--dry-run"]],
                check=False,
                capture_output=True,
            )
            command_stdout = command_result.stdout.decode("utf-8", errors="replace")
            command_stderr = command_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(command_result.returncode, 0, command_stderr)
            command_payload = json.loads(command_stdout)
            self.assertEqual(command_payload["status"], "subtitle_planned")
            self.assertEqual(command_payload["action"], "subtitle-window")
            self.assertIn("subtitle-window", command_payload["command"])
            self.assertIn("--source-log", command_payload["command"])
            self.assertIn(str(log_path), command_payload["command"])
            self.assertTrue(command_payload["missWatcher"]["dryRun"])
            self.assertIn("translate-log", command_payload["missWatcher"]["command"])
            self.assertIn(str(miss_log_path), command_payload["missWatcher"]["command"])
            self.assertTrue(command_payload["sessionLogWatcher"]["dryRun"])
            self.assertIn("translate-log", command_payload["sessionLogWatcher"]["command"])
            self.assertIn(str(log_path), command_payload["sessionLogWatcher"]["command"])

    def test_resume_session_can_plan_saved_subtitle_command(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            report_path = root / "live-session-report.json"
            subtitle_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "subtitle-window",
                str(project.project_root),
            ]
            watch_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(root / "misses.txt"),
                "--watch",
                "--watch-require-ready",
            ]
            watch_session_log_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(root / "textractor-log.txt"),
                "--source-name",
                "textractor",
                "--watch",
                "--watch-require-ready",
            ]
            report_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "projectRoot": str(project.project_root),
                        "sessionReportPath": str(report_path),
                        "session": {
                            "sessionSummary": {
                                "status": "subtitle_ready",
                                "projectRoot": str(project.project_root),
                                "subtitleCommand": subtitle_command,
                                "watchMissLogCommand": watch_command,
                                "watchSessionLogCommand": watch_session_log_command,
                            },
                            "projectInfo": {"projectRoot": str(project.project_root)},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "resume-session",
                    str(report_path),
                    "--dry-run",
                    "--open-subtitle",
                    "--start-miss-watcher",
                    "--start-session-log-watcher",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "subtitle_planned")
            self.assertEqual(payload["action"], "subtitle-window")
            self.assertEqual(payload["command"], subtitle_command)
            self.assertEqual(payload["missWatcher"]["command"], watch_command)
            self.assertEqual(payload["sessionLogWatcher"]["command"], watch_session_log_command)
            self.assertTrue(payload["missWatcher"]["dryRun"])
            self.assertTrue(payload["sessionLogWatcher"]["dryRun"])
            self.assertIn("subtitle window", payload["nextActions"][0])
            self.assertIn("miss-log translation", payload["nextActions"][1])
            self.assertIn("session-log translation", payload["nextActions"][2])

    def test_resume_session_script_passes_recovery_options(self) -> None:
        powershell = shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for resume-session script smoke")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            report_path = root / "live-session-report.json"
            subtitle_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "subtitle-window",
                str(project.project_root),
            ]
            watch_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(root / "misses.txt"),
                "--watch",
                "--watch-require-ready",
            ]
            watch_session_log_command = [
                sys.executable,
                "-m",
                "gal_translator",
                "translate-log",
                str(project.project_root),
                str(root / "textractor-log.txt"),
                "--source-name",
                "textractor",
                "--watch",
                "--watch-require-ready",
            ]
            report_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "projectRoot": str(project.project_root),
                        "sessionReportPath": str(report_path),
                        "session": {
                            "sessionSummary": {
                                "status": "subtitle_ready",
                                "projectRoot": str(project.project_root),
                                "subtitleCommand": subtitle_command,
                                "watchMissLogCommand": watch_command,
                                "watchSessionLogCommand": watch_session_log_command,
                            },
                            "projectInfo": {"projectRoot": str(project.project_root)},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path("scripts") / "resume-session.ps1"),
                    "-SessionReport",
                    str(report_path),
                    "-DryRun",
                    "-OpenSubtitle",
                    "-StartMissWatcher",
                    "-StartSessionLogWatcher",
                    "-RetryFailed",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "subtitle_planned")
            self.assertTrue(payload["retryFailedRequested"])
            self.assertEqual(payload["command"], subtitle_command)
            self.assertEqual(payload["missWatcher"]["command"], watch_command)
            self.assertEqual(payload["sessionLogWatcher"]["command"], watch_session_log_command)

    def test_play_session_record_duration_defaults_to_finite_session(self) -> None:
        class Args:
            record_duration = 60.0
            record_until_interrupted = False

        self.assertEqual(_play_session_record_duration(Args()), 60.0)

        Args.record_until_interrupted = True
        self.assertEqual(_play_session_record_duration(Args()), 0.0)

    def test_play_session_empty_log_does_not_prepare_subtitle(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text("WINDOW: Config\n", encoding="utf-8")
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "play-session",
                    str(game_path),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--translate-dry-run",
                    "--subtitle-dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sessionSummary"]["status"], "no_source_text")
            self.assertEqual(payload["sessionSummary"]["sourceEntryCount"], 0)
            self.assertIsNone(payload["subtitleWindow"])
            self.assertIn("Record or provide", payload["nextActions"][0])

    def test_play_session_can_open_subtitle_when_no_new_log_lines_but_existing_state_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "\u304a\u306f\u3088\u3046", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            log_path = root / "capture.txt"
            log_path.write_text("WINDOW: Config\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "play-session",
                    str(game_path),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--append",
                    "--subtitle-dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sessionSummary"]["status"], "subtitle_ready")
            self.assertEqual(payload["sessionSummary"]["capturedEntryCount"], 0)
            self.assertEqual(payload["sessionSummary"]["sourceEntryCount"], 1)
            self.assertEqual(payload["subtitleWindow"]["recordCount"], 1)
            self.assertNotIn("Record or provide", payload["nextActions"][0])

    def test_play_session_reports_when_existing_state_is_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            project = TranslationProjectManager(workspace).create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("old:1", "邵ｺ鄙ｫ繝ｻ郢ｧ蛹ｻ竕ｧ", None, "old", 1, "clipboard_capture")],
            )
            tracker.mark_translated("old:1", "translated old")
            log_path = root / "capture.txt"
            log_path.write_text("邵ｺ・ｾ邵ｺ貅倥・", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "play-session",
                    str(game_dir / "game.exe"),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--translate-dry-run",
                    "--no-subtitle",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["sessionSummary"]["captureMode"], "replace")
            self.assertTrue(payload["sessionSummary"]["existingStateBeforeCapture"])
            self.assertTrue(payload["sessionSummary"]["replacedExistingState"])
            self.assertIn("--append", payload["nextActions"][0])

    def test_play_session_reports_detached_subtitle_exit_as_attention_needed(self) -> None:
        translate_payload = {
            "status": "ready",
            "finalProgress": {"pending": 0, "failed": 0, "translated": 1},
        }
        subtitle_payload = {
            "started": True,
            "detached": True,
            "detachedRunning": False,
            "detachedReturnCode": 7,
            "detachedStdoutPath": "stdout.txt",
            "detachedStderrPath": "stderr.txt",
        }

        status = _session_status(translate_payload, None, subtitle_payload)
        actions = _play_session_next_actions(
            {"status": status, "capturedEntryCount": 1},
            translate_payload,
            None,
            subtitle_payload,
        )

        self.assertEqual(status, "subtitle_exited")
        self.assertIn("detachedStderrPath", actions[0])

    def test_translate_log_appends_misses_and_translates_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "縺翫・繧医≧", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            miss_log = root / "misses.txt"
            miss_log.write_text("縺ｾ縺溘・", encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {"items": [{"id": "misses:1", "translation": "translated miss"}]},
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            replay_log_path = root / "miss-replay.jsonl"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--size",
                    "1",
                    "--timeout",
                    "30",
                    "--replay-event-log",
                    str(replay_log_path),
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["append"]["addedEntryCount"], 1)
            self.assertEqual(payload["translateAll"]["status"], "ready")
            self.assertEqual(payload["projectInfo"]["progress"]["translated"], 2)
            self.assertEqual(payload["replay"]["matched"], 1)
            self.assertEqual(json.loads(replay_log_path.read_text(encoding="utf-8").splitlines()[0])["text"], "translated miss")
            self.assertEqual(payload["sessionSummary"]["status"], "translation_ready")
            self.assertEqual(payload["sessionSummary"]["addedEntryCount"], 1)
            self.assertEqual(payload["sessionSummary"]["translatedCount"], 2)
            self.assertIn("play-session", " ".join(payload["nextActions"]))

    def test_translate_log_only_new_entries_does_not_translate_global_pending(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "縺翫・繧医≧", None, "base", 1, "clipboard_capture")],
            )
            miss_log = root / "misses.txt"
            miss_log.write_text("縺ｾ縺溘・", encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            _write_fake_codex_cmd(
                bin_dir / "codex.cmd",
                {"items": [{"id": "misses:1", "translation": "translated miss"}]},
            )
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--size",
                    "1",
                    "--timeout",
                    "30",
                    "--only-new-log-entries",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["translateScope"], "entry_ids")
            self.assertEqual(payload["append"]["addedEntryIds"], ["misses:1"])
            self.assertEqual(payload["translateAll"]["finalProgress"]["pending"], 1)
            self.assertEqual(payload["translateAll"]["finalScopeProgress"]["pending"], 0)
            self.assertEqual(payload["sessionSummary"]["status"], "translation_ready")
            state = json.loads((project.project_root / "translation-state.json").read_text(encoding="utf-8"))
            by_id = {item["entryId"]: item for item in state["items"]}
            self.assertEqual(by_id["base:1"]["status"], "pending")
            self.assertEqual(by_id["misses:1"]["status"], "translated")

    def test_translate_log_only_new_entries_scopes_existing_pending_log_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [
                    ScriptEntry("base:1", "縺翫・繧医≧", None, "base", 1, "clipboard_capture"),
                    ScriptEntry("misses:1", "縺ｾ縺溘・", None, "misses", 1, "clipboard_capture"),
                ],
            )
            miss_log = root / "misses.txt"
            miss_log.write_text("縺ｾ縺溘・", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--dry-run",
                    "--only-new-log-entries",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["append"]["addedEntryCount"], 0)
            self.assertEqual(payload["append"]["existingLogEntryIds"], ["misses:1"])
            self.assertEqual(payload["append"]["logEntryIds"], ["misses:1"])
            self.assertEqual(payload["translateAll"]["translateScope"], "entry_ids")
            self.assertEqual(payload["translateAll"]["firstBatch"]["entryIds"], ["misses:1"])
            self.assertEqual(payload["projectInfo"]["progress"]["pending"], 2)

    def test_translate_log_only_new_entries_skips_existing_translated_log_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("misses:1", "縺ｾ縺溘・", None, "misses", 1, "clipboard_capture")],
            )
            tracker.mark_translated("misses:1", "translated miss")
            miss_log = root / "misses.txt"
            miss_log.write_text("縺ｾ縺溘・", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--dry-run",
                    "--only-new-log-entries",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["append"]["addedEntryCount"], 0)
            self.assertEqual(payload["append"]["logEntryIds"], ["misses:1"])
            self.assertEqual(payload["translateAll"]["firstBatch"], None)
            self.assertEqual(payload["translateAll"]["finalScopeProgress"]["translated"], 1)

    def test_translate_log_watch_processes_changed_log_once_in_dry_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "縺翫・繧医≧", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            miss_log = root / "misses.txt"
            miss_log.write_text("縺ｾ縺溘・", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--dry-run",
                    "--watch",
                    "--watch-interval",
                    "0.1",
                    "--watch-max-cycles",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            payload = lines[0]
            self.assertEqual(payload["status"], "processed")
            self.assertEqual(payload["cycle"], 1)
            self.assertEqual(payload["result"]["sessionSummary"]["status"], "translation_planned")
            self.assertEqual(payload["result"]["sessionSummary"]["addedEntryCount"], 1)
            self.assertTrue(payload["result"]["translateAll"]["firstBatch"]["entryIds"])

    def test_translate_log_watch_waits_for_translation_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "Workspace" / "projects" / "pending-project"
            project_root.mkdir(parents=True)
            miss_log = root / "misses.txt"
            miss_log.write_text("邵ｺ・ｾ邵ｺ貅倥・", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project_root),
                    str(miss_log),
                    "--dry-run",
                    "--watch",
                    "--watch-interval",
                    "0.1",
                    "--watch-max-cycles",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            payload = lines[0]
            self.assertEqual(payload["status"], "idle")
            self.assertEqual(payload["reason"], "translation_state_missing")
            self.assertEqual(payload["idleCount"], 1)

    def test_translate_log_watch_waits_for_active_translation_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            tracker = TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "邵ｺ鄙ｫ繝ｻ郢ｧ蛹ｻ竕ｧ", None, "base", 1, "clipboard_capture")],
            )
            tracker.mark_translated("base:1", "translated base")
            miss_log = root / "misses.txt"
            miss_log.write_text("邵ｺ・ｾ邵ｺ貅倥・", encoding="utf-8")
            lock_path = project.project_root / "logs" / "translation.lock"
            lock_path.write_text("locked", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--dry-run",
                    "--watch",
                    "--watch-interval",
                    "0.1",
                    "--watch-max-cycles",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            payload = lines[0]
            self.assertEqual(payload["status"], "idle")
            self.assertEqual(payload["reason"], "translation_locked")
            self.assertEqual(payload["result"]["translateAll"]["status"], "translation_locked")

    def test_translate_log_watch_can_wait_until_project_is_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            project = TranslationProjectManager(root / "Workspace").create_project(game_dir)
            TranslationProgressTracker.initialize(
                project,
                [ScriptEntry("base:1", "驍ｵ・ｺ驗呻ｽｫ郢晢ｽｻ驛｢・ｧ陋ｹ・ｻ遶包ｽｧ", None, "base", 1, "clipboard_capture")],
            )
            miss_log = root / "misses.txt"
            miss_log.write_text("驍ｵ・ｺ繝ｻ・ｾ驍ｵ・ｺ雋・･繝ｻ", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "translate-log",
                    str(project.project_root),
                    str(miss_log),
                    "--dry-run",
                    "--watch",
                    "--watch-require-ready",
                    "--watch-interval",
                    "0.1",
                    "--watch-max-cycles",
                    "1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            self.assertEqual(len(lines), 1)
            payload = lines[0]
            self.assertEqual(payload["status"], "idle")
            self.assertEqual(payload["reason"], "translation_not_ready")
            self.assertEqual(payload["idleCount"], 1)
            self.assertEqual(TranslationProgressTracker(project.project_root / "translation-state.json").summary().total, 1)

    def test_live_session_script_reports_watcher_command_and_status_actions(self) -> None:
        powershell = shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for live-session script smoke")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            log_path = workspace / "captures" / "game-live-capture.txt"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002", encoding="utf-8")

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path("scripts") / "live-session.ps1"),
                    "-GamePath",
                    str(game_dir / "game.exe"),
                    "-Workspace",
                    str(workspace),
                    "-DryRun",
                    "-NoSubtitle",
                    "-SubtitleSourceLog",
                    "-WatchMaxCycles",
                    "1",
                    "-WatchInterval",
                    "0.1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["sessionLogPath"], str(log_path))
            self.assertTrue(Path(payload["sessionReportPath"]).is_file())
            report_payload = json.loads(Path(payload["sessionReportPath"]).read_text(encoding="utf-8"))
            self.assertEqual(report_payload["session"]["sessionSummary"]["status"], "translation_planned")
            self.assertIn("resume-session.ps1", " ".join(payload["resumeCommand"]))
            self.assertIn("-SessionReport", payload["resumeCommand"])
            self.assertIn(payload["sessionReportPath"], payload["resumeCommand"])
            self.assertIn("-StartMissWatcher", payload["resumeCommand"])
            self.assertIn("-StartSessionLogWatcher", payload["resumeCommand"])
            self.assertNotIn("-OpenSubtitle", payload["resumeCommand"])
            self.assertEqual(payload["session"]["sessionLogPath"], str(log_path))
            self.assertEqual(payload["session"]["sessionSummary"]["status"], "translation_planned")
            self.assertIn("without -DryRun", payload["nextActions"][0])
            self.assertTrue(payload["missWatcher"]["started"])
            self.assertFalse(payload["missWatcher"]["running"])
            self.assertFalse(payload["missWatcher"]["willStopOnExit"])
            self.assertIn("-WatchRequireReady", payload["missWatcher"]["command"])
            self.assertTrue(Path(payload["missWatcher"]["stdoutPath"]).is_file())
            self.assertTrue(payload["sessionLogWatcher"]["started"])
            self.assertFalse(payload["sessionLogWatcher"]["running"])
            self.assertFalse(payload["sessionLogWatcher"]["willStopOnExit"])
            self.assertIn("-SourceName", payload["sessionLogWatcher"]["command"])
            self.assertIn("textractor", payload["sessionLogWatcher"]["command"])
            self.assertIn(str(log_path), payload["sessionLogWatcher"]["command"])
            self.assertIn("-WatchRequireReady", payload["sessionLogWatcher"]["command"])
            self.assertTrue(Path(payload["sessionLogWatcher"]["stdoutPath"]).is_file())

            resume_result = subprocess.run(
                [str(part) for part in payload["resumeCommand"] + ["-DryRun"]],
                check=False,
                capture_output=True,
            )
            resume_stdout = resume_result.stdout.decode("utf-8", errors="replace")
            resume_stderr = resume_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(resume_result.returncode, 0, resume_stderr)
            resume_payload = json.loads(resume_stdout)
            self.assertEqual(resume_payload["status"], "translation_planned")
            self.assertEqual(resume_payload["action"], "translate-all")
            self.assertEqual(resume_payload["command"][2:4], ["gal_translator", "translate-all"])

    def test_source_log_session_script_plans_scoped_watcher_and_subtitle_window(self) -> None:
        powershell = shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for source-log-session script smoke")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            project_root.mkdir()
            source_log = root / "lunahook-source.txt"
            source_log.write_text("\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002", encoding="utf-8")

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path("scripts") / "source-log-session.ps1"),
                    "-ProjectRoot",
                    str(project_root),
                    "-SourceLog",
                    str(source_log),
                    "-SourceName",
                    "lunahook",
                    "-StartClipboardBridge",
                    "-ClipboardDuration",
                    "30",
                    "-StartLunaHookBridge",
                    "-LunaHookGamePid",
                    "1234",
                    "-LunaHookDuration",
                    "30",
                    "-DryRun",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["projectRoot"], str(project_root))
            self.assertEqual(payload["sourceLog"], str(source_log))
            self.assertEqual(payload["sourceName"], "lunahook")
            self.assertTrue(payload["scopedTranslation"])
            self.assertFalse(payload["watcher"]["started"])
            self.assertFalse(payload["subtitleWindow"]["started"])
            self.assertTrue(payload["clipboardBridge"]["enabled"])
            self.assertFalse(payload["clipboardBridge"]["started"])
            self.assertTrue(payload["lunaHookBridge"]["enabled"])
            self.assertFalse(payload["lunaHookBridge"]["started"])
            self.assertEqual(payload["lunaHookBridge"]["gamePid"], 1234)
            self.assertTrue(Path(payload["sessionReportPath"]).is_file())
            report_payload = json.loads(Path(payload["sessionReportPath"]).read_text(encoding="utf-8"))
            self.assertEqual(report_payload["status"], "planned")
            self.assertEqual(report_payload["sourceLog"], str(source_log))
            self.assertIn("-StartClipboardBridge", payload["restartCommand"])
            self.assertIn("-StartLunaHookBridge", payload["restartCommand"])
            self.assertIn("-ClipboardDuration", payload["restartCommand"])
            self.assertIn("-LunaHookDuration", payload["restartCommand"])
            self.assertIn("source-log-session.ps1", " ".join(payload["restartCommand"]))
            self.assertIn("-SessionReport", payload["restartCommand"])
            self.assertIn(payload["sessionReportPath"], payload["restartCommand"])
            self.assertIn("--only-new-log-entries", payload["watcher"]["command"])
            self.assertNotIn("--watch-require-ready", payload["watcher"]["command"])
            self.assertIn("--watch", payload["watcher"]["command"])
            self.assertIn("--max-batches", payload["watcher"]["command"])
            self.assertIn("1", payload["watcher"]["command"])
            self.assertIn("--source-log", payload["subtitleWindow"]["command"])
            self.assertIn("--source-log-name", payload["subtitleWindow"]["command"])
            self.assertIn("lunahook", payload["subtitleWindow"]["command"])
            self.assertIn("--miss-log", payload["subtitleWindow"]["command"])
            self.assertIn("--event-log", payload["subtitleWindow"]["command"])
            self.assertIn("record-clipboard", payload["clipboardBridge"]["command"])
            self.assertIn(str(source_log), payload["clipboardBridge"]["command"])
            self.assertIn("--duration", payload["clipboardBridge"]["command"])
            self.assertIn("30", payload["clipboardBridge"]["command"])
            self.assertIn("luna-hook-bridge", payload["lunaHookBridge"]["command"])
            self.assertIn(str(source_log), payload["lunaHookBridge"]["command"])
            self.assertIn("--status-log", payload["lunaHookBridge"]["command"])
            self.assertIn("--hook-code", payload["lunaHookBridge"]["command"])
            self.assertTrue(str(project_root / "logs") in payload["missLog"])
            self.assertTrue(any("--only-new-log-entries" in action for action in payload["nextActions"]))
            self.assertTrue(any("clipboard bridge" in action for action in payload["nextActions"]))
            self.assertTrue(any("LunaHook bridge" in action for action in payload["nextActions"]))

    def test_source_log_session_script_creates_missing_source_log_for_live_appenders(self) -> None:
        powershell = shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for source-log-session script smoke")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            project_root.mkdir()
            source_log = root / "new-session" / "lunahook-source.txt"

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path("scripts") / "source-log-session.ps1"),
                    "-ProjectRoot",
                    str(project_root),
                    "-SourceLog",
                    str(source_log),
                    "-NoWatcher",
                    "-NoSubtitle",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "started")
            self.assertTrue(source_log.is_file())
            self.assertTrue(payload["sourceLogExists"])
            self.assertTrue(payload["sourceLogCreated"])
            self.assertTrue(Path(payload["sessionReportPath"]).is_file())
            report_payload = json.loads(Path(payload["sessionReportPath"]).read_text(encoding="utf-8"))
            self.assertTrue(report_payload["sourceLogCreated"])
            self.assertEqual(report_payload["restartCommand"], payload["restartCommand"])
            self.assertFalse(payload["watcher"]["started"])
            self.assertFalse(payload["subtitleWindow"]["started"])
            self.assertTrue(any("created as an empty file" in action for action in payload["nextActions"]))

    def test_live_session_cli_reports_watcher_command_and_resume_command(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            (game_dir / "game.exe").write_bytes(b"MZ")
            workspace = root / "Workspace"
            log_path = root / "capture.txt"
            log_path.write_text("\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "live-session",
                    str(game_dir / "game.exe"),
                    str(log_path),
                    "--workspace",
                    str(workspace),
                    "--translate-dry-run",
                    "--no-subtitle",
                    "--subtitle-source-log",
                    "--watch-max-cycles",
                    "1",
                    "--watch-interval",
                    "0.1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["session"]["sessionSummary"]["status"], "translation_planned")
            self.assertTrue(Path(payload["sessionReportPath"]).is_file())
            report_payload = json.loads(Path(payload["sessionReportPath"]).read_text(encoding="utf-8"))
            self.assertEqual(report_payload["status"], "completed")
            self.assertTrue(payload["missWatcher"]["started"])
            self.assertFalse(payload["missWatcher"]["running"])
            self.assertIn("--watch-require-ready", payload["missWatcher"]["command"])
            self.assertTrue(payload["missWatcher"]["stdout"]["exists"])
            self.assertEqual(payload["missWatcher"]["stdout"]["lastEvent"]["reason"], "log_missing")
            self.assertEqual(payload["missWatcher"]["statusSummary"]["lastReason"], "log_missing")
            self.assertTrue(payload["sessionLogWatcher"]["started"])
            self.assertFalse(payload["sessionLogWatcher"]["running"])
            self.assertIn("--source-name", [part.lower() for part in payload["sessionLogWatcher"]["command"]])
            self.assertIn("textractor", payload["sessionLogWatcher"]["command"])
            self.assertTrue(payload["sessionLogWatcher"]["stdout"]["exists"])
            self.assertEqual(payload["sessionLogWatcher"]["stdout"]["lastEvent"]["reason"], "translation_not_ready")
            self.assertEqual(payload["sessionLogWatcher"]["statusSummary"]["lastReason"], "translation_not_ready")
            self.assertEqual(report_payload["missWatcher"]["statusSummary"]["lastReason"], "log_missing")
            self.assertEqual(report_payload["sessionLogWatcher"]["statusSummary"]["lastReason"], "translation_not_ready")
            self.assertTrue(any("watched log is missing" in action for action in payload["nextActions"]))
            self.assertTrue(any("main project translation to finish" in action for action in payload["nextActions"]))
            self.assertIn("--start-session-log-watcher", payload["resumeCommand"])
            self.assertNotIn("--open-subtitle", payload["resumeCommand"])

            resume_result = subprocess.run(
                [str(part) for part in payload["resumeCommand"] + ["--dry-run"]],
                check=False,
                capture_output=True,
            )
            resume_stdout = resume_result.stdout.decode("utf-8", errors="replace")
            resume_stderr = resume_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(resume_result.returncode, 0, resume_stderr)
            resume_payload = json.loads(resume_stdout)
            self.assertEqual(resume_payload["status"], "translation_planned")
            self.assertEqual(resume_payload["action"], "translate-all")

            info_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "session-info",
                    payload["sessionReportPath"],
                ],
                check=False,
                capture_output=True,
            )
            info_stdout = info_result.stdout.decode("utf-8", errors="replace")
            info_stderr = info_result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(info_result.returncode, 0, info_stderr)
            info_payload = json.loads(info_stdout)
            self.assertEqual(info_payload["reportType"], "live-session")
            self.assertEqual(info_payload["commands"]["watchMissLogCommand"], payload["missWatcher"]["command"])
            self.assertEqual(info_payload["commands"]["watchSessionLogCommand"], payload["sessionLogWatcher"]["command"])
            self.assertIn("--start-miss-watcher", info_payload["commands"]["resumeSessionCommand"])
            self.assertIn("--start-session-log-watcher", info_payload["commands"]["resumeSessionCommand"])

    def test_live_session_script_surfaces_no_source_text_status(self) -> None:
        powershell = shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for live-session script smoke")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            workspace = root / "Workspace"
            log_path = workspace / "captures" / "game-live-capture.txt"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("WINDOW: Config\n", encoding="utf-8")

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path("scripts") / "live-session.ps1"),
                    "-GamePath",
                    str(game_path),
                    "-Workspace",
                    str(workspace),
                    "-DryRun",
                    "-NoSubtitle",
                    "-WatchMaxCycles",
                    "1",
                    "-WatchInterval",
                    "0.1",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["session"]["sessionSummary"]["status"], "no_source_text")
            self.assertIn("No Japanese source lines", payload["nextActions"][0])
            self.assertEqual(payload["sessionLogPath"], str(log_path))

    def test_live_session_script_surfaces_detached_subtitle_exit(self) -> None:
        powershell = shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is required for live-session script smoke")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir()
            shutil.copyfile(Path("scripts") / "live-session.ps1", scripts_dir / "live-session.ps1")
            (scripts_dir / "translate-miss-log.ps1").write_text(
                """
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$CommandArgs
)
Start-Sleep -Seconds 30
""".strip(),
                encoding="utf-8",
            )
            (scripts_dir / "translated-session.ps1").write_text(
                """
param(
    [string]$GamePath,
    [string]$LogPath,
    [string]$Workspace,
    [string]$SourceName,
    [int]$BatchSize,
    [int]$TranslateTimeout,
    [int]$TranslateMaxBatches,
    [string]$SubtitleMissLog,
    [int]$X,
    [int]$Y,
    [int]$Width,
    [int]$Height,
    [int]$FontSize,
    [double]$Opacity,
    [double]$ClearAfter,
    [string]$FontFamily,
    [switch]$SubtitleDetach
)
[ordered]@{
    sessionSummary = [ordered]@{
        status = "subtitle_exited"
    }
    subtitleWindow = [ordered]@{
        detached = $true
        detachedStderrPath = "C:\\temp\\subtitle-stderr.txt"
        detachedStdoutPath = "C:\\temp\\subtitle-stdout.txt"
    }
} | ConvertTo-Json -Depth 10
exit 0
""".strip(),
                encoding="utf-8",
            )
            game_dir = root / "Game"
            game_dir.mkdir()
            game_path = game_dir / "game.exe"
            game_path.write_bytes(b"MZ")
            log_path = root / "capture.txt"
            log_path.write_text("\u3053\u308c\u306f\u30c6\u30b9\u30c8\u3067\u3059\u3002", encoding="utf-8")
            workspace = root / "Workspace"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(scripts_dir / "live-session.ps1"),
                    "-GamePath",
                    str(game_path),
                    "-LogPath",
                    str(log_path),
                    "-Workspace",
                    str(workspace),
                    "-SubtitleDetach",
                    "-WatchInterval",
                    "0.1",
                ],
                check=False,
                capture_output=True,
                env=env,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["session"]["sessionSummary"]["status"], "subtitle_exited")
            self.assertIn("subtitle-stderr.txt", payload["nextActions"][0])
            self.assertFalse(payload["missWatcher"]["running"])
            self.assertTrue(payload["missWatcher"]["willStopOnExit"])


if __name__ == "__main__":
    unittest.main()


def _pf8_entry(path: str, offset: int, size: int) -> bytes:
    raw_path = path.encode("utf-8")
    return (
        offset.to_bytes(4, "little")
        + size.to_bytes(4, "little")
        + len(raw_path).to_bytes(4, "little")
        + raw_path
        + b"\x00\x00\x00\x00"
    )


def _write_fake_codex_cmd(path: Path, result: dict[str, object]) -> None:
    payload = json.dumps(result, ensure_ascii=True).replace('"', '^"')
    path.write_text(
        "\r\n".join(
            [
                "@echo off",
                "set \"out=\"",
                ":loop",
                "if \"%~1\"==\"\" goto done",
                "if \"%~1\"==\"-o\" (",
                "  set \"out=%~2\"",
                "  shift",
                ")",
                "shift",
                "goto loop",
                ":done",
                f"> \"%out%\" echo {payload}",
                "exit /b 0",
            ]
        ),
        encoding="utf-8",
    )


def _write_failing_codex_cmd(path: Path) -> None:
    path.write_text(
        "\r\n".join(
            [
                "@echo off",
                "echo fake codex stdout 1",
                "echo fake codex stdout 2",
                "echo fake codex stderr 1 1>&2",
                "echo fake codex stderr 2 1>&2",
                "exit /b 9",
            ]
        ),
        encoding="utf-8",
    )


def _write_slow_codex_cmd(path: Path, result: dict[str, object]) -> None:
    payload = json.dumps(result, ensure_ascii=True).replace('"', '^"')
    path.write_text(
        "\r\n".join(
            [
                "@echo off",
                "set \"out=\"",
                ":loop",
                "if \"%~1\"==\"\" goto done",
                "if \"%~1\"==\"-o\" (",
                "  set \"out=%~2\"",
                "  shift",
                ")",
                "shift",
                "goto loop",
                ":done",
                f"> \"%out%\" echo {payload}",
                "powershell -NoProfile -Command \"Start-Sleep -Seconds 5\"",
                "exit /b 0",
            ]
        ),
        encoding="utf-8",
    )
