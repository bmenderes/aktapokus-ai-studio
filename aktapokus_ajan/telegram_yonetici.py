"""Telegram botunu ARAYUZLE AYNI SURECTE calistirir (Ayarlar > Telegram): baslat/durdur, otomatik baslat, eslestirme kodu, proje kokleri, gunluk.

Neden ayni surec: telefon ve arayuz TEK `Uygulama`'yi (proje, gorev, olay akisi) paylasir; ayri 'telegram-baslat.bat' sureci ise kendi ayri durumunu tutar
(ayni klasorde iki surec ayni anda gorev calistirabilirdi). Token'a yalniz bu modul dokunur ve ARAYUZE/GUNLUGE HIC YAZILMAZ; yalnizca 'var/yok' bilinir.
Bu islemler yalniz yerel, belirtec korumali arayuz API'sinden yapilir; Telegram'dan (telefondan) erisilemez.

Sinir: bot, Telegram'in 25 sn'lik uzun yoklamasinda bekler; 'durdur' sonrasi is parcacigi en cok ~35 sn icinde biter. O sure boyunca yeniden baslatma reddedilir
(iki yoklayici ayni anda calisirsa Telegram 409 Conflict verir)."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from .telegram import Bot, TelegramApi, TelegramHatasi, eslestirme_baglantisi, kok_ekle, token_oku, varsayilan_ayar_yolu

ARAYUZ_AYAR_ORTAMI = "AKTAPOKUS_ARAYUZ_AYAR"
GUNLUK_SATIRI = 300


class YoneticiHatasi(Exception):
    pass


def _varsayilan_token() -> str | None:
    """Testler bunu yamalar: HICBIR test kullanicinin gercek token'ini okumaz/kullanmaz."""
    return token_oku()


def arayuz_ayar_yolu() -> Path:
    ortam = os.environ.get(ARAYUZ_AYAR_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "arayuz-ayar.json"


def arayuz_ayar_oku() -> dict:
    try:
        v = json.loads(arayuz_ayar_yolu().read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def arayuz_ayar_yaz(**kv) -> None:
    """Var olan anahtarlari KORUYARAK birlestirir."""
    yol = arayuz_ayar_yolu()
    veri = arayuz_ayar_oku()
    veri.update(kv)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, indent=2), encoding="utf-8")
    os.replace(gecici, yol)


