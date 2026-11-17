@echo off
chcp 65001 >nul
title AI CO2 MeOH Catalyst Project Workbench v1.1
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  start "" "http://localhost:8765/"
  py -m http.server 8765
) else (
  where python >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    start "" "http://localhost:8765/"
    python -m http.server 8765
  ) else (
    echo Python is not installed. Please double-click index.html to open in Edge/Chrome.
    pause
  )
)
