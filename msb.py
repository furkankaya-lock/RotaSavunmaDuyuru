import re
import time
import logging
from urllib.parse import urljoin

from .base import get_soup

logger = logging.getLogger(__name__)

BASE_URL = "https://personeltemin.msb.gov.tr"
HOME_URL = f"{BASE_URL}/"

# Kartlar <a href> DEĞİL, şu biçimde:
#   <div class="item cal" onclick="javascript: window.location.href='/AnaSayfa/DuyuruDetay/?id=...';">
# Bu yüzden link onclick içinden çıkarılır.
ONCLICK_HREF_RE = re.compile(r"window\.location\.href\s*=\s*'([^']+)'")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

# MSB zaman zaman kartları olmayan boş/engel sayfası döndürüyor (sadece başlık).
# Bu durumda taze oturumla, aralıklarla yeniden denenir.
PAGE_ATTEMPTS = 6
RETRY_WAIT_SECONDS = 6


def scrape_home() -> dict:
    """
    MSB Personel Temin ana sayfasını (personeltemin.msb.gov.tr) tek istekle tarar.

    Gerçek sayfa yapısı (kaynak koddan doğrulandı):
      - Güncel Teminler : div.cal > div.home-first-block--item    > h3 + p.date
      - Güncel Duyurular: div.cal > div.home-first-calendar--item > div.item--exp > h3 + p.date
        (duyuru kartında ayrıca gün rozeti olarak "8" gibi bir p.date daha var;
         bu yüzden sadece DD.MM.YYYY biçimindeki tarih alınır)

    Dönüş: {"duyuru": [...], "temin": [...]}
    Her öğe: {"id": url, "title": str, "url": str, "date": "DD.MM.YYYY"}
    """
    cards = []
    for attempt in range(1, PAGE_ATTEMPTS + 1):
        soup = get_soup(HOME_URL, warmup_url=HOME_URL)
        if soup is None:
            logger.warning(f"[MSB] ana sayfa alınamadı (deneme {attempt}/{PAGE_ATTEMPTS}).")
        else:
            cards = soup.find_all("div", class_="cal")
            logger.info(f"[MSB] sayfa alındı, {len(cards)} adet kart (div.cal) bulundu (deneme {attempt}/{PAGE_ATTEMPTS}).")
            if cards:
                break
            # Teşhis: beklenen sayfa mı geldi, yoksa engel/bakım/yönlendirme sayfası mı?
            title_tag = soup.find("title")
            page_title = title_tag.get_text(strip=True) if title_tag else "(başlık yok)"
            preview = soup.get_text(" ", strip=True)[:300]
            logger.warning(f"[MSB] 0 kart bulundu. Sayfa başlığı: '{page_title}'")
            logger.warning(f"[MSB] Sayfa metni önizleme: {preview}")
        if attempt < PAGE_ATTEMPTS:
            time.sleep(RETRY_WAIT_SECONDS * attempt)

    if not cards:
        logger.error("[MSB] tüm denemelerde kart bulunamadı.")
        return {"duyuru": [], "temin": []}

    result = {"duyuru": [], "temin": []}
    seen_urls = set()

    for card in cards:
        match = ONCLICK_HREF_RE.search(card.get("onclick", ""))
        if not match:
            continue

        full_url = urljoin(BASE_URL, match.group(1).strip())
        if full_url in seen_urls:
            continue

        h3 = card.find("h3")
        title = " ".join(h3.get_text(" ", strip=True).split()) if h3 else ""

        date_str = ""
        for date_tag in card.find_all("p", class_="date"):
            candidate = date_tag.get_text(strip=True)
            if DATE_RE.match(candidate):
                date_str = candidate
                break

        if not title or not date_str:
            continue

        if card.find(class_="home-first-block--item"):
            category = "temin"
        elif card.find(class_="home-first-calendar--item"):
            category = "duyuru"
        else:
            continue

        seen_urls.add(full_url)
        result[category].append({
            "id": full_url,
            "title": title,
            "url": full_url,
            "date": date_str,
        })

    for key, items in result.items():
        if not items:
            logger.warning(f"[MSB-{key}] hiç sonuç bulunamadı; sayfa yapısı beklenenden farklı olabilir.")

    return result
