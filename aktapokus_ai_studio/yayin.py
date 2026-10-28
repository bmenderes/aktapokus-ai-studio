"""Yayinla: bir projedeki klasoru (ornek: olusturulan web sayfasi) baska bir GitHub deposuna (ornek: aktapokus.github.io/haberler) tasir.

Ajanlar yalniz KENDI proje klasorunde calisir ve GitHub'a erisemez; yayin Aktapokus'un isidir: hedef depo klonlanir/guncellenir, klasor oraya KOPYALANIR,
sonra commit (yapay zeka mesaji) ve push mevcut gonderme kontrolunden (gonderme_kontrol.py: kural tabanli tarama + yapay zeka + kullanici onayi) gecer.
Bu modul yalniz GUVENLI yol/kopya islerini yapar:
- Kaynak, projenin icinde bir klasor olmali (gizli klasorler, `..`, mutlak yol, sembolik baglanti disari kacisi reddedilir).
- Gizli gorunen dosya adlari (.env, *.pem, *.key...), nokta ile baslayan dosya/klasorler (`.nojekyll` haric), sembolik baglantilar ve 5 MB ustu dosyalar KOPYALANMAZ.
- Hedef klasor depo icinde, `.git`/`.github`/`.aktapokus` disinda bir yol olmali; hedef klasorun onceki icerigi yenisiyle DEGISTIRILIR (kaynakta silinen dosya sitede de silinir)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from . import github

HEDEF_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}(?:/[A-Za-z0-9][A-Za-z0-9._-]{0,60}){0,3}$")
YASAK_HEDEF = {".git", ".github", ".aktapokus"}
ATLANAN_KLASORLER = {"node_modules", "__pycache__"}
IZINLI_NOKTALI = {".nojekyll"}
AZAMI_DOSYA = 500
AZAMI_BAYT = 20_000_000
AZAMI_TEK_DOSYA = 5_000_000


class YayinHatasi(ValueError):
    pass


def yayin_klasoru() -> Path:
    """Hedef depolarin otomatik klonlandigi uygulama klasoru (AKTAPOKUS_YAYIN ile degistirilir)."""
    ortam = os.environ.get("AKTAPOKUS_YAYIN")
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "yayin"


def hedef_yol_dogrula(h: object, kok_izinli: bool = False) -> str:
    """kok_izinli=True iken bos hedef deponun KOKU demektir ("" doner); aksi halde klasor zorunludur."""
    if not isinstance(h, str):
        raise YayinHatasi("Hedef klasor metin olmali (ornek: haberler)")
    h = h.strip().strip("/").replace("\\", "/")
    if not h and kok_izinli:
        return ""
    if not HEDEF_DESENI.fullmatch(h) or any(p in (".", "..") or p.lower() in YASAK_HEDEF for p in h.split("/")) or h.endswith("."):
        raise YayinHatasi("Hedef klasor depo icinde, harf/rakam/./-/_ iceren goreli bir yol olmali (ornek: haberler); .git/.github olamaz")
    return h


def kaynak_goreli(goreli: object) -> str:
    """Kaynak klasorun SOZ DIZIMI dogrulamasi (diske bakmaz; otomasyon kaydederken de kullanilir). Normallestirilmis goreli yolu doner."""
    if not isinstance(goreli, str) or not goreli.strip() or len(goreli) > 200:
        raise YayinHatasi("Kaynak klasor yazilmali (projenin icindeki klasor, ornek: aktapokus.github.io/haberler)")
    g = goreli.strip().strip("/").replace("\\", "/")
    parcalar = g.split("/")
    if re.match(r"^[A-Za-z]:", g) or g.startswith("/") or ".." in parcalar or any(p == "" or p.startswith(".") for p in parcalar) or "\x00" in g:
        raise YayinHatasi("Kaynak, projenin icinde bir klasor olmali (tam yol, '..' ve gizli klasor olamaz)")
    return g


def kaynak_coz(proje_klasoru: Path, goreli: object) -> Path:
    g = kaynak_goreli(goreli)
    parcalar = g.split("/")
    kok = Path(proje_klasoru).resolve()
    yol = kok.joinpath(*parcalar)
    try:
        cozulmus = yol.resolve(strict=True)
        cozulmus.relative_to(kok)
    except (OSError, ValueError):
        raise YayinHatasi(f"Kaynak klasor bulunamadi ya da proje disina cikiyor: {g}") from None
    if not cozulmus.is_dir():
        raise YayinHatasi(f"Kaynak bir klasor olmali: {g}")
    return cozulmus


def dosyalari_listele(kaynak: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """[(goreli_yol, dosya)] ve atlananlar. Sinirlari asarsa hata verir (sessizce eksik yayinlamaz)."""
    dosyalar: list[tuple[str, Path]] = []
    atlanan: list[str] = []
    toplam = 0
    for kok, klasorler, adlar in os.walk(kaynak, followlinks=False):
        klasorler[:] = sorted(d for d in klasorler if not (d.startswith(".") or d in ATLANAN_KLASORLER or (Path(kok) / d).is_symlink()))
        for ad in sorted(adlar):
            p = Path(kok) / ad
            rel = p.relative_to(kaynak).as_posix()
            if p.is_symlink() or (ad.startswith(".") and ad not in IZINLI_NOKTALI) or github.gizli_yol_mu(rel):
                atlanan.append(rel)
                continue
            boyut = p.stat().st_size
            if boyut > AZAMI_TEK_DOSYA:
                raise YayinHatasi(f"Dosya cok buyuk ({boyut // 1_000_000} MB, en cok {AZAMI_TEK_DOSYA // 1_000_000} MB): {rel}")
            toplam += boyut
            dosyalar.append((rel, p))
            if len(dosyalar) > AZAMI_DOSYA or toplam > AZAMI_BAYT:
                raise YayinHatasi(f"Yayinlanacak klasor cok buyuk (en cok {AZAMI_DOSYA} dosya, {AZAMI_BAYT // 1_000_000} MB)")
    if not dosyalar:
        raise YayinHatasi("Kaynak klasorde yayinlanacak dosya yok" + (f" ({len(atlanan)} gizli/atlanan dosya)" if atlanan else ""))
    return dosyalar, atlanan


def _kok_aynala(dosyalar: list[tuple[str, Path]], kok: Path) -> tuple[int, list[str]]:
    """Deponun KOKUNE ekler: hicbir sey silinmez; ayni adli dosyalar degisir (degisenlerin listesi doner). .git/.github/.aktapokus'a yazilmaz."""
    ezilen: list[str] = []
    for rel, p in dosyalar:
        if rel.split("/", 1)[0] in YASAK_HEDEF:
            raise YayinHatasi(f"Kok yayininda yazilamaz: {rel}")
        h = kok.joinpath(*rel.split("/"))
        ara = kok
        for parca in rel.split("/")[:-1]:
            ara = ara / parca
            if ara.is_symlink():
                raise YayinHatasi("Hedef yolda sembolik baglanti var")
        if h.is_symlink() or (h.exists() and not h.is_file()):
            raise YayinHatasi(f"Hedefte ayni adli bir klasor/baglanti var: {rel}")
        if h.is_file() and h.read_bytes() != p.read_bytes():
            ezilen.append(rel)
    for rel, p in dosyalar:
        h = kok.joinpath(*rel.split("/"))
        h.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, h)
    return len(dosyalar), ezilen


