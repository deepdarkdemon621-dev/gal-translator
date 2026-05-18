import unittest

from gal_translator.matching import MatchIndex, TranslationRecord


class MatchIndexTests(unittest.TestCase):
    def test_exact_match_returns_chinese_translation_only(self) -> None:
        index = MatchIndex(
            [
                TranslationRecord(
                    entry_id="scenario/opening.ks:2",
                    source="おはよう、先輩",
                    translation="早上好，前辈。",
                    status="translated",
                )
            ]
        )

        result = index.lookup("おはよう、先輩")

        self.assertEqual(result.translation, "早上好，前辈。")
        self.assertEqual(result.match_type, "exact")
        self.assertEqual(result.entry_id, "scenario/opening.ks:2")

    def test_normalized_match_handles_whitespace_and_repeated_clipboard_text(self) -> None:
        index = MatchIndex(
            [
                TranslationRecord(
                    entry_id="scenario/opening.ks:5",
                    source="……また会えたね。",
                    translation="……又见面了呢。",
                    status="translated",
                )
            ]
        )

        result = index.lookup(" ……また会えたね。\r\n……また会えたね。 ")

        self.assertEqual(result.translation, "……又见面了呢。")
        self.assertEqual(result.match_type, "normalized")

    def test_untranslated_record_is_not_returned_as_match(self) -> None:
        index = MatchIndex(
            [
                TranslationRecord(
                    entry_id="scenario/opening.ks:7",
                    source="行こう、先輩",
                    translation="",
                    status="pending",
                )
            ]
        )

        result = index.lookup("行こう、先輩")

        self.assertIsNone(result.translation)
        self.assertEqual(result.match_type, "unmatched")


if __name__ == "__main__":
    unittest.main()
