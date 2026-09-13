@echo off
chcp 65001 >nul
call "%~dp0run.bat" --install
exit /b %ERRORLEVEL%