def aynala(kaynak: Path, depo_koku: Path, hedef_yol: str, kok_izinli: bool = False) -> dict:
    """Kaynaktaki dosyalari depo_koku/hedef_yol'a kopyalar; hedefin onceki icerigi silinir. {kopyalanan, silinen, atlanan}.
    hedef_yol bos (ve kok_izinli) ise deponun kokune EKLER: hicbir sey silinmez, ayni adli dosyalar degisir ({ezilen} listesi)."""
    hedef_yol = hedef_yol_dogrula(hedef_yol, kok_izinli)
    dosyalar, atlanan = dosyalari_listele(kaynak)
    kok = Path(depo_koku).resolve()
    if not hedef_yol:
        sayi, ezilen = _kok_aynala(dosyalar, kok)
        return {"kopyalanan": sayi, "silinen": 0, "atlanan": atlanan[:20], "ezilen": ezilen[:20], "ezilen_sayisi": len(ezilen)}
    hedef = kok.joinpath(*hedef_yol.split("/"))
    try:
        hedef.resolve().relative_to(kok)
    except ValueError:
        raise YayinHatasi("Hedef klasor depo disina cikiyor") from None
    ara = kok
    for parca in hedef_yol.split("/"):
        ara = ara / parca
        if ara.is_symlink():
            raise YayinHatasi("Hedef yolda sembolik baglanti var")
    silinen = 0
    if hedef.exists():
        if not hedef.is_dir():
            raise YayinHatasi("Hedef yol depoda bir dosya; klasor olmali")
        silinen = sum(len(f) for _, _, f in os.walk(hedef))
        shutil.rmtree(hedef)
    for rel, p in dosyalar:
        h = hedef / rel
        h.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, h)
    return {"kopyalanan": len(dosyalar), "silinen": silinen, "atlanan": atlanan[:20]}


def calisma_geri_al(depo_koku: Path, hedef_yol: str) -> None:
    """Kopyalanan ama commit EDILMEMIS icerigi geri alir (yayin engellendiginde hedef depo eski haline doner): izlenen dosyalar HEAD'e doner, yeniler silinir.
    Bos hedef (kok): hedef depo kopyalamadan once temizdi (yayin_hazirla bunu sart kosar), bu yuzden tum calisma agaci geri alinir."""
    hedef_yol = hedef_yol_dogrula(hedef_yol, True) or "."
    github._git(Path(depo_koku), "restore", "--staged", "--worktree", "--source=HEAD", "--", hedef_yol, kontrol=False)
    github._git(Path(depo_koku), "clean", "-fdq", "--", hedef_yol, kontrol=False)


def commit_geri_al(depo_koku: Path, onceki_head: str) -> None:
    """Yalniz BIZIM yaptigimiz son commit'i geri alir (HEAD'in ebeveyni `onceki_head` ise); baska bir durumda dokunmaz ve hata verir."""
    k = Path(depo_koku)
    if github._git(k, "rev-parse", "HEAD~1", kontrol=False).strip() != onceki_head or not re.fullmatch(r"[0-9a-f]{40}", onceki_head or ""):
        raise YayinHatasi("Son commit bizim degil; otomatik geri alma yapilmadi (hedef depoyu kontrol edin)")
    github._git(k, "reset", "--hard", onceki_head)


def yayin_adresi(depo: str, hedef_yol: str) -> str:
    """Olasi GitHub Pages adresi: `<sahip>.github.io` deposu kokten, diger depolar `<sahip>.github.io/<depo>/` altindan yayinlanir (Pages acik olmali)."""
    sahip, ad = depo.split("/", 1)
    taban = f"https://{ad}" if ad.lower() == f"{sahip.lower()}.github.io" else f"https://{sahip}.github.io/{ad}"
    return f"{taban}/{hedef_yol}/" if hedef_yol else f"{taban}/"
