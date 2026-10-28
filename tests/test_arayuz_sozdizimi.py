"""web/index.html icindeki betik soz diziminden gecmeli: tek bir bozuk dize ARAYUZUN TAMAMINI bos birakir (Python testleri bunu yakalamaz). node yoksa atlanir."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"


@pytest.mark.skipif(shutil.which("node") is None, reason="node kurulu degil")
def test_index_html_betigi_soz_dizimi_hatasiz(tmp_path):
    kaynak = (WEB / "index.html").read_text(encoding="utf-8")
    betikler = re.findall(r"<script[^>]*>(.*?)</script>", kaynak, re.S)
    assert betikler
    dosya = tmp_path / "ui.js"
    dosya.write_text("\n".join(betikler), encoding="utf-8")
    s = subprocess.run(["node", "--check", str(dosya)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert s.returncode == 0, s.stderr[:800]
