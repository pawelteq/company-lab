@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Najpierw uruchom INSTALUJ.bat.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo Brak zbudowanej strony. Uruchom INSTALUJ.bat.
  pause
  exit /b 1
)
if not exist ".local\company_lab.sqlite3" (
  echo Brak danych. Najpierw uruchom IMPORTUJ_DANE_Z_ZIP.bat.
  pause
  exit /b 1
)

echo Uruchamiam Company Lab pod adresem http://127.0.0.1:8000/
start "Company Lab - serwer" cmd /k "cd /d ""%~dp0"" && .venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/"
exit /b 0
