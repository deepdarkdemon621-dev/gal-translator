param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$SourceLog,

    [string]$SessionReport = "",
    [string]$SourceName = "textractor",
    [int]$BatchSize = 1,
    [string]$Model = "gpt-5.5",
    [int]$Timeout = 600,
    [int]$MaxBatches = 1,
    [double]$WatchInterval = 1.0,
    [int]$WatchMaxCycles = 0,
    [int]$WatchIdleCycles = 0,
    [switch]$AllPending,
    [switch]$DryRun,
    [switch]$NoWatcher,
    [switch]$NoSubtitle,
    [switch]$NoReload,
    [switch]$SourceLogFromStart,
    [switch]$StartClipboardBridge,
    [double]$ClipboardInterval = 0.25,
    [int]$ClipboardMaxEvents = 0,
    [double]$ClipboardDuration = 0,

    [string]$MissLog = "",
    [string]$EventLog = "",
    [string]$WatcherStdout = "",
    [string]$WatcherStderr = "",
    [string]$SubtitleStdout = "",
    [string]$SubtitleStderr = "",
    [string]$ClipboardStdout = "",
    [string]$ClipboardStderr = "",
    [switch]$StartLunaHookBridge,
    [string]$LunaRoot = "C:\Game\LunaTranslator_x64_win10_v10.12.3\LunaTranslator_x64_win10",
    [int]$LunaHookGamePid = 0,
    [string]$LunaHookGameProcess = "selectoblige",
    [string[]]$LunaHookCode = @("ENHVXN-24@195720:selectoblige.exe", "HVXN-4C@1971E0:selectoblige.exe"),
    [double]$LunaHookDuration = 3600,
    [int]$LunaHookMaxEvents = 0,
    [double]$LunaHookIdleTimeout = 0,
    [string]$LunaHookStdout = "",
    [string]$LunaHookStderr = "",
    [string]$LunaHookStatusLog = "",

    [int]$X = 120,
    [int]$Y = 760,
    [int]$Width = 1200,
    [int]$Height = 120,
    [int]$FontSize = 30,
    [double]$Opacity = 0.82,
    [double]$ClearAfter = 4.0,
    [double]$ExitAfter = 0,
    [string]$FontFamily = "Microsoft YaHei UI",
    [string]$Background = "#050505",
    [string]$Foreground = "#f5f5f5",
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
        [string]$ProjectLogDir
    )
    if ($Path) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return Join-Path $ProjectLogDir $FallbackName
}

function Add-SwitchIf {
    param(
        [string[]]$Arguments,
        [string]$Name,
        [bool]$Enabled
    )
    if ($Enabled) {
        return $Arguments + $Name
    }
    return $Arguments
}

