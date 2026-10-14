import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Kaynak başına saklanacak en fazla kayıt. Siteler sayfada sadece son birkaç
# duyuruyu gösterdiği için bu sayı fazlasıyla yeterli; dosyanın şişmesini engeller.
MAX_ITEMS_PER_SOURCE = 500


class JsonStorage:
    """
    Görülen duyuruları küçük bir JSON dosyasında tutar.

    GitHub Actions'ta her çalıştırma sıfırdan başladığı için bu dosya her turdan
    sonra repoya commit edilir; bir sonraki tur aynı dosyayı okuyarak eski
    duyuruları tekrar göndermez.

    Dosya biçimi:
        {"jandarma": {"<id>": {"title": "...", "url": "...", "seen_at": "..."}}, ...}
    """

    def __init__(self, path: str):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            logger.info(f"Kayıt dosyası yok, boş başlanıyor: {self.path}")
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("kök öğe sözlük değil")
            return data
        except (OSError, ValueError) as e:
            logger.error(f"Kayıt dosyası okunamadı ({e}); boş başlanıyor: {self.path}")
            return {}

    def _save(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        # Önce geçici dosyaya yaz, sonra yerine taşı: yarım yazılmış dosya kalmaz.
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
                f.write("\n")
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def has_any(self, source: str) -> bool:
        return bool(self._data.get(source))

    def is_seen(self, source: str, external_id: str) -> bool:
        return external_id in self._data.get(source, {})

    def mark_seen(self, source: str, external_id: str, title: str, url: str):
        bucket = self._data.setdefault(source, {})
        if external_id in bucket:
            return
        bucket[external_id] = {
            "title": title,
            "url": url,
            "seen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        while len(bucket) > MAX_ITEMS_PER_SOURCE:
            bucket.pop(next(iter(bucket)))  # en eskiyi at (ekleme sırası korunur)
        self._save()


class SqlStorage:
    """
    SQLite (varsayılan) veya Postgres (database_url verilirse) kullanır.
    Sürekli çalışan sunucu/VPS kurulumları için; GitHub Actions'ta kullanılmaz.
    """

    def __init__(self, database_url: str = "", sqlite_path: str = "bot_data.db"):
        self.database_url = database_url
        self.sqlite_path = sqlite_path
        self.backend = "postgres" if database_url else "sqlite"
        self._ph = "%s" if self.backend == "postgres" else "?"
        self._init_db()

    def _get_conn(self):
        if self.backend == "postgres":
            try:
                import psycopg2
            except ImportError as e:
                raise RuntimeError(
                    "Postgres için 'psycopg2-binary' paketi gerekli (pip install psycopg2-binary)."
                ) from e
            return psycopg2.connect(self.database_url)
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            ts_default = "NOW()" if self.backend == "postgres" else "CURRENT_TIMESTAMP"
            ts_type = "TIMESTAMP" if self.backend == "postgres" else "TEXT"
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS seen_announcements (
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    first_seen_at {ts_type} DEFAULT {ts_default},
                    PRIMARY KEY (source, external_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(f"Veritabanı hazır (backend={self.backend})")

    def _fetch_one(self, query: str, params: tuple):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur.fetchone()
        finally:
            conn.close()

    def is_seen(self, source: str, external_id: str) -> bool:
        ph = self._ph
        row = self._fetch_one(
            f"SELECT 1 FROM seen_announcements WHERE source={ph} AND external_id={ph}",
            (source, external_id),
        )
        return row is not None

    def has_any(self, source: str) -> bool:
        ph = self._ph
        row = self._fetch_one(
            f"SELECT 1 FROM seen_announcements WHERE source={ph} LIMIT 1", (source,)
        )
        return row is not None

    def mark_seen(self, source: str, external_id: str, title: str, url: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            if self.backend == "postgres":
                cur.execute(
                    """INSERT INTO seen_announcements (source, external_id, title, url)
                       VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (source, external_id, title, url),
                )
            else:
                cur.execute(
                    """INSERT OR IGNORE INTO seen_announcements (source, external_id, title, url)
                       VALUES (?, ?, ?, ?)""",
                    (source, external_id, title, url),
                )
            conn.commit()
        finally:
            conn.close()


def build_storage(state_file: str = "", database_url: str = "", sqlite_path: str = "bot_data.db"):
    """Ayarlara göre uygun kayıt mekanizmasını seçer (STATE_FILE > DATABASE_URL > SQLite)."""
    if state_file:
        logger.info(f"Kayıt: JSON dosyası ({state_file})")
        return JsonStorage(state_file)
    return SqlStorage(database_url=database_url, sqlite_path=sqlite_path)
