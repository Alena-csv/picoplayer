@echo off
chcp 65001 >nul
rem PicoPlayer — запуск. Можно перетащить файлы или папку прямо на этот значок.
setlocal
set "APP_DIR=%~dp0"
set "PYTHONUTF8=1"

rem --- ищем Python ---
set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo.
    echo  Python не найден.
    echo  Скачайте его с https://www.python.org/downloads/
    echo  и при установке отметьте галочку "Add Python to PATH".
    echo.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)

rem --- при первом запуске ставим PySide6 ---
%PY% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Первый запуск: устанавливаю библиотеку PySide6 ^(нужен интернет, 1-3 минуты^)...
    echo.
    %PY% -m pip install --user --upgrade PySide6
    if errorlevel 1 (
        echo.
        echo  Не удалось установить PySide6. Проверьте интернет и попробуйте ещё раз.
        pause
        exit /b 1
    )
)

rem --- берём pythonw.exe именно из того же Python, где есть PySide6 ---
set "PYW="
for /f "usebackq delims=" %%I in (`%PY% -c "import os, sys; d = os.path.dirname(sys.executable); p = os.path.join(d, 'pythonw.exe'); print(p if os.path.isfile(p) else sys.executable)"`) do set "PYW=%%I"

if defined PYW (
    start "" "%PYW%" "%APP_DIR%picoplayer.py" %*
) else (
    start "" %PY% "%APP_DIR%picoplayer.py" %*
)
