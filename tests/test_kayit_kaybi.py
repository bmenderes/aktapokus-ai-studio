"""Gercek hata (2026-10-28): kosu surerken proje 'Git'e aktarildi'; golge depodaki 'once' goruntusu okunamadi ('bad object'), kosunun kaydi HIC yazilmadi,
konusma ve verilen ad listeden dustu. Duzeltmeler: eski golge goruntuler gorunur kalir, kayit HER ZAMAN yazilir, eksik kayit olay gunlugunden onarilir,
kosu surerken 'Git'e aktar' reddedilir."""

import copy
import json
import types
from pathlib import Path

import pytest

from aktapokus_ai_studio import pipeline, snapshot
from aktapokus_ai_studio.arayuz import Uygulama, UygulamaHatasi
from aktapokus_ai_studio.config import VARSAYILAN_AYAR, ayar_coz
from conftest import SahteCalistirici, sonuc


def golge_proje(tmp_path) -> Path:
    k = tmp_path / "golge-proje"
    k.mkdir()
    (k / "a.txt").write_text("bir\n", encoding="utf-8")
    snapshot.golge_baslat(k)
    assert snapshot.golge_mi(k)
    return k


def test_proje_kosu_surerken_git_olursa_golge_goruntuleri_okunur_kalir(tmp_path):
    k = golge_proje(tmp_path)
    once = snapshot.anlik_goruntu(k, "x oncesi")  # golge depoda
    (k / "a.txt").write_text("iki\n", encoding="utf-8")
    (k / "yeni.txt").write_text("yeni\n", encoding="utf-8")
    snapshot.repo_baslat(k)  # 'Git'e aktar': artik gercek .git var, golge_mi False
    assert not snapshot.golge_mi(k) and (k / ".git").exists()
    sonra = snapshot.anlik_goruntu(k, "x sonrasi")  # gercek depoda
    assert snapshot.commit_var_mi(k, once) and snapshot.commit_var_mi(k, sonra)  # eski goruntu hala gorunur
    assert snapshot.degisenler(k, once, sonra)["yeni.txt"] == "A" and "a.txt" in snapshot.degisenler(k, once, sonra)  # eskiden 'bad object' ile dusuyordu
    assert "a.txt" in snapshot.fark_ozeti(k, once, sonra) and "iki" in snapshot.fark_yamasi(k, once, sonra, "a.txt")
    assert snapshot.geri_yukle(k, once, sonra) >= 2 and (k / "a.txt").read_text(encoding="utf-8") == "bir\n" and not (k / "yeni.txt").exists()  # geri alma da calisir


def test_etiketten_commit_gercek_ve_golge_depoda_bulur(tmp_path):
    k = golge_proje(tmp_path)
    eski = snapshot.anlik_goruntu(k, "aktapokus K1 sonrasi")
    snapshot.repo_baslat(k)
    yeni = snapshot.anlik_goruntu(k, "aktapokus K2 sonrasi")
    assert snapshot.etiketten_commit(k, "aktapokus K2 sonrasi") == yeni and snapshot.etiketten_commit(k, "aktapokus K1 sonrasi") == eski
    assert snapshot.etiketten_commit(k, "aktapokus yok sonrasi") is None


