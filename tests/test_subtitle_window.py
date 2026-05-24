import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from gal_translator.cli import (
    _DETACHED_PROCESSES,
    _append_miss_log_line,
    _clipboard_runtime_event_payload,
    _start_detached_subtitle_window,
    _subtitle_runtime_event_payload,
)
from gal_translator.matching import MatchIndex, TranslationRecord
from gal_translator.runtime import RuntimeSubtitleService
from gal_translator.subtitle_window import SubtitleViewModel, SubtitleViewState, SubtitleWindowConfig


class SubtitleWindowConfigTests(unittest.TestCase):
    def test_config_builds_geometry_with_optional_position(self) -> None:
        self.assertEqual(SubtitleWindowConfig(width=900, height=140).geometry(), "900x140")
        self.assertEqual(
            SubtitleWindowConfig(width=900, height=140, x=120, y=80).geometry(),
            "900x140+120+80",
        )

    def test_config_clamps_opacity_and_poll_interval(self) -> None:
        self.assertEqual(SubtitleWindowConfig(opacity=2.0).normalized_opacity(), 1.0)
        self.assertEqual(SubtitleWindowConfig(opacity=0.1).normalized_opacity(), 0.2)
        self.assertEqual(SubtitleWindowConfig(interval_ms=10).poll_interval_ms(), 50)
        self.assertEqual(SubtitleWindowConfig(exit_after_ms=-100).auto_exit_after_ms(), 0)
        self.assertEqual(SubtitleWindowConfig(exit_after_ms=1500).auto_exit_after_ms(), 1500)

    def test_config_round_trips_json_payload(self) -> None:
        config = SubtitleWindowConfig(
            interval_ms=333,
            font_size=32,
            opacity=0.7,
            width=1100,
            height=130,
            topmost=False,
            x=40,
            y=720,
            font_family="Test Font",
            background="#111111",
            foreground="#eeeeee",
            clear_after_ms=2500,
            exit_after_ms=1500,
        )

        restored = SubtitleWindowConfig.from_json_dict(config.to_json_dict())

        self.assertEqual(restored.geometry(), "1100x130+40+720")
        self.assertEqual(restored.poll_interval_ms(), 333)
        self.assertEqual(restored.font_size, 32)
        self.assertEqual(restored.normalized_opacity(), 0.7)
        self.assertFalse(restored.topmost)
        self.assertEqual(restored.font_family, "Test Font")
        self.assertEqual(restored.clear_after_ms, 2500)
        self.assertEqual(restored.exit_after_ms, 1500)


class SubtitleViewModelTests(unittest.TestCase):
    def test_view_model_shows_translated_chinese_only_for_matches(self) -> None:
        view_model = SubtitleViewModel(
            RuntimeSubtitleService(
                MatchIndex(
                    [
                        TranslationRecord(
                            entry_id="cap:1",
                            source="source one",
                            translation="translated one",
                            status="translated",
                        )
                    ]
                )
            )
        )

        state = view_model.update_source("source one")

        self.assertEqual(state.text, "translated one")
        self.assertEqual(state.match_type, "exact")
        self.assertTrue(state.visible)

    def test_view_model_keeps_unmatched_state_quiet(self) -> None:
        view_model = SubtitleViewModel(RuntimeSubtitleService(MatchIndex([])))

        state = view_model.update_source("unmatched source")

        self.assertEqual(state.text, "")
        self.assertEqual(state.match_type, "unmatched")
        self.assertFalse(state.visible)

    def test_view_model_can_clear_stale_subtitle_text(self) -> None:
        view_model = SubtitleViewModel(
            RuntimeSubtitleService(
                MatchIndex(
                    [
                        TranslationRecord(
                            entry_id="cap:1",
                            source="source one",
                            translation="translated one",
                            status="translated",
                        )
                    ]
                )
            )
        )

        visible_state = view_model.update_source("source one", now_ms=1000)
        early_state = view_model.clear_if_stale(now_ms=1499, clear_after_ms=500)
        cleared_state = view_model.clear_if_stale(now_ms=1500, clear_after_ms=500)

        self.assertTrue(visible_state.visible)
        self.assertTrue(early_state.visible)
        self.assertEqual(cleared_state.text, "")
        self.assertEqual(cleared_state.match_type, "cleared")
        self.assertFalse(cleared_state.visible)

    def test_view_model_refreshes_previous_unmatched_source_after_translation_reload(self) -> None:
        runtime = RuntimeSubtitleService(MatchIndex([]))
        view_model = SubtitleViewModel(runtime)

        unmatched_state = view_model.update_source("source one", now_ms=1000)
        runtime.match_index = MatchIndex(
            [
                TranslationRecord(
                    entry_id="cap:1",
                    source="source one",
                    translation="translated one",
                    status="translated",
                )
            ]
        )
        refreshed_state, refreshed = view_model.refresh_unmatched_source(now_ms=1250)

        self.assertFalse(unmatched_state.visible)
        self.assertTrue(refreshed)
        self.assertEqual(refreshed_state.text, "translated one")
        self.assertEqual(refreshed_state.match_type, "exact")
        self.assertEqual(refreshed_state.updated_at_ms, 1250)

    def test_view_model_does_not_restore_cleared_subtitle_on_idle_refresh(self) -> None:
        runtime = RuntimeSubtitleService(
            MatchIndex(
                [
                    TranslationRecord(
                        entry_id="cap:1",
                        source="source one",
                        translation="translated one",
                        status="translated",
                    )
                ]
            )
        )
        view_model = SubtitleViewModel(runtime)

        view_model.update_source("source one", now_ms=1000)
        cleared_state = view_model.clear_if_stale(now_ms=1500, clear_after_ms=500)
        refreshed_state, refreshed = view_model.refresh_unmatched_source(now_ms=1750)

        self.assertEqual(cleared_state.match_type, "cleared")
        self.assertFalse(refreshed)
        self.assertEqual(refreshed_state.match_type, "cleared")
        self.assertFalse(refreshed_state.visible)


