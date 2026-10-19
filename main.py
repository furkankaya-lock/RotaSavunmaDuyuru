import logging
import sys
import time
from dataclasses import dataclass

import config
from storage import build_storage
from telegram_notifier import TelegramNotifier
from scrapers import jandarma, msb

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

# key  : kayıt dosyasında/veritabanında kaynağı ayırt eden benzersiz ad
# label: Telegram mesajındaki "Site" alanında görünen ad
JANDARMA_SOURCE = {"key": "jandarma", "label": "Jandarma"}

# MSB'de iki kategori aynı ana sayfadan tek istekle çıkarılır (bkz. scrapers/msb.py)
MSB_SOURCES = {
    "duyuru": {"key": "msb_duyuru", "label": "MSB"},
    "temin": {"key": "msb_temin", "label": "MSB"},
}


@dataclass
class RunStats:
    sources_ok: int = 0       # içerik okunabilen kaynak sayısı
    sources_failed: int = 0   # hiç içerik okunamayan kaynak sayısı
    sent: int = 0             # Telegram'a gönderilen duyuru
    send_failed: int = 0      # gönderilemeyen duyuru (sonraki turda tekrar denenir)

    @property
    def healthy(self) -> bool:
        return self.sources_failed == 0 and self.send_failed == 0


def process_items(source: dict, items: list, storage, notifier, stats: RunStats):
    """Tek bir kaynağın sonuçlarını işler: ilk çalıştırmada baseline, sonrasında sadece yeniler."""
    key, label = source["key"], source["label"]

    if not items:
        stats.sources_failed += 1
        logger.warning(f"[{key}] içerik okunamadı, bu tur atlandı.")
        return
    stats.sources_ok += 1

    if not storage.has_any(key):
        # İlk çalıştırma: kanalı eski duyurularla doldurmamak için sadece en güncel
        # duyuruyu gönder, geri kalanları sessizce "görüldü" say.
        latest = items[0]
        if not notifier.send_announcement(latest["title"], label, latest["url"], latest["date"]):
            stats.send_failed += 1
            logger.error(f"[{key}] ilk duyuru gönderilemedi; sonraki turda tekrar denenecek.")
            return
        stats.sent += 1
        for item in items:
            storage.mark_seen(key, item["id"], item["title"], item["url"])
        logger.info(f"[{key}] ilk çalıştırma: {len(items)} kayıt baseline olarak işaretlendi.")
        return

    new_items = [item for item in items if not storage.is_seen(key, item["id"])]

    # Eskiden yeniye doğru gönder: kanalda kronolojik sırayla görünsün.
    for item in reversed(new_items):
        if notifier.send_announcement(item["title"], label, item["url"], item["date"]):
            storage.mark_seen(key, item["id"], item["title"], item["url"])
            stats.sent += 1
            logger.info(f"[{key}] yeni duyuru gönderildi: {item['title'][:70]}")
        else:
            stats.send_failed += 1
            logger.error(f"[{key}] gönderilemedi, sonraki turda tekrar denenecek: {item['title'][:70]}")
        time.sleep(1)  # Telegram flood limitine takılmamak için

    if not new_items:
        logger.info(f"[{key}] yeni duyuru yok.")


def check_all_sources(storage, notifier) -> RunStats:
    stats = RunStats()

    # --- Jandarma ---
    try:
        jandarma_items = jandarma.scrape()
    except Exception:
        logger.exception("[jandarma] tarama sırasında beklenmeyen hata")
        jandarma_items = []
    process_items(JANDARMA_SOURCE, jandarma_items, storage, notifier, stats)

    # --- MSB (tek istek, iki kategori) ---
    try:
        msb_result = msb.scrape_home()
    except Exception:
        logger.exception("[msb] tarama sırasında beklenmeyen hata")
        msb_result = {}

    for category, source in MSB_SOURCES.items():
        process_items(source, msb_result.get(category, []), storage, notifier, stats)

    logger.info(
        f"Tur bitti: {stats.sources_ok} kaynak okundu, {stats.sources_failed} okunamadı, "
        f"{stats.sent} duyuru gönderildi, {stats.send_failed} gönderilemedi."
    )
    return stats


def main():
    config.validate_config()

    storage = build_storage(
        state_file=config.STATE_FILE,
        database_url=config.DATABASE_URL,
        sqlite_path=config.SQLITE_PATH,
    )
    notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHANNEL_ID)

    if config.RUN_ONCE:
        logger.info("Tek tur modu (RUN_ONCE) — tarama başlıyor.")
        stats = check_all_sources(storage, notifier)
        # Sorun varsa çıkış kodu 1: GitHub Actions çalıştırmayı kırmızı gösterir ve
        # hesabına e-posta bildirimi gönderir. Kayıt dosyası yine de kaydedilir.
        sys.exit(0 if stats.healthy else 1)

    logger.info(f"Sürekli mod. Kontrol aralığı: {config.CHECK_INTERVAL_MINUTES} dakika")
    while True:
        try:
            check_all_sources(storage, notifier)
        except Exception:
            logger.exception("Ana döngüde beklenmeyen hata")
        time.sleep(config.CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
