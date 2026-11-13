@echo off
setlocal enabledelayedexpansion
title NInfer 27B - 本地 Agent
color 0A

echo.
echo  ============================================================
echo    NInfer 27B   稠密模型，约 122 tokens/s
echo  ============================================================
echo.
echo    需要显存约 14.7 GB    /    需要内存约 31 GB
echo.

netstat -an | findstr ":1234" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo  服务已在运行，跳过启动，直接打开网页。
  goto openweb
)

powershell -NoProfile -Command "if (Test-Path -LiteralPath 'D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai\dsh\package.json') { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ------------------------------------------------------------
  echo   启动前需要先做一次性修复。
  echo.
  echo   请先双击桌面上这个文件：
  echo     修复 NInfer 启动（需管理员运行一次）.cmd
  echo.
  echo   右键它 - 选择「以管理员身份运行」，只需一次。
  echo   之后本文件就能正常双击启动了。
  echo  ------------------------------------------------------------
  echo.
  pause
  exit /b 1
)

echo  ============================================================
echo  [1/3] 先停掉 Strata 125B，腾出显存...
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'StrataServe','StrataTestBench' -ErrorAction SilentlyContinue; Get-Process -Name strata,python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like 'D:\AI\Strata*' } | Stop-Process -Force" >nul 2>&1
echo        完成。

echo  [2/3] 启动 NInfer 服务...
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'NInferAll'" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  错误：无法启动计划任务 NInferAll
  echo  备选：双击 D:\AI\start-all.cmd
  echo.
  pause
  exit /b 1
)
echo        完成。

echo  [3/3] 等待引擎加载（通常 110 秒）...
set /a n=0
:wait
ping -n 4 127.0.0.1 >nul 2>&1
netstat -an | findstr ":1234" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  set /a n+=1
  if !n! geq 45 (
    echo.
    echo  超时（3 分钟）。请查看日志：
    echo    D:\AI\ninfer-local\runtime\logs\engine.stderr.log
    echo.
    pause
    exit /b 1
  )
  echo        加载中  !n!/45
  goto wait
)

:openweb
echo.
echo  ============================================================
echo    就绪
echo  ============================================================
echo    网页界面    http://127.0.0.1:3080
echo    接口 API    http://127.0.0.1:1234/v1
echo    缓存网关    http://127.0.0.1:1236/v1
echo.
echo    模型：qwen3.8-27b-gsq-rco-iq3-xxs
echo  ============================================================
echo.

set "DSHURL="
for /f "tokens=2" %%i in ('findstr /c:"dsh web: http" "D:\AI\ninfer-local\runtime\logs\dsh.stdout.log" 2^>nul') do set "DSHURL=%%i"
if defined DSHURL (
  echo  正在打开网页界面...
  start "" "!DSHURL!"
) else (
  echo  没找到登录链接。请打开这个文件复制地址：
  echo    D:\AI\ninfer-local\runtime\logs\dsh.stdout.log
)

echo.
echo  本窗口 15 秒后自动关闭，服务继续在后台运行。
echo  停止服务请双击「停止所有模型.cmd」
echo.
ping -n 16 127.0.0.1 >nul 2>&1
exit /b 0
