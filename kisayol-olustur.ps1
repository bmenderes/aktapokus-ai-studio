# Aktapokus masaustu kisayolu. Hangi klasorden calistirilirsa calistirilsin dogru yeri bulur (ev bilgisayarinda da kullanilabilir).
$ErrorActionPreference = "Stop"
$proje = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $proje ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $py)) { Write-Host "Once kur.bat dosyasini calistirin (bir kerelik kurulum)."; exit 1 }
$masaustu = [Environment]::GetFolderPath("Desktop")
$yol = Join-Path $masaustu "Aktapokus.lnk"
$ws = New-Object -ComObject WScript.Shell
$k = $ws.CreateShortcut($yol)
$k.TargetPath = $py
$k.Arguments = "-m aktapokus_ajan ui --uygulama"
$k.WorkingDirectory = $proje
$icon = Join-Path $proje "aktapokus.ico"
if (Test-Path $icon) { $k.IconLocation = $icon }
$k.Description = "Aktapokus - kendi penceresinde acilir, pencere kapaninca kapanir"
$k.Save()
Write-Host "Kisayol olusturuldu: $yol"
