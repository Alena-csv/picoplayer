@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo  Python не найден. Сначала запустите «Запустить PicoPlayer.bat».
    pause
    exit /b 1
)
%PY% "%~dp0register_windows.py"
echo.
pause
