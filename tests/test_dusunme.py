"""Rol basina dusunme (effort) seviyesi: ayar dogrulamasi, Claude Code --effort, Codex model_reasoning_effort, hat baglantisi, model menusu."""

import re
from pathlib import Path

import pytest

from aktapokus_ai_studio.config import AyarHatasi, ayar_coz
from aktapokus_ai_studio.runners import ClaudeCodeCalistirici, CodexCalistirici

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def _veri(**rol):
    return {
        "akis": ["kodcu"],
        "roller": {"kodcu": {"calistirici": "claude", "model": None, "talimat": "t", **rol}},
        "azami_duzeltme": 1, "butce_token": 0, "zaman_asimi_sn": 600,
    }


def test_dusunme_ayari_dogrulanir():
    assert ayar_coz(_veri()).roller["kodcu"].dusunme == ""
    for k in ("low", "medium", "high", "xhigh", "max"):
        assert ayar_coz(_veri(dusunme=k)).roller["kodcu"].dusunme == k
    for kotu in ("ultra", "HIGH", 3, None):
        with pytest.raises(AyarHatasi):
            ayar_coz(_veri(dusunme=kotu))


def test_claude_effort_bayragi_yalniz_secilince():
    c = ClaudeCodeCalistirici(cli_yolu="claude")
    assert "--effort" not in c.komut("ayar.json", None, True)
    c.dusunme = "max"
    k = c.komut("ayar.json", None, True)
    assert k[k.index("--effort") + 1] == "max"
    c.dusunme = "gecersiz"
    assert "--effort" not in c.komut("ayar.json", None, True)


def test_codex_dusunme_yalniz_low_medium_high(tmp_path):
    c = CodexCalistirici(komut_oneki=["codex"])
    assert not any("model_reasoning_effort" in x for x in c.komut(tmp_path, None, True, "son.txt"))
    c.dusunme = "high"
    assert 'model_reasoning_effort="high"' in c.komut(tmp_path, None, True, "son.txt")
    c.dusunme = "max"  # Codex'te yok: gonderilmez
    assert not any("model_reasoning_effort" in x for x in c.komut(tmp_path, None, True, "son.txt"))


def test_hat_rolun_dusunmesini_calistiriciya_verir():
    from aktapokus_ai_studio.pipeline import calistir_hat  # noqa: F401  (baglanti: pipeline rol.dusunme'yi okur)
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "pipeline.py").read_text(encoding="utf-8")
    assert re.search(r"ru\.dusunme = rol\.dusunme or None", kaynak)


def test_model_menusunde_dusunme_secenekleri():
    assert "DUSUNME_SEVIYE" in HTML and "ham.roller[rol].dusunme=k" in HTML
    assert '"low","medium","high","xhigh","max"' in HTML and 'c==="codex"?["low","medium","high"]' in HTML
