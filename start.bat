@echo off
chcp 65001 >nul
cd /d "%~dp0"
title B站优质视频案例检索工具
echo ============================================
echo   B站优质视频案例检索工具
echo   本机访问: http://127.0.0.1:8000
echo   关闭本窗口即停止服务
echo ============================================
echo.
start "" http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
