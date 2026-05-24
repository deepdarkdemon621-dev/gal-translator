from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from gal_translator.progress import TranslationProgressTracker


@dataclass(frozen=True)
class TranslationBatchItem:
    entry_id: str
    source: str
    speaker: str | None


@dataclass(frozen=True)
class TranslationApplySummary:
    applied_ids: tuple[str, ...]
    failed_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]
    duplicate_ids: tuple[str, ...]
    empty_ids: tuple[str, ...]
    invalid_item_count: int

    @property
    def applied_count(self) -> int:
        return len(self.applied_ids)

    @property
    def failed_count(self) -> int:
        return len(self.failed_ids)

    @property
    def missing_count(self) -> int:
        return len(self.missing_ids)

    @property
    def unknown_count(self) -> int:
        return len(self.unknown_ids)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_ids)

    @property
    def empty_count(self) -> int:
        return len(self.empty_ids)

    def to_payload(self) -> dict[str, Any]:
        return {
            "appliedCount": self.applied_count,
            "failedCount": self.failed_count,
            "missingCount": self.missing_count,
            "unknownCount": self.unknown_count,
            "duplicateCount": self.duplicate_count,
            "emptyCount": self.empty_count,
            "invalidItemCount": self.invalid_item_count,
            "appliedIds": list(self.applied_ids),
            "failedIds": list(self.failed_ids),
            "missingIds": list(self.missing_ids),
            "unknownIds": list(self.unknown_ids),
            "duplicateIds": list(self.duplicate_ids),
            "emptyIds": list(self.empty_ids),
        }


class CodexBatchTranslator:
    def __init__(self, state_path: str | Path) -> None:
        self.state_path = Path(state_path)
        self.tracker = TranslationProgressTracker(self.state_path)

    def next_batch(
        self,
        batch_size: int,
        allowed_entry_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[TranslationBatchItem]:
        state = self._read_state()
        pending = [item for item in state["items"] if item["status"] == "pending"]
        if allowed_entry_ids is not None:
            allowed = set(allowed_entry_ids)
            pending = [item for item in pending if item["entryId"] in allowed]
        return [
            TranslationBatchItem(
                entry_id=item["entryId"],
                source=item["source"],
                speaker=item["speaker"],
            )
            for item in pending[:batch_size]
        ]

    def build_prompt(self, batch: list[TranslationBatchItem]) -> str:
        payload = {
            "items": [
                {
                    "id": item.entry_id,
                    "speaker": item.speaker,
                    "source": item.source,
                }
                for item in batch
            ]
        }
        return "\n".join(
            [
                "Translate the following Galgame story lines from Japanese to Simplified Chinese.",
                "preserve the original Galgame style, tone, character voice, honorific nuance, and line intensity.",
                "Return Chinese translations only; do not include Japanese source text in translation fields.",
                "Return strict JSON matching this shape: {\"items\":[{\"id\":\"...\",\"translation\":\"...\",\"notes\":\"optional\"}]}",
                json.dumps(payload, ensure_ascii=False, indent=2),
            ]
        )

    def apply_result(
        self,
        result: dict[str, Any],
        expected_ids: list[str] | tuple[str, ...] | None = None,
    ) -> TranslationApplySummary:
        known_ids = self.tracker.entry_ids()
        expected_set = set(expected_ids or [])
        result_items = result.get("items", [])
        if not isinstance(result_items, list):
            return TranslationApplySummary((), (), (), (), (), (), 1)

        seen_ids: set[str] = set()
        applied_ids: list[str] = []
        failed_ids: list[str] = []
        unknown_ids: list[str] = []
        duplicate_ids: list[str] = []
        empty_ids: list[str] = []
        invalid_item_count = 0

        for item in result_items:
            if not isinstance(item, dict):
                invalid_item_count += 1
                continue
            entry_id = item.get("id")
            translation = item.get("translation")
            if not isinstance(entry_id, str) or not entry_id:
                invalid_item_count += 1
                continue
            if entry_id in seen_ids:
                duplicate_ids.append(entry_id)
                continue
            seen_ids.add(entry_id)
            if entry_id not in known_ids:
                unknown_ids.append(entry_id)
                continue
            if not isinstance(translation, str) or not translation.strip():
                empty_ids.append(entry_id)
                if self.tracker.mark_failed(entry_id, "Codex output had empty translation"):
                    failed_ids.append(entry_id)
                continue
            if self.tracker.mark_translated(entry_id, translation.strip()):
                applied_ids.append(entry_id)

        missing_ids = sorted(expected_set - seen_ids)
        for entry_id in missing_ids:
            if entry_id in known_ids and self.tracker.mark_failed(entry_id, "Codex output missing id"):
                failed_ids.append(entry_id)

        return TranslationApplySummary(
            applied_ids=tuple(applied_ids),
            failed_ids=tuple(failed_ids),
            missing_ids=tuple(missing_ids),
            unknown_ids=tuple(unknown_ids),
            duplicate_ids=tuple(duplicate_ids),
            empty_ids=tuple(empty_ids),
            invalid_item_count=invalid_item_count,
        )

    def _read_state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class CodexCliInvocation:
    model: str

    def command(self, prompt_path: Path, schema_path: Path, output_path: Path) -> list[str]:
        return [
            "codex",
            "exec",
            "--ephemeral",
            "-m",
            self.model,
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ]

    def write_output_schema(self, schema_path: Path) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "translation", "notes"],
                        "properties": {
                            "id": {"type": "string"},
                            "translation": {"type": "string"},
                            "notes": {"type": ["string", "null"]},
                        },
                    },
                }
            },
        }
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
