"""Ciktilar (Outputs): bir projede gorevlerle OLUSAN ya da DEGISEN dosyalarin birlesik listesi.

Kaynak: `<proje>/.aktapokus/kayit/*.json` kayitlarindaki `degisen` ({yol: A|M|D}). Yalniz KALICI olan gorevler sayilir: kullanicinin
"korunsun" dedigi (`korundu`) ve sonradan geri alinmamis (`geri_alindi_sonradan` degil) gorevler; geri alinan gorevlerin dosyalari cikti degildir.
Bir dosya sonradan silindiyse (kayitta D ya da diskte yok) listelenmez. Gizli/hassas yollar ve proje disina cikan yollar atlanir (`yol_dogrula`)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from .pipeline import _kayit_klasoru

AZAMI_CIKTI = 500
TURLER = {
    "html": {".html", ".htm"},
    "md": {".md", ".markdown"},
    "gorsel": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"},
    "kod": {".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".json", ".yaml", ".yml", ".toml", ".sh", ".bat", ".ps1", ".cs", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".sql", ".xml"},
}


def tur_bul(ad: str) -> str:
    uzanti = Path(ad).suffix.lower()
    for tur, kume in TURLER.items():
        if uzanti in kume:
            return tur
    return "diger"


def kayitlari_oku(klasor: Path) -> list[dict]:
    """Eskiden yeniye (dosya adi sirasi = olusturma sirasi). Bozuk dosyalar atlanir."""
    klasoru = _kayit_klasoru(Path(klasor))
    try:
        dosyalar = sorted(klasoru.glob("*.json"))
    except OSError:
        return []
    sonuc = []
    for d in dosyalar:
        try:
            k = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(k, dict):
            sonuc.append(k)
    return sonuc


def _kalici(k: dict) -> bool:
    return bool(k.get("korundu")) and not k.get("geri_alindi_sonradan")


def topla(klasor: Path, kayitlar: list[dict], yol_dogrula: Callable[[Path, str], Path], azami: int = AZAMI_CIKTI) -> list[dict]:
    """kayitlar: ESKIDEN YENIYE sirali. En son degisen en ustte."""
    durum: dict[str, dict] = {}
    for k in kayitlar:
        if not _kalici(k) or not isinstance(k.get("degisen"), dict):
            continue
        bilgi = {"id": k.get("id"), "zaman": k.get("zaman"), "gorev": str(k.get("gorev", ""))[:120]}
        for yol, d in k["degisen"].items():
            if not isinstance(yol, str):
                continue
            if d == "D":
                durum.pop(yol, None)
            elif d in ("A", "M"):
                eski = durum.get(yol)
                durum[yol] = {
                    "olusturan": eski["olusturan"] if eski else bilgi,
                    "yeni": eski["yeni"] if eski else d == "A",  # ilk gorulen A ise dosya gorevle OLUSTU, M ise var olan dosya degisti
                    "son": bilgi,
                    "adet": (eski["adet"] if eski else 0) + 1,
                }
    cikti = []
    for yol, v in durum.items():
        try:
            hedef = yol_dogrula(Path(klasor), yol)
            st = hedef.stat()
        except (ValueError, OSError):
            continue
        if not hedef.is_file():
            continue
        goreli = yol.replace("\\", "/")
        cikti.append({
            "yol": goreli, "ad": goreli.rsplit("/", 1)[-1], "klasor": goreli.rsplit("/", 1)[0] if "/" in goreli else "",
            "tur": tur_bul(goreli), "durum": "yeni" if v["yeni"] else "degisti", "adet": v["adet"],
            "gorev": v["olusturan"]["gorev"], "gorev_id": v["olusturan"]["id"], "son_gorev": v["son"]["gorev"], "zaman": v["son"]["zaman"],
            "boyut": st.st_size, "degisti": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"), "_mtime": st.st_mtime,
        })
    cikti.sort(key=lambda c: -c["_mtime"])
    for c in cikti:
        del c["_mtime"]
    return cikti[:azami]
