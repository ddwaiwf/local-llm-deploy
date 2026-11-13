@echo off
setlocal
title 修复 NInfer 启动（需要管理员）
color 0E

echo.
echo  ============================================================
echo    修复 NInfer 的符号链接
echo  ============================================================
echo.
echo    原因：NInfer 的网页界面（dsh）需要一个真正的符号链接。
echo    普通 Windows 账户建不了，只有管理员权限或打开
echo    「开发者模式」才行。
echo.
echo    本文件只需以管理员身份运行一次，之后正常双击启动即可。
echo.

net session >nul 2>&1
if errorlevel 1 (
  echo  ------------------------------------------------------------
  echo   当前不是管理员权限。
  echo.
  echo   请：右键本文件 - 选择「以管理员身份运行」
  echo  ------------------------------------------------------------
  echo.
  pause
  exit /b 1
)

set "LINK=D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai\dsh"
set "TARGET=D:\AI\ninfer-local\integrations\dsh\node_modules\@deepseek-ai\dsh"

echo  [1/3] 检查目标路径...
if not exist "%TARGET%\package.json" (
  echo    错误：找不到 dsh 程序
  echo      %TARGET%
  pause
  exit /b 1
)
echo        正常。

echo  [2/3] 创建父目录...
powershell -NoProfile -Command "New-Item -ItemType Directory -Path 'D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai' -Force | Out-Null" >nul 2>&1
echo        正常。

echo  [3/3] 创建符号链接...
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%LINK%') { Remove-Item -LiteralPath '%LINK%' -Recurse -Force -ErrorAction SilentlyContinue }; New-Item -ItemType SymbolicLink -Path '%LINK%' -Target '%TARGET%' -ErrorAction Stop | Out-Null"
if errorlevel 1 (
  echo.
  echo    创建失败。
  echo    备选办法：打开「开发者模式」后重试
  echo      设置 - 系统 - 开发者选项 - 开发人员模式 = 开
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (Test-Path -LiteralPath '%LINK%\package.json') { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo    链接已建但读不到，请手动检查。
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo    修复完成
echo  ============================================================
echo    现在可以双击「启动 NInfer 27B.cmd」正常启动了。
echo  ============================================================
echo.
echo  12 秒后自动关闭。
ping -n 13 127.0.0.1 >nul 2>&1
exit /b 0
