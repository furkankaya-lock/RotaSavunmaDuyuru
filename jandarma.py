import re
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from .base import get_soup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jandarma.gov.tr"
LIST_URL = f"{BASE_URL}/duyurular"

TR_MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
MONTH_PATTERN = "|".join(TR_MONTHS)

DAY_RE = re.compile(r"^\d{1,2}$")
MONTH_RE = re.compile(rf"^({MONTH_PATTERN})$")
MIN_TITLE_LEN = 12

TURKEY_TZ = timezone(timedelta(hours=3))  # Türkiye yıl boyunca UTC+3


def format_date(day: str, month_abbr: str, today=None) -> str:
    """
    Sitedeki "10" + "Eyl" rozetini "10.09.2026" biçimine çevirir (MSB ile aynı biçim).

    Sitede yıl yazmıyor; bu yüzden içinde bulunulan yıl kullanılır. Eğer bu,
    bugünden belirgin şekilde ileride bir tarih çıkarırsa (örn. Ocak'ta
    görülen bir Aralık duyurusu) bir önceki yıl alınır.
    """
    today = today or datetime.now(TURKEY_TZ).date()
    month = TR_MONTHS.index(month_abbr) + 1
    day_i = int(day)
    try:
        candidate = today.replace(year=today.year, month=month, day=day_i)
    except ValueError:  # örn. 29 Şubat artık yıl değilken
        return f"{day_i:02d}.{month:02d}.{today.year}"
    if candidate > today + timedelta(days=7):
        candidate = candidate.replace(year=today.year - 1)
    return candidate.strftime("%d.%m.%Y")


def scrape() -> list:
    """
    Jandarma /duyurular sayfasını tarar. Her duyuru bir 'gün' + 'ay (kısaltma)'
    rozeti ve başlık linkinden oluşuyor. DOM sırasına göre eşleştirilir.

    Dönüş: [{"id": url, "title": str, "url": str, "date": "10.09.2026"}, ...]
    En güncel duyuru listenin başında (sitedeki sırayla aynı).
    """
    soup = get_soup(LIST_URL)
    if soup is None:
        return []

    results = []
    seen_urls = set()
    pending_day = None
    pending_month = None

    for node in soup.descendants:
        if isinstance(node, str):
            text = node.strip()
            if not text:
                continue
            if DAY_RE.match(text):
                pending_day = text
            elif MONTH_RE.match(text):
                pending_month = text
        elif getattr(node, "name", None) == "a" and node.get("href"):
            href = node["href"].strip()
            if href.startswith("#") or href.startswith("javascript"):
                continue
            text = node.get_text(strip=True)
            if len(text) < MIN_TITLE_LEN:
                continue
            full_url = urljoin(BASE_URL, href)
            if not full_url.startswith(BASE_URL) or full_url in seen_urls:
                continue
            if pending_day and pending_month:
                results.append({
                    "id": full_url,
                    "title": text,
                    "url": full_url,
                    "date": format_date(pending_day, pending_month),
                })
                seen_urls.add(full_url)
                pending_day = None
                pending_month = None

    if not results:
        logger.warning("Jandarma sayfasında hiç duyuru bulunamadı; site yapısı değişmiş olabilir.")

    return results
