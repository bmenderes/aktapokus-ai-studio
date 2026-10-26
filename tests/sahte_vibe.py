"""Sahte Mistral Vibe: --prompt-file dosyasini okur, argumanlari SAHTE_CLI_LOG'a yazar, duz metin basar, --output-dir'e export.json yazar.
SAHTE_VIBE_MOD: sinir (cikis kodu 3)."""
import json
import os
import sys

a = sys.argv[1:]
istem = open(a[a.index("--prompt-file") + 1], encoding="utf-8").read()
log = os.environ.get("SAHTE_CLI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": a, "istem": istem, "cwd": os.getcwd()}) + "\n")
if os.environ.get("SAHTE_VIBE_MOD") == "sinir":
    print("tur siniri")
    sys.exit(3)
cikti = a[a.index("--output-dir") + 1]
os.makedirs(cikti, exist_ok=True)
with open(os.path.join(cikti, "export.json"), "w", encoding="utf-8") as f:
    json.dump({"version": "1", "usage": {"prompt_tokens": 700, "completion_tokens": 30}, "steps": []}, f)
print("Bitti: " + istem[:20])
