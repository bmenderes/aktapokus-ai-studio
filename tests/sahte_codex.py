"""`codex exec` taklidi (yalnizca testler icin). Gercek Codex 0.101'de gozlenen arguman/olay bicimini izler.
Davranis, istem metnindeki isaretlerle secilir: FAIL -> turn.failed (cikis 1), DOSYA:<ad> -> klasore dosya yazar (read-only degilse),
YAVAS -> uzun bekler. Aldigi argumanlari/istemi SAHTE_CODEX_KAYIT dosyasina yazar."""

import json
import os
import re
import sys
import time
from pathlib import Path

a = sys.argv[1:]
istem = sys.stdin.buffer.read().decode("utf-8")  # gercek CLI gibi UTF-8 oku (yerel kod sayfasina bagimli olma)
kayit = os.environ.get("SAHTE_CODEX_KAYIT")


def deger(bayrak):
    return a[a.index(bayrak) + 1] if bayrak in a else None


klasor, son_dosya, kum, model = deger("-C"), deger("-o"), deger("--sandbox"), deger("-m")
if kayit:
    Path(kayit).write_text(json.dumps({"args": a, "istem": istem, "cwd": os.getcwd(), "pwd": os.environ.get("PWD")}), encoding="utf-8")
print(json.dumps({"type": "thread.started", "thread_id": "t1"}), flush=True)
print(json.dumps({"type": "turn.started"}), flush=True)
if "YAVAS" in istem:
    time.sleep(30)
if "FAIL" in istem:
    mesaj = "The 'x' model requires a newer version of Codex."
    print(json.dumps({"type": "error", "message": mesaj}), flush=True)
    print(json.dumps({"type": "turn.failed", "error": {"message": mesaj}}), flush=True)
    sys.stderr.write("2026-10-22 ERROR codex_core: gurultu\n")
    sys.exit(1)
m = re.search(r"DOSYA:(\S+)", istem)
if m and kum != "read-only" and klasor:
    (Path(klasor) / m.group(1)).write_text("codex yazdi\n", encoding="utf-8")
son = "Bitti.\nSONUC: BASARILI"
print(json.dumps({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "ara mesaj"}}), flush=True)
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 120, "cached_input_tokens": 40, "output_tokens": 30}}), flush=True)
if son_dosya:
    Path(son_dosya).write_text(son, encoding="utf-8")
