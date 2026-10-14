@echo off
setlocal
cd /d "%~dp0"

REM Prefer pythonw (no console window). Fall back to python if needed.
where pythonw >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" pythonw "%~dp0legacy\python\exifexit.py"
    exit /b 0
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" py -3w "%~dp0legacy\python\exifexit.py"
    exit /b 0
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" python "%~dp0legacy\python\exifexit.py"
    exit /b 0
)

echo.
echo EXIFexit could not start: Python was not found on PATH.
echo Install Python from https://www.python.org/ and tick "Add to PATH".
echo Then run:  pip install -r legacy\python\requirements.txt
echo.
pause
exit /b 1
