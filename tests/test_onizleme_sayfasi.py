from aktapokus_ai_studio.arayuz import Uygulama


def test_onizleme_asil_siteyi_yardimci_sayfaya_tercih_eder(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (tmp_path / "site" / "veri.js").write_text("var a=1", encoding="utf-8")
    (tmp_path / "KOPYALA.html").write_text("<p>y</p>", encoding="utf-8")
    f = Uygulama._onizleme_sayfasi
    assert f(tmp_path, [{"yol": "KOPYALA.html", "tur": "html"}]) == "KOPYALA.html"
    assert f(tmp_path, [{"yol": "site/veri.js", "tur": "js"}, {"yol": "KOPYALA.html", "tur": "html"}]) == "site/index.html"
    assert f(tmp_path, [{"yol": "site/index.html", "tur": "html"}, {"yol": "KOPYALA.html", "tur": "html"}]) == "site/index.html"
    assert f(tmp_path, [{"yol": "../dis/x.js", "tur": "js"}]) is None
    assert f(tmp_path, []) is None
