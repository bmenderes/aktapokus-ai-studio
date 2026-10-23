"""ATLANMAYAN terminal denetimi: pytest'in cikti yakalamasi surecin standart tutamaclarini yonlendirir; terminal bu durumda da (ve konsolsuz `pythonw`
altinda da) calismali. GERCEK HATA: STARTF_USESTDHANDLES verilmeyince kabuk sahte konsola degil ebeveynin yonlendirmesine yaziyor, terminal sessiz kaliyordu.
Bu test, test_terminal.py'nin ConPTY yokken atlanmasina ragmen bu gerilemeyi YAKALAR."""

import pytest

from aktapokus_ajan import terminal


@pytest.mark.skipif(not terminal.destekleniyor(), reason="ConPTY yalniz Windows 10 (1809+) / 11'de")
def test_terminal_yonlendirilmis_standart_cikti_altinda_da_calisir():
    assert terminal.kontrol(yeniden=True) is True, "ConPTY kabugu sahte konsola baglanmadi (standart tutamaclar yonlendirilmis olabilir)"


def test_destek_yoksa_kontrol_false_doner_ve_hata_firlatmaz(monkeypatch):
    monkeypatch.setattr(terminal, "destekleniyor", lambda: False)
    assert terminal.kontrol(yeniden=True) is False
    with pytest.raises(terminal.TerminalHatasi, match="Windows"):
        terminal.Terminal()
