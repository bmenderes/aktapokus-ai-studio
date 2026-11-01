"""Yapay zekasiz veri akisi motoru: dogrulama, mesaj tasima, dallanma, hata yalitimi, sinirlar."""

import threading
from pathlib import Path

import pytest

from aktapokus_ai_studio import akis_motoru as am
from aktapokus_ai_studio.akis_motoru import AkisMotoruHatasi, Baglam, DugumTuru, calistir, dogrula


def _esik_akisi():
    return {
        "dugumler": [
            {"id": "b", "tur": "baslat"},
            {"id": "e", "tur": "esik", "ayar": {"alan": "sicaklik", "islec": ">", "deger": 80}},
            {"id": "alarm", "tur": "gunluk", "ayar": {"etiket": "alarm"}},
            {"id": "normal", "tur": "gunluk", "ayar": {"etiket": "normal"}},
        ],
        "oklar": [
            {"kaynak": "b", "hedef": "e"},
            {"kaynak": "e", "cikis": "evet", "hedef": "alarm"},
            {"kaynak": "e", "cikis": "hayir", "hedef": "normal"},
        ],
    }


@pytest.mark.parametrize("sicaklik,etiket", [(90, "alarm"), (80, "normal"), (20.5, "normal")])
def test_esik_dogru_dali_secer_ve_mesaj_tasinir(sicaklik, etiket):
    s = calistir(_esik_akisi(), {"sicaklik": sicaklik})
    assert s["durum"] == "bitti" and [g["etiket"] for g in s["gunluk"]] == [etiket] and s["gunluk"][0]["mesaj"]["sicaklik"] == sicaklik


@pytest.mark.parametrize("mesaj", [{}, {"sicaklik": "bozuk"}, {"sicaklik": True}])
def test_okunamayan_deger_sessizce_hayir_sayilmaz(mesaj):
    s = calistir(_esik_akisi(), mesaj)
    assert s["durum"] == "hata" and s["hatalar"][0]["dugum"] == "e" and s["gunluk"] == []


def test_dallar_birbirinin_mesajini_degistiremez():
    akis = {
        "dugumler": [{"id": "b", "tur": "baslat"}, {"id": "a1", "tur": "ata", "ayar": {"alan": "x", "deger": 1}}, {"id": "a2", "tur": "gunluk"}, {"id": "a3", "tur": "gunluk"}],
        "oklar": [{"kaynak": "b", "hedef": "a1"}, {"kaynak": "b", "hedef": "a2"}, {"kaynak": "a1", "hedef": "a3"}],
    }
    gunluk = calistir(akis, {"x": 0})["gunluk"]
    assert sorted(g["mesaj"]["x"] for g in gunluk) == [0, 1]


@pytest.mark.parametrize("bozuk,parca", [
    ("x", "dugumler"),
    ({"dugumler": []}, "dugum icermeli"),
    ({"dugumler": [{"id": "g", "tur": "gunluk"}]}, "baslangic"),
    ({"dugumler": [{"id": "b", "tur": "yok"}]}, "Bilinmeyen"),
    ({"dugumler": [{"id": "../x", "tur": "baslat"}]}, "kimligi"),
    ({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "b", "tur": "baslat"}]}, "tekrarli"),
    ({"dugumler": [{"id": "b", "tur": "baslat"}], "oklar": [{"kaynak": "b", "hedef": "z"}]}, "bilinen"),
    ({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "c", "tur": "baslat"}], "oklar": [{"kaynak": "b", "hedef": "c"}]}, "hedef olamaz"),
    ({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "g", "tur": "gunluk"}], "oklar": [{"kaynak": "b", "cikis": "yok", "hedef": "g"}]}, "cikisi yok"),
    ({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "e", "tur": "esik", "ayar": {"islec": "rm", "deger": 1}}]}, "isleci"),
    ({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "e", "tur": "esik", "ayar": {"islec": ">", "deger": "1"}}]}, "sayi"),
])
def test_bozuk_akis_reddedilir(bozuk, parca):
    with pytest.raises(AkisMotoruHatasi, match=parca):
        dogrula(bozuk)


def test_dongu_reddedilir():
    with pytest.raises(AkisMotoruHatasi, match="dongu"):
        dogrula({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "a", "tur": "gunluk"}, {"id": "c", "tur": "gunluk"}],
                 "oklar": [{"kaynak": "b", "hedef": "a"}, {"kaynak": "a", "hedef": "c"}, {"kaynak": "c", "hedef": "a"}]})


def test_iptal_ve_adim_siniri(monkeypatch):
    iptal = threading.Event()
    iptal.set()
    assert calistir(_esik_akisi(), {"sicaklik": 1}, Baglam(iptal=iptal))["durum"] == "iptal"
    monkeypatch.setattr(am, "AZAMI_ADIM", 1)
    assert calistir(_esik_akisi(), {"sicaklik": 1})["durum"] == "sinir"


def test_dugum_hatasi_diger_dali_durdurmaz(monkeypatch):
    monkeypatch.setitem(am.TURLER, "patlar", DugumTuru("patlar", ("cikis",), lambda a, m, b: 1 / 0))
    s = calistir({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "p", "tur": "patlar"}, {"id": "g", "tur": "gunluk"}],
                  "oklar": [{"kaynak": "b", "hedef": "p"}, {"kaynak": "b", "hedef": "g"}]})
    assert s["durum"] == "hata" and len(s["gunluk"]) == 1 and "ZeroDivisionError" in s["hatalar"][0]["hata"]


def test_kayit_defterine_yeni_tur_eklenebilir_ve_tekrar_edemez(monkeypatch):
    monkeypatch.setattr(am, "TURLER", dict(am.TURLER))
    am.kaydet(DugumTuru("iki_kat", ("cikis",), lambda a, m, b: [("cikis", {**m, "deger": m["deger"] * 2})]))
    with pytest.raises(ValueError):
        am.kaydet(DugumTuru("iki_kat", ("cikis",), lambda a, m, b: []))
    s = calistir({"dugumler": [{"id": "b", "tur": "baslat"}, {"id": "k", "tur": "iki_kat"}, {"id": "g", "tur": "gunluk"}],
                  "oklar": [{"kaynak": "b", "hedef": "k"}, {"kaynak": "k", "hedef": "g"}]}, {"deger": 21})
    assert s["gunluk"][0]["mesaj"]["deger"] == 42


def test_plc_yazan_dugum_ve_model_bagimliligi_yok():
    assert not [t for t in am.TURLER if "yaz" in t or "write" in t]
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "akis_motoru.py").read_text(encoding="utf-8")
    for yasak in ("import opcua", "from .runners", "from .pipeline", "subprocess", "eval(", "exec("):
        assert yasak not in kaynak
