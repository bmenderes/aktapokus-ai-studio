"""Sahte Mistral Vibe: --prompt-file dosyasini okur, argumanlari SAHTE_CLI_LOG'a yazar, gercek --output streaming bicimiyle JSON satirlari basar, --output-dir'e export.json yazar.
SAHTE_VIBE_MOD: sinir (cikis kodu 3), yavas (kayitlar arasi 0.5 sn, toplam ~2.5 sn), takili (hic kayit yok, bekler)."""
import json
import os
import sys
import time

a = sys.argv[1:]
istem = open(a[a.index("--prompt-file") + 1], encoding="utf-8").read()
log = os.environ.get("SAHTE_CLI_LOG")
mod = os.environ.get("SAHTE_VIBE_MOD")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": a, "istem": istem, "cwd": os.getcwd()}) + "\n")


def yaz(**olay):
    print(json.dumps({"id": "x", "generationStatus": "completed", **olay}), flush=True)
    if mod == "yavas":
        time.sleep(0.5)


if mod == "sinir":
    print("tur siniri")
    sys.exit(3)
yaz(type="message", role="user", content=[{"type": "text", "text": istem}])
if mod == "takili":
    time.sleep(60)
yaz(type="reasoning", text="dusunuyorum", outcome={"type": "committed"})
yaz(type="effect", title="file_system.bash", detail={"toolName": "file_system.bash", "kind": "shell", "input": {"command": "echo merhaba"}}, state={"status": "completed", "display": {"success": True}})
yaz(type="effect", title="file_system.read_file", detail={"toolName": "file_system.read_file", "kind": "tool", "input": {"path": "yok.txt"}}, state={"status": "completed", "display": {"success": False}})
yaz(type="message", role="assistant", content=[{"type": "text", "text": "Bitti: " + istem[:20]}])
cikti = a[a.index("--output-dir") + 1]
os.makedirs(cikti, exist_ok=True)
with open(os.path.join(cikti, "export.json"), "w", encoding="utf-8") as f:
    json.dump({"version": "1", "usage": {"input_tokens": 700, "output_tokens": 30}, "steps": 2}, f)
