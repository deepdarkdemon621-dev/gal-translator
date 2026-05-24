param(
    [Parameter(Mandatory = $true)]
    [string]$GamePath,

    [string]$LogPath = "",

    [string]$Workspace = "$env:LOCALAPPDATA\GalTranslator",
    [string]$SourceName = "textractor",
    [int]$BatchSize = 40,
    [int]$TranslateTimeout = 600,
    [int]$TranslateMaxBatches = 0,
    [switch]$TranslateRetryFailed,
    [string]$ReplayEventLog = "",
    [string]$SubtitleMissLog = "",
    [string]$SubtitlePreviewSource = "",
    [string]$SessionReport = "",
    [switch]$RecordClipboard,
    [double]$RecordDuration = 60.0,
    [int]$RecordMaxEvents = 0,
    [double]$RecordInterval = 0.25,
    [switch]$RecordUntilInterrupted,
    [switch]$OverwriteLog,
    [switch]$LaunchGame,
    [switch]$Append,
    [switch]$DryRun,
    [switch]$NoSubtitle,
    [switch]$SubtitleDetach,
    [switch]$NoSubtitleReload,
    [switch]$SubtitlePreviewFirstMatch,
    [switch]$SubtitleSourceLog,
    [switch]$SubtitleSourceLogFromStart,

    [int]$X = 120,
    [int]$Y = 760,
    [int]$Width = 1200,
    [int]$Height = 120,
    [int]$FontSize = 30,
    [double]$Opacity = 0.82,
    [double]$ClearAfter = 4.0,
    [double]$SubtitleExitAfter = 0,
    [string]$FontFamily = "Microsoft YaHei UI",
    [string]$SubtitleConfig = "",
    [string]$SubtitleSaveConfig = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-CaptureLogPath {
    param(
        [string]$Path,
        [string]$GamePath,
        [string]$Workspace
    )
    if ($Path) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    $workspaceRoot = [System.IO.Path]::GetFullPath($Workspace)
    $gameName = [System.IO.Path]::GetFileNameWithoutExtension($GamePath)
    if (-not $gameName) {
        $trimmedGamePath = $GamePath.TrimEnd([char[]]@('\', '/'))
        $gameName = [System.IO.Path]::GetFileName($trimmedGamePath)
    }
    if (-not $gameName) {
        $gameName = "session"
    }
    foreach ($invalid in [System.IO.Path]::GetInvalidFileNameChars()) {
        $gameName = $gameName.Replace([string]$invalid, "_")
    }
    return Join-Path (Join-Path $workspaceRoot "captures") "$gameName-live-capture.txt"
}

Push-Location $RepoRoot
try {
    $resolvedLogPath = Resolve-CaptureLogPath -Path $LogPath -GamePath $GamePath -Workspace $Workspace
    $sessionArgs = @(
        "-m", "gal_translator",
        "play-session", $GamePath, $resolvedLogPath,
        "--workspace", $Workspace,
        "--source-name", $SourceName,
        "--batch-size", $BatchSize,
        "--translate-timeout", $TranslateTimeout,
        "--translate-max-batches", $TranslateMaxBatches,
        "--x", $X,
        "--y", $Y,
        "--width", $Width,
        "--height", $Height,
        "--font-size", $FontSize,
        "--opacity", $Opacity,
        "--clear-after", $ClearAfter,
        "--subtitle-exit-after", $SubtitleExitAfter,
        "--font-family", $FontFamily
    )
    if ($LaunchGame) {
        $sessionArgs += "--launch-game"
    }
    if ($Append) {
        $sessionArgs += "--append"
    }
    if ($RecordClipboard) {
        $sessionArgs += "--record-clipboard"
        $sessionArgs += "--record-interval"
        $sessionArgs += $RecordInterval
        $sessionArgs += "--record-duration"
        $sessionArgs += $RecordDuration
        $sessionArgs += "--record-max-events"
        $sessionArgs += $RecordMaxEvents
        if ($RecordUntilInterrupted) {
            $sessionArgs += "--record-until-interrupted"
        }
    }
    if ($OverwriteLog) {
        $sessionArgs += "--overwrite-log"
    }
    if ($DryRun) {
        $sessionArgs += "--translate-dry-run"
        $sessionArgs += "--subtitle-dry-run"
    }
    if ($TranslateRetryFailed) {
        $sessionArgs += "--translate-retry-failed"
    }
    if ($ReplayEventLog) {
        $sessionArgs += "--replay-event-log"
        $sessionArgs += $ReplayEventLog
    }
    if ($SubtitleMissLog) {
        $sessionArgs += "--subtitle-miss-log"
        $sessionArgs += $SubtitleMissLog
    }
    if ($SubtitlePreviewSource) {
        $sessionArgs += "--subtitle-preview-source"
        $sessionArgs += $SubtitlePreviewSource
    }
    if ($SubtitlePreviewFirstMatch) {
        $sessionArgs += "--subtitle-preview-first-match"
    }
    if ($SubtitleConfig) {
        $sessionArgs += @("--subtitle-config", $SubtitleConfig)
    }
    if ($SubtitleSaveConfig) {
        $sessionArgs += @("--subtitle-save-config", $SubtitleSaveConfig)
    }
    if ($SubtitleSourceLog) {
        $sessionArgs += "--subtitle-source-log"
    }
    if ($SubtitleSourceLogFromStart) {
        $sessionArgs += "--subtitle-source-log-from-start"
    }
    if ($SessionReport) {
        $sessionArgs += "--session-report"
        $sessionArgs += $SessionReport
    }
    if ($NoSubtitleReload) {
        $sessionArgs += "--subtitle-no-reload"
    }
    if ($SubtitleDetach) {
        $sessionArgs += "--subtitle-detach"
    }
    if ($NoSubtitle) {
        $sessionArgs += "--no-subtitle"
    }
    & python @sessionArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
