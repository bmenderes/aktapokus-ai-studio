"""Gorev calisirken yeni gorev verilebilir: sirayla kosulmak uzere kuyruga girer; basarisiz/durdurulan gorevden sonra kuyruk bosalir."""

from test_arayuz import Engelli, bekle, klasor_sec, kur  # noqa: F401  (pytest fixture'lari)


def _karara_getir(app, api, proje, gorev="yeni.txt ekle"):
    klasor_sec(api, proje)
    st, plan = api("POST", "/api/gorev", {"gorev": gorev})
    assert st == 200
    assert api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})[0] == 200
    assert bekle(lambda: app.kosu.durum == "karar-bekliyor")
    return plan


def test_calisirken_gorev_kuyruga_girer_ve_siradaki_baslar(kur):
    app, sv, api, _ = kur()
    plan = _karara_getir(app, api, kur.proje)
    assert api("POST", "/api/gorev", {"gorev": "ikinci"})[0] == 409  # kuyruga istenmedi: eskisi gibi reddedilir
    st, d = api("POST", "/api/gorev", {"gorev": "ikinci", "kuyruga": True})
    assert st == 200 and d == {"kuyruk": 1}
    assert api("GET", "/api/durum")[1]["kuyruk"] == ["ikinci"]
    assert [o for o in app.bus.gecmis if o["tur"] == "kuyruk"][-1]["gorevler"] == ["ikinci"]
    assert api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": True})[0] == 200
    assert bekle(lambda: app.kosu.gorev == "ikinci" and app.kosu.durum == "plan")  # siradaki gorev planiyla gelir (plan onayi acik)
    assert api("GET", "/api/durum")[1]["kuyruk"] == []


def test_durdurulan_gorevden_sonra_kuyruk_bosalir(kur):
    e = Engelli()
    app, sv, api, _ = kur(uret=lambda ad: e)
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "g"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert e.basladi.wait(5)
    assert api("POST", "/api/gorev", {"gorev": "sonraki", "kuyruga": True})[1] == {"kuyruk": 1}
    api("POST", f"/api/gorev/{plan['kosu']}/durdur", {})
    assert bekle(lambda: app.kosu.durum == "bitti")
    assert bekle(lambda: api("GET", "/api/durum")[1]["kuyruk"] == [])
    assert app.kosu.gorev == "g"  # durdurulan gorevin ardindan yenisi baslamadi


def test_kuyruktan_silme_ve_sinir(kur):
    e = Engelli()
    app, sv, api, _ = kur(uret=lambda ad: e)
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "g"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert e.basladi.wait(5)
    for i in range(10):
        assert api("POST", "/api/gorev", {"gorev": f"k{i}", "kuyruga": True})[0] == 200
    assert api("POST", "/api/gorev", {"gorev": "fazla", "kuyruga": True})[0] == 409  # kuyruk dolu
    assert api("POST", "/api/kuyruk/sil", {"sira": 0})[1] == {"kuyruk": 9}
    assert api("GET", "/api/durum")[1]["kuyruk"][0] == "k1"
    assert api("POST", "/api/kuyruk/sil", {"sira": 99})[0] == 404
    assert api("POST", "/api/kuyruk/sil", {"sira": "0"})[0] == 404
    e.serbest.set()
