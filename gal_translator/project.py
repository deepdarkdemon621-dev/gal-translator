from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from gal_translator.scanner import GameScanner, ScanReport


@dataclass(frozen=True)
class TranslationProject:
    project_id: str
    project_root: Path
    game_root: Path
    source_lang: str
    target_lang: str
    status: str
    scan_report: ScanReport


class TranslationProjectManager:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def create_project(self, input_path: str | Path) -> TranslationProject:
        report = GameScanner().scan(input_path)
        project_id = self._project_id(report.game_root)
        project_root = self.base_dir / "projects" / project_id
        for child in ("extracted", "scripts", "db", "logs"):
            (project_root / child).mkdir(parents=True, exist_ok=True)

        project = TranslationProject(
            project_id=project_id,
            project_root=project_root,
            game_root=report.game_root,
            source_lang="ja",
            target_lang="zh-Hans",
            status="scanned",
            scan_report=report,
        )
        (project_root / "project.json").write_text(
            json.dumps(_project_payload(project), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (project_root / "scan-report.json").write_text(
            json.dumps(_scan_payload(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return project

    def _project_id(self, game_root: Path) -> str:
        digest = hashlib.sha1(str(game_root.resolve()).encode("utf-8")).hexdigest()[:12]
        return f"{game_root.name}-{digest}"


def _project_payload(project: TranslationProject) -> dict[str, Any]:
    return {
        "projectId": project.project_id,
        "projectRoot": str(project.project_root.resolve()),
        "gameRoot": str(project.game_root.resolve()),
        "sourceLang": project.source_lang,
        "targetLang": project.target_lang,
        "status": project.status,
        "scanReport": "scan-report.json",
    }


def _scan_payload(report: ScanReport) -> dict[str, Any]:
    return {
        "inputPath": str(report.input_path),
        "gameRoot": str(report.game_root),
        "inputWasExe": report.input_was_exe,
        "fileCount": len(report.files),
        "directories": list(report.directories),
        "extensionCounts": {
            extension: len(files) for extension, files in report.files_by_extension.items()
        },
        "archiveDiagnostics": [
            {
                "relativePath": diagnostic.relative_path,
                "formatId": diagnostic.format_id,
                "label": diagnostic.label,
                "magic": diagnostic.magic,
                "size": diagnostic.size,
                "sampledBytes": diagnostic.sampled_bytes,
                "structuredEntryCount": diagnostic.structured_entry_count,
                "visibleExtensionCounts": diagnostic.visible_extension_counts,
                "visibleScriptPaths": list(diagnostic.visible_script_paths),
                "notes": list(diagnostic.notes),
            }
            for diagnostic in report.archive_diagnostics
        ],
        "files": [
            {
                "relativePath": file.relative_path,
                "extension": file.extension,
                "size": file.size,
            }
            for file in report.files
        ],
    }
