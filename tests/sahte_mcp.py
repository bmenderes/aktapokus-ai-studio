"""Deneme icin minik stdio MCP sunucusu (yalniz standart kutuphane). Tek arac: `aktp_yanki` (metni 'YANKI:' onekiyle geri verir).
Gercek CLI'larin (OpenCode, Claude Code, Codex) MCP baglantisini sinamak icin kullanilir; satir satir JSON-RPC (protokol 2024-11-05)."""

import json
import sys

ARAC = {
    "name": "aktp_yanki",
    "description": "Verilen metni YANKI: onekiyle geri verir (Aktapokus MCP denemesi).",
    "inputSchema": {"type": "object", "properties": {"metin": {"type": "string"}}, "required": ["metin"]},
}


def yanit(kimlik, sonuc=None, hata=None):
    govde = {"jsonrpc": "2.0", "id": kimlik}
    if hata is not None:
        govde["error"] = hata
    else:
        govde["result"] = sonuc
    sys.stdout.write(json.dumps(govde) + "\n")
    sys.stdout.flush()


for satir in sys.stdin:
    satir = satir.strip()
    if not satir:
        continue
    try:
        m = json.loads(satir)
    except json.JSONDecodeError:
        continue
    yontem, kimlik = m.get("method"), m.get("id")
    if yontem == "initialize":
        surum = (m.get("params") or {}).get("protocolVersion") or "2024-11-05"
        yanit(kimlik, {"protocolVersion": surum, "capabilities": {"tools": {}}, "serverInfo": {"name": "sahte-mcp", "version": "1"}})
    elif yontem == "tools/list":
        yanit(kimlik, {"tools": [ARAC]})
    elif yontem == "tools/call":
        metin = ((m.get("params") or {}).get("arguments") or {}).get("metin", "")
        yanit(kimlik, {"content": [{"type": "text", "text": "YANKI:" + str(metin)}]})
    elif kimlik is not None:
        yanit(kimlik, hata={"code": -32601, "message": "yok"})
