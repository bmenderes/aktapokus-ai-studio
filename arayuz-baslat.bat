@echo off
rem Aktapokus canli arayuz baslatici. Hangi klasorden acilirsa acilsin dogru yere gecer. Durdurmak icin Ctrl+C ^(sorarsa E^).
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :var
echo Run setup.bat first ^(one-time setup^).
pause
exit /b 1
:var
".venv\Scripts\python.exe" -u -m aktapokus_ai_studio ui --tarayici %*
echo.
echo Arayuz durdu.
pause
