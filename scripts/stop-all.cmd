@echo off
setlocal
title Stop all local models
color 0C

echo.
echo  ============================================================
echo    Stopping all local model services
echo  ============================================================
echo.

echo  [1/3] NInfer 27B...
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'NInferAll' -ErrorAction SilentlyContinue; Get-Process -Name ninfer-serve,node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like 'D:\AI\ninfer-local*' } | Stop-Process -Force" >nul 2>&1
echo        stopped.

echo  [2/3] Strata 125B...
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'StrataServe' -ErrorAction SilentlyContinue; Get-Process -Name strata,python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like 'D:\AI\Strata*' } | Stop-Process -Force" >nul 2>&1
echo        stopped.

echo  [3/3] Test bench...
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'StrataTestBench' -ErrorAction SilentlyContinue" >nul 2>&1
echo        stopped.

echo.
echo  ============================================================
ping -n 3 127.0.0.1 >nul 2>&1
echo    VRAM check:
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
echo  ============================================================
echo.
echo  Done. Both models are off.
echo  This window closes in 8 seconds.
ping -n 9 127.0.0.1 >nul 2>&1
exit /b 0
