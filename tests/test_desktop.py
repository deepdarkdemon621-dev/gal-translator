import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from gal_translator.desktop import (
    DesktopShellConfig,
    build_live_session_command,
    build_source_log_session_command,
    build_subtitle_window_command,
    build_translate_all_command,
    desktop_shell_payload,
    failed_items_payload,
)


class DesktopShellTests(unittest.TestCase):
    def test_desktop_payload_exposes_two_product_entries_and_mvp_scope(self) -> None:
        config = DesktopShellConfig(workspace=Path("Workspace"))

        payload = desktop_shell_payload(config)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(
            [entry["id"] for entry in payload["entries"]],
            ["translation_preparation", "play_output"],
        )
        self.assertIn("translate-all", payload["entries"][0]["actions"])
        self.assertIn("retry-failed", payload["entries"][0]["actions"])
        self.assertIn("subtitle-window", payload["entries"][1]["actions"])
        self.assertIn("source-log-session", payload["entries"][1]["actions"])
        self.assertIn("sourceLogSession", payload["commandTemplates"])
        self.assertEqual(payload["config"]["sourceLogBatchSize"], 1)
        self.assertEqual(payload["config"]["sourceLogMaxBatches"], 1)
        self.assertFalse(payload["config"]["lunaHookBridge"]["enabled"])
        self.assertTrue(payload["mvpScope"]["externalSubtitleWindow"])
        self.assertTrue(payload["mvpScope"]["localRuntimeMatching"])
        self.assertFalse(payload["mvpScope"]["inGameTextRewrite"])
        self.assertFalse(payload["mvpScope"]["drmBypass"])
        self.assertFalse(payload["mvpScope"]["archiveCracking"])
        self.assertFalse(payload["mvpScope"]["defaultRealtimeLlmTranslation"])
        self.assertFalse(payload["mvpScope"]["defaultOcrTranslation"])

    def test_desktop_dry_run_cli_outputs_shell_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "desktop",
                    "--workspace",
                    str(Path(tmp) / "Workspace"),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["app"], "Gal Translator Desktop Shell")
            self.assertEqual(payload["entries"][0]["id"], "translation_preparation")
            self.assertEqual(payload["entries"][1]["id"], "play_output")
            self.assertEqual(payload["config"]["workspace"], str(Path(tmp) / "Workspace"))

    def test_desktop_dry_run_cli_can_plan_lunahook_play_output(self) -> None:
        with TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "desktop",
                    "--workspace",
                    str(Path(tmp) / "Workspace"),
                    "--source-name",
                    "lunahook",
                    "--start-luna-hook-bridge",
                    "--luna-hook-game-process",
                    "selectoblige.exe",
                    "--luna-hook-code",
                    "HOOK-A",
                    "--luna-hook-code",
                    "HOOK-B",
                    "--luna-hook-duration",
                    "30",
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["config"]["lunaHookBridge"]["enabled"])
            self.assertEqual(payload["config"]["lunaHookBridge"]["gameProcess"], "selectoblige.exe")
            self.assertEqual(payload["config"]["lunaHookBridge"]["hookCodes"], ["HOOK-A", "HOOK-B"])
            command = payload["commandTemplates"]["sourceLogSession"]
            self.assertIn("-StartLunaHookBridge", command)
            self.assertIn("-LunaHookGameProcess", command)
            self.assertEqual(command[command.index("-LunaHookGameProcess") + 1], "selectoblige.exe")
            self.assertEqual(command.count("-LunaHookCode"), 2)
            self.assertNotIn("-StartClipboardBridge", command)

    def test_translate_all_command_can_retry_failed_entries(self) -> None:
        config = DesktopShellConfig(workspace=Path("Workspace"), batch_size=7, model="model-x", translate_timeout=123)

        command = build_translate_all_command("Project", config, retry_failed=True)

        self.assertEqual(command[2:5], ["gal_translator", "translate-all", "Project"])
        self.assertIn("--retry-failed", command)
        self.assertEqual(command[command.index("--size") + 1], "7")
        self.assertEqual(command[command.index("--model") + 1], "model-x")
        self.assertEqual(command[command.index("--timeout") + 1], "123")

    def test_subtitle_command_follows_source_log_and_writes_misses(self) -> None:
        config = DesktopShellConfig(workspace=Path("Workspace"), source_name="lunahook")

        command = build_subtitle_window_command(
            "Project",
            config,
            source_log="hook.txt",
            miss_log="misses.txt",
            dry_run=True,
        )

        self.assertEqual(command[2:5], ["gal_translator", "subtitle-window", "Project"])
        self.assertIn("--source-log", command)
        self.assertEqual(command[command.index("--source-log") + 1], "hook.txt")
        self.assertIn("--source-log-name", command)
        self.assertEqual(command[command.index("--source-log-name") + 1], "lunahook")
        self.assertIn("--miss-log", command)
        self.assertEqual(command[command.index("--miss-log") + 1], "misses.txt")
        self.assertIn("--dry-run", command)

    def test_live_session_command_uses_external_subtitle_and_miss_feedback(self) -> None:
        config = DesktopShellConfig(workspace=Path("Workspace"), source_name="textractor")

        command = build_live_session_command("Game.exe", "capture.txt", "misses.txt", config, dry_run=True)

        self.assertEqual(command[2:5], ["gal_translator", "live-session", "Game.exe"])
        self.assertIn("--subtitle-source-log", command)
        self.assertIn("--subtitle-detach", command)
        self.assertIn("--subtitle-miss-log", command)
        self.assertEqual(command[command.index("--subtitle-miss-log") + 1], "misses.txt")
        self.assertIn("--translate-dry-run", command)
        self.assertIn("--subtitle-dry-run", command)
        self.assertNotIn("--ocr", command)
        self.assertNotIn("--rewrite-game", command)

    def test_source_log_session_command_uses_scoped_cost_control_defaults(self) -> None:
        config = DesktopShellConfig(workspace=Path("Workspace"), source_name="lunahook", model="model-x")

        command = build_source_log_session_command(
            "Project",
            "hook.txt",
            config,
            miss_log="misses.txt",
            dry_run=True,
        )

        self.assertEqual(command[:5], ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
        self.assertIn("source-log-session.ps1", command[5])
        self.assertIn("-ProjectRoot", command)
        self.assertEqual(command[command.index("-ProjectRoot") + 1], "Project")
        self.assertIn("-SourceLog", command)
        self.assertEqual(command[command.index("-SourceLog") + 1], "hook.txt")
        self.assertIn("-SourceName", command)
        self.assertEqual(command[command.index("-SourceName") + 1], "lunahook")
        self.assertIn("-BatchSize", command)
        self.assertEqual(command[command.index("-BatchSize") + 1], "1")
        self.assertIn("-MaxBatches", command)
        self.assertEqual(command[command.index("-MaxBatches") + 1], "1")
        self.assertIn("-MissLog", command)
        self.assertEqual(command[command.index("-MissLog") + 1], "misses.txt")
        self.assertIn("-DryRun", command)
        self.assertNotIn("-AllPending", command)
        self.assertNotIn("-WatchRequireReady", command)
        self.assertNotIn("-StartLunaHookBridge", command)

    def test_source_log_session_command_can_start_lunahook_bridge(self) -> None:
        config = DesktopShellConfig(
            workspace=Path("Workspace"),
            source_name="lunahook",
            start_luna_hook_bridge=True,
            luna_hook_game_process="selectoblige.exe",
            luna_hook_codes=("HOOK-A", "HOOK-B"),
            luna_hook_duration=30.0,
            luna_hook_max_events=7,
            luna_hook_idle_timeout=3.5,
        )

        command = build_source_log_session_command(
            "Project",
            "hook.txt",
            config,
            miss_log="misses.txt",
            dry_run=True,
        )

        self.assertIn("-StartLunaHookBridge", command)
        self.assertIn("-LunaHookGameProcess", command)
        self.assertEqual(command[command.index("-LunaHookGameProcess") + 1], "selectoblige.exe")
        self.assertIn("-LunaHookDuration", command)
        self.assertEqual(command[command.index("-LunaHookDuration") + 1], "30.0")
        self.assertIn("-LunaHookMaxEvents", command)
        self.assertEqual(command[command.index("-LunaHookMaxEvents") + 1], "7")
        self.assertIn("-LunaHookIdleTimeout", command)
        self.assertEqual(command[command.index("-LunaHookIdleTimeout") + 1], "3.5")
        self.assertEqual(command.count("-LunaHookCode"), 2)
        self.assertIn("HOOK-A", command)
        self.assertIn("HOOK-B", command)
        self.assertNotIn("-StartClipboardBridge", command)

    def test_failed_items_payload_reports_retry_state_for_ui(self) -> None:
        with TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "Project"
            project_root.mkdir()
            (project_root / "translation-state.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "entryId": "cap:1",
                                "status": "failed",
                                "error": "Codex output missing id",
                                "retryCount": 3,
                                "maxRetryReached": True,
                            },
                            {
                                "entryId": "cap:2",
                                "status": "translated",
                                "error": "",
                                "retryCount": 0,
                                "maxRetryReached": False,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = failed_items_payload(project_root)

            self.assertEqual(payload["failedCount"], 1)
            self.assertEqual(payload["shownCount"], 1)
            self.assertEqual(payload["items"][0]["entryId"], "cap:1")
            self.assertEqual(payload["items"][0]["retryCount"], 3)
            self.assertTrue(payload["items"][0]["maxRetryReached"])


if __name__ == "__main__":
    unittest.main()
