@echo off
setlocal enableextensions
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo === Aktapokus AI Studio setup ===
echo This script checks Python and git, creates a virtual environment in this folder
echo and installs the optional extras. No administrator rights needed. It writes
echo nothing outside this folder. Accounts and API keys are NOT part of setup:
echo you sign in to each provider yourself.
echo.

rem --- Python 3.10+ ---
set "PYCMD="
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto :python_ok
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto :python_ok
echo [ERROR] Python 3.10 or newer was not found.
echo   Install it from: https://www.python.org/downloads/
echo   Tick "Add python.exe to PATH" during installation, then run this file again.
goto :fail
:python_ok
echo [ok] Python found: %PYCMD%

rem --- git ---
git --version >nul 2>nul
if not errorlevel 1 goto :git_ok
echo [ERROR] git was not found. The undo feature relies on git.
echo   Install it from: https://git-scm.com/download/win
echo   Then run this file again.
goto :fail
:git_ok
echo [ok] git found.

rem --- virtual environment ---
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo Creating virtual environment ^(.venv^)...
%PYCMD% -m venv .venv
if not errorlevel 1 goto :venv_ok
echo [ERROR] Could not create the virtual environment.
goto :fail
:venv_ok
echo [ok] Virtual environment ready: %~dp0.venv

rem --- optional: QR code support for Telegram pairing (segno) ---
set "ANS=N"
if defined AKTAPOKUS_SETUP_QUIET (
  if defined AKTAPOKUS_SETUP_QR set "ANS=%AKTAPOKUS_SETUP_QR%"
) else (
  set /p ANS="Install QR code support for Telegram pairing? ^(segno package, downloaded from the internet^) [Y/N, Enter=N]: "
)
if /i not "%ANS%"=="Y" goto :qr_skip
echo Installing segno...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet segno
if errorlevel 1 echo [WARNING] segno could not be installed; pairing still works without QR ^(the link is printed^).
if not errorlevel 1 echo [ok] QR code support installed.
goto :qr_done
:qr_skip
echo QR code support skipped ^(optional; the pairing link is printed anyway^).
:qr_done

rem --- optional: OPC UA support (asyncua) ---
set "ANS=Y"
if defined AKTAPOKUS_SETUP_QUIET (
  if defined AKTAPOKUS_SETUP_OPCUA set "ANS=%AKTAPOKUS_SETUP_OPCUA%"
) else (
  set /p ANS="Install OPC UA support? ^(asyncua package, downloaded from the internet^) [Y/N, Enter=Y]: "
)
if /i not "%ANS%"=="Y" goto :opcua_skip
echo Installing asyncua...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet asyncua
if errorlevel 1 echo [WARNING] asyncua could not be installed; the OPC UA page will not work, everything else is unaffected.
if not errorlevel 1 echo [ok] OPC UA support installed.
goto :opcua_done
:opcua_skip
echo OPC UA support skipped ^(later: .venv\Scripts\python.exe -m pip install asyncua^).
:opcua_done

echo.
echo --- Installation check ---
".venv\Scripts\python.exe" -m aktapokus_ai_studio durum --arac
if errorlevel 1 goto :check_fail

echo.
echo === Setup complete. Next steps ===
echo 1^) Install at least one agent CLI: OpenCode ^(https://opencode.ai^), Claude Code ^(npm install -g @anthropic-ai/claude-code^) or Codex ^(npm install -g @openai/codex^). If the check above says "not found" for all three, install one first. Then sign in to it yourself; setup never asks for or stores logins.
echo 2^) Telegram ^(optional^): create a NEW bot for this computer with BotFather and write its token as a single line into
echo    %USERPROFILE%\.aktapokus\telegram.token ^(never share the token^).
echo    The same token cannot run on two computers at once; make one bot per computer.
echo 3^) Register your project folders once and start the bot:
echo    telegram-baslat.bat --kok C:\path\to\projects
echo 4^) Open the pairing link from your phone, then send /projeler to the bot.
echo Live interface: arayuz-baslat.bat
echo Desktop app ^(own window, shortcut^): kisayol-olustur.bat
echo.
if not defined AKTAPOKUS_SETUP_QUIET pause
exit /b 0

:check_fail
echo [ERROR] The installation check failed; see the output above.
:fail
echo.
if not defined AKTAPOKUS_SETUP_QUIET pause
exit /b 1
