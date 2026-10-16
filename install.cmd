@echo off
chcp 65001 >nul
set SRC=%~dp0
if "%WORKBUDDY_CONFIG_DIR%"=="" (set DST=%USERPROFILE%\.workbuddy) else (set DST=%WORKBUDDY_CONFIG_DIR%)
if not exist "%DST%\skills" mkdir "%DST%\skills"
robocopy "%SRC%" "%DST%\skills\workbuddy-account-sync" /E /XD .git /NFL /NDL /NJH /NJS
echo.
echo installed to: %DST%\skills\workbuddy-account-sync
pause
