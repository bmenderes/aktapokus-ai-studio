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
from .config import AYAR_KLASORU
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
        if not SAGLAYICI_DESENI.fullmatch(saglayici):
            raise SunucuHatasi("Gecersiz saglayici kimligi")
        govde: dict = {"key": anahtar}
        if etiket:
            govde["label"] = etiket
        self._istek("POST", f"/api/integration/{saglayici}/connect/key", govde)

    def baglanti_kaldir(self, baglanti_kimligi: str) -> None:
        if not BAGLANTI_DESENI.fullmatch(baglanti_kimligi):
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

    # --- MCP sunuculari (OpenCode API'si; calisma anina ozel, dosyaya yazilmaz) ---
    @staticmethod
    def _konum(klasor: str | Path) -> str:
        import urllib.parse

        return "location[directory]=" + urllib.parse.quote(str(klasor), safe="")

    def mcp_liste(self, klasor: str | Path) -> dict[str, dict]:
        """{ad: durum} (durum: connected | pending | disabled | failed ...)."""
        v = self._veri(self._istek("GET", "/api/mcp?" + self._konum(klasor))) or []
        return {x["name"]: x.get("status") or {} for x in v if isinstance(x, dict) and "name" in x}

    def mcp_ekle(self, klasor: str | Path, ad: str, config: dict) -> None:
        self._istek("PUT", f"/api/experimental/mcp/{ad}?" + self._konum(klasor), {"config": config})

    def mcp_sil(self, klasor: str | Path, ad: str) -> None:
        self._istek("DELETE", f"/api/experimental/mcp/{ad}?" + self._konum(klasor))

    def beceriler(self, klasor: str | Path, bekle_sn: float = 8.0) -> list[dict]:
        """OpenCode'un bu klasor icin gordugu beceriler. Ilk cagri tarama bitmeden bos donebilir: liste durulana kadar yoklanir."""
        yol = "/api/skill?" + self._konum(klasor)
        onceki: list[str] | None = None
        bitis = time.monotonic() + bekle_sn
        while True:
            v = self._veri(self._istek("GET", yol)) or []
            kimlikler = sorted(str(x.get("id")) for x in v if isinstance(x, dict))
            if (kimlikler == onceki and kimlikler) or time.monotonic() > bitis:
                return [{"kimlik": x.get("id"), "ad": x.get("name"), "aciklama": x.get("description") or "", "yol": x.get("path") or "", "otomatik": x.get("autoinvoke", True)} for x in v if isinstance(x, dict)]
            onceki = kimlikler
            time.sleep(0.5)

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

    def kabuk_cikti(self, kabuk: str, klasor: str | Path, imlec: int = 0) -> dict:
        """Ajanin calistirdigi komutun imlecten sonraki ciktisi {output, cursor, size}. Sunucu kabugu yalniz kendi klasoruyle bulur (klasorsuz 404)."""
        return self._veri(self._istek("GET", f"/api/shell/{kabuk}/output?{self._konum(klasor)}&cursor={int(imlec)}&limit=65536")) or {}

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
                raise SunucuHatasi("OpenCode CLI bulunamadi (PATH ya da AKTAPOKUS_OPENCODE; kurulum: https://opencode.ai). OpenCode kullanmayacaksaniz Ayarlar > Roller'den kurulu bir CLI secin.")
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


def arac_calisiyor(mesajlar: list[dict]) -> bool:
    """Bitmemis arac var mi: uzun test/derleme token sayacini oynatmaz ama model takilmis demek degildir."""
    return any(isinstance(c, dict) and c.get("type") == "tool" and (c.get("state") or {}).get("status") in ("pending", "running")
               for m in mesajlar if m.get("type") == "assistant" for c in m.get("content") or [])


