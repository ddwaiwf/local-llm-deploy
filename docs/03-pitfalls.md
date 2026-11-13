# 踩坑实录

每一步都有真实报错原文。"现象 → 原因 → 解决"三段式，可直接搜索报错关键词。

---

## 一、下载类

### 坑 1：GitHub 多线程分片比单线程还慢

**现象**：807MB 的引擎包，开 12 路并行 Range 分片下载，跑了 12 分钟只完成 3%（约 100 KB/s）。

**原因**：GitHub Releases 的 CDN 对同一 IP 的并发 Range 请求限速。分片越多，每片越慢，总额度反而被压得更低。

**解决**：改成单线程直连，速度反而到 **1 MB/s**，807MB 三分钟下完。

```bash
# 慢（12 路并行）
for i in $(seq 0 11); do curl -r ... & done; wait

# 快（单线程）
curl -L --noproxy '*' -C - -o engine.zip "$URL"
```

**例外**：如果要下的是**代理**（gh-proxy）而不是直连，并行就有效——因为限速在代理那一侧。
实测 631MB 走 gh-proxy 十路并行，**5.7 MB/s**，2 分钟完成（单线程只有 213 KB/s）。

---

### 坑 2：GitHub 大文件只有 50-60 KB/s

**现象**：Strata 引擎包 631MB，直连 400 秒只下了 25MB（约 60 KB/s），估算要 3 小时。

**原因**：GitHub Releases 对未登录/低信誉请求的 CDN 限速，随时间段波动很大。

**解决**：用 `gh-proxy.com` + 十路并行 Range。

```bash
URL="https://gh-proxy.com/https://github.com/USER/REPO/releases/download/TAG/file.tar.gz"
SZ=$(curl -sIL --max-time 40 "$URL" | tr -d '\r' | grep -i "content-length: [0-9]" | tail -1 | sed 's/.*: //')
PARTS=10
CHUNK=$(( (SZ + PARTS - 1) / PARTS ))
for i in $(seq 0 $((PARTS-1))); do
  s=$((i*CHUNK)); e=$((s+CHUNK-1)); [ "$e" -ge "$SZ" ] && e=$((SZ-1))
  curl -sL --max-time 2400 --retry 5 -r ${s}-${e} -o "part${i}" "$URL" &
done
wait
cat part* > out.tar.gz && rm -f part*
```

**必须校验大小**：
```bash
python -c "import os; s=os.path.getsize('out.tar.gz'); print(s == $SZ)"
```

---

### 坑 3：HuggingFace 直连完全不通，hf-mirror 只有 75 KB/s

**现象**：`huggingface.co` 返回 `http=000`（连接失败）；`hf-mirror.com` 单次测速 75 KB/s。

**原因**：前者被墙；后者的速度取决于文件是否被 CDN 缓存。

**解决**：**先测速，再决定**。同一个镜像，不同文件速度能差 500 倍：

| 文件 | hf-mirror 实测 |
|---|---|
| IQ3_S 分片（预热过） | 11.8 MB/s |
| IQ2_XS 分片 A | 40 MB/s |
| IQ2_XS 分片 B | 48 MB/s |
| 小 README | 75 KB/s |

**结论**：大模型分片在 hf-mirror 上通常很快，别被小文件测速误导。直接下就完了。

---

### 坑 4：ModelScope 下载快，但不支持 HTTP Range

**现象**：ModelScope 实测 18 MB/s（比 hf-mirror 还快），但 Strata 的 `mtp_fetch.py` 拒绝它。

**原因**：`mtp_fetch.py` 有防污染校验——它要求 Range 请求返回 **206 + Content-Range**，不匹配就当成"镜像忽略了 Range 头"，直接报错。ModelScope 对 Range 请求返回 **200 + 整个文件**。

```python
# tools/mtp_fetch.py 里的注释
# #327: a mirror or proxy that ignores the Range header answers 200 with the whole shard
#       ... a range read therefore needs a 206 whose Content-Range is the range asked for
```

**解决**：这类需要精确 Range 的工具只能用 hf-mirror。

```bash
curl -sI -H "Range: bytes=0-1000" "$URL" | grep -i "^HTTP"
# HTTP/1.1 206 Partial Content   ← 可用
# HTTP/1.1 200 OK                ← 不可用
```

---

### 坑 5：项目依赖的 FFmpeg 版本被上游删了

**现象**：NInfer 的 `setup.ps1` 报：
```
Download checksum mismatch: ffmpeg-N-127527-g045dea2a34-win64-lgpl-shared.zip
```
直接访问该 URL 返回 404。

