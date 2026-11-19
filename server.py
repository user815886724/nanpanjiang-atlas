#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态站点服务：支持 Range 分段请求（视频边下边播）、HTTP/1.1 长连接、缓存头。"""
import os
import sys
import re
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("text/html", ".html")

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "atlas-static/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()

    def do_HEAD(self):
        self._serve(head_only=True)

    def do_GET(self):
        self._serve(head_only=False)

    def _resolve(self):
        path = unquote(urlparse(self.path).path)
        if path.endswith("/"):
            path += "index.html"
        full = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not full.startswith(ROOT):
            return None
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        return full

    def _serve(self, head_only=False):
        full = self._resolve()
        if not full or not os.path.isfile(full):
            body = b"404 Not Found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return

        size = os.path.getsize(full)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1

        if rng:
            m = RANGE_RE.match(rng.strip())
            if m:
                s, e = m.group(1), m.group(2)
                if s:
                    start = int(s)
                    if e:
                        end = min(int(e), size - 1)
                elif e:
                    start = max(0, size - int(e))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            else:
                self.send_response(200)
        else:
            self.send_response(200)

        length = end - start + 1
        st = os.stat(full)
        etag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", self.date_time_string(st.st_mtime))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if head_only:
            return

        with open(full, "rb") as f:
            f.seek(start)
            remain = length
            chunk = 256 * 1024
            while remain > 0:
                buf = f.read(min(chunk, remain))
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remain -= len(buf)


def main():
    host = os.environ.get("BIND", "0.0.0.0")
    httpd = ThreadingHTTPServer((host, PORT), Handler)
    httpd.daemon_threads = True
    print("serving %s on 0.0.0.0:%d" % (ROOT, PORT))
    sys.stdout.flush()
    httpd.serve_forever()


if __name__ == "__main__":
    main()
