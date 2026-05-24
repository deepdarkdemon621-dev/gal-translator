param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [int]$FontSize = 28,
    [double]$Opacity = 0.85,
    [int]$Width = 900,
    [int]$Height = 140,
    [Nullable[int]]$X = $null,
    [Nullable[int]]$Y = $null,
    [string]$FontFamily = "Microsoft YaHei UI",
    [string]$Background = "#050505",
    [string]$Foreground = "#f5f5f5",
    [double]$ClearAfter = 0,
    [double]$ExitAfter = 0,
    [string]$EventLog = "",
    [string]$MissLog = "",
    [string]$SourceLog = "",
    [string]$SourceLogEncoding = "utf-8",
    [string]$SourceLogName = "",
    [switch]$SourceLogFromStart,
    [switch]$NoReload,
    [string]$Config = "",
    [string]$SaveConfig = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    $arguments = @(
        "-m", "gal_translator", "subtitle-window", $ProjectRoot,
        "--font-size", $FontSize,
        "--opacity", $Opacity,
        "--width", $Width,
        "--height", $Height,
        "--font-family", $FontFamily,
        "--background", $Background,
        "--foreground", $Foreground,
        "--clear-after", $ClearAfter,
        "--exit-after", $ExitAfter
    )
    if ($null -ne $X) {
        $arguments += @("--x", $X)
    }
    if ($null -ne $Y) {
        $arguments += @("--y", $Y)
    }
    if ($EventLog) {
        $arguments += @("--event-log", $EventLog)
    }
    if ($MissLog) {
        $arguments += @("--miss-log", $MissLog)
    }
    if ($SourceLog) {
        $arguments += @("--source-log", $SourceLog)
        $arguments += @("--source-log-encoding", $SourceLogEncoding)
        if ($SourceLogName) {
            $arguments += @("--source-log-name", $SourceLogName)
        }
        if ($SourceLogFromStart) {
            $arguments += "--source-log-from-start"
        }
    }
    if ($NoReload) {
        $arguments += "--no-reload"
    }
    if ($Config) {
        $arguments += @("--config", $Config)
    }
    if ($SaveConfig) {
        $arguments += @("--save-config", $SaveConfig)
    }
    python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
