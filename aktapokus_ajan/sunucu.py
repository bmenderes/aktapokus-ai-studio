"""OpenCode v2 sunucu istemcisi (SDK): `opencode serve` surecini yonetir, HTTP API'sini surer.

Dogrulanan davranis (OpenCode 2.0.30, gercek sunucuyla):
- `serve --hostname 127.0.0.1 --port N`, kimlik: HTTP Basic (kullanici `opencode`, parola OPENCODE_SERVER_PASSWORD).
- POST /api/session {location:{directory}, model:{id,providerID}} -> oturum; POST /api/session/{id}/prompt {text}
  hemen doner (asenkron); GET /api/session/active ile bitis beklenir; GET /api/session/{id} -> outcome + tokens.
- GET /api/event SSE akisi: session.text.delta, session.tool.called, session.tool.success, session.step.ended,
  session.usage.updated, session.execution.started|succeeded|interrupted.
- Her oturum kendi `location.directory`'sinin .opencode/opencode.json izin ayarini kullanir (koruyucu gecerli).
- DIKKAT: koruyucu yoksa sunucu modunda klasor disi yazma SORUSUZ gerceklesir (denendi).
"""

from __future__ import annotations

import base64
import json
import re
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from . import winjob
from .runners import Calistirici, CalistirmaSonucu, _alt_surec_ortami, _istemi_denetle, opencode_bul


SAGLAYICI_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")
BAGLANTI_DESENI = re.compile(r"^cred_[A-Za-z0-9]{1,100}$")


class SunucuHatasi(Exception):
    pass


@dataclass
class Olay:
    tip: str
    veri: dict
    ham: dict

    @property
    def oturum(self) -> str | None:
        v = self.veri.get("sessionID") if isinstance(self.veri, dict) else None
        return v if isinstance(v, str) else None


def model_coz(model: str | None) -> dict | None:
    """'saglayici/model#varyant' -> {providerID, id, variant}. Saglayici ilk '/' oncesi, kalan model kimligi."""
    if not model:
        return None
    ad, _, varyant = model.partition("#")
    saglayici, ayrac, kimlik = ad.partition("/")
    if not ayrac or not saglayici or not kimlik:
        raise SunucuHatasi(f"Model 'saglayici/model' biciminde olmali: {model!r}")
    sonuc = {"providerID": saglayici, "id": kimlik}
    if varyant:
        sonuc["variant"] = varyant
    return sonuc


