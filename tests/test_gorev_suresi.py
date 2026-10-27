"""Gorev suresi gostergesi (ne kadar suredir calisiyor) ve Gemini/Mistral giris ipuclari."""

import time
from pathlib import Path

from aktapokus_ai_studio import hesaplar, motorlar
from test_arayuz import BASARILI, bekle, klasor_sec, kur  # noqa: F401  (kur: pytest fixture'i)
from test_devam import Engelleyici

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_durum_calisan_gorevin_gecen_suresini_verir_bitince_vermez(kur):
    eng = Engelleyici()
    app, sv, api, _ = kur({"kodcu": eng.kodcu, "test": BASARILI})
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "uzun is"})[1]
    assert api("GET", "/api/durum")[1]["kosu"]["gecen_sn"] is None  # plan asamasinda sayac yok
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert eng.basladi.wait(10)
    time.sleep(1.2)
    g = api("GET", "/api/durum")[1]["kosu"]["gecen_sn"]
    assert isinstance(g, int) and 1 <= g < 30
    eng.serbest.set()
    assert bekle(lambda: app.kosu.durum == "karar-bekliyor") and api("GET", "/api/durum")[1]["kosu"]["gecen_sn"] >= g  # karar beklerken de sayar
    api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": True})
    assert bekle(lambda: app.kosu.durum == "bitti") and api("GET", "/api/durum")[1]["kosu"]["gecen_sn"] is None


def test_arayuz_sure_gostergesi_tek_eleman_ve_saniyede_bir_guncellenir():
    assert 'id="gecenSure"' in HTML and "function sureYaz(sn)" in HTML
    assert "setInterval(()=>{if(S.kosuAktif)durumMetniGuncelle()},1000)" in HTML
    assert "S.kosuT0=d.kosu&&d.kosu.gecen_sn!=null?Date.now()-d.kosu.gecen_sn*1000:null" in HTML  # yeniden yuklemede sunucu suresi esas alinir


def test_gemini_ve_mistral_ipuclari_guncel():
    kaynak = (Path(hesaplar.__file__)).read_text(encoding="utf-8")
    assert "Haziran 2026" in kaynak and "console.mistral.ai" in kaynak and "Experiment" in kaynak
    mk = Path(motorlar.__file__).read_text(encoding="utf-8")
    assert "pip install uv" in mk and "GEMINI_API_KEY" in mk
