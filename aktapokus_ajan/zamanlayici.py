"""Otomasyon zamanlayicisi: uygulama calisirken, zamani gelen 'zamanli' otomasyonlar icin PLAN uretir (onay yine sart).

Kurallar (tasarim: docs/otomasyon-tasarimi.md):
- Uygulama kapaliyken hicbir sey tetiklenmez. Acilista gecmis zamanlar GERIYE DONUK calistirilmaz; "kacirildi" olarak kayda yazilir.
- Birikmez: bir otomasyon icin gecen tum planli anlar tek degerlendirmeyle kapanir (en cok bir kayit/calistirma).
- Projede gorev varsa tetikleme atlanir (otomasyon_calistir bunu kayda yazar).
- Gunluk tavan: zamanlayicinin bir gunde uretecegi en cok plan sayisi (token tavaninin sade karsiligi)."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Callable

from . import otomasyon

TOLERANS_DK = 10  # planli andan bu kadar gec kalan tetikleme (tik gecikmesi, kisa uyku) hala calisir; daha gecse 'kacirildi'
GUNLUK_TAVAN = 12
TIK_SN = 30.0


class Zamanlayici:
    def __init__(self, calistir: Callable[[str], object], saat: Callable[[], datetime] = datetime.now, tik_sn: float = TIK_SN, tolerans_dk: int = TOLERANS_DK, gunluk_tavan: int = GUNLUK_TAVAN):
        self._calistir = calistir
        self._saat = saat
        self._tik_sn = tik_sn
        self._tolerans = timedelta(minutes=tolerans_dk)
        self._tavan = gunluk_tavan
        self._dur = threading.Event()
        self._is: threading.Thread | None = None
        self._tik_kilit = threading.Lock()

    def _bugunku_plan_sayisi(self, gun: str) -> int:
        return sum(1 for k in otomasyon.gecmis_oku(otomasyon.AZAMI_GECMIS) if k.get("tetikleyen") == "zamanlayici" and k.get("sonuc") == "plan-olustu" and str(k.get("zaman", "")).startswith(gun))

    def tikla(self) -> list[tuple[str, str]]:
        """Bir degerlendirme turu. (otomasyon adi, sonuc) listesi doner; testler icin dogrudan cagrilabilir."""
        sonuclar: list[tuple[str, str]] = []
        with self._tik_kilit:
            simdi = self._saat()
            for o in list(otomasyon.yukle().values()):
                if o.tur != "zamanli" or not o.acik or not o.zamanlama:
                    continue
                try:
                    ref = otomasyon.durum_oku(o.ad) or datetime.strptime(o.olusturma, otomasyon.ZAMAN_BICIMI)
                    vakit = otomasyon.sonraki(o.zamanlama, ref)
                except (ValueError, otomasyon.OtomasyonHatasi):
                    continue
                if vakit > simdi:
                    continue
                otomasyon.durum_yaz(o.ad, simdi)  # ONCE yazilir: calistirma cokse ya da atlansa bile ayni an tekrar denenmez
                zaman = simdi.strftime(otomasyon.ZAMAN_BICIMI)
                if simdi - vakit > self._tolerans:
                    otomasyon.gecmis_ekle(o.ad, "kacirildi", f"{vakit:%Y-%m-%d %H:%M} anini uygulama kapaliydi ya da bilgisayar uykudaydi; geriye donuk calistirilmadi", "zamanlayici", proje=o.proje, zaman=zaman)
                    sonuclar.append((o.ad, "kacirildi"))
                    continue
                if self._bugunku_plan_sayisi(simdi.strftime("%Y-%m-%d")) >= self._tavan:
                    otomasyon.gecmis_ekle(o.ad, "atlandi", f"gunluk zamanlayici tavani ({self._tavan} plan) doldu", "zamanlayici", proje=o.proje, zaman=zaman)
                    sonuclar.append((o.ad, "atlandi"))
                    continue
                try:
                    self._calistir(o.ad)
                    sonuclar.append((o.ad, "plan-olustu"))
                except Exception as hata:  # UygulamaHatasi (atlandi/hata) kaydini otomasyon_calistir zaten yazdi
                    if type(hata).__name__ != "UygulamaHatasi":
                        otomasyon.gecmis_ekle(o.ad, "hata", f"{type(hata).__name__}: {hata}", "zamanlayici", proje=o.proje)
                    sonuclar.append((o.ad, "atlandi/hata"))
        return sonuclar

    def baslat(self) -> None:
        if self._is is not None:
            return
        self._dur.clear()

        def don() -> None:
            while True:
                try:
                    self.tikla()
                except Exception:
                    pass  # zamanlayici hicbir zaman uygulamayi dusurmez
                if self._dur.wait(self._tik_sn):
                    return

        self._is = threading.Thread(target=don, daemon=True, name="otomasyon-zamanlayici")
        self._is.start()

    def durdur(self) -> None:
        self._dur.set()
        t, self._is = self._is, None
        if t is not None and t is not threading.current_thread():
            t.join(timeout=5)