class Istemci:
    def __init__(self, taban: str, parola: str, kullanici: str = "opencode", zaman_asimi: float = 30.0):
        self.taban = taban.rstrip("/")
        self._kimlik = "Basic " + base64.b64encode(f"{kullanici}:{parola}".encode()).decode()
        self.zaman_asimi = zaman_asimi

    def _istek(self, yontem: str, yol: str, veri: Any = None, zaman_asimi: float | None = None) -> Any:
        govde = json.dumps(veri).encode() if veri is not None else None
        r = urllib.request.Request(
            self.taban + yol, method=yontem, data=govde, headers={"Content-Type": "application/json", "Authorization": self._kimlik}
        )
        try:
            with urllib.request.urlopen(r, timeout=zaman_asimi or self.zaman_asimi) as y:
                ham = y.read()
                return json.loads(ham) if ham else None
        except urllib.error.HTTPError as hata:
            icerik = hata.read()[:400].decode("utf-8", "replace")
            try:
                j = json.loads(icerik)
                icerik = f"{j.get('_tag', '')}: {j.get('message', icerik)}"
            except (json.JSONDecodeError, AttributeError):
                pass
            raise SunucuHatasi(f"HTTP {hata.code} {yontem} {yol}: {icerik}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as hata:
            raise SunucuHatasi(f"Sunucuya ulasilamadi ({yontem} {yol}): {hata}") from None

    @staticmethod
    def _veri(yanit: Any) -> Any:
        return yanit.get("data") if isinstance(yanit, dict) and "data" in yanit else yanit

    def bilgi(self) -> dict:
        return self._istek("GET", "/api/info")

    def modeller(self) -> list:
        return self._veri(self._istek("GET", "/api/model")) or []

    def ajanlar(self) -> list:
        return self._veri(self._istek("GET", "/api/agent")) or []

    # --- saglayicilar ve anahtarlar (OpenCode v2 /api/integration). NOT: GET /api/credential anahtari DUZ METIN dondurur; hic cagrilmaz. ---
    def saglayicilar(self) -> list:
        """Kullanilabilir saglayicilar: [{id, name, methods:[{type, names?}], connections:[{id, label, method}]}] (anahtar icermez)."""
        return self._veri(self._istek("GET", "/api/integration")) or []

    def anahtar_baglan(self, saglayici: str, anahtar: str, etiket: str | None = None) -> None:
        if not SAGLAYICI_DESENI.match(saglayici):
            raise SunucuHatasi("Gecersiz saglayici kimligi")
        govde: dict = {"key": anahtar}
        if etiket:
            govde["label"] = etiket
        self._istek("POST", f"/api/integration/{saglayici}/connect/key", govde)

    def baglanti_kaldir(self, baglanti_kimligi: str) -> None:
        if not BAGLANTI_DESENI.match(baglanti_kimligi):
            raise SunucuHatasi("Gecersiz baglanti kimligi")
        self._istek("DELETE", f"/api/credential/{baglanti_kimligi}")

    def oturum_olustur(self, klasor: str | Path, model: str | None = None, agent: str | None = None, baslik: str | None = None) -> str:
        govde: dict = {"location": {"directory": str(klasor)}}
        if model:
            govde["model"] = model_coz(model)
        if agent:
            govde["agent"] = agent
        if baslik:
            govde["title"] = baslik
        return self._veri(self._istek("POST", "/api/session", govde))["id"]

    def oturum_al(self, sid: str) -> dict:
        return self._veri(self._istek("GET", f"/api/session/{sid}"))

    def oturum_sil(self, sid: str) -> None:
        self._istek("DELETE", f"/api/session/{sid}")

    def aktif_oturumlar(self) -> list[str]:
        sonuc = []
        for x in self._veri(self._istek("GET", "/api/session/active")) or []:
            kimlik = x if isinstance(x, str) else (x or {}).get("id") or (x or {}).get("sessionID")
            if kimlik:
                sonuc.append(kimlik)
        return sonuc

    def mesaj_gonder(self, sid: str, metin: str) -> str:
        return self._veri(self._istek("POST", f"/api/session/{sid}/prompt", {"text": metin}))["id"]

    def durdur(self, sid: str) -> bool:
        y = self._istek("POST", f"/api/session/{sid}/interrupt")
        return bool((y or {}).get("interrupted"))

    def mesajlar(self, sid: str, limit: int = 100) -> list[dict]:
        return self._veri(self._istek("GET", f"/api/session/{sid}/message?limit={int(limit)}")) or []

    def izinler(self, sid: str) -> list[dict]:
        return self._veri(self._istek("GET", f"/api/session/{sid}/permission")) or []

    def izin_yanitla(self, sid: str, istek_kimligi: str, karar: str, mesaj: str | None = None) -> None:
        if karar not in ("once", "always", "reject"):
            raise SunucuHatasi(f"Gecersiz izin karari: {karar!r}")
        govde: dict = {"decision": karar}
        if mesaj:
            govde["message"] = mesaj
        self._istek("POST", f"/api/session/{sid}/permission/{istek_kimligi}/reply", govde)

    def olaylar(self, zaman_asimi: float = 3600.0) -> Iterator[Olay]:
        """SSE akisi. Baglanti kopunca ya da zaman asiminda biter. Bilinmeyen olay tipleri de dondurulur."""
        r = urllib.request.Request(self.taban + "/api/event", headers={"Authorization": self._kimlik, "Accept": "text/event-stream"})
        try:
            with urllib.request.urlopen(r, timeout=zaman_asimi) as y:
                for satir in y:
                    satir = satir.decode("utf-8", "replace").rstrip("\r\n")
                    if not satir.startswith("data:"):
                        continue
                    try:
                        ham = json.loads(satir[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if isinstance(ham, dict) and isinstance(ham.get("type"), str):
                        yield Olay(ham["type"], ham.get("data") if isinstance(ham.get("data"), dict) else {}, ham)
        except (urllib.error.URLError, OSError, TimeoutError):
            return


def _bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _agaci_oldur(islem: subprocess.Popen) -> None:
    """Sunucu ve baslattigi alt surecleri (MCP sunuculari vb.) kapatir."""
    if islem.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(islem.pid), "/T", "/F"], capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
    else:
        islem.terminate()
    try:
        islem.wait(timeout=10)
    except subprocess.TimeoutExpired:
        islem.kill()


def _is_nesnesine_bagla(islem: subprocess.Popen):
    """Windows: alt sureci, bu surec olunce (hatta zorla kapatilirsa) OS tarafindan oldurulen bir 'job' nesnesine baglar (bkz. winjob.py)."""
    if os.name != "nt":
        return None
    return winjob.bagla(int(islem._handle))


class Sunucu:
    """Ozel (bu uygulamaya ait) bir `opencode serve` sureci: yalnizca 127.0.0.1, rastgele port ve parola."""

    def __init__(self, komut_oneki: list[str] | None = None, baslangic_klasoru: str | Path | None = None, hazir_zaman_asimi: float = 90.0):
        if komut_oneki is None:
            cli = opencode_bul()
            if not cli:
                raise SunucuHatasi("OpenCode CLI bulunamadi (PATH ya da AKTAPOKUS_OPENCODE).")
            komut_oneki = [cli]
        self.komut_oneki = komut_oneki
        self.baslangic_klasoru = Path(baslangic_klasoru or Path.cwd())
        self.hazir_zaman_asimi = hazir_zaman_asimi
        self.islem: subprocess.Popen | None = None
        self.istemci: Istemci | None = None
        self._kilit = threading.Lock()  # es zamanli istekler (arayuz) tek surec baslatsin

    def baslat(self) -> Istemci:
        with self._kilit:
            return self._baslat()

    def _baslat(self) -> Istemci:
        if self.istemci is not None and self.islem is not None and self.islem.poll() is None:
            return self.istemci
        port, parola = _bos_port(), secrets.token_urlsafe(24)
        ortam = _alt_surec_ortami(self.baslangic_klasoru)
        ortam["OPENCODE_SERVER_PASSWORD"] = parola  # argv'de degil, ortamda: komut satirinda gorunmesin
        self.islem = subprocess.Popen(
            [*self.komut_oneki, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
            cwd=str(self.baslangic_klasoru),
            env=ortam,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._is = _is_nesnesine_bagla(self.islem)
        istemci = Istemci(f"http://127.0.0.1:{port}", parola)
        son = time.monotonic() + self.hazir_zaman_asimi
        while time.monotonic() < son:
            if self.islem.poll() is not None:
                raise SunucuHatasi(f"OpenCode sunucusu erken kapandi (cikis kodu {self.islem.returncode})")
            try:
                istemci.bilgi()
                self.istemci = istemci
                return istemci
            except SunucuHatasi:
                time.sleep(0.3)
        self.kapat()
        raise SunucuHatasi(f"OpenCode sunucusu {self.hazir_zaman_asimi:.0f} sn icinde hazir olmadi")

    def kapat(self) -> None:
        if self.islem is not None:
            _agaci_oldur(self.islem)
        self.islem = None
        self.istemci = None

    def __enter__(self) -> Istemci:
        return self.baslat()

    def __exit__(self, *_a) -> None:
        self.kapat()


def mesajlardan_metin(mesajlar: list[dict]) -> str:
    """Asistan mesajlarindaki 'text' parcalarini zaman sirasiyla birlestirir (reasoning/arac haric)."""
    asistan = [m for m in mesajlar if m.get("type") == "assistant"]
    asistan.sort(key=lambda m: (m.get("time") or {}).get("created", 0))
    parcalar = []
    for m in asistan:
        for c in m.get("content") or []:
            if c.get("type") == "text" and isinstance(c.get("text"), str) and c["text"].strip():
                parcalar.append(c["text"].strip())
    return "\n".join(parcalar)


class SunucuCalistirici(Calistirici):
    """Kalici `opencode serve` uzerinden calistirir: her cagri yeni oturum (temiz baglam); sunucu cagrilar arasi acik kalir."""

    ad = "opencode-sunucu"

    def __init__(
        self,
        sunucu: Sunucu | None = None,
        istemci: Istemci | None = None,
        ilerleme: Callable[[dict], None] | None = None,
        izin_karari: str = "reject",
        yoklama_sn: float = 0.5,
        paylasilan: bool = False,
    ):
        self._aktif_sid: str | None = None  # bu ORNEGIN su an kosan oturumu (ornek koşu basina ayridir)
        self._paylasilan = paylasilan  # sunucu baska calistiricilarla ortak: kapat() sunucuyu KAPATMAZ (hepsini_kapat kapatir)
        self._sunucu = sunucu
        self._istemci = istemci
        self._sunucu_kilidi = threading.Lock()
        self.ilerleme = ilerleme
        self.izin_karari = izin_karari
        self.yoklama_sn = yoklama_sn

    def _al(self) -> Istemci:
        if self._istemci is not None:
            return self._istemci
        with self._sunucu_kilidi:
            if self._sunucu is None:
                self._sunucu = Sunucu()
        return self._sunucu.baslat()

    def kapat(self) -> None:
        if self._sunucu is not None and not self._paylasilan:
            self._sunucu.kapat()

    def durdur(self) -> bool:
        sid, istemci = getattr(self, "_aktif_sid", None), self._istemci or (self._sunucu.istemci if self._sunucu else None)
        if not sid or istemci is None:
            return False
        try:
            return istemci.durdur(sid)
        except SunucuHatasi:
            return False

    def _dinleyici(self, istemci: Istemci, sid: str, durdur: threading.Event, bitti: threading.Event) -> threading.Thread | None:
        if self.ilerleme is None:
            bitti.set()
            return None
        ilerleme = self.ilerleme

        def calis() -> None:
            for olay in istemci.olaylar():
                if durdur.is_set():
                    return
                if olay.oturum != sid:
                    continue
                if olay.tip.startswith("session.execution.") and not olay.tip.endswith(".started"):
                    bitti.set()
                v = olay.veri
                if olay.tip == "session.text.delta":
                    ilerleme({"tur": "metin", "parca": v.get("delta", "")})
                elif olay.tip == "session.tool.called":
                    ilerleme({"tur": "arac", "ad": v.get("name") or v.get("tool"), "girdi": v.get("input")})
                elif olay.tip == "session.tool.success":
                    ilerleme({"tur": "arac-sonuc"})
                elif olay.tip == "session.usage.updated":
                    ilerleme({"tur": "kullanim", "token": v.get("tokens")})
                elif olay.tip.startswith("session.execution."):
                    ilerleme({"tur": "bitti" if olay.tip != "session.execution.started" else "basladi", "durum": olay.tip.rsplit(".", 1)[-1]})

        t = threading.Thread(target=calis, daemon=True)
        t.start()
        return t

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        baslangic = time.monotonic()
        try:
            _istemi_denetle(istem)
            istemci = self._al()
            sid = istemci.oturum_olustur(klasor, model=model, agent=agent, baslik="aktapokus")
        except Exception as hata:
            return CalistirmaSonucu(False, hata=f"{type(hata).__name__}: {hata}", sure_sn=time.monotonic() - baslangic)
        durdur, bitti = threading.Event(), threading.Event()
        self._aktif_sid = sid
        self._dinleyici(istemci, sid, durdur, bitti)
        try:
            istemci.mesaj_gonder(sid, istem)
            son = baslangic + zaman_asimi_sn
            islenen_izinler: set[str] = set()
            while True:
                time.sleep(self.yoklama_sn)
                for izin in istemci.izinler(sid):
                    if izin.get("id") and izin["id"] not in islenen_izinler:
                        islenen_izinler.add(izin["id"])
                        istemci.izin_yanitla(sid, izin["id"], self.izin_karari, "Aktapokus: izin istegi otomatik yanitlandi")
                if sid not in istemci.aktif_oturumlar():
                    break
                if time.monotonic() > son:
                    try:
                        istemci.durdur(sid)
                    except SunucuHatasi:
                        pass
                    return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
            bilgi = istemci.oturum_al(sid)
            metin = mesajlardan_metin(istemci.mesajlar(sid))
        except SunucuHatasi as hata:
            return CalistirmaSonucu(False, hata=str(hata), sure_sn=time.monotonic() - baslangic)
        finally:
            self._aktif_sid = None
            bitti.wait(timeout=1.5)  # bitis olayi, aktiflik kapandiktan biraz sonra gelebilir
            durdur.set()
        t = bilgi.get("tokens") or {}
        sonuc = CalistirmaSonucu(
            ok=bilgi.get("outcome") == "succeeded",
            metin=metin,
            token_girdi=int(t.get("input") or 0),
            token_cikti=int(t.get("output") or 0) + int(t.get("reasoning") or 0),
            token_onbellek=int((t.get("cache") or {}).get("read") or 0),
            sure_sn=time.monotonic() - baslangic,
        )
        if not sonuc.ok:
            sonuc.hata = f"OpenCode oturumu basarisiz bitti (outcome={bilgi.get('outcome')!r})" + (f": {bilgi['error']}" if bilgi.get("error") else "")
        return sonuc
