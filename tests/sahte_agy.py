"""Sahte Antigravity CLI (`agy -p`): stdin'i okur, argumanlari SAHTE_CLI_LOG'a yazar, stream-json/json/metin uretir.
SAHTE_AGY_MOD: '' (varsayilan NDJSON akisi), json (tekli JSON), metin (duz metin), hata (error olayi), cikis1 (cikis kodu 1), takili (bekler)."""
import json
import os
import sys
import time

stdin_metni = sys.stdin.buffer.read().decode("utf-8")
# Gercek agy (1.5) istemi YALNIZ --print=<istem> argumanindan alir, stdin okumaz; sahte de oyle davranir (stdin yalniz kayda yazilir).
girdi = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--print=")), "")
log = os.environ.get("SAHTE_CLI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": stdin_metni, "istem": girdi, "cwd": os.getcwd()}) + "\n")

mod = os.environ.get("SAHTE_AGY_MOD", "")
if mod == "json":
    print(json.dumps({
        "status": "SUCCESS",
        "response": "Tamam: " + girdi[:20],
        "usage": {"input_tokens": 1000, "output_tokens": 50, "cache_read_tokens": 200},
    }))
elif mod == "gercek":  # agy 1.5'in gercek ic ice bicimi (2026-11-23 kurulumdan)
    cid = "c-1"
    for o in [
        {"event": "init", "conversation_id": cid, "init": {"cwd": os.getcwd()}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 0, "state": "DONE", "step_type": "user_input"}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 1, "state": "ACTIVE", "step_type": "tool", "tool_name": "run_command", "tool_info": {"name": "run_command", "parameters": {"CommandLine": "dir"}}}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 1, "state": "DONE", "step_type": "tool", "tool_name": "run_command", "tool_info": {"name": "run_command", "parameters": {"CommandLine": "dir"}, "output": "x"}}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 2, "state": "ACTIVE", "step_type": "tool", "tool_name": "write_file", "tool_info": {"name": "write_file", "parameters": {"Path": "not.txt"}}}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 2, "state": "ERROR", "step_type": "tool", "tool_name": "write_file", "tool_info": {"name": "write_file"}}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 3, "state": "ACTIVE", "step_type": "agent_response", "text_delta": "Tamam: "}},
        {"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 3, "state": "DONE", "step_type": "agent_response", "text_delta": girdi[:6], "usage": {"input_tokens": 5}}},
        {"event": "result", "result": {"conversation_id": cid, "status": "SUCCESS", "response": "Tamam: " + girdi[:6], "num_turns": 1, "usage": {"input_tokens": 700, "output_tokens": 30, "thinking_tokens": 0, "cache_read_tokens": 100, "total_tokens": 730}}},
    ]:
        print(json.dumps(o), flush=True)
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
