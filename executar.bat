@echo off
rem Abre o programa. Antes, garante que o Docker esta aberto e o banco pronto.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\executar.ps1"
if errorlevel 1 pause
