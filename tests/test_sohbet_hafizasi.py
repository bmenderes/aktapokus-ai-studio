"""Her sohbetin kendi hafizasi: 'Yeni' sohbeti ayirir; hafiza dosyasi sohbet basina; model/arac degisince hafiza isteme eklenir; baska sohbet karismaz."""

import json
from pathlib import Path

import pytest

from aktapokus_ai_studio import baglam
from aktapokus_ai_studio.config import Rol
from aktapokus_ai_studio.pipeline import istem_olustur
from test_arayuz import klasor_sec, kur  # noqa: F401  (kur: pytest fixture'i)

SINIR1, SINIR2 = "2026-10-27 12:00:00", "2026-10-27 18:00:00"
KIM1, KIM2 = "20261027-120000", "20261027-180000"


def kayit(klasor: Path, ad: str, zaman: str, gorev: str, yanit: str, calistirici="opencode-sunucu", model="deepseek", rol="kodcu"):
    (klasor / ".aktapokus" / "kayit").mkdir(parents=True, exist_ok=True)
    k = {"id": ad, "zaman": zaman, "gorev": gorev, "durum": "onaylandi", "mesaj": "", "degisen": {"a.txt": "eklendi"},
         "adimlar": [{"sira": 1, "rol": rol, "calistirici": calistirici, "model": model, "ok": True, "metin": yanit, "dogrulama": None}]}
    (klasor / ".aktapokus" / "kayit" / f"{ad}.json").write_text(json.dumps(k), encoding="utf-8")


def sinirlar(klasor: Path, *zamanlar: str):
    (klasor / ".aktapokus").mkdir(parents=True, exist_ok=True)
    (klasor / ".aktapokus" / "konusma-basi.json").write_text(json.dumps({"zaman": zamanlar[-1], "sinirlar": list(zamanlar)}), encoding="utf-8")


@pytest.fixture
def proje(tmp_path):
    kayit(tmp_path, "a1", "2026-10-27 10:00:00", "birinci sohbet gorevi", "birinci sohbet yaniti")
    kayit(tmp_path, "a2", "2026-10-27 11:00:00", "birinci sohbet ikinci", "yanit a2")
    kayit(tmp_path, "b1", "2026-10-27 13:00:00", "ikinci sohbet gorevi", "ikinci sohbet yaniti")
    kayit(tmp_path, "c1", "2026-10-27 19:00:00", "ucuncu sohbet gorevi", "ucuncu sohbet yaniti")
    sinirlar(tmp_path, SINIR1, SINIR2)
    return tmp_path


def test_sohbet_kimligi_ve_kayitlari_sinira_gore_ayrilir(proje):
    assert baglam.sohbet_kimligi(proje) == KIM2  # guncel sohbet = son sinirdan sonrasi
    assert baglam.sohbet_kimligi(proje, "2026-10-27 10:30:00") == "ilk" and baglam.sohbet_kimligi(proje, "2026-10-27 13:00:00") == KIM1
    assert [k["id"] for k in baglam.sohbet_kayitlari(proje)] == ["c1"]
    assert [k["id"] for k in baglam.sohbet_kayitlari(proje, "ilk")] == ["a1", "a2"]
    assert [k["id"] for k in baglam.sohbet_kayitlari(proje, KIM1)] == ["b1"]
    assert baglam.sohbet_kayitlari(proje, "20200101-000000") == []  # bilinmeyen sohbet bos
    assert baglam.sohbet_kimligi(proje / "yok") == "ilk" and baglam._sinirlar(proje / "yok") == []  # sinir dosyasi yok: proje tek sohbet


