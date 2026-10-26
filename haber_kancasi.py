"""Claude Code UserPromptSubmit kancasi baslaticisi.

Claude Code her kullanici mesajindan once bu dosyayi calistirir; yazdigi metin Claude'un baglamina eklenir (yeni bir sey yoksa hicbir sey yazmaz).
Kurulum (~/.claude/settings.json):  {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "<python> <bu dosya>"}]}]}}
Hicbir hatada Claude Code'u engellemez."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], "haber", "--kanca"]
try:
    from aktapokus_ai_studio.cli import main_giris

    main_giris()
except SystemExit as cikis:
    sys.exit(0 if cikis.code not in (0, None) else 0)
except BaseException:
    sys.exit(0)
