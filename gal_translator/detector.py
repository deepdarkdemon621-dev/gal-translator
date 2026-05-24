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
            self._pf8_pfs(report),
            self._kirikiri(report),
            self._renpy(report),
            self._nscripter(report),
            self._direct_script(report),
        ]
        present = [candidate for candidate in candidates if candidate.reasons]
        return sorted(present, key=lambda candidate: candidate.confidence, reverse=True)

    def _pf8_pfs(self, report: ScanReport) -> EngineCandidate:
        archives = [
            diagnostic
            for diagnostic in report.archive_diagnostics
            if diagnostic.format_id == "pf8_pfs"
        ]
        reasons: list[str] = []
        if archives:
            names = ", ".join(diagnostic.relative_path for diagnostic in archives[:3])
            reasons.append(f"found PFS/pf8 archive header: {names}")

        ast_count = sum(
            diagnostic.visible_extension_counts.get(".ast", 0)
            for diagnostic in archives
        )
        if ast_count:
            reasons.append(f"found {ast_count} visible .ast script entries in archive file table")

        script_samples = [
            path
            for diagnostic in archives
            for path in diagnostic.visible_script_paths[:3]
        ]
        if script_samples:
            reasons.append("sample script entries: " + ", ".join(script_samples[:5]))

        confidence = 0.45
        if archives:
            confidence += 0.2
        if ast_count:
            confidence += 0.2
        if script_samples:
            confidence += 0.1

        return EngineCandidate(
            engine_id="pf8_pfs_ast",
            label="PFS/pf8 AST scripts",
            confidence=min(0.9, confidence),
            reasons=tuple(reasons),
        )

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
        found_extensions = sorted(_direct_script_extensions(report))
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


def _direct_script_extensions(report: ScanReport) -> set[str]:
    extensions: set[str] = set()
    for file in report.files:
        normalized = file.relative_path.lower().replace("\\", "/")
        if file.extension in {".ks", ".rpy"}:
            extensions.add(file.extension)
        elif normalized == "0.txt":
            extensions.add(file.extension)
        elif normalized.startswith(("scenario/", "script/")) and file.extension in {
            ".csv",
            ".json",
            ".txt",
        }:
            extensions.add(file.extension)
    return extensions
