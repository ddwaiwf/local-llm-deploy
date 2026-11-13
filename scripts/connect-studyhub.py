#!/usr/bin/env python3
"""把「学习助手」的 AI 答疑接到本地大模型。

用法（在 Git Bash / cmd 里跑，参数只用一个英文单词，避开中文 argv 坑）：
    python connect-studyhub.py ninfer              # 接 NInfer 27B（1236，推荐）
    python connect-studyhub.py strata              # 接 Strata 125B（8080）
    python connect-studyhub.py ninfer --fix-ping   # 同时修「测试连接」假阴性
    python connect-studyhub.py --restore           # 从最近一次备份还原（含原云端 Key）

三个必须知道的坑：
  1. ai.mode 必须是 "direct"。默认的 "workbuddy" 会写任务单据交给 WorkBuddy，
     压根不读 baseUrl，界面上看着配好了其实没走本地模型。
  2. baseUrl 填到 /v1 就行。lib/ai.js 的 normalizeUrl() 会自动补 /chat/completions；
     填完整的 /chat/completions 也能识别。
  3. 「测试连接」只给 16 个 token 且非流式。NInfer / Strata 都是思考型模型，
     16 个 token 全花在 reasoning_content 上，返回的 message.content 是空的，
     按钮会显示「(空回复)」——这是假阴性，不是没接上。--fix-ping 把它放到 512。

安全：本脚本不含也不保存任何真实 API Key；还原靠本地备份文件（不入库）。
"""

import json
import os
import shutil
import struct
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA = r"C:\Users\123\AppData\Roaming\学习助手\studyhub-data.json"
ASAR = r"C:\Users\123\AppData\Local\Programs\study-hub\resources\app.asar"

# 只改这五个字段；history / useKb / topK / temperature 等一律保留。
TARGETS = {
    "ninfer": {
        "providerId": "custom",
        "baseUrl": "http://127.0.0.1:1236/v1",
        "apiKey": "local",
        "model": "qwen3.8-27b-gsq-rco-iq3-xxs",
        "mode": "direct",
        "hint": "NInfer 27B（先双击桌面「启动 NInfer 27B.cmd」）",
    },
    "strata": {
        "providerId": "custom",
        "baseUrl": "http://127.0.0.1:8080/v1",
        "apiKey": "local",
        "model": "qwen3.8-flash-next-iq2_xs",
        "mode": "direct",
        "hint": "Strata 125B（先双击桌面「启动 Strata 125B.cmd」）",
    },
}

# 等长替换：+1 字节的 token 上限，用 headers 里一个可省的空格抵掉，
# 文件总长不变 -> asar header 里所有 offset/size 仍然有效，不必重打包。
PING_PLUS = (b"max_tokens: 16, stream: false", b"max_tokens: 512, stream: false")
PING_MINUS = (b", Accept: 'text/event-stream'", b",Accept: 'text/event-stream'")


def stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup(path, tag):
    dst = "%s.bak-%s-%s" % (path, stamp(), tag)
    shutil.copy2(path, dst)
    return dst


def asar_files(head):
    """把 asar header 摊平成 {路径: 文件项}。"""
    out = {}

    def walk(node, prefix=""):
        for name, item in node.get("files", {}).items():
            full = prefix + "/" + name
            if "files" in item:
                walk(item, full)
            else:
                out[full] = item

    walk(head)
    return out


def fix_ping():
    """原地等长补丁，修「测试连接」对思考型模型的假阴性。"""
    if not os.path.isfile(ASAR):
        print("[fix-ping] 跳过：找不到 app.asar")
        return
    raw = open(ASAR, "rb").read()
    header_size = struct.unpack("<I", raw[12:16])[0]
    head = json.loads(raw[16:16 + header_size].decode("utf-8"))
    base = 16 + header_size
    entry = asar_files(head).get("/lib/ai.js")
    if not entry:
        print("[fix-ping] 跳过：asar 里没有 /lib/ai.js")
        return
    start = base + int(entry["offset"])
    end = start + int(entry["size"])
    seg = raw[start:end]

    if PING_PLUS[1] in seg and PING_PLUS[0] not in seg:
        print("[fix-ping] 已修过，无需重复操作")
        return
    if seg.count(PING_PLUS[0]) != 1 or seg.count(PING_MINUS[0]) != 1:
        print("[fix-ping] 跳过：目标文本不唯一，版本可能已变，不敢改")
        return
    if raw.count(PING_PLUS[0]) != 1 or raw.count(PING_MINUS[0]) != 1:
        print("[fix-ping] 跳过：目标文本在包内不唯一，不敢改")
        return

    patched = seg.replace(*PING_PLUS).replace(*PING_MINUS)
    if len(patched) != len(seg):
        print("[fix-ping] 跳过：长度对不上，放弃")
        return
    out = bytearray(raw)
    out[start:end] = patched
    out = bytes(out)
    assert len(out) == len(raw), "asar 总长度变了，不能写"
    # header 完全没动，再解一次确认包结构仍完好
    json.loads(out[16:16 + header_size].decode("utf-8"))

    bak = backup(ASAR, "localmodel")
    open(ASAR, "wb").write(out)
    print("[fix-ping] 已修：测试连接 token 上限 16 -> 512")
    print("[fix-ping] 备份：%s" % bak)


def restore():
    folder = os.path.dirname(DATA)
    name = os.path.basename(DATA) + ".bak-"
    cands = sorted(f for f in os.listdir(folder) if f.startswith(name))
    if not cands:
        print("没有找到备份，无法还原")
        return
    src = os.path.join(folder, cands[-1])
    shutil.copy2(src, DATA)
    print("已从备份还原：%s" % cands[-1])


def connect(target):
    cfg = dict(TARGETS[target])
    hint = cfg.pop("hint")
    raw = open(DATA, "r", encoding="utf-8").read()
    db = json.loads(raw)
    if "ai" not in db or not isinstance(db["ai"], dict):
        print("数据文件里没有 ai 配置段，放弃")
        return
    old = {k: db["ai"].get(k) for k in cfg}
    db["ai"].update(cfg)

    bak = backup(DATA, "localmodel")
    # 原文件是紧凑 JSON，写回时保持同样风格，避免 5 MB 文件整篇变成缩进版
    with open(DATA, "w", encoding="utf-8", newline="") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    # 旧配置里可能存着云端厂商的真实 Key，打印时脱敏，避免泄露到终端/截图
    def mask(key, val):
        if key == "apiKey" and isinstance(val, str) and len(val) > 8:
            return val[:3] + "***" + val[-2:]
        return val

    print("已接到：%s" % hint)
    for k, v in cfg.items():
        print("  %-10s %s  ->  %s" % (k, mask(k, old.get(k)), mask(k, v)))
    print("备份：%s" % bak)
    print("提示：学习助手没开就直接打开；已开着会由 onDataChanged 自动重载。")


def main():
    args = [a for a in sys.argv[1:] if a != "--fix-ping"]
    if "--restore" in args:
        restore()
        return
    target = args[0] if args else "ninfer"
    if target not in TARGETS:
        print("用法: connect-studyhub.py ninfer|strata|--restore [--fix-ping]")
        return
    connect(target)
    if "--fix-ping" in sys.argv[1:]:
        fix_ping()


if __name__ == "__main__":
    main()
