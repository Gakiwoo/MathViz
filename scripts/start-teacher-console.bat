@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Math-To-Manim Teacher Console (M2M2)
echo ============================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PS1_FILE=%SCRIPT_DIR%start-teacher-console.ps1"

if not exist "%PS1_FILE%" (
    echo [ERROR] File not found: %PS1_FILE%
    echo Please ensure the directory structure is intact.
    pause
    exit /b 1
)

REM Check for PowerShell
where powershell >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PowerShell is required but not found in PATH.
    echo Please install PowerShell: https://learn.microsoft.com/en-us/powershell/
    pause
    exit /b 1
)

echo Starting, please wait...
echo If nothing happens, check the terminal for prompts.
echo.

REM Switch to UTF-8 (chcp 65001) before calling PowerShell so that
REM Chinese characters in path survive the command-line handoff.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%PS1_FILE:\=\\%' %*"
set "EXIT_CODE=!ERRORLEVEL!"

if not "!EXIT_CODE!"=="0" (
    echo.
    echo [ERROR] Startup failed (exit code: !EXIT_CODE!^)
    echo Check the red error messages above.
) else (
    echo.
    echo Server stopped. You may close this window.
)

pause
endlocal
