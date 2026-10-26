"""Sahte Gemini CLI: stdin'i okur, argumanlari SAHTE_CLI_LOG'a yazar, Gemini'nin --output-format json bicimini uretir.
SAHTE_GEMINI_MOD: hata (JSON error alani), bozuk (JSON degil), cikis1 (cikis kodu 1)."""
import json
import os
import sys

girdi = sys.stdin.buffer.read().decode("utf-8")
log = os.environ.get("SAHTE_CLI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": girdi, "cwd": os.getcwd()}) + "\n")
mod = os.environ.get("SAHTE_GEMINI_MOD", "")
if mod == "bozuk":
    print("Merhaba ben JSON degilim")
elif mod == "hata":
    print(json.dumps({"error": {"type": "ApiError", "message": "kota doldu"}}))
elif mod == "cikis1":
    sys.stderr.write("beklenmeyen")
    sys.exit(1)
else:
    if os.environ.get("SAHTE_GEMINI_DOSYA"):
        with open(os.environ["SAHTE_GEMINI_DOSYA"], "w", encoding="utf-8") as f:
            f.write("yazildi")
    print("Loaded cached credentials.")
    print(json.dumps({"response": "Tamam: " + girdi[:20], "stats": {"models": {"gemini-2.5-pro": {"tokens": {"prompt": 1000, "candidates": 50, "cached": 200, "total": 1050}}}}}))
