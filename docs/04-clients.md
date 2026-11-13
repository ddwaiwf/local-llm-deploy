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

### 配置步骤

1. 打开学习助手 → 设置 / AI 配置
2. 提供商选「**自定义（OpenAI 兼容）**」
3. 填三个字段：

| 字段 | 填什么 |
|---|---|
| Base URL | `http://127.0.0.1:8080/v1`（Strata）<br>或 `http://127.0.0.1:1236/v1`（NInfer） |
| API Key | `local`（随便填，本地不校验） |
| 模型 | `qwen3.8-flash-next-iq2_xs`<br>或 `qwen3.8-27b-gsq-rco-iq3-xxs` |

4. 保存后先问一句"你好"确认连通

### 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 连接超时 | 服务没启动 | 先双击桌面启动脚本，等到提示 READY |
| 404 | Base URL 少了 `/v1` | 补上（Anthropic 端点才不带 `/v1`） |
| 模型不存在 | 模型 ID 打错 | 访问 `http://127.0.0.1:8080/v1/models` 看准确 ID |
| 回答很慢 | 上下文填太大 | 关掉其他吃显存的程序 |

### 两个模型交替用时注意

**先切服务再切配置**。Strata 和 NInfer 不能同时跑，切换顺序：

```
1. 双击「启动 NInfer 27B.cmd」（会自动停掉 Strata）
2. 等 READY
3. 到学习助手里改 Base URL 和模型 ID
```

---

## WorkBuddy（不支持 ❌）

WorkBuddy 用的是官方云端模型，`settings.json` 里没有任何模型/API 端点配置项，**没有接本地模型的入口**。

它作为客户端的价值在这里：

- 可以**指挥它去操作**这两个本地服务（启动、停止、查日志、跑测试）
- 但**不能把本地模型当成它的推理后端**

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

两个引擎不会同时占用——启动脚本会自动停掉另一个。
