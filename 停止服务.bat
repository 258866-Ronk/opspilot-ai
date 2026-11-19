@echo off
title Stop OpsPilot AI
echo Stopping backend on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  taskkill /PID %%a /F >nul 2>&1
  echo  Stopped PID %%a
)
echo Done.
timeout /t 3 >nul
