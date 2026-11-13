# NInfer 27B 部署

**项目**：[`CSUNX233/Sparkle-Qwen27b-Kvmem-ninfer`](https://github.com/CSUNX233/Sparkle-Qwen27b-Kvmem-ninfer)
**模型**：Qwen3.8-27B 稠密，IQ3_XXS 量化（10.06GB）
**实测**：122 t/s（RTX 5080 16GB）

---

## 它解决什么问题

27B 稠密模型每个 token 都要算全部 27B 参数，权重必须整体驻留显存。16GB 卡上只能靠激进量化（3bit）压到 10GB。

但长对话会撑爆 KV 缓存。这个项目用 **KVMem 分层**解决：热的 KV 在显存，冷的放内存，按需调回。

配套三个组件：

| 组件 | 端口 | 作用 |
|---|---|---|
| 引擎 `ninfer-serve.exe` | 1234 | OpenAI 兼容 API，1.3GB 单体 exe |
| 缓存守卫 | 1236 | 前缀缓存复用，省重复预填充（**推荐接这个**） |
| dsh 网页 | 3080 | Agent 界面，带登录 token |

---

## 前置条件

| 项目 | 要求 |
|---|---|
| 显卡 | RTX 50 系（引擎是 sm_120a 专属编译；30/40 系需自行编译） |
| 显存 | ≥ 12GB（16GB 最舒服） |
| 内存 | ≥ 32GB |
| Node.js | **≥ 24**（24.9.0 实测可用） |
| Python | 3.11（只用于模型转换） |
| 磁盘 | 引擎 2GB + 模型 10GB（DLL 另算 650MB） |

---

## 步骤

### 1. 拿源码（别用 git clone）

```bash
cd D:\AI
# 国内 git clone 容易卡在代理上，用 tarball
curl -L --noproxy '*' -o src.tar.gz \
  "https://codeload.github.com/CSUNX233/Sparkle-Qwen27b-Kvmem-ninfer/tar.gz/refs/heads/main"
mkdir ninfer-local && tar -xzf src.tar.gz -C ninfer-local --strip-components=1
```

### 2. 装 Node 24（便携版，不动系统）

```bash
curl -L --noproxy '*' -o node24.zip \
  "https://registry.npmmirror.com/-/binary/node/v24.9.0/node-v24.9.0-win-x64.zip"
unzip -q node24.zip -d D:\AI\node24
cp -r D:\AI\node24\node-v24.9.0-win-x64\* D:\AI\ninfer-local\runtime\node\
```

### 3. 预下依赖（避开 setup 的慢下载）

`config/downloads.json` 需要三个归档，全部预下好放进 `runtime/cache/`，setup 就会跳过下载：

| 归档 | 大小 | 来源 |
|---|---|---|
| `ninfer-5070ti-win-x64-sm120a-v1.1.0.zip` | 807MB | GitHub Releases，**单线程**约 1MB/s |
| `libcublas-windows-x86_64-13.0.0.19-archive.zip` | 399MB | `developer.download.nvidia.com`，直连快 |
| `ffmpeg-N-...-lgpl-shared.zip` | 76MB | ⚠️ 见下方注意 |

```bash
# cuBLAS（注意路径是 windows-x86_64，不是 windows/x86_64）
curl -L --noproxy '*' -o cublas.zip \
  "https://developer.download.nvidia.com/compute/cuda/redist/libcublas/windows-x86_64/libcublas-windows-x86_64-13.0.0.19-archive.zip"
```

> ⚠️ **FFmpeg 那个版本已被上游删除**（404）。必须换成 FFmpeg **9.0** 并改 `downloads.json` 的哈希。
> 详细步骤见 [踩坑 #5](03-pitfalls.md#坑-5项目依赖的-ffmpeg-版本被上游删了)。

放好之后校验：
```bash
python -c "
import json, hashlib, os
d = json.load(open('config/downloads.json', encoding='utf-8'))
for a in d['archives']:
    p = os.path.join('runtime/cache', a['name'])
    ok = os.path.exists(p) and hashlib.sha256(open(p,'rb').read()).hexdigest() == a['sha256']
    print(('OK  ' if ok else 'FAIL'), a['name'])
"
```

### 4. 下模型（ModelScope 快 240 倍）

```bash
mkdir -p models && cd models
curl -L --noproxy '*' -C - \
  -o Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf \
  "https://modelscope.cn/api/v1/models/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/repo?Revision=master&FilePath=Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf"
# 9.73GB，实测 18 MB/s，6 分 50 秒
```

基础模型的元数据（23MB，不用下 50GB 权重）：

```bash
mkdir -p base-qwen3.8-27b && cd base-qwen3.8-27b
BASE="https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-27B/repo?Revision=master&FilePath="
for f in config.json chat_template.jinja generation_config.json merges.txt \
         tokenizer.json tokenizer_config.json vocab.json preprocessor_config.json \
         model.safetensors.index.json; do
  curl -sL --noproxy '*' -o "$f" "${BASE}${f}"
done
```

### 5. 转换模型（GGUF → .ninfer）

```bash
py -3.11 -m venv .venv-convert
.venv-convert\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-convert\Scripts\python.exe -m pip install numpy safetensors gguf huggingface_hub \
  -i https://pypi.tuna.tsinghua.edu.cn/simple

cd engine
..\.venv-convert\Scripts\python.exe -m tools.convert ^
  --model ..\models\base-qwen3.8-27b ^
  --recipe qwen3_8_27b_gguf ^
  --source gguf=..\models\Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf ^
  --components text,mtp ^
  --resource chat_template.jinja=..\templates\chat_template_qwen3.8-enhanced.jinja ^
  --proposal --name qwen3.8-27b-gsq-rco-iq3-xxs --device cpu ^
  --out ..\models\qwen3.8-27b-gsq-rco-iq3-xxs.ninfer
```

耗时约 4 分钟，产出 **10,796,652,288 字节**（10.06GB）。官方记录是 10,796,660,224，差 7KB 属正常元数据差异。

### 6. 装引擎

```powershell
cd D:\AI\ninfer-local
$env:NPM_CONFIG_REGISTRY = "https://registry.npmmirror.com"
.\setup.ps1 -ModelPath "D:\AI\ninfer-local\models\qwen3.8-27b-gsq-rco-iq3-xxs.ninfer"
```

setup 会：校验三个归档 → 解压到 `runtime/engine/` → npm 装 dsh（584+117 包）→ 写 `config/local.json`。

### 7. 启动

```powershell
.\start.cmd              # 完整（引擎 + 守卫 + 网页）
.\start.ps1 -EngineOnly  # 只要 API
```

**⚠️ 这一步会踩符号链接的坑**：dsh 需要真 symlink，普通权限建不了。见 [踩坑 #7](03-pitfalls.md#坑-7windows-普通权限建不了符号链接ninfer-的致命坑)。

---

## 生成的配置

`config/local.json` 关键项：

```json
{
  "MaxContext": 262144,
  "DeviceKV": 36864,
  "HostKVMiB": 7168,
  "KVDType": "rk4v4",
  "RecentTokens": 19456,
  "SinkTokens": 12288,
  "RetrieveTokens": 3840,
  "ReasoningEffort": "xhigh"
}
```

| 项 | 含义 |
|---|---|
| `DeviceKV` | 显存里的 KV 页数（16GB 卡 36864 已吃满） |
| `HostKVMiB` | 内存里的冷 KV（7GB） |
| `RecentTokens` / `SinkTokens` / `RetrieveTokens` | 分层策略：最近 / 开头 / 检索回来的 |

---

## 实测

```
权重加载   62 秒（9.71 GiB，159 MiB/s）
首启总耗时 1 分 48 秒（含 CUDA Graph 捕获）
短问题     69 t/s
代码生成   122 t/s
显存       14,704 / 16,303 MiB
内存       31 / 47 GB
```

启动日志里有一条值得注意的警告：

```
WARN CUDA graphs used 3.05 GiB but the KV sizing allowed 64.0 MiB;
leave more room with --kv-headroom-mib or --cuda-graph-allowance-mib
```

CUDA Graph 实际吃了 3GB，但预算只算了 64MB。当前余量够用，长上下文 OOM 时按这个顺序调：
1. `--cuda-graph-allowance-mib` 从 64 调到 3072
2. `DeviceKV` 降到 34816 或 32768
3. **不要**关掉 7GB 的 HostKV（那是长历史的核心）

---

## 已知限制（作者自述）

- 256K 上下文**未完成验收**，实际压缩阈值约 184K
- 多图 + 压缩会话有 `scatter` 未修 bug，遇到就开新会话
- 搜索需要联网，站点改版会失败
- 三比特量化的固有局限：长文写作容易重复，适合短任务和代码片段
