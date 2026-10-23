"""Telegram Bot API'sini taklit eden yerel sunucu (yalnizca testler icin)."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "123456:SAHTE-TOKEN-abcdef"


class SahteTelegram:
    def __init__(self, token: str = TOKEN):
        self.token = token
        self.kilit = threading.Lock()
        self.bekleyen: list[dict] = []
        self.sayac = 100
        self.cagrilar: list[tuple[str, dict]] = []
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self._yapi())
        self.http.daemon_threads = True
        self.taban = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self._mesaj_no = 0

    # --- test yardimcilari ---
    def mesaj(self, uid: int, metin: str, chat_id: int | None = None, tur: str = "private") -> int:
        with self.kilit:
            self.sayac += 1
            self.bekleyen.append({"update_id": self.sayac, "message": {"message_id": self.sayac, "from": {"id": uid}, "chat": {"id": chat_id if chat_id is not None else uid, "type": tur}, "text": metin}})
            return self.sayac

    def dugme(self, uid: int, veri: str, mesaj_id: int = 1, chat_id: int | None = None, tur: str = "private") -> None:
        with self.kilit:
            self.sayac += 1
            self.bekleyen.append({"update_id": self.sayac, "callback_query": {"id": f"cb{self.sayac}", "from": {"id": uid}, "data": veri, "message": {"message_id": mesaj_id, "chat": {"id": chat_id if chat_id is not None else uid, "type": tur}}}})

    def gonderilen(self, yontem: str = "sendMessage") -> list[dict]:
        return [v for m, v in self.cagrilar if m == yontem]

    def metinler(self) -> list[str]:
        return [v["text"] for v in self.gonderilen("sendMessage")]

    def kapat(self) -> None:
        self.http.shutdown()
        self.http.server_close()

    def _yapi(self):
        s = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _yanit(self, kod, veri):
                b = json.dumps(veri).encode()
                self.send_response(kod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                veri = json.loads(self.rfile.read(n) or b"{}")
                on = f"/bot{s.token}/"
                if not self.path.startswith(on):
                    return self._yanit(401, {"ok": False, "description": f"Unauthorized (yol: {self.path})"})
                yontem = self.path[len(on):]
                s.cagrilar.append((yontem, veri))
                if yontem == "getUpdates":
                    offset, bekle = veri.get("offset", 0), min(veri.get("timeout", 0), 1)
                    son = time.monotonic() + bekle
                    while True:
                        with s.kilit:
                            if offset == -1:  # gercek Telegram gibi: yalniz SON guncelleme doner ve onaylanana (offset > id) dek kalir
                                sonuc = s.bekleyen[-1:]
                                s.bekleyen = list(sonuc)
                            else:
                                s.bekleyen = [u for u in s.bekleyen if u["update_id"] >= offset]
                                sonuc = list(s.bekleyen)
                        if sonuc or time.monotonic() >= son:
                            return self._yanit(200, {"ok": True, "result": sonuc})
                        time.sleep(0.05)
                if yontem == "getMe":
                    return self._yanit(200, {"ok": True, "result": {"id": 1, "is_bot": True, "username": "sahte_bot"}})
                if yontem == "sendMessage":
                    s._mesaj_no += 1
                    return self._yanit(200, {"ok": True, "result": {"message_id": 1000 + s._mesaj_no}})
                return self._yanit(200, {"ok": True, "result": True})

        return H
