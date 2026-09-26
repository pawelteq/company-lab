@echo off
chcp 65001 >nul
title Weryfikacja Firm Gemini AI - Company Lab
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto no_python
if not "%~1"=="" goto run_args

:menu
cls
echo ======================================================================
echo       AUTOMATYCZNA WERYFIKACJA FIRM PRZEZ GOOGLE GEMINI AI
echo ======================================================================
echo.
echo  [1] Start weryfikacji (standardowy pakiet 1500 firm, bezpieczne tempo)
echo  [2] Szybki test (sprawdz 10 firm)
echo  [3] Tylko firmy "Do sprawdzenia" (status: review, max 1500)
echo  [4] Tylko powiat poznanski (firmy z powiatu poznanskiego, max 1500)
echo  [5] Wpisz wlasna liczbe firm do sprawdzenia
echo  [6] Podglad kolejki firm (Dry-Run, bez wysylania zapytan do AI)
echo  [0] Wyjscie
echo.
set /p "choice=Wybierz opcje [1-6, domyslnie 1 - nacisnij Enter]: "

if "%choice%"=="" set choice=1
if "%choice%"=="1" goto run_standard
if "%choice%"=="2" goto run_test
if "%choice%"=="3" goto run_review
if "%choice%"=="4" goto run_poznanski
if "%choice%"=="5" goto run_custom
if "%choice%"=="6" goto run_dry
if "%choice%"=="0" exit /b 0

echo Nieprawidlowy wybor. Sprobuj ponownie.
timeout /t 2 >nul
goto menu

:run_args
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini %*
goto finish

:run_standard
echo.
echo [INFO] Uruchamianie pelnej weryfikacji (limit do 1500 firm na dobe)...
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini --limit 1500
goto finish

:run_test
echo.
echo [INFO] Uruchamianie szybkiego testu (limit 10 firm)...
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini --limit 10
goto finish

:run_review
echo.
echo [INFO] Uruchamianie weryfikacji firm ze statusem "Do sprawdzenia" (review)...
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini --status review --limit 1500
goto finish

:run_poznanski
echo.
echo [INFO] Uruchamianie weryfikacji dla powiatu poznanskiego (max 1500 firm)...
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini --county poznanski --limit 1500
goto finish

:run_custom
echo.
set "custom_limit="
set /p "custom_limit=Podaj liczbe firm do weryfikacji (np. 50): "
if "%custom_limit%"=="" set custom_limit=50
echo [INFO] Uruchamianie weryfikacji dla %custom_limit% firm...
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini --limit %custom_limit%
goto finish

:run_dry
echo.
echo [INFO] Generowanie podgladu kolejki (Dry-Run)...
".venv\Scripts\python.exe" -m scripts.auto_verify_gemini --dry-run
goto finish

:no_python
echo.
echo [BLAD] Nie znaleziono srodowiska Python (.venv\Scripts\python.exe).
echo Upewnij sie, ze uruchamiasz skrypt w glownym folderze aplikacji.
echo.
pause
exit /b 1

:finish
echo.
echo ======================================================================
echo  Proces zakonczony. Wyniki zostaly zapisane w bazie danych SQLite.
echo ======================================================================
echo.
pause
if not "%~1"=="" exit /b 0
goto menu
