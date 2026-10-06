@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "DEMO_BODY=%TEMP%\fraud-pipeline-demo-50-%RANDOM%-%RANDOM%.json"
> "%DEMO_BODY%" echo {"count":50,"delay":0,"source":"frontend_simulator"}
curl.exe -fsS --max-time 15 -H "Content-Type: application/json" --data-binary "@%DEMO_BODY%" http://localhost:8001/api/batches
set "DEMO_RESULT=%ERRORLEVEL%"
del "%DEMO_BODY%" >nul 2>&1
if not "%DEMO_RESULT%"=="0" (
  echo The 50-transaction demo request failed.
  exit /b 1
)
echo.
echo The Control Center accepted the 50-transaction demo batch.
exit /b 0
