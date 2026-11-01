"""Node-RED'i yerel olarak kurar ve calistirir (Ayarlar > Node-RED). Ayri kurulum, sabit surum, yalniz 127.0.0.1.

Node-RED duzenleyicisi kod calistirabilir: bu yuzden yalniz yerel dinler, yonetim adresi her baslangicta rastgele uretilir ve adres yalniz belirtecli API'den
verilir; uzaktan yonetilemez (uzak.politika). Node-RED akislari Aktapokus'un plan onayi ve geri alma korumalarinin DISINDADIR; PLC'ye yazan akis kullanicinin sorumlulugundadir.
"""

from __future__ import annotations

import atexit
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from .runners import _alt_surec_ortami

SURUM = "5.0.9"
_PENCERESIZ = 0x08000000 if sys.platform == "win32" else 0


class NodeRedHatasi(Exception):
    pass


def kok() -> Path:
    return Path(os.environ.get("AKTAPOKUS_NODERED") or Path.home() / ".aktapokus" / "node-red")


def _red_js() -> Path:
    return kok() / "node_modules" / "node-red" / "red.js"


def ayar_metni(port: int, yonetim_yolu: str, veri: Path, sir: str) -> str:
    ayar = {
        "uiHost": "127.0.0.1", "uiPort": port, "httpAdminRoot": yonetim_yolu, "httpNodeRoot": yonetim_yolu + "/n",
        "userDir": str(veri), "flowFile": "flows.json", "credentialSecret": sir, "editorTheme": {"tours": False},
    }
    return "module.exports = " + json.dumps(ayar, indent=1) + ";\n"


class Yonetici:
    def __init__(self):
        self._kilit = threading.Lock()
        self._islem: subprocess.Popen | None = None
        self._adres: str | None = None
        self._kuruluyor = False
        self._hata: str | None = None
        atexit.register(self.durdur)

    def durum(self) -> dict:
        calisiyor = self._islem is not None and self._islem.poll() is None
        return {"node": bool(shutil.which("node")), "npm": bool(shutil.which("npm")), "surum": SURUM, "kurulu": _red_js().is_file(), "kuruluyor": self._kuruluyor,
                "calisiyor": calisiyor, "adres": self._adres if calisiyor else None, "hata": self._hata}

    def kur(self) -> dict:
        npm = shutil.which("npm")
        if not npm:
            raise NodeRedHatasi("Node.js bulunamadi. https://nodejs.org adresinden LTS surumunu kurup uygulamayi yeniden baslatin.")
        with self._kilit:
            if not self._kuruluyor and not _red_js().is_file():
                self._kuruluyor, self._hata = True, None
                threading.Thread(target=self._kur_is, args=(npm,), daemon=True).start()
        return self.durum()

    def _kur_is(self, npm: str) -> None:
        try:
            kok().mkdir(parents=True, exist_ok=True)
            r = subprocess.run([npm, "install", "--prefix", str(kok()), "--no-audit", "--no-fund", "--omit=dev", f"node-red@{SURUM}"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               stdin=subprocess.DEVNULL, timeout=900, creationflags=_PENCERESIZ, env=_alt_surec_ortami(kok()), cwd=str(kok()))
            if r.returncode != 0 or not _red_js().is_file():
                self._hata = "Kurulum basarisiz: " + (r.stderr or r.stdout or "").strip()[-400:]
        except (OSError, subprocess.SubprocessError) as hata:
            self._hata = f"Kurulum basarisiz: {hata}"
        finally:
            self._kuruluyor = False

    def baslat(self, bekleme_sn: float = 60) -> dict:
        node = shutil.which("node")
        if not node or not _red_js().is_file():
            raise NodeRedHatasi("Node-RED kurulu degil")
        with self._kilit:
            if self._islem is not None and self._islem.poll() is None:
                return self.durum()
            veri = kok() / "veri"
            veri.mkdir(parents=True, exist_ok=True)
            sir_yolu = kok() / "kimlik-sirri"
            if not sir_yolu.is_file():
                sir_yolu.write_text(secrets.token_hex(32), encoding="utf-8")
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            yol = "/r-" + secrets.token_hex(24)
            ayar = kok() / "settings.js"
            ayar.write_text(ayar_metni(port, yol, veri, sir_yolu.read_text(encoding="utf-8").strip()), encoding="utf-8")
            kayit = open(kok() / "nodered.log", "ab")
            self._hata = None
            self._islem = subprocess.Popen([node, str(_red_js()), "--settings", str(ayar), "--userDir", str(veri)], stdin=subprocess.DEVNULL, stdout=kayit, stderr=kayit, cwd=str(kok()),
                                           creationflags=_PENCERESIZ, env=_alt_surec_ortami(kok()))
            kayit.close()
            son = time.monotonic() + bekleme_sn
            while time.monotonic() < son:
                if self._islem.poll() is not None:
                    self._hata = "Node-RED baslarken kapandi (bkz. nodered.log)"
                    return self.durum()
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                    self._adres = f"http://127.0.0.1:{port}{yol}/"
                    return self.durum()
                except OSError:
                    time.sleep(0.3)
            self._hata = "Node-RED zamaninda baslamadi"
            return self.durum()

    def durdur(self) -> dict:
        i = self._islem
        if i is not None and i.poll() is None:
            i.terminate()
            try:
                i.wait(timeout=10)
            except subprocess.TimeoutExpired:
                i.kill()
        self._islem, self._adres = None, None
        return self.durum()


YONETICI = Yonetici()
