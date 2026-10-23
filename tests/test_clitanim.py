import json
import sys
from pathlib import Path

import pytest

from aktapokus_ajan import clitanim, runners
from aktapokus_ajan.clitanim import CliTanim, TanimHatasi, TanimliCalistirici, tanim_coz
from aktapokus_ajan.config import AyarHatasi, ayar_coz
from aktapokus_ajan.runners import CalistiriciHatasi

SAHTE = str(Path(__file__).with_name("sahte_cli.py"))


@pytest.fixture(autouse=True)
def kayit_yalitimi(tmp_path, monkeypatch):
    """Gercek ~/.aktapokus/clilar.json'a asla dokunma."""
    monkeypatch.setenv(clitanim.KAYIT_ORTAMI, str(tmp_path / "clilar.json"))


def tanim(**ek) -> dict:
    d = {"ad": "sahte", "komut": [sys.executable, SAHTE, "--stdin"], "istem": "stdin"}
    d.update(ek)
    return d


def test_gecerli_tanim_cozulur_varsayilanlarla():
    t = tanim_coz(tanim())
    assert t.ad == "sahte" and t.istem == "stdin" and t.cikti == "metin" and t.gorunen_ad == "sahte" and t.model_bayragi is None


@pytest.mark.parametrize(
    "bozuk, mesaj",
    [
        ({"ad": "Buyuk Harf"}, "'ad'"),
        ({"ad": "opencode"}, "ayrilmis"),
        ({"ad": "opencode-benim"}, "ayrilmis"),  # opencode ile baslayan ad koruyucu kapsami gibi gorunurdu
        ({"ad": "claude"}, "ayrilmis"),
        ({"komut": []}, "komut"),
        ({"komut": ["goreli.exe"]}, "MUTLAK"),
        ({"komut": ["C:\\yok\\program.exe"]}, "bulunamadi"),
        ({"istem": "baska"}, "'istem'"),
        ({"istem": "arguman"}, "{istem}"),
        ({"komut": [sys.executable, SAHTE, "{istem}"]}, "stdin"),
        ({"cikti": "xml"}, "'cikti'"),
        ({"cikti": "json"}, "metin_yolu"),
        ({"onayli_args": "tek-metin"}, "liste"),
    ],
)
def test_gecersiz_tanimlar_reddedilir(bozuk, mesaj):
    with pytest.raises(TanimHatasi, match=mesaj):
        tanim_coz(tanim(**bozuk))


@pytest.mark.parametrize("uzanti", [".cmd", ".bat", ".ps1"])
def test_sarmalayici_dosyalari_reddedilir(tmp_path, uzanti):
    sarmalayici = tmp_path / f"cli{uzanti}"
    sarmalayici.write_text("@echo off")
    with pytest.raises(TanimHatasi, match="sarmalayici"):
        tanim_coz(tanim(komut=[str(sarmalayici)]))


def test_kayit_defteri_kaydet_yukle_sil_ve_bozuk_olanlari_atlar(tmp_path):
    assert clitanim.yukle() == {}
    clitanim.kaydet(tanim_coz(tanim(ad="a1", modeller=["m1"])))
    clitanim.kaydet(tanim_coz(tanim(ad="b2")))
    assert set(clitanim.yukle()) == {"a1", "b2"} and clitanim.yukle()["a1"].modeller == ("m1",)
    assert clitanim.bilinen_adlar() == ["opencode", "opencode-sunucu", "claude", "codex", "a1", "b2"]
    # bir tanimin programi silinirse yalniz o atlanir
    ham = json.loads(clitanim.kayit_yolu().read_text(encoding="utf-8"))
    ham["clilar"][0]["komut"][0] = str(tmp_path / "silindi.exe")
    clitanim.kayit_yolu().write_text(json.dumps(ham), encoding="utf-8")
    assert set(clitanim.yukle()) == {"b2"}
    assert clitanim.sil("b2") and not clitanim.sil("yok")
    clitanim.kayit_yolu().write_text("{bozuk", encoding="utf-8")
    assert clitanim.yukle() == {}


def test_rol_ayari_eklenen_cli_adini_kabul_eder_digerini_reddeder():
    veri = {"akis": ["k"], "azami_duzeltme": 1, "butce_token": 1000, "zaman_asimi_sn": 60,
            "roller": {"k": {"calistirici": "sahte", "model": None, "talimat": "x"}}}
    with pytest.raises(AyarHatasi, match="bilinmeyen calistirici 'sahte'"):
        ayar_coz(veri)
    clitanim.kaydet(tanim_coz(tanim()))
    assert ayar_coz(veri).roller["k"].calistirici == "sahte"


def test_calistirici_olustur_eklenen_cli_icin_genel_calistirici_verir():
    with pytest.raises(CalistiriciHatasi, match="Bilinmeyen"):
        runners.calistirici_olustur("sahte")
    clitanim.kaydet(tanim_coz(tanim()))
    assert isinstance(runners.calistirici_olustur("sahte"), TanimliCalistirici)
    assert isinstance(runners.calistirici_olustur("claude"), runners.ClaudeCodeCalistirici)  # yerlesikler etkilenmez


