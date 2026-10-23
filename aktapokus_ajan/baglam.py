"""Ortak baglam: hangi model/CLI calisirsa calissin AYNI kurallari gorsun ve kaldigi yerden devam edebilsin.

Tek kaynak: <proje>/.aktapokus/baglam.md (kullanicinin kurallari). Bundan her CLI'in okudugu dosyaya YONETILEN BIR BLOK yazilir:
  AGENTS.md  (OpenCode, Codex)   CLAUDE.md (yalniz Claude Code rolu varsa)   GEMINI.md (yalniz Gemini rolu varsa)
Blok disindaki icerige (kullanicinin kendi AGENTS.md metni) DOKUNULMAZ. Blok KARARLIDIR (calistirmadan calistirmaya degismez),
boylece proje git gecmisinde gurultu olusturmaz ve token tasarrufu icin kisadir. Degisen bilgi (son calistirmalarin ozeti)
`.aktapokus/DURUM.md` dosyasindadir (git'e girmez); bloktaki bir satir ve istem, modele once onu okumasini soyler.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import AYAR_KLASORU, Ayar

BASLA_ONEK = "<!-- aktapokus:basla"
BASLA = BASLA_ONEK + " (bu blogu Aktapokus yonetir; elle degistirmeyin, kurallari .aktapokus/baglam.md dosyasinda duzenleyin) -->"
BITIR = "<!-- aktapokus:bitir -->"
KAYNAK_ADI = "baglam.md"
DURUM_ADI = "DURUM.md"
AZAMI_KURAL = 2000
AZAMI_DURUM = 1800
SON_CALISTIRMA = 6
VARSAYILAN_KURALLAR = (
    "## Aktapokus çalışma kuralları\n"
    "- Kullanıcıyla Türkçe konuş.\n"
    "- Yalnızca bu proje klasöründe çalış; klasör dışına yazma, `.env` ve anahtar/parola dosyalarını okuma ya da yazma.\n"
    "- Küçük, odaklı değişiklikler yap; çalışan bir şeyi bozma, değişiklikten sonra varsa testleri çalıştır.\n"
    "- İş bitince ne yaptığını kısaca özetle; yarım kalanı açıkça belirt.\n"
    "- Hedef makinede ek kurulum (Python, SDK) gerektirme.\n"
)
DURUM_ISARETI = "Önceki çalışmaların özeti ve yarım kalanlar: `.aktapokus/DURUM.md` (varsa önce oku)."


def kaynak_yolu(klasor: str | Path) -> Path:
    return Path(klasor) / AYAR_KLASORU / KAYNAK_ADI


def durum_yolu(klasor: str | Path) -> Path:
    return Path(klasor) / AYAR_KLASORU / DURUM_ADI


def kurallar(klasor: str | Path) -> str:
    """Kullanicinin kurallari (yoksa varsayilan), AZAMI_KURAL ile sinirli: her adimda baglama girer."""
    try:
        metin = kaynak_yolu(klasor).read_text(encoding="utf-8").strip()
    except OSError:
        metin = ""
    metin = metin or VARSAYILAN_KURALLAR.strip()
    if len(metin) > AZAMI_KURAL:
        metin = metin[:AZAMI_KURAL].rstrip() + "\n... [kısaltıldı: kurallar çok uzun, kısa tutun; her adımda modele gider]"
    return metin


def blok_uret(klasor: str | Path) -> str:
    return f"{BASLA}\n{kurallar(klasor)}\n\n{DURUM_ISARETI}\n{BITIR}"


def dosya_adlari(ayar: Ayar) -> list[str]:
    adlar = ["AGENTS.md"]
    kullanilan = {r.calistirici for r in ayar.roller.values()}
    if "claude" in kullanilan:
        adlar.append("CLAUDE.md")
    if "gemini" in kullanilan:
        adlar.append("GEMINI.md")
    return adlar


def bloku_yaz(dosya: Path, blok: str) -> str:
    """'olusturuldu' | 'guncellendi' | 'ayni'. Dosya varsa yalniz blogu degistirir (ya da sonuna ekler)."""
    if not dosya.exists():
        dosya.write_text(blok + "\n", encoding="utf-8")
        return "olusturuldu"
    metin = dosya.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in metin else "\n"
    blok_nl = blok.replace("\n", nl)
    b, s = metin.find(BASLA_ONEK), metin.find(BITIR)
    if b != -1 and s != -1 and s > b:
        yeni = metin[:b] + blok_nl + metin[s + len(BITIR):]
    else:  # blok yok (ya da bozuk isaretler): sona ekle, kullanicinin metnine dokunma
        yeni = metin.rstrip("\r\n") + (nl + nl if metin.strip() else "") + blok_nl + nl
    if yeni == metin:
        return "ayni"
    dosya.write_text(yeni, encoding="utf-8")
    return "guncellendi"


def durum_metni(klasor: str | Path) -> str:
    """Son calistirmalarin model/CLI'dan bagimsiz ozeti (.aktapokus/kayit/*.json): kimin ne yaptigi ve neyin yarim kaldigi."""
    kayitlar = []
    kayit_klasoru = Path(klasor) / AYAR_KLASORU / "kayit"
    dosyalar = sorted(kayit_klasoru.glob("*.json"))[-SON_CALISTIRMA:] if kayit_klasoru.is_dir() else []
    for yol in dosyalar:
        try:
            kayitlar.append(json.loads(yol.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    satirlar = ["# Proje durumu", "(Aktapokus üretir; elle düzenlemeyin. Model/CLI'dan bağımsızdır: hangi model devam ederse etsin buradan öğrenir.)", ""]
    if not kayitlar:
        satirlar.append("Henüz Aktapokus ile yapılmış bir çalıştırma yok.")
    for k in reversed(kayitlar):
        roller = ", ".join(f"{a['rol']}({a.get('calistirici', '?')}/{(a.get('model') or '-').split('/')[-1]})" for a in k.get("adimlar", [])[:4])
        degisen = ", ".join(f"{y} ({d})" for y, d in list(k.get("degisen", {}).items())[:8])
        satirlar.append(f"- {k.get('zaman', '?')} | {k.get('durum', '?')} | {roller or '-'}")
        satirlar.append(f"  Görev: {' '.join(str(k.get('gorev', '')).split())[:160]}")
        if degisen:
            satirlar.append(f"  Değişen: {degisen}")
        yarim = k.get("durum") not in ("onaylandi", "degisiklik_yok", "geri_alindi", "reddedildi")
        if k.get("mesaj") or yarim:
            satirlar.append(f"  {'YARIM/SORUNLU: ' if yarim else 'Not: '}{' '.join(str(k.get('mesaj', '')).split())[:200]}")
    metin = "\n".join(satirlar)
    return metin if len(metin) <= AZAMI_DURUM else metin[:AZAMI_DURUM].rstrip() + "\n... [kısaltıldı]"


def guncelle(klasor: str | Path, ayar: Ayar) -> dict[str, str]:
    """Baglam dosyalarini ve DURUM.md'yi gunceller. {dosya: durum}. Calistirmadan ONCE (anlik goruntuden once) cagrilmali."""
    klasor = Path(klasor)
    sonuc: dict[str, str] = {}
    blok = blok_uret(klasor)
    for ad in dosya_adlari(ayar):
        sonuc[ad] = bloku_yaz(klasor / ad, blok)
    yol = durum_yolu(klasor)
    yol.parent.mkdir(parents=True, exist_ok=True)
    metin = durum_metni(klasor) + "\n"
    onceki = yol.read_text(encoding="utf-8") if yol.exists() else None
    if onceki != metin:
        yol.write_text(metin, encoding="utf-8")
    sonuc[f"{AYAR_KLASORU}/{DURUM_ADI}"] = "ayni" if onceki == metin else ("olusturuldu" if onceki is None else "guncellendi")
    return sonuc


def kaynak_olustur(klasor: str | Path) -> str:
    """Kullanicinin duzenleyecegi kural dosyasini yoksa varsayilanla olusturur. 'olusturuldu' | 'mevcut'."""
    yol = kaynak_yolu(klasor)
    if yol.exists():
        return "mevcut"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(VARSAYILAN_KURALLAR, encoding="utf-8")
    return "olusturuldu"
