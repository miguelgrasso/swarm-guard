@echo off
REM Reanuda el entorno swarm-guard: bridge local + Claude Code con el mod spec-board cargado.
REM Uso:  .claude\spec-board\start.cmd            (continua la ultima sesion de esta carpeta)
REM       .claude\spec-board\start.cmd <session>  (reanuda una sesion concreta)
setlocal
cd /d "%~dp0..\.."

REM 1) Bridge del dashboard (si no esta corriendo ya)
tasklist /FI "WINDOWTITLE eq spec-board-bridge*" 2>nul | find /I "python" >nul || start "spec-board-bridge" /min .venv\Scripts\python.exe .claude\spec-board\bridge.py
echo Dashboard local: http://127.0.0.1:8787/board

REM 2) Binario de Claude Code: el de la extension de VS Code (mas nuevo) o el CLI instalado
set "CLAUDE="
for /f "delims=" %%D in ('dir /b /ad /o-n "%USERPROFILE%\.vscode\extensions\anthropic.claude-code-*" 2^>nul') do (
  if not defined CLAUDE if exist "%USERPROFILE%\.vscode\extensions\%%D\resources\native-binary\claude.exe" set "CLAUDE=%USERPROFILE%\.vscode\extensions\%%D\resources\native-binary\claude.exe"
)
if not defined CLAUDE set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
echo Claude: %CLAUDE%

REM 3) Sesion con el mod
if "%~1"=="" (
  "%CLAUDE%" --continue --plugin-dir .claude\spec-board-mod
) else (
  "%CLAUDE%" --resume %~1 --plugin-dir .claude\spec-board-mod
)
