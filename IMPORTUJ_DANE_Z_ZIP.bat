@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Najpierw uruchom INSTALUJ.bat.
  pause
  exit /b 1
)

set "ZIP_FILE=%~1"
if not defined ZIP_FILE (
  set "COUNT=0"
  for %%F in ("IMPORTUJ_TUTAJ\*.zip") do (
    if exist "%%~fF" (
      set /a COUNT+=1
      set "ZIP_FILE=%%~fF"
    )
  )
  if !COUNT! EQU 0 (
    echo Brak pliku ZIP w folderze IMPORTUJ_TUTAJ.
    echo Mozesz tez przeciagnac ZIP na ten plik BAT.
    pause
    exit /b 1
  )
  if !COUNT! GTR 1 (
    echo W folderze IMPORTUJ_TUTAJ jest wiecej niz jeden ZIP.
    echo Zostaw jeden plik albo przeciagnij wybrany ZIP na ten plik BAT.
    pause
    exit /b 1
  )
)

if not exist "%ZIP_FILE%" (
  echo Nie znaleziono pliku: %ZIP_FILE%
  pause
  exit /b 1
)

echo.
echo Import: %ZIP_FILE%
echo Nie zamykaj tego okna. Przy surowych danych operacja moze potrwac.
echo Istniejace bazy zostana zachowane w .local\backups.
echo.
".venv\Scripts\python.exe" scripts\data_zip.py import "%ZIP_FILE%"
if errorlevel 1 (
  echo.
  echo Import nie powiodl sie. Dotychczasowe dane nie zostaly usuniete.
  pause
  exit /b 1
)

echo.
echo Import zakonczony. Opisy, oznaczenia i gotowe analizy sa na miejscu.
echo Uruchom URUCHOM_STRONE.bat.
pause
exit /b 0
