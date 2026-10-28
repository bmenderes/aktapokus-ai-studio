"""Sohbet basligi: hangi projede hangi adla calisildigi sohbet alaninda (telefonda kenar cubugu kapaliyken) gorunur."""

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_sohbet_basligi_proje_ve_gorev_adini_gosterir_ve_dogru_yerlerde_guncellenir():
    assert '<div id="sohbetBaslik"></div>\n    <div id="akis">'.replace("\n", "\r\n") in HTML or '<div id="sohbetBaslik"></div>\n    <div id="akis">' in HTML
    assert "function sohbetBasligiCiz()" in HTML and 't.ozel_ad||t.gorev' in HTML and '"Yeni görev"' in HTML
    for yer in ("kenarCiz();sohbetBasligiCiz()", "S.gecmisGorev=id;S.sohbetYeni=false;sohbetBasligiCiz()", "S.sohbetYeni=true;sohbetBasligiCiz()", "S.projeId=d.proje||null;sohbetBasligiCiz()"):
        assert yer in HTML, yer
    assert "#sohbetBaslik{flex:none;" in HTML and "text-overflow:ellipsis" in HTML.split("#sohbetBaslik{", 1)[1].split("}", 1)[0]  # tek satir


def test_baslik_tiklaninca_gorev_adi_degistirilir_yeni_sohbette_tiklanmaz():
    assert "async function sohbetAdiDegistir(g,t)" in HTML and 'api("/api/p/"+g.id+"/gorev-meta",{method:"POST",body:{id:t.id,ad:yeni}})' in HTML
    assert 'b.onclick=t?()=>sohbetAdiDegistir(g,t):null' in HTML and "#sohbetBaslik.duzenlenir{cursor:pointer}" in HTML
    assert "konusmaGruplari(g).find(x=>x.some(y=>y.id===S.gecmisGorev))" in HTML  # kenar cubugundaki ile ayni sohbet/gorev (grubun en yenisi)


def test_sohbet_adi_yeni_gorev_eklenince_eski_metne_donmez_en_yeni_ad_gecerlidir():
    """GERCEK HATA: ad grubun en yeni gorevine yazilir; sohbete yeni gorev eklenince en yeni gorevin adi bos oldugu icin baslik ilk gorev metnine donuyordu."""
    import json
    import re
    import shutil
    import subprocess

    import pytest

    if shutil.which("node") is None:
        pytest.skip("node kurulu degil")
    fn = re.search(r"function konusmaOzeti\(a\)\{.*?\}\n", HTML, re.S).group(0)
    betik = fn + """
const g = (id, ad, gorev) => ({id, zaman: id, gorev, ozel_ad: ad, degisen_sayisi: 1});
const out = {
  // en yeni basta: [yeni gorev (adsiz), eski gorev (ADLI)] -> ad korunur
  adli_sonra_yeni: konusmaOzeti([g("3", "", "ucuncu"), g("2", "Benim adim", "ikinci"), g("1", "", "birinci")]).ozel_ad,
  // iki ad varsa en yenisi gecer
  iki_ad: konusmaOzeti([g("3", "", "c"), g("2", "Yeni ad", "b"), g("1", "Eski ad", "a")]).ozel_ad,
  // hic ad yok: bos (arayuz gorev metnini kullanir)
  hic_ad: konusmaOzeti([g("2", "", "b"), g("1", "", "a")]).ozel_ad,
  idler: konusmaOzeti([g("2", "", "b"), g("1", "", "a")]).idler,
};
console.log(JSON.stringify(out));
"""
    s = subprocess.run(["node", "-e", betik], capture_output=True, text=True, encoding="utf-8")
    assert s.returncode == 0, s.stderr[:500]
    d = json.loads(s.stdout)
    assert d == {"adli_sonra_yeni": "Benim adim", "iki_ad": "Yeni ad", "hic_ad": "", "idler": ["2", "1"]}
    assert 'body:{id:o.id,ad:""}' in HTML  # ad temizlenince sohbetteki eski adlar da temizlenir
