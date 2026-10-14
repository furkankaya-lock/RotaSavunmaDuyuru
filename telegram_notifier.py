import logging
import time

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.api_url = TELEGRAM_API_BASE.format(token=bot_token)

    def _redact(self, text: str) -> str:
        """Hata mesajlarında bot token'ı sızmasın (loglar herkese açık olabilir)."""
        if self.bot_token:
            return str(text).replace(self.bot_token, "***")
        return str(text)

    def send_announcement(self, title: str, site_label: str, url: str, date_str: str) -> bool:
        message = (
            "🚨 Yeni Duyuru!\n"
            f"📌 Başlık: {title}\n"
            f"🌐 Site: {site_label}\n"
            f"🔗 Link: {url}\n"
            f"🕒 Tarih: {date_str}"
        )
        return self._send(message)

    def send_text(self, text: str) -> bool:
        return self._send(text)

    def _send(self, text: str, max_retries: int = 3) -> bool:
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(self.api_url, data=payload, timeout=15)
                if resp.status_code == 200:
                    return True

                logger.warning(
                    f"Telegram gönderim hatası (deneme {attempt}/{max_retries}): "
                    f"{resp.status_code} {self._redact(resp.text)}"
                )

                if resp.status_code == 429:
                    try:
                        retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                    except Exception:
                        retry_after = 5
                    time.sleep(min(retry_after, 60))
                    continue

            except requests.RequestException as e:
                logger.warning(
                    f"Telegram istek hatası (deneme {attempt}/{max_retries}): {self._redact(e)}"
                )

            time.sleep(2 * attempt)

        logger.error("Telegram mesajı gönderilemedi, tüm denemeler başarısız oldu.")
        return False
