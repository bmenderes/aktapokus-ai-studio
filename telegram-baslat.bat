@echo off
rem Aktapokus Telegram botu baslatici. Hangi klasorden acilirsa acilsin dogru yere gecer. Durdurmak icin Ctrl+C ^(sorarsa E^).
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :var
echo Once kur.bat dosyasini calistirin ^(bir kerelik kurulum^).
pause
exit /b 1
:var
".venv\Scripts\python.exe" -u -m aktapokus_ajan telegram %*
echo.
echo Bot durdu.
pause
