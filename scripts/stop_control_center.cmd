@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "STOP_FAILED=0"
echo Stopping only Control Center processes in project-launched windows.
call :stopwindow FraudPipeline-Backend 8001
call :stopwindow FraudPipeline-Frontend 5173
call :stopwindow "Fraud Control Center API" 8001
call :stopwindow "Fraud Control Center UI" 5173
if "!STOP_FAILED!"=="1" (
  echo One or more Control Center process trees could not be stopped.
  exit /b 1
)
echo Control Center stop requests completed.
exit /b 0

:stopwindow
set "WINDOW_MATCHED=0"
for /f "tokens=2 delims=," %%P in ('tasklist.exe /V /FI "IMAGENAME eq cmd.exe" /FO CSV /NH ^| findstr.exe /I /C:"%~1"') do call :killpid %%~P %~2
if "!WINDOW_MATCHED!"=="0" (
  netstat -ano -p tcp | findstr /R /C:":%~2 .*LISTENING" >nul
  if not errorlevel 1 (
    echo FAIL: Port %~2 is still listening, but no Control Center window matched "%~1".
    set "STOP_FAILED=1"
  )
)
exit /b 0

:killpid
set "WINDOW_MATCHED=1"
echo Stopping project window process tree (PID %~1).
taskkill.exe /PID %~1 /T /F
if errorlevel 1 (
  tasklist.exe /FI "PID eq %~1" /FO TABLE /NH | findstr.exe /C:"%~1" >nul
  if not errorlevel 1 (
    echo FAIL: Control Center window PID %~1 is still running.
    set "STOP_FAILED=1"
  ) else (
    netstat -ano -p tcp | findstr /R /C:":%~2 .*LISTENING" >nul
    if not errorlevel 1 (
      echo FAIL: Control Center service port %~2 is still listening.
      set "STOP_FAILED=1"
    ) else (
      echo WARNING: The Control Center window is gone and port %~2 is down; taskkill reported an auxiliary child error.
    )
  )
)
exit /b 0
