@echo off
setlocal
chcp 65001 >nul
title Cerebro MCP

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [FAIL] Python was not found.
    pause
    exit /b 3
)

pushd "%~dp0"
%PYTHON_CMD% cerebro_tool.py mcp %*
set "RESULT=%errorlevel%"
popd

pause
endlocal & exit /b %RESULT%
