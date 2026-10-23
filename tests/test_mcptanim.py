import json
import sys

import pytest

from aktapokus_ajan import mcptanim as m

SAHTE = {"ad": "sahte", "tur": "local", "komut": [sys.executable, "sunucu.py", "--x"], "ortam": {"ANAHTAR": "gizli-deger-123"}}
P1, P2 = "a" * 10, "b" * 10


def test_gecerli_tanim_kaydedilir_ve_yuklenir():
    t = m.kaydet(SAHTE)
    assert t.ad == "sahte" and t.komut[1:] == ("sunucu.py", "--x") and t.projeler == ()
    assert m.yukle()["sahte"].ortam == {"ANAHTAR": "gizli-deger-123"}  # diske TAM deger yazilir (CLI'lara aktarilacak)


def test_arayuze_giden_gorunumde_degerler_maskelidir():
    m.kaydet({**SAHTE, "ad": "uzak", "tur": "remote", "url": "https://x.example/mcp", "basliklar": {"Authorization": "Bearer ABC"}, "komut": None, "ortam": None})
    liste = {d["ad"]: d for d in m.listele()}
    assert liste["uzak"]["basliklar"] == {"Authorization": m.MASKE}
    kayit = json.dumps(m.listele())
    assert "Bearer ABC" not in kayit


def test_maskeli_deger_guncellemede_eskisini_korur_yeni_deger_degistirir():
    m.kaydet(SAHTE)
    m.kaydet({**SAHTE, "ortam": {"ANAHTAR": m.MASKE, "YENI": "v"}})
    assert m.yukle()["sahte"].ortam == {"ANAHTAR": "gizli-deger-123", "YENI": "v"}
    m.kaydet({**SAHTE, "ortam": {"ANAHTAR": "degisti"}})
    assert m.yukle()["sahte"].ortam == {"ANAHTAR": "degisti"}
    with pytest.raises(m.McpHatasi, match="kayitli deger yok"):
        m.kaydet({**SAHTE, "ad": "baska", "ortam": {"X": m.MASKE}})  # olmayan degeri 'koru' diyemezsin


@pytest.mark.parametrize("kotu", [
    {"ad": "Buyuk"}, {"ad": "../x"}, {"ad": ""}, {"ad": "a" * 40}, {"ad": "x", "tur": "baska"},
    {"ad": "x", "komut": []}, {"ad": "x", "komut": "cmd /c calc"}, {"ad": "x", "komut": [sys.executable, 5]},
    {"ad": "x", "komut": ["olmayan-program-xyz"]}, {"ad": "x", "komut": [sys.executable] + ["a"] * 60},
    {"ad": "x", "komut": [sys.executable, "a\x00b"]},
    {"ad": "x", "komut": [sys.executable], "ortam": {"1KOTU": "v"}}, {"ad": "x", "komut": [sys.executable], "ortam": {"A": "satir\nsonu"}},
    {"ad": "x", "komut": [sys.executable], "ortam": {"A": 5}}, {"ad": "x", "komut": [sys.executable], "projeler": ["../x"]},
    {"ad": "x", "tur": "remote", "url": "ftp://x"}, {"ad": "x", "tur": "remote", "url": "javascript:alert(1)"},
    {"ad": "x", "tur": "remote", "url": "https://kullanici:parola@x.example/"}, {"ad": "x", "tur": "remote", "url": "https:///yol"},
    {"ad": "x", "tur": "remote", "url": "https://x.example", "basliklar": {"Kotu Ad": "v"}},
])
def test_gecersiz_tanimlar_reddedilir(kotu):
    with pytest.raises(m.McpHatasi):
        m.tanim_coz(kotu)
    assert m.yukle() == {}


def test_ps1_ve_vbs_reddedilir(tmp_path):
    for uzanti in (".ps1", ".vbs"):
        f = tmp_path / f"x{uzanti}"
        f.write_text("x")
        with pytest.raises(m.McpHatasi, match="desteklenmez"):
            m.tanim_coz({"ad": "x", "komut": [str(f)]})


