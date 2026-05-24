param(
    [Parameter(Mandatory = $true)]
    [string]$SessionReport,

    [switch]$DryRun,
    [switch]$OpenSubtitle,
    [switch]$StartMissWatcher,
    [switch]$StartSessionLogWatcher,
    [switch]$SubtitleForeground,
    [switch]$RetryFailed
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    $arguments = @(
        "-m", "gal_translator",
        "resume-session", $SessionReport
    )
    if ($DryRun) {
        $arguments += "--dry-run"
    }
    if ($OpenSubtitle) {
        $arguments += "--open-subtitle"
    }
    if ($StartMissWatcher) {
        $arguments += "--start-miss-watcher"
    }
    if ($StartSessionLogWatcher) {
        $arguments += "--start-session-log-watcher"
    }
    if ($SubtitleForeground) {
        $arguments += "--subtitle-foreground"
    }
    if ($RetryFailed) {
        $arguments += "--retry-failed"
    }
    python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
