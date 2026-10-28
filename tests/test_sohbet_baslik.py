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
