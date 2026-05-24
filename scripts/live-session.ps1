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
    [string]$MissWatcherLog = "",
    [string]$MissWatcherErrorLog = "",
    [string]$SessionLogWatcherLog = "",
    [string]$SessionLogWatcherErrorLog = "",
    [switch]$NoMissWatcher,
    [switch]$NoSessionLogWatcher,
    [double]$WatchInterval = 5.0,
    [int]$WatchMaxCycles = 0,
    [int]$WatchIdleCycles = 0,
    [switch]$KeepMissWatcher,
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

function ConvertTo-ProcessArgumentList {
    param([string[]]$Arguments)
    ($Arguments | ForEach-Object {
        '"' + ($_ -replace '"', '\"') + '"'
    }) -join " "
}

function Resolve-SessionPath {
    param(
        [string]$Path,
        [string]$FallbackName,
        [string]$BaseLogPath
    )
    if ($Path) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    $logFullPath = [System.IO.Path]::GetFullPath($BaseLogPath)
    $logDirectory = Split-Path -Parent $logFullPath
    return Join-Path $logDirectory $FallbackName
}

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

function New-DefaultSessionReportPath {
    param([string]$ProjectLogDir)
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    return Join-Path $ProjectLogDir "live-session-$stamp-$PID.json"
}

