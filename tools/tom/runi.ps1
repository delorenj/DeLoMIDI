# Run a PowerShell script inside jarad's interactive desktop session (session 1) via a throwaway
# scheduled task with an Interactive logon type: no password, and it only works while that user
# is logged on. Invoke from an admin SSH session:  powershell -File runi.ps1 -Script C:\ProgramData\DeLoMIDI\shot.ps1
param([Parameter(Mandatory)][string]$Script, [string]$User = 'jarad', [int]$TimeoutSec = 40, [string]$ScriptArgs = '')
$ErrorActionPreference = 'Stop'
$name = 'klt-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$arg = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Script`" $ScriptArgs"
$act = New-ScheduledTaskAction -Execute 'conhost.exe' -Argument $arg
$pr  = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$User" -LogonType Interactive -RunLevel Limited
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $name -Action $act -Principal $pr -Settings $set | Out-Null
try {
    Start-ScheduledTask -TaskName $name
    $sw = [Diagnostics.Stopwatch]::StartNew()
    do {
        Start-Sleep -Milliseconds 250
        $i = Get-ScheduledTaskInfo -TaskName $name
    } while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec -and ($i.LastTaskResult -eq 267009 -or $i.LastTaskResult -eq 267011 -or $i.LastRunTime.Year -lt 2000))
    "task=$name result=$($i.LastTaskResult) elapsed=$([int]$sw.Elapsed.TotalMilliseconds)ms"
} finally {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
