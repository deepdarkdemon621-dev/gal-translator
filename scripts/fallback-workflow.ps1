param(
    [Parameter(Mandatory = $true)]
    [string]$GamePath,

    [Parameter(Mandatory = $true)]
    [string]$LogPath,

    [string]$Workspace = "$env:LOCALAPPDATA\GalTranslator",
    [string]$SourceName = "textractor",
    [switch]$Append,
    [int]$PrepareSize = 40,
    [switch]$TranslateAll,
    [switch]$TranslateDryRun,
    [int]$TranslateTimeout = 600,
    [int]$TranslateMaxBatches = 0,
    [string]$ReplayEventLog = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    $workflowArgs = @(
        "-m", "gal_translator",
        "workflow-fallback", $GamePath, $LogPath,
        "--workspace", $Workspace,
        "--source-name", $SourceName,
        "--prepare-size", $PrepareSize
    )
    if ($Append) {
        $workflowArgs += "--append"
    }
    if ($TranslateAll) {
        $workflowArgs += "--translate-all"
        $workflowArgs += "--translate-timeout"
        $workflowArgs += $TranslateTimeout
        $workflowArgs += "--translate-max-batches"
        $workflowArgs += $TranslateMaxBatches
    }
    if ($TranslateDryRun) {
        $workflowArgs += "--translate-dry-run"
    }
    if ($ReplayEventLog) {
        $workflowArgs += "--replay-event-log"
        $workflowArgs += $ReplayEventLog
    }
    python @workflowArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
