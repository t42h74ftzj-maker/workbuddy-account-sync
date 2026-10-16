@echo off
chcp 65001 >nul
echo WorkBuddy account sync - quit WorkBuddy (tray icon too) first
pause
python "%~dp0account_sync.py" sync
echo exit code: %ERRORLEVEL%
pause
