"""Otomasyon rehberi (resimli yardim): web/yardim/otomasyon*.html statik servis edilir (belirtecsiz, yalniz izin listesi), arayuzde yan cerceve olarak acilir,
TR ve EN sayfalari ayni bolumleri ve resimleri icerir, dis kaynak yuklemez."""

import re
from pathlib import Path

from test_pwa import _ham_get
from test_uzak import ac, ortam, sunucu  # noqa: F401  (pytest fixture'lari)

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
SAYFALAR = {"tr": (WEB / "yardim" / "otomasyon.html").read_text(encoding="utf-8"), "en": (WEB / "yardim" / "otomasyon-en.html").read_text(encoding="utf-8")}


def test_yardim_sayfalari_tutarli_resimli_ve_dis_kaynaksiz():
    bolumler = {d: re.findall(r'<h2 id="([a-z]+)"', s) for d, s in SAYFALAR.items()}
    assert bolumler["tr"] == bolumler["en"] and {"ilk", "dugum", "haber", "onay", "yayin", "telegram", "hesap", "sinir"} <= set(bolumler["tr"])
    for d, s in SAYFALAR.items():
        assert s.count("<svg") == 10 and s.count("<svg") == s.count("</svg>")  # her sayfada ayni 10 resim
        assert s.count("<figure>") == 10 and 'lang="' + d + '"' in s
        assert "<script" not in s and "<iframe" not in s and "<img" not in s
        assert set(re.findall(r'(?:https?:)?//[^\s"\')>]+', s)) <= {"http://www.w3.org/2000/svg"}  # dis adres yok (yalniz SVG ad alani)
        assert "Segoe" not in s and "Inter" in s
        for bolum in bolumler[d]:  # icindekiler baglantilari gecerli
            assert f'href="#{bolum}"' in s
    # arayuzun yardim dugmeleri bu bolumlere gider
    for parca in ('yardimDugmesi("ilk")', '"/yardim/otomasyon.html")+"#dugum"'):  # dugum yardimi duzenleyicinin yan cercevesinde
        assert parca in HTML
    assert {"ilk", "dugum"} <= set(bolumler["tr"])


def test_yardim_sayfalari_belirtecsiz_servis_edilir_baska_adlar_reddedilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    for adres, h, p in (("127.0.0.1", f"127.0.0.1:{sv.port}", sv.port), ("127.0.0.2", f"127.0.0.2:{port}", port)):
        for ad, dil in (("otomasyon", "tr"), ("otomasyon-en", "en")):
            st, ct, govde = _ham_get(p, f"/yardim/{ad}.html", h, adres)
            assert st == 200 and ct.startswith("text/html") and f'lang="{dil}"' in govde.decode("utf-8", "replace") if isinstance(govde, bytes) else f'lang="{dil}"' in govde
        for kotu in ("/yardim/baska.html", "/yardim/../index.html", "/yardim/%2e%2e/index.html", "/yardim/otomasyon.html/x", "/yardim/Otomasyon.html", "/yardim/otomasyon.js", "/yardim/"):
            assert _ham_get(p, kotu, h, adres)[0] in (403, 404), kotu


def test_arayuz_yardim_paneli_yan_cerceve_ve_dile_gore_sayfa():
    for parca in ("function yardimPaneli", '"/yardim/otomasyon-en.html"', '"/yardim/otomasyon.html"', 'id:"yardimPaneli"', "position:fixed", "iframe"):
        assert parca in HTML, parca
    assert "frame-src 'self'" in (WEB.parent / "arayuz.py").read_text(encoding="utf-8")  # ayni kokenli cerceve CSP'de acik
    assert '"web/yardim/*.html"' in (WEB.parent.parent / "pyproject.toml").read_text(encoding="utf-8")  # paketlemeye dahil
