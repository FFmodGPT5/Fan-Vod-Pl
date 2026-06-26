@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aktualizacja_repo_z_zipow_v2.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo [BLAD] Aktualizacja nie zostala zakonczona.
  pause
  exit /b %RC%
)
echo [OK] Wszystko zakonczone.
pause
exit /b 0
