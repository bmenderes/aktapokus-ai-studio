"""Sahte Gemini CLI: stdin'i okur, argumanlari SAHTE_CLI_LOG'a yazar, Gemini'nin --output-format json / stream-json bicimini uretir.
SAHTE_GEMINI_MOD: hata (JSON error alani), bozuk (JSON degil), cikis1 (cikis kodu 1), stream_canli (NDJSON akis), takili (bekler)."""
import json
import os
import sys
import time

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
elif mod == "takili":
    print(json.dumps({"type": "init", "session_id": "s1", "model": "auto"}), flush=True)
    time.sleep(30)
elif mod == "stream_canli":
    for olay in (
        {"type": "init", "session_id": "s1", "model": "gemini-2.5-pro"},
        {"type": "thought", "content": "planliyorum", "delta": False},
        {"type": "tool_use", "tool_name": "run_shell_command", "tool_id": "t1", "parameters": {"command": "pytest -q"}},
        {"type": "tool_result", "tool_id": "t1", "status": "success"},
        {"type": "tool_use", "tool_name": "read_file", "tool_id": "t2", "parameters": {"path": "x.py"}},
        {"type": "tool_result", "tool_id": "t2", "status": "error", "error": {"message": "yok"}},
        {"type": "message", "role": "assistant", "content": "Merhaba ", "delta": True},
        {"type": "message", "role": "assistant", "content": girdi[:10], "delta": True},
        {"type": "result", "status": "success", "stats": {"models": {"gemini-2.5-pro": {"tokens": {"prompt": 1000, "candidates": 50, "cached": 200}}}}},
    ):
        print(json.dumps(olay), flush=True)
else:
    if os.environ.get("SAHTE_GEMINI_DOSYA"):
        with open(os.environ["SAHTE_GEMINI_DOSYA"], "w", encoding="utf-8") as f:
            f.write("yazildi")
    print("Loaded cached credentials.")
    print(json.dumps({"response": "Tamam: " + girdi[:20], "stats": {"models": {"gemini-2.5-pro": {"tokens": {"prompt": 1000, "candidates": 50, "cached": 200, "total": 1050}}}}}))
