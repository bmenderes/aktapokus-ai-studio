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
AZAMI_DURUM = 3200
AZAMI_YANIT = 240  # her calistirmanin son yanitindan alinan parca: sonraki model "ne konusuldu/ne bulundu"yu bilsin
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
        yanit = next((" ".join(str(a.get("metin", "")).split()) for a in reversed(k.get("adimlar", [])) if a.get("ok") and a.get("metin") and not a.get("dogrulama")), "")
        if yanit:
            satirlar.append(f"  Yanıt: {yanit[:AZAMI_YANIT]}{'…' if len(yanit) > AZAMI_YANIT else ''}")
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


def istem_baglami(klasor: str | Path) -> str:
    """AGENTS.md'yi projeye GUVENMEDIGI icin yok sayan CLI'lar (Mistral Vibe: 'folder is not trusted; AGENTS.md will be ignored') icin kurallar ve onceki
    calismalar ISTEMIN BASINA konur. Baglam kapaliysa (DURUM.md hic yazilmamissa) bos doner. Klasore guven verilmez (zehirli depo korumasi)."""
    try:
        durum = durum_yolu(klasor).read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not durum:
        return ""
    return (
        "[Aktapokus ortak bağlam: kurallar ve önceki çalışmalar (başka modeller dahil)]\n"
        f"{kurallar(klasor)}\n\n{durum}\n"
        "[/Aktapokus ortak bağlam]\n\n"
    )


OZET_ADI = "KONUSMA-OZETI.md"
OZET_ISTEMI = f"`{AYAR_KLASORU}/{OZET_ADI}` dosyasını önce oku, sonra kaldığın yerden devam et."
OZET_AYRINTILI = 12  # son bu kadar calisma tam, daha eskiler tek satir


def _kisalt(metin: object, n: int) -> str:
    m = " ".join(str(metin or "").split())
    return m if len(m) <= n else m[:n].rstrip() + "…"


def konusma_ozeti_yaz(klasor: str | Path) -> dict:
    """Projenin TUM calisma kayitlarindan (hangi model/CLI olursa olsun) kronolojik konusma ozeti: `.aktapokus/KONUSMA-OZETI.md`. Basa donen bir modele
    OZET_ISTEMI verilir. Her calisma bittiginde ve 'ozeti yenile' dugmesiyle guncellenir. {yol, kayit, istem} doner."""
    klasor = Path(klasor)
    kayitlar = []
    kayit_klasoru = klasor / AYAR_KLASORU / "kayit"
    for yol in sorted(kayit_klasoru.glob("*.json")) if kayit_klasoru.is_dir() else []:
        try:
            k = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(k, dict) and isinstance(k.get("adimlar"), list):
            kayitlar.append(k)
    satir = [
        "# Konuşma özeti (Aktapokus kayıtlarından üretildi)",
        "",
        "Bu projede farklı modellerle (OpenCode, Claude Code, Mistral vb.) yapılan çalışmaların kronolojik özetidir; model değişse de buradan devam edilir.",
        f"Kullanım: yeni bir modele şunu söyleyin: {OZET_ISTEMI}",
        "",
    ]
    eski, son = kayitlar[:-OZET_AYRINTILI], kayitlar[-OZET_AYRINTILI:]
    if eski:
        satir.append("## Daha eski çalışmalar (tek satır)")
        satir += [f"- {k.get('zaman', '?')} | {k.get('durum', '?')} | {_kisalt(k.get('gorev'), 140)}" for k in eski]
        satir.append("")
    satir.append("## Son çalışmalar (eskiden yeniye)" if son else "Henüz Aktapokus ile yapılmış bir çalıştırma yok.")
    for k in son:
        roller = ", ".join(f"{a.get('rol')}({a.get('calistirici', '?')})" for a in k["adimlar"][:4] if isinstance(a, dict))
        satir.append(f"### {k.get('zaman', '?')} — {k.get('durum', '?')} — {roller}")
        satir.append(f"**İstek:** {_kisalt(k.get('gorev'), 500)}")
        degisen = list((k.get("degisen") or {}).items())
        if degisen:
            satir.append("**Değişen dosyalar:** " + ", ".join(f"{y} ({d})" for y, d in degisen[:10]) + (f" … (+{len(degisen) - 10})" if len(degisen) > 10 else ""))
        yanit = next((a.get("metin") for a in reversed(k["adimlar"]) if isinstance(a, dict) and a.get("ok") and a.get("metin") and not a.get("dogrulama")), "")
        if yanit:
            satir.append("**Son yanıt:** " + _kisalt(yanit, 1500))
        if k.get("mesaj") and k.get("durum") not in ("onaylandi", "degisiklik_yok", "geri_alindi"):
            satir.append("**Sorun/not:** " + _kisalt(k.get("mesaj"), 300))
        satir.append("")
    hedef = klasor / AYAR_KLASORU / OZET_ADI
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("\n".join(satir), encoding="utf-8")
    return {"yol": f"{AYAR_KLASORU}/{OZET_ADI}", "kayit": len(kayitlar), "istem": OZET_ISTEMI}


def kaynak_olustur(klasor: str | Path) -> str:
    """Kullanicinin duzenleyecegi kural dosyasini yoksa varsayilanla olusturur. 'olusturuldu' | 'mevcut'."""
    yol = kaynak_yolu(klasor)
    if yol.exists():
        return "mevcut"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(VARSAYILAN_KURALLAR, encoding="utf-8")
    return "olusturuldu"
