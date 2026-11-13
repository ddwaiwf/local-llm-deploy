"""Strata 本地测试台 —— 一个文件搞定代理 + 页面。

为什么要这一层：Strata 的 API（8080）不返回 CORS 头，浏览器直接 fetch 会被拦。
这个进程同时提供页面和 API 转发，同源，没有跨域问题。

    python proxy.py            # 然后打开 http://127.0.0.1:8899

不依赖任何第三方库，只用标准库。
"""

import http.server
import json
import os
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path

UPSTREAM = "http://127.0.0.1:8080"
PORT = 8899
HERE = Path(__file__).resolve().parent


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # 只记错误，正常请求不刷屏
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            print(f"[proxy] {fmt % args}")

    # ---------- 页面 ----------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        # 透传 /v1/models 之类的 GET
        self._forward("GET")

    # ---------- API 转发 ----------
    def do_POST(self):
        self._forward("POST")

    def _forward(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(UPSTREAM + self.path, data=body, method=method)
        for k in ("Content-Type", "Accept", "Authorization"):
            if self.headers.get(k):
                req.add_header(k, self.headers[k])

        try:
            resp = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
            return
        except Exception as e:
            msg = json.dumps({"error": {"message": f"连不上 Strata（{UPSTREAM}）：{e}"}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(msg)
            return

        ctype = resp.headers.get("Content-Type", "")
        is_stream = "text/event-stream" in ctype

        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        if is_stream:
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    self.wfile.write(line)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # 用户关掉页面
            return

        data = resp.read()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    if not (HERE / "index.html").exists():
        raise SystemExit(f"缺 index.html（应在 {HERE}）")
    srv = Server(("127.0.0.1", PORT), Handler)
    print(f"Strata 测试台: http://127.0.0.1:{PORT}")
    print(f"转发目标:     {UPSTREAM}")
    print("Ctrl+C 退出")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
