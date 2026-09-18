@echo off
rem ???? WorkBuddy2API??????? start.ps1?
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause