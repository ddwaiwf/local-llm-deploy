@echo off
setlocal enabledelayedexpansion
title Strata 125B - MoE
color 0B

echo.
echo  ============================================================
echo    Strata 125B   -   MoE 125B, about 93 tokens/s
echo  ============================================================
echo.
echo    VRAM about 15.4 GB   /   RAM about 40 GB
echo    Context 32768 tokens
echo.

netstat -an | findstr ":8080" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo  Already running - skipping the start, opening the test bench.
  goto openweb
)

echo  ============================================================
echo  [1/3] Stopping NInfer 27B to free VRAM and RAM...
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'NInferAll' -ErrorAction SilentlyContinue; Get-Process -Name ninfer-serve,node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like 'D:\AI\ninfer-local*' } | Stop-Process -Force" >nul 2>&1
echo        done.

echo  [2/3] Starting Strata plus the test bench...
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'StrataServe'" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ERROR: could not start the task "StrataServe".
  echo  Fallback: double-click D:\AI\strata-launch-final.cmd
  echo.
  pause
  exit /b 1
)
ping -n 3 127.0.0.1 >nul 2>&1
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'StrataTestBench'" >nul 2>&1
echo        started.

echo  [3/3] Waiting for the model (usually 45 to 90 seconds)...
set /a n=0
:wait
ping -n 4 127.0.0.1 >nul 2>&1
netstat -an | findstr ":8080" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  set /a n+=1
  if !n! geq 45 (
    echo.
    echo  TIMEOUT after 3 minutes.
    echo  Check: C:\Users\123\AppData\Local\Strata\launch\iq2_xs-32k.engine.log
    echo.
    pause
    exit /b 1
  )
  echo        ... loading  !n!/45
  goto wait
)

:openweb
echo.
echo  ============================================================
echo    READY
echo  ============================================================
echo    Test bench  http://127.0.0.1:8899      chat in a browser
echo    API         http://127.0.0.1:8080/v1   OpenAI style
echo    Anthropic   http://127.0.0.1:8080      no /v1, for Claude Code
echo.
echo    Model : qwen3.8-flash-next-iq2_xs
echo  ============================================================
echo.

echo  Opening the test bench...
start "" "http://127.0.0.1:8899/"

echo.
echo  This window closes in 15 seconds. Services keep running.
echo  To stop: double-click  "Stop all models.cmd"
echo.
ping -n 16 127.0.0.1 >nul 2>&1
exit /b 0
