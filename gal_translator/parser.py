from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ScriptEntry:
    id: str
    source: str
    speaker: str | None
    file: str
    line: int
    kind: str


class ScriptParser:
    def parse(self, path: str | Path, relative_path: str) -> list[ScriptEntry]:
        script_path = Path(path)
        entries: list[ScriptEntry] = []
        skipped_block_indent: int | None = None
        for line_number, raw_line in enumerate(
            script_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            stripped = raw_line.strip()
            if skipped_block_indent is not None:
                if stripped and indent > skipped_block_indent:
                    continue
                skipped_block_indent = None
            if _starts_skipped_block(stripped):
                skipped_block_indent = indent
                continue

            parsed = _parse_line(raw_line)
            if parsed is None:
                continue
            speaker, source = parsed
            entries.append(
                ScriptEntry(
                    id=f"{relative_path}:{line_number}",
                    source=source,
                    speaker=speaker,
                    file=relative_path,
                    line=line_number,
                    kind="candidate_dialogue",
                )
            )
        return entries


def _parse_line(raw_line: str) -> tuple[str | None, str] | None:
    line = raw_line.strip()
    if not line:
        return None
    if line.startswith(("[", "@", ";", "#", "label ", "define ", "screen ")):
        return None
    if _starts_skipped_block(line):
        return None

    kag_match = re.fullmatch(r"(?P<speaker>[^「」]{1,32})「(?P<text>.+)」", line)
    if kag_match:
        return kag_match.group("speaker").strip(), kag_match.group("text").strip()

    renpy_match = re.fullmatch(r"(?P<speaker>[A-Za-z_][A-Za-z0-9_]*)\s+\"(?P<text>.+)\"", line)
    if renpy_match:
        return renpy_match.group("speaker"), renpy_match.group("text").strip()

    quoted_match = re.fullmatch(r"\"(?P<text>.+)\"", line)
    if quoted_match:
        return None, quoted_match.group("text").strip()

    if _looks_like_command(line):
        return None

    return None, line


def _looks_like_command(line: str) -> bool:
    command_prefixes = ("if ", "elif ", "else", "return", "jump ", "call ", "$")
    return line.startswith(command_prefixes)


def _starts_skipped_block(line: str) -> bool:
    return line.endswith(":") and line.split(" ", 1)[0] in {"menu", "screen", "label", "translate"}
