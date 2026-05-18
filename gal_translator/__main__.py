from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from gal_translator.detector import EngineDetector, EngineCandidate
from gal_translator.importer import DirectScriptImporter, ImportedScript
from gal_translator.matching import MatchIndex, TranslationRecord
from gal_translator.parser import ScriptEntry, ScriptParser
from gal_translator.profiles import ExtractorProfile, ExtractorProfileRegistry
from gal_translator.progress import TranslationProgressTracker, TranslationSummary
from gal_translator.project import TranslationProject, TranslationProjectManager
from gal_translator.runtime import RuntimeSubtitleService
from gal_translator.scanner import GameScanner, ScanReport, ScannedFile
from gal_translator.story_filter import StoryTextFilter
from gal_translator.translator import CodexBatchTranslator


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="gal-translator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan a Galgame exe or game directory")
    scan_parser.add_argument("path", help="path to game exe or game directory")

    init_parser = subparsers.add_parser("init", help="create a local translation project")
    init_parser.add_argument("path", help="path to game exe or game directory")
    init_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )

    import_parser = subparsers.add_parser("import", help="import direct scripts into a project")
    import_parser.add_argument("path", help="path to game exe or game directory")
    import_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )

    progress_parser = subparsers.add_parser("progress", help="show translation progress")
    progress_parser.add_argument("project_root", help="path to an existing translation project")

    batch_parser = subparsers.add_parser("batch", help="print the next translation batch prompt")
    batch_parser.add_argument("project_root", help="path to an existing translation project")
    batch_parser.add_argument("--size", type=int, default=40, help="maximum items in the batch")

    apply_parser = subparsers.add_parser("apply-result", help="apply a Codex result JSON file")
    apply_parser.add_argument("project_root", help="path to an existing translation project")
    apply_parser.add_argument("result_json", help="path to Codex output JSON")

    lookup_parser = subparsers.add_parser("lookup", help="look up translated display text")
    lookup_parser.add_argument("project_root", help="path to an existing translation project")
    lookup_parser.add_argument("text", help="current Japanese text from clipboard or hook")

    args = parser.parse_args()
    if args.command == "scan":
        report = GameScanner().scan(Path(args.path))
        candidates = EngineDetector().detect(report)
        print(json.dumps(_scan_payload(report, candidates), ensure_ascii=False, indent=2))
        return 0
    if args.command == "init":
        project = TranslationProjectManager(Path(args.workspace)).create_project(Path(args.path))
        profiles = ExtractorProfileRegistry.default().match(project.scan_report)
        print(json.dumps(_project_payload(project, profiles), ensure_ascii=False, indent=2))
        return 0
    if args.command == "import":
        project = TranslationProjectManager(Path(args.workspace)).create_project(Path(args.path))
        profiles = ExtractorProfileRegistry.default().match(project.scan_report)
        if not profiles:
            print(json.dumps(_import_payload(project, [], []), ensure_ascii=False, indent=2))
            return 0
        imported = DirectScriptImporter().import_scripts(project, profiles[0])
        entries = _parse_story_entries(imported)
        entries_path = project.project_root / "story-entries.json"
        entries_path.write_text(
            json.dumps([_entry_payload(entry) for entry in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tracker = TranslationProgressTracker.initialize(project, entries)
        print(json.dumps(_import_payload(project, imported, entries, tracker), ensure_ascii=False, indent=2))
        return 0
    if args.command == "progress":
        tracker = TranslationProgressTracker(Path(args.project_root) / "translation-state.json")
        print(json.dumps(_summary_payload(tracker.summary()), ensure_ascii=False, indent=2))
        return 0
    if args.command == "batch":
        translator = CodexBatchTranslator(Path(args.project_root) / "translation-state.json")
        print(translator.build_prompt(translator.next_batch(args.size)))
        return 0
    if args.command == "apply-result":
        translator = CodexBatchTranslator(Path(args.project_root) / "translation-state.json")
        result = json.loads(Path(args.result_json).read_text(encoding="utf-8"))
        translator.apply_result(result)
        print(json.dumps(_summary_payload(translator.tracker.summary()), ensure_ascii=False, indent=2))
        return 0
    if args.command == "lookup":
        state_path = Path(args.project_root) / "translation-state.json"
        records = _translation_records_from_state(state_path)
        display = RuntimeSubtitleService(MatchIndex(records)).display_for(args.text)
        print(
            json.dumps(
                {
                    "text": display.text,
                    "matchType": display.match_type,
                    "showSource": display.show_source,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _scan_payload(report: ScanReport, candidates: list[EngineCandidate]) -> dict[str, Any]:
    return {
        "inputPath": str(report.input_path),
        "gameRoot": str(report.game_root),
        "inputWasExe": report.input_was_exe,
        "fileCount": len(report.files),
        "directories": list(report.directories),
        "extensionCounts": {
            extension: len(files) for extension, files in report.files_by_extension.items()
        },
        "engineCandidates": [_candidate_payload(candidate) for candidate in candidates],
        "files": [_file_payload(file) for file in report.files],
    }


def _candidate_payload(candidate: EngineCandidate) -> dict[str, Any]:
    return {
        "engineId": candidate.engine_id,
        "label": candidate.label,
        "confidence": candidate.confidence,
        "reasons": list(candidate.reasons),
    }


def _file_payload(file: ScannedFile) -> dict[str, Any]:
    return {
        "relativePath": file.relative_path,
        "extension": file.extension,
        "size": file.size,
    }


def _project_payload(
    project: TranslationProject,
    matched_profiles: list[ExtractorProfile],
) -> dict[str, Any]:
    return {
        "projectId": project.project_id,
        "projectRoot": str(project.project_root),
        "gameRoot": str(project.game_root),
        "sourceLang": project.source_lang,
        "targetLang": project.target_lang,
        "status": project.status,
        "matchedProfiles": [_profile_payload(profile) for profile in matched_profiles],
    }


def _profile_payload(profile: ExtractorProfile) -> dict[str, Any]:
    return {
        "profileId": profile.profile_id,
        "label": profile.label,
        "sourceLang": profile.source_lang,
        "targetLang": profile.target_lang,
        "scriptGlobs": list(profile.script_globs),
        "encoding": profile.encoding,
    }


def _parse_story_entries(imported_scripts: list[ImportedScript]) -> list[ScriptEntry]:
    parser = ScriptParser()
    parsed_entries: list[ScriptEntry] = []
    for script in imported_scripts:
        parsed_entries.extend(parser.parse(script.project_path, script.relative_path))
    return StoryTextFilter().keep_story_entries(parsed_entries)


def _import_payload(
    project: TranslationProject,
    imported_scripts: list[ImportedScript],
    story_entries: list[ScriptEntry],
    tracker: TranslationProgressTracker | None = None,
) -> dict[str, Any]:
    summary = tracker.summary() if tracker is not None else None
    return {
        "projectId": project.project_id,
        "projectRoot": str(project.project_root),
        "sourceLang": project.source_lang,
        "targetLang": project.target_lang,
        "importedScriptCount": len(imported_scripts),
        "storyEntryCount": len(story_entries),
        "storyEntriesPath": str(project.project_root / "story-entries.json"),
        "translationStatePath": str(project.project_root / "translation-state.json"),
        "progress": _summary_payload(summary) if summary is not None else None,
    }


def _entry_payload(entry: ScriptEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "source": entry.source,
        "speaker": entry.speaker,
        "file": entry.file,
        "line": entry.line,
        "kind": entry.kind,
    }


def _summary_payload(summary: TranslationSummary) -> dict[str, Any]:
    return {
        "total": summary.total,
        "pending": summary.pending,
        "translated": summary.translated,
        "failed": summary.failed,
        "status": summary.status,
        "percent": summary.percent,
    }


def _translation_records_from_state(state_path: Path) -> list[TranslationRecord]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return [
        TranslationRecord(
            entry_id=item["entryId"],
            source=item["source"],
            translation=item["translation"],
            status=item["status"],
        )
        for item in state["items"]
    ]


if __name__ == "__main__":
    raise SystemExit(main())