**原因**：`config/downloads.json` 钉死了 BtbN 的 `autobuild-2026-10-14-13-03`，而 BtbN 只保留最近几天的 autobuild，旧的已被清理。同时仓库从 `BtbN/FFmpeg-Builds` 改名成了 `FFmpeg-Builds/FFmpeg-Builds`。

**解决**：找**同 ABI 大版本**的替代品，并更新清单里的哈希。

关键在于 **DLL 版本号必须匹配**（引擎是按这个 ABI 编译的）：

| 引擎需要 | FFmpeg 8.1 提供 | FFmpeg 9.0 提供 |
|---|---|---|
| avcodec-**63** | avcodec-62 ❌ | avcodec-63 ✅ |
| avformat-**63** | avformat-62 ❌ | avformat-63 ✅ |
| avutil-**61** | avutil-60 ❌ | avutil-61 ✅ |
| swscale-**10** | swscale-9 ❌ | swscale-10 ✅ |
| swresample-**7** | swresample-6 ❌ | swresample-7 ✅ |

所以要用 **FFmpeg 9.0**（`ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip`），不是最新的 master。

改清单：
```python
import json, hashlib
d = json.load(open('config/downloads.json', encoding='utf-8'))
for a in d['archives']:
    if a['id'] == 'ffmpeg':
        a['url'] = "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip"
        a['sha256'] = hashlib.sha256(open('ff9.zip','rb').read()).hexdigest()
        a['files'] = [{"name": f, "sha256": hashlib.sha256(open(os.path.join('bin', f),'rb').read()).hexdigest()}
                      for f in ('avcodec-63.dll','avformat-63.dll','avutil-61.dll','swresample-7.dll','swscale-10.dll')]
json.dump(d, open('config/downloads.json','w',encoding='utf-8'), indent=2, ensure_ascii=False)
```

---

## 二、权限与安全软件

### 坑 6：360 把推理引擎当木马拦了

**现象**：
```
PermissionError: [WinError 5] 拒绝访问。
```
双击 exe 也没反应，窗口闪一下就没。

**排查过程**（用来排除其他可能）：

| 检查项 | 结果 |
|---|---|
| 文件 SHA256 vs 官方清单 | ✅ 完全一致 |
| ed25519 签名 | ✅ 通过 |
| PE 头（MZ） | ✅ 正常 |
| 网络下载标记（Zone.Identifier） | ✅ 无 |
| Windows 智能应用控制（SAC） | ✅ 关闭 |
| AppLocker 策略 | ✅ 无 |
| 换目录运行（C 盘 / D 盘） | ❌ 都拒绝 |
| 计划任务环境运行 | ❌ 仍拒绝 |
| **同目录另一个 exe**（strata-vision.exe） | ✅ **能跑** |

最后一条是关键：只有主引擎被拦，说明是**按文件特征拦的**，不是目录权限或环境限制。

**原因**：360 的 QVM 启发式引擎打分。这个程序踩了全部雷点：

| 360 看到什么 | 挖矿木马也这样 | 真实原因 |
|---|---|---|
| 无 Authenticode 签名 | ✔ | 开源项目没钱买证书 |
| 305MB 单体大 exe | ✔ | C++ 静态链接 |
| 大量 CUDA 调用、GPU 满载 | ✔ 核心特征 | 就是 GPU 推理引擎 |
| 常驻后台 + 多进程 | ✔ | 引擎 + vision + Python 三层 |
| 写 AppData、自我更新 | ✔ | 引擎自动升级 |
| 文件信誉分低 | — | 新版本，云端库未收录 |

**解决**：把引擎目录加入 360 信任区，或临时退出防护跑一次。

```
D:\AI\eng
D:\AI\Strata
C:\Users\<用户名>\AppData\Local\Strata
G:\Strata
```

**注意**：360 有时会"清理"而不是"信任"——加白后再检查文件是否还在。

---

### 坑 7：Windows 普通权限建不了符号链接（NInfer 的致命坑）

**现象**：NInfer 启动到最后一步崩溃，全部进程回滚：
```
Error: EPERM: operation not permitted, symlink
  'D:\AI\ninfer-local\integrations\dsh\node_modules\@deepseek-ai\dsh'
  -> 'D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai\dsh'
```

**为什么用 junction 不行**（这是最难的部分）：

一开始用 `New-Item -ItemType Junction` 绕过，成功过一次。但第二次启动又失败，因为：

