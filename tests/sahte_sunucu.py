"""OpenCode v2 sunucusunu taklit eden kucuk HTTP sunucusu (yalnizca testler icin).
Gercek denemede gozlenen uc noktalari ve yanit bicimlerini izler. Alt surec olarak da calisir:
    python sahte_sunucu.py serve --hostname 127.0.0.1 --port N   (parola: OPENCODE_SERVER_PASSWORD)
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Durum:
    def __init__(self, parola="p", davranis="basarili", metin="Bitti.\nSONUC: BASARILI", gecikme=0.4, dosya=None):
        self.parola, self.davranis, self.metin, self.gecikme, self.dosya = parola, davranis, metin, gecikme, dosya
        self.oturumlar: dict[str, dict] = {}
        self.izinler: dict[str, list] = {}
        self.yanitlar: list = []
        self.cagrilar: list = []
        self.olaylar: list[dict] = []
        self.kilit = threading.Lock()


def _isle_bitir(d: Durum, sid: str) -> None:
    o = d.oturumlar[sid]
    time.sleep(d.gecikme)
    if d.davranis == "takili":
        return
    if d.davranis == "izin":
        d.izinler[sid] = [{"id": "per_1", "action": "external_directory"}]
        for _ in range(100):
            if not d.izinler[sid]:
                break
            time.sleep(0.1)
    if d.dosya:
        (Path(o["dir"]) / d.dosya[0]).write_text(d.dosya[1], encoding="utf-8")
    with d.kilit:
        if o["outcome"] is None:
            o["outcome"] = "failed" if d.davranis == "basarisiz" else "succeeded"
        o["aktif"] = False
        d.olaylar.append({"id": "e1", "type": "session.text.delta", "data": {"sessionID": sid, "delta": "Bitti."}})
        d.olaylar.append({"id": "e2", "type": "session.execution." + o["outcome"], "data": {"sessionID": sid}})


def yapi(d: Durum):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _gonder(self, kod, veri=None):
            govde = json.dumps(veri).encode() if veri is not None else b""
            self.send_response(kod)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def _yetkili(self):
            beklenen = "Basic " + base64.b64encode(f"opencode:{d.parola}".encode()).decode()
            if self.headers.get("Authorization") != beklenen:
                self._gonder(401, {"_tag": "UnauthorizedError", "message": "Unauthorized"})
                return False
            return True

        def _oku(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"null") if n else None

        def _yol(self, yontem):
            if not self._yetkili():
                return
            yol = self.path.split("?")[0]
            d.cagrilar.append((yontem, yol))
            if yontem == "GET" and yol == "/api/info":
                return self._gonder(200, {"version": "2.0.30-sahte", "pid": os.getpid()})
            if yontem == "POST" and yol == "/api/session":
                g = self._oku()
                if (g.get("model") or {}).get("providerID") == "yok":
                    return self._gonder(400, {"_tag": "InvalidRequestError", "message": "bilinmeyen saglayici"})
                sid = f"ses_{len(d.oturumlar) + 1}"
                d.oturumlar[sid] = {"dir": g["location"]["directory"], "model": g.get("model"), "agent": g.get("agent"), "title": g.get("title"), "outcome": None, "aktif": False, "istemler": []}
                return self._gonder(200, {"data": {"id": sid}})
            if yontem == "GET" and yol == "/api/session/active":
                return self._gonder(200, {"data": [{"id": s} if i % 2 else s for i, (s, o) in enumerate(d.oturumlar.items()) if o["aktif"]]})
            if yontem == "GET" and yol == "/api/event":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                gonderilen = 0
                try:
                    self.wfile.write(b'data: {"id":"e0","type":"server.connected","data":{}}\n\n')
                    self.wfile.flush()
                    for _ in range(100):
                        while gonderilen < len(d.olaylar):
                            self.wfile.write(b"data: " + json.dumps(d.olaylar[gonderilen]).encode() + b"\n\n")
                            gonderilen += 1
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    pass
                return
            m = re.match(r"^/api/session/([^/]+)(?:/(.+))?$", yol)
            if not m:
                return self._gonder(404, {"_tag": "NotFound", "message": yol})
            sid, alt = m.group(1), m.group(2)
            o = d.oturumlar.get(sid)
            if o is None:
                return self._gonder(404, {"_tag": "SessionNotFoundError", "sessionID": sid, "message": "yok"})
            if yontem == "DELETE" and alt is None:
                del d.oturumlar[sid]
                return self._gonder(204)
            if yontem == "GET" and alt is None:
                return self._gonder(200, {"data": {"id": sid, "outcome": o["outcome"], "tokens": {"input": 100, "output": 20, "reasoning": 5, "cache": {"read": 50, "write": 0}}}})
            if yontem == "POST" and alt == "prompt":
                g = self._oku()
                o["istemler"].append(g["text"])
                o["aktif"], o["outcome"] = True, None
                threading.Thread(target=_isle_bitir, args=(d, sid), daemon=True).start()
                return self._gonder(200, {"data": {"id": "msg_1", "sessionID": sid}})
            if yontem == "POST" and alt == "interrupt":
                d.cagrilar.append(("INTERRUPT", sid))
                was = o["aktif"]
                o["aktif"], o["outcome"] = False, "interrupted"
                return self._gonder(200, {"interrupted": was})
            if yontem == "GET" and alt and alt.startswith("message"):
                return self._gonder(200, {"data": [
                    {"type": "idle", "time": {"created": 3}},
                    {"type": "assistant", "time": {"created": 2}, "content": [{"type": "reasoning", "text": "dusunuyorum"}, {"type": "text", "text": d.metin}]},
                    {"type": "assistant", "time": {"created": 1}, "content": [{"type": "tool", "name": "write"}, {"type": "text", "text": "Dosyayi olusturuyorum."}]},
                    {"type": "user", "time": {"created": 0}, "text": "istem"},
                ]})
            if yontem == "GET" and alt == "permission":
                return self._gonder(200, {"data": list(d.izinler.get(sid, []))})
            m2 = re.match(r"^permission/([^/]+)/reply$", alt or "")
            if yontem == "POST" and m2:
                g = self._oku()
                d.yanitlar.append((sid, m2.group(1), g))
                d.izinler[sid] = []
                return self._gonder(204)
            return self._gonder(404, {"_tag": "NotFound", "message": yol})

        def do_GET(self):
            self._yol("GET")

        def do_POST(self):
            self._yol("POST")

        def do_DELETE(self):
            self._yol("DELETE")

    return H


class SahteSunucu:
    def __init__(self, **kw):
        self.durum = Durum(**kw)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), yapi(self.durum))
        self.http.daemon_threads = True
        self.port = self.http.server_address[1]
        self.taban = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def kapat(self):
        self.http.shutdown()
        self.http.server_close()


if __name__ == "__main__":  # alt surec modu
    a = sys.argv[1:]
    if a[:1] == ["serve"]:
        port = int(a[a.index("--port") + 1])
        parola = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
        if "--cokus" in a:
            sys.exit(3)
        durum = Durum(parola=parola)
        srv = ThreadingHTTPServer(("127.0.0.1", port), yapi(durum))
        srv.serve_forever()