def olay_ilerlemesi(olay: Olay) -> dict | None:
    """OpenCode oturum olayinin arayuze giden karsiligi; gosterilmeyen olaylar None (yine de etkinlik sayilir)."""
    v = olay.veri
    if olay.tip == "session.text.delta":
        return {"tur": "metin", "parca": v.get("delta", "")}
    if olay.tip == "session.reasoning.delta":
        return {"tur": "dusunce", "parca": v.get("delta", "")}
    if olay.tip == "session.step.started":
        return {"tur": "durum", "durum": "bekliyor"}
    if olay.tip == "session.tool.input.started":
        return {"tur": "durum", "durum": "arac", "ad": v.get("name")}
    if olay.tip == "session.compaction.started":
        return {"tur": "durum", "durum": "ozetleniyor"}
    if olay.tip == "session.retry.scheduled":
        return {"tur": "durum", "durum": "yeniden", "deneme": v.get("attempt"), "hata": " ".join(_hata_metni(v.get("error")).split())[:160]}
    if olay.tip == "session.tool.called":
        return {"tur": "arac", "ad": v.get("name") or v.get("tool"), "girdi": v.get("input")}
    if olay.tip == "session.tool.success":
        return {"tur": "arac-sonuc"}
    if olay.tip == "session.usage.updated":
        return {"tur": "kullanim", "token": v.get("tokens")}
    if olay.tip.startswith("session.execution."):
        return {"tur": "bitti" if olay.tip != "session.execution.started" else "basladi", "durum": olay.tip.rsplit(".", 1)[-1]}
    return None


def _kabuk_olayi(olay: Olay, sid: str, etkinlik: dict) -> None:
    """Komut baslayinca/bitince izlenecek kabuk listesini gunceller. shell.* olaylari ust duzeyde oturum tasimaz."""
    v, kabuklar = olay.veri, etkinlik["kabuklar"]
    kimlik = None
    if olay.tip == "shell.created" and ((v.get("info") or {}).get("metadata") or {}).get("sessionID") == sid:
        kimlik = (v.get("info") or {}).get("id")
    elif olay.tip == "session.tool.progress" and olay.oturum == sid:
        kimlik = (v.get("metadata") or {}).get("shellID")
    elif olay.tip == "shell.exited" and v.get("id") in kabuklar:
        kabuklar.pop(v["id"], None)
        etkinlik["zaman"] = time.monotonic()
    if isinstance(kimlik, str) and re.fullmatch(r"[A-Za-z0-9_-]{3,80}", kimlik):  # URL'ye girer
        kabuklar.setdefault(kimlik, {"imlec": 0, "satir": "", "kalan": "", "baslangic": time.monotonic()})


def mesajlardan_beceriler(mesajlar: list[dict]) -> list[str]:
    """Asistan mesajlarinda cagrilan `skill` aracinin beceri kimlikleri (sirayla, tekrarsiz)."""
    bulunan: list[str] = []
    for m in sorted((m for m in mesajlar if m.get("type") == "assistant"), key=lambda m: (m.get("time") or {}).get("created", 0)):
        for c in m.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool" and c.get("name") == "skill":
                kimlik = ((c.get("state") or {}).get("input") or {}).get("id")
                if isinstance(kimlik, str) and kimlik and kimlik not in bulunan:
                    bulunan.append(kimlik)
    return bulunan


KOTA_DESENI = re.compile(r"free (usage|messages)|usage limit|rate limit|quota|too many requests|\b429\b", re.IGNORECASE)


def _hata_metni(v: object, derinlik: int = 0) -> str:
    """OpenCode hata nesnesi bicimleri degisebilir (metin, {message}, {data:{message}}, {name}); okunur bir metin cikarir."""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict) and derinlik < 3:
        for anahtar in ("message", "data", "error", "name"):
            m = _hata_metni(v.get(anahtar), derinlik + 1) if v.get(anahtar) is not None else ""
            if m:
                return m
    return ""


def mesajlardan_hata(mesajlar: list[dict]) -> str:
    """Asistan mesajlarinda OpenCode'un kendi hata metni varsa (ornek: 'You've used today's free messages. They reset at 3:00 AM.') onu doner."""
    for m in reversed([m for m in mesajlar if m.get("type") == "assistant"]):
        for aday in [m.get("error"), *(c.get("error") or c for c in (m.get("content") or []) if isinstance(c, dict) and (c.get("type") == "error" or c.get("error")))]:
            metin = _hata_metni(aday)
            if metin:
                return " ".join(metin.split())[:300]
    return ""