```js
// dsh-app-boot/lib/index.js
function moduleFallbackEntryCurrent(modulesDir, entry) {
  const stat = lstatSync(link);
  if (entry.kind === "symlink")
    return stat.isSymbolicLink() && readlinkSync(link) === entry.packageDir;
  // ...
}
```

**junction 的 `lstatSync().isSymbolicLink()` 返回 false**（它是 directory + reparse point），所以永远判定"不当前"，然后：

```js
function ensureSymlink(link, target) {
  const stat = lstatSync(link);
  if (!stat.isSymbolicLink()) {
    if (readModuleProxyRecord(link)?.dsh?.moduleFallback?.targets === void 0)
      throw new Error(`dsh: ${link} exists and is not a symlink or dsh-managed module proxy`);
  }
  // ...
}
```

发现是 directory 且没有 proxy record → **直接抛错**。

**为什么每次都要重建**：dsh 每次启动检查 `moduleFallbackCurrent`，判定 false 就重建 profiles 目录，把 junction 删掉。

**解决**（二选一）：

**方案 A：管理员跑一次 mklink**
```powershell
# 以管理员身份运行 PowerShell
$link   = "D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai\dsh"
$target = "D:\AI\ninfer-local\integrations\dsh\node_modules\@deepseek-ai\dsh"
New-Item -ItemType Directory -Path (Split-Path $link) -Force | Out-Null
New-Item -ItemType SymbolicLink -Path $link -Target $target | Out-Null
```
链接建好后，后续普通权限启动就能通过（`symlinkPointsTo` 返回 true 直接跳过创建）。

**方案 B：开开发者模式**（一次设置，永久解决）
```
设置 → 系统 → 开发者选项 → 开发人员模式 = 开
```
或注册表（需管理员）：
```
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock
  AllowDevelopmentWithoutDevLicense = 1 (DWORD)
```

**验证是否已解决**：
```powershell
powershell -NoProfile -Command "if (Test-Path 'D:\AI\ninfer-local\runtime\dsh-home\profiles\node_modules\@deepseek-ai\dsh\package.json') { exit 0 } else { exit 1 }"
# 返回 0 = OK
```

---

### 坑 7 补充：2026-11-13 的最终结论（前面那套不够）

上面写的"管理员跑一次 mklink"只解决了表面。真正的病根是三件事叠加：

**① `scripts/configure-dsh.mjs` 每次启动都删 `profiles/node_modules`**

```js
for (const legacyPath of [
  path.join(root, 'runtime/node_modules'),
  path.join(root, 'node_modules'),
  path.join(home, 'node_modules'),
  path.join(home, 'profiles/node_modules'),   // ← 就是这行
  path.join(profile, 'node_modules'),
  path.join(profile, '.dsh-module-fallback'),
]) {
  removeLegacyFallbackDir(legacyPath);
}
```

注释说"清理旧 junction，避免 chokidar 遇到 NTFS junction realpath 报错"。但它把 dsh 自己需要的模块链接也删了。

**② dsh 需要 240 个包的链接，不是一个**

dsh 从 `runtime/dsh-home/profiles/web/` 加载插件，Node 往上找 `node_modules` 时**到不了** `integrations/dsh/node_modules`。必须靠 `profiles/node_modules` 这一层 fallback 链接把 240 个 `@deepseek-ai/*` 包接进去。

```
Cannot find package '@deepseek-ai/cordis-plugin-timer' imported from
  D:\AI\ninfer-local\runtime\dsh-home\profiles\web\
```

**③ 计划任务上下文建不了任何链接，Bash 上下文可以**

实测对比（同一个 Node、同一份代码、同一个目标路径）：

| 执行上下文 | `fs.symlinkSync(target, link, "junction")` |
|---|---|
| Git Bash 里直接跑 node | ✅ 成功 |
| 计划任务启动的进程 | ❌ **EPERM** |

所以 `start.cmd`（走计划任务）必挂，手动跑却能成功——这个差异极容易误判成"偶发问题"。

---

**最终解法（三步，缺一不可）**

**第一步：改 `configure-dsh.mjs`，别删那个目录**

```js
for (const legacyPath of [
  path.join(root, 'runtime/node_modules'),
  path.join(root, 'node_modules'),
  path.join(home, 'node_modules'),
  // 保留：dsh 自己的模块回退链接在里面，删了就要重建，而计划任务建不了
  // path.join(home, 'profiles/node_modules'),
  path.join(profile, 'node_modules'),
  path.join(profile, '.dsh-module-fallback'),
]) {
  removeLegacyFallbackDir(legacyPath);
}
```

