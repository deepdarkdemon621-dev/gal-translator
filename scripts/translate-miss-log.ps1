param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$LogPath,

    [string]$SourceName = "misses",
    [int]$Size = 40,
    [string]$Model = "gpt-5.5",
    [int]$Timeout = 600,
    [int]$MaxBatches = 0,
    [string]$ReplayEventLog = "",
    [switch]$DryRun,
    [switch]$Watch,
    [switch]$WatchRequireReady,
    [double]$WatchInterval = 5.0,
    [int]$WatchMaxCycles = 0,
    [int]$WatchIdleCycles = 0,
    [switch]$AllPending
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    $arguments = @(
        "-m", "gal_translator",
        "translate-log", $ProjectRoot, $LogPath,
        "--source-name", $SourceName,
        "--size", $Size,
        "--model", $Model,
        "--timeout", $Timeout,
        "--max-batches", $MaxBatches
    )
    if (-not $AllPending) {
        $arguments += "--only-new-log-entries"
    }
    if ($DryRun) {
        $arguments += "--dry-run"
    }
    if ($Watch) {
        $arguments += "--watch"
        $arguments += "--watch-interval"
        $arguments += $WatchInterval
        $arguments += "--watch-max-cycles"
        $arguments += $WatchMaxCycles
        $arguments += "--watch-idle-cycles"
        $arguments += $WatchIdleCycles
        if ($WatchRequireReady) {
            $arguments += "--watch-require-ready"
        }
    }
    if ($ReplayEventLog) {
        $arguments += @("--replay-event-log", $ReplayEventLog)
    }
    python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
