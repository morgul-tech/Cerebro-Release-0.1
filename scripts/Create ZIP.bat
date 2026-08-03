@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py cerebro_tool.py zip
) else (
  python cerebro_tool.py zip
)
echo.
pause
endlocal