def hata_acikla(bilgi: dict, mesajlar: list[dict]) -> str:
    """Basarisiz OpenCode oturumunun nedeni: kota dolduysa bunu acikca yazar (eskiden yalniz outcome='failed' gorunurdu)."""
    neden = mesajlardan_hata(mesajlar) or _hata_metni(bilgi.get("error"))
    if neden and KOTA_DESENI.search(neden):
        return f"OpenCode ucretsiz kotasi doldu: {neden}"
    return f"OpenCode oturumu basarisiz bitti (outcome={bilgi.get('outcome')!r})" + (f": {neden}" if neden else "")


AZAMI_SUNUCU_ISTEMI = 200_000  # istem HTTP govdesiyle gider (komut satiri degil): 24.000'lik CLI siniri burada gecerli degil; 13 web sayfali otomasyon 38.000 karakter tutmustu


class SunucuCalistirici(Calistirici):
    """Kalici `opencode serve` uzerinden calistirir; sunucu cagrilar arasi acik kalir.

    Oturum kipi (`oturum_kipi`, Ayarlar > Genel > Konusma): 'tek' = proje + rol (model/agent) basina TEK OpenCode oturumu surdurulur (ayni projede
    konusurken her gorev yeni sayfa acmaz; 24 saat sonra ya da 'Yeni' ile yenilenir); 'yeni'/'hic' = her cagri yeni oturum (temiz baglam)."""

    ad = "opencode-sunucu"
    OTURUM_OMRU_SN = 14 * 24 * 3600  # sohbetler kalici
    oturum_surdurur = True
    oturum_kipi = "yeni"  # arayuz proje ayarindan (varsayilan "tek") atar; CLI/testlerde eski davranis
    sohbet = None  # verilirse oturum anahtari sohbet basina ayrilir

    def __init__(
        self,
        sunucu: Sunucu | None = None,
        istemci: Istemci | None = None,
        ilerleme: Callable[[dict], None] | None = None,
        izin_karari: str = "reject",
        yoklama_sn: float = 0.5,
        paylasilan: bool = False,
    ):
        self.mcp: tuple = ()
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

    def _dinleyici(self, istemci: Istemci, sid: str, durdur: threading.Event, bitti: threading.Event, etkinlik: dict) -> threading.Thread:
        """Oturumun her olayi `etkinlik` zamanini yeniler (zaman asimi buna bakar); ekran dinlemese de calisir."""
        ilerleme = self.ilerleme
        if ilerleme is None:
            bitti.set()
        adlar: dict = {}

        def calis() -> None:
            for olay in istemci.olaylar():
                if durdur.is_set():
                    return
                _kabuk_olayi(olay, sid, etkinlik)
                if olay.oturum != sid:
                    continue
                etkinlik["zaman"] = time.monotonic()
                if olay.tip.startswith("session.execution.") and not olay.tip.endswith(".started"):
                    bitti.set()
                karsilik = olay_ilerlemesi(olay)
                if olay.tip == "session.tool.input.started":
                    adlar[olay.veri.get("id")] = olay.veri.get("name")
                elif olay.tip == "session.tool.called" and karsilik and not karsilik["ad"]:  # gercek sunucu adi yalniz arac hazirlanirken bildirir
                    karsilik["ad"] = adlar.get(olay.veri.get("id"))
                if karsilik and ilerleme:
                    ilerleme(karsilik)

        t = threading.Thread(target=calis, daemon=True)
        t.start()
        return t

    def _kabuklari_izle(self, istemci: Istemci, klasor, etkinlik: dict) -> None:
        """Calisan komutlarin yeni ciktisi etkinlik sayilir, son satiri ekrana gider. Ciktisi olmayan komut da gecen sureyle gorunur."""
        for kabuk, d in list(etkinlik["kabuklar"].items()):
            try:
                c = istemci.kabuk_cikti(kabuk, klasor, d["imlec"])
            except SunucuHatasi:
                continue
            imlec = c.get("cursor")
            if isinstance(imlec, int) and imlec > d["imlec"]:
                d["imlec"], etkinlik["zaman"] = imlec, time.monotonic()
                parcalar = re.split(r"[\r\n]+", d["kalan"] + str(c.get("output") or ""))
                d["kalan"] = parcalar[-1][-200:]  # pytest -q gibi satir sonu vermeyen cikti parcalanmasin; uzayan satirda guncel olan sonudur
                satirlar = [x.strip() for x in parcalar if x.strip()]
                if satirlar:
                    d["satir"] = satirlar[-1][-200:]
            if self.ilerleme:
                self.ilerleme({"tur": "kabuk", "satir": d["satir"], "sure_sn": int(time.monotonic() - d["baslangic"])})

    # Sunucu sureci tum projeler icin ortak; 'bu proje icin su MCP uygulandi' bilgisi surec boyunca burada tutulur (config karmasi)
    _mcp_uygulanan: dict[tuple[str, str], str] = {}
    _mcp_kilit = threading.Lock()

    def _mcp_uygula(self, istemci: Istemci, klasor: Path) -> list[dict]:
        """Projede ETKIN sunuculari OpenCode'a tanitir, etkin olmayan (bizim kayitli) sunuculari kaldirir. Kullanicinin kendi
        opencode.json'daki sunuculara dokunmaz. Donus: sorunlu sunucular [{ad, hata}] (degerler/anahtarlar yazilmaz)."""
        from . import mcptanim

        kayitli = set(mcptanim.yukle())
        etkin = {t.ad: t for t in self.mcp}
        if not kayitli and not etkin:
            return []
        sorunlar: list[dict] = []
        try:
            mevcut = istemci.mcp_liste(klasor)
        except SunucuHatasi:
            return [{"ad": "*", "hata": "MCP listesi alinamadi"}] if etkin else []
        for ad in kayitli - set(etkin):
            if ad in mevcut:
                try:
                    istemci.mcp_sil(klasor, ad)
                except SunucuHatasi:
                    sorunlar.append({"ad": ad, "hata": "kaldirilamadi"})
                with self._mcp_kilit:
                    self._mcp_uygulanan.pop((str(klasor), ad), None)
        for ad, t in etkin.items():
            ayar = mcptanim.opencode_ayari(t)
            karma = json.dumps(ayar, sort_keys=True)
            anahtar = (str(klasor), ad)
            try:
                if ad in mevcut and self._mcp_uygulanan.get(anahtar) == karma:
                    continue
                if ad in mevcut:
                    istemci.mcp_sil(klasor, ad)
                istemci.mcp_ekle(klasor, ad, ayar)
                with self._mcp_kilit:
                    self._mcp_uygulanan[anahtar] = karma
            except SunucuHatasi as hata:
                mesaj = str(hata)
                for g in [*t.ortam.values(), *t.basliklar.values()]:
                    if g:
                        mesaj = mesaj.replace(g, "***")
                sorunlar.append({"ad": ad, "hata": mesaj[:160]})
        bitis = time.monotonic() + 30
        bekleyen = [ad for ad in etkin if ad not in {s["ad"] for s in sorunlar}]
        while bekleyen and time.monotonic() < bitis:
            try:
                durum = istemci.mcp_liste(klasor)
            except SunucuHatasi:
                break
            bekleyen = [ad for ad in bekleyen if (durum.get(ad) or {}).get("status") in (None, "pending")]
            if bekleyen:
                time.sleep(0.3)
        try:
            son = istemci.mcp_liste(klasor)
        except SunucuHatasi:
            son = {}
        for ad in etkin:
            d = son.get(ad) or {}
            if d.get("status") == "failed":
                sorunlar.append({"ad": ad, "hata": str(d.get("error") or "baglanilamadi")[:160]})
        return sorunlar

    @staticmethod
    def oturum_yolu(klasor) -> Path:
        return Path(klasor) / AYAR_KLASORU / "opencode-oturum.json"

    def _oturum_oku(self, klasor, anahtar: str) -> str | None:
        try:
            k = json.loads(self.oturum_yolu(klasor).read_text(encoding="utf-8"))[anahtar]
            sid, zaman = k["id"], float(k["zaman"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", sid) or time.time() - zaman > self.OTURUM_OMRU_SN:
            return None  # proje klasorundeki dosya guvenilmez: yalniz kimlik bicimi URL'ye girer
        return sid

    def _oturum_anahtari(self, model, agent) -> str:
        return f"{self.sohbet + '#' if self.sohbet else ''}{model or ''}|{agent or ''}"  # oturum sohbet basina

    def oturum_sifirla(self, klasor, model=None, agent=None) -> None:
        self._oturum_yaz(klasor, self._oturum_anahtari(model, agent), None)

    def _oturum_yaz(self, klasor, anahtar: str, sid: str | None) -> None:
        try:
            yol = self.oturum_yolu(klasor)
            try:
                d = json.loads(yol.read_text(encoding="utf-8"))
                d = d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                d = {}
            if sid:
                d[anahtar] = {"id": sid, "zaman": time.time()}
            else:
                d.pop(anahtar, None)
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(json.dumps(d), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _token_fark(simdi: dict, once: dict) -> dict:
        """Surdurulen oturumun sayaclari birikimlidir: yalniz bu cagrinin kullandigi token."""
        def f(a, b):
            return max(0, int(a or 0) - int(b or 0))
        return {
            "input": f(simdi.get("input"), once.get("input")),
            "output": f(simdi.get("output"), once.get("output")),
            "reasoning": f(simdi.get("reasoning"), once.get("reasoning")),
            "cache": {"read": f((simdi.get("cache") or {}).get("read"), (once.get("cache") or {}).get("read"))},
        }

    @classmethod
    def _token_alanlari(cls, simdi: dict, once: dict) -> dict:
        t = cls._token_fark(simdi, once) if once else simdi
        return {
            "token_girdi": int(t.get("input") or 0),
            "token_cikti": int(t.get("output") or 0) + int(t.get("reasoning") or 0),
            "token_onbellek": int((t.get("cache") or {}).get("read") or 0),
        }

    @staticmethod
    def _modelleri_kesfet(istemci, model: str | None) -> None:
        """OpenCode sunucusu yerel/ucuncu taraf modelleri (ornek: ollama/qwen3:8b) ilk model listesi istegiyle KESFEDER; liste hic istenmediyse oturum
        'Model unavailable' ile basarisiz olur (gercek deneme). Opencode'un kendi modelleri icin gerekmez. Sunucu basina bir kez; hata gorevi bozmaz."""
        if not model or model.split("/", 1)[0] == "opencode" or getattr(istemci, "_modeller_kesfedildi", False):
            return
        try:
            istemci.modeller()
            istemci._modeller_kesfedildi = True
        except Exception:
            pass

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        baslangic = time.monotonic()
        anahtar = self._oturum_anahtari(model, agent)
        self.hafiza_eklendi = False
        once_tokens: dict = {}
        once_mesajlar: set | None = None
        sid = None
        try:
            _istemi_denetle(istem, AZAMI_SUNUCU_ISTEMI)
            istemci = self._al()
            self._modelleri_kesfet(istemci, model)
            for sorun in self._mcp_uygula(istemci, Path(klasor)):
                if self.ilerleme:
                    self.ilerleme({"tur": "mcp-sorun", "ad": sorun["ad"], "hata": sorun["hata"]})
            if self.oturum_kipi == "tek":
                aday = self._oturum_oku(klasor, anahtar)
                if aday:
                    try:  # surdurulecek oturum hala var ve bos mu? yoksa yenisi acilir
                        if aday not in istemci.aktif_oturumlar():
                            once_tokens = (istemci.oturum_al(aday) or {}).get("tokens") or {}
                            once_mesajlar = {m.get("id") for m in istemci.mesajlar(aday, limit=1000)}
                            sid = aday
                    except Exception:
                        sid, once_tokens, once_mesajlar = None, {}, None
            if sid is None:
                sid = istemci.oturum_olustur(klasor, model=model, agent=agent, baslik="aktapokus")
                if self.oturum_kipi == "tek":
                    self._oturum_yaz(klasor, anahtar, sid)
                    if self.yeni_oturum_istemi:  # yeni oturum hafizasiz baslamasin
                        istem = f"{self.yeni_oturum_istemi}\n\n{istem}"
                        self.hafiza_eklendi = True
        except Exception as hata:
            return CalistirmaSonucu(False, hata=f"{type(hata).__name__}: {hata}", sure_sn=time.monotonic() - baslangic)
        durdur, bitti = threading.Event(), threading.Event()
        self._aktif_sid = sid
        etkinlik: dict = {"zaman": baslangic, "kabuklar": {}}
        self._dinleyici(istemci, sid, durdur, bitti, etkinlik)
        try:
            istemci.mesaj_gonder(sid, istem)
            # Zaman asimi HAREKETSIZLIK sayilir: oturumun her olayi (dusunme, arac, yeniden deneme), token sayaci ya da calisan komutun ciktisi degistikce
            # sure yeniden baslar; token yalniz adim sonunda artar, tek basina yetmez. Ilerleme gosteren gorev (gercek durum: 79 arac cagrisi, derleme,
            # ekran goruntusu) 'zaman asimi' ile oldurulmez. Mutlak ust sinir: 4 kat (en cok 4 saat).
            mutlak = baslangic + min(zaman_asimi_sn * 4, 14400)
            son_hareket, son_belirti, sonraki_yoklama = baslangic, None, 0.0
            islenen_izinler: set[str] = set()
            while True:
                time.sleep(self.yoklama_sn)
                simdi = time.monotonic()
                if simdi >= sonraki_yoklama:
                    sonraki_yoklama = simdi + min(5.0, max(0.2, zaman_asimi_sn / 4))
                    try:
                        belirti = json.dumps((istemci.oturum_al(sid) or {}).get("tokens"), sort_keys=True, default=str)
                    except (SunucuHatasi, TypeError, ValueError):
                        belirti = None
                    if belirti is not None and belirti != son_belirti:
                        son_belirti, son_hareket = belirti, simdi
                    self._kabuklari_izle(istemci, klasor, etkinlik)
                son_hareket = max(son_hareket, etkinlik["zaman"])
                for izin in istemci.izinler(sid):
                    if izin.get("id") and izin["id"] not in islenen_izinler:
                        islenen_izinler.add(izin["id"])
                        istemci.izin_yanitla(sid, izin["id"], self.izin_karari, "Aktapokus: izin istegi otomatik yanitlandi")
                if sid not in istemci.aktif_oturumlar():
                    break
                if son_hareket + zaman_asimi_sn < simdi <= mutlak:
                    try:
                        if arac_calisiyor(istemci.mesajlar(sid, limit=20)):  # gercek durum: tam test takimi 900 sn sessiz kaldi, gorev bosuna olduruldu
                            son_hareket = simdi
                    except SunucuHatasi:
                        pass
                if simdi > son_hareket + zaman_asimi_sn or simdi > mutlak:
                    try:
                        istemci.durdur(sid)
                    except SunucuHatasi:
                        pass
                    neden = f"Zaman asimi ({zaman_asimi_sn} sn)" if simdi <= mutlak else f"Zaman asimi (toplam sure siniri {int(mutlak - baslangic)} sn)"
                    try:  # yarida kesilen gorev de token harcadi: 0 gorunmesin
                        harcanan = self._token_alanlari((istemci.oturum_al(sid) or {}).get("tokens") or {}, once_tokens)
                    except SunucuHatasi:
                        harcanan = {}
                    return CalistirmaSonucu(False, hata=neden, sure_sn=time.monotonic() - baslangic, **harcanan)
            bilgi = istemci.oturum_al(sid)
            mesajlar = istemci.mesajlar(sid, limit=1000 if once_mesajlar is not None else 100)
            if once_mesajlar:  # surdurulen oturum: yalniz bu cagrinin yeni mesajlari
                yeni = [m for m in mesajlar if m.get("id") not in once_mesajlar]
                mesajlar = yeni or mesajlar
            metin = mesajlardan_metin(mesajlar)
            kullanilan = mesajlardan_beceriler(mesajlar)
            if kullanilan and self.ilerleme is not None:
                self.ilerleme({"tur": "beceri", "adlar": kullanilan})
        except SunucuHatasi as hata:
            self._oturum_yaz(klasor, anahtar, None) if self.oturum_kipi == "tek" else None
            return CalistirmaSonucu(False, hata=str(hata), sure_sn=time.monotonic() - baslangic)
        finally:
            self._aktif_sid = None
            bitti.wait(timeout=1.5)  # bitis olayi, aktiflik kapandiktan biraz sonra gelebilir
            durdur.set()
        sonuc = CalistirmaSonucu(
            ok=bilgi.get("outcome") == "succeeded",
            metin=metin,
            sure_sn=time.monotonic() - baslangic,
            **self._token_alanlari(bilgi.get("tokens") or {}, once_tokens),
        )
        if not sonuc.ok:
            if self.oturum_kipi == "tek":
                self._oturum_yaz(klasor, anahtar, None)  # basarisiz oturum surdurulmez
            sonuc.hata = hata_acikla(bilgi, mesajlar)
        return sonuc
