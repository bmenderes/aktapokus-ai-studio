"""Telegram botu: telefondan gorev ver, plani/farki onayla, ilerlemeyi izle. Yalnizca standart kutuphane.

Mimari: `arayuz.Uygulama` (plan -> onay -> calisma -> karar akisi ve olay otobusu) ile ayni motoru kullanir; bot yalnizca
Telegram <-> Uygulama cevirmenidir. Telegram'i UZUN YOKLAMA (getUpdates) ile dinler: bilgisayara dis baglanti/webhook/port yok.

Guvenlik:
- Yalniz ESLESMIS kullanicidan, yalniz OZEL sohbetten gelen guncellemeler islenir; digerleri sessizce yok sayilir.
- Eslestirme: baslangicta uretilen tek kullanimlik, 10 dk gecerli kod (`/eslestir KOD`); 5 yanlis denemede kilitlenir.
- Baslangictan ONCE biriken guncellemeler atlanir (bayat 'Onayla' dugmesi yeniden calismaz).
- Varsayilan GIZLILIK: dosya icerigi/fark metni Telegram'a (bulut) gonderilmez; yalniz dosya adlari, sayilar ve durum. `/gizlilik acik` ile kullanici acabilir.
- Token yalniz ortam degiskeni/dosyadan okunur; hata mesajlarindan ve gunluklerden ayiklanir.
- Onay istenen adimlar (plan, fark) yalniz dugme/komut ile ilerler; bot onaysiz bir sey calistirmaz.
"""

from __future__ import annotations

import contextlib
import hmac
import html
import io
import json
import os
import queue
import re
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import projeler as proje_kayit
from . import snapshot
from .arayuz import Uygulama, UygulamaHatasi

GIZLI_VARSAYILAN = ["aktapokus-ajan"]  # botun kendi kaynak klasoru telefondan secilemez (kendi kodunu degistirmesin)
AD_KALIBI = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,40}")
YASAK_AD = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])", re.IGNORECASE)  # Windows ayrilmis aygit adlari
AZAMI_PROJE_DUGMESI = 40
AZAMI_MESAJ = 3500
ESLESTIRME_OMRU_SN = 600
AZAMI_YANLIS = 5
TOKEN_ORTAMI = "AKTAPOKUS_TELEGRAM_TOKEN"
AYAR_ORTAMI = "AKTAPOKUS_TELEGRAM_AYAR"
YARDIM = (
    "Aktapokus botu\n"
    "/durum  aktif proje, roller, calisan gorev, diger projeler\n"
    "/projeler  proje klasorlerini dugme olarak goster; dokunduğunuz bu sohbetin aktif projesi olur (bilgisayar ekranini degistirmez)\n"
    "/yeni <ad>  yeni proje klasoru olustur (git ve koruyucu kurulur)\n"
    "/kokler  izinli proje klasorleri (degistirmek icin bilgisayardan)\n"
    "/klasor <tam yol>  elle sec (yalniz izinli proje klasorlerinin altinda)\n"
    "/gorev <metin>  yeni gorev (duz metin de gorev sayilir); once plan gelir, siz onaylarsiniz\n"
    "/durdur  calisan gorevi durdur\n"
    "/fark <dosya>  degisikligi goster (yalniz /gizlilik acik ise)\n"
    "/gizlilik acik|kapali  dosya iceriginin Telegram'a gonderilmesi (varsayilan: kapali)\n"
    "Not: Telegram bulutta; icerik gonderimi kapaliyken yalniz dosya adlari ve durum gider."
)


class TelegramHatasi(Exception):
    pass


