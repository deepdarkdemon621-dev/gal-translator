from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from gal_translator.parser import ScriptEntry
from gal_translator.project import TranslationProject

MAX_FAILED_RETRIES = 3


@dataclass(frozen=True)
class TranslationSummary:
    total: int
    pending: int
    translated: int
    failed: int
    status: str
    percent: float


@dataclass(frozen=True)
class FailedRetrySummary:
    reset_count: int
    skipped_count: int
    retry_limit: int
    reset_ids: tuple[str, ...]
    skipped_ids: tuple[str, ...]

    @property
    def next_actions(self) -> list[str]:
        if self.skipped_count == 0:
            return []
        return [
            "Some failed entries already reached the retry limit; review them, but it is usually safe to abandon isolated lines after three failed retries."
        ]

    def to_payload(self) -> dict[str, Any]:
        return {
            "resetCount": self.reset_count,
            "skippedCount": self.skipped_count,
            "retryLimit": self.retry_limit,
            "resetIds": list(self.reset_ids),
            "skippedIds": list(self.skipped_ids),
            "nextActions": self.next_actions,
        }


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
                    "retryCount": 0,
                    "maxRetryReached": False,
                }
                for entry in entries
            ],
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return cls(state_path)

    def append_entries(self, entries: list[ScriptEntry]) -> int:
        state = self._read_state()
        existing_ids = {item["entryId"] for item in state["items"]}
        added = 0
        for entry in entries:
            if entry.id in existing_ids:
                continue
            state["items"].append(
                {
                    "entryId": entry.id,
                    "source": entry.source,
                    "speaker": entry.speaker,
                    "status": "pending",
                    "translation": "",
                    "error": "",
                    "retryCount": 0,
                    "maxRetryReached": False,
                }
            )
            existing_ids.add(entry.id)
            added += 1
        self._write_state(state)
        return added

    def mark_translated(self, entry_id: str, translation: str) -> bool:
        state = self._read_state()
        for item in state["items"]:
            if item["entryId"] == entry_id:
                item["status"] = "translated"
                item["translation"] = translation
                item["error"] = ""
                item["maxRetryReached"] = False
                self._write_state(state)
                return True
        self._write_state(state)
        return False

    def mark_failed(self, entry_id: str, error: str) -> bool:
        state = self._read_state()
        for item in state["items"]:
            if item["entryId"] == entry_id:
                item["status"] = "failed"
                item["error"] = error
                item["maxRetryReached"] = int(item.get("retryCount", 0)) >= MAX_FAILED_RETRIES
                self._write_state(state)
                return True
        self._write_state(state)
        return False

    def entry_ids(self) -> set[str]:
        return {item["entryId"] for item in self._read_state()["items"]}

    def preview_reset_failed(self, max_retries: int = MAX_FAILED_RETRIES) -> FailedRetrySummary:
        state = self._read_state()
        return self._failed_retry_summary(state, max_retries=max_retries, mutate=False)

    def reset_failed(self, max_retries: int = MAX_FAILED_RETRIES) -> int:
        return self.reset_failed_summary(max_retries=max_retries).reset_count

    def reset_failed_summary(self, max_retries: int = MAX_FAILED_RETRIES) -> FailedRetrySummary:
        state = self._read_state()
        summary = self._failed_retry_summary(state, max_retries=max_retries, mutate=True)
        self._write_state(state)
        return summary

    def _failed_retry_summary(
        self,
        state: dict[str, Any],
        max_retries: int,
        mutate: bool,
    ) -> FailedRetrySummary:
        reset_count = 0
        skipped_count = 0
        reset_ids: list[str] = []
        skipped_ids: list[str] = []
        for item in state["items"]:
            if item["status"] == "failed":
                retry_count = int(item.get("retryCount", 0))
                if retry_count >= max_retries:
                    skipped_count += 1
                    skipped_ids.append(item["entryId"])
                    if mutate:
                        item["maxRetryReached"] = True
                    continue
                reset_count += 1
                reset_ids.append(item["entryId"])
                if mutate:
                    item["status"] = "pending"
                    item["error"] = ""
                    item["retryCount"] = retry_count + 1
                    item["maxRetryReached"] = False
        return FailedRetrySummary(
            reset_count=reset_count,
            skipped_count=skipped_count,
            retry_limit=max_retries,
            reset_ids=tuple(reset_ids),
            skipped_ids=tuple(skipped_ids),
        )

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