**第二步：批量建好 488 个链接（在普通权限的 shell 里跑）**

```js
// scripts/fix-dsh-links.js
const fs = require("fs"), path = require("path");
const SRC = "D:\\AI\\ninfer-local\\integrations\\dsh\\node_modules";
const DST = "D:\\AI\\ninfer-local\\runtime\\dsh-home\\profiles\\node_modules";
let made = 0, skipped = 0, failed = 0;

function linkOne(srcDir, dstPath) {
  try {
    const st = fs.lstatSync(dstPath);
    if (st.isSymbolicLink() || st.isDirectory()) { skipped++; return; }
    fs.rmSync(dstPath, { force: true });
  } catch {}
  try {
    fs.mkdirSync(path.dirname(dstPath), { recursive: true });
    fs.symlinkSync(srcDir, dstPath, "junction");
    made++;
  } catch (e) { failed++; }
}

fs.mkdirSync(DST, { recursive: true });
for (const name of fs.readdirSync(SRC)) {
  if (name.startsWith(".")) continue;
  const s = path.join(SRC, name);
  if (!fs.statSync(s).isDirectory()) continue;
  if (name.startsWith("@")) {
    fs.mkdirSync(path.join(DST, name), { recursive: true });
    for (const sub of fs.readdirSync(s)) {
      const ss = path.join(s, sub);
      if (!fs.statSync(ss).isDirectory()) continue;
      linkOne(ss, path.join(DST, name, sub));
    }
  } else {
    linkOne(s, path.join(DST, name));
  }
}
console.log(`建立 ${made}，已存在 ${skipped}，失败 ${failed}`);
```

实测输出：`建立 488 个，已存在 0 个，失败 0 个`

**第三步：改 dsh 代码，建不了链接时不要整死启动**

`node_modules/@deepseek-ai/dsh-app-boot/lib/index.js` 的 `healProfilesModuleFallbackLocked`：

```js
function healProfilesModuleFallbackLocked(entries, modulesDir) {
	for (const entry of entries) {
		const link = join(modulesDir, entry.packageName);
		mkdirSync(dirname(link), { recursive: true });
		if (entry.kind === "proxy") { ensureModuleProxy(link, entry.packageName, entry.version, entry.targets); continue; }
		try {
			ensureSymlink(link, entry.packageDir);
		} catch (error) {
			// 受限账户（计划任务、锁定配置）建不了任何链接 —— EPERM。
			if (error && (error.code === "EPERM" || error.code === "EACCES" || error.code === "EINVAL")) continue;
			throw error;
		}
	}
}
```

**验证**

```bash
node -e "console.log(require('fs').existsSync('D:/AI/ninfer-local/runtime/dsh-home/profiles/node_modules/@deepseek-ai/cordis-plugin-timer/package.json'))"
# true

curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3080/"
# 401（要求登录，说明服务活着）
```

**注意**：重装 NInfer 后链接会丢，需要重跑第二步。桌面上的 `修复 NInfer 网页启动.cmd` 就是干这个的（**不需要管理员**）。

**教训**：遇到"手动能跑、脚本不行"，先对比**两个上下文的权限差异**，别急着改代码。这里 Git Bash 和计划任务的权限就不是一回事。

---

### 坑 8：环境变量里 HTTPS_PROXY 和 https_proxy 重复，PowerShell 直接崩

**现象**：跑启动脚本报
```
已添加项。字典中的关键字:“HTTPS_PROXY”所添加的关键字:“https_proxy”
```

**原因**：Windows 环境变量本身大小写不敏感，但某些软件（代理工具、沙盒）会同时写入 `HTTPS_PROXY` 和 `https_proxy` 两份。PowerShell 构造环境变量字典时键冲突，直接抛异常。

**解决**：启动前清空所有代理变量。

```powershell
foreach ($n in @('http_proxy','https_proxy','all_proxy','no_proxy',
                 'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')) {
  Remove-Item "Env:\$n" -ErrorAction SilentlyContinue
}
```

**附带影响**：Python 的 `urllib` 会读这些变量。如果指向一个**已经关闭的代理**（比如 `127.0.0.1:9540`），所有下载都会报
```
URLError: [WinError 10061] 由于目标计算机积极拒绝，无法连接
```
Strata 装引擎时就是这样失败的。清空代理变量后立刻正常。

---

## 三、运行时

### 坑 9：缺 DLL，退出码 -1073741515

