@echo off
setlocal
title 修复 NInfer 网页启动（不需要管理员）
color 0E

echo.
echo  ============================================================
echo    修复 NInfer 的模块链接
echo  ============================================================
echo.
echo    作用：NInfer 的网页界面（dsh）要从 dsh-home 目录加载
echo    240 个 @deepseek-ai 插件包。这些包实际在
echo    integrations\dsh\node_modules 里，中间需要一层链接。
echo.
echo    计划任务权限建不了这种链接，所以提前用你的账户建好。
echo    本文件不需要管理员，双击运行即可。
echo.

set "NODE=D:\AI\ninfer-local\runtime\node\node.exe"
set "FIXER=D:\AI\ninfer-local\scripts\fix-dsh-links.js"

if not exist "%NODE%" (
  echo    错误：找不到 Node
  echo      %NODE%
  pause
  exit /b 1
)
if not exist "%FIXER%" (
  echo    错误：找不到修复脚本
  echo      %FIXER%
  pause
  exit /b 1
)

echo  [1/2] 建立模块链接...
"%NODE%" "%FIXER%"
if errorlevel 1 (
  echo.
  echo    建立失败。请把上面的信息发给技术支持。
  pause
  exit /b 1
)

echo  [2/2] 验证...
set "CHK=D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai\cordis-plugin-timer\package.json"
if exist "%CHK%" (
  echo        正常。
) else (
  echo        链接建了但读不到，可能被杀毒软件拦了。
)

echo.
echo  ============================================================
echo    完成
echo  ============================================================
echo    现在双击「启动 NInfer 27B.cmd」就能打开网页了。
echo.
echo    注意：如果以后重装了 NInfer，需要再跑一次本文件。
echo  ============================================================
echo.
echo  12 秒后自动关闭。
ping -n 13 127.0.0.1 >nul 2>&1
exit /b 0
