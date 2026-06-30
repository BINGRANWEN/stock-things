#!/usr/bin/env python3
"""
实时行情本地代理 — 绕过浏览器 CORS 限制
启动: python live_proxy.py
端口: 8899
接口: GET /api/live?code=sh688256
"""

import http.server
import json
import re
import sys
import urllib.request
from urllib.parse import urlparse, parse_qs

PORT = 8899

SINA_QUOTE_URL = "https://hq.sinajs.cn/list={code}"
SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_sina_realtime(code: str) -> dict | None:
    """从新浪获取实时行情，返回标准化 dict"""
    url = SINA_QUOTE_URL.format(code=code)
    req = urllib.request.Request(url, headers=SINA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("gbk")
    except Exception as e:
        print(f"[Proxy] 新浪请求失败: {e}")
        return None

    # 解析 var hq_str_sh688256="name,open,prev_close,price,high,low,..."
    match = re.search(r'"([^"]*)"', raw)
    if not match:
        return None

    fields = match.group(1).split(",")
    if len(fields) < 10:
        return None

    try:
        name = fields[0]
        open_price = float(fields[1]) if fields[1] else 0.0
        prev_close = float(fields[2]) if fields[2] else 0.0
        price = float(fields[3]) if fields[3] else prev_close
        high = float(fields[4]) if fields[4] else price
        low = float(fields[5]) if fields[5] else price
        volume = float(fields[8]) if fields[8] else 0.0          # 股
        amount = float(fields[9]) if fields[9] else 0.0           # 元
        date_str = fields[30] if len(fields) > 30 else ""
        time_str = fields[31] if len(fields) > 31 else ""

        change = price - prev_close if prev_close > 0 else 0
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        return {
            "code": code,
            "name": name,
            "open": open_price,
            "prev_close": prev_close,
            "price": price,
            "high": high,
            "low": low,
            "volume": volume / 100,              # 股 → 手（与Tushare一致）
            "amount": amount,                    # 元
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "date": date_str,
            "time": time_str,
            "source": "sina",
        }
    except (ValueError, IndexError) as e:
        print(f"[Proxy] 解析失败: {e}")
        return None


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/live":
            params = parse_qs(parsed.query)
            code = params.get("code", ["sh688256"])[0]

            data = fetch_sina_realtime(code)

            self.send_response(200 if data else 502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

            if data:
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            else:
                self.wfile.write(json.dumps({"error": "无法获取行情"}, ensure_ascii=False).encode("utf-8"))
        else:
            # 健康检查
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"live-proxy","port":%d}' % PORT)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def log_message(self, format, *args):
        # 精简日志
        print(f"[Proxy] {args[0]}" if args else "")


if __name__ == "__main__":
    print(f"实时行情代理已启动 → http://localhost:{PORT}/api/live?code=sh688256")
    print(f"按 Ctrl+C 停止")
    server = http.server.HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n代理已停止")
        server.shutdown()