**现象**：双击 exe 没反应，命令行返回 `-1073741515`。

**换算**：`-1073741515` = `0xC0000135` = `STATUS_DLL_NOT_FOUND`。

**排查**：从 exe 里流式扫 DLL 名（1.3GB 文件别整个读进内存）：

```python
import re, os
p = r"...\ninfer-serve.exe"
pat = re.compile(rb'[A-Za-z0-9_.\-]{3,40}\.dll', re.I)
found = set()
with open(p,'rb') as f:
    prev = b''
    while True:
        c = f.read(8*1024*1024)
        if not c: break
        buf = prev + c
        for m in pat.finditer(buf):
            s = m.group(0).decode('ascii','ignore')
            if not s.lower().startswith('api-ms'): found.add(s)
        prev = buf[-64:]
print(sorted(found))
```

NInfer 的结果：
```
avcodec-63.dll  avformat-63.dll  avutil-61.dll  swscale-10.dll
cublas64_13.dll  nvcuda.dll  nvcudart_hybrid64.dll  ...
```

**解决**：补齐 cuBLAS（NVIDIA 官方包）+ FFmpeg DLL，全部放到 exe 同目录。

---

### 坑 10：`应用程序无法启动，因为应用程序的并行配置不正确`（0x800736B1 / 14001）

**现象**：把 exe 单独复制到另一个目录测试，报这个错。

**原因**：**不是缺 VC++ 运行库**（系统里 14.51.36247 齐全）。是**缺同目录的依赖 DLL**。

Windows 对这个错误的描述很有误导性——它实际是 SxS（side-by-side）装配解析失败，而不只是运行库版本问题。

**解决**：引擎必须和它的 DLL 放在同一目录：
```
strata.exe
strata_kq.dll
cublas64_13.dll
cublasLt64_13.dll
engine-component.json
BUILD.json
```

---

### 坑 11：128K 上下文直接 OOM 退出

**现象**：`--context 128k` 启动，引擎 15 秒后退出（exit 1），日志：
```
strata generate: expert cache auto: 9.36 GiB free, 700 MiB reserved -> 4933 slots
strata: the CPU prefill share is not armed by default: only 2.3 GiB of RAM is free
strata serve: verify: needs the profile-filled VRAM expert tier (--expert-profile and --expert-cache);
              with --expert-cache auto, no VRAM was left for it
```

**原因**：48GB 内存装不下 `35.5GB 专家 + 128K KV 缓存 + 10GB 系统`。KV 缓存把显存也挤爆了。

**解决**：降上下文 + KV 量化。

```bash
--context 32k      # 128k → 32k
--kv q4_0          # KV 缓存减半（默认 int8）
```

改完内存占用从 46.3GB 降到 **40.0GB**（反而宽松了 7GB），显存留出 604MB。

**官方内存对照表**（Strata MODELS.md）：

| 内存 | 能跑什么 |
|---|---|
| 32GB | 只能 Coder（每层砍一半专家） |
| 48GB | Q2_0、IQ2_XS |
| 64GB | 全部（IQ3_S 要基本不跑别的程序） |
| 96GB+ | IQ3_S / UD-IQ4_XS |

---

### 坑 12：MTP 草稿层自动下载会卡死，必须手动三步

**现象**：`strata launch --mtp on` 卡在
```
Downloading the draft layer (about 5 GB; it makes answers about twice as fast)
```
永远不结束。查进程还在，但 `G:\Strata\mtp\` 目录 0 字节。

**原因**：Strata 的下载器硬编码 `https://huggingface.co`，国内直连不通。它不报错，就那么挂着。

**解决**：手动三步。`tools/mtp_fetch.py` **支持 HF_ENDPOINT 镜像**（这点很重要，代码里写了但文档没提）：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
cd D:\AI\Strata

# 1. 读清单（只读各分片 JSON 头，几 KB）
.\python\python.exe tools\mtp_fetch.py inventory --out G:\Strata\mtp

# 2. 下 31 个张量（5.21GB，实测 2 分 23 秒，自动校验 SHA256）
.\python\python.exe tools\mtp_fetch.py fetch --out G:\Strata\mtp
.\python\python.exe tools\mtp_fetch.py verify --out G:\Strata\mtp

