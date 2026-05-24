$ShortcutPath = [System.IO.Path]::Combine($env:APPDATA, 'Microsoft\Windows\Start Menu\Programs\Startup', 'SynthesusPipeline.lnk')
$TargetFile = 'C:\Users\dakin\Downloads\synthesus\synthesus\scripts\silent_run.vbs'
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetFile
$Shortcut.Save()
Write-Host "Startup shortcut created at $ShortcutPath"
