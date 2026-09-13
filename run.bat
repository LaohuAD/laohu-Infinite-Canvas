@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYEXE=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0python\python.exe" set "PYEXE=%~dp0python\python.exe"
"%PYEXE%" "%~dp0local_runtime.py" %*
set "RUN_EXIT=%ERRORLEVEL%"
if not defined CANVAS_NO_PAUSE pause
exit /b %RUN_EXIT%
