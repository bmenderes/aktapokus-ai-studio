"""Gorev geri bildirimi sadelestirme: araclar adim basina tek kapali satir, yanit duz metin, degisen dosya listesi yalniz Degisiklikler sekmesinde."""

import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"


def _html() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def _olay_isle(html: str) -> str:
    return html.split("function olayIsle(o){")[1].split("async function karar(")[0]


def test_araclar_adim_basina_tek_kapali_satirda_toplanir():
    html = _html()
    govde = _olay_isle(html)
    assert "function aracGrubu(" in html and 'e("details",{class:"arac-grup"}' in html
    assert 'aracGrubu(S.canliSira,S.canliDiv)' in govde and '" araç adımı"' in govde
    assert "insertBefore(aracKarti(o)" not in govde  # her arac ayri kart olarak akisi doldurmaz
    assert 'e("details",{class:"arac-grup"},ozet,e("div"))' in html

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
