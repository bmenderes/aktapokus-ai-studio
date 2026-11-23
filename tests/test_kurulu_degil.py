"""Kurulu olmayan CLI'ya bagli rol: gorev plan ONAYINDAN ONCE durur ve kurulum yolu soylenir."""

from types import SimpleNamespace

import pytest

from aktapokus_ai_studio import arayuz, clitanim


def _ayar(*roller):
    return SimpleNamespace(rol_sirasi=lambda: [SimpleNamespace(ad=a, calistirici=c, dogrulama=d) for a, c, d in roller])


@pytest.fixture
def listede(monkeypatch):
    monkeypatch.setattr(clitanim, "listele", lambda: [
        {"ad": "claude", "gorunen_ad": "Claude Code", "kurulu": True, "kurulum": clitanim.KURULUM["claude"]},
        {"ad": "antigravity", "gorunen_ad": "Antigravity CLI", "kurulu": False, "kurulum": clitanim.KURULUM["antigravity"]},
    ])


def test_kurulu_degilse_kurulum_yolu_ile_durur(listede):
    with pytest.raises(arayuz.UygulamaHatasi) as h:
        arayuz.Uygulama._kurulu_degilse_durdur(_ayar(("kodcu", "antigravity", False), ("test", "claude", True)), False)
    assert "Antigravity CLI kurulu degil" in str(h.value) and "install.ps1" in str(h.value) and "kodcu" in str(h.value)


def test_testsiz_kosuda_dogrulama_rolu_denetlenmez(listede):
    arayuz.Uygulama._kurulu_degilse_durdur(_ayar(("kodcu", "claude", False), ("test", "antigravity", True)), True)


def test_hepsi_kuruluysa_gecer(listede):
    arayuz.Uygulama._kurulu_degilse_durdur(_ayar(("kodcu", "claude", False)), False)


def test_her_yerlesik_cli_icin_kurulum_yolu_var():
    assert {c["ad"] for c in clitanim.listele() if c["yerlesik"]} <= set(clitanim.KURULUM)
