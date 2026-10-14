import logging
import ssl
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# OpenSSL 3.x bazı .gov.tr sunucularıyla "UNEXPECTED_EOF_WHILE_READING" hatası
# veriyor (eski TLS yapılandırması). Bu bayrak, eski sunucularla el sıkışmayı
# mümkün kılıyor.
_SSL_OP_LEGACY_SERVER_CONNECT = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)


def _legacy_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    ctx.options |= _SSL_OP_LEGACY_SERVER_CONNECT
    return ctx


class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = _legacy_ssl_context()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = _legacy_ssl_context()
        return super().proxy_manager_for(*args, **kwargs)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.mount("https://", LegacySSLAdapter())
    return session


def _same_host(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


def fetch_html(url: str, warmup_url: str = None, timeout: int = 20, max_retries: int = 3) -> Optional[str]:
    """
    Sayfayı indirir. Hata veya beklenmedik yönlendirme olursa her denemede
    taze bir oturumla yeniden dener.

    - warmup_url verilirse önce o adrese gidilip çerez alınır, asıl istek
      Referer ile yapılır (bazı siteler doğrudan isteklere karşı korumalı).
    - Site bot korumasına takılınca isteği başka bir alan adına (örn. ana
      siteye) yönlendirebiliyor; bu durumda yanlış sayfayı ayrıştırmamak için
      son adresin beklenenle aynı sunucuda olduğu doğrulanır.
    """
    for attempt in range(1, max_retries + 1):
        session = _build_session()

        if warmup_url:
            try:
                session.get(warmup_url, timeout=timeout)
            except requests.RequestException as e:
                logger.warning(f"Warmup isteği başarısız ({warmup_url}): {e}")

        headers = {"Referer": warmup_url} if warmup_url else {}

        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            if not _same_host(resp.url, url):
                logger.warning(
                    f"[{url}] beklenmedik şekilde farklı bir adrese yönlendirildi ({resp.url}), "
                    f"tekrar deneniyor (deneme {attempt}/{max_retries})."
                )
                time.sleep(2 * attempt)
                continue
            resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"[{url}] fetch hatası (deneme {attempt}/{max_retries}): {e}")
            time.sleep(2 * attempt)

    logger.error(f"[{url}] sayfa alınamadı, tüm denemeler başarısız.")
    return None


def get_soup(url: str, warmup_url: str = None) -> Optional[BeautifulSoup]:
    html = fetch_html(url, warmup_url=warmup_url)
    if html is None:
        return None
    return BeautifulSoup(html, "html.parser")
