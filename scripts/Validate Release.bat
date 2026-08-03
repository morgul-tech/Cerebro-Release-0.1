@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py cerebro_tool.py validate
) else (
  python cerebro_tool.py validate
)
echo.
pause
endlocal
