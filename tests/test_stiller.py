"""Arayuz stilleri (docs/arayuz-stilleri.md): yazi boyutu ve agirlik sinirlari, Inter, Segoe yasagi."""

import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _html() -> str:
    return (KOK / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_govde_14px_yumusak_sans_ilk_secenek_inter_yedek():
    """Kullanici istegi (2026-10-30): Inter fazla keskin/kucuk bulundu; govde 14 px, yumusak hatli sistem yazisi ilk, Inter yedek."""
    html = _html()
    govde = re.search(r"\nbody\{background:var\(--bg\)[^}]*\}", html).group(0)
    assert 'font:15px/1.55 "Lora",Georgia' in govde
    assert govde.index('"Lora"') < govde.index("system-ui") < govde.index('"Inter"')


def test_yazi_boyutu_ust_siniri_ve_alt_siniri():
    html = _html()
    boyutlar = [float(b) for b in re.findall(r"font-size:\s*([\d.]+)px", html)]
    assert boyutlar and max(boyutlar) <= 18, max(boyutlar)  # 18 px: yalniz eslestirme kodu
    buyukler = [b for b in boyutlar if b > 15]
    assert len(buyukler) <= 2 + 1, buyukler  # eslestirme kodu (18) ve mobil input (16) disinda buyuk yazi yok
    assert ".ayar-baslik{font-size:15px;" in html and ".md h1{font-size:14px" in html


def test_kalin_700_yalniz_okunmamis_sayac_icin():
    html = _html()
    assert html.count("font-weight:700") <= 3 and "font-weight:800" not in html and "font-weight:900" not in html.replace("100 900", "")


def test_stil_belgesi_var_ve_ana_kurallari_icerir():
    belge = (KOK / "docs" / "arayuz-stilleri.md").read_text(encoding="utf-8")
    for parca in ("Açıklama yok", "Tek satır", "yuvarlak", "Tekrar yok", "Inter", "15 px", "en az 12 px", "test edilir"):
        assert parca in belge, parca


def test_sekme_cubugu_dar_panelde_kayar_arac_dugmeleri_ve_aktif_sekme_gorunur():
    """Dar sag panelde son sekmenin x'i ve + / genislet / kapat dugmeleri ekran disinda kalmamali."""
    html = _html()
    cubuk = re.search(r"#sekmeler\{[^}]*\}", html).group(0)
    assert "flex-wrap:nowrap" in cubuk and "overflow-x:auto" in cubuk
    assert "position:sticky;right:0" in re.search(r"\.sekme-araclar\{[^}]*\}", html).group(0)
    assert "flex:none;white-space:nowrap" in re.search(r"\.sekme\{[^}]*\}", html).group(0)
    assert 'b.scrollIntoView({inline:"nearest",block:"nearest"})' in html  # secilen sekme gorunume kaydirilir
