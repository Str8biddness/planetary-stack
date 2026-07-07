$Action = New-ScheduledTaskAction -Execute "C:\Users\dakin\Downloads\synthesus\synthesus\.venv\Scripts\python.exe" -Argument "C:\Users\dakin\Downloads\synthesus\synthesus\scripts\keep_alive.py" -WorkingDirectory "C:\Users\dakin\Downloads\synthesus\synthesus"
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "SynthesusPipelinePersistence" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

Write-Host "Synthesus Pipeline Persistence task registered successfully."
Write-Host "It will now run at every system startup."
