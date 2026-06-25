# Registers a Scheduled Task that starts the server every time you log in.
# Run once, in PowerShell:  powershell -ExecutionPolicy Bypass -File windows\install-autostart.ps1
#
# Belt-and-suspenders with Docker Desktop's own "Start when you log in" setting
# (Settings -> General). Either alone is enough; both is most reliable.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$start = Join-Path $PSScriptRoot "start.bat"

$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$start`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "BadmintonBros" -Action $action -Trigger $trigger `
  -Settings $settings -Description "Start the Badminton Bros server at login" -Force | Out-Null

Write-Host "Installed. The server will start automatically when you log in."
Write-Host "Remove later with:  Unregister-ScheduledTask -TaskName BadmintonBros -Confirm:`$false"
