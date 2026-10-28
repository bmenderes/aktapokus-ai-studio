"""Genel izinler (TUM projeler): kullanici duzeyinde `~/.aktapokus/izinler.json` (AKTAPOKUS_IZINLER ile degistirilir). Varsayilan hepsi KAPALI.

- `degisiklikleri_koru`: gorev bitince 'Degisiklikler korunsun mu?' (Keep/Undo) sorulmaz, degisiklikler korunur. Geri alma noktasi yine alinir; sonradan geri alinabilir.
  Projeye ozel ayar (roller.json `otomatik_koru`) yerine her projede gecerli tek anahtar: is Keep sorusunda beklemesin diye.
- Yalniz yerel arayuzden yazilir (`uzak.politika` uzaktan erisimi reddeder); proje klasorunden ASLA okunmaz (klonlanan bir depo izin veremez)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

KAYIT_ORTAMI = "AKTAPOKUS_IZINLER"
ALANLAR = ("degisiklikleri_koru",)
_kilit = threading.Lock()


class IzinHatasi(Exception):
    pass


def dosya_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "izinler.json"


def oku() -> dict[str, bool]:
    try:
        ham = json.loads(dosya_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ham = {}
    ham = ham if isinstance(ham, dict) else {}
    return {a: ham.get(a) is True for a in ALANLAR}


def yaz(veri: object) -> dict[str, bool]:
    if not isinstance(veri, dict) or not veri or any(a not in ALANLAR for a in veri) or any(not isinstance(v, bool) for v in veri.values()):
        raise IzinHatasi(f"Izinler {', '.join(ALANLAR)} alanlarindan true/false olmali")
    with _kilit:
        yeni = {**oku(), **veri}
        yol = dosya_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(yeni, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, yol)
        return yeni


def koru() -> bool:
    return oku()["degisiklikleri_koru"]
