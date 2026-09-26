@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ========================================
echo   Company Lab - instalacja lokalna
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo BLAD: Nie znaleziono Pythona.
  echo Zainstaluj Python 3.12 z https://www.python.org/downloads/
  pause
  exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo BLAD: Wymagany jest Python 3.12.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo BLAD: Nie znaleziono Node.js i npm.
  echo Zainstaluj wersje LTS z https://nodejs.org/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Tworzenie srodowiska Python...
  py -3.12 -m venv .venv || goto :error
) else (
  echo [1/4] Srodowisko Python juz istnieje.
)

echo [2/4] Instalowanie zaleznosci Python...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.lock || goto :error

echo [3/4] Instalowanie interfejsu...
pushd frontend
call npm ci || goto :frontend_error

echo [4/4] Budowanie strony...
call npm run build || goto :frontend_error
popd

if not exist "IMPORTUJ_TUTAJ" mkdir "IMPORTUJ_TUTAJ"
if not exist "PACZKI_DANYCH" mkdir "PACZKI_DANYCH"

echo.
echo GOTOWE.
echo 1. Umiesc ZIP z danymi w folderze IMPORTUJ_TUTAJ.
echo 2. Uruchom IMPORTUJ_DANE_Z_ZIP.bat.
echo 3. Uruchom URUCHOM_STRONE.bat.
echo.
pause
exit /b 0

:frontend_error
popd
:error
echo.
echo Instalacja nie powiodla sie. Przeczytaj komunikat powyzej.
pause
exit /b 1
