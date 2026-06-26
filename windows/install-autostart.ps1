# Registers a Scheduled Task that starts the server every time you log in.
# Run once, in PowerShell:  powershell -ExecutionPolicy Bypass -File windows\install-autostart.ps1
#
# Belt-and-suspenders with Docker Desktop's own "Start when you log in" setting
# (Settings -> General). Either alone is enough; both is most reliable.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$start = Join-Path $PSScriptRoot "start.bat"

# --- 1) Start the server at login -----------------------------------------
$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$start`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "BadmintonBros" -Action $action -Trigger $trigger `
  -Settings $settings -Description "Start the Badminton Bros server at login" -Force | Out-Null

# --- 2) Auto-redeploy when new code is pushed (pull-based CD) --------------
# Polls origin/main every 5 minutes; redeploys only when there's a new commit,
# and rolls back automatically if the rebuilt server fails its health check.
$redeploy = Join-Path $PSScriptRoot "redeploy.bat"
$log      = Join-Path $PSScriptRoot "redeploy.log"
$rAction  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"`"$redeploy`" >> `"$log`" 2>&1`""
$rTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$rSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName "BadmintonBrosRedeploy" -Action $rAction -Trigger $rTrigger `
  -Settings $rSettings -Description "Auto-redeploy the Badminton Bros server on new commits" -Force | Out-Null

Write-Host "Installed two tasks:"
Write-Host "  BadmintonBros         - starts the server when you log in."
Write-Host "  BadmintonBrosRedeploy - checks for new code every 5 min and redeploys (log: $log)."
Write-Host "Remove later with:"
Write-Host "  Unregister-ScheduledTask -TaskName BadmintonBros -Confirm:`$false"
Write-Host "  Unregister-ScheduledTask -TaskName BadmintonBrosRedeploy -Confirm:`$false"