Push-Location $RepoRoot
$watcherProcess = $null
$sessionLogWatcherProcess = $null
$keepWatcherAfterExit = [bool]$KeepMissWatcher
$keepSessionLogWatcherAfterExit = [bool]$KeepMissWatcher
try {
    $resolvedLogPath = Resolve-CaptureLogPath -Path $LogPath -GamePath $GamePath -Workspace $Workspace
    $missLogPath = Resolve-SessionPath -Path $SubtitleMissLog -FallbackName "misses.txt" -BaseLogPath $resolvedLogPath
    $initJson = & python -m gal_translator init $GamePath --workspace $Workspace
    if ($LASTEXITCODE -ne 0) {
        throw "project initialization failed"
    }
    $projectRoot = ($initJson | ConvertFrom-Json).projectRoot
    $projectLogDir = Join-Path $projectRoot "logs"
    New-Item -ItemType Directory -Force -Path $projectLogDir | Out-Null
    if ($SessionReport) {
        $sessionReportPath = [System.IO.Path]::GetFullPath($SessionReport)
    }
    else {
        $sessionReportPath = New-DefaultSessionReportPath -ProjectLogDir $projectLogDir
    }

    $watcherStdout = Resolve-SessionPath -Path $MissWatcherLog -FallbackName "miss-watch.jsonl" -BaseLogPath $resolvedLogPath
    $watcherStderr = Resolve-SessionPath -Path $MissWatcherErrorLog -FallbackName "miss-watch-stderr.txt" -BaseLogPath $resolvedLogPath
    $sessionLogWatcherStdout = Resolve-SessionPath -Path $SessionLogWatcherLog -FallbackName "session-log-watch.jsonl" -BaseLogPath $resolvedLogPath
    $sessionLogWatcherStderr = Resolve-SessionPath -Path $SessionLogWatcherErrorLog -FallbackName "session-log-watch-stderr.txt" -BaseLogPath $resolvedLogPath

    if (-not $NoMissWatcher) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $watcherStdout) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $watcherStderr) | Out-Null
        $watcherArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "translate-miss-log.ps1"),
            "-ProjectRoot", $projectRoot,
            "-LogPath", $missLogPath,
            "-Watch",
            "-WatchInterval", $WatchInterval,
            "-WatchMaxCycles", $WatchMaxCycles,
            "-WatchIdleCycles", $WatchIdleCycles,
            "-WatchRequireReady",
            "-Size", $BatchSize,
            "-Timeout", $TranslateTimeout,
            "-MaxBatches", $TranslateMaxBatches
        )
        if ($DryRun) {
            $watcherArgs += "-DryRun"
        }
        $watcherProcess = Start-Process `
            -FilePath "powershell" `
            -ArgumentList (ConvertTo-ProcessArgumentList -Arguments $watcherArgs) `
            -RedirectStandardOutput $watcherStdout `
            -RedirectStandardError $watcherStderr `
            -WindowStyle Hidden `
            -PassThru
    }
    if ($SubtitleSourceLog -and -not $NoSessionLogWatcher) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sessionLogWatcherStdout) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sessionLogWatcherStderr) | Out-Null
        $sessionLogWatcherArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "translate-miss-log.ps1"),
            "-ProjectRoot", $projectRoot,
            "-LogPath", $resolvedLogPath,
            "-SourceName", $SourceName,
            "-Watch",
            "-WatchInterval", $WatchInterval,
            "-WatchMaxCycles", $WatchMaxCycles,
            "-WatchIdleCycles", $WatchIdleCycles,
            "-WatchRequireReady",
            "-Size", $BatchSize,
            "-Timeout", $TranslateTimeout,
            "-MaxBatches", $TranslateMaxBatches
        )
        if ($DryRun) {
            $sessionLogWatcherArgs += "-DryRun"
        }
        $sessionLogWatcherProcess = Start-Process `
            -FilePath "powershell" `
            -ArgumentList (ConvertTo-ProcessArgumentList -Arguments $sessionLogWatcherArgs) `
            -RedirectStandardOutput $sessionLogWatcherStdout `
            -RedirectStandardError $sessionLogWatcherStderr `
            -WindowStyle Hidden `
            -PassThru
    }

    $sessionParams = @{
        GamePath = $GamePath
        LogPath = $resolvedLogPath
        Workspace = $Workspace
        SourceName = $SourceName
        BatchSize = $BatchSize
        TranslateTimeout = $TranslateTimeout
        TranslateMaxBatches = $TranslateMaxBatches
        SubtitleMissLog = $missLogPath
        X = $X
        Y = $Y
        Width = $Width
        Height = $Height
        FontSize = $FontSize
        Opacity = $Opacity
        ClearAfter = $ClearAfter
        SubtitleExitAfter = $SubtitleExitAfter
        FontFamily = $FontFamily
    }
    if ($SubtitleConfig) {
        $sessionParams.SubtitleConfig = $SubtitleConfig
    }
    if ($SubtitleSaveConfig) {
        $sessionParams.SubtitleSaveConfig = $SubtitleSaveConfig
    }
    if ($ReplayEventLog) {
        $sessionParams.ReplayEventLog = $ReplayEventLog
    }
    if ($TranslateRetryFailed) {
        $sessionParams.TranslateRetryFailed = $true
    }
    if ($RecordClipboard) {
        $sessionParams.RecordClipboard = $true
        $sessionParams.RecordDuration = $RecordDuration
        $sessionParams.RecordMaxEvents = $RecordMaxEvents
        $sessionParams.RecordInterval = $RecordInterval
        if ($RecordUntilInterrupted) {
            $sessionParams.RecordUntilInterrupted = $true
        }
    }
    if ($OverwriteLog) {
        $sessionParams.OverwriteLog = $true
    }
    if ($LaunchGame) {
        $sessionParams.LaunchGame = $true
    }
    if ($Append) {
        $sessionParams.Append = $true
    }
    if ($DryRun) {
        $sessionParams.DryRun = $true
    }
    if ($NoSubtitle) {
        $sessionParams.NoSubtitle = $true
    }
    if ($SubtitleDetach) {
        $sessionParams.SubtitleDetach = $true
    }
    if ($NoSubtitleReload) {
        $sessionParams.NoSubtitleReload = $true
    }
    if ($SubtitlePreviewSource) {
        $sessionParams.SubtitlePreviewSource = $SubtitlePreviewSource
    }
    if ($SubtitlePreviewFirstMatch) {
        $sessionParams.SubtitlePreviewFirstMatch = $true
    }
    if ($SubtitleSourceLog) {
        $sessionParams.SubtitleSourceLog = $true
    }
    if ($SubtitleSourceLogFromStart) {
        $sessionParams.SubtitleSourceLogFromStart = $true
    }

    $sessionOutput = & (Join-Path $PSScriptRoot "translated-session.ps1") @sessionParams
    $sessionExitCode = $LASTEXITCODE
    $sessionPayload = $null
    try {
        $sessionPayload = $sessionOutput | ConvertFrom-Json
    }
    catch {
        $sessionPayload = $sessionOutput
    }

    if ($watcherProcess -and $DryRun) {
        $watcherProcess.WaitForExit(10000) | Out-Null
    }
    if ($sessionLogWatcherProcess -and $DryRun) {
        $sessionLogWatcherProcess.WaitForExit(10000) | Out-Null
    }

    $sessionStatus = $null
    if ($sessionPayload -and $sessionPayload.PSObject.Properties.Name -contains "sessionSummary") {
        $sessionStatus = $sessionPayload.sessionSummary.status
    }
    $subtitleDetached = $false
    if ($sessionPayload -and $sessionPayload.PSObject.Properties.Name -contains "subtitleWindow" -and $sessionPayload.subtitleWindow) {
        $subtitleDetached = [bool]$sessionPayload.subtitleWindow.detached
    }
    $keepWatcherAfterExit = [bool]($KeepMissWatcher -or ($subtitleDetached -and $sessionStatus -ne "subtitle_exited"))
    $keepSessionLogWatcherAfterExit = [bool]($KeepMissWatcher -or ($subtitleDetached -and $sessionStatus -ne "subtitle_exited"))

    $nextActions = [System.Collections.Generic.List[string]]::new()
    if ($sessionExitCode -ne 0) {
        $nextActions.Add("Review the session payload and rerun live-session after fixing the reported translation or capture issue.")
    }
    elseif ($sessionStatus -eq "translation_planned") {
        $nextActions.Add("Rerun live-session without -DryRun to execute Codex translation batches.")
    }
    elseif ($sessionStatus -eq "subtitle_ready") {
        $nextActions.Add("Rerun live-session without -DryRun, or start the returned subtitleWindow.command to open the live subtitle window.")
    }
    elseif ($sessionStatus -eq "no_source_text") {
        $nextActions.Add("No Japanese source lines were captured; check Textractor/clipboard output at sessionLogPath, then rerun live-session after the log contains story text.")
    }
    elseif ($sessionStatus -eq "subtitle_exited") {
        $detachedStderrPath = $null
        $detachedStdoutPath = $null
        if ($sessionPayload -and $sessionPayload.PSObject.Properties.Name -contains "subtitleWindow" -and $sessionPayload.subtitleWindow) {
            $detachedStderrPath = $sessionPayload.subtitleWindow.detachedStderrPath
            $detachedStdoutPath = $sessionPayload.subtitleWindow.detachedStdoutPath
        }
        if ($detachedStderrPath -or $detachedStdoutPath) {
            $nextActions.Add("Detached subtitle-window exited immediately; review detached logs stderr='$detachedStderrPath' stdout='$detachedStdoutPath', then rerun live-session or subtitle-window.")
        }
        else {
            $nextActions.Add("Detached subtitle-window exited immediately; review the nested subtitleWindow detached logs, then rerun live-session or subtitle-window.")
        }
    }
    elseif ($sessionStatus -eq "subtitle_started") {
        if ($subtitleDetached) {
            $nextActions.Add("Keep playing with the detached subtitle window open; unmatched lines go to the miss log and the watcher translates them.")
        }
        else {
            $nextActions.Add("Keep playing with the subtitle window open; unmatched lines go to the miss log and the watcher translates them.")
        }
    }
    elseif ($NoSubtitle) {
        $nextActions.Add("Start the subtitle window for this project, or rerun live-session without -NoSubtitle.")
    }
    else {
        $nextActions.Add("Review the nested sessionSummary and continue with its nextActions.")
    }
    if ($watcherProcess) {
        $nextActions.Add("Review the miss watcher JSONL log if translations do not appear automatically.")
    }
    if ($sessionLogWatcherProcess) {
        $nextActions.Add("Review the session-log watcher JSONL log if newly appended source-log lines do not translate automatically.")
    }

    $watcherActiveAtSummary = $false
    $watcherWillStopOnExit = $false
    $watcherRunningAfterExit = $false
    if ($watcherProcess) {
        $watcherActiveAtSummary = -not $watcherProcess.HasExited
        $watcherWillStopOnExit = $watcherActiveAtSummary -and -not $keepWatcherAfterExit
        $watcherRunningAfterExit = $watcherActiveAtSummary -and $keepWatcherAfterExit
        if ($watcherWillStopOnExit) {
            $nextActions.Add("Rerun with -KeepMissWatcher if the miss watcher should keep running after this command exits.")
        }
    }
    $sessionLogWatcherActiveAtSummary = $false
    $sessionLogWatcherWillStopOnExit = $false
    $sessionLogWatcherRunningAfterExit = $false
    if ($sessionLogWatcherProcess) {
        $sessionLogWatcherActiveAtSummary = -not $sessionLogWatcherProcess.HasExited
        $sessionLogWatcherWillStopOnExit = $sessionLogWatcherActiveAtSummary -and -not $keepSessionLogWatcherAfterExit
        $sessionLogWatcherRunningAfterExit = $sessionLogWatcherActiveAtSummary -and $keepSessionLogWatcherAfterExit
        if ($sessionLogWatcherWillStopOnExit) {
            $nextActions.Add("Rerun with -KeepMissWatcher if the session-log watcher should keep running after this command exits.")
        }
    }

    $resumeArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "resume-session.ps1"),
        "-SessionReport", $sessionReportPath
    )
    if (-not $NoSubtitle) {
        $resumeArgs += "-OpenSubtitle"
    }
    if (-not $NoMissWatcher) {
        $resumeArgs += "-StartMissWatcher"
    }
    if ($SubtitleSourceLog) {
        $resumeArgs += "-StartSessionLogWatcher"
    }
    $resumeCommand = @("powershell") + $resumeArgs
    if ($sessionExitCode -eq 0 -and $sessionStatus -ne "subtitle_started") {
        $nextActions.Add("Resume from sessionReportPath with the returned resumeCommand when you are ready to continue translation or restore subtitle display.")
    }

    $payload = [ordered]@{
        status = if ($sessionExitCode -eq 0) { "completed" } else { "failed" }
        projectRoot = $projectRoot
        sessionLogPath = $resolvedLogPath
        sessionReportPath = $sessionReportPath
        resumeCommand = $resumeCommand
        subtitleMissLog = $missLogPath
        missWatcher = if ($watcherProcess) {
            [ordered]@{
                started = $true
                pid = $watcherProcess.Id
                stdoutPath = $watcherStdout
                stderrPath = $watcherStderr
                activeAtSummary = $watcherActiveAtSummary
                willStopOnExit = $watcherWillStopOnExit
                running = $watcherRunningAfterExit
                command = @("powershell") + $watcherArgs
            }
        } else {
            [ordered]@{
                started = $false
                pid = $null
                stdoutPath = $null
                stderrPath = $null
                activeAtSummary = $false
                willStopOnExit = $false
                running = $false
                command = $null
            }
        }
        sessionLogWatcher = if ($sessionLogWatcherProcess) {
            [ordered]@{
                started = $true
                pid = $sessionLogWatcherProcess.Id
                stdoutPath = $sessionLogWatcherStdout
                stderrPath = $sessionLogWatcherStderr
                activeAtSummary = $sessionLogWatcherActiveAtSummary
                willStopOnExit = $sessionLogWatcherWillStopOnExit
                running = $sessionLogWatcherRunningAfterExit
                command = @("powershell") + $sessionLogWatcherArgs
            }
        } else {
            [ordered]@{
                started = $false
                pid = $null
                stdoutPath = $null
                stderrPath = $null
                activeAtSummary = $false
                willStopOnExit = $false
                running = $false
                command = $null
            }
        }
        sessionExitCode = $sessionExitCode
        session = $sessionPayload
        nextActions = $nextActions.ToArray()
    }
    $jsonPayload = $payload | ConvertTo-Json -Depth 20
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sessionReportPath) | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($sessionReportPath, $jsonPayload + [Environment]::NewLine, $utf8NoBom)
    $jsonPayload
    exit $sessionExitCode
}
finally {
    if ($watcherProcess -and -not $keepWatcherAfterExit -and -not $watcherProcess.HasExited) {
        Stop-Process -Id $watcherProcess.Id -Force
    }
    if ($sessionLogWatcherProcess -and -not $keepSessionLogWatcherAfterExit -and -not $sessionLogWatcherProcess.HasExited) {
        Stop-Process -Id $sessionLogWatcherProcess.Id -Force
    }
    Pop-Location
}
