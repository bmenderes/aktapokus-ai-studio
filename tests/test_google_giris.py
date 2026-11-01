"""Google girisi (google_giris.py): PKCE, state dogrulamasi, anahtarlarin disari verilmemesi, kayit sifreleme (sahte DPAPI)."""

import json
import urllib.parse

import pytest

from aktapokus_ai_studio import google_giris as g

ISTEMCI = "1234567890-abcdefghijklmnop.apps.googleusercontent.com"


@pytest.fixture
def yonetici(tmp_path, monkeypatch):
    monkeypatch.setenv("AKTAPOKUS_GOOGLE_AYAR", str(tmp_path / "google.json"))
    monkeypatch.delenv("AKTAPOKUS_GOOGLE_ISTEMCI_ID", raising=False)
    monkeypatch.setattr(g, "_koru", lambda b: "KORUNDU:" + b[::-1].hex())  # DPAPI yerine: acik metin DEGIL
    monkeypatch.setattr(g, "_ac", lambda m: bytes.fromhex(m.split(":", 1)[1])[::-1])
    return g.Yonetici()


def test_pkce_rfc7636_ornegi():
    assert g.sinama_hesapla("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    d, s = g.pkce_olustur()
    assert len(d) >= 43 and s == g.sinama_hesapla(d) and "=" not in s


def test_istemci_kimligi_dogrulanir(yonetici):
    for kotu in (None, "", "abc", "x" * 30, 5):
        with pytest.raises(g.GoogleHatasi):
            yonetici.istemci_kaydet(kotu, None)
    yonetici.istemci_kaydet(ISTEMCI, "GOCSPX-gizli-sir")
    ham = g.ayar_yolu().read_text(encoding="utf-8")
    assert "gizli-sir" not in ham and "KORUNDU:" in ham  # sir acik metin yazilmaz
    assert yonetici.durum()["istemci_var"] is True


def test_baglan_istemcisiz_reddedilir_ve_bilinmeyen_baglayici(yonetici):
    with pytest.raises(g.GoogleHatasi):
        yonetici.baglan("gmail")
    yonetici.istemci_kaydet(ISTEMCI, None)
    with pytest.raises(g.GoogleHatasi):
        yonetici.baglan("yazma-izni")


def test_yetki_adresi_pkce_state_ve_yalniz_okuma_izni(yonetici):
    yonetici.istemci_kaydet(ISTEMCI, None)
    adres = yonetici.baglan("gmail")
    try:
        u = urllib.parse.urlsplit(adres)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        assert u.netloc == "accounts.google.com" and q["code_challenge_method"] == "S256" and q["response_type"] == "code"
        assert q["redirect_uri"].startswith("http://127.0.0.1:") and len(q["state"]) >= 40 and q["access_type"] == "offline"
        izinler = q["scope"].split()
        assert "https://www.googleapis.com/auth/gmail.readonly" in izinler
        assert all(i in ("openid", "email") or i.endswith(".readonly") for i in izinler)  # yazma/silme izni YOK
        assert yonetici.durum()["bekliyor"] is True
    finally:
        yonetici._akisi_kapat()


def test_yanlis_state_akisi_tuketmez_ve_dogru_state_tek_kullanimlik(yonetici, monkeypatch):
    yonetici.istemci_kaydet(ISTEMCI, None)
    adres = yonetici.baglan("hesap")
    q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(adres).query).items()}
    port = int(urllib.parse.urlsplit(q["redirect_uri"]).netloc.split(":")[1])
    host = f"127.0.0.1:{port}"
    gonderilen = {}

    def sahte(adres_, alanlar):
        gonderilen.update(alanlar)
        return {"refresh_token": "yenileme-123", "scope": "openid email https://www.googleapis.com/auth/gmail.readonly", "id_token": "a." + _yuk({"email": "ben@example.com"}) + ".c"}

    monkeypatch.setattr(g, "_form_gonder", sahte)
    assert yonetici.geri_donus(host, "/oauth2callback?code=x&state=yanlis", port)[0] == 400
    assert yonetici.durum()["bekliyor"] is True  # sahte istek gercek girisi bozmadi
    assert yonetici.geri_donus("evil.example:80", "/oauth2callback?code=x&state=" + q["state"], port)[0] == 400  # Host kontrolu
    kod, _ = yonetici.geri_donus(host, "/oauth2callback?code=KOD&state=" + q["state"], port)
    assert kod == 200 and gonderilen["code_verifier"] and gonderilen["grant_type"] == "authorization_code"
    assert yonetici.geri_donus(host, "/oauth2callback?code=KOD&state=" + q["state"], port)[0] == 410  # tek kullanimlik
    d = yonetici.durum()
    assert d["bagli"] and d["eposta"] == "ben@example.com" and d["baglayicilar"] == ["gmail"]
    assert "yenileme-123" not in json.dumps(d) and "yenileme-123" not in g.ayar_yolu().read_text(encoding="utf-8")  # anahtar ne durumda ne dosyada acik


def test_cikis_kaydi_siler_ve_iptal_ister(yonetici, monkeypatch):
    yonetici.istemci_kaydet(ISTEMCI, None)
    veri = json.loads(g.ayar_yolu().read_text(encoding="utf-8"))
    veri["hesap"] = {"eposta": "ben@example.com", "baglayicilar": ["drive"], "yenileme": g._koru(b"yenileme-9")}
    g.ayar_yolu().write_text(json.dumps(veri), encoding="utf-8")
    istekler = []
    monkeypatch.setattr(g, "_form_gonder", lambda a, alanlar: istekler.append((a, alanlar)) or {})
    yonetici.cikis()
    assert istekler == [(g.IPTAL_ADRESI, {"token": "yenileme-9"})]
    assert yonetici.durum()["bagli"] is False and "yenileme" not in g.ayar_yolu().read_text(encoding="utf-8")


def _yuk(veri: dict) -> str:
    import base64
    return base64.urlsafe_b64encode(json.dumps(veri).encode()).decode().rstrip("=")


def test_hepsi_tek_girista_uc_okuma_izni_ister(yonetici):
    yonetici.istemci_kaydet(ISTEMCI, None)
    adres = yonetici.baglan("hepsi")
    try:
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(adres).query).items()}
        izinler = set(q["scope"].split())
        assert set(g.BAGLAYICILAR.values()) <= izinler and all(i in ("openid", "email") or i.endswith(".readonly") for i in izinler)
    finally:
        yonetici._akisi_kapat()
