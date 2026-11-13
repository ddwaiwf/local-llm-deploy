# -*- coding: utf-8 -*-
"""生成/修正 NInfer 网页入口脚本。

背景：dsh web 每次启动生成新的激活 secret，token 与浏览器 cookie 全都会失效；
旧启动脚本只等 1234（引擎）就去读 dsh.stdout.log，容易拿到上一条旧地址 -> 401。
这里做两件事：
  1. 新增桌面「打开 NInfer 网页.cmd」：随时读当前最新 token 并打开。
  2. 修「启动 NInfer 27B.cmd」：等 3080 真正监听后再读日志，并打印完整带 token 地址。

.cmd 必须 GBK + CRLF（中文 Windows 的 cmd.exe 默认代码页 936）。
"""
import os
import shutil

DESK = r"C:\Users\123\Desktop"
LOG = r"D:\AI\ninfer-local\runtime\logs\dsh.stdout.log"
READ_URL = r'''for /f "tokens=2" %%i in ('findstr /c:"dsh web: http" "''' + LOG + r'''" 2^>nul') do set "DSHURL=%%i"'''


def write_cmd(path, lines):
    text = "\r\n".join(lines) + "\r\n"
    with open(path, "wb") as f:
        f.write(text.encode("gbk"))
    print("written:", path, os.path.getsize(path), "bytes")


open_web = [
    "@echo off",
    "setlocal enabledelayedexpansion",
    "title 打开 NInfer 27B 网页",
    "color 0A",
    "",
    "echo.",
    "echo  ============================================================",
    "echo   打开 NInfer 27B 网页界面",
    "echo  ============================================================",
    "echo.",
    "",
    "netstat -an | findstr \":3080\" | findstr \"LISTENING\" >nul 2>&1",
    "if errorlevel 1 (",
    "  echo   网页服务 3080 还没启动。",
    "  echo   请先双击「启动 NInfer 27B.cmd」，等出现「就绪」后再运行本文件。",
    "  echo.",
    "  pause",
    "  exit /b 1",
    ")",
    "",
    "set \"DSHURL=\"",
    READ_URL,
    "if not defined DSHURL (",
    "  echo   还没拿到登录地址（日志是空的）。",
    "  echo   稍等 10 秒再双击本文件；仍不行就先跑「修复 NInfer 网页启动.cmd」。",
    "  echo.",
    "  pause",
    "  exit /b 1",
    ")",
    "",
    "echo   完整地址（每次重启都会变，不要收藏这一条）：",
    "echo   !DSHURL!",
    "echo.",
    "echo   正在打开浏览器...",
    "start \"\" \"!DSHURL!\"",
    "echo.",
    "echo   若浏览器里只有一行英文 authentication required，",
    "echo   说明地址过期了 —— 关掉窗口，重新双击本文件即可。",
    "echo.",
    "ping -n 12 127.0.0.1 >nul 2>&1",
    "exit /b 0",
]
write_cmd(os.path.join(DESK, "打开 NInfer 网页.cmd"), open_web)

start = os.path.join(DESK, "启动 NInfer 27B.cmd")
raw = open(start, "rb").read().decode("gbk")
shutil.copy2(start, start + ".bak-20261113")
lines = raw.replace("\r\n", "\n").split("\n")

out = []
wait_done = False
echo_done = False
for line in lines:
    if line.strip() == ":openweb" and not wait_done:
        out.append(line)
        # 等 3080 真正监听后再读日志，否则会拿到上一次启动的旧 token
        out += [
            "set /a w=0",
            ":waitweb",
            "netstat -an | findstr \":3080\" | findstr \"LISTENING\" >nul 2>&1",
            "if not errorlevel 1 goto webok",
            "set /a w+=1",
            "if !w! geq 40 goto webfail",
            "ping -n 3 127.0.0.1 >nul 2>&1",
            "goto waitweb",
            ":webfail",
            "echo.",
            "echo   网页服务 3080 一直没起来。",
            "echo   可双击「修复 NInfer 网页启动.cmd」后重试。",
            "echo.",
            "pause",
            "exit /b 1",
            ":webok",
            "echo       网页服务已就绪。",
        ]
        wait_done = True
        continue
    # 裸地址会 401，改成提示看下面那条完整地址
    if "http://127.0.0.1:3080" in line and line.lstrip().startswith("echo"):
        out.append("echo    网页地址    见下方完整地址")
        continue
    out.append(line)
    # 读到 DSHURL 之后立刻打印完整地址（此时 !DSHURL! 已赋值）
    if line.strip().startswith("for /f") and "dsh web: http" in line and not echo_done:
        out += [
            "echo.",
            "echo   完整网页地址（每次重启会变，请复制这一行）：",
            "echo   !DSHURL!",
            "echo.",
        ]
        echo_done = True

new = "\r\n".join(out)
if not new.endswith("\r\n"):
    new += "\r\n"
open(start, "wb").write(new.encode("gbk"))
print("patched:", start, "wait=", wait_done, "echo=", echo_done, os.path.getsize(start), "bytes")
