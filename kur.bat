@echo off
rem Old name kept so existing instructions still work: the installer is now setup.bat (English).
call "%~dp0setup.bat" %*
exit /b %errorlevel%
