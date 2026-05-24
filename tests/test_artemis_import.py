import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from gal_translator.importer import ArtemisAstParser


ARTEMIS_FIXTURE = """astver = 2.0
astname = "ast"
ast = {
\tblock_00000 = {
\t\t{"text"},
\t\ttext = {
\t\t\tja = {
\t\t\t\t{
\t\t\t\t\tname = {"internal_kan", "花"},
\t\t\t\t\t"「その通りです。",
\t\t\t\t\t{"rt2"},
\t\t\t\t\t"今日は学生寮に入る流れになっています」",
\t\t\t\t\t{"rt2"},
\t\t\t\t},
\t\t\t},
\t\t},
\t\tline = 7,
\t},
\tblock_00001 = {
\t\t{"text"},
\t\ttext = {
\t\t\tja = {
\t\t\t\t{
\t\t\t\t\t"私は",
\t\t\t\t\t{"txruby", text="かなえ"},
\t\t\t\t\t"叶",
\t\t\t\t\t{"txruby"},
\t\t\t\t\t"様を守る必要があります。",
\t\t\t\t\t{"rt2"},
\t\t\t\t},
\t\t\t},
\t\t},
\t\tline = 18,
\t},
}
"""


class ArtemisImportTests(unittest.TestCase):
    def test_parser_reads_text_ja_blocks_and_merges_message_strings(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            ast_path = root / "script" / "scene.ast"
            ast_path.parent.mkdir()
            ast_path.write_text(ARTEMIS_FIXTURE, encoding="utf-8")

            entries = ArtemisAstParser().parse(ast_path, "script/scene.ast")

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].speaker, "花")
        self.assertEqual(entries[0].source, "「その通りです。今日は学生寮に入る流れになっています」")
        self.assertEqual(entries[0].kind, "artemis_ast_text")
        self.assertEqual(entries[0].file, "script/scene.ast")
        self.assertEqual(entries[0].line, 10)
        self.assertEqual(entries[0].id, "script/scene.ast:10")
        self.assertIsNone(entries[1].speaker)
        self.assertEqual(entries[1].source, "私は叶様を守る必要があります。")

    def test_import_command_uses_artemis_ast_importer_for_exported_scripts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_root = root / "Extracted"
            ast_path = export_root / "script" / "scene.ast"
            ast_path.parent.mkdir(parents=True)
            ast_path.write_text(ARTEMIS_FIXTURE, encoding="utf-8")
            workspace = root / "Workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gal_translator",
                    "import",
                    str(export_root),
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
            self.assertEqual(payload["importType"], "artemis_ast")
            self.assertEqual(payload["importedScriptCount"], 1)
            self.assertEqual(payload["storyEntryCount"], 2)
            self.assertEqual(payload["progress"]["pending"], 2)
            self.assertTrue((Path(payload["projectRoot"]) / "scripts" / "script" / "scene.ast").is_file())
            entries = json.loads(Path(payload["storyEntriesPath"]).read_text(encoding="utf-8"))
            self.assertEqual(entries[0]["speaker"], "花")
            self.assertEqual(entries[1]["source"], "私は叶様を守る必要があります。")

    def test_real_selectoblige_sample_smoke_when_available(self) -> None:
        sample = Path(
            r"C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige"
            r"\pfs-rs-extract-selectoblige-pfs-v0.2.5\script\01_01プロローグ_01.ast"
        )
        if not sample.is_file():
            self.skipTest("real selectoblige Artemis export is not available")

        entries = ArtemisAstParser().parse(sample, "script/01_01プロローグ_01.ast")

        self.assertGreaterEqual(len(entries), 20)
        self.assertEqual(entries[0].source, "「これが最後の質問だ」")
        self.assertEqual(entries[0].speaker, "？？？")
        self.assertEqual(entries[0].id, "script/01_01プロローグ_01.ast:16")


if __name__ == "__main__":
    unittest.main()