def test_stdin_kipi_istemi_aynen_ve_pwd_ile_verir(tmp_path, monkeypatch):
    kayit = tmp_path / "kayit.json"
    monkeypatch.setenv("SAHTE_CLI_KAYIT", str(kayit))
    istem = 'tirnak " & | $(x) satir\nsonu ç ğ ş ' + "x" * 30000
    r = TanimliCalistirici(tanim_coz(tanim())).calistir(istem, tmp_path)
    assert r.ok and r.metin.startswith("yanit: tirnak")
    k = json.loads(kayit.read_text(encoding="utf-8"))
    assert k["istem"] == istem and k["pwd"] == str(tmp_path) and Path(k["cwd"]) == tmp_path
    assert istem[:20] not in " ".join(k["args"])


def test_arguman_kipi_istem_tek_arguman_ve_tire_ile_baslayamaz(tmp_path, monkeypatch):
    kayit = tmp_path / "kayit.json"
    monkeypatch.setenv("SAHTE_CLI_KAYIT", str(kayit))
    t = tanim_coz(tanim(istem="arguman", komut=[sys.executable, SAHTE, "{istem}"]))
    c = TanimliCalistirici(t)
    istem = 'iki  kelime "tirnakli" & ozel'
    assert c.calistir(istem, tmp_path).ok
    assert json.loads(kayit.read_text(encoding="utf-8"))["args"][-1] == istem
    with pytest.raises(CalistiriciHatasi, match="'-' ile"):
        c.calistir("-x gizli secenek", tmp_path)


def test_model_ve_izin_argumanlari(tmp_path):
    t = tanim_coz(tanim(model_bayragi="--model", onayli_args=["--yaz"], salt_okunur_args=["--oku"]))
    c = TanimliCalistirici(t)
    assert c.komut("x", "m1", True)[-3:] == ["--yaz", "--model", "m1"]
    assert c.komut("x", None, False)[-1] == "--oku" and "--model" not in c.komut("x", None, False)
    with pytest.raises(CalistiriciHatasi, match="'-' ile"):
        c.komut("x", "--tehlikeli", True)
    with pytest.raises(CalistiriciHatasi, match="model secimini desteklemiyor"):
        TanimliCalistirici(tanim_coz(tanim())).komut("x", "m1", True)


def test_json_cikti_noktali_yollarla_cozulur(tmp_path):
    t = tanim_coz(tanim(cikti="json", metin_yolu="sonuc.metin", hata_yolu="bayrak.hata",
                        girdi_yolu="kullanim.gir", cikti_yolu="kullanim.cik", onbellek_yolu="kullanim.onb",
                        komut=[sys.executable, SAHTE, "--stdin", "--kip", "json"]))
    c = TanimliCalistirici(t)
    r = c.calistir("merhaba dunya bu bir istem", tmp_path)
    assert r.ok and r.metin == "yanit: merhaba dunya bu bir" and (r.token_girdi, r.token_cikti, r.token_onbellek) == (11, 5, 40)
    r = c.calistir("HATA olsun", tmp_path)
    assert not r.ok and r.hata.startswith("yanit: HATA")


def test_jsonl_cikti_son_dolu_degeri_alir_ve_json_olmayan_satiri_atlar(tmp_path):
    t = tanim_coz(tanim(cikti="jsonl", metin_yolu="ogeler.0.metin", girdi_yolu="kullanim.gir", cikti_yolu="kullanim.cik",
                        hata_yolu="hata", komut=[sys.executable, SAHTE, "--stdin", "--kip", "jsonl"]))
    r = TanimliCalistirici(t).calistir("selam", tmp_path)
    assert r.ok and r.metin == "yanit: selam" and (r.token_girdi, r.token_cikti) == (11, 5)
    assert not TanimliCalistirici(t).calistir("HATA", tmp_path).ok


def test_cikis_kodu_zaman_asimi_ve_baslatilamayan_program(tmp_path):
    c = TanimliCalistirici(tanim_coz(tanim()))
    r = c.calistir("FAIL", tmp_path)
    assert not r.ok and "cikis kodu 3" in r.hata and "patladi" in r.hata
    yavas = tmp_path / "yavas.py"
    yavas.write_text("import time; time.sleep(30)")
    r = TanimliCalistirici(tanim_coz(tanim(komut=[sys.executable, str(yavas)]))).calistir("x", tmp_path, zaman_asimi_sn=1)
    assert not r.ok and "Zaman asimi (1 sn)" in r.hata
    ham = tanim(komut=[str(tmp_path / "bozuk.exe")])
    (tmp_path / "bozuk.exe").write_text("bu bir program degil")
    r = TanimliCalistirici(tanim_coz(ham)).calistir("x", tmp_path)
    assert not r.ok and "baslatilamadi" in r.hata


def test_program_sonradan_silinirse_anlamli_hata(tmp_path):
    kopya = tmp_path / "gecici.exe"
    kopya.write_bytes(Path(sys.executable).read_bytes()[:10])
    c = TanimliCalistirici(tanim_coz(tanim(komut=[str(kopya)])))
    kopya.unlink()
    with pytest.raises(CalistiriciHatasi, match="program bulunamadi"):
        c.calistir("x", tmp_path)


def test_listele_yerlesik_ve_eklenen_cli_leri_kurulu_durumuyla_verir():
    clitanim.kaydet(tanim_coz(tanim(ad="benim", gorunen_ad="Benim CLI", modeller=["a", "b"])))
    liste = {c["ad"]: c for c in clitanim.listele()}
    assert {"opencode", "opencode-sunucu", "claude", "codex", "benim"} <= set(liste)
    assert liste["benim"]["yerlesik"] is False and liste["benim"]["kurulu"] is True and liste["benim"]["modeller"] == ["a", "b"]
    assert liste["claude"]["yerlesik"] is True and "tanim" not in liste["claude"]
