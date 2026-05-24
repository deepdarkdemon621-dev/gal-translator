from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gal_translator.capture import ClipboardLogImporter


class CaptureImportTests(unittest.TestCase):
    def test_import_log_keeps_japanese_lines_and_skips_duplicates(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "textractor.txt"
            log_path.write_text(
                "\n".join(
                    [
                        "\ufeff[hook] おはよう、先輩。",
                        "[hook] おはよう、先輩。",
                        "WINDOW: Config",
                        "……また会えた。",
                    ]
                ),
                encoding="utf-8",
            )

            result = ClipboardLogImporter().import_log(log_path, source_name="textractor")

        self.assertEqual([entry.source for entry in result.entries], ["おはよう、先輩。", "……また会えた。"])
        self.assertEqual([entry.id for entry in result.entries], ["textractor:1", "textractor:4"])
        self.assertEqual(result.entries[0].kind, "clipboard_capture")
        self.assertEqual(result.raw_line_count, 4)
        self.assertEqual(result.candidate_line_count, 4)
        self.assertEqual(result.duplicate_line_count, 1)
        self.assertEqual(result.non_japanese_line_count, 1)
        self.assertEqual(result.control_line_count, 0)
        self.assertEqual(result.imported_entry_count, 2)
        self.assertEqual(result.unique_imported_entry_count, 2)
        self.assertEqual(result.repeated_source_count, 0)

    def test_import_log_skips_ui_help_text(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "lunahook.txt"
            log_path.write_text(
                "\n".join(
                    [
                        "「選べ。認めるか、認めないか」",
                        "タッチパネル用ＵＩを左に移動します。バックログを開きます。テキストをスキップします。クイックセーブします。セーブ画面を開きます。ロード画面を開きます。コンフィグ画面を開きます。テキストウィンドウを隠します。タイトル画面に戻ります。",
                    ]
                ),
                encoding="utf-8",
            )

            result = ClipboardLogImporter().import_log(log_path, source_name="lunahook")

        self.assertEqual([entry.source for entry in result.entries], ["「選べ。認めるか、認めないか」"])
        self.assertEqual(result.raw_line_count, 2)
        self.assertEqual(result.candidate_line_count, 2)
        self.assertEqual(result.control_line_count, 1)
        self.assertEqual(result.imported_entry_count, 1)

    def test_import_log_skips_short_ui_help_text(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "lunahook.txt"
            log_path.write_text(
                "\n".join(
                    [
                        "タッチパネル用ＵＩを右に移動します。",
                        "直前に再生されたボイスを再生します。テキストを自動で読み進めます。",
                        "「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」",
                    ]
                ),
                encoding="utf-8",
            )

            result = ClipboardLogImporter().import_log(log_path, source_name="lunahook")

        self.assertEqual(
            [entry.source for entry in result.entries],
            ["「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」"],
        )
        self.assertEqual(result.control_line_count, 2)
        self.assertEqual(result.imported_entry_count, 1)

    def test_import_log_reports_repeated_non_consecutive_sources(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "textractor.txt"
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

            result = ClipboardLogImporter().import_log(log_path, source_name="textractor")

        self.assertEqual(result.imported_entry_count, 3)
        self.assertEqual(result.unique_imported_entry_count, 2)
        self.assertEqual(result.repeated_source_count, 1)


if __name__ == "__main__":
    unittest.main()