def test_fark_hesaplanamazsa_kayit_yine_yazilir_konusma_dusmez(proje, monkeypatch):
    def patlar(klasor, once, sonra):
        raise snapshot.GitHatasi("git diff --name-status: fatal: bad object eb9454c")

    monkeypatch.setattr(snapshot, "degisenler", patlar)
    sahte = SahteCalistirici({"kodcu": lambda k, i, n: sonuc("yanit metni"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    olaylar, bildirimler = [], []
    s = pipeline.calistir_hat(proje, "uzun is", ayar_coz(copy.deepcopy(VARSAYILAN_AYAR)), lambda ad: sahte, lambda q: True, bildir=bildirimler.append, olay=olaylar.append)
    assert s.kayit_yolu and Path(s.kayit_yolu).exists()  # KAYIT YAZILDI
    k = json.loads(Path(s.kayit_yolu).read_text(encoding="utf-8"))
    assert k["durum"] == "hata" and "farki hesaplanamadi" in k["mesaj"] and "bad object" in k["mesaj"] and k["adimlar"][0]["metin"] == "yanit metni" and k["degisen"] == {}
    assert olaylar[-1]["tur"] == "bitti" and any("UYARI" in b for b in bildirimler)


def olay_gunlugu(kimlik, once, durum="hata", mesaj="git diff --name-status -z: fatal: bad object eb9454c"):
    return [
        {"tur": "plan", "kosu": "k1", "gorev": "ekran goruntusu isi", "adimlar": [{"rol": "kodcu", "calistirici": "opencode-sunucu", "model": "m"}], "butce": 1000, "azami_duzeltme": 2, "testsiz": True, "otomatik": True},
        {"tur": "basladi", "kimlik": kimlik, "once": once, "butce": 1000, "kosu": "k1"},
        {"tur": "adim-basladi", "sira": 1, "rol": "kodcu", "calistirici": "opencode-sunucu", "model": "m", "kosu": "k1"},
        {"tur": "canli", "alt": "arac", "ad": None, "girdi": {"command": "x"}},
        {"tur": "adim-bitti", "sira": 1, "rol": "kodcu", "ok": True, "hata": None, "token_girdi": 10, "token_cikti": 5, "token_toplam": 15, "sure_sn": 120.0, "metin": "yapilanlarin ozeti", "kosu": "k1"},
        {"tur": "bitti", "durum": durum, "mesaj": mesaj, "kosu": "k1"},
    ]


def test_eksik_kayit_olay_gunlugunden_yeniden_kurulur_degisiklikler_hesaplanir(tmp_path):
    k = golge_proje(tmp_path)
    kimlik = "20261028-101328-790-c84a"
    once = snapshot.anlik_goruntu(k, f"aktapokus {kimlik} oncesi")
    (k / "a.txt").write_text("degisti\n", encoding="utf-8")
    snapshot.repo_baslat(k)  # kosu surerken git'e gecildi
    snapshot.anlik_goruntu(k, f"aktapokus {kimlik} sonrasi")
    olay_klasoru = k / ".aktapokus" / "kayit" / "olaylar"
    olay_klasoru.mkdir(parents=True)
    (olay_klasoru / f"{kimlik}.json").write_text(json.dumps(olay_gunlugu(kimlik, once)), encoding="utf-8")
    (olay_klasoru / "bozuk.json").write_text("{bozuk", encoding="utf-8")
    assert pipeline.eksik_kayitlari_onar(k) == [kimlik]
    kayit = json.loads((k / ".aktapokus" / "kayit" / f"{kimlik}.json").read_text(encoding="utf-8"))
    assert kayit["id"] == kimlik and kayit["gorev"] == "ekran goruntusu isi" and kayit["onarildi"] is True and kayit["akis"] == ["kodcu"]
    assert kayit["degisen"] == {"a.txt": "M"} and kayit["durum"] == "onaylandi" and kayit["korundu"] is True  # fark simdi hesaplanabildi: dosyalar calisma klasorunde duruyor
    assert kayit["adimlar"][0]["metin"] == "yapilanlarin ozeti" and kayit["adimlar"][0]["token_girdi"] == 10 and kayit["token_toplam"] == 15 and kayit["zaman"] == "2026-10-28 10:15:28"  # baslangic + 120 sn
    assert "yeniden olusturuldu" in kayit["mesaj"] and "bad object" not in kayit["mesaj"]
    assert pipeline.eksik_kayitlari_onar(k) == []  # idempotent: var olan kayda dokunmaz
    mevcut = (k / ".aktapokus" / "kayit" / f"{kimlik}.json").read_text(encoding="utf-8")
    assert pipeline.eksik_kayitlari_onar(k) == [] and (k / ".aktapokus" / "kayit" / f"{kimlik}.json").read_text(encoding="utf-8") == mevcut


def test_bitis_olayi_olmayan_kosu_hata_olarak_onarilir_gecersiz_gunluk_atlanir(tmp_path):
    k = tmp_path / "p"
    (k / ".aktapokus" / "kayit" / "olaylar").mkdir(parents=True)
    olaylar = olay_gunlugu("20261028-090000-001-aaaa", "a" * 40)[:-1]  # bitti olayi yok (uygulama kapanmis)
    (k / ".aktapokus" / "kayit" / "olaylar" / "20261028-090000-001-aaaa.json").write_text(json.dumps(olaylar), encoding="utf-8")
    (k / ".aktapokus" / "kayit" / "olaylar" / "20261028-090100-002-bbbb.json").write_text(json.dumps([{"tur": "canli"}]), encoding="utf-8")  # plan/basladi yok: kayit kurulamaz
    (k / ".aktapokus" / "kayit" / "olaylar" / "kotu ad.json").write_text("[]", encoding="utf-8")
    assert pipeline.eksik_kayitlari_onar(k) == ["20261028-090000-001-aaaa"]
    kayit = json.loads((k / ".aktapokus" / "kayit" / "20261028-090000-001-aaaa.json").read_text(encoding="utf-8"))
    assert kayit["durum"] == "hata" and "bitis kaydi yok" in kayit["mesaj"] and kayit["degisen"] == {}


def test_konusma_listesi_eksik_kaydi_kendiliginden_onarir(tmp_path):
    k = tmp_path / "p"
    (k / ".aktapokus" / "kayit" / "olaylar").mkdir(parents=True)
    (k / ".aktapokus" / "kayit" / "olaylar" / "20261028-090000-001-aaaa.json").write_text(json.dumps(olay_gunlugu("20261028-090000-001-aaaa", "a" * 40)), encoding="utf-8")
    liste = Uygulama._gecmis_oku(k, 50)
    assert [g["id"] for g in liste] == ["20261028-090000-001-aaaa"] and liste[0]["gorev"] == "ekran goruntusu isi"  # kenar cubugunda gorunur (ve verilen ad bu kimlige bagli kalir)


def test_gorev_surerken_git_e_aktarma_reddedilir_sonra_calisir(tmp_path):
    k = golge_proje(tmp_path)
    app = Uygulama()
    app.klasor_sec(str(k))
    oturum = app._oturum()
    oturum.kosu = types.SimpleNamespace(durum="calisiyor")
    with pytest.raises(UygulamaHatasi, match="Gorev surerken Git'e aktarilamaz") as hata:
        app.proje_ac(str(k), git_baslat=True)
    assert hata.value.kod == 409 and not (k / ".git").exists()  # depo turu degismedi
    oturum.kosu = None
    app.proje_ac(str(k), git_baslat=True)
    assert (k / ".git").exists()
