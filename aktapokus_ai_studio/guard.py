"""Klasor siniri ve gizli dosya korumasi: OpenCode'un yerel IZIN sistemine yazilan proje ayari.

Gercek denemelerde (OpenCode 2.0.30) dogrulandi: okuma/yazma araclarinda klasor disi (external_directory) ve
.env engellendi; ajan kendi izin dosyasini degistiremedi. KABUK KOMUTLARI icin kurallar yalnizca desen
eslestirmesidir (.., surucu yolu, ~, $HOME, .env gecen komutlari reddeder); yorumlayicilarla (python -c vb.)
yolu dolayli olusturan bir komut bu denetimi asabilir. Tam kabuk yalitimi icin konteyner/sanal makine gerekir.

Dosya: <klasor>/.opencode/opencode.json (kullanicinin kok opencode.json'una dokunulmaz). Yalniz OpenCode
calistiricisi icin gecerlidir; Claude Code calistiricisi bu dosyayi okumaz.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import AYAR_KLASORU


class KoruyucuHatasi(Exception):
    pass


YEDEK_ADI = "opencode.json.yedek"

# `*` her karakter dizisiyle eslesir ("/" dahil); son eslesen kural gecerlidir, bu yuzden genel izin once gelir.
IZIN_AYARI: dict = {
    "external_directory": "deny",
    "read": {"*": "allow", "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow"},
    "edit": {
        "*": "allow",
        "*.env": "deny",
        "*.env.*": "deny",
        "*opencode.json": "deny",
        "*.opencode/*": "deny",
        f"*{AYAR_KLASORU}/*": "deny",
        "*.git/*": "deny",
    },
    "shell": {
        "*": "allow",
        "*..*": "deny",
        "*:\\*": "deny",
        "*:/*": "deny",
        "*~*": "deny",
        "*$HOME*": "deny",
        "*$env:*": "deny",
        "*%*%*": "deny",
        "*.env*": "deny",
        "*.env.example*": "allow",
    },
}


SEVIYELER = ("hayir", "riskli", "hepsi")  # gorev sirasinda kullaniciya izin sorma seviyesi (proje ayari 'izin_sor')


def izin_ayari(seviye: str = "hayir") -> dict:
    """Seviyeye gore izin ayari. 'hayir' = IZIN_AYARI (sormaz). 'riskli' = kabuk komutu ve web getirme SORULUR. 'hepsi' = dosya duzenleme de sorulur.
    Yasaklar (klasor disi, .env, kendi ayar dosyalari) HER seviyede yasak kalir: sormak korumayi gevsetmez."""
    import copy

    a = copy.deepcopy(IZIN_AYARI)
    if seviye in ("riskli", "hepsi"):
        a["shell"]["*"] = "ask"
        a["webfetch"] = "ask"
    if seviye == "hepsi":
        a["edit"]["*"] = "ask"
    return a


def _izin_oku(klasor: str | Path) -> dict | None:
    try:
        veri = json.loads(koruyucu_yolu(klasor).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    izin = veri.get("permission") if isinstance(veri, dict) else None
    return izin if isinstance(izin, dict) else None


def seviye_oku(klasor: str | Path) -> str | None:
    """Dosyadaki ayar hangi seviyeyle TAM eslesiyor; hicbiriyle eslesmiyorsa None."""
    izin = _izin_oku(klasor)
    if izin is None:
        return None
    for s in reversed(SEVIYELER):
        beklenen_ayar = izin_ayari(s)
        if all(izin.get(ad) == beklenen for ad, beklenen in beklenen_ayar.items()):
            return s
    return None


_SIR_ONEKLERI = (".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", "credentials")
_SIR_UZANTILARI = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")
_SIR_ORNEKLERI = (".env.example", ".env.sample", ".env.template", ".env.dist")
_TARAMA_ATLA = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".aktapokus", ".opencode"}


def hassas_dosyalar(klasor: str | Path, azami_tarama: int = 5000, azami_sonuc: int = 10) -> list[str]:
    """Klasorde .env/anahtar/parola benzeri dosyalar (goreli yollar). OpenCode koruyucusu OLMAYAN CLI'lar (Codex...) bunlari
    OKUYABILIR ve modele/bulutu gonderebilir; bu yuzden onlardan once taranir. Ornek dosyalar (.env.example) sayilmaz."""
    import os

    bulunan: list[str] = []
    taranan = 0
    kok = Path(klasor)
    for yol, altlar, dosyalar in os.walk(kok):
        altlar[:] = [a for a in altlar if a not in _TARAMA_ATLA]
        for d in dosyalar:
            taranan += 1
            k = d.lower()
            if k in _SIR_ORNEKLERI:
                continue
            if k.startswith(_SIR_ONEKLERI) or k.endswith(_SIR_UZANTILARI):
                bulunan.append((Path(yol) / d).relative_to(kok).as_posix())
                if len(bulunan) >= azami_sonuc:
                    return bulunan
            if taranan >= azami_tarama:
                return bulunan
    return bulunan


def koruyucu_yolu(klasor: str | Path) -> Path:
    return Path(klasor) / ".opencode" / "opencode.json"


def kur(klasor: str | Path, seviye: str | None = None) -> str:
    """Izin ayarini yazar/birlestirir. 'olusturuldu' | 'guncellendi' | 'zaten-etkin' dondurur.
    `seviye` verilmezse dosyadaki gecerli seviye korunur (yoksa 'hayir')."""
    klasor = Path(klasor)
    yol = koruyucu_yolu(klasor)
    if seviye is not None and seviye not in SEVIYELER:
        raise KoruyucuHatasi(f"Gecersiz izin seviyesi: {seviye!r}")
    seviye = seviye or seviye_oku(klasor) or "hayir"
    hedef = izin_ayari(seviye)
    if yol.exists():
        try:
            mevcut_metin = yol.read_text(encoding="utf-8")
            mevcut = json.loads(mevcut_metin)
        except (OSError, json.JSONDecodeError) as hata:
            raise KoruyucuHatasi(f"{yol} okunamadi/bozuk; uzerine yazilmadi: {hata}") from hata
        if not isinstance(mevcut, dict):
            raise KoruyucuHatasi(f"{yol} bir JSON nesnesi degil; uzerine yazilmadi")
        if not dogrula(klasor, seviye):
            return "zaten-etkin"
        yedek = klasor / AYAR_KLASORU / YEDEK_ADI
        if not yedek.exists():
            yedek.parent.mkdir(parents=True, exist_ok=True)
            yedek.write_text(mevcut_metin, encoding="utf-8")
        izin = mevcut.get("permission")
        izin = dict(izin) if isinstance(izin, dict) else {}
        izin.update(hedef)  # 'webfetch' yalniz sorulan seviyelerde yazilir; kullanicinin kendi webfetch ayarina 'hayir'da dokunulmaz
        mevcut["permission"] = izin
        sonuc, durum = mevcut, "guncellendi"
    else:
        sonuc, durum = {"$schema": "https://opencode.ai/config.json", "permission": hedef}, "olusturuldu"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return durum


def dogrula(klasor: str | Path, seviye: str | None = None) -> list[str]:
    """Eksik/degistirilmis koruma ogelerinin listesi; bos liste = koruyucu tam ve yerinde.
    `seviye` verilmezse bilinen seviyelerden HERHANGI biriyle tam eslesme yeterlidir."""
    yol = koruyucu_yolu(klasor)
    if not yol.is_file():
        return [f"koruyucu ayar dosyasi yok: {yol}"]
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"koruyucu ayar dosyasi okunamadi: {yol}"]
    izin = veri.get("permission") if isinstance(veri, dict) else None
    if not isinstance(izin, dict):
        return ["'permission' bolumu yok"]
    if seviye is None:
        seviye = seviye_oku(klasor) or "hayir"
    return [f"'permission.{ad}' beklenen degerde degil" for ad, beklenen in izin_ayari(seviye).items() if izin.get(ad) != beklenen]
