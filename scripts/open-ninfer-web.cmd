@echo off
setlocal enabledelayedexpansion
title 打开 NInfer 27B 网页
color 0A

echo.
echo  ============================================================
echo   打开 NInfer 27B 网页界面
echo  ============================================================
echo.

netstat -an | findstr ":3080" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  echo   网页服务 3080 还没启动。
  echo   请先双击「启动 NInfer 27B.cmd」，等出现「就绪」后再运行本文件。
  echo.
  pause
  exit /b 1
)

set "DSHURL="
for /f "tokens=2" %%i in ('findstr /c:"dsh web: http" "D:\AI\ninfer-local\runtime\logs\dsh.stdout.log" 2^>nul') do set "DSHURL=%%i"
if not defined DSHURL (
  echo   还没拿到登录地址（日志是空的）。
  echo   稍等 10 秒再双击本文件；仍不行就先跑「修复 NInfer 网页启动.cmd」。
  echo.
  pause
  exit /b 1
)

echo   完整地址（每次重启都会变，不要收藏这一条）：
echo   !DSHURL!
echo.
echo   正在打开浏览器...
start "" "!DSHURL!"
echo.
echo   若浏览器里只有一行英文 authentication required，
echo   说明地址过期了 —— 关掉窗口，重新双击本文件即可。
echo.
ping -n 12 127.0.0.1 >nul 2>&1
exit /b 0
