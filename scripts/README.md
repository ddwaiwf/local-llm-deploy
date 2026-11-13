# 脚本说明

这些是从实际部署里抽出来的可复用脚本。

> ⚠️ **`.cmd` 文件是 GBK 编码 + CRLF**。这是故意的——Windows `cmd.exe` 默认代码页 936，
> UTF-8 编码的中文提示会变成乱码。GitHub 网页预览可能显示乱码，**下载到本地直接用是正常的**。
> `.gitattributes` 里标记了 `*.cmd binary`，防止 Git 转换换行符。

---

## 启动/停止（Windows）

| 文件 | 作用 |
|---|---|
| `start-ninfer.cmd` | 启动 NInfer 27B（自动停掉 Strata），等 **3080 就绪**后开网页 |
| `open-ninfer-web.cmd` | 用**当前最新 token** 打开 dsh 网页（token 每次重启会变，随时双击它） |
| `make-dsh-shortcuts.py` | 生成/修正上面两个脚本（负责 GBK + CRLF 编码） |
| `start-strata.cmd` | 启动 Strata 125B（自动停掉 NInfer），等就绪后开测试台 |
| `stop-all.cmd` | 全部停止，并显示释放后的显存 |
| `fix-ninfer-links.cmd` | 修复 dsh 网页的模块回退链接，**不需要管理员**，双击一次即可（调用 `fix-dsh-links.js`，批量建 488 个 junction） |
| `connect-studyhub.py` | 把「学习助手」的 AI 答疑切到 NInfer / Strata / 还原云端，见下 |

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

7. **dsh 网页的 token 每次重启都会变**。`@deepseek-ai/dsh-client-connection` 每次 activation
   生成新的 secret（`randomBytes`），旧 token 和旧 cookie 立刻失效；不带 token 访问 3080
   只返回一行 `dsh web authentication required; reopen the URL printed by dsh web.`，
   界面里什么都没有。因此：
   - 启动脚本必须**等 3080 真正 LISTENING** 再去读 `dsh.stdout.log`。
     只等 1234（引擎）会读到上一次启动的旧 token —— 引擎比 dsh 起得快。
   - 脚本里打印的必须是**完整带 token 的地址**，不能只打印 `http://127.0.0.1:3080`。
   - 单独留一个 `open-ninfer-web.cmd`，任何时候双击都用当前最新 token 打开。
   - 别把带 token 的地址存成书签，重启就失效；cookie 有效期内裸地址能进，但换浏览器就废。

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

## 客户端接入：connect-studyhub.py

把「学习助手」的 AI 答疑后端切到本地模型。改的是
`C:\Users\<你>\AppData\Roaming\学习助手\studyhub-data.json` 里的 `ai` 段。

```bash
python connect-studyhub.py ninfer            # NInfer 27B（1236）
python connect-studyhub.py strata            # Strata 125B（8080）
python connect-studyhub.py --restore         # 还原最近一次备份
python connect-studyhub.py ninfer --fix-ping # 顺带修「测试连接」假阴性
```

三个要点：

1. **`ai.mode` 必须是 `direct`**。`workbuddy` 模式走任务队列，不读 `baseUrl`，
   界面看着配好了其实一个字节都没发到本地服务。
2. **每次自动备份**，文件名带时间戳，留在本地不入库；脚本不含任何真实 API Key，
   打印配置变更时对 Key 脱敏。
3. **`--fix-ping` 是等长原地补丁**：把 `lib/ai.js::ping()` 的 `max_tokens: 16`
   改成 `512`，靠 `headers()` 里省一个空格抵消多出的 1 字节，asar 总长和所有文件
   `offset/size` 都不变，**不用重打包**。改前备份 `app.asar`，且要求目标文本在包内
   唯一、改完反向还原逐字节一致，否则直接跳过不改。

换机器改脚本顶部的 `DATA` / `ASAR` 常量，以及 `TARGETS` 里的端口和模型 ID。
中文路径由 Python 自己读写没问题；命令行参数保持英文，避开外部 exe 的 ANSI argv 坑。

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
