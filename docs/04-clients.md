# 客户端接入

两个引擎都提供 **OpenAI 兼容 API**，所以任何支持"自定义 OpenAI 端点"的客户端都能接。

---

## 先记住两个地址

| 引擎 | OpenAI 端点 | 模型 ID |
|---|---|---|
| NInfer 27B | `http://127.0.0.1:1236/v1`（缓存守卫，推荐）<br>`http://127.0.0.1:1234/v1`（直连引擎） | `qwen3.8-27b-gsq-rco-iq3-xxs` |
| Strata 125B | `http://127.0.0.1:8080/v1` | `qwen3.8-flash-next-iq2_xs` |

**API Key**：本地服务不校验，随便填（比如 `local` 或 `sk-local`）。

> NInfer 优先接 **1236**，那是缓存守卫，会复用前缀缓存，多轮对话明显更快。

---

## 学习助手（支持 ✅）

`study-hub` 内置了「**自定义（OpenAI 兼容）**」选项。

从 `app.asar` 里可以看到这个配置项：

```js
{ id: 'custom', name: '自定义（OpenAI 兼容）', baseUrl: '', models: [],
  hint: '任何兼容 /chat/completions 的服务' }
```

### 配置文件在哪（本机已接好）

`C:\Users\123\AppData\Roaming\学习助手\studyhub-data.json`，`ai` 段就是全部 AI 配置。
2026-11-13 已直接改好，接的是 **NInfer 27B**：

| 字段 | 现在的值 | 说明 |
|---|---|---|
| `providerId` | `custom` | 自定义（OpenAI 兼容） |
| `baseUrl` | `http://127.0.0.1:1236/v1` | NInfer 缓存守卫 |
| `apiKey` | `local` | 本地不校验 |
| `model` | `qwen3.8-27b-gsq-rco-iq3-xxs` | 以 `/v1/models` 为准 |
| `mode` | `direct` | **最关键，见下** |

`lib/ai.js::normalizeUrl()` 会把 `/v1` 自动补成 `/v1/chat/completions`；
填完整的 `/chat/completions` 也能识别。

### 最大的坑：`mode` 不是 `direct` 就不走本地

`ai.mode` 只有两个值：

- `direct` —— 直连上面配的 `baseUrl`，**接本地模型必须用这个**
- `workbuddy` —— 把问题写成任务单据交给 WorkBuddy 队列，压根不读 `baseUrl`

本机原配置就是 `workbuddy`。界面上 Base URL、模型名看着都填好了，实际一个字节
都没发到本地服务。改配置时务必把 `mode` 一起改成 `direct`。

### 一键切换脚本

`scripts/connect-studyhub.py` 把五个字段、备份、还原都封装好了：

```bash
cd D:\AI\local-llm-deploy\scripts
python connect-studyhub.py ninfer            # NInfer 27B（1236）
python connect-studyhub.py strata            # Strata 125B（8080）
python connect-studyhub.py --restore         # 还原成原来的云端 DeepSeek
python connect-studyhub.py ninfer --fix-ping # 顺带修「测试连接」
```

- 每次自动备份 `studyhub-data.json.bak-<时间>-localmodel`（留在本地，不入库）
- 脚本不含任何真实 API Key；还原靠备份，打印配置时对 Key 脱敏
- 学习助手没开就直接打开；已开着会由 `onDataChanged` 自动重载磁盘改动

### 界面里怎么填（等价于上面的脚本）

1. 打开学习助手 → 设置 / AI 配置
2. 提供商选「**自定义（OpenAI 兼容）**」
3. 填三个字段：

| 字段 | 填什么 |
|---|---|
| Base URL | `http://127.0.0.1:8080/v1`（Strata）<br>或 `http://127.0.0.1:1236/v1`（NInfer） |
| API Key | `local`（随便填，本地不校验） |
| 模型 | `qwen3.8-flash-next-iq2_xs`<br>或 `qwen3.8-27b-gsq-rco-iq3-xxs` |

4. 对话模式选「**直连模型**」，不要选「用 WorkBuddy 跑」
5. 保存后先问一句"你好"确认连通

