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


class CodexBatchTranslator:
    def __init__(self, state_path: str | Path) -> None:
        self.state_path = Path(state_path)
        self.tracker = TranslationProgressTracker(self.state_path)

    def next_batch(self, batch_size: int) -> list[TranslationBatchItem]:
        state = self._read_state()
        pending = [item for item in state["items"] if item["status"] == "pending"]
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

    def apply_result(self, result: dict[str, Any]) -> None:
        for item in result.get("items", []):
            entry_id = item.get("id")
            translation = item.get("translation")
            if isinstance(entry_id, str) and isinstance(translation, str) and translation:
                self.tracker.mark_translated(entry_id, translation)

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
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "translation"],
                        "properties": {
                            "id": {"type": "string"},
                            "translation": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                    },
                }
            },
        }
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
