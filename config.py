import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()

# RUN_ONCE=1  -> tek tur tara ve çık (GitHub Actions bu modu kullanır)
# RUN_ONCE boş -> CHECK_INTERVAL_MINUTES aralığıyla sürekli döngü (yerel/VPS)
RUN_ONCE = _flag("RUN_ONCE")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "45"))

# "Hangi duyuruyu gönderdim" kaydının nerede tutulacağı (öncelik sırası):
#   1) STATE_FILE   -> JSON dosyası (GitHub Actions: repoya commit edilir)
#   2) DATABASE_URL -> Postgres
#   3) SQLITE_PATH  -> yerel SQLite dosyası
STATE_FILE = os.getenv("STATE_FILE", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "bot_data.db").strip()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

REQUIRED_VARS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID"]


def validate_config():
    missing = [v for v in REQUIRED_VARS if not os.getenv(v, "").strip()]
    if missing:
        raise RuntimeError(
            f"Eksik ortam değişkenleri: {', '.join(missing)}. "
            f"GitHub'da Settings > Secrets and variables > Actions bölümünden ekleyin "
            f"(yerelde .env dosyası kullanılabilir)."
        )