### 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 连接超时 | 服务没启动 | 先双击桌面启动脚本，等到提示 READY |
| 404 | Base URL 少了 `/v1` | 补上（Anthropic 端点才不带 `/v1`） |
| 模型不存在 | 模型 ID 打错 | 访问 `http://127.0.0.1:8080/v1/models` 看准确 ID |
| 回答很慢 | 上下文填太大 | 关掉其他吃显存的程序 |

### 第二个坑：「测试连接」假阴性

`lib/ai.js::ping()` 只给 `max_tokens: 16` 且非流式。NInfer / Strata 都是思考型模型，
16 个 token 全花在 `reasoning_content` 上，`message.content` 返回空串，按钮显示
「(空回复)」——其实连接是通的。改之前的实测：

```json
{"message":{"content":"","reasoning_content":"We need to respond..."},"finish_reason":"length"}
```

`chatStream()` 里也明确写了 `d.content || (d.reasoning_content ? '' : '')`，思考过程会被
丢弃但正文照常显示，正常问答不受影响（学习助手给 4096 token）。

已用**等长原地补丁**把 `16` 改成 `512`：从 `headers()` 里省掉一个可有可无的空格，
抵掉多出来的 1 字节，asar 总长与所有文件 `offset/size` 都不变，**不用重打包**。
补丁后实测 `content = "正常"`。备份是 `app.asar.bak-<时间>-localmodel`。
验证：反向还原后与原版逐字节一致；两版 JS 语法检查都通过。

> 不改程序也行：直接在学习助手里发一句真问题，比点「测试连接」更准。

### 两个模型交替用时注意

**先切服务再切配置**。Strata 和 NInfer 不能同时跑，切换顺序：

```
1. 双击「启动 NInfer 27B.cmd」（会自动停掉 Strata）
2. 等 READY
3. 到学习助手里改 Base URL 和模型 ID
```

---

## WorkBuddy（支持 ✅ —— 这里之前写错过）

早先只翻了 `~/.workbuddy/settings.json` 就下结论，没看程序本体，错误地写成「不支持」。
实际上 `app.asar` 里有完整的本地模型子系统，三条路都能走：

| 路线 | 证据 | 说明 |
|---|---|---|
| 内置本地模型 | `~/.workbuddy/local-models/state.json` | 已下载且 `enabled: true`，自带 `llama-server.exe`（CUDA-13） |
| Ollama provider | `settings.models.providers.ollama` = 「Ollama 本地」 | 默认 `localhost:11434` |
| Custom provider | `settings.models.providers.custom` = 「自定义」 | 提供商一项写着「仅支持 OpenAI 兼容协议 API」 |

内置模型读 GGUF 头确认是 `qwen35moe`，`Qwen36_35B A3B REAP ...`，41 层，
`local_model.gguf` 15.79GB + `local_model.mmproj.gguf` 861MB（可看图）。
`~/.workbuddy/models.json` 里已经有这一条：

```json
{
  "id": "local_model", "name": "本地模型", "local": true,
  "url": "http://127.0.0.1:52741/v1/chat/completions",
  "maxInputTokens": 131072, "maxOutputTokens": 8192,
  "supportsToolCall": true, "supportsImages": true, "supportsReasoning": true
}
```

设置 → 模型里还有「添加模型 / 测试连接 / 本地模型管理（下载、切换、显存与内存要求）」。

### 用 Custom 接 NInfer / Strata

表单字段是从 `buildEmptyModelFormState()` 解出来的，界面文案：「供应商（仅支持 OpenAI 兼容协议 API）」「接口地址」「模型名称」「API Key」「工具调用」。

| 字段 | 填什么 |
|---|---|
| 提供商 | 自定义 |
| 接口地址 | `http://127.0.0.1:1236/v1/chat/completions`（NInfer）<br>`http://127.0.0.1:8080/v1/chat/completions`（Strata） |
| 模型名称 | `qwen3.8-27b-gsq-rco-iq3-xxs` / `qwen3.8-flash-next-iq2_xs` |
| API Key | 留空也行（界面明写「本地部署无需 API Key」），填 `local` 更保险 |
| 工具调用 | 勾上，两个引擎都支持 |

