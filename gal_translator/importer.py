from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from gal_translator.profiles import ExtractorProfile
from gal_translator.project import TranslationProject


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
