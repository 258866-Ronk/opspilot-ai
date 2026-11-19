@echo off
title OpsPilot AI Launcher
cd /d "%~dp0"
echo.
echo  ============================================
echo   OpsPilot AI - Enterprise IT Ops Agent
echo  ============================================
echo.
echo  [1/2] Starting backend server in a new window...
start "OpsPilot AI Backend - KEEP OPEN" cmd /k ""%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo       Waiting 6s for the server to be ready...
timeout /t 6 /nobreak >nul
echo  [2/2] Opening web console in your browser...
start "" "%~dp0frontend\index.html"
echo.
echo  ============================================
echo   READY!
echo   Login : operator / 123456
echo   Stop  : close the "OpsPilot AI Backend" window
echo  ============================================
echo.
timeout /t 15 >nul
