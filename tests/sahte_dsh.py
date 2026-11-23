"""Sahte DeepSeek Harness (`dsh --profile headless`): stdin'i okur, argumanlari SAHTE_CLI_LOG'a yazar, duz metin ya da JSON/JSONL olay uretir.
SAHTE_DSH_MOD: json (JSON olay), jsonl (satir satir JSONL olay), hata (JSON error), cikis1 (cikis kodu 1), takili (bekler)."""
import json
import os
import sys
import time

girdi = sys.stdin.buffer.read().decode("utf-8")
log = os.environ.get("SAHTE_CLI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": girdi, "cwd": os.getcwd()}) + "\n")
mod = os.environ.get("SAHTE_DSH_MOD", "")
if mod == "json":
    print(json.dumps({
        "event": "response",
        "session_id": "sess_123",
        "data": {
            "text": "Tamam: " + girdi[:20],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 50,
                "cache_read_tokens": 200,
                "cache_write_tokens": 100,
                "uncached_input_tokens": 800,
            },
        },
    }))
elif mod == "jsonl":
    print(json.dumps({"event": "start", "session_id": "sess_1"}), flush=True)
    sys.stderr.write("dsh: reasoning: analiz ediyorum\n")
    sys.stderr.flush()
    print(json.dumps({"event": "thinking", "data": {"text": "derin dusunce"}}), flush=True)
    print(json.dumps({"event": "tool_call", "data": {"tool": "bash", "input": {"command": "pytest"}}}), flush=True)
    print(json.dumps({"event": "tool_result", "data": {"is_error": False}}), flush=True)
    print(json.dumps({"event": "response", "data": {"text": "SatirA"}}), flush=True)
    print(json.dumps({"event": "response", "data": {"text": "SatirB", "usage": {"prompt_tokens": 500, "completion_tokens": 40, "cache_read_tokens": 100}}}), flush=True)
elif mod == "takili":
    print("dsh: starting", flush=True)
    time.sleep(30)
elif mod == "hata":
    print(json.dumps({"event": "error", "error": {"message": "bakiye yetersiz"}}))
elif mod == "cikis1":
    sys.stderr.write("yetki hatasi")
    sys.exit(1)
else:
    print("Tamam: " + girdi[:20])
