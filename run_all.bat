@echo off
chcp 65001 >nul
title 电机故障诊断系统 — 一键启动

echo ================================================
echo   电机智能故障诊断系统 — 流水线二 一键启动
echo ================================================
echo.

REM ============================================
REM 配置区（根据实际路径修改）
REM ============================================
set PROJECT_DIR=%~dp0
set EMQX_BIN=E:\BaiduNetdiskDownload\emqx-5.3.2-windows-amd64\bin

echo [0/4] 检查 EMQX 是否运行...
curl -s http://localhost:18083 >nul 2>&1
if %errorlevel% neq 0 (
    echo   正在启动 EMQX...
    start "EMQX Broker" /D "%EMQX_BIN%" cmd /c "emqx.cmd console"
    echo   等待 EMQX 启动 (15秒)...
    timeout /t 15 /nobreak >nul
) else (
    echo   EMQX 已在运行
)

echo.
echo [1/4] 启动 Flask API 服务...
start "Flask API" /D "%PROJECT_DIR%" cmd /c "venv\Scripts\python src\app.py --port 5000"
timeout /t 3 /nobreak >nul

echo [2/4] 启动 Consumer (推理引擎)...
start "Consumer" /D "%PROJECT_DIR%" cmd /c "venv\Scripts\python src\consumer.py"
timeout /t 3 /nobreak >nul

echo [3/4] 启动 Producer (数据模拟)...
start "Producer" /D "%PROJECT_DIR%" cmd /c "venv\Scripts\python src\producer.py --no-loop"

echo [4/4] 启动 Dashboard (大屏前端)...
start "Dashboard" /D "%PROJECT_DIR%\dashboard" cmd /c "npm run dev"

echo.
echo ================================================
echo   全部启动完成！
echo.
echo   浏览器打开 http://localhost:3000 查看大屏
echo.
echo   已启动的窗口:
echo     - EMQX Broker   (MQTT 消息中间件)
echo     - Flask API     (localhost:5000)
echo     - Consumer      (推理 + 存储)
echo     - Producer      (数据模拟发送)
echo     - Dashboard     (localhost:3000)
echo.
echo   关闭方式: 逐个关闭各窗口, 或直接关闭本窗口
echo ================================================
pause
