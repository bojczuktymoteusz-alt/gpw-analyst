@echo off
title GPW Analyst V2 Starter
echo ========================================
echo   Starting GPW Analyst V2...
echo ========================================

:: Check Environment First
echo Running Pre-start Diagnosis...
python check_env.py
echo.

:: Start Backend in a new window
echo Launching Backend server (FastAPI)...
start "GPW Backend" cmd /k "cd /d backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload || pause"

:: Start Frontend in a new window
echo Launching Frontend server (Vite)...
start "GPW Frontend" cmd /k "cd /d frontend && npm run dev -- --host || pause"

echo.
echo ========================================
echo   Done! Both servers are starting.
echo   - Local Access:    http://localhost:5173
echo.
echo   Check the new windows for any errors.
echo ========================================
pause
