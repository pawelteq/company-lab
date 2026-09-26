@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Najpierw uruchom INSTALUJ.bat.
  pause
  exit /b 1
)
if not exist ".local\company_lab.sqlite3" (
  echo Brak lokalnej bazy do wyeksportowania.
  pause
  exit /b 1
)
if not exist ".local\financial_map.sqlite3" (
  echo Brak bazy mapy. Uruchom najpierw INSTALUJ.bat i przebuduj dane.
  pause
  exit /b 1
)
if not exist "PACZKI_DANYCH" mkdir "PACZKI_DANYCH"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"
set "OUTPUT=PACZKI_DANYCH\company-lab-dane-%STAMP%.zip"

echo Tworze prywatna paczke danych, opisow, oznaczen i analiz: %OUTPUT%
echo Nie publikuj jej w publicznym repozytorium.
".venv\Scripts\python.exe" scripts\data_zip.py export "%OUTPUT%"
if errorlevel 1 (
  echo Eksport nie powiodl sie.
  pause
  exit /b 1
)

echo.
echo Gotowe: %OUTPUT%
pause
exit /b 0
