from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil

from gal_translator.profiles import ExtractorProfile
from gal_translator.project import TranslationProject
from gal_translator.parser import ScriptEntry


@dataclass(frozen=True)
class ImportedScript:
    source_path: Path
    project_path: Path
    relative_path: str


class DirectScriptImporter:
    def import_scripts(
        self,
        project: TranslationProject,
        profile: ExtractorProfile,
    ) -> list[ImportedScript]:
        imported: list[ImportedScript] = []
        scripts_root = project.project_root / "scripts"
        seen: set[Path] = set()

        for pattern in profile.script_globs:
            for source_path in sorted(project.game_root.glob(pattern)):
                if not source_path.is_file() or source_path in seen:
                    continue
                seen.add(source_path)
                relative_path = source_path.relative_to(project.game_root)
                project_path = scripts_root / relative_path
                project_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, project_path)
                imported.append(
                    ImportedScript(
                        source_path=source_path,
                        project_path=project_path,
                        relative_path=relative_path.as_posix(),
                    )
                )

        return imported


class ArtemisAstImporter:
    def import_scripts(self, project: TranslationProject) -> list[ImportedScript]:
        imported: list[ImportedScript] = []
        scripts_root = project.project_root / "scripts"
        seen: set[Path] = set()

        for source_path in sorted(project.game_root.glob("**/*.ast")):
            if not source_path.is_file() or source_path in seen:
                continue
            seen.add(source_path)
            relative_path = source_path.relative_to(project.game_root)
            project_path = scripts_root / relative_path
            project_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, project_path)
            imported.append(
                ImportedScript(
                    source_path=source_path,
                    project_path=project_path,
                    relative_path=relative_path.as_posix(),
                )
            )

        return imported


class ArtemisAstParser:
    def parse(self, path: str | Path, relative_path: str) -> list[ScriptEntry]:
        script_path = Path(path)
        entries: list[ScriptEntry] = []
        reserved_ids: set[str] = set()
        in_ja_block = False
        ja_depth = 0
        in_entry = False
        entry_depth = 0
        speaker: str | None = None
        segments: list[str] = []
        first_text_line = 0

        for line_number, raw_line in enumerate(
            script_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            stripped = raw_line.strip()

            if not in_ja_block:
                if re.fullmatch(r"ja\s*=\s*\{", stripped):
                    in_ja_block = True
                    ja_depth = _brace_delta(stripped)
                continue

            if not in_entry and ja_depth == 1 and stripped == "{":
                in_entry = True
                entry_depth = _brace_delta(stripped)
                speaker = None
                segments = []
                first_text_line = 0
                ja_depth += _brace_delta(stripped)
                continue

            if in_entry:
                if stripped.startswith("name"):
                    speaker = _speaker_from_name_line(stripped)
                elif _is_standalone_string_line(stripped):
                    strings = _lua_strings(stripped)
                    if strings:
                        if first_text_line == 0:
                            first_text_line = line_number
                        segments.extend(strings)

                delta = _brace_delta(stripped)
                entry_depth += delta
                ja_depth += delta
                if entry_depth <= 0:
                    source = "".join(segment.strip() for segment in segments if segment.strip())
                    if source:
                        entry_line = first_text_line or line_number
                        entry_id = _unique_entry_id(f"{relative_path}:{entry_line}", reserved_ids)
                        entries.append(
                            ScriptEntry(
                                id=entry_id,
                                source=source,
                                speaker=speaker,
                                file=relative_path,
                                line=entry_line,
                                kind="artemis_ast_text",
                            )
                        )
                    in_entry = False
                if ja_depth <= 0:
                    in_ja_block = False
                continue

            ja_depth += _brace_delta(stripped)
            if ja_depth <= 0:
                in_ja_block = False

        return entries


def _speaker_from_name_line(line: str) -> str | None:
    names = [name.strip() for name in _lua_strings(line) if name.strip()]
    if not names:
        return None
    return names[-1]


def _is_standalone_string_line(line: str) -> bool:
    if not line.startswith('"'):
        return False
    return bool(re.fullmatch(r'"(?:\\.|[^"\\])*"\s*,?', line))


def _lua_strings(line: str) -> list[str]:
    return [_unescape_lua_string(match.group(1)) for match in re.finditer(r'"((?:\\.|[^"\\])*)"', line)]


def _unescape_lua_string(value: str) -> str:
    return (
        value.replace(r"\"", '"')
        .replace(r"\\", "\\")
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
    )


def _brace_delta(line: str) -> int:
    without_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    return without_strings.count("{") - without_strings.count("}")


def _unique_entry_id(base_id: str, reserved_ids: set[str]) -> str:
    if base_id not in reserved_ids:
        reserved_ids.add(base_id)
        return base_id
    counter = 2
    while f"{base_id}#{counter}" in reserved_ids:
        counter += 1
    entry_id = f"{base_id}#{counter}"
    reserved_ids.add(entry_id)
    return entry_id
