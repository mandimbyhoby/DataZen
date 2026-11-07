@echo off
REM Lance le serveur de developpement DataZen dans cette fenetre.
REM Double-cliquez sur ce fichier, ou lancez-le depuis un terminal.
REM Les arguments sont transmis a start-dev.ps1 (-Port, -Sqlite, -Postgres, -NoBrowser).

setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" %*

if errorlevel 1 (
    echo.
    echo Le serveur s'est arrete avec une erreur.
    pause
)
endlocal
