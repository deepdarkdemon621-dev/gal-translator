from pathlib import Path
from tempfile import TemporaryDirectory
import io
import unittest

from gal_translator.lunahook_bridge import LunaHookBridge, LunaHookBridgeConfig, ThreadParam


class LunaHookBridgeTests(unittest.TestCase):
    def test_bridge_skips_text_already_present_in_source_log(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_log = root / "lunahook-source.txt"
            source_log.write_text("「これが最後の質問だ」\n", encoding="utf-8")
            bridge = LunaHookBridge(
                LunaHookBridgeConfig(
                    luna_root=root,
                    game_pid=1234,
                    source_log=source_log,
                )
            )
            bridge._existing_outputs = bridge._load_existing_outputs()
            output = io.StringIO()
            bridge._output_handle = output
            thread = ThreadParam()

            bridge._on_output("HOOK", b"Artemis", thread, "「これが最後の質問だ」")
            bridge._on_output("HOOK", b"Artemis", thread, "「選べ。認めるか、認めないか」")

            self.assertEqual(output.getvalue(), "「選べ。認めるか、認めないか」\n")
            self.assertEqual(bridge._captured_count, 1)

    def test_bridge_skips_ui_help_text_before_writing_source_log(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_log = root / "lunahook-source.txt"
            bridge = LunaHookBridge(
                LunaHookBridgeConfig(
                    luna_root=root,
                    game_pid=1234,
                    source_log=source_log,
                )
            )
            output = io.StringIO()
            bridge._output_handle = output
            thread = ThreadParam()

            bridge._on_output("HOOK", b"Artemis", thread, "タッチパネル用ＵＩを右に移動します。")
            bridge._on_output("HOOK", b"Artemis", thread, "直前に再生されたボイスを再生します。テキストを自動で読み進めます。")
            bridge._on_output("HOOK", b"Artemis", thread, "「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」")

            self.assertEqual(
                output.getvalue(),
                "「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」\n",
            )
            self.assertEqual(bridge._captured_count, 1)


if __name__ == "__main__":
    unittest.main()