class SubtitleRuntimeEventTests(unittest.TestCase):
    def test_event_payload_omits_source_by_default(self) -> None:
        payload = _subtitle_runtime_event_payload(
            "source one",
            SubtitleViewState(text="translated one", match_type="exact", visible=True),
            include_source=False,
        )

        self.assertEqual(payload["text"], "translated one")
        self.assertEqual(payload["matchType"], "exact")
        self.assertTrue(payload["visible"])
        self.assertFalse(payload["missLogged"])
        self.assertNotIn("rawText", payload)

    def test_event_payload_can_include_source_for_diagnostics(self) -> None:
        payload = _subtitle_runtime_event_payload(
            "source one",
            SubtitleViewState(text="", match_type="unmatched", visible=False),
            include_source=True,
            miss_logged=True,
        )

        self.assertEqual(payload["rawText"], "source one")
        self.assertFalse(payload["visible"])
        self.assertTrue(payload["missLogged"])

    def test_clipboard_event_payload_omits_source_by_default(self) -> None:
        payload = _clipboard_runtime_event_payload(
            "source one",
            SimpleNamespace(text="translated one", match_type="exact", show_source=False),
            include_source=False,
        )

        self.assertEqual(payload["text"], "translated one")
        self.assertEqual(payload["matchType"], "exact")
        self.assertFalse(payload["showSource"])
        self.assertFalse(payload["missLogged"])
        self.assertNotIn("rawText", payload)

    def test_clipboard_event_payload_can_include_source_for_diagnostics(self) -> None:
        payload = _clipboard_runtime_event_payload(
            "source one",
            SimpleNamespace(text="", match_type="unmatched", show_source=False),
            include_source=True,
            miss_logged=True,
        )

        self.assertEqual(payload["rawText"], "source one")
        self.assertEqual(payload["matchType"], "unmatched")
        self.assertTrue(payload["missLogged"])

    def test_miss_log_writes_unique_plain_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "misses.txt"

            first = _append_miss_log_line(path, "未翻訳\r\nテキスト")
            duplicate = _append_miss_log_line(path, "未翻訳 テキスト")
            second = _append_miss_log_line(path, "またね")

            self.assertTrue(first)
            self.assertFalse(duplicate)
            self.assertTrue(second)
            self.assertEqual(path.read_text(encoding="utf-8").splitlines(), ["未翻訳 テキスト", "またね"])


class DetachedSubtitleLaunchTests(unittest.TestCase):
    def test_detached_subtitle_process_payload_reports_pid_command_and_logs(self) -> None:
        with TemporaryDirectory() as tmp:
            command = [sys.executable, "-c", "print('subtitle-detached-smoke')"]
            log_dir = Path(tmp) / "logs"

            payload = _start_detached_subtitle_window(command, cwd=Path(tmp), log_dir=log_dir)

            self.assertIsInstance(payload["detachedPid"], int)
            self.assertGreater(payload["detachedPid"], 0)
            self.assertEqual(payload["detachedCommand"], command)
            stdout_path = Path(payload["detachedStdoutPath"])
            stderr_path = Path(payload["detachedStderrPath"])
            self.assertTrue(stdout_path.is_file())
            self.assertTrue(stderr_path.is_file())
            self.assertEqual(stdout_path.parent, log_dir)
            for process in list(_DETACHED_PROCESSES):
                if process.pid == payload["detachedPid"]:
                    process.wait(timeout=5)
                    break
            self.assertFalse(payload["detachedRunning"])
            self.assertEqual(payload["detachedReturnCode"], 0)
            self.assertIn("subtitle-detached-smoke", stdout_path.read_text(encoding="utf-8"))

    def test_detached_subtitle_process_payload_reports_running_process(self) -> None:
        with TemporaryDirectory() as tmp:
            command = [sys.executable, "-c", "import time; time.sleep(2)"]

            payload = _start_detached_subtitle_window(command, cwd=Path(tmp), log_dir=Path(tmp) / "logs")

            self.assertTrue(payload["detachedRunning"])
            self.assertIsNone(payload["detachedReturnCode"])
            for process in list(_DETACHED_PROCESSES):
                if process.pid == payload["detachedPid"]:
                    process.terminate()
                    process.wait(timeout=5)
                    break


if __name__ == "__main__":
    unittest.main()
