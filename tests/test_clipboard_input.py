import unittest

from gal_translator.clipboard import ClipboardRuntimeInput


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


if __name__ == "__main__":
    unittest.main()
