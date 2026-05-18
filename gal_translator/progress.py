from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from gal_translator.parser import ScriptEntry
from gal_translator.project import TranslationProject


@dataclass(frozen=True)
class TranslationSummary:
    total: int
    pending: int
    translated: int
    failed: int
    status: str
    percent: float


class TranslationProgressTracker:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    @classmethod
    def initialize(
        cls,
        project: TranslationProject,
        entries: list[ScriptEntry],
    ) -> TranslationProgressTracker:
        state_path = project.project_root / "translation-state.json"
        state = {
            "sourceLang": project.source_lang,
            "targetLang": project.target_lang,
            "items": [
                {
                    "entryId": entry.id,
                    "source": entry.source,
                    "speaker": entry.speaker,
                    "status": "pending",
                    "translation": "",
                    "error": "",
                }
                for entry in entries
            ],
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return cls(state_path)

    def mark_translated(self, entry_id: str, translation: str) -> None:
        state = self._read_state()
        for item in state["items"]:
            if item["entryId"] == entry_id:
                item["status"] = "translated"
                item["translation"] = translation
                item["error"] = ""
                break
        self._write_state(state)

    def mark_failed(self, entry_id: str, error: str) -> None:
        state = self._read_state()
        for item in state["items"]:
            if item["entryId"] == entry_id:
                item["status"] = "failed"
                item["error"] = error
                break
        self._write_state(state)

    def summary(self) -> TranslationSummary:
        items = self._read_state()["items"]
        total = len(items)
        translated = sum(1 for item in items if item["status"] == "translated")
        failed = sum(1 for item in items if item["status"] == "failed")
        pending = total - translated - failed
        if total == 0:
            percent = 0.0
        else:
            percent = round((translated / total) * 100, 2)
        return TranslationSummary(
            total=total,
            pending=pending,
            translated=translated,
            failed=failed,
            status=_status(total, pending, translated, failed),
            percent=percent,
        )

    def _read_state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _status(total: int, pending: int, translated: int, failed: int) -> str:
    if total == 0:
        return "empty"
    if translated == total:
        return "ready"
    if translated > 0 or failed > 0:
        return "partial"
    if pending == total:
        return "pending"
    return "partial"
