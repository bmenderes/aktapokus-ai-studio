"""Sahte Antigravity CLI (`agy -p`): stdin'i okur, argumanlari SAHTE_CLI_LOG'a yazar, stream-json/json/metin uretir.
SAHTE_AGY_MOD: '' (varsayilan NDJSON akisi), json (tekli JSON), metin (duz metin), hata (error olayi), cikis1 (cikis kodu 1), takili (bekler)."""
import json
import os
import sys
import time

girdi = sys.stdin.buffer.read().decode("utf-8")
log = os.environ.get("SAHTE_CLI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": girdi, "cwd": os.getcwd()}) + "\n")

mod = os.environ.get("SAHTE_AGY_MOD", "")
if mod == "json":
    print(json.dumps({
        "status": "SUCCESS",
        "response": "Tamam: " + girdi[:20],
        "usage": {"input_tokens": 1000, "output_tokens": 50, "cache_read_tokens": 200},
    }))
elif mod == "metin":
    print("Tamam: " + girdi[:20])
elif mod == "takili":
    print(json.dumps({"event": "init", "conversation_id": "agy-takili"}), flush=True)
    time.sleep(60)
elif mod == "hata":
    print(json.dumps({"event": "error", "error": {"message": "kota doldu"}}), flush=True)
    print(json.dumps({"event": "result", "status": "error", "error": {"message": "kota doldu"}}), flush=True)
elif mod == "cikis1":
    sys.stderr.write("yetki hatasi")
    sys.exit(1)
else:
    olaylar = [
        {"event": "init", "conversation_id": "agy-1", "model": "gemini-4-argon"},
        {"event": "step_update", "step_type": "thought", "content": "planliyorum"},
        {"event": "step_update", "step_type": "tool_call", "tool": "bash", "arguments": {"command": "pytest -q"}},
        {"event": "step_update", "step_type": "tool_result", "status": "success"},
        {"event": "step_update", "step_type": "tool_call", "tool": "read_file", "arguments": {"path": "x.py"}},
        {"event": "step_update", "step_type": "tool_result", "status": "error"},
        {"event": "step_update", "step_type": "text", "content": "Merhaba ", "delta": True},
        {"event": "step_update", "step_type": "text", "content": girdi[:10], "delta": True},
        {
            "event": "result",
            "status": "SUCCESS",
            "response": "Merhaba " + girdi[:10],
            "usage": {"input_tokens": 1000, "output_tokens": 50, "cache_read_tokens": 200},
        },
    ]
    for o in olaylar:
        print(json.dumps(o), flush=True)
