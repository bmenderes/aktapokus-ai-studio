"""Ortak baglam: farkli LLM'ler ayni projede birbirinin yaptigini bilir (DURUM.md yanit parcasi) ve AGENTS.md'yi yok sayan Vibe'e istemle verilir."""

import json
from pathlib import Path

from aktapokus_ai_studio import baglam, runners
from test_arayuz import kur  # noqa: F401  (kur: pytest fixture'i)


def _kayit(klasor: Path, ad: str, gorev: str, metin: str, calistirici: str = "claude", dogrulama_metni: str | None = None) -> None:
    (klasor / ".aktapokus" / "kayit").mkdir(parents=True, exist_ok=True)
    adimlar = [{"sira": 1, "rol": "kodcu", "calistirici": calistirici, "model": "m", "ok": True, "metin": metin, "dogrulama": None}]
    if dogrulama_metni:
        adimlar.append({"sira": 2, "rol": "test", "calistirici": calistirici, "model": "m", "ok": True, "metin": dogrulama_metni, "dogrulama": "basarili"})
    k = {"id": ad, "zaman": "2026-10-27 10:00:00", "gorev": gorev, "durum": "onaylandi", "mesaj": "", "degisen": {}, "adimlar": adimlar}
    (klasor / ".aktapokus" / "kayit" / f"{ad}.json").write_text(json.dumps(k), encoding="utf-8")


def test_durum_onceki_calismanin_yanitindan_parca_icerir_dogrulama_adimini_almaz(tmp_path):
    _kayit(tmp_path, "a1", "NetView duzelt", "Tirnak koseyi 30 derece yaptim; ekran-2.png guncellendi. " + "x" * 400, "claude", dogrulama_metni="SONUC: BASARILI")
    metin = baglam.durum_metni(tmp_path)
    assert "Yanıt: Tirnak koseyi 30 derece yaptim" in metin and "SONUC: BASARILI" not in metin
    yanit = [s for s in metin.splitlines() if s.strip().startswith("Yanıt:")][0]
    assert len(yanit) <= baglam.AZAMI_YANIT + 20 and yanit.endswith("…")  # parca sinirli, kisaltildigi belli


def test_istem_baglami_durum_varsa_kurallar_ve_onceki_calismalari_verir_yoksa_bos(tmp_path):
    assert baglam.istem_baglami(tmp_path) == ""  # baglam hic yazilmamis (kapali)
    _kayit(tmp_path, "a1", "ilk gorev", "ilk yanit")
    (tmp_path / ".aktapokus" / baglam.DURUM_ADI).write_text(baglam.durum_metni(tmp_path), encoding="utf-8")
    b = baglam.istem_baglami(tmp_path)
    assert b.startswith("[Aktapokus ortak bağlam") and "ilk gorev" in b and "ilk yanit" in b and "Türkçe" in b and b.endswith("\n\n")


def test_vibe_istemin_basina_ortak_baglami_koyar_baglam_kapaliysa_istem_aynen(tmp_path, monkeypatch):
    gorulen = []

    class Islem:
        returncode = 0
        stdout = b"tamam"
        stderr = b""

    def sahte_run(komut, **k):
        gorulen.append(Path(komut[komut.index("--prompt-file") + 1]).read_text(encoding="utf-8"))
        return Islem()

    monkeypatch.setattr(runners.subprocess, "run", sahte_run)
    v = runners.VibeCalistirici(komut_oneki=["vibe"])
    v.calistir("yeni istek", tmp_path)
    assert gorulen[-1] == "yeni istek"  # DURUM.md yok: degisiklik yok
    _kayit(tmp_path, "a1", "onceki gorev", "onceki yanit", "opencode-sunucu")
    (tmp_path / ".aktapokus" / baglam.DURUM_ADI).write_text(baglam.durum_metni(tmp_path), encoding="utf-8")
    v.calistir("yeni istek", tmp_path)
    assert gorulen[-1].endswith("yeni istek") and "onceki gorev" in gorulen[-1] and "onceki yanit" in gorulen[-1] and gorulen[-1].startswith("[Aktapokus ortak bağlam")


def test_konusma_ozeti_tum_kayitlari_kronolojik_ozetler_ve_istemi_verir(tmp_path):
    for i in range(15):
        _kayit(tmp_path, f"k{i:02d}", f"gorev {i}", f"yanit {i}", "claude" if i % 2 else "opencode-sunucu")
    r = baglam.konusma_ozeti_yaz(tmp_path)
    assert r == {"yol": ".aktapokus/KONUSMA-OZETI.md", "kayit": 15, "istem": baglam.OZET_ISTEMI, "sohbet": "ilk"}
    metin = (tmp_path / ".aktapokus" / "KONUSMA-OZETI.md").read_text(encoding="utf-8")
    assert "KONUSMA-OZETI.md" in baglam.OZET_ISTEMI and baglam.OZET_ISTEMI in metin
    assert "## Daha eski çalışmalar" in metin and "gorev 0" in metin and "yanit 0" not in metin  # ilk 3 calisma tek satir (yanit yok)
    assert metin.index("gorev 3") < metin.index("gorev 14") and "yanit 14" in metin and "yanit 3" in metin  # son 12 calisma tam, eskiden yeniye
    bos = tmp_path / "bos"
    bos.mkdir()
    assert baglam.konusma_ozeti_yaz(bos)["kayit"] == 0 and "Henüz" in (bos / ".aktapokus" / "KONUSMA-OZETI.md").read_text(encoding="utf-8")


def test_konusma_ozeti_ucu_ve_dugme_ve_calisma_sonu_guncellemesi(kur):
    from test_arayuz import klasor_sec

    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    assert api("POST", "/api/konusma-ozeti", {}, token=None)[0] == 401
    st, r = api("POST", "/api/konusma-ozeti", {})
    assert st == 200 and r["istem"] == baglam.OZET_ISTEMI and (kur.proje / ".aktapokus" / "KONUSMA-OZETI.md").exists()
    from test_arayuz import tam_kosu

    tam_kosu(app, api, kur.proje, gorev="ozete girecek gorev")
    assert "ozete girecek gorev" in (kur.proje / ".aktapokus" / "KONUSMA-OZETI.md").read_text(encoding="utf-8")  # calisma bitince kendiliginden yenilendi
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="ozetDugme"' in html and 'api("/api/konusma-ozeti"' in html and "t.value=r.istem" in html
