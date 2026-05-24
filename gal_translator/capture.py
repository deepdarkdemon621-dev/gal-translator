from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from gal_translator.parser import ScriptEntry


@dataclass(frozen=True)
class CaptureImportResult:
    entries: list[ScriptEntry]
    source_name: str
    raw_line_count: int
    candidate_line_count: int
    duplicate_line_count: int
    non_japanese_line_count: int
    control_line_count: int = 0

    @property
    def imported_entry_count(self) -> int:
        return len(self.entries)

    @property
    def unique_imported_entry_count(self) -> int:
        return len({entry.source for entry in self.entries})

    @property
    def repeated_source_count(self) -> int:
        return self.imported_entry_count - self.unique_imported_entry_count


class ClipboardLogImporter:
    def import_log(
        self,
        log_path: str | Path,
        source_name: str | None = None,
        encoding: str = "utf-8",
    ) -> CaptureImportResult:
        path = Path(log_path)
        text = path.read_text(encoding=encoding)
        raw_line_count = len(text.splitlines())
        lines = _candidate_lines(text)
        entries: list[ScriptEntry] = []
        logical_source = source_name or path.name
        last_source = ""
        duplicate_line_count = 0
        non_japanese_line_count = 0
        control_line_count = 0
        for line_number, line in lines:
            if line == last_source:
                duplicate_line_count += 1
                continue
            last_source = line
            if not _contains_japanese(line):
                non_japanese_line_count += 1
                continue
            if _is_control_or_help_text(line):
                control_line_count += 1
                continue
            entries.append(
                ScriptEntry(
                    id=f"{logical_source}:{line_number}",
                    source=line,
                    speaker=None,
                    file=logical_source,
                    line=line_number,
                    kind="clipboard_capture",
                )
            )
        return CaptureImportResult(
            entries=entries,
            source_name=logical_source,
            raw_line_count=raw_line_count,
            candidate_line_count=len(lines),
            duplicate_line_count=duplicate_line_count,
            non_japanese_line_count=non_japanese_line_count,
            control_line_count=control_line_count,
        )


def _candidate_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.lstrip("\ufeff").strip()
        if not line:
            continue
        line = _strip_textractor_prefix(line)
        if line:
            lines.append((line_number, line))
    return lines


def _strip_textractor_prefix(line: str) -> str:
    prefixed = re.fullmatch(r"(?:\[[^\]]+\]\s*)?(?:[A-Z0-9_]+:)?\s*(?P<text>.+)", line)
    if prefixed is None:
        return line.strip()
    return prefixed.group("text").strip()


def _contains_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))


def _is_control_or_help_text(text: str) -> bool:
    ui_terms = [
        "タッチパネル用ＵＩ",
        "バックログ",
        "テキストをスキップ",
        "テキストを自動で読み進め",
        "クイックセーブ",
        "セーブ画面",
        "ロード画面",
        "コンフィグ画面",
        "テキストウィンドウ",
        "タイトル画面",
        "直前に再生されたボイスを再生",
        "マスター音量",
        "次の選択肢",
        "前の選択肢",
    ]
    return any(term in text for term in ui_terms)
