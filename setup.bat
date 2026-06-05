@echo off
REM TMRP one-click setup launcher. Double-click this file.
REM It starts setup.ps1, which requests administrator approval (UAC) and then
REM installs WSL2 + Docker, generates secrets, and starts the whole stack.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
