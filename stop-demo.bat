@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" -ConfigPath "%~dp0demo-config.json"
