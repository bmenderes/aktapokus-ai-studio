"""Gorev geri bildirimi sadelestirme: araclar adim basina tek kapali satir, yanit duz metin, degisen dosya listesi yalniz Degisiklikler sekmesinde."""

import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"


def _html() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def _olay_isle(html: str) -> str:
    return html.split("function olayIsle(o){")[1].split("async function karar(")[0]


def test_canli_akis_adim_basina_tek_zaman_sirali_akista():
    """2026-11-23 kullanici istegi: geri bildirim Claude Code gibi tek akista; metin/arac/komut sirayla, ic kaydirma ve birikmis gecici durum yok."""
    html = _html()
    govde = _olay_isle(html)
    assert "function akisGrubu(" in html and 'akisGrubu(S.canliSira,S.canliDiv)' in govde
    assert 'ak.liste.append(k)' in govde  # arac karti akisa sirayla eklenir (ayri liste degil)
    assert 'class:"fb-satir fb-durum"' not in govde  # 'model bekleniyor' gibi durumlar akista birikmez
    css = re.search(r"\.ak-liste\{[^}]*\}", html).group(0)
    assert "max-height" not in css and "overflow" not in css  # ic kaydirma yok

def test_yanit_duz_metin_ve_fark_tek_satir():
    govde = _olay_isle(_html())
    assert 'text:"yanıt"' not in govde  # 'yanit' ozetli ac/kapa kutusu yok
    fark = govde.split('case "fark":')[1].split('case "karar-bekleniyor"')[0]
    assert 'class:"fark-sade"' in fark and 'sekme("p-degisiklik")' in fark and "fark-satir" not in fark and "dosya daha" not in fark
    assert 'id:"karar-dugmeleri"' in fark  # bitti olayi bu kapsayiciyi hala temizler
    bitti = govde.split('case "bitti":')[1].split('case "kuyruk"')[0]
    assert '" dosya: "' not in bitti  # dosya listesi bitis satirinda tekrarlanmaz


def test_arac_adimi_sayaci_ingilizceye_cevrilir():
    desen = json.loads((WEB / "diller" / "en.json").read_text(encoding="utf-8"))["desen"]
    sonuc = {}
    for kalip, yeni in desen:
        for metin in ("1 araç adımı", "7 araç adımı"):
            if metin not in sonuc and re.search(kalip, metin):
                sonuc[metin] = re.sub(kalip, yeni.replace("$1", r"\1"), metin)
    assert sonuc == {"1 araç adımı": "1 tool step", "7 araç adımı": "7 tool steps"}


def test_canli_durum_tek_satir_ve_yanitta_yuvarlak_kopyala_dugmesi():
    html = _html()
    govde = _olay_isle(html)
    assert ".canli{white-space:nowrap;text-overflow:ellipsis" in html and "max-height:80px" not in html.split(".canli{")[1].split("}")[0]
    assert 'S.canliTam.split("\\n").filter(x=>x.trim()).pop()' in govde  # yalniz son satir gosterilir
    assert 'class:"ikon-yuvarlak",title:"Kopyala"' in govde and "navigator.clipboard.writeText(o.metin)" in govde
    assert ".ikon-yuvarlak{flex:none;width:22px;height:22px" in html and "border-radius:50%" in html.split(".ikon-yuvarlak{")[1].split("}")[0]


def test_cli_rozetleri_renkli_saglayicilar_kaldirildi_hafiza_ve_canli_geri_bildirim_var():
    html = _html()
    assert '.badge[class*="b-"]' not in html
    assert ".badge.b-ok{background:var(--okbg)!important" in html and ".badge.b-err{background:var(--errbg)!important" in html
    assert '["saglayicilar",' not in html
    assert "cliDenemeKaydet" in html and "aktapokus.cliDeneme" in html
    assert "Hafıza (.md)" in html and "async function hafizaAc(" in html and "/api/konusma-hafiza" in html
    assert "function fbGrubu(" in html and 'o.alt==="arac-sonuc"' in html


def test_ilk_acilis_uc_tek_satir_adim_ve_kendiliginden_gizlenir():
    """2026-11-23: ilk acilis rehberi (arac, proje, ilk gorev). Acilir pencere degil; hepsi tamamlaninca ya da kapatilinca gizlenir."""
    html = _html()
    assert 'id="ilkAdim"' in html and "async function ilkAdimCiz(" in html
    govde = html.split("async function ilkAdimCiz(")[1].split("\nasync function kenarCubugu(")[0]
    assert 'adimlar.every(a=>a[1])' in govde and 'k.style.display="none"' in govde  # hepsi tamam: gizli
    assert "ILK_GIZLE" in govde and "modal" not in govde  # kapatilabilir; acilir pencere yok
    assert "sohbetOzetiYukle();ilkAdimCiz()" in html  # proje/sohbet degisince yenilenir