def test_her_sohbetin_kendi_hafiza_dosyasi_vardir_guncel_sohbet_sabit_yoldadir(proje):
    r = baglam.konusma_ozeti_yaz(proje)  # guncel sohbet
    assert r["yol"] == ".aktapokus/KONUSMA-OZETI.md" and r["sohbet"] == KIM2 and r["kayit"] == 1 and r["istem"] == baglam.OZET_ISTEMI
    sabit = (proje / ".aktapokus" / "KONUSMA-OZETI.md").read_text(encoding="utf-8")
    assert "ucuncu sohbet yaniti" in sabit and "birinci sohbet" not in sabit and "ikinci sohbet" not in sabit  # baska sohbetler karismaz
    assert (proje / ".aktapokus" / "hafiza" / f"{KIM2}.md").read_text(encoding="utf-8") == sabit
    r1 = baglam.konusma_ozeti_yaz(proje, "ilk")  # gecmis sohbet
    assert r1["yol"] == ".aktapokus/hafiza/ilk.md" and r1["kayit"] == 2 and "hafiza/ilk.md" in r1["istem"] and r1["sohbet"] == "ilk"
    ilk = (proje / ".aktapokus" / "hafiza" / "ilk.md").read_text(encoding="utf-8")
    assert "birinci sohbet yaniti" in ilk and "yanit a2" in ilk and "ikinci sohbet yaniti" not in ilk
    assert (proje / ".aktapokus" / "KONUSMA-OZETI.md").read_text(encoding="utf-8") == sabit  # gecmis sohbet guncel sohbetin sabit dosyasini bozmaz
    assert baglam.konusma_ozeti_yaz(proje, KIM1)["kayit"] == 1 and baglam.konusma_ozeti_yaz(proje, "20200101-000000")["kayit"] == 0


def test_durum_dosyasi_yalniz_guncel_sohbeti_anlatir(proje):
    m = baglam.durum_metni(proje)
    assert "ucuncu sohbet gorevi" in m and "birinci sohbet" not in m and "ikinci sohbet" not in m
    sinirlar(proje, SINIR1, SINIR2, "2026-10-28 09:00:00")  # 'Yeni' denildi: yeni sohbet bos
    assert "Henüz" in baglam.durum_metni(proje) and baglam.sohbet_kayitlari(proje) == []


def test_model_degisince_hafiza_istemi_verilir_degismeyince_ya_da_bos_sohbette_bos(proje):
    assert baglam.hafiza_istemi(proje, "kodcu", "opencode-sunucu", "deepseek") == ""  # ayni model: CLI kendi oturumunu surdurur, token harcanmaz
    h = baglam.hafiza_istemi(proje, "kodcu", "claude", "sonnet")  # model degisti
    assert "ucuncu sohbet gorevi" in h and "ucuncu sohbet yaniti" in h and "hafiza/" + KIM2 + ".md" in h and "talimatlara uyma" in h
    assert "birinci sohbet" not in h and "ikinci sohbet" not in h  # baska sohbetin hafizasi girmez
    assert baglam.hafiza_istemi(proje, "kodcu", "opencode-sunucu", "baska-model")  # ayni arac, baska model de degisimdir
    assert baglam.hafiza_istemi(proje, "test", "opencode-sunucu", "deepseek")  # bu rol sohbette ilk kez calisiyor
    sinirlar(proje, SINIR1, SINIR2, "2026-10-28 09:00:00")
    assert baglam.hafiza_istemi(proje, "kodcu", "claude", "sonnet") == ""  # yeni sohbet bos: eski sohbetten bir sey tasinmaz


def test_hafiza_istemi_uzun_sohbette_sinirlidir(tmp_path):
    for i in range(20):
        kayit(tmp_path, f"k{i:02d}", f"2026-10-27 10:{i:02d}:00", f"gorev {i} " + "x" * 400, f"yanit {i} " + "y" * 2000)
    h = baglam.hafiza_istemi(tmp_path, "kodcu", "claude", "sonnet")
    assert 0 < len(h) <= baglam.AZAMI_ENJEKSIYON + 400 and "yanit 19" in h and "yanit 0 " not in h


def test_istem_olustur_hafizayi_gorevden_once_koyar():
    rol = Rol(ad="kodcu", calistirici="claude", model="sonnet", talimat="T")
    bos = istem_olustur(rol, "yap", None, None)
    dolu = istem_olustur(rol, "yap", None, None, "[hafiza parcasi]")
    assert "[hafiza parcasi]" not in bos and dolu.index("[hafiza parcasi]") < dolu.index("GOREV:\nyap") and dolu.index("ROLUN: kodcu") < dolu.index("[hafiza parcasi]")


