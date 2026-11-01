"""Ayarlar cerceveleri: Terminal ile cakisma, Esc sirasi, bolucu, kayitsiz otomasyon formu, bolum yarisi (denetim 2026-11-01)."""

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def _govde(bas: str) -> str:
    return HTML.split(bas)[1].split("\n")[0]


def test_ayarlar_ve_terminal_ayni_anda_acik_olmaz():
    assert "terminalKapat();" in _govde("function ayarAc(id){")
    assert '$("#ayarlar").classList.contains("on")&&!ayarKapat()' in _govde("async function terminalAc(){")


def test_esc_once_en_ustteki_katmani_kapatir():
    i = HTML.index('document.addEventListener("keydown",ev=>{if(ev.key!=="Escape")return;const m=')
    parca = HTML[i:i + 700]
    assert parca.index(".modal-arka") < parca.index(".rd-arka") < parca.index("ayarKapat()")
    assert '.some(x=>getComputedStyle(x).display!=="none"))return' in parca


def test_bolucu_ayarlar_menusunun_ustunde_kalmaz():
    assert "body:has(#ayarlar.on) #bolucuSol" in HTML and "pointer-events:none" in HTML.split("body:has(#ayarlar.on) #bolucuSol")[1][:120]


def test_sigmayan_ayarlar_tum_genisligi_kullanir():
    assert "AYAR_EN_AZ=760" in HTML and "g-ayarSag<AYAR_EN_AZ" in HTML and '"ayar-tam"' in HTML


def test_kayitsiz_otomasyon_formu_sormadan_kaybolmaz():
    assert "if(!otoFormTerk())return false" in _govde("function ayarKapat(){")
    assert "id!==S.ayarBolum&&!otoFormTerk()" in _govde("async function ayarGit(id){")
    assert 'k.dataset.kirli="1"' in HTML


def test_ayarlar_kapaninca_sayac_durur():
    assert "clearInterval(S.telegramZ)" in _govde("function ayarKapat(){")


def test_gec_gelen_bolum_yeni_bolume_karismaz():
    g = _govde("async function ayarGit(id){")
    assert 'const h=e("div");ic.append(h)' in g and 'ic.textContent=""' in g


def test_otomasyon_duzenleyici_tam_ekran_ve_yakinlastirilir():
    assert '#otoForm.oto-tam{position:fixed;inset:0' in HTML and "height:300px" not in HTML.split(".oto-tuval{")[1][:80]
    assert "sahne.style.zoom=oran" in HTML and "ev.ctrlKey" in HTML and "sigdir()" in HTML
    assert "m.clientX/oran-dx" in HTML and "(m.clientX-r.left+tuval.scrollLeft)/oran" in HTML  # surukleme ve baglama oranla uyumlu


def test_esc_acik_duzenleyiciyi_ayarlardan_once_kapatir():
    i = HTML.index('const of=$("#otoForm");if(of){if(otoFormTerk()')
    assert HTML.index('if($("#ayarlar").classList.contains("on"))ayarKapat()});') > i


def test_otomasyon_yan_cercevesi_acilip_kapanir():
    assert 'id:"otoYan"' in HTML and "yanDegis" in HTML and 'text:"Dosyalar"' in HTML and "Otomasyon yardımı" in HTML
    assert 'pYol("/ciktilar")' in HTML and 'pYol("/dosyalar")' in HTML and 'pYol("/dosya?yol="' in HTML  # secili projenin ciktilari ve belgeleri okunur
    assert HTML.index('const yan=$("#otoYan.on")') < HTML.index('const of=$("#otoForm");if(of){')  # Esc once yan cerceveyi kapatir


def test_klon_satiri_kalkti_ag_popup_acmaz():
    assert 'id="klon"' not in HTML and "klon_bekleyen" not in HTML
    assert 'window.open("/ag' not in HTML


def test_bos_ekran_yeni_simgeyi_kullanir():
    assert "--maskot:url(/simge-512.png)" in HTML
