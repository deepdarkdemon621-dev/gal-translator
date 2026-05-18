import unittest

from gal_translator.matching import MatchIndex, TranslationRecord
from gal_translator.runtime import RuntimeSubtitleService


class RuntimeDisplayTests(unittest.TestCase):
    def test_runtime_display_returns_translation_only_for_matched_text(self) -> None:
        service = RuntimeSubtitleService(
            MatchIndex(
                [
                    TranslationRecord(
                        entry_id="a.ks:1",
                        source="おはよう、先輩",
                        translation="早上好，前辈。",
                        status="translated",
                    )
                ]
            )
        )

        display = service.display_for("おはよう、先輩")

        self.assertEqual(display.text, "早上好，前辈。")
        self.assertEqual(display.match_type, "exact")
        self.assertFalse(display.show_source)

    def test_runtime_display_hides_source_when_unmatched(self) -> None:
        service = RuntimeSubtitleService(MatchIndex([]))

        display = service.display_for("未翻訳の文")

        self.assertEqual(display.text, "")
        self.assertEqual(display.match_type, "unmatched")
        self.assertFalse(display.show_source)


if __name__ == "__main__":
    unittest.main()