def test_proje_etkinlestirme_varsayilan_kapali_ac_kapat():
    m.kaydet(SAHTE)
    assert m.proje_icin(P1) == [] and m.yukle()["sahte"].projeler == ()
    m.proje_ayarla("sahte", P1, True)
    m.proje_ayarla("sahte", P1, True)  # tekrar: cogalmaz
    m.proje_ayarla("sahte", P2, True)
    assert [t.ad for t in m.proje_icin(P1)] == ["sahte"] and m.yukle()["sahte"].projeler == (P1, P2)
    m.proje_ayarla("sahte", P1, False)
    assert m.proje_icin(P1) == [] and [t.ad for t in m.proje_icin(P2)] == ["sahte"]
    assert m.proje_icin(None) == []
    with pytest.raises(m.McpHatasi):
        m.proje_ayarla("yok", P1, True)
    with pytest.raises(m.McpHatasi):
        m.proje_ayarla("sahte", "../kotu", True)


def test_sil_ve_olmayani_silme():
    m.kaydet(SAHTE)
    assert m.sil("sahte") is True and m.sil("sahte") is False and m.yukle() == {}


def test_bozuk_kayit_dosyasi_bos_sayilir_ve_gecersiz_girdi_atlanir():
    m.kayit_yolu().write_text("{bozuk", encoding="utf-8")
    assert m.yukle() == {}
    m.kayit_yolu().write_text(json.dumps({"sunucular": [{"ad": "KOTU"}, {"ad": "iyi", "tur": "remote", "url": "https://a.example/mcp"}]}), encoding="utf-8")
    assert list(m.yukle()) == ["iyi"]


def test_sunucu_sayisi_siniri():
    for i in range(m.AZAMI_SUNUCU):
        m.kaydet({**SAHTE, "ad": f"s{i}"})
    with pytest.raises(m.McpHatasi, match="En cok"):
        m.kaydet({**SAHTE, "ad": "fazla"})
    m.kaydet({**SAHTE, "ad": "s0", "aciklama": "guncelleme sinira takilmaz"})


# ---- CLI bicimleri ----
def _t(**kw):
    return m.tanim_coz({**SAHTE, **kw}, program_denetle=False)


def test_opencode_ayari_yerel_ve_uzak():
    assert m.opencode_ayari(_t()) == {"type": "local", "command": [sys.executable, "sunucu.py", "--x"], "environment": {"ANAHTAR": "gizli-deger-123"}}
    u = m.tanim_coz({"ad": "u", "tur": "remote", "url": "https://x.example/mcp", "basliklar": {"A": "b"}})
    assert m.opencode_ayari(u) == {"type": "remote", "url": "https://x.example/mcp", "headers": {"A": "b"}}


def test_claude_ayari_stdio_ve_http():
    u = m.tanim_coz({"ad": "u", "tur": "remote", "url": "https://x.example/mcp"})
    c = m.claude_ayari([_t(), u])["mcpServers"]
    assert c["sahte"] == {"type": "stdio", "command": sys.executable, "args": ["sunucu.py", "--x"], "env": {"ANAHTAR": "gizli-deger-123"}}
    assert c["u"] == {"type": "http", "url": "https://x.example/mcp"}


def test_codex_kilmalari_toml_gecerli_ve_ozel_karakterleri_kacirir():
    tomllib = pytest.importorskip("tomllib")
    t = _t(komut=[r"C:\Program Files\node\node.exe", 'dizge "tirnakli"', "uzun-ğüş"], ortam={"K": 'de"ger\\x'})
    args = m.codex_gecersiz_kilmalari([t])
    assert args[0::2] == ["-c"] * (len(args) // 2)
    birlesik = "\n".join(args[1::2])
    cozulen = tomllib.loads(birlesik)["mcp_servers"]["sahte"]
    assert cozulen["command"] == r"C:\Program Files\node\node.exe" and cozulen["args"] == ['dizge "tirnakli"', "uzun-ğüş"]
    assert cozulen["env"] == {"K": 'de"ger\\x'} and cozulen["default_tools_approval_mode"] == "approve"


def test_codex_uzak_sunucu_basliklari():
    tomllib = pytest.importorskip("tomllib")
    u = m.tanim_coz({"ad": "u", "tur": "remote", "url": "https://x.example/mcp", "basliklar": {"X-Anahtar": "d"}})
    c = tomllib.loads("\n".join(m.codex_gecersiz_kilmalari([u])[1::2]))["mcp_servers"]["u"]
    assert c["url"] == "https://x.example/mcp" and c["http_headers"] == {"X-Anahtar": "d"}
