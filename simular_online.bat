@echo off
chcp 65001 >nul
title Sistema de Formulacion - simulacion online
cd /d "%~dp0"

REM ===================================================================
REM  Simula el funcionamiento en la web (Railway) en este computador:
REM  mismas variables de entorno, carpeta de datos separada, clave admin.
REM  Los datos de esta prueba quedan en "datos_simulacion" (no se suben a git
REM  y no tocan tu base real epi_sistema.db).
REM ===================================================================

set PORT=8790
set DATA_DIR=%~dp0datos_simulacion
set ADMIN_KEY=simulacion-local-2026
set CLAUDE_MODEL=claude-opus-5-5
set CLAUDE_MAX_TOKENS=4096

REM Clave de Claude opcional: si existe el archivo clave_anthropic_local.txt
REM (una sola linea con la clave), se usa como clave del servidor.
REM Ese archivo esta en .gitignore: nunca se sube a GitHub.
set ANTHROPIC_API_KEY=
if exist "clave_anthropic_local.txt" set /p ANTHROPIC_API_KEY=<"clave_anthropic_local.txt"

echo.
echo  Sistema de Formulacion - SIMULACION ONLINE
echo  -------------------------------------------
echo  Direccion:          http://localhost:%PORT%
echo  Clave de admin:     %ADMIN_KEY%   (para crear cuentas en el panel de administracion)
echo  Datos de prueba en: %DATA_DIR%
echo.
echo  Deja esta ventana abierta mientras pruebas. Cierrala para detener el servidor.
echo.

start "" "http://localhost:%PORT%"

where py >nul 2>nul
if %errorlevel%==0 (
  py backend_epi.py
) else (
  python backend_epi.py
)
pause
