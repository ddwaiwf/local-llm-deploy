# 脚本说明

这些是从实际部署里抽出来的可复用脚本。

> ⚠️ **`.cmd` 文件是 GBK 编码 + CRLF**。这是故意的——Windows `cmd.exe` 默认代码页 936，
> UTF-8 编码的中文提示会变成乱码。GitHub 网页预览可能显示乱码，**下载到本地直接用是正常的**。
> `.gitattributes` 里标记了 `*.cmd binary`，防止 Git 转换换行符。

---

## 启动/停止（Windows）

| 文件 | 作用 |
|---|---|
| `start-ninfer.cmd` | 启动 NInfer 27B（自动停掉 Strata），等就绪后开网页 |
| `start-strata.cmd` | 启动 Strata 125B（自动停掉 NInfer），等就绪后开测试台 |
| `stop-all.cmd` | 全部停止，并显示释放后的显存 |
| `fix-ninfer-symlink.cmd` | **需管理员运行一次**：修复 dsh 的符号链接 |

### 设计要点（改的时候别踩回去）

1. **不用 `schtasks.exe`** —— 某些环境在程序黑名单里。改用：
   ```cmd
   powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'NInferAll'"
   ```

2. **不用 `taskkill /f /im node.exe`** —— 会误杀机器上其他用 Node 的软件。改用按路径匹配：
   ```cmd
   powershell -NoProfile -Command "Get-Process node -EA SilentlyContinue | Where-Object { $_.Path -like 'D:\AI\ninfer-local*' } | Stop-Process -Force"
   ```

3. **两模型互斥** —— 显存和内存都不够同时跑，所以启动脚本第一步先停另一个。

4. **已运行就跳过** —— 检测端口，已在监听则直接开浏览器（二次双击秒开）。

5. **等待用 `ping -n` 不用 `timeout`** —— `timeout` 在重定向或非交互环境下会直接跳过。

6. **中文提示需要 GBK**：
   ```powershell
   [IO.File]::WriteAllText($path, $text, [Text.Encoding]::GetEncoding(936))
   ```

---

## 测试台

| 文件 | 作用 |
|---|---|
| `proxy.py` | 本地反向代理 + 静态页面服务（标准库，无依赖） |
| `index.html` | 聊天界面，流式输出 + 实时性能指标 |

### 为什么需要代理

两个引擎的 HTTP 服务都是裸 `BaseHTTP`，**不返回 CORS 头**。浏览器直接 `fetch` 会被拦：

```
Access to fetch at 'http://127.0.0.1:8080/v1/chat/completions' from origin
'http://127.0.0.1:8899' has been blocked by CORS policy
```

代理做三件事：
1. `GET /` 返回页面
2. `POST /v1/*` 转发到 8080
3. 补 `Access-Control-Allow-Origin: *`

同源之后就没有跨域问题了。

### 用

```powershell
# 改成你自己的 Python 路径（或任意 3.10+）
python proxy.py
# 打开 http://127.0.0.1:8899
```

改上游地址：编辑 `proxy.py` 顶部的 `UPSTREAM`。

### 流式转发的关键

SSE 必须边读边写，不能缓冲：

```python
if is_stream:
    self.send_header("Cache-Control", "no-cache")
    self.send_header("Connection", "close")
    self.end_headers()
    while True:
        line = resp.readline()
        if not line: break
        self.wfile.write(line)
        self.wfile.flush()      # ← 少了这行就变成"一次性吐完"
```

---

## 改成自己的路径

这些脚本默认装在：

```
D:\AI\ninfer-local      NInfer
D:\AI\Strata            Strata 程序
G:\Strata               Strata 数据（模型、MTP）
C:\Users\<你>\AppData\Local\Strata   引擎组件
```

换机器的话，全局替换这几处路径即可。注册计划任务时改 `-Execute` 指向的 `.cmd`：

```powershell
$act = New-ScheduledTaskAction -Execute "D:\AI\start-all.cmd" -WorkingDirectory "D:\AI\ninfer-local"
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$prin = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName "NInferAll" -Action $act -Settings $set -Principal $prin -Force
```

不要加 `-RunLevel Highest`（需要管理员，普通用户会报"拒绝访问"）。