class TelegramYoneticisi:
    def __init__(
        self,
        app,
        taban: str = "https://api.telegram.org",
        ayar_yolu: Path | None = None,
        token_fn: Callable[[], str | None] | None = None,
        yoklama_sn: int = 25,
    ):
        self.app = app
        self.taban = taban
        self.ayar_yolu = ayar_yolu or varsayilan_ayar_yolu()
        self._token_fn = token_fn or _varsayilan_token
        self.yoklama_sn = yoklama_sn
        self.log_tamponu: deque[str] = deque(maxlen=GUNLUK_SATIRI)
        self._kilit = threading.Lock()
        self._bot: Bot | None = None
        self._is: threading.Thread | None = None
        self._bot_adi: str | None = None
        self._hata: str | None = None

    # ---- gunluk (token asla yazilmaz) ----
    def _log(self, mesaj: str) -> None:
        metin = str(mesaj)
        token = self._token_fn()
        if token:
            metin = metin.replace(token, "[TOKEN]")
        self.log_tamponu.append(time.strftime("%H:%M:%S ") + metin[:300])

    # ---- durum ----
    def _canli(self) -> bool:
        return self._is is not None and self._is.is_alive()

    def _ayar(self) -> dict:
        try:
            v = json.loads(self.ayar_yolu.read_text(encoding="utf-8"))
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}

    def durum(self) -> dict:
        canli = self._canli()
        durduruluyor = bool(canli and self._bot and self._bot.dur.is_set())
        ayar = self._ayar()
        eslestirme = None
        b = self._bot
        if canli and b and b.eslestirme and b.eslestirme["bitis"] > time.monotonic():
            kod = b.eslestirme["kod"]
            try:
                baglanti = eslestirme_baglantisi((self._bot_adi or "").lstrip("@"), kod)
            except ValueError:
                baglanti = None
            eslestirme = {"kod": kod, "komut": f"/eslestir {kod}", "baglanti": baglanti, "kalan_sn": int(b.eslestirme["bitis"] - time.monotonic())}
        return {
            "token_var": bool(self._token_fn()),
            "calisiyor": canli and not durduruluyor,
            "durduruluyor": durduruluyor,
            "bot": self._bot_adi if canli else None,
            "eslesmis": len(ayar.get("izinli", [])) if isinstance(ayar.get("izinli", []), list) else 0,
            "eslestirme": eslestirme,
            "otomatik": bool(arayuz_ayar_oku().get("telegram_otomatik", False)),
            "kokler": [str(k) for k in ayar.get("kokler", [])],
            "hata": self._hata,
            "log": list(self.log_tamponu)[-60:],
        }

    # ---- islemler ----
    def baslat(self) -> dict:
        with self._kilit:
            if self._canli():
                raise YoneticiHatasi("Bot zaten çalışıyor." if not (self._bot and self._bot.dur.is_set()) else "Bot durduruluyor (en çok ~35 sn); bitince yeniden başlatın.")
            token = self._token_fn()
            if not token:
                self._hata = "Token yok"
                raise YoneticiHatasi("Telegram token'ı yok. BotFather'dan aldığınız token'ı SİZ ~/.aktapokus/telegram.token dosyasına ya da AKTAPOKUS_TELEGRAM_TOKEN ortam değişkenine yazın (bana/sohbete yazmayın).")
            api = TelegramApi(token, taban=self.taban)
            try:
                kimlik = api.cagir("getMe", zaman_asimi=15)
            except TelegramHatasi as hata:
                self._hata = f"Token doğrulanamadı: {hata}"
                self._log(self._hata)
                raise YoneticiHatasi(self._hata) from None
            self._hata = None
            self._bot_adi = "@" + (kimlik.get("username", "?") if isinstance(kimlik, dict) else "?")
            bot = Bot(self.app, api, ayar_yolu=self.ayar_yolu, log=self._log, yoklama_sn=self.yoklama_sn)
            bot.eslestirme_kodu_uret()  # eslesmis kullanici yoksa kod uretir
            self._bot = bot
            self._is = threading.Thread(target=self._calistir, args=(bot,), daemon=True, name="telegram-bot")
            self._is.start()
            self._log(f"Bot başlatıldı: {self._bot_adi}")
            return self.durum()

    def _calistir(self, bot: Bot) -> None:
        try:
            bot.calistir()
        except Exception as hata:  # bot hatasi arayuzu dusurmesin
            self._hata = f"Bot durdu: {type(hata).__name__}"
            self._log(f"{self._hata}: {hata}")
        finally:
            self._log("Bot durdu.")

    def durdur(self) -> dict:
        if self._bot and self._canli():
            self._bot.durdur()
            self._log("Durduruluyor… (Telegram uzun yoklamasının bitmesi ~35 sn sürebilir)")
        return self.durum()

    def yeni_eslestirme(self) -> dict:
        if not (self._bot and self._canli()) or self._bot.dur.is_set():
            raise YoneticiHatasi("Önce botu başlatın.")
        self._bot.eslestirme_kodu_uret(zorla=True)
        return self.durum()

    def otomatik_ayarla(self, acik: bool) -> dict:
        arayuz_ayar_yaz(telegram_otomatik=bool(acik))
        return self.durum()

    def kok_ekle(self, yol: str) -> dict:
        try:
            kok_ekle(yol, self.ayar_yolu)
        except Exception as hata:  # guvensiz/gecersiz klasor
            raise YoneticiHatasi(str(hata)) from None
        self._bota_yansit()
        return self.durum()

    def kok_sil(self, yol: str) -> dict:
        ayar = self._ayar()
        kokler = [str(k) for k in ayar.get("kokler", [])]
        kalan = [k for k in kokler if k.lower() != str(yol).lower()]
        if len(kalan) == len(kokler):
            raise YoneticiHatasi("Böyle bir kök klasör yok.")
        ayar["kokler"] = kalan
        self.ayar_yolu.write_text(json.dumps(ayar, indent=2), encoding="utf-8")
        self._bota_yansit()
        return self.durum()

    def _bota_yansit(self) -> None:
        if self._bot:
            self._bot.ayar = self._bot._yukle()  # calisan bot yeni kokleri hemen gorsun

    def otomatik_baslat(self) -> None:
        """Arayuz acilirken: ayar aciksa arka planda baslatir; hata (token yok, ag yok...) arayuzu engellemez, gunluge yazilir."""
        if not arayuz_ayar_oku().get("telegram_otomatik"):
            return  # ayar kapali; token yoksa baslat() acik bir hata verir ve gunluge yazilir (kullanici nedenini gorur)

        def is_():
            try:
                self.baslat()
            except YoneticiHatasi as hata:
                self._log(f"Otomatik başlatma başarısız: {hata}")

        threading.Thread(target=is_, daemon=True, name="telegram-otomatik").start()
