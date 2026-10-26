"""Aktapokus'un CANLI durumu (diske yazilir): hangi projede hangi gorev, hangi adimda, son arac ne. Claude Code'un kancasi (`aktapokus haber`) ve
diger araclar uygulamaya baglanmadan (belirtec gerekmeden) bunu okuyarak Aktapokus'ta ne oldugunu bilir.

Dosya: ~/.aktapokus/canli.json (AKTAPOKUS_CANLI ile degistirilir). Yalniz kisa ozet tutulur (gorev metni 200 karakter, arac hedefi 80); sir, istem
metni, dosya icerigi YAZILMAZ. Uygulama kapaninca dosya bayatlar: okuyucu pid'in canli oldugunu ve guncelleme zamanini denetler."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

KAYIT_ORTAMI = "AKTAPOKUS_CANLI"
YAZMA_ARALIGI = 0.8  # akici olaylar (arac) bu araliktan sik dosyaya yazilmaz
BITTI_OMRU_SN = 90  # biten gorev kaydi bu sure sonra silinir
_kilit = threading.Lock()
_projeler: dict[str, dict] = {}
_son_yazma = 0.0


def dosya_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "canli.json"


def _hedef(girdi: object) -> str:
    if not isinstance(girdi, dict):
        return ""
    for k in ("file_path", "path", "filePath", "command", "pattern", "url"):
        v = girdi.get(k)
        if isinstance(v, str) and v:
            return v[:80]
    return ""


def _yaz(zorla: bool) -> None:
    global _son_yazma
    simdi = time.time()
    if not zorla and simdi - _son_yazma < YAZMA_ARALIGI:
        return
    for pid_, d in list(_projeler.items()):
        if d.get("durum") == "bitti" and simdi - d.get("guncelleme", 0) > BITTI_OMRU_SN:
            del _projeler[pid_]
    veri = {"surum": 1, "pid": os.getpid(), "guncelleme": simdi, "projeler": _projeler}
    yol = dosya_yolu()
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
        os.replace(gecici, yol)
        _son_yazma = simdi
    except OSError:
        pass  # canli durum yazilamazsa gorev etkilenmez


def olay(proje: str, ad: str, klasor: str, e: dict) -> None:
    """Uygulama olay akisindan her olayda cagrilir; yalniz durum degistiren olaylar ve (aralikli) arac olaylari yazilir."""
    tur = e.get("tur")
    simdi = time.time()
    with _kilit:
        d = _projeler.setdefault(proje, {"ad": ad, "klasor": klasor})
        d["guncelleme"] = simdi
        zorla = True
        if tur == "plan":
            d.update(durum="plan", gorev=str(e.get("gorev", ""))[:200], baslangic=simdi, rol="", adim=0, son_arac="", sonuc=None)
        elif tur == "basladi":
            d["durum"] = "calisiyor"
        elif tur == "adim-basladi":
            d.update(durum="calisiyor", rol=str(e.get("rol", "")), adim=e.get("sira") or 0, son_arac="", calistirici=str(e.get("calistirici", "")), model=str(e.get("model") or ""))
        elif tur == "canli" and e.get("alt") == "arac":
            d["son_arac"] = (str(e.get("ad") or "") + " " + _hedef(e.get("girdi"))).strip()
            zorla = False
        elif tur == "karar-bekleniyor":
            d["durum"] = "karar-bekliyor"
        elif tur == "bitti":
            d.update(durum="bitti", sonuc=str(e.get("durum", "")), mesaj=str(e.get("mesaj", ""))[:200])
        else:
            return
        _yaz(zorla)


def oku() -> dict | None:
    try:
        v = json.loads(dosya_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None
