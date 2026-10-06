@echo off
rem Instala e prepara o projeto. Pode rodar de novo quando quiser:
rem o que ja estiver pronto e mantido.
rem
rem O -ExecutionPolicy Bypass vale so para este processo. Sem ele, o Windows
rem recusa scripts .ps1 por padrao; a politica do sistema nao e alterada.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1"
echo.
pause
