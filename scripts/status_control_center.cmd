@echo off
setlocal EnableExtensions
set "FAIL=0"
call :checkhttp "Control Center API" http://localhost:8001/api/health
call :checkhttp "Control Center frontend" http://localhost:5173/
if "%FAIL%"=="1" exit /b 1
exit /b 0

:checkhttp
curl.exe -fsS --max-time 3 -o nul "%~2" >nul 2>&1
if errorlevel 1 (
  echo %~1: DOWN
  set "FAIL=1"
) else (
  echo %~1: UP
)
exit /b 0
