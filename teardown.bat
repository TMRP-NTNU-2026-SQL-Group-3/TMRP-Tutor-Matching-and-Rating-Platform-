@echo off
REM TMRP teardown launcher. Double-click this file.
REM It starts teardown.ps1, which requests administrator approval (UAC) and then
REM stops the stack, deletes generated secrets, and uninstalls Docker + WSL.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0teardown.ps1"