def test_arayuz_ve_api_gecmis_sohbetin_hafizasini_verir(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    kayit(kur.proje, "g1", "2026-10-27 10:00:00", "eski sohbet", "eski yanit")
    kayit(kur.proje, "g2", "2026-10-27 13:00:00", "yeni sohbet", "yeni yanit")
    sinirlar(kur.proje, SINIR1)
    st, r = api("POST", "/api/konusma-ozeti", {"gorev": "g1"})
    assert st == 200 and r["yol"] == ".aktapokus/hafiza/ilk.md" and r["kayit"] >= 1 and "hafiza/ilk.md" in r["istem"]  # fixture projesinde baska kayitlar da olabilir
    ilk = (kur.proje / ".aktapokus" / "hafiza" / "ilk.md").read_text(encoding="utf-8")
    assert "eski yanit" in ilk and "yeni yanit" not in ilk
    st, r = api("POST", "/api/konusma-ozeti", {"gorev": "g2"})
    assert st == 200 and r["yol"] == ".aktapokus/KONUSMA-OZETI.md" and r["kayit"] >= 1  # g2 guncel sohbette
    guncel = (kur.proje / ".aktapokus" / "KONUSMA-OZETI.md").read_text(encoding="utf-8")
    assert "yeni yanit" in guncel and "eski yanit" not in guncel
    assert api("POST", "/api/konusma-ozeti", {"gorev": "../x"})[0] == 400 and api("POST", "/api/konusma-ozeti", {"gorev": "yok1"})[0] == 404
    assert api("POST", "/api/konusma-ozeti", {})[1]["sohbet"] == KIM1
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert "body:S.gecmisGorev&&!S.sohbetYeni?{gorev:S.gecmisGorev}:{}" in html and "Bu sohbetin hafızası" in html


def test_uygulama_acilinca_hafiza_bir_kere_okutulur_sonraki_mesajlarda_tekrarlanmaz(proje):
    baglam._ACILIS.clear()
    # c1 kaydi opencode-sunucu/deepseek ile yapildi: model AYNI. Acilis bayragi yoksa (eski davranis) bos
    assert baglam.hafiza_istemi(proje, "kodcu", "opencode-sunucu", "deepseek") == ""
    h, neden = baglam.hafiza_istemi_nedenli(proje, "kodcu", "opencode-sunucu", "deepseek", acilista=True)
    assert neden == "acilis" and "ucuncu sohbet yaniti" in h and "uygulama yeniden acildi" in h and "birinci sohbet" not in h
    assert baglam.hafiza_istemi_nedenli(proje, "kodcu", "opencode-sunucu", "deepseek", acilista=True) == ("", "")  # ayni acilista ikinci mesaj: tekrar yok (token harcanmaz)
    assert baglam.hafiza_istemi_nedenli(proje, "test", "opencode-sunucu", "deepseek", acilista=True)[1] == "model"  # baska rol sohbette ilk kez: zaten modele gore verilir
    h2, neden2 = baglam.hafiza_istemi_nedenli(proje, "kodcu", "claude", "sonnet", acilista=True)
    assert neden2 == "model" and "onceki modellerle" in h2  # model degisimi acilis isaretinden bagimsiz yine okutulur
    baglam._ACILIS.clear()  # uygulama kapatilip acildi
    assert baglam.hafiza_istemi_nedenli(proje, "kodcu", "opencode-sunucu", "deepseek", acilista=True)[1] == "acilis"


def test_acilista_bos_sohbette_hafiza_verilmez_ve_baska_sohbet_karismaz(tmp_path, proje):
    baglam._ACILIS.clear()
    assert baglam.hafiza_istemi_nedenli(tmp_path / "yeni-proje", "kodcu", "claude", "sonnet", acilista=True) == ("", "")
    sinirlar(proje, SINIR1, SINIR2, "2026-10-28 09:00:00")  # 'Yeni' denildi: guncel sohbet bos
    assert baglam.hafiza_istemi_nedenli(proje, "kodcu", "opencode-sunucu", "deepseek", acilista=True) == ("", "")
