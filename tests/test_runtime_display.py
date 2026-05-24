import unittest

from gal_translator.matching import MatchIndex, TranslationRecord
from gal_translator.runtime import ReloadableRuntimeSubtitleService, RuntimeSubtitleService


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

    def test_reloadable_runtime_refreshes_match_index_when_signature_changes(self) -> None:
        records: list[TranslationRecord] = []
        signature = {"value": 1}
        service = ReloadableRuntimeSubtitleService(
            load_records=lambda: records,
            current_signature=lambda: signature["value"],
        )

        before = service.display_for("source one")
        records = [
            TranslationRecord(
                entry_id="cap:1",
                source="source one",
                translation="translated one",
                status="translated",
            )
        ]
        signature["value"] = 2
        after = service.display_for("source one")

        self.assertEqual(before.match_type, "unmatched")
        self.assertEqual(after.text, "translated one")
        self.assertEqual(after.match_type, "exact")


if __name__ == "__main__":
    unittest.main()
