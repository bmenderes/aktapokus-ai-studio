"""Sohbet ekrani en alta yapisik kalir ve sayfa yeniden acilinca/sekmeye donulunce en son yere iner."""

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_yeni_icerik_resim_ve_boyut_degisikligi_altta_tutulur_kullanici_yukaridaysa_dokunulmaz():
    assert "#akis{flex:1;overflow:auto;padding:10px;overflow-anchor:none}" in HTML  # tarayicinin kaydirma capasi sohbeti yukari oynatmasin
    assert "const a=$(\"#akis\"),sabitle=()=>{if(S.altaYapisik)a.scrollTop=a.scrollHeight}" in HTML  # yalniz alta yapisiksa
    assert 'a.addEventListener("load",sabitle,true)' in HTML  # resimler sonradan yuklenince
    assert "new ResizeObserver(sabitle)" in HTML and "ro.observe(a)" in HTML  # kutu (klavye/yazi kutusu) ve icerik boyutu degisince
    assert "a.addEventListener(\"scroll\",()=>{S.altaYapisik=a.scrollTop+a.clientHeight>=a.scrollHeight-70})" in HTML


def test_sayfa_acilinca_ve_sekmeye_donunce_en_son_yere_inilir():
    assert "function alttaGoster(){S.altaYapisik=true;" in HTML and "requestAnimationFrame(git);setTimeout(git,250);setTimeout(git,1000)" in HTML
    assert 'document.addEventListener("visibilitychange",()=>{if(!document.hidden){akisiYenidenKur();alttaGoster()}})' in HTML
    assert 'addEventListener("pageshow",()=>{akisiYenidenKur();alttaGoster()})' in HTML
    assert "alttaGoster();if(hedef){" in HTML  # gecmis konusma yuklenince