Push-Location $RepoRoot
try {
    $resolvedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
    $resolvedSourceLog = [System.IO.Path]::GetFullPath($SourceLog)
    $projectLogDir = Join-Path $resolvedProjectRoot "logs"
    New-Item -ItemType Directory -Force -Path $projectLogDir | Out-Null
    $sourceLogExisted = [System.IO.File]::Exists($resolvedSourceLog)
    $sourceLogCreated = $false
    if (-not $DryRun -and -not $sourceLogExisted) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resolvedSourceLog) | Out-Null
        New-Item -ItemType File -Force -Path $resolvedSourceLog | Out-Null
        $sourceLogCreated = $true
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $sessionReportPath = Resolve-SessionPath -Path $SessionReport -FallbackName "source-log-session-$stamp-report.json" -ProjectLogDir $projectLogDir
    $missLogPath = Resolve-SessionPath -Path $MissLog -FallbackName "source-log-session-$stamp-misses.txt" -ProjectLogDir $projectLogDir
    $eventLogPath = Resolve-SessionPath -Path $EventLog -FallbackName "source-log-session-$stamp-subtitle-events.jsonl" -ProjectLogDir $projectLogDir
    $watcherStdoutPath = Resolve-SessionPath -Path $WatcherStdout -FallbackName "source-log-session-$stamp-watcher-stdout.jsonl" -ProjectLogDir $projectLogDir
    $watcherStderrPath = Resolve-SessionPath -Path $WatcherStderr -FallbackName "source-log-session-$stamp-watcher-stderr.txt" -ProjectLogDir $projectLogDir
    $subtitleStdoutPath = Resolve-SessionPath -Path $SubtitleStdout -FallbackName "source-log-session-$stamp-subtitle-stdout.txt" -ProjectLogDir $projectLogDir
    $subtitleStderrPath = Resolve-SessionPath -Path $SubtitleStderr -FallbackName "source-log-session-$stamp-subtitle-stderr.txt" -ProjectLogDir $projectLogDir
    $clipboardStdoutPath = Resolve-SessionPath -Path $ClipboardStdout -FallbackName "source-log-session-$stamp-clipboard-stdout.json" -ProjectLogDir $projectLogDir
    $clipboardStderrPath = Resolve-SessionPath -Path $ClipboardStderr -FallbackName "source-log-session-$stamp-clipboard-stderr.txt" -ProjectLogDir $projectLogDir
    $lunaHookStdoutPath = Resolve-SessionPath -Path $LunaHookStdout -FallbackName "source-log-session-$stamp-lunahook-stdout.json" -ProjectLogDir $projectLogDir
    $lunaHookStderrPath = Resolve-SessionPath -Path $LunaHookStderr -FallbackName "source-log-session-$stamp-lunahook-stderr.txt" -ProjectLogDir $projectLogDir
    $lunaHookStatusLogPath = Resolve-SessionPath -Path $LunaHookStatusLog -FallbackName "source-log-session-$stamp-lunahook-status.jsonl" -ProjectLogDir $projectLogDir

    $watcherArgs = @(
        "-m", "gal_translator",
        "translate-log", $resolvedProjectRoot, $resolvedSourceLog,
        "--source-name", $SourceName,
        "--size", [string]$BatchSize,
        "--model", $Model,
        "--timeout", [string]$Timeout,
        "--max-batches", [string]$MaxBatches,
        "--watch",
        "--watch-interval", [string]$WatchInterval,
        "--watch-max-cycles", [string]$WatchMaxCycles,
        "--watch-idle-cycles", [string]$WatchIdleCycles
    )
    if (-not $AllPending) {
        $watcherArgs += "--only-new-log-entries"
    }
    if ($DryRun) {
        $watcherArgs += "--dry-run"
    }

    $subtitleArgs = @(
        "-m", "gal_translator",
        "subtitle-window", $resolvedProjectRoot,
        "--source-log", $resolvedSourceLog,
        "--source-log-name", $SourceName,
        "--miss-log", $missLogPath,
        "--event-log", $eventLogPath,
        "--x", [string]$X,
        "--y", [string]$Y,
        "--width", [string]$Width,
        "--height", [string]$Height,
        "--font-size", [string]$FontSize,
        "--opacity", [string]$Opacity,
        "--clear-after", [string]$ClearAfter,
        "--exit-after", [string]$ExitAfter,
        "--font-family", $FontFamily,
        "--background", $Background,
        "--foreground", $Foreground
    )
    if ($SourceLogFromStart) {
        $subtitleArgs += "--source-log-from-start"
    }
    if ($NoReload) {
        $subtitleArgs += "--no-reload"
    }
    if ($SubtitleConfig) {
        $subtitleArgs += @("--config", $SubtitleConfig)
    }
    if ($SubtitleSaveConfig) {
        $subtitleArgs += @("--save-config", $SubtitleSaveConfig)
    }

    $clipboardArgs = @(
        "-m", "gal_translator",
        "record-clipboard", $resolvedSourceLog,
        "--interval", [string]$ClipboardInterval,
        "--max-events", [string]$ClipboardMaxEvents,
        "--duration", [string]$ClipboardDuration
    )

    $resolvedLunaHookGamePid = $LunaHookGamePid
    if ($StartLunaHookBridge -and $resolvedLunaHookGamePid -le 0 -and $LunaHookGameProcess) {
        $processName = [System.IO.Path]::GetFileNameWithoutExtension($LunaHookGameProcess)
        $gameProcess = Get-Process -Name $processName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($gameProcess) {
            $resolvedLunaHookGamePid = $gameProcess.Id
        }
        elseif (-not $DryRun) {
            throw "Cannot start LunaHook bridge because process '$LunaHookGameProcess' is not running. Pass -LunaHookGamePid or start the game first."
        }
    }

    $lunaHookArgs = @(
        "-m", "gal_translator",
        "luna-hook-bridge", [string]$resolvedLunaHookGamePid, $resolvedSourceLog,
        "--luna-root", $LunaRoot,
        "--duration", [string]$LunaHookDuration,
        "--max-events", [string]$LunaHookMaxEvents,
        "--idle-timeout", [string]$LunaHookIdleTimeout,
        "--status-log", $lunaHookStatusLogPath
    )
    foreach ($hookCode in $LunaHookCode) {
        $lunaHookArgs += @("--hook-code", $hookCode)
    }

    $watcherProcess = $null
    $subtitleProcess = $null
    $clipboardProcess = $null
    $lunaHookProcess = $null
    if (-not $DryRun -and -not $NoWatcher) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $watcherStdoutPath) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $watcherStderrPath) | Out-Null
        $watcherProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList (ConvertTo-ProcessArgumentList -Arguments $watcherArgs) `
            -RedirectStandardOutput $watcherStdoutPath `
            -RedirectStandardError $watcherStderrPath `
            -WindowStyle Hidden `
            -PassThru
    }
    if (-not $DryRun -and -not $NoSubtitle) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $subtitleStdoutPath) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $subtitleStderrPath) | Out-Null
        $subtitleProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList (ConvertTo-ProcessArgumentList -Arguments $subtitleArgs) `
            -RedirectStandardOutput $subtitleStdoutPath `
            -RedirectStandardError $subtitleStderrPath `
            -PassThru
    }
    if (-not $DryRun -and $StartClipboardBridge) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $clipboardStdoutPath) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $clipboardStderrPath) | Out-Null
        $clipboardProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList (ConvertTo-ProcessArgumentList -Arguments $clipboardArgs) `
            -RedirectStandardOutput $clipboardStdoutPath `
            -RedirectStandardError $clipboardStderrPath `
            -WindowStyle Hidden `
            -PassThru
    }
    if (-not $DryRun -and $StartLunaHookBridge) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $lunaHookStdoutPath) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $lunaHookStderrPath) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $lunaHookStatusLogPath) | Out-Null
        $lunaHookProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList (ConvertTo-ProcessArgumentList -Arguments $lunaHookArgs) `
            -RedirectStandardOutput $lunaHookStdoutPath `
            -RedirectStandardError $lunaHookStderrPath `
            -WindowStyle Hidden `
            -PassThru
    }

    $nextActions = [System.Collections.Generic.List[string]]::new()
    if ($DryRun) {
        $nextActions.Add("Rerun source-log-session.ps1 without -DryRun to start the scoped source-log watcher and subtitle window.")
        if ($StartClipboardBridge) {
            $nextActions.Add("The planned clipboard bridge will append changed clipboard text into the same source log.")
        }
        if ($StartLunaHookBridge) {
            $nextActions.Add("The planned LunaHook bridge will append hooked game text into the same source log.")
        }
    }
    else {
        if (-not $NoWatcher) {
            $nextActions.Add("Keep the source-log watcher running; it translates only log-referenced entries unless -AllPending was used.")
        }
        if (-not $NoSubtitle) {
            $nextActions.Add("Keep the subtitle window open while LunaHook, Textractor, or a clipboard logger appends source lines to the source log.")
        }
        if ($StartClipboardBridge) {
            $nextActions.Add("The clipboard bridge is recording changed clipboard text into the same source log; use it when LunaHook/Textractor copies captured text instead of appending a file.")
        }
        if ($StartLunaHookBridge) {
            $nextActions.Add("The LunaHook bridge is recording hooked game text into the same source log.")
        }
    }
    if (-not $AllPending) {
        $nextActions.Add("Full archive translation remains paused; this session uses --only-new-log-entries so unrelated pending entries are not translated.")
    }
    if ($sourceLogCreated) {
        $nextActions.Add("The source log was created as an empty file; configure LunaHook, Textractor, or the logger to append runtime text to it.")
    }
    $nextActions.Add("Review sessionReportPath for watcher pid, subtitle pid, commands, and log paths if the launcher output is closed.")

    $restartArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "source-log-session.ps1"),
        "-ProjectRoot", $resolvedProjectRoot,
        "-SourceLog", $resolvedSourceLog,
        "-SessionReport", $sessionReportPath,
        "-SourceName", $SourceName,
        "-BatchSize", [string]$BatchSize,
        "-Model", $Model,
        "-Timeout", [string]$Timeout,
        "-MaxBatches", [string]$MaxBatches,
        "-WatchInterval", [string]$WatchInterval,
        "-WatchMaxCycles", [string]$WatchMaxCycles,
        "-WatchIdleCycles", [string]$WatchIdleCycles,
        "-MissLog", $missLogPath,
        "-EventLog", $eventLogPath,
        "-WatcherStdout", $watcherStdoutPath,
        "-WatcherStderr", $watcherStderrPath,
        "-SubtitleStdout", $subtitleStdoutPath,
        "-SubtitleStderr", $subtitleStderrPath,
        "-ClipboardStdout", $clipboardStdoutPath,
        "-ClipboardStderr", $clipboardStderrPath,
        "-LunaRoot", $LunaRoot,
        "-LunaHookGamePid", [string]$resolvedLunaHookGamePid,
        "-LunaHookGameProcess", $LunaHookGameProcess,
        "-LunaHookDuration", [string]$LunaHookDuration,
        "-LunaHookMaxEvents", [string]$LunaHookMaxEvents,
        "-LunaHookIdleTimeout", [string]$LunaHookIdleTimeout,
        "-LunaHookStdout", $lunaHookStdoutPath,
        "-LunaHookStderr", $lunaHookStderrPath,
        "-LunaHookStatusLog", $lunaHookStatusLogPath,
        "-X", [string]$X,
        "-Y", [string]$Y,
        "-Width", [string]$Width,
        "-Height", [string]$Height,
        "-FontSize", [string]$FontSize,
        "-Opacity", [string]$Opacity,
        "-ClearAfter", [string]$ClearAfter,
        "-ExitAfter", [string]$ExitAfter,
        "-FontFamily", $FontFamily,
        "-Background", $Background,
        "-Foreground", $Foreground
    )
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-AllPending" -Enabled ([bool]$AllPending)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-DryRun" -Enabled ([bool]$DryRun)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-NoWatcher" -Enabled ([bool]$NoWatcher)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-NoSubtitle" -Enabled ([bool]$NoSubtitle)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-NoReload" -Enabled ([bool]$NoReload)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-SourceLogFromStart" -Enabled ([bool]$SourceLogFromStart)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-StartClipboardBridge" -Enabled ([bool]$StartClipboardBridge)
    $restartArgs = Add-SwitchIf -Arguments $restartArgs -Name "-StartLunaHookBridge" -Enabled ([bool]$StartLunaHookBridge)
    if ($StartClipboardBridge) {
        $restartArgs += @("-ClipboardInterval", [string]$ClipboardInterval)
        $restartArgs += @("-ClipboardMaxEvents", [string]$ClipboardMaxEvents)
        $restartArgs += @("-ClipboardDuration", [string]$ClipboardDuration)
    }
    foreach ($hookCode in $LunaHookCode) {
        $restartArgs += @("-LunaHookCode", $hookCode)
    }
    if ($SubtitleConfig) {
        $restartArgs += @("-SubtitleConfig", $SubtitleConfig)
    }
    if ($SubtitleSaveConfig) {
        $restartArgs += @("-SubtitleSaveConfig", $SubtitleSaveConfig)
    }

    $payload = [ordered]@{
        status = if ($DryRun) { "planned" } else { "started" }
        projectRoot = $resolvedProjectRoot
        sessionReportPath = $sessionReportPath
        restartCommand = @("powershell") + $restartArgs
        sourceLog = $resolvedSourceLog
        sourceLogExists = [System.IO.File]::Exists($resolvedSourceLog)
        sourceLogCreated = $sourceLogCreated
        sourceName = $SourceName
        missLog = $missLogPath
        eventLog = $eventLogPath
        scopedTranslation = -not [bool]$AllPending
        watcher = [ordered]@{
            started = [bool]$watcherProcess
            pid = if ($watcherProcess) { $watcherProcess.Id } else { $null }
            stdoutPath = $watcherStdoutPath
            stderrPath = $watcherStderrPath
            command = @("python") + $watcherArgs
        }
        subtitleWindow = [ordered]@{
            started = [bool]$subtitleProcess
            pid = if ($subtitleProcess) { $subtitleProcess.Id } else { $null }
            stdoutPath = $subtitleStdoutPath
            stderrPath = $subtitleStderrPath
            command = @("python") + $subtitleArgs
        }
        clipboardBridge = [ordered]@{
            started = [bool]$clipboardProcess
            enabled = [bool]$StartClipboardBridge
            pid = if ($clipboardProcess) { $clipboardProcess.Id } else { $null }
            stdoutPath = $clipboardStdoutPath
            stderrPath = $clipboardStderrPath
            command = @("python") + $clipboardArgs
        }
        lunaHookBridge = [ordered]@{
            started = [bool]$lunaHookProcess
            enabled = [bool]$StartLunaHookBridge
            pid = if ($lunaHookProcess) { $lunaHookProcess.Id } else { $null }
            gamePid = $resolvedLunaHookGamePid
            gameProcess = $LunaHookGameProcess
            stdoutPath = $lunaHookStdoutPath
            stderrPath = $lunaHookStderrPath
            statusLogPath = $lunaHookStatusLogPath
            command = @("python") + $lunaHookArgs
        }
        nextActions = $nextActions.ToArray()
    }
    $jsonPayload = $payload | ConvertTo-Json -Depth 14
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sessionReportPath) | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($sessionReportPath, $jsonPayload + [Environment]::NewLine, $utf8NoBom)
    [Console]::Out.WriteLine($jsonPayload)
}
finally {
    Pop-Location
}
