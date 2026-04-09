@echo off
chcp 65001 >nul
echo ========================================
echo   检察侦查画像系统 - 前后端分离版本
echo ========================================
echo.
echo 正在启动 FastAPI 服务器...
echo.
echo 服务地址: http://localhost:8001
echo 按 Ctrl+C 停止服务器
echo.
echo ========================================
echo.

python server.py

pause
