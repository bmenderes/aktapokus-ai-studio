"""Masaustu araclarini MCP (stdio, satir bazli JSON-RPC) ile ajana sunar. Ek kutuphane yok. Sunucuyu CLI baslatir: `python -m aktapokus_ai_studio masaustu-mcp`."""

from __future__ import annotations

import base64
import json
import sys
import time

from . import masaustu

SURUM = "2024-11-05"
_YER = {"x": {"type": "number"}, "y": {"type": "number"}, "kaynak": {"type": "string", "enum": ["goruntu", "ekran"], "description": "goruntu: son ekran_goruntusu pikseli (varsayilan); ekran: ogeler aracindaki koordinat"}}
ARACLAR = [
    {"name": "pencereler", "description": "Acik pencereleri listeler (numara, baslik, program, konum).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ekran_goruntusu", "description": "Ekranin ya da verilen pencerenin goruntusunu verir. Goruntu dis model saglayicisina gider; gizli bilgi acikken kullanmayin.", "inputSchema": {"type": "object", "properties": {"pencere": {"type": "integer"}}}},
    {"name": "ogeler", "description": "Penceredeki dugme ve kutulari yazili verir (ekran koordinatiyla). Goruntu gormeyen modeller bunu kullanir.", "inputSchema": {"type": "object", "properties": {"pencere": {"type": "integer"}}, "required": ["pencere"]}},
    {"name": "program_baslat", "description": "Program acar: .exe yolu, PATH'teki ad ya da Baslat menusu adi (ornek: SOLIDWORKS). PLC programlama yazilimlari ve kabuklar engellidir; PLC'ye yazmak yasaktir.", "inputSchema": {"type": "object", "properties": {"ad": {"type": "string"}, "argumanlar": {"type": "array", "items": {"type": "string"}}}, "required": ["ad"]}},
    {"name": "odakla", "description": "Pencereyi one getirir.", "inputSchema": {"type": "object", "properties": {"pencere": {"type": "integer"}}, "required": ["pencere"]}},
    {"name": "tikla", "description": "Tiklar. Once ekran_goruntusu ya da ogeler ile yeri belirleyin.", "inputSchema": {"type": "object", "properties": {**_YER, "dugme": {"type": "string", "enum": ["sol", "sag"]}, "cift": {"type": "boolean"}}, "required": ["x", "y"]}},
    {"name": "yaz", "description": "Etkin pencereye metin yazar. Etkin pencere degisirse durur.", "inputSchema": {"type": "object", "properties": {"metin": {"type": "string"}}, "required": ["metin"]}},
    {"name": "tus", "description": "Tus ya da kisayol basar, ornek: enter, ctrl+s, alt+f4. Win tusu kullanilamaz.", "inputSchema": {"type": "object", "properties": {"tuslar": {"type": "string"}}, "required": ["tuslar"]}},
    {"name": "kaydir", "description": "Verilen noktada fare tekerlegini cevirir (arti: yukari).", "inputSchema": {"type": "object", "properties": {**_YER, "miktar": {"type": "integer"}}, "required": ["x", "y", "miktar"]}},
    {"name": "bekle", "description": "En cok 10 saniye bekler (program acilirken).", "inputSchema": {"type": "object", "properties": {"saniye": {"type": "number"}}, "required": ["saniye"]}},
]


def _metin(v: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(v, ensure_ascii=False)}]}


def arac_calistir(ad: str, g: dict) -> dict:
    try:
        if ad == "pencereler":
            return _metin(masaustu.pencereler())
        if ad == "ekran_goruntusu":
            png, bilgi = masaustu.ekran_goruntusu(g.get("pencere"))
            return {"content": [{"type": "image", "data": base64.b64encode(png).decode("ascii"), "mimeType": "image/png"}, {"type": "text", "text": json.dumps(bilgi)}]}
        if ad == "ogeler":
            return _metin(masaustu.ogeler(g.get("pencere")))
        if ad == "program_baslat":
            return _metin(masaustu.program_baslat(g.get("ad"), g.get("argumanlar")))
        if ad == "odakla":
            return _metin(masaustu.odakla(g.get("pencere")))
        if ad == "tikla":
            return _metin(masaustu.tikla(g.get("x"), g.get("y"), g.get("dugme", "sol"), g.get("cift", False), g.get("kaynak", "goruntu")))
        if ad == "yaz":
            return _metin(masaustu.yaz(g.get("metin")))
        if ad == "tus":
            return _metin(masaustu.tus(g.get("tuslar")))
        if ad == "kaydir":
            return _metin(masaustu.kaydir(g.get("x"), g.get("y"), g.get("miktar"), g.get("kaynak", "goruntu")))
        if ad == "bekle":
            time.sleep(max(0.0, min(10.0, float(g.get("saniye", 1)))))
            return _metin({"beklendi": True})
        raise masaustu.MasaustuHatasi(f"Bilinmeyen arac: {ad}")
    except (masaustu.MasaustuHatasi, OSError, TypeError, ValueError) as hata:
        masaustu.kaydet(ad, "", f"hata: {hata}")
        return {"content": [{"type": "text", "text": str(hata)}], "isError": True}


def isle(istek: dict) -> dict | None:
    """Bir JSON-RPC iletisi > yanit (bildirimlere yanit yok)."""
    no, yontem = istek.get("id"), istek.get("method")
    if no is None:
        return None
    if yontem == "initialize":
        sonuc: dict = {"protocolVersion": (istek.get("params") or {}).get("protocolVersion") or SURUM, "capabilities": {"tools": {}}, "serverInfo": {"name": "aktapokus-masaustu", "version": "1"}}
    elif yontem == "ping":
        sonuc = {}
    elif yontem == "tools/list":
        sonuc = {"tools": ARACLAR}
    elif yontem == "tools/call":
        p = istek.get("params") or {}
        sonuc = arac_calistir(str(p.get("name")), p.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": no, "error": {"code": -32601, "message": "Bilinmeyen yontem"}}
    return {"jsonrpc": "2.0", "id": no, "result": sonuc}


def calistir(giris=None, cikis=None) -> int:
    giris, cikis = giris or sys.stdin.buffer, cikis or sys.stdout.buffer
    for satir in giris:
        try:
            istek = json.loads(satir)
        except ValueError:
            continue
        yanit = isle(istek) if isinstance(istek, dict) else None
        if yanit is not None:
            cikis.write(json.dumps(yanit, ensure_ascii=False).encode("utf-8") + b"\n")
            cikis.flush()
    return 0
