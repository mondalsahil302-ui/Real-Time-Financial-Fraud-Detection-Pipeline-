@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found at .venv.
  exit /b 1
)
echo [1/5] Compile producer and backend
.venv\Scripts\python.exe -m py_compile producer\producer.py backend\app\main.py backend\app\chat.py
if errorlevel 1 exit /b 1
echo [2/5] Python tests
.venv\Scripts\python.exe -m pytest tests\
if errorlevel 1 exit /b 1
echo [3/5] Frontend tests
pushd frontend
node node_modules\vitest\vitest.mjs run
if errorlevel 1 (popd & exit /b 1)
echo [4/5] Frontend production build
node node_modules\typescript\bin\tsc -b
if errorlevel 1 (popd & exit /b 1)
node node_modules\vite\bin\vite.js build
if errorlevel 1 (popd & exit /b 1)
popd
echo [5/5] Control Center endpoints
curl.exe -fsS --max-time 5 -o nul http://localhost:8001/api/health
if errorlevel 1 (
  echo API health check failed.
  exit /b 1
)
curl.exe -fsS --max-time 5 -o nul http://localhost:5173/
if errorlevel 1 (
  echo Frontend health check failed.
  exit /b 1
)
echo API and frontend are responding.
echo Validation passed.