**接口地址要填完整的 `/chat/completions`**，不是只填 `/v1`：内置模型在 `models.json`
里存的就是完整路径，界面占位符也是 `https://api.example.com/v1/chat/completions`。
填完点「测试连接」。

> 这条 Custom 路线本机还没实测连通，字段是从程序包里解出来的。若报 404，改成只填 `/v1` 再试。

### 三个本地模型抢显存

RTX 5080 只有 16GB。WorkBuddy 内置 35B（15.79GB）、NInfer 27B、Strata 125B
**只能同时跑一个**。要用 WorkBuddy 内置模型，先双击桌面「停止所有模型.cmd」
把 NInfer / Strata 停掉，否则会 OOM。

---

## Claude Code（支持 ✅）

Strata 官方支持，一条命令生成配置：

```powershell
D:\AI\Strata\bin\strata.cmd connect claude-code
```

它会打印需要设置的环境变量，大致是：

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8080"
$env:ANTHROPIC_AUTH_TOKEN = "local"
```

**注意**：Anthropic 端点末尾**不带 `/v1`**，这是和 OpenAI 格式的区别。

---

## OpenCode / Codex / 其他（支持 ✅）

```powershell
D:\AI\Strata\bin\strata.cmd connect opencode
D:\AI\Strata\bin\strata.cmd connect codex
```

官方还支持：`omp`、`pi`、`hermes`、`openclaw`。

这些工具能用上本地模型的实际意义：**代码不出本机，且零 token 成本**。

---

## 自建测试台（推荐先试这个）

官方 API 不返回 CORS 头，浏览器直接 fetch 会被拦。所以需要一个本地代理。

`scripts/proxy.py` + `scripts/index.html` 是一个开箱即用的方案：

```powershell
cd D:\AI\strata-test
"D:\AI\Strata\python\python.exe" proxy.py
# 打开 http://127.0.0.1:8899
```

功能：
- 聊天界面（流式输出，区分思考过程和正文）
- 实时性能：首 token 延迟、t/s、MTP 接受率、缓存命中
- 四个预设测试：代码 / 知识 / 推理 / 长文测速

代理本身只做三件事：提供页面、转发 `/v1/*`、补 CORS 头。不占显存。

---

## 用 curl 直接测

```bash
# 非流式
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-flash-next-iq2_xs","messages":[{"role":"user","content":"你好"}],"max_tokens":100}'

# 流式
curl -s -N http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-flash-next-iq2_xs","messages":[{"role":"user","content":"你好"}],"max_tokens":100,"stream":true}'
```

**留意返回里的 `timings` 字段**（Strata 特有，很有用）：

```json
"timings": {
  "cache_n": 48,                     // 前缀缓存命中
  "prompt_per_second": 52.9,         // 预填充速度
  "predicted_per_second": 80.4,      // 纯生成速度
  "draft_n": 6,
  "draft_n_accepted": 4              // MTP 草稿接受数
}
```

`predicted_per_second` 才是真实生成速度。端到端 t/s 会被首 token 延迟摊薄——短回答看起来会低很多。

---

## 看实时监控

```powershell
# Strata（TUI 面板，显示 GPU、缓存命中、每 token 延迟）
D:\AI\Strata\bin\strata.cmd monitor --url http://127.0.0.1:8080
```

NInfer 的日志：
```
D:\AI\ninfer-local\runtime\logs\engine.stderr.log
```

---

## 端口速查

| 端口 | 谁 |
|---|---|
| 1234 | NInfer 引擎直连 |
| 1236 | NInfer 缓存守卫（推荐） |
| 3080 | NInfer dsh 网页 |
| 8080 | Strata 引擎 |
| 8899 | 测试台代理 |
| 52741 | WorkBuddy 内置本地模型的 llama-server（仅在启用内置模型时出现） |

两个引擎不会同时占用——启动脚本会自动停掉另一个。
