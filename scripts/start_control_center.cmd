@echo off
setlocal
call "%~dp0start_backend.cmd"
if errorlevel 1 exit /b 1
timeout /t 2 /nobreak >nul
call "%~dp0start_frontend.cmd"
