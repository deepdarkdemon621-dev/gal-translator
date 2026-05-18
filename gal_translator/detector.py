from __future__ import annotations

from dataclasses import dataclass

from gal_translator.scanner import ScanReport


@dataclass(frozen=True)
class EngineCandidate:
    engine_id: str
    label: str
    confidence: float
    reasons: tuple[str, ...]


class EngineDetector:
    def detect(self, report: ScanReport) -> list[EngineCandidate]:
        candidates = [
            self._kirikiri(report),
            self._renpy(report),
            self._nscripter(report),
            self._direct_script(report),
        ]
        present = [candidate for candidate in candidates if candidate.reasons]
        return sorted(present, key=lambda candidate: candidate.confidence, reverse=True)

    def _kirikiri(self, report: ScanReport) -> EngineCandidate:
        reasons: list[str] = []
        if ".xp3" in report.extensions:
            reasons.append("found .xp3 resource package")
        if ".ks" in report.extensions:
            reasons.append("found .ks KAG script")
        return EngineCandidate(
            engine_id="kirikiri_kag",
            label="Kirikiri/KAG",
            confidence=min(0.95, 0.45 + 0.25 * len(reasons)),
            reasons=tuple(reasons),
        )

    def _renpy(self, report: ScanReport) -> EngineCandidate:
        reasons = [
            f"found {extension} Ren'Py file"
            for extension in (".rpa", ".rpy", ".rpyc")
            if extension in report.extensions
        ]
        return EngineCandidate(
            engine_id="renpy",
            label="Ren'Py",
            confidence=min(0.9, 0.4 + 0.2 * len(reasons)),
            reasons=tuple(reasons),
        )

    def _nscripter(self, report: ScanReport) -> EngineCandidate:
        file_names = {file.relative_path.lower() for file in report.files}
        reasons: list[str] = []
        if "0.txt" in file_names:
            reasons.append("found 0.txt NScripter script")
        if "nscript.dat" in file_names:
            reasons.append("found nscript.dat NScripter archive")
        return EngineCandidate(
            engine_id="nscripter",
            label="NScripter/ONScripter",
            confidence=min(0.85, 0.4 + 0.25 * len(reasons)),
            reasons=tuple(reasons),
        )

    def _direct_script(self, report: ScanReport) -> EngineCandidate:
        reasons: list[str] = []
        direct_extensions = {".ks", ".rpy", ".txt", ".json", ".csv"}
        found_extensions = sorted(set(report.extensions).intersection(direct_extensions))
        if found_extensions:
            reasons.append("found directly readable script files: " + ", ".join(found_extensions))

        root_dirs = {directory.split("/", 1)[0].lower() for directory in report.directories}
        found_dirs = sorted(root_dirs.intersection({"scenario", "script"}))
        if found_dirs:
            reasons.append("found common script directories: " + ", ".join(found_dirs))

        return EngineCandidate(
            engine_id="direct_script",
            label="Direct script import",
            confidence=min(0.8, 0.35 + 0.15 * len(reasons)),
            reasons=tuple(reasons),
        )
