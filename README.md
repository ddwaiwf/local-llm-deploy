# 本地大模型部署实录（Windows + RTX 50 系）

两份完整的本地推理部署记录：一个 27B 稠密模型，一个 125B MoE 模型，都跑在同一台消费级机器上。

不是教程转载，是从零踩坑踩出来的实录——每一步的实际命令、每个坑的真实报错、每个坑的解决办法。

---

## 硬件

| 项目 | 配置 |
|---|---|
| CPU | AMD Ryzen 7 9800X3D |
| 显卡 | RTX 5080 16GB（sm_120） |
| 内存 | 48GB（3×16GB DDR5 4800） |
| 系统盘 | 致钛 TiPlus7100 1TB（NVMe） |
| 数据盘 | 三星 MZVLQ512 512GB（NVMe，G:） |
| 机械盘 | 希捷 ST4000VX015 4TB（SATA，D:） |
| 系统 | Windows 11 专业工作站版 26200 |
| 驱动 | 616.56 |

> **关键：模型必须放 NVMe SSD。** 两个引擎都有"按 token 随机读磁盘"的机制，机械盘会把性能拖死。详见 [踩坑实录](docs/03-pitfalls.md#磁盘).

---

## 两个模型怎么选

| | NInfer 27B | Strata 125B |
|---|---|---|
| 模型 | Qwen3.8-27B 稠密 | Qwen3.8-Flash-Next 125B MoE |
| 架构特点 | 每 token 算全部 27B 参数 | 24576 个专家，每 token 只激活 10 个（约 6B） |
| 量化 | IQ3_XXS（3bit） | IQ2_XS（2bit） |
| 模型体积 | 10.06 GB | 63.35 GB |
| 显存占用 | 14.7 / 16.3 GB | 15.4 / 16.3 GB |
| 内存占用 | 31 / 47 GB | 40 / 47 GB |
| 上下文 | 262144（256K） | 32768（32K，受内存限制） |
| **实测速度** | **122 t/s** | **93.7 t/s**（长输出） |
| 擅长 | 代码、推理、精确任务 | 知识面广、长文档 |
| 界面 | 自带 Agent 网页（3080） | 自带 API，可接各种客户端 |
| 部署难度 | 中（符号链接坑） | 高（下载器在国内基本不可用） |

**一句话建议**：写代码用 27B，查资料/读长文用 125B。两个不能同时跑（显存和内存都不够）。

---

## 快速开始

### NInfer 27B（约 5 分钟，前提是模型已下好）

```powershell
cd D:\AI\ninfer-local
.\setup.ps1 -ModelPath "D:\AI\ninfer-local\models\qwen3.8-27b-gsq-rco-iq3-xxs.ninfer"
.\start.cmd
```

### Strata 125B（约 2 小时，主要是下载）

```powershell
# 引擎（601MB，用 gh-proxy 十路并行，2 分钟）
# 模型（63.35GB，用 hf-mirror，约 25 分钟）
# 详见 docs/02-strata-125b.md
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [01 · NInfer 27B 部署](docs/01-ninfer-27b.md) | 完整步骤、模型转换、服务架构 |
| [02 · Strata 125B 部署](docs/02-strata-125b.md) | 国内下载方案、MTP 草稿层手动安装 |
| [03 · 踩坑实录](docs/03-pitfalls.md) | 14 个坑的真实报错与解法 |
| [04 · 客户端接入](docs/04-clients.md) | 学习助手、Claude Code、OpenCode 等 |

## 脚本

`scripts/` 目录是可复用的启动模板（Windows `.cmd`，GBK 编码 + CRLF）。

---

## 核心结论（如果只看一段）

1. **国内下模型用 hf-mirror，下 GitHub 大文件用 gh-proxy 十路并行 Range 分片**。Strata 自带下载器只有 50KB/s，hf 直连不通，ModelScope 不支持 Range——这三条堵死了所有"正常"路径。
2. **杀毒软件会把推理引擎当木马**。无签名 + 大 exe + 狂调 CUDA + 常驻后台，这画像和挖矿木马重合度 90%。加白即可。
3. **Windows 普通权限建不了符号链接**。NInfer 的 dsh 偏偏需要真 symlink（junction 骗不过它的 `isSymbolicLink()` 检查），必须管理员跑一次修复。
4. **48GB 内存是 125B MoE 的生死线**。IQ2_XS 专家要 35.5GB 进内存 + 10GB 系统开销，刚好卡住。想上 IQ3_S 或 128K 上下文，得 64GB。

---

## 实测数据

同一条指令（写质数判断函数）在两个模型上的表现：

| | NInfer 27B | Strata 125B |
|---|---|---|
| 首 token | 0.4 s | 0.5 s |
| 输出速度 | 122 t/s | 93.7 t/s |
| 输出质量 | 正确，含偶数跳过优化 | 正确，含偶数跳过优化 |

两者代码质量相当，27B 快 30%，125B 知识面更广。

---

## 许可

文档 MIT。两个引擎各自的许可：
- NInfer：见其仓库 LICENSE
- Strata：MIT（模型权重各自独立许可）
