"""Sahte `subprocess.Popen`: Claude Code'un `stream-json` akisini gercek surec baslatmadan taklit eder (satir satir, istege bagli bloklayan)."""

import io
import json
import threading
from pathlib import Path


class _Yazici:
    def __init__(self, kayit):
        self.kayit = kayit
        kayit["girdi"] = b""

    def write(self, b):
        self.kayit["girdi"] += b

    def close(self):
        self.kayit["stdin_kapandi"] = True


class SahtePopen:
    senaryo: dict = {}

    def __init__(self, komut, stdin=None, stdout=None, stderr=None, cwd=None, env=None, **kw):
        sen = type(self).senaryo
        k = sen["kayit"]
        k.update(komut=list(komut), cwd=cwd, env=env, kw=kw)
        k.setdefault("cagrilar", []).append(list(komut))
        for bayrak, anahtar in (("--settings", "ayar"), ("--mcp-config", "mcp")):  # gecici dosyalar calisma bitince silinir: simdi oku
            if bayrak in komut:
                try:
                    k[anahtar] = json.loads(Path(komut[komut.index(bayrak) + 1]).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
        self.stdin = _Yazici(k)
        hata = sen["hata_sirasi"].pop(0) if sen.get("hata_sirasi") else sen.get("hata", b"")  # cagri basina hata/cikis kodu verilebilir
        kod = sen["kod_sirasi"].pop(0) if sen.get("kod_sirasi") else sen.get("kod", 0)
        self.stderr = io.BytesIO(hata)
        self.pid = 4242
        self.returncode = kod
        self._oldu = threading.Event()
        self._bitti = False
        self.stdout = self._satirlar(sen)

    def _satirlar(self, sen):
        sira = sen.get("olaylar_sirasi")
        olaylar = sira.pop(0) if sira else sen["olaylar"]  # birden cok cagri icin her cagriya ayri olay listesi
        for o in olaylar:
            yield (json.dumps(o) + "\n").encode("utf-8")
        if sen.get("engelle"):
            self._oldu.wait(10)
        self._bitti = True

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode if (self._bitti or self._oldu.is_set()) else None

    def kill(self):
        self._oldu.set()


def sonuc_olayi(metin="x", oturum="11111111-1111-1111-1111-111111111111", hata=False, **ek):
    return {"type": "result", "subtype": "success", "is_error": hata, "result": metin, "session_id": oturum,
            "usage": {"input_tokens": 5, "cache_creation_input_tokens": 10, "output_tokens": 3, "cache_read_input_tokens": 2}, **ek}


def claude_taklit(monkeypatch, runners, olaylar=None, hata=b"", kod=0, engelle=False, sirali=None):
    """Claude calistiricisinin Popen'ini sahtesiyle degistirir; (kayit, senaryo) doner. Gercek taskkill HICBIR ZAMAN calismaz."""
    kayit: dict = {}
    sen = {"kayit": kayit, "olaylar": olaylar if olaylar is not None else [sonuc_olayi()], "hata": hata, "kod": kod, "engelle": engelle}
    if sirali:
        sen["olaylar_sirasi"] = list(sirali)
    monkeypatch.setattr(runners.subprocess, "Popen", type("P", (SahtePopen,), {"senaryo": sen}))
    monkeypatch.setattr(runners.ClaudeCodeCalistirici, "_surec_oldur", staticmethod(lambda islem: islem.kill()))
    return kayit, sen
