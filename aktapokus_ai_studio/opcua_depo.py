"""OPC UA olcumleri icin SQLite deposu (standart kutuphane; ek kurulum yok). Dosya: ~/.aktapokus/opcua.db (AKTAPOKUS_OPCUA_DB ile degisir)."""
import os
import sqlite3
import threading
from pathlib import Path

DB_ORTAMI = "AKTAPOKUS_OPCUA_DB"


def db_yolu() -> Path:
    ortam = os.environ.get(DB_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "opcua.db"


class Depo:
    def __init__(self, yol: Path | str | None = None):
        self.yol = Path(yol) if yol else db_yolu()
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._kilit = threading.Lock()
        self._db = sqlite3.connect(self.yol, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS olcum (id INTEGER PRIMARY KEY AUTOINCREMENT, zaman REAL NOT NULL, kaynak TEXT NOT NULL, "
            "kimlik TEXT NOT NULL, ad TEXT, sayi REAL, metin TEXT)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS olcum_kimlik_zaman ON olcum (kimlik, zaman)")
        self._db.commit()

    def ekle(self, kaynak: str, satirlar: list[tuple]) -> None:
        """satirlar: [(zaman, kimlik, ad, deger)]. bool/int/float -> sayi (bool 0/1), digerleri metin."""
        kayit = []
        for zaman, kimlik, ad, deger in satirlar:
            sayi = float(deger) if isinstance(deger, (bool, int, float)) else None
            kayit.append((zaman, kaynak, kimlik, ad, sayi, None if sayi is not None or deger is None else str(deger)))
        with self._kilit:
            self._db.executemany("INSERT INTO olcum (zaman, kaynak, kimlik, ad, sayi, metin) VALUES (?,?,?,?,?,?)", kayit)
            self._db.commit()

    def son(self, kimlik: str | None = None, n: int = 50) -> list[dict]:
        sorgu, arg = "SELECT zaman, kaynak, kimlik, ad, sayi, metin FROM olcum", []
        if kimlik:
            sorgu += " WHERE kimlik = ?"
            arg.append(kimlik)
        with self._kilit:
            satirlar = self._db.execute(sorgu + " ORDER BY id DESC LIMIT ?", [*arg, n]).fetchall()
        return [{"zaman": z, "kaynak": k, "kimlik": i, "ad": a, "deger": s if m is None else m} for z, k, i, a, s, m in satirlar]

    def say(self) -> int:
        with self._kilit:
            return self._db.execute("SELECT COUNT(*) FROM olcum").fetchone()[0]

    def sil_eski(self, zaman: float) -> int:
        with self._kilit:
            n = self._db.execute("DELETE FROM olcum WHERE zaman < ?", (zaman,)).rowcount
            self._db.commit()
        return n

    def kapat(self) -> None:
        with self._kilit:
            self._db.close()
