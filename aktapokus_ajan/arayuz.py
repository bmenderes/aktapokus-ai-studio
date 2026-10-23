"""Canli arayuz sunucusu: yalniz 127.0.0.1, token'li JSON API + SSE olay akisi + tek sayfa arayuz + ayri portta guvenli onizleme.

Guvenlik:
- Tum /api/* istekleri `X-Aktapokus-Token` ister (rastgele, calisma basina; URL parcasinda (#t=...) verilir).
- Host basligi yalnizca 127.0.0.1/localhost olabilir (DNS rebinding'e karsi). CORS yok.
- Dosya okuma: proje klasoru icinde, gizli/nokta ile baslayan yollar ve .env/anahtar dosyalari reddedilir.
- Onizleme AYRI portta, proje dosyalarini salt okunur sunar. Ayri port = ayri kokendir: onizlenen sayfa uygulamanin
  token'ina (sessionStorage) erisemez, API'ye CORS ile istek atamaz (ozel baslik + preflight). iframe sandbox'i ust sayfaya
  gitmeyi ve acilir pencereyi engeller. (Opak-kokenli CSP sandbox, uygulamanin tarayici panelinde cerceveyi bos biraktigi icin kullanilmadi.)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from . import ciktilar, clitanim, guard, istatistik, projeler, snapshot
from .config import AyarHatasi, ayar_coz, ayar_yolu, ayar_yukle
from .klasor import KlasorHatasi, guvenli_klasor
from .pipeline import HatHatasi, _kayit_klasoru, calistir_hat, son_kayit
from .proje import GitGerekli, hazirla as proje_hazirla
from .runners import Calistirici, CalistiriciHatasi, calistirici_olustur, hepsini_kapat

ATLANAN_KLASORLER = {".git", "node_modules", "__pycache__", ".aktapokus", ".opencode", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
GIZLI_UZANTILAR = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")
GIZLI_ADLAR = ("id_rsa", "id_ed25519", ".npmrc", ".pypirc", "credentials")
AZAMI_DOSYA_SAYISI = 1500
AZAMI_OKUMA = 300_000
AZAMI_GOVDE = 1_000_000
WEB = Path(__file__).with_name("web")


def gizli_mi(yol_parcalari: list[str]) -> bool:
    """Nokta ile baslayan (.git, .env, .opencode...) herhangi bir parca ya da bilinen sir dosyasi."""
    for p in yol_parcalari:
        k = p.lower()
        if k.startswith(".") or k.endswith(GIZLI_UZANTILAR) or any(k.startswith(a) for a in GIZLI_ADLAR):
            return True
    return False


def guvenli_goreli(klasor: Path, goreli: str) -> Path:
    """Proje icindeki, gizli olmayan bir yolu cozer; aksi halde ValueError."""
    goreli = (goreli or "").replace("\\", "/").lstrip("/")
    parcalar = [p for p in goreli.split("/") if p]
    if not parcalar or any(p in (".", "..") for p in parcalar) or ":" in goreli:
        raise ValueError("Gecersiz yol")
    if gizli_mi(parcalar):
        raise ValueError("Bu yol gizli/hassas; arayuz okumaz")
    hedef = (klasor / Path(*parcalar)).resolve()
    if klasor.resolve() not in hedef.parents:
        raise ValueError("Yol proje klasorunun disina cikiyor")
    return hedef


def dosyalari_tara(klasor: Path) -> list[dict]:
    sonuc: list[dict] = []
    gercek_kok = os.path.realpath(klasor)
    for kok, altlar, dosyalar in os.walk(klasor):
        # sembolik baglanti/junction ile proje disina cikan klasorlere inilmez
        altlar[:] = sorted(
            a for a in altlar
            if a not in ATLANAN_KLASORLER and not a.startswith(".") and os.path.realpath(os.path.join(kok, a)).startswith(gercek_kok + os.sep)
        )
        for d in sorted(dosyalar):
            if gizli_mi([d]):
                continue
            tam = Path(kok) / d
            try:
                st = tam.stat()
            except OSError:
                continue
            sonuc.append({"yol": tam.relative_to(klasor).as_posix(), "boyut": st.st_size, "zaman": st.st_mtime_ns})
            if len(sonuc) >= AZAMI_DOSYA_SAYISI:
                return sonuc
    return sonuc


def imza(dosyalar: list[dict]) -> str:
    h = hashlib.sha256()
    for d in dosyalar:
        h.update(f"{d['yol']}|{d['zaman']}|{d['boyut']}\n".encode())
    return h.hexdigest()[:16]


class OlayAkisi:
    """Bellek ici olay gecmisi + SSE aboneleri. Olaylar sirali kimlik alir; yeni baglanan gecmisi yeniden oynatir."""

    def __init__(self, azami: int = 800):
        self.gecmis: list[dict] = []
        self.azami = azami
        self.kilit = threading.Lock()
        self.aboneler: list[queue.Queue] = []
        self.sayac = 0

    def yayinla(self, olay: dict) -> dict:
        with self.kilit:
            self.sayac += 1
            olay = {**olay, "id": self.sayac, "zaman": time.strftime("%H:%M:%S")}
            self.gecmis.append(olay)
            del self.gecmis[: -self.azami]
            for q in list(self.aboneler):
                q.put(olay)
        return olay

    def abone_ol(self, son_id: int = 0) -> tuple[queue.Queue, list[dict]]:
        q: queue.Queue = queue.Queue()
        with self.kilit:
            tekrar = [o for o in self.gecmis if o["id"] > son_id]
            self.aboneler.append(q)
        return q, tekrar

    def ayril(self, q: queue.Queue) -> None:
        with self.kilit:
            if q in self.aboneler:
                self.aboneler.remove(q)


@dataclass
class Kosu:
    kimlik: str
    gorev: str
    durum: str = "plan"  # plan | calisiyor | karar-bekliyor | bitti | reddedildi
    iptal: threading.Event = field(default_factory=threading.Event)
    karar_olayi: threading.Event = field(default_factory=threading.Event)
    karar: bool = False
    sonuc: object = None


class UygulamaHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.kod = kod


class Uygulama:
    def __init__(
        self,
        calistirici_uret: Callable[[str], Calistirici] = calistirici_olustur,
        token: str | None = None,
        saglayici_istemci_uret: Callable[[], object] | None = None,
    ):
        self.calistirici_uret = calistirici_uret
        self._saglayici_istemci_uret = saglayici_istemci_uret
        self.telegram = None  # TelegramYoneticisi: ilk kullanimda olusur (Ayarlar > Telegram)
        self.token = token or secrets.token_urlsafe(24)
        self.bus = OlayAkisi()
        self.klasor: Path | None = None
        self.kosu: Kosu | None = None
        self.kilit = threading.RLock()
        self.aktif_calistirici: Calistirici | None = None
        self.son_hat: dict = {}

    # --- proje ---
    def klasor_sec(self, yol: str, git_baslat: bool = False) -> dict:
        if not Path(str(yol)).expanduser().is_absolute():
            # Goreli yol, botun/arayuzun calistigi klasore gore cozulur: yanlis klasorde calisma riski (gercek denemede yasandi)
            raise UygulamaHatasi("Klasor yolu TAM olmali (ornek: C:\\Users\\adiniz\\Desktop\\proje); goreli yol belirsiz.", 400)
        with self.kilit:
            if self.kosu and self.kosu.durum in ("calisiyor", "karar-bekliyor"):
                raise UygulamaHatasi("Bir gorev calisirken klasor degistirilemez", 409)
            try:
                sonuc = proje_hazirla(yol, git_baslat=git_baslat)
            except GitGerekli:
                raise UygulamaHatasi("git_gerekli", 428) from None
            except (KlasorHatasi, snapshot.GitHatasi, guard.KoruyucuHatasi) as hata:
                raise UygulamaHatasi(str(hata)) from None
            self.klasor, self.kosu, self.son_hat = sonuc["klasor"], None, {}
            try:
                projeler.ekle_veya_guncelle(self.klasor)  # son projeler listesi (ortam cipi); hata klasor secimini engellemez
            except OSError:
                pass
            self.bus.yayinla({"tur": "klasor", "klasor": str(self.klasor), "git": sonuc["git"], "koruyucu": sonuc["koruyucu"]})
            return self.durum()

    def _klasor(self) -> Path:
        if self.klasor is None:
            raise UygulamaHatasi("Once bir klasor secin", 409)
        return self.klasor

    def ayar_ozeti(self) -> dict | None:
        if self.klasor is None:
            return None
        try:
            a = ayar_yukle(self.klasor)
        except AyarHatasi as hata:
            return {"hata": str(hata)}
        return {
            "akis": list(a.akis),
            "roller": {ad: {"calistirici": r.calistirici, "model": r.model, "dogrulama": r.dogrulama} for ad, r in a.roller.items()},
            "butce_token": a.butce_token,
            "azami_duzeltme": a.azami_duzeltme,
        }

    def klon_bekleyen(self) -> int | None:
        try:
            from aktapokus_klon.depo import Depo  # opsiyonel paket

            return len(list(Depo().bekleyen.glob("*/*.md")))
        except Exception:
            return None

    def durum(self) -> dict:
        d: dict = {"klasor": str(self.klasor) if self.klasor else None, "ayar": self.ayar_ozeti(), "klon_bekleyen": self.klon_bekleyen()}
        if self.klasor:
            d["git"] = snapshot.hazir_mi(self.klasor)
            d["koruyucu_eksik"] = guard.dogrula(self.klasor)
            k = son_kayit(self.klasor)
            d["son_kayit"] = {x: k.get(x) for x in ("id", "zaman", "gorev", "durum", "token_toplam")} if k else None
        d["kosu"] = {"kimlik": self.kosu.kimlik, "gorev": self.kosu.gorev, "durum": self.kosu.durum} if self.kosu else None
        return d

    def ayar_oku(self) -> dict:
        yol = ayar_yolu(self._klasor())
        return json.loads(yol.read_text(encoding="utf-8"))

    def ayar_yaz(self, veri: object) -> None:
        klasor = self._klasor()
        if self.kosu and self.kosu.durum in ("calisiyor", "karar-bekliyor"):
            raise UygulamaHatasi("Gorev calisirken ayar degistirilemez", 409)
        try:
            ayar_coz(veri)
        except AyarHatasi as hata:
            raise UygulamaHatasi(str(hata)) from None
        ayar_yolu(klasor).write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- CLI'lar: yerlesik + tanimla eklenenler. Yazma islemleri YALNIZ bu yerel, belirtec korumali arayuzden yapilir (Telegram'dan degil):
    # bir tanim bu bilgisayarda program calistirmak demektir.
    def clilar(self) -> list[dict]:
        return clitanim.listele()

    def cli_kaydet(self, veri: object) -> dict:
        try:
            tanim = clitanim.tanim_coz(veri)
        except clitanim.TanimHatasi as hata:
            raise UygulamaHatasi(str(hata)) from None
        clitanim.kaydet(tanim)
        return {"tamam": True, "ad": tanim.ad}

    def cli_sil(self, ad: object) -> dict:
        if not isinstance(ad, str) or ad in clitanim.YERLESIK:
            raise UygulamaHatasi("Yerlesik CLI silinemez")
        if self.klasor:
            try:
                kullanan = [r.ad for r in ayar_yukle(self.klasor).roller.values() if r.calistirici == ad]
            except AyarHatasi:
                kullanan = []
            if kullanan:
                raise UygulamaHatasi(f"'{ad}' su rollerde kullaniliyor: {', '.join(kullanan)}. Once rolleri baska CLI'a gecirin.", 409)
        if not clitanim.sil(ad):
            raise UygulamaHatasi("Boyle bir CLI yok", 404)
        return {"tamam": True}

    def cli_dene(self, ad: object, model: object = None) -> dict:
        """CLI'i BOS gecici bir klasorde, yazma izni olmadan tek kucuk istemle dener (kullanici dugmeye basinca; token harcar)."""
        import tempfile

        if not isinstance(ad, str) or (model is not None and not isinstance(model, str)):
            raise UygulamaHatasi("Gecersiz istek")
        if self.kosu and self.kosu.durum in ("calisiyor", "karar-bekliyor"):
            raise UygulamaHatasi("Gorev calisirken CLI denenemez", 409)
        if not model:  # model verilmediyse onerilenlerin ILKI (ucuz/ucretsiz olan basa yazilir); varsayilan model pahali olabilir
            onerilen = next((c["modeller"] for c in clitanim.listele() if c["ad"] == ad and c["modeller"]), [])
            model = onerilen[0] if onerilen else None
        try:
            c = calistirici_olustur(ad)
            with tempfile.TemporaryDirectory(prefix="aktapokus-dene-") as gecici:
                r = c.calistir("Yalnizca 'tamam' yaz, baska bir sey yapma.", Path(gecici), model=model or None, zaman_asimi_sn=90, onayli=False)
        except CalistiriciHatasi as hata:
            return {"ok": False, "hata": str(hata)}
        return {"ok": r.ok, "metin": r.metin[:300], "hata": r.hata, "sure_sn": round(r.sure_sn, 1), "token": r.token_yeni}

    # --- model saglayicilari (OpenCode): saglayici sec -> API anahtari yapistir -> modeller listelenir ---
    # Anahtar yalniz bu yerel, belirtec korumali arayuzden gelir; dogrudan yerel OpenCode'a iletilir. Burada SAKLANMAZ, gunluge/olaylara
    # yazilmaz, yanitta/hata mesajinda geri verilmez. Telegram bu metotlari cagirmaz.
    ONERILEN_SAGLAYICILAR = ("google", "openrouter", "openai", "anthropic", "deepseek", "groq", "mistral", "xai")

    def _saglayici_istemcisi(self):
        if self._saglayici_istemci_uret:
            return self._saglayici_istemci_uret()
        return calistirici_olustur("opencode-sunucu")._al()  # kalici OpenCode sunucusu (ilk cagrida baslar, birkac sn)

    def _sunucu_hatasi(self, hata: Exception, gizli: str = "") -> UygulamaHatasi:
        mesaj = str(hata)
        if gizli:
            mesaj = mesaj.replace(gizli, "***")
        return UygulamaHatasi(f"OpenCode: {mesaj}"[:400], 502)

    def saglayicilar(self) -> list[dict]:
        from .sunucu import SunucuHatasi

        try:
            ham = self._saglayici_istemcisi().saglayicilar()
        except (SunucuHatasi, CalistiriciHatasi) as hata:
            raise self._sunucu_hatasi(hata) from None
        cikti = []
        for x in ham:
            yontemler = x.get("methods") or []
            baglantilar = [{"id": b.get("id"), "label": b.get("label") or ""} for b in x.get("connections") or [] if b.get("type") == "credential" and b.get("id")]
            cikti.append({
                "id": x.get("id"), "ad": x.get("name") or x.get("id"),
                "anahtarla": any(m.get("type") == "key" for m in yontemler),
                "ortam": next((m.get("names") or [] for m in yontemler if m.get("type") == "env"), []),
                "bagli": bool(x.get("connections")), "baglantilar": baglantilar,
            })
        oneri = {a: i for i, a in enumerate(self.ONERILEN_SAGLAYICILAR)}
        cikti.sort(key=lambda c: (not c["bagli"], oneri.get(c["id"], 99), str(c["ad"]).lower()))
        return cikti

    def modeller(self) -> list[dict]:
        from .sunucu import SunucuHatasi

        try:
            ham = self._saglayici_istemcisi().modeller()
        except (SunucuHatasi, CalistiriciHatasi) as hata:
            raise self._sunucu_hatasi(hata) from None
        return sorted(
            ({"id": f"{m['providerID']}/{m['modelID']}", "saglayici": m["providerID"], "ad": m.get("name") or m["modelID"]} for m in ham if m.get("providerID") and m.get("modelID")),
            key=lambda m: (m["saglayici"], m["id"]),
        )

    def saglayici_baglan(self, saglayici: object, anahtar: object, etiket: object = None) -> dict:
        from .sunucu import SAGLAYICI_DESENI, SunucuHatasi

        if not isinstance(saglayici, str) or not SAGLAYICI_DESENI.match(saglayici):
            raise UygulamaHatasi("Gecersiz saglayici")
        if not isinstance(anahtar, str):
            raise UygulamaHatasi("Anahtar metin olmali")
        anahtar = anahtar.strip()
        if not anahtar or len(anahtar) > 4096 or any(c.isspace() or ord(c) < 32 for c in anahtar):
            raise UygulamaHatasi("Anahtar bos olamaz, bosluk/satir sonu icermemeli (4096 karakteri gecmemeli)")
        if etiket is not None and (not isinstance(etiket, str) or len(etiket) > 80):
            raise UygulamaHatasi("Etiket en fazla 80 karakter metin olmali")
        try:
            istemci = self._saglayici_istemcisi()
            istemci.anahtar_baglan(saglayici, anahtar, (etiket or "").strip() or None)
            sayi = sum(1 for m in istemci.modeller() if m.get("providerID") == saglayici)
        except (SunucuHatasi, CalistiriciHatasi) as hata:
            raise self._sunucu_hatasi(hata, anahtar) from None
        return {"tamam": True, "model_sayisi": sayi, "uyari": "Anahtar dogrulanmadi; 'Dene' ile sinayin." if sayi else "Bu saglayici icin model bulunamadi."}

    def saglayici_kaldir(self, baglanti: object) -> dict:
        from .sunucu import SunucuHatasi

        if not isinstance(baglanti, str):
            raise UygulamaHatasi("Gecersiz baglanti")
        try:
            self._saglayici_istemcisi().baglanti_kaldir(baglanti)
        except (SunucuHatasi, CalistiriciHatasi) as hata:
            raise self._sunucu_hatasi(hata) from None
        return {"tamam": True}

    # --- Telegram botu ARAYUZLE AYNI SURECTE (Ayarlar > Telegram): baslat/durdur, otomatik, eslestirme, kokler. Yalniz yerel arayuz; telefondan degil. ---
    def _telegram(self):
        from .telegram_yonetici import TelegramYoneticisi

        if self.telegram is None:
            self.telegram = TelegramYoneticisi(self)
        return self.telegram

    def telegram_islem(self, islem: str, g: dict) -> dict:
        from .telegram_yonetici import YoneticiHatasi

        y = self._telegram()
        try:
            if islem == "durum":
                return y.durum()
            if islem == "baslat":
                return y.baslat()
            if islem == "durdur":
                return y.durdur()
            if islem == "eslestir":
                return y.yeni_eslestirme()
            if islem == "otomatik":
                return y.otomatik_ayarla(bool(g.get("acik")))
            if islem == "kok":
                return y.kok_ekle(str(g.get("yol", "")))
            if islem == "kok-sil":
                return y.kok_sil(str(g.get("yol", "")))
        except YoneticiHatasi as hata:
            raise UygulamaHatasi(str(hata)) from None
        raise UygulamaHatasi("Bilinmeyen Telegram işlemi", 404)

    # --- ciktilar (Outputs): projede gorevlerle olusan/degisen dosyalarin birlesik listesi (yalniz okur) ---
    def ciktilar(self) -> dict:
        klasor = self._klasor()
        liste = ciktilar.topla(klasor, ciktilar.kayitlari_oku(klasor), guvenli_goreli)
        return {"ciktilar": liste, "toplam": len(liste)}

    # --- gorev gecmisi (sol kenar cubugu): .aktapokus/kayitlar altindaki calistirma kayitlari, yalniz okunur ---
    def gecmis(self, adet: int = 30) -> list[dict]:
        klasoru = _kayit_klasoru(self._klasor())
        dosyalar = sorted(klasoru.glob("*.json"), reverse=True)[: max(1, min(int(adet), 100))] if klasoru.is_dir() else []
        cikti = []
        for d in dosyalar:
            try:
                k = json.loads(d.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cikti.append({
                "id": k.get("id"), "zaman": k.get("zaman"), "gorev": str(k.get("gorev", ""))[:200], "durum": k.get("durum"),
                "token_toplam": k.get("token_toplam", 0), "akis": k.get("akis", []), "degisen_sayisi": len(k.get("degisen") or {}),
            })
        return cikti

    def gecmis_kaydi(self, kimlik: object) -> dict:
        if not isinstance(kimlik, str) or not re.fullmatch(r"[0-9a-zA-Z_-]{1,64}", kimlik):
            raise UygulamaHatasi("Gecersiz kayit kimligi")
        yol = _kayit_klasoru(self._klasor()) / f"{kimlik}.json"
        try:
            return json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise UygulamaHatasi("Kayit bulunamadi", 404) from None

    # --- istatistik: gorev kayitlarindan harcama, hata siniflari, model degistirme onerileri (yalniz okur) ---
    def istatistik(self, kapsam: str = "proje") -> dict:
        if kapsam not in ("proje", "tum"):
            raise UygulamaHatasi("kapsam 'proje' ya da 'tum' olmali")
        if kapsam == "proje":
            klasorler = [self._klasor()]
        else:
            klasorler = istatistik.bilinen_klasorler(self.klasor)
        veri = istatistik.ozet(istatistik.kayitlari_oku(klasorler))
        roller = None
        if self.klasor:
            try:
                roller = {r.ad: {"calistirici": r.calistirici, "model": r.model} for r in ayar_yukle(self.klasor).roller.values()}
            except AyarHatasi:
                roller = None
        adaylar = []
        for c in clitanim.listele():
            if not c["kurulu"] or c["ad"] == "opencode":  # 'opencode-sunucu' varsayilan; ikisini birden onermeyelim
                continue
            for m in (c["modeller"] or [None]):
                adaylar.append({"calistirici": c["ad"], "model": m, "ucretsiz": bool(m and "free" in m.lower())})
        veri["oneriler"] = istatistik.oneriler(veri, roller, adaylar)
        veri["kapsam"] = kapsam
        veri["proje_sayisi"] = len(klasorler)
        return {k: v for k, v in veri.items() if not k.startswith("_")}

    # --- gorev akisi: plan -> onay -> calisma -> karar ---
    def gorev_olustur(self, gorev: str) -> dict:
        klasor = self._klasor()
        if not isinstance(gorev, str) or not gorev.strip():
            raise UygulamaHatasi("Gorev bos olamaz")
        with self.kilit:
            if self.kosu and self.kosu.durum in ("plan", "calisiyor", "karar-bekliyor"):
                raise UygulamaHatasi("Zaten bir gorev var (onay/calisma/karar bekliyor)", 409)
            try:
                ayar = ayar_yukle(klasor)
            except AyarHatasi as hata:
                raise UygulamaHatasi(str(hata)) from None
            self.kosu = Kosu(kimlik=secrets.token_hex(4), gorev=gorev.strip())
            plan = {
                "tur": "plan",
                "kosu": self.kosu.kimlik,
                "gorev": self.kosu.gorev,
                "adimlar": [{"rol": r.ad, "calistirici": r.calistirici, "model": r.model, "dogrulama": r.dogrulama} for r in ayar.rol_sirasi()],
                "butce": ayar.butce_token,
                "azami_duzeltme": ayar.azami_duzeltme,
            }
            self.bus.yayinla(plan)
            return plan

    def _kosu(self, kimlik: str, durumlar: tuple[str, ...]) -> Kosu:
        if not self.kosu or self.kosu.kimlik != kimlik:
            raise UygulamaHatasi("Gorev bulunamadi", 404)
        if self.kosu.durum not in durumlar:
            raise UygulamaHatasi(f"Gorev su an '{self.kosu.durum}' durumunda", 409)
        return self.kosu

    def onayla(self, kimlik: str) -> None:
        with self.kilit:
            kosu = self._kosu(kimlik, ("plan",))
            kosu.durum = "calisiyor"
        threading.Thread(target=self._kos, args=(kosu,), daemon=True).start()

    def reddet(self, kimlik: str) -> None:
        with self.kilit:
            kosu = self._kosu(kimlik, ("plan",))
            kosu.durum = "reddedildi"
        self.bus.yayinla({"tur": "bitti", "durum": "reddedildi", "mesaj": "Plan onaylanmadi; hicbir sey calistirilmadi.", "kosu": kimlik})

    def karar_ver(self, kimlik: str, korunsun: bool) -> None:
        with self.kilit:
            kosu = self._kosu(kimlik, ("karar-bekliyor",))
            kosu.karar = bool(korunsun)
        kosu.karar_olayi.set()

    def durdur(self, kimlik: str) -> bool:
        with self.kilit:
            kosu = self._kosu(kimlik, ("calisiyor", "karar-bekliyor"))
        kosu.iptal.set()
        if kosu.durum == "karar-bekliyor":
            kosu.karar = False  # fark karari beklerken durdurma = geri al
            kosu.karar_olayi.set()
        self.bus.yayinla({"tur": "durduruluyor", "kosu": kimlik})
        r = self.aktif_calistirici
        return bool(r and r.durdur())

    def _canli(self, e: dict) -> None:
        self.bus.yayinla({**e, "tur": "canli", "alt": e.get("tur")})

    def _kos(self, kosu: Kosu) -> None:
        klasor = self._klasor()

        def uret(ad: str) -> Calistirici:
            r = self.calistirici_uret(ad)
            self.aktif_calistirici = r
            if hasattr(r, "ilerleme"):
                r.ilerleme = self._canli
            return r

        def onay(_soru: str) -> bool:
            kosu.durum = "karar-bekliyor"
            self.bus.yayinla({"tur": "karar-bekleniyor", "kosu": kosu.kimlik})
            kosu.karar_olayi.wait()
            kosu.durum = "calisiyor"
            return kosu.karar

        def olay(e: dict) -> None:
            if e.get("tur") == "fark":  # karar beklerken de (Telegram /fark, arayuz dosya agaci) degisiklikler gorulebilsin
                self.son_hat = {"once": e["once"], "sonra": e["sonra"], "degisen": e["degisen"], "durum": e.get("durum")}
            if e.get("tur") == "bitti":
                kosu.durum = "bitti"  # istemci 'bitti' olayini gorunce /api/durum'u okuyacak: onceden guncel olmali
            self.bus.yayinla({**e, "kosu": kosu.kimlik})

        try:
            ayar = ayar_yukle(klasor)
            kosu.sonuc = calistir_hat(klasor, kosu.gorev, ayar, uret, onay, bildir=lambda m: self.bus.yayinla({"tur": "gunluk", "mesaj": m}), olay=olay, iptal=kosu.iptal)
            self.son_hat = {"once": kosu.sonuc.once, "sonra": kosu.sonuc.sonra, "degisen": kosu.sonuc.degisen, "durum": kosu.sonuc.durum}
        except (HatHatasi, KlasorHatasi, AyarHatasi, snapshot.GitHatasi, CalistiriciHatasi) as hata:
            self.bus.yayinla({"tur": "bitti", "durum": "hata", "mesaj": str(hata), "kosu": kosu.kimlik})
        except Exception as hata:  # arayuz sunucusu hicbir hatayla dusmesin
            self.bus.yayinla({"tur": "bitti", "durum": "hata", "mesaj": f"Beklenmeyen hata: {type(hata).__name__}: {hata}", "kosu": kosu.kimlik})
        finally:
            kosu.durum = "bitti"
            r, self.aktif_calistirici = self.aktif_calistirici, None
            if r is not None and hasattr(r, "ilerleme"):
                r.ilerleme = None

    # --- dosya islemleri ---
    def dosyalar(self) -> dict:
        klasor = self._klasor()
        liste = dosyalari_tara(klasor)
        md = sorted((d["yol"] for d in liste if d["yol"].lower().endswith(".md") and d["yol"].count("/") <= 3), key=lambda p: (p.count("/"), p.lower()))[:60]
        return {"dosyalar": [{"yol": d["yol"], "boyut": d["boyut"]} for d in liste], "belgeler": md, "imza": imza(liste), "kesildi": len(liste) >= AZAMI_DOSYA_SAYISI, "degisen": self.son_hat.get("degisen", {})}

    def imza_al(self) -> str:
        return imza(dosyalari_tara(self._klasor()))

    def dosya_oku(self, goreli: str) -> dict:
        klasor = self._klasor()
        try:
            hedef = guvenli_goreli(klasor, goreli)
        except ValueError as hata:
            raise UygulamaHatasi(str(hata), 403) from None
        if not hedef.is_file():
            raise UygulamaHatasi("Dosya yok", 404)
        ham = hedef.read_bytes()[: AZAMI_OKUMA + 1]
        if b"\0" in ham[:4096]:
            return {"yol": goreli, "ikili": True, "icerik": ""}
        kesildi = len(ham) > AZAMI_OKUMA
        return {"yol": goreli, "ikili": False, "kesildi": kesildi, "icerik": ham[:AZAMI_OKUMA].decode("utf-8", "replace")}

    def fark(self, once: str, sonra: str, dosya: str | None) -> dict:
        klasor = self._klasor()
        if dosya:
            try:
                guvenli_goreli(klasor, dosya)
            except ValueError as hata:
                raise UygulamaHatasi(str(hata), 403) from None
        try:
            return {"yama": snapshot.fark_yamasi(klasor, once, sonra, dosya)}
        except snapshot.GitHatasi as hata:
            raise UygulamaHatasi(str(hata)) from None

    def klasorleri_listele(self, yol: str | None) -> dict:
        p = Path(yol).expanduser() if yol else Path.home()
        try:
            p = p.resolve()
            if not p.is_dir():
                raise UygulamaHatasi("Klasor degil", 404)
            alt = sorted((c.name for c in p.iterdir() if c.is_dir() and not c.name.startswith(".") and not c.name.startswith("$")), key=str.lower)
        except OSError as hata:
            raise UygulamaHatasi(f"Listelenemedi: {hata}", 403) from None
        return {"yol": str(p), "ust": str(p.parent) if p.parent != p else None, "klasorler": alt[:500], "kisayollar": self.klasor_kisayollari()}

    @staticmethod
    def klasor_kisayollari() -> list[dict]:
        """Klasor secicinin hizli gecis dugmeleri: ev, masaustu, belgeler, indirilenler ve (Windows'ta) var olan surucular."""
        ev = Path.home()
        liste = [{"ad": "Ev", "yol": str(ev)}]
        for ad, alt in (("Masaüstü", "Desktop"), ("Belgeler", "Documents"), ("İndirilenler", "Downloads")):
            if (ev / alt).is_dir():
                liste.append({"ad": ad, "yol": str(ev / alt)})
        if os.name == "nt":
            for harf in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                if os.path.exists(f"{harf}:\\"):
                    liste.append({"ad": f"{harf}:", "yol": f"{harf}:\\"})
        return liste

    def proje_listesi(self) -> dict:
        return {"projeler": projeler.listele(), "aktif": str(self.klasor) if self.klasor else None}

    def proje_unut(self, kimlik: object) -> dict:
        if not isinstance(kimlik, str) or not projeler.sil(kimlik):
            raise UygulamaHatasi("Boyle bir proje yok", 404)
        return {"tamam": True}


def _host_gecerli(host: str | None, portlar: set[int]) -> bool:
    if not host:
        return False
    ad, _, port = host.rpartition(":") if ":" in host else (host, "", "")
    return ad in ("127.0.0.1", "localhost") and port.isdigit() and int(port) in portlar


def yapi_arayuz(app: Uygulama, sunucu: "ArayuzSunucusu"):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _gonder(self, kod: int, veri=None, tur: str = "application/json; charset=utf-8", ek: dict | None = None):
            govde = veri if isinstance(veri, bytes) else (json.dumps(veri, ensure_ascii=False).encode() if veri is not None else b"")
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (ek or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(govde)

        def _govde(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > AZAMI_GOVDE:
                raise UygulamaHatasi("Govde cok buyuk", 413)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n))
            except json.JSONDecodeError:
                raise UygulamaHatasi("Gecersiz JSON") from None

        def _yol(self, yontem: str):
            if not _host_gecerli(self.headers.get("Host"), {sunucu.port}):
                return self._gonder(403, {"hata": "Gecersiz Host"})
            u = urllib.parse.urlsplit(self.path)
            yol, sorgu = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if yontem in ("GET", "HEAD") and yol in ("/", "/index.html"):
                dosya = WEB / "index.html"
                if not dosya.is_file():
                    return self._gonder(500, {"hata": "web/index.html yok"})
                return self._gonder(200, dosya.read_bytes(), "text/html; charset=utf-8", {"Content-Security-Policy": f"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-src http://127.0.0.1:* http://localhost:*; img-src 'self' data:"})
            if yontem in ("GET", "HEAD") and yol == "/favicon.ico":  # pencere/gorev cubugu simgesi (token gerektirmez, herkese acik statik dosya)
                simge = WEB / "favicon.ico"
                if simge.is_file():
                    return self._gonder(200, simge.read_bytes(), "image/x-icon")
            if not yol.startswith("/api/"):
                return self._gonder(404, {"hata": "yok"})
            if not hmac.compare_digest(self.headers.get("X-Aktapokus-Token", ""), app.token):
                return self._gonder(401, {"hata": "Token gerekli"})
            try:
                self._api(yontem, yol, sorgu)
            except UygulamaHatasi as hata:
                self._gonder(hata.kod, {"hata": str(hata)})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as hata:
                self._gonder(500, {"hata": f"{type(hata).__name__}: {hata}"})

        def _api(self, yontem: str, yol: str, q: dict):
            if yontem == "GET":
                if yol == "/api/durum":
                    return self._gonder(200, app.durum())
                if yol == "/api/ayar":
                    return self._gonder(200, app.ayar_oku())
                if yol == "/api/clilar":
                    return self._gonder(200, {"clilar": app.clilar()})
                if yol == "/api/projeler":
                    return self._gonder(200, app.proje_listesi())
                if yol == "/api/istatistik":
                    return self._gonder(200, app.istatistik(q.get("kapsam", "proje")))
                if yol == "/api/telegram":
                    return self._gonder(200, app.telegram_islem("durum", {}))
                if yol == "/api/ciktilar":
                    return self._gonder(200, app.ciktilar())
                if yol == "/api/gecmis":
                    return self._gonder(200, app.gecmis_kaydi(q["id"]) if q.get("id") else {"gecmis": app.gecmis()})
                if yol == "/api/saglayicilar":
                    return self._gonder(200, {"saglayicilar": app.saglayicilar()})
                if yol == "/api/modeller":
                    return self._gonder(200, {"modeller": app.modeller()})
                if yol == "/api/dosyalar":
                    return self._gonder(200, app.dosyalar())
                if yol == "/api/imza":
                    return self._gonder(200, {"imza": app.imza_al()})
                if yol == "/api/dosya":
                    return self._gonder(200, app.dosya_oku(q.get("yol", "")))
                if yol == "/api/fark":
                    return self._gonder(200, app.fark(q.get("once", ""), q.get("sonra", ""), q.get("dosya")))
                if yol == "/api/klasorler":
                    return self._gonder(200, app.klasorleri_listele(q.get("yol")))
                if yol == "/api/onizleme":
                    return self._gonder(200, {"url": sunucu.onizleme_url()})
                if yol == "/api/olaylar":
                    return self._akis(int(q.get("son", "0") or 0))
            if yontem == "POST":
                g = self._govde()
                if yol == "/api/klasor":
                    return self._gonder(200, app.klasor_sec(str(g.get("yol", "")), bool(g.get("git_baslat"))))
                if yol == "/api/clilar":
                    return self._gonder(200, app.cli_kaydet(g))
                if yol == "/api/saglayicilar/baglan":
                    return self._gonder(200, app.saglayici_baglan(g.get("saglayici"), g.get("anahtar"), g.get("etiket")))
                if yol == "/api/saglayicilar/kaldir":
                    return self._gonder(200, app.saglayici_kaldir(g.get("baglanti")))
                m = re.match(r"^/api/telegram/(baslat|durdur|eslestir|otomatik|kok|kok-sil)$", yol)
                if m:
                    return self._gonder(200, app.telegram_islem(m.group(1), g))
                if yol == "/api/projeler/unut":
                    return self._gonder(200, app.proje_unut(g.get("id")))
                if yol == "/api/clilar/sil":
                    return self._gonder(200, app.cli_sil(g.get("ad")))
                if yol == "/api/clilar/dene":
                    return self._gonder(200, app.cli_dene(g.get("ad"), g.get("model")))
                if yol == "/api/gorev":
                    return self._gonder(200, app.gorev_olustur(g.get("gorev")))
                m = re.match(r"^/api/gorev/([0-9a-f]+)/(onayla|reddet|karar|durdur)$", yol)
                if m:
                    kimlik, islem = m.groups()
                    if islem == "onayla":
                        app.onayla(kimlik)
                    elif islem == "reddet":
                        app.reddet(kimlik)
                    elif islem == "karar":
                        app.karar_ver(kimlik, bool(g.get("korunsun")))
                    else:
                        return self._gonder(200, {"durduruldu": app.durdur(kimlik)})
                    return self._gonder(200, {"tamam": True})
            if yontem == "PUT" and yol == "/api/ayar":
                app.ayar_yaz(self._govde())
                return self._gonder(200, {"tamam": True})
            return self._gonder(404, {"hata": "yok"})

        def _akis(self, son_id: int):
            q, tekrar = app.bus.abone_ol(son_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                for o in tekrar:
                    self.wfile.write(f"id: {o['id']}\ndata: {json.dumps(o, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                while not sunucu.kapaniyor.is_set():
                    try:
                        o = q.get(timeout=10)
                        self.wfile.write(f"id: {o['id']}\ndata: {json.dumps(o, ensure_ascii=False)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.bus.ayril(q)

        def do_GET(self):
            self._yol("GET")

        def do_HEAD(self):
            self._yol("HEAD")

        def do_POST(self):
            self._yol("POST")

        def do_PUT(self):
            self._yol("PUT")

    return H


def yapi_onizleme(app: Uygulama, sunucu: "ArayuzSunucusu"):
    class O(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _hata(self, kod: int, mesaj: str):
            b = mesaj.encode()
            self.send_response(kod)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if not _host_gecerli(self.headers.get("Host"), {sunucu.onizleme_port}):
                return self._hata(403, "Gecersiz Host")
            klasor = app.klasor
            if klasor is None:
                return self._hata(404, "Klasor secilmedi")
            yol = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            goreli = yol.strip("/")
            try:
                hedef = guvenli_goreli(klasor, goreli) if goreli else klasor.resolve()
            except ValueError:
                return self._hata(403, "Yasak yol")
            if hedef.is_dir():
                hedef = hedef / "index.html"
            if not hedef.is_file():
                return self._hata(404, "Dosya yok")
            tur = mimetypes.guess_type(hedef.name)[0] or "application/octet-stream"
            boyut = hedef.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", tur + ("; charset=utf-8" if tur.startswith("text/") or tur in ("application/javascript", "application/json") else ""))
            self.send_header("Content-Length", str(boyut))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # CSP 'sandbox' / 'frame-ancestors' basliklari ve opak-kokenli iframe, uygulama icindeki tarayici panelinde cerceveyi
            # BOS biraktigi icin kullanilmadi (denendi). Yalitim: AYRI PORT (ayri kokten: uygulamanin token'ina/sessionStorage'ina
            # erisemez, CORS yok) + iframe sandbox'i (ust sayfaya gitme ve acilir pencere yok).
            self.end_headers()
            with open(hedef, "rb") as f:
                try:
                    shutil.copyfileobj(f, self.wfile)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    return O


class ArayuzSunucusu:
    def __init__(self, app: Uygulama, port: int = 0):
        self.app = app
        self.kapaniyor = threading.Event()
        self.http = ThreadingHTTPServer(("127.0.0.1", port), yapi_arayuz(app, self))
        self.http.daemon_threads = True
        self.port = self.http.server_address[1]
        self.onizleme_http = ThreadingHTTPServer(("127.0.0.1", 0), yapi_onizleme(app, self))
        self.onizleme_http.daemon_threads = True
        self.onizleme_port = self.onizleme_http.server_address[1]

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.app.token}"

    def onizleme_url(self) -> str:
        return f"http://127.0.0.1:{self.onizleme_port}/"

    def baslat(self) -> None:
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        threading.Thread(target=self.onizleme_http.serve_forever, daemon=True).start()

    def kapat(self) -> None:
        self.kapaniyor.set()
        for s in (self.http, self.onizleme_http):
            try:
                s.shutdown()
                s.server_close()
            except Exception:
                pass


def ui_calistir(klasor: str | None = None, port: int = 0, tarayici: bool = False) -> int:
    app = Uygulama()
    app._telegram().otomatik_baslat()  # Ayarlar > Telegram'da 'otomatik baslat' aciksa ve token varsa bot arka planda baslar
    sunucu = ArayuzSunucusu(app, port)
    sunucu.baslat()
    if klasor:
        try:
            app.klasor_sec(klasor, git_baslat=False)
        except UygulamaHatasi as hata:
            print(f"Klasor secilemedi ({hata}); arayuzden secebilirsiniz.", flush=True)
    print(f"Aktapokus arayuzu: {sunucu.url()}\n(Yalnizca bu bilgisayardan erisilir. Durdurmak icin Ctrl+C.)", flush=True)
    if tarayici:
        import webbrowser

        webbrowser.open(sunucu.url())
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sunucu.kapat()
        hepsini_kapat()
    return 0