def varsayilan_ayar_yolu() -> Path:
    ortam = os.environ.get(AYAR_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "telegram.json"


def token_oku() -> str | None:
    t = os.environ.get(TOKEN_ORTAMI, "").strip()
    if t:
        return t
    yol = Path.home() / ".aktapokus" / "telegram.token"
    if yol.is_file():
        satirlar = yol.read_text(encoding="utf-8").strip().splitlines()
        return satirlar[0].strip() if satirlar else None
    return None


class TelegramApi:
    def __init__(self, token: str, taban: str = "https://api.telegram.org", zaman_asimi: float = 35.0):
        self._token = token
        self.taban = taban.rstrip("/")
        self.zaman_asimi = zaman_asimi

    def _temizle(self, metin: str) -> str:
        return metin.replace(self._token, "[TOKEN]")

    def cagir(self, yontem: str, veri: dict | None = None, zaman_asimi: float | None = None):
        r = urllib.request.Request(
            f"{self.taban}/bot{self._token}/{yontem}", data=json.dumps(veri or {}).encode(), headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(r, timeout=zaman_asimi or self.zaman_asimi) as y:
                j = json.loads(y.read())
        except urllib.error.HTTPError as hata:
            raise TelegramHatasi(self._temizle(f"HTTP {hata.code} {yontem}: {hata.read()[:200].decode('utf-8', 'replace')}")) from None
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as hata:
            raise TelegramHatasi(self._temizle(f"{yontem}: {type(hata).__name__}: {hata}")) from None
        if not j.get("ok"):
            raise TelegramHatasi(self._temizle(f"{yontem}: {j.get('description')}"))
        return j.get("result")


class Bot:
    def __init__(self, app: Uygulama, api: TelegramApi, ayar_yolu: Path | None = None, log: Callable[[str], None] = print, yoklama_sn: int = 25):
        self.app, self.api, self.log, self.yoklama_sn = app, api, log, yoklama_sn
        self.ayar_yolu = ayar_yolu or varsayilan_ayar_yolu()
        self.ayar = self._yukle()
        self.dur = threading.Event()
        self.offset = 0
        self.eslestirme: dict | None = None
        self.eslesince: Callable[[], None] | None = None
        self.proje_tablosu: list[Path] = []  # /projeler dugmelerinin (p:N, g:N) gosterdigi klasorler
        self.aktif_proje: dict[int, str] = {}  # sohbet -> proje kimligi (bilgisayardaki secili projeden BAGIMSIZ; yeniden baslayinca sifirlanir)
        self.ilerleme: dict[str, dict] = {}  # kosu -> {chat: (mesaj_id, satirlar)}
        self._olay_kuyrugu: queue.Queue | None = None

    # ---- ayar ----
    def _yukle(self) -> dict:
        varsayilan = {"izinli": [], "icerik_gonder": False, "kokler": [], "gizli": list(GIZLI_VARSAYILAN)}
        try:
            v = json.loads(self.ayar_yolu.read_text(encoding="utf-8"))
            return {
                "izinli": [int(x) for x in v.get("izinli", [])],
                "icerik_gonder": bool(v.get("icerik_gonder", False)),
                "kokler": [str(x) for x in v.get("kokler", [])],
                "gizli": [str(x) for x in v.get("gizli", GIZLI_VARSAYILAN)],
            }
        except (OSError, ValueError, TypeError):
            return varsayilan

    def _kaydet(self) -> None:
        self.ayar_yolu.parent.mkdir(parents=True, exist_ok=True)
        self.ayar_yolu.write_text(json.dumps(self.ayar, indent=2), encoding="utf-8")

    @property
    def izinli(self) -> list[int]:
        return self.ayar["izinli"]

    def eslestirme_kodu_uret(self, zorla: bool = False) -> str | None:
        """Eslesmis kullanici varsa None (zorla=True: bir cihaz daha eklemek icin yine de kod uretir; yalniz bilgisayardan cagrilir)."""
        if self.izinli and not zorla:
            return None
        kod = secrets.token_hex(4)
        self.eslestirme = {"kod": kod, "bitis": time.monotonic() + ESLESTIRME_OMRU_SN, "yanlis": 0}
        return kod

    # ---- sohbetin aktif projesi ----
    def _proje_kimligi(self, chat: int) -> str | None:
        """Sohbetin aktif projesi; secilmediyse bilgisayarda secili proje."""
        kimlik = self.aktif_proje.get(chat) or self.app.secili_kimlik
        return kimlik if kimlik in self.app.oturumlar else None

    def _baglam(self, chat: int):
        """`with self._baglam(chat):` icindeki uygulama islemleri sohbetin aktif projesine gider (bilgisayar ekranindaki secimi degistirmez)."""
        kimlik = self._proje_kimligi(chat)
        return self.app.proje_baglami(kimlik) if kimlik else contextlib.nullcontext()

    def _proje_adi(self, kimlik: object) -> str:
        o = self.app.oturumlar.get(kimlik) if isinstance(kimlik, str) else None
        return o.klasor.name if o else ""

    # ---- gonderim ----
    def _gonder(self, chat: int, metin: str, klavye: list | None = None) -> int | None:
        govde: dict = {"chat_id": chat, "text": metin[:AZAMI_MESAJ], "disable_web_page_preview": True}
        if klavye:
            govde["reply_markup"] = {"inline_keyboard": klavye}
        try:
            return (self.api.cagir("sendMessage", govde) or {}).get("message_id")
        except TelegramHatasi as hata:
            self.log(f"gonderilemedi: {hata}")
            return None

    def _herkese(self, metin: str, klavye: list | None = None) -> None:
        for chat in self.izinli:
            self._gonder(chat, metin, klavye)

    def _ilerleme_yaz(self, kosu: str, satir: str) -> None:
        for chat in self.izinli:
            durum = self.ilerleme.setdefault(kosu, {})
            mesaj_id, satirlar = durum.get(chat, (None, []))
            satirlar = (satirlar + [satir])[-15:]
            metin = "\n".join(satirlar)
            if mesaj_id is None:
                mesaj_id = self._gonder(chat, metin)
            else:
                try:
                    self.api.cagir("editMessageText", {"chat_id": chat, "message_id": mesaj_id, "text": metin[:AZAMI_MESAJ]})
                except TelegramHatasi as hata:
                    self.log(f"duzenlenemedi: {hata}")
            durum[chat] = (mesaj_id, satirlar)

    # ---- guncellemeler ----
    def guncelleme_isle(self, u: dict) -> None:
        if "callback_query" in u:
            return self._dugme(u["callback_query"])
        m = u.get("message")
        if not m:
            return
        chat, kisi = m.get("chat") or {}, m.get("from") or {}
        if chat.get("type") != "private" or kisi.get("id") != chat.get("id"):
            return  # grup/kanal/baskasi adina: yok say
        uid, metin = kisi.get("id"), (m.get("text") or "").strip()
        if uid not in self.izinli:
            ad, _, arg = metin.partition(" ")
            if ad.split("@")[0].lower() in ("/eslestir", "/start") and arg.strip():  # /start KOD: t.me?start= baglantisindan/QR'dan gelir
                self._eslestir(uid, arg.strip())
            return  # yetkisiz: sessiz
        self._komut(uid, metin)

    def _eslestir(self, uid: int, kod: str) -> None:
        e = self.eslestirme
        if self.izinli or e is None or time.monotonic() > e["bitis"]:
            return
        if hmac.compare_digest(kod, e["kod"]):
            self.ayar["izinli"] = [uid]
            self._kaydet()
            self.eslestirme = None
            self._gonder(uid, "Eslesti. Bu sohbet artik botu yonetebilir.\n\n" + YARDIM)
            self.log("telegram: kullanici eslesti")
            if self.eslesince:
                self.eslesince()
        else:
            e["yanlis"] += 1
            if e["yanlis"] >= AZAMI_YANLIS:
                self.eslestirme = None
                self.log("telegram: cok fazla yanlis kod, eslestirme kilitlendi (yeniden baslatin)")
            else:
                self._gonder(uid, "Kod yanlis.")

    def _komut(self, chat: int, metin: str) -> None:
        if not metin:
            return
        if not metin.startswith("/"):
            self.log(f"[{time.strftime('%H:%M:%S')}] telegram: gorev (duz metin)")
            return self._gorev(chat, metin)
        ad, _, arg = metin.partition(" ")
        ad, arg = ad.split("@")[0].lower(), arg.strip()
        self.log(f"[{time.strftime('%H:%M:%S')}] telegram komutu: {ad}")  # yalniz komut adi (icerik/yol yazilmaz)
        if ad in ("/start", "/yardim", "/help"):
            return self._gonder(chat, YARDIM)
        if ad == "/durum":
            return self._gonder(chat, self._durum_metni(chat))
        if ad == "/projeler":
            return self._projeler(chat)
        if ad == "/yeni":
            return self._yeni(chat, arg)
        if ad == "/kokler":
            k = self.ayar["kokler"]
            return self._gonder(chat, ("Izinli proje klasorleri:\n" + "\n".join(f"  {x}" for x in k) + f"\nGizli: {', '.join(self.ayar['gizli']) or '-'}\n(Degistirmek yalniz bilgisayardan: telegram-baslat.bat --kok <yol>)") if k else "Proje klasoru tanimli degil. Bilgisayarda: telegram-baslat.bat --kok <klasor yolu>")
        if ad == "/klasor":
            if self.ayar["kokler"] and not self._kokte(Path(arg)):
                return self._gonder(chat, "Bu klasor izinli proje klasorlerinin altinda degil (ya da gizli). /projeler ile secin.")
            try:
                d = self.app.proje_ac(arg, git_baslat=False, sec=False)
                self.aktif_proje[chat] = proje_kayit.proje_kimligi(d["klasor"])
                return self._gonder(chat, f"Klasor: {d['klasor']}\nGit: {'hazir' if d.get('git') else 'yok'}  Koruyucu: {'etkin' if not d.get('koruyucu_eksik') else 'EKSIK'}\nBu sohbetin aktif projesi.")
            except UygulamaHatasi as hata:
                if str(hata) == "git_gerekli":
                    return self._gonder(chat, "Bu klasor git deposu degil. Geri alma icin gerekli; bilgisayarda 'aktapokus ac <klasor> --git-baslat' calistirin (Telegram'dan git init yapilmaz).")
                return self._gonder(chat, f"Klasor secilemedi: {hata}")
        if ad == "/gorev":
            return self._gorev(chat, arg)
        if ad == "/durdur":
            with self._baglam(chat):
                k = self.app.kosu
                if not k:
                    return self._gonder(chat, "Calisan gorev yok." + self._digerleri(chat))
                try:
                    self.app.durdur(k.kimlik)
                    return self._gonder(chat, f"Durduruluyor ({self._proje_adi(self._proje_kimligi(chat))})...")
                except UygulamaHatasi as hata:
                    return self._gonder(chat, str(hata))
        if ad == "/gizlilik":
            if arg.lower() in ("acik", "kapali"):
                self.ayar["icerik_gonder"] = arg.lower() == "acik"
                self._kaydet()
            return self._gonder(chat, "Dosya icerigi Telegram'a gonderimi: " + ("ACIK" if self.ayar["icerik_gonder"] else "kapali") + "\n(Telegram bulutta, uctan uca sifreli degil.)")
        if ad == "/fark":
            return self._fark(chat, arg)
        self._gonder(chat, "Bilinmeyen komut.\n\n" + YARDIM)

    # ---- proje kokleri: dugmeyle secim, /yeni ----
    def _kokler(self) -> list[Path]:
        return [Path(k) for k in self.ayar["kokler"]]

    def _kokte(self, yol: Path) -> bool:
        """Yol, tanimli koklerden birinin ALTINDA (kokun kendisi degil), gizli/nokta ile baslayan bir klasorde degilse True."""
        try:
            yol = yol.expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        gizli = {g.lower() for g in self.ayar["gizli"]}
        for kok in self._kokler():
            try:
                goreli = yol.relative_to(kok.resolve())
            except ValueError:
                continue
            if goreli.parts and not goreli.parts[0].startswith(".") and goreli.parts[0].lower() not in gizli:
                return True
        return False

    @staticmethod
    def _ust_depo_var(yol: Path) -> bool:
        """Klasor, baska bir git deposunun ICINDE mi (kendisi depo kokuyse False)? Ic ice depo olusturulmaz."""
        koku = snapshot.repo_koku(yol)
        return koku is not None and koku != yol.resolve()

    def _projeler(self, chat: int) -> None:
        if not self._kokler():
            return self._gonder(chat, "Proje klasoru tanimli degil. Bilgisayarda: telegram-baslat.bat --kok <klasor yolu>")
        liste: list[Path] = []
        for kok in self._kokler():
            if not kok.is_dir():
                continue
            for c in sorted(kok.iterdir(), key=lambda p: p.name.lower()):
                if c.is_dir() and not c.name.startswith("$") and self._kokte(c):
                    liste.append(c)
        liste = liste[:AZAMI_PROJE_DUGMESI]
        self.proje_tablosu = liste
        if not liste:
            return self._gonder(chat, "Izinli klasorlerde proje yok. /yeni <ad> ile olusturabilirsiniz.")
        dugmeler = [{"text": (c.name + ("" if snapshot.hazir_mi(c) else " (git yok)"))[:40], "callback_data": f"p:{i}"} for i, c in enumerate(liste)]
        self._gonder(chat, "Bir proje secin:", [dugmeler[i:i + 2] for i in range(0, len(dugmeler), 2)])

    def _proje_sec(self, chat: int, yol: Path, git: bool) -> None:
        if git and self._ust_depo_var(yol):
            return self._gonder(chat, f"{yol.name} baska bir git deposunun icinde; ic ice depo olusturulmaz. Bilgisayarda hazirlayin.")
        try:
            d = self.app.proje_ac(str(yol), git_baslat=git, sec=False)
        except UygulamaHatasi as hata:
            if str(hata) != "git_gerekli":
                return self._gonder(chat, f"Klasor secilemedi: {hata}")
            if self._ust_depo_var(yol):
                return self._gonder(chat, f"{yol.name} baska bir git deposunun icinde; ic ice depo olusturulmaz. Bilgisayarda hazirlayin.")
            i = self.proje_tablosu.index(yol) if yol in self.proje_tablosu else None
            if i is None:
                return self._gonder(chat, f"{yol.name} git deposu degil. /projeler ile secip 'Git baslat' dugmesini kullanin.")
            return self._gonder(chat, f"{yol.name} git deposu degil. Geri alma icin git gerekir. Bu klasorde git baslatilsin mi? (yalniz bu klasore 'git init' yapilir)", [[{"text": "Git baslat", "callback_data": f"g:{i}"}]])
        self.aktif_proje[chat] = proje_kayit.proje_kimligi(d["klasor"])
        self._gonder(chat, f"Klasor secildi: {yol.name} (bu sohbetin aktif projesi)\nGit: {'hazir' if d.get('git') else 'yok'}  Koruyucu: {'etkin' if not d.get('koruyucu_eksik') else 'EKSIK'}\nGorev icin /gorev <metin> yazin.")

    def _yeni(self, chat: int, ad: str) -> None:
        if not self._kokler():
            return self._gonder(chat, "Proje klasoru tanimli degil. Bilgisayarda: telegram-baslat.bat --kok <klasor yolu>")
        if not AD_KALIBI.fullmatch(ad) or YASAK_AD.fullmatch(ad.split(".")[0]):
            return self._gonder(chat, "Gecersiz ad. Harf, rakam, - ve _ kullanin (en cok 41 karakter, bosluk ve yol isareti yok). Ornek: /yeni blog")
        kok = self._kokler()[0]
        hedef = kok / ad
        if not kok.is_dir():
            return self._gonder(chat, "Ilk proje klasoru bulunamadi.")
        if hedef.exists():
            return self._gonder(chat, f"{ad} zaten var. /projeler ile secebilirsiniz.")
        if snapshot.repo_koku(kok) is not None:
            return self._gonder(chat, "Ilk proje klasoru bir git deposunun icinde; ic ice depo olusturulmaz. Bilgisayarda hazirlayin.")
        hedef.mkdir()
        self.proje_tablosu = [*self.proje_tablosu, hedef] if hedef not in self.proje_tablosu else self.proje_tablosu
        self._proje_sec(chat, hedef, git=True)

    def _gorev(self, chat: int, metin: str) -> None:
        if not metin.strip():
            return self._gonder(chat, "Gorev metni bos. Ornek: /gorev ana sayfadaki basligi degistir")
        try:
            with self._baglam(chat):
                self.app.gorev_olustur(metin)  # plan olayi bildirim akisindan gelir (onay dugmeleriyle)
        except UygulamaHatasi as hata:
            self._gonder(chat, f"Gorev olusturulamadi: {hata}")

    def _digerleri(self, chat: int) -> str:
        """Sohbetin aktif projesi disinda su an calisan/onay bekleyen projeler (telefondan hangisi aktif oldugu karismasin)."""
        aktif = self._proje_kimligi(chat)
        diger = [f"  {o['ad']}: {o['durum']}" for o in self.app.oturum_durumlari() if o["durum"] and o["proje"] != aktif]
        return ("\nDiger projeler:\n" + "\n".join(diger)) if diger else ""

    def _durum_metni(self, chat: int) -> str:
        with self._baglam(chat):
            d = self.app.durum()
        if not d.get("klasor"):
            return "Klasor secilmedi. /klasor <yol>"
        satirlar = [f"Aktif proje: {Path(d['klasor']).name}", f"Klasor: {d['klasor']}", f"Git: {'hazir' if d.get('git') else 'yok'}  Koruyucu: {'etkin' if not d.get('koruyucu_eksik') else 'EKSIK'}"]
        a = d.get("ayar") or {}
        if a.get("akis"):
            satirlar.append("Roller: " + ", ".join(f"{ad} ({a['roller'][ad]['model'] or 'varsayilan'})" for ad in a["akis"]))
        k = d.get("kosu")
        satirlar.append(f"Gorev: {k['durum']}" if k else "Gorev: yok")
        return "\n".join(satirlar) + self._digerleri(chat)

    def _fark(self, chat: int, dosya: str) -> None:
        if not self.ayar["icerik_gonder"]:
            return self._gonder(chat, "Dosya icerigi gonderimi kapali (/gizlilik acik ile acabilirsiniz). Fark icin arayuze ya da bilgisayara bakin.")
        with self._baglam(chat):
            h = self.app.son_hat
            if not h or not dosya:
                return self._gonder(chat, "Kullanim: /fark <dosya>  (son gorevin degisen dosyalarindan biri)")
            try:
                yama = self.app.fark(h["once"], h["sonra"], dosya)["yama"]
            except UygulamaHatasi as hata:
                return self._gonder(chat, f"Fark alinamadi: {hata}")
        self._gonder(chat, yama or "(fark yok)")

    def _dugme(self, cb: dict) -> None:
        kisi, msg = cb.get("from") or {}, cb.get("message") or {}
        chat = (msg.get("chat") or {})
        if kisi.get("id") not in self.izinli or chat.get("type") != "private" or chat.get("id") != kisi.get("id"):
            return  # yetkisiz: yanit bile verme
        parcalar = (cb.get("data") or "").split(":")

        def yanit(metin: str) -> None:
            try:
                self.api.cagir("answerCallbackQuery", {"callback_query_id": cb.get("id"), "text": metin[:150]})
            except TelegramHatasi as hata:
                self.log(f"yanit verilemedi: {hata}")

        def klavyeyi_kaldir() -> None:
            try:
                self.api.cagir("editMessageReplyMarkup", {"chat_id": chat["id"], "message_id": msg.get("message_id"), "reply_markup": {"inline_keyboard": []}})
            except TelegramHatasi as hata:
                self.log(f"klavye kaldirilamadi: {hata}")

        try:
            if len(parcalar) == 2 and parcalar[0] == "o":
                with self._kosu_baglami(parcalar[1]):
                    self.app.onayla(parcalar[1])
                yanit("Onaylandi, calisiyor")
            elif len(parcalar) == 2 and parcalar[0] == "r":
                with self._kosu_baglami(parcalar[1]):
                    self.app.reddet(parcalar[1])
                yanit("Reddedildi")
            elif len(parcalar) == 2 and parcalar[0] in ("p", "g") and parcalar[1].isdigit():
                i = int(parcalar[1])
                yol = self.proje_tablosu[i] if i < len(self.proje_tablosu) else None
                if yol is None or not yol.is_dir() or not self._kokte(yol):
                    return yanit("Liste eskimis, /projeler yazin")
                yanit("Tamam")
                self._proje_sec(chat["id"], yol, git=parcalar[0] == "g")
            elif len(parcalar) == 3 and parcalar[0] == "k" and parcalar[2] in ("0", "1"):
                with self._kosu_baglami(parcalar[1]):
                    self.app.karar_ver(parcalar[1], parcalar[2] == "1")
                yanit("Korunuyor" if parcalar[2] == "1" else "Geri aliniyor")
            else:
                return yanit("Gecersiz dugme")
            klavyeyi_kaldir()
        except UygulamaHatasi:
            yanit("Bu gorev artik gecerli degil")
            klavyeyi_kaldir()

    def _kosu_baglami(self, kosu: str):
        """Dugmedeki gorev kimligine sahip projenin baglami (sohbetin aktif projesinden bagimsiz: baska projenin plani da onaylanabilir)."""
        kimlik = self.app.kosu_projesi(kosu)
        if kimlik is None:
            raise UygulamaHatasi("Gorev bulunamadi", 404)
        return self.app.proje_baglami(kimlik)

    # ---- uygulama olaylari -> Telegram ----
    def _etiket(self, o: dict) -> str:
        ad = self._proje_adi(o.get("proje"))
        return f"[{ad}] " if ad and len(self.app.oturumlar) > 1 else ""

    def olay_isle(self, o: dict) -> None:
        t, k = o.get("tur"), o.get("kosu")
        et = self._etiket(o)
        if t in ("plan", "adim-basladi", "adim-bitti", "dogrulama", "duzeltme", "fark", "bitti"):  # bilgisayar tarafinda de ilerleme gorunsun
            self.log(f"[{time.strftime('%H:%M:%S')}] {t}" + "".join(f" {o[a]}" for a in ("rol", "sonuc", "durum") if o.get(a)))
        if t == "plan":
            adimlar = "\n".join(f"  {a['rol']}: {a['calistirici']} / {a['model'] or 'varsayilan model'}" for a in o["adimlar"])
            self._herkese(
                f"{et}Plan\nGorev: {o['gorev']}\n{adimlar}\nButce: {o['butce']} token, en cok {o['azami_duzeltme']} duzeltme, yalniz secili klasor",
                [[{"text": "Onayla", "callback_data": f"o:{k}"}, {"text": "Reddet", "callback_data": f"r:{k}"}]],
            )
        elif t == "adim-basladi":
            self._ilerleme_yaz(k, f"{et}{o['rol']} ({o['model'] or o['calistirici']}) calisiyor...")
        elif t == "adim-bitti":
            self._ilerleme_yaz(k, f"{o['rol']}: {'tamam' if o['ok'] else 'HATA: ' + str(o.get('hata'))} - {o['sure_sn']} sn, {o['token_girdi'] + o['token_cikti']} token")
        elif t == "dogrulama":
            self._ilerleme_yaz(k, f"dogrulama: {o['sonuc']}")
        elif t == "duzeltme":
            self._ilerleme_yaz(k, f"duzeltme turu {o['no']}/{o['azami']}")
        elif t == "fark":
            dosyalar = sorted(o["degisen"].items())
            satirlar = [f"{d} {y}" for y, d in dosyalar[:20]] + ([f"... {len(dosyalar) - 20} dosya daha"] if len(dosyalar) > 20 else [])
            uyari = f"\nUYARI: {o['durum']}" if o.get("durum") != "tamam" else ""
            ek = "\n(Icerik gonderimi kapali; /fark <dosya> icin /gizlilik acik)" if not self.ayar["icerik_gonder"] else "\n/fark <dosya> ile degisikligi gorebilirsiniz."
            self._herkese(f"{et}{len(dosyalar)} dosya degisti:\n" + "\n".join(satirlar) + uyari + ek,
                          [[{"text": "Korunsun", "callback_data": f"k:{k}:1"}, {"text": "Geri al", "callback_data": f"k:{k}:0"}]])
        elif t == "bitti":
            self.ilerleme.pop(k, None)
            self._herkese(f"{et}Bitti: {o['durum']}" + (f"\n{o['mesaj']}" if o.get("mesaj") else "") + (f"\nToplam {o['token_toplam']} token" if o.get("token_toplam") else ""))

    def _olay_dongusu(self) -> None:
        assert self._olay_kuyrugu is not None
        while not self.dur.is_set():
            try:
                o = self._olay_kuyrugu.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.olay_isle(o)
            except Exception as hata:  # bildirim hatasi botu dusurmesin
                self.log(f"olay islenemedi: {type(hata).__name__}")

    # ---- ana dongu ----
    def birikimi_atla(self) -> None:
        try:
            son = self.api.cagir("getUpdates", {"offset": -1, "timeout": 0}, zaman_asimi=15)
        except TelegramHatasi as hata:
            self.log(f"baslangic yoklamasi basarisiz: {hata}")
            return
        if son:
            self.offset = son[-1]["update_id"] + 1

    def calistir(self) -> None:
        self.birikimi_atla()
        self._olay_kuyrugu, _ = self.app.bus.abone_ol(self.app.bus.sayac)  # gecmisi yeniden oynatma
        threading.Thread(target=self._olay_dongusu, daemon=True).start()
        while not self.dur.is_set():
            try:
                guncellemeler = self.api.cagir(
                    "getUpdates", {"offset": self.offset, "timeout": self.yoklama_sn, "allowed_updates": ["message", "callback_query"]}, zaman_asimi=self.yoklama_sn + 10
                )
            except TelegramHatasi as hata:
                self.log(f"yoklama hatasi: {hata}")
                self.dur.wait(3)
                continue
            for u in guncellemeler or []:
                self.offset = u["update_id"] + 1
                try:
                    self.guncelleme_isle(u)
                except Exception as hata:
                    self.log(f"guncelleme islenemedi: {type(hata).__name__}: {hata}")

    def durdur(self) -> None:
        self.dur.set()


def eslestirme_baglantisi(kullanici_adi: str, kod: str) -> str:
    """https://t.me/<bot>?start=<kod>: telefonda acilinca Telegram botun sohbetini acar ve '/start <kod>' gonderir."""
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", kullanici_adi or "") or not re.fullmatch(r"[0-9a-f]{8}", kod or ""):
        raise ValueError("Gecersiz bot adi ya da kod")
    return f"https://t.me/{kullanici_adi}?start={kod}"


def eslestirme_sayfasi(baglanti: str) -> Path | None:
    """Baglantiyi QR kod olarak gosteren yerel bir HTML dosyasi yazar (QR icin 'segno' paketi gerekir; yoksa None)."""
    try:
        import segno
    except ImportError:
        return None
    qr = segno.make(baglanti, error="m")
    try:
        svg = qr.svg_inline(scale=6, border=4)
    except AttributeError:
        tampon = io.BytesIO()
        qr.save(tampon, kind="svg", scale=6, border=4)
        svg = tampon.getvalue().decode("utf-8")
    sayfa = (
        '<!doctype html><html lang="tr"><meta charset="utf-8"><title>Aktapokus Telegram eslestirme</title>'
        '<body style="font-family:system-ui,sans-serif;background:#f7f5f1;color:#2c2c2a;text-align:center;padding:24px">'
        "<h2>Telegram eslestirme</h2><p>Telefonunuzun kamerasiyla okutun; Telegram botunuzun sohbetini acar.<br>"
        "Tek kullanimlik, 10 dakika gecerli. Eslesince bu sayfa silinir.</p>"
        f'<div style="display:inline-block;background:#fff;padding:12px;border-radius:12px">{svg}</div>'
        f'<p style="margin-top:12px;font-size:13px">Okutamazsaniz bu baglantiyi telefonda acin:<br><a href="{html.escape(baglanti)}">{html.escape(baglanti)}</a></p></body></html>'
    )
    fd, yol = tempfile.mkstemp(prefix="aktapokus-eslestirme-", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(sayfa)
    return Path(yol)


def kok_ekle(kok: str, ayar_yolu: Path | None = None) -> Path:
    """Telefondan secilebilecek bir proje kok klasoru ekler (yalniz bilgisayardan). Guvensiz klasorler reddedilir."""
    from .klasor import guvenli_klasor

    yol = guvenli_klasor(kok)
    ayar_yolu = ayar_yolu or varsayilan_ayar_yolu()
    try:
        ayar = json.loads(ayar_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ayar = {}
    kokler = [str(k) for k in ayar.get("kokler", [])]
    if str(yol) not in kokler:
        kokler.append(str(yol))
    ayar["kokler"] = kokler
    ayar.setdefault("gizli", list(GIZLI_VARSAYILAN))
    ayar_yolu.parent.mkdir(parents=True, exist_ok=True)
    ayar_yolu.write_text(json.dumps(ayar, indent=2), encoding="utf-8")
    return yol


def telegram_calistir(klasor: str | None = None, bekle: Callable[[float], None] = time.sleep, kokler: list[str] | None = None) -> int:
    token = token_oku()
    if not token:
        print(
            "Telegram token'i yok. Adimlar:\n"
            "  1) Telegram'da @BotFather ile yeni bot olusturun, verdigi token'i kopyalayin.\n"
            f"  2) Token'i SIZ ortam degiskenine ({TOKEN_ORTAMI}) ya da {Path.home() / '.aktapokus' / 'telegram.token'} dosyasina yazin\n"
            "     (token'i sohbete/komut satirina yazmayin; kimseyle paylasmayin).\n"
            "  3) 'aktapokus telegram' komutunu tekrar calistirin."
        )
        return 2
    for kok in kokler or []:
        try:
            print(f"Proje klasoru eklendi: {kok_ekle(kok)}", flush=True)
        except Exception as hata:
            print(f"Proje klasoru eklenemedi ({kok}): {hata}", flush=True)
            return 1
    api = TelegramApi(token)
    try:
        kimlik = api.cagir("getMe", zaman_asimi=15)
        print(f"Telegram botu dogrulandi: @{kimlik.get('username', '?')}" if isinstance(kimlik, dict) else "Telegram botu dogrulandi.", flush=True)
    except TelegramHatasi as hata:
        print(f"Token dogrulanamadi: {hata}\nToken'i kontrol edin (BotFather'dan kopyalarken bosluk/eksik karakter olmasin).", flush=True)
        return 1
    app = Uygulama()
    if klasor:
        try:
            app.klasor_sec(klasor, git_baslat=False)
        except UygulamaHatasi as hata:
            print(f"Klasor secilemedi ({hata}); Telegram'dan /klasor ile secebilirsiniz.", flush=True)
    bot = Bot(app, api, log=lambda m: print(m, flush=True))
    kod = bot.eslestirme_kodu_uret()
    sayfa: Path | None = None
    if kod:
        print(f"Eslestirme (10 dk gecerli, tek kullanimlik). Elle: botunuza su mesaji yazin:\n  /eslestir {kod}", flush=True)
        try:
            baglanti = eslestirme_baglantisi(kimlik.get("username", "") if isinstance(kimlik, dict) else "", kod)
        except ValueError:
            baglanti = None
        if baglanti:
            print(f"Ya da telefonda su baglantiyi acin (kod hazir yazilir):\n  {baglanti}", flush=True)
            sayfa = eslestirme_sayfasi(baglanti)
            if sayfa:
                import webbrowser

                webbrowser.open(sayfa.as_uri())
                print("QR kod sayfasi tarayicida acildi; telefonla okutun.", flush=True)
                bot.eslesince = lambda: sayfa.unlink(missing_ok=True)
            else:
                print("(QR kod icin istege bagli 'segno' paketi gerekir: pip install segno)", flush=True)
    else:
        print(f"Eslesmis kullanici var ({len(bot.izinli)}). Bot dinliyor; durdurmak icin Ctrl+C.", flush=True)
    # Bot ayri is parcaciginda calisir; ana is parcacigi kisa 'sleep'lerle bekler. Windows'ta Ctrl+C, engelleyen bir ag
    # cagrisini (25 sn'lik Telegram yoklamasi) beklemeden yalniz boyle aninda etki eder (gercek denemede Ctrl+C 'calismiyordu').
    t = threading.Thread(target=bot.calistir, daemon=True)
    t.start()
    try:
        while t.is_alive():
            bekle(0.5)
    except KeyboardInterrupt:
        print("Durduruluyor...", flush=True)
    finally:
        bot.durdur()
        if sayfa:
            sayfa.unlink(missing_ok=True)
        from .runners import hepsini_kapat

        hepsini_kapat()
    return 0
