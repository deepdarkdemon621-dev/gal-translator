from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from gal_translator.clipboard import ClipboardRuntimeInput, ClipboardTextRecorder, TextLogRuntimeInput, WindowsClipboardProvider


class FakeClipboard:
    def __init__(self, values: list[str]) -> None:
        self.values = values
        self.index = 0

    def read_text(self) -> str:
        value = self.values[self.index]
        if self.index < len(self.values) - 1:
            self.index += 1
        return value


class ClipboardInputTests(unittest.TestCase):
    def test_poll_once_returns_changed_non_empty_text(self) -> None:
        clipboard = FakeClipboard(["おはよう", "行こう"])
        runtime = ClipboardRuntimeInput(clipboard)

        first = runtime.poll_once()
        second = runtime.poll_once()

        self.assertEqual(first.raw_text, "おはよう")
        self.assertEqual(second.raw_text, "行こう")

    def test_poll_once_ignores_repeated_and_empty_text(self) -> None:
        clipboard = FakeClipboard(["", "おはよう", "おはよう"])
        runtime = ClipboardRuntimeInput(clipboard)

        self.assertIsNone(runtime.poll_once())
        self.assertEqual(runtime.poll_once().raw_text, "おはよう")
        self.assertIsNone(runtime.poll_once())

    def test_recorder_writes_changed_clipboard_text_to_log(self) -> None:
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "clipboard.txt"
            clipboard = FakeClipboard(["", "source one", "source one", "source two"])
            recorder = ClipboardTextRecorder(clipboard)

            summary = recorder.record(log_path, max_events=2, max_polls=4, append=False)

            self.assertEqual(summary.captured_count, 2)
            self.assertEqual(summary.poll_count, 4)
            self.assertFalse(summary.append)
            self.assertEqual(log_path.read_text(encoding="utf-8").splitlines(), ["source one", "source two"])

    def test_recorder_can_append_to_existing_log(self) -> None:
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "clipboard.txt"
            log_path.write_text("existing\n", encoding="utf-8")
            recorder = ClipboardTextRecorder(FakeClipboard(["added"]))

            summary = recorder.record_once(log_path, append=True)

            self.assertEqual(summary.captured_count, 1)
            self.assertTrue(summary.append)
            self.assertEqual(log_path.read_text(encoding="utf-8").splitlines(), ["existing", "added"])

    @unittest.skipUnless(sys.platform == "win32", "Windows clipboard provider is Windows-only")
    def test_windows_clipboard_provider_reads_text_without_handle_overflow(self) -> None:
        provider = WindowsClipboardProvider()

        text = provider.read_text()

        self.assertIsInstance(text, str)


class TextLogRuntimeInputTests(unittest.TestCase):
    def test_source_log_input_tails_clean_imported_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "textractor.txt"
            log_path.write_text("WINDOW: config\nHOOK: \u304a\u306f\u3088\u3046\n", encoding="utf-8")
            runtime = TextLogRuntimeInput(log_path, source_name="textractor")

            self.assertIsNone(runtime.poll_once())
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write("HOOK: \u304a\u306f\u3088\u3046\n")
                handle.write("HOOK: \u3055\u3088\u3046\u306a\u3089\n")

            self.assertEqual(runtime.poll_once().raw_text, "\u3055\u3088\u3046\u306a\u3089")
            self.assertIsNone(runtime.poll_once())

    def test_source_log_input_can_replay_existing_lines_from_start(self) -> None:
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "textractor.txt"
            log_path.write_text("HOOK: \u304a\u306f\u3088\u3046\nHOOK: \u3055\u3088\u3046\u306a\u3089\n", encoding="utf-8")
            runtime = TextLogRuntimeInput(log_path, source_name="textractor", from_start=True)

            self.assertEqual(runtime.poll_once().raw_text, "\u304a\u306f\u3088\u3046")
            self.assertEqual(runtime.poll_once().raw_text, "\u3055\u3088\u3046\u306a\u3089")
            self.assertIsNone(runtime.poll_once())


if __name__ == "__main__":
    unittest.main()
