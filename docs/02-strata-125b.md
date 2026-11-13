# Strata 125B 部署

**项目**：[`Niko1221/Strata`](https://github.com/Niko1221/Strata)（43,609 star，MIT，C++）
**模型**：Qwen3.8-Flash-Next 125B MoE，IQ2_XS 量化（63.35GB）
**实测**：93.7 t/s（RTX 5080 16GB + 48GB RAM）

---

## 它解决什么问题

125B 模型按常规思路要 60GB+ 显存，消费级卡根本放不下。

MoE 架构给了另一条路：这个模型有 **24,576 个路由专家**，但**每个 token 只调用其中 10 个**（约 6B 参数）。

Strata 的分工：

| 硬件 | 负责什么 |
|---|---|
| **显存** | 注意力、路由器、共享专家、MTP 草稿层、KV 缓存，剩下的空间缓存热点专家 |
| **内存** | 全部 24,576 个专家的权重；显存没缓存的由 CPU 直接算（AVX-512/AVX2） |
| **SSD** | 26.8GB 的 n-gram 查找表，每个 token 只读少量行 |

**所以"12GB 跑 125B"的准确含义是整机协同**，不是把 125B 权重塞进显存。也**不能和 125B 稠密模型等同**——每 token 实际只算 6B。

---

## 内存是真正的门槛

这是最容易误判的地方。官方 MEMORY 对照表（`docs/MODELS.md`）：

| 你有的内存 | 能跑什么 |
|---|---|
| 32GB | 只能 Coder（每层 512 个专家砍到 256 个） |
| **48GB** | **Q2_0、IQ2_XS** |
| 64GB | 全部规格（IQ3_S 需基本不跑其他程序） |
| 96GB+ | IQ3_S、Unsloth UD-IQ4_XS |

规格对应的专家内存占用：

| 规格 | 专家占 RAM | 总占用（RAM+VRAM） | 质量 |
|---|---|---|---|
| Q2_0 | 34 GB | 37.6 GB | good，最快 |
| **IQ2_XS** | **35.5 GB** | **39.2 GB** | better，快 |
| IQ3_XXS | 43 GB | 47.0 GB | great，慢 |
| IQ3_S | 50 GB | 54.8 GB | best，最慢 |

**48GB 内存跑 IQ2_XS 是刚好卡在线上**：35.5GB 专家 + 约 10GB 系统开销 = 45.5GB。

---

## 步骤

### 1. 装 Terminal

```bash
cd D:\AI
curl -L --noproxy '*' -o strata-control.zip \
  "https://github.com/Niko1221/Strata/releases/download/v0.2.13/strata-control-0.1.59-windows-x86_64.zip"
unzip -q strata-control.zip -d D:\AI\Strata
```

自带 Python 3.12，不需要额外装环境。

### 2. 下引擎（gh-proxy 十路并行）

```bash
URL="https://gh-proxy.com/https://github.com/Niko1221/Strata/releases/download/v0.2.13/strata-engine-0.1.59-windows-x86_64-cuda-cuda13.tar.gz"
SZ=$(curl -sIL --max-time 40 "$URL" | tr -d '\r' | grep -i "content-length: [0-9]" | tail -1 | sed 's/.*: //')
PARTS=10
CHUNK=$(( (SZ + PARTS - 1) / PARTS ))
for i in $(seq 0 $((PARTS-1))); do
  s=$((i*CHUNK)); e=$((s+CHUNK-1)); [ "$e" -ge "$SZ" ] && e=$((SZ-1))
  curl -sL --max-time 2400 --retry 5 -r ${s}-${e} -o "part${i}" "$URL" &
done
wait
cat part* > engine.tar.gz && rm -f part*
```

**实测**：631MB，单线程 213 KB/s（要 49 分钟），十路并行 **5.7 MB/s（2 分钟）**。

选对包：RTX 50 系 → `cuda13`；驱动要 ≥ 580.65。

### 3. 装引擎

官方命令（离线、带 ed25519 签名校验）：

```powershell
.\python\python.exe strata.py components install-file "D:\AI\eng\engine.tar.gz"
```

**但这个命令会失败**：
```
Test-starting engine 0.1.59 windows-x86_64-cuda-cuda13 before switching to it
（然后就没了）
```

原因：`default_test_start` 需要一个已安装的模型做一 token 生成探针，没有模型就抛
`TestStartFailed("no installed model to test with")`。

**绕过**：手动按官方目录结构放。目录名规则是 `{version}-{platform}-{backend}-{variant}`：

```bash
DST="$LOCALAPPDATA/Strata/components/engine/0.1.59-windows-x86_64-cuda-cuda13"
mkdir -p "$DST"
cd D:\AI\eng && tar -xzf engine.tar.gz
cp BUILD.json cublas64_13.dll cublasLt64_13.dll engine-component.json \
   strata-vision.exe strata.exe strata_kq.dll "$DST/"
```

验证：
```powershell
.\python\python.exe strata.py components engine
# installed  0.1.59 windows-x86_64-cuda  C:\...\engine\0.1.59-windows-x86_64-cuda-cuda13
# engine     ...\strata.exe  (version 0.1.59)
```

### 4. 下模型（hf-mirror）

```bash
mkdir -p G:\Strata\models\IQ2_XS && cd G:\Strata\models\IQ2_XS
B="https://hf-mirror.com/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/resolve/main/IQ2_XS"
for f in Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00001-of-00002.gguf \
         Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00002-of-00002.gguf; do
  curl -L --noproxy '*' -C - -o "$f" "$B/$f" &
done
wait
```

**注意**：第一个分片 36.53GB（专家），第二个 26.82GB（查找表）。hf-mirror 实测 **40-48 MB/s**，25 分钟下完。

> 别用 ModelScope——它不支持 Range 请求，Strata 的工具会拒绝。

### 5. 装 MTP 草稿层（关键，决定速度）

自动下载会卡死在 `huggingface.co`。手动三步见 [踩坑 #12](03-pitfalls.md#坑-12mtp-草稿层自动下载会卡死必须手动三步)。

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
.\python\python.exe tools\mtp_fetch.py inventory --out G:\Strata\mtp
.\python\python.exe tools\mtp_fetch.py fetch --out G:\Strata\mtp
.\python\python.exe tools\mtp_fetch.py verify --out G:\Strata\mtp
.\python\python.exe tools\mtp_pack.py --src G:\Strata\mtp --experts q2_0 --out G:\Strata\mtp\mtp-q2_0.gguf
.\python\python.exe tools\mtp_rt.py --gguf G:\Strata\mtp\mtp-q2_0.gguf --out G:\Strata\mtp\rt
```

**判定就绪的标志**：`G:\Strata\mtp\rt\experts.bin` 存在（675MB）+ `dense.bin`（111MB）。

### 6. 启动

```powershell
$env:STRATA_DATA_DIR = "G:\Strata"
$env:HF_ENDPOINT = "https://hf-mirror.com"

.\python\python.exe strata.py launch `
  --model-path "G:\Strata\models\IQ2_XS" `
  --context 32k --kv q4_0 --vision off `
  --mtp on --drafting mtp --tune skip `
  --access local --port 8080 --yes --no-tui
```

| 参数 | 为什么这么设 |
|---|---|
| `--context 32k` | 128k 会 OOM（内存装不下 35.5GB 专家 + 大 KV） |
| `--kv q4_0` | KV 缓存减半，省出 7GB 内存 |
| `--vision off` | 省 0.9GB 下载 + 显存 |
| `--mtp on` | 速度翻倍的核心 |
| `--drafting mtp` | 用 MTP 而不是 DFlash2（后者要另下 1.2GB） |
| `--tune skip` | 跳过自动调参（省时间） |

首次启动会做一次性预处理（约 2 分钟），生成 `G:\Strata\packs\iq2_xs\`。

---

## 服务地址

| 用途 | 地址 |
|---|---|
| OpenAI 兼容 | `http://127.0.0.1:8080/v1` |
| Anthropic 兼容 | `http://127.0.0.1:8080`（末尾**不带** `/v1`，给 Claude Code 用） |
| 模型 ID | `qwen3.8-flash-next-iq2_xs` |
| 引擎日志 | `%LOCALAPPDATA%\Strata\launch\iq2_xs-32k.engine.log` |

---

## 实测

```
模型加载     45 秒
首 token     417-590 ms
长输出       93.7 t/s（400 token）
引擎纯生成   80.2 t/s
MTP 接受率   73%（129/176）
显存         15,374 / 16,303 MiB（只剩 604MB）
内存         40.0 / 47.2 GB（kv q4_0 帮了大忙）
```

**为什么比官方 5070 12GB 的 79 t/s 还快**：16GB 显存能多缓存约 1,400 个专家
（6,379 slots vs 4,933），显存命中率 73.3%。

官方在 5070 12GB + 64GB 上：Q2_0 是 87.3-93.0 t/s，IQ3_S 是 52-53 t/s。

---

## 优化方向

| 想要 | 怎么做 |
|---|---|
| 更快 | 换 `--context 16k` 腾显存给专家缓存（每 GB 约多 700 个专家） |
| 更长上下文 | 加内存到 64GB，然后 `--context 128k` |
| 更好质量 | 加内存后换 IQ3_S（54.8GB 专家） |
| 不占显存 | `--vision cpu`（图片识别放 CPU，慢几秒但省 1.4GB） |

---

## 已知问题

- **多图和对话压缩同时用有 bug**：`scatter` 失败，作者未修
- **上下文实际上限**：逻辑 32768，但 dsh 类客户端压缩阈值更低
- **查找表占磁盘**：26.8GB 常驻，别删
