@echo off
rem Masaustune "Aktapokus" kisayolu koyar. Hangi klasorden acilirsa acilsin dogru yere gecer.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kisayol-olustur.ps1"
if errorlevel 1 (
  echo.
  echo Kisayol olusturulamadi.
)
echo.
pause
