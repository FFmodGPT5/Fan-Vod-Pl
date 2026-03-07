@echo off
setlocal

rem === STALA SCIEZKA AWARYJNA DO REPO ===
set "REPO_FALLBACK=C:\github pliki"

rem === WYKRYWANIE REPO ===
if exist "%CD%\.git" (
    set "REPO=%CD%"
) else if exist "%~dp0\.git" (
    set "REPO=%~dp0"
) else (
    set "REPO=%REPO_FALLBACK%"
)

echo.
echo Repo: %REPO%
echo.

git -C "%REPO%" add -A
if errorlevel 1 goto :err

git -C "%REPO%" commit -m "update"
if errorlevel 1 goto :err

git -C "%REPO%" push origin main
if errorlevel 1 goto :err

echo.
echo GOTOWE - aktualizacja wyslana na GitHub.
pause
exit /b 0

:err
echo.
echo BLAD - sprawdz czy:
echo 1. Git jest zainstalowany
echo 2. Folder repo istnieje
echo 3. Repo ma poprawnie ustawione origin
echo 4. Masz zmiany do commit
pause
exit /b 1