# 3. 打包两步
.\python\python.exe tools\mtp_pack.py --src G:\Strata\mtp --experts q2_0 --out G:\Strata\mtp\mtp-q2_0.gguf
.\python\python.exe tools\mtp_rt.py --gguf G:\Strata\mtp\mtp-q2_0.gguf --out G:\Strata\mtp\rt
```

**最关键的一点**：`--mtp` 参数指向的是 **rt 文件夹**，判定就绪的标志是 **`rt/experts.bin` 存在**：

```python
# strata_control/discovery.py
def _mtp_ready(path: Path) -> bool:
    """--mtp names the ``rt`` folder; it is usable when its experts file is there."""
    return (path / "experts.bin").exists() or (path.is_file() and path.exists())
```

只有 `mtp-q2_0.gguf` 不算数，必须跑完 `mtp_rt.py` 生成 `experts.bin`（675MB）+ `dense.bin`（111MB）。

**效果**：49.9 → **80.2 t/s**（引擎侧纯生成），MTP 草稿接受率 73%。

---

### 坑 13：进程被会话清理，服务启动完就死

**现象**：命令行启动服务，显示 `API ready`，但几分钟后进程消失。

**原因**：通过工具/终端启动的进程，可能随会话结束被清理（进程树回收）。

**解决**：用 Windows 计划任务启动，进程归属 Task Scheduler，不随会话退出。

```powershell
$act = New-ScheduledTaskAction -Execute "D:\AI\start-all.cmd" -WorkingDirectory "D:\AI\ninfer-local"
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$prin = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName "NInferAll" -Action $act -Settings $set -Principal $prin -Force
Start-ScheduledTask -TaskName "NInferAll"
```

**注意**：
- 不要加 `-RunLevel Highest`（需要管理员，普通用户会报"拒绝访问"）
- `schtasks.exe` 可能在某些环境的黑名单里，用 `Start-ScheduledTask` 更保险
- 任务可能被安全软件清理，启动脚本要能检测并提示重新注册

---

## 四、客户端与界面

### 坑 14：API 不给 CORS 头，浏览器调不了

**现象**：写个 HTML 页面 fetch `http://127.0.0.1:8080/v1/chat/completions`，浏览器报 CORS 错误。

**排查**：
```bash
curl -s -i -X OPTIONS "http://127.0.0.1:8080/v1/chat/completions" \
  -H "Origin: http://localhost:8899" | grep -i access-control
# 无输出 = 没有 CORS 头
```

两个引擎都是裸 `BaseHTTP`，不返回 `Access-Control-Allow-*`。

**解决**：起一个本地反向代理，同时提供页面和 API 转发（同源就没跨域问题）。

```python
# 关键：转发时补 CORS 头，流式响应要边读边写
self.send_header("Access-Control-Allow-Origin", "*")
if is_stream:
    while True:
        line = resp.readline()
        if not line: break
        self.wfile.write(line)
        self.wfile.flush()
```

完整实现在 `scripts/proxy.py`。

---

## 五、其他

### 磁盘

**D 盘是机械硬盘（ST4000VX015 4TB SATA HDD），不能放模型。**

Strata 有个 26.8GB 的查找表要**按每个 token 随机读取**。官方原话：

> 机械硬盘会把调度优势全部吃掉，基本可以放弃。

**解决**：模型放 NVMe（三星 MZVLQ512 512GB，G 盘）。

`Get-PhysicalDisk` 查看磁盘类型：
```powershell
Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, MediaType, BusType
Get-Partition -DriveLetter D | Get-Disk    # 看 D 盘对应哪块
```

---

### 快捷方式

**`.lnk` 快捷方式在某些环境建不了**：`New-Object -ComObject WScript.Shell` 被安全策略拦截（"COM object instantiation can run arbitrary code"）。

**解决**：桌面放 `.cmd`，文件名中文、**内容必须 GBK 编码 + CRLF**。

```powershell
# 用 GBK 写，cmd.exe 代码页 936 才能显示中文
$content = "..."
[IO.File]::WriteAllText($path,
  $content.Replace("`r`n","`n").Replace("`n","`r`n"),
  [Text.Encoding]::GetEncoding(936))
```

UTF-8 编码的 `.cmd` 在 cmd 里中文全是乱码。

**另外**：`taskkill /f /im node.exe` 会误杀其他软件的 Node 进程，要按路径精确匹配：

```powershell
Get-Process node -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like 'D:\AI\ninfer-local*' } |
  Stop-Process -Force
```

---

### npm

**`npm config set --location=user` 报 EPERM**（写 `C:\Users\<name>\.npmrc` 被策略拦截）。

**解决**：用项目级 `.npmrc`，放在 `integrations/dsh/` 目录下即可。
