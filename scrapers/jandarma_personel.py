"""
Jandarma Personel Temin Sistemi (https://personeltemin.jandarma.gov.tr/)

Bu site istemci tarafında (Next.js) çizilen bir uygulama olduğu için ham HTML boş
gelir; içerik ancak gerçek bir tarayıcıda görünür. Bu yüzden Playwright (Chromium)
ile sayfa açılır ve ekranda GÖRÜNEN METİN okunur. CSS sınıflarına bağımlı olmamak
için ayrıştırma metin üzerinden yapılır (parse_text).

Sayfada iki liste var:
  - "Güncel Faaliyetler"       : başvuru süreci olan alımlar (Başlama / Bitiş Tarihi)
  - "Güncel Sonuç Duyuruları"  : sonuç duyuruları (Yayın Tarihi)

scrape() dönüşü: {"faaliyet": list | None, "sonuc": list | None}
  - liste      : bölüm okundu (boş liste = o an gerçekten kayıt yok)
  - None       : bölüm okunamadı (sayfa gelmedi / yapı değişti) -> hata sayılır
Her öğe: {"id", "title", "url", "date": "DD.MM.YYYY"}
"""
import re
import logging
import time

logger = logging.getLogger(__name__)

PAGE_URL = "https://personeltemin.jandarma.gov.tr/"

DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
INDEX_PREFIX_RE = re.compile(r"^\d{1,2}\s+(?=\S)")  # "1 2027 YILI..." -> "2027 YILI..."
MIN_TITLE_LEN = 15

_ASCII_FOLD = str.maketrans("ıüöşçğâîû", "iuoscgaiu")


def _norm(text: str) -> str:
    """Büyük/küçük harf ve Türkçe karakter farklarını yok sayan karşılaştırma biçimi."""
    t = text.replace("İ", "i").replace("I", "ı").lower()
    return " ".join(t.translate(_ASCII_FOLD).split())


HEAD_FAALIYET = "guncel faaliyetler"
HEAD_SONUC = "guncel sonuc duyurulari"
LABEL_START = "baslama tarihi"
LABEL_END = "bitis tarihi"
LABEL_PUBLISH = "yayin tarihi"


def _find_date(lines: list, start: int, window: int = 4):
    """lines[start] ve sonraki birkaç satırda ilk DD.MM.YYYY tarihini arar."""
    for j in range(start, min(start + window, len(lines))):
        m = DATE_RE.search(lines[j])
        if m:
            return m.group(1), j
    return None, start


def _best_title(buffer: list) -> str:
    """Tarihten önce biriken satırlar arasından başlığı seçer (en uzun anlamlı satır)."""
    candidates = []
    for line in buffer:
        line = INDEX_PREFIX_RE.sub("", line.strip())
        if line.isdigit() or len(line) < MIN_TITLE_LEN:
            continue
        candidates.append(line)
    if not candidates:
        return ""
    return max(candidates, key=len)


def _split_sections(lines: list) -> dict:
    """Satırları başlıklara göre bölümlere ayırır: {"faaliyet": [...], "sonuc": [...]}"""
    marks = []
    for idx, line in enumerate(lines):
        n = _norm(line)
        if n == HEAD_FAALIYET:
            marks.append((idx, "faaliyet"))
        elif n == HEAD_SONUC:
            marks.append((idx, "sonuc"))
    sections = {}
    for pos, (idx, name) in enumerate(marks):
        end = marks[pos + 1][0] if pos + 1 < len(marks) else len(lines)
        if name not in sections:
            sections[name] = lines[idx + 1:end]
    return sections


def _parse_faaliyet(lines: list) -> list:
    items, buffer = [], []
    pending = None  # {"title", "start", "end"}
    i = 0
    while i < len(lines):
        line = lines[i]
        n = _norm(line)
        if LABEL_START in n:
            date, j = _find_date(lines, i)
            if date:
                if pending:  # öncekinin bitiş tarihi yoksa onu tamamla
                    items.append(pending)
                pending = {"title": _best_title(buffer), "start": date, "end": ""}
                buffer = []
                i = j + 1
                continue
        elif LABEL_END in n and pending:
            date, j = _find_date(lines, i)
            if date:
                pending["end"] = date
                items.append(pending)
                pending = None
                i = j + 1
                continue
        else:
            buffer.append(line)
        i += 1
    if pending:
        items.append(pending)

    result = []
    for it in items:
        if not it["title"]:
            continue
        result.append({
            "id": f"faaliyet|{it['title']}|{it['start']}",
            "title": it["title"],
            "url": PAGE_URL,
            "date": it["start"] if not it["end"] else f"{it['start']} (Bitiş: {it['end']})",
        })
    return result


def _parse_sonuc(lines: list) -> list:
    result, buffer = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if LABEL_PUBLISH in _norm(line):
            date, j = _find_date(lines, i)
            if date:
                title = _best_title(buffer)
                buffer = []
                i = j + 1
                if title:
                    result.append({
                        "id": f"sonuc|{title}|{date}",
                        "title": title,
                        "url": PAGE_URL,
                        "date": date,
                    })
                continue
        else:
            buffer.append(line)
        i += 1
    return result


def parse_text(text: str) -> dict:
    """Ekrandaki düz metni ayrıştırır (tarayıcıdan bağımsız, test edilebilir)."""
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n") if ln.strip()]
    sections = _split_sections(lines)

    faaliyet = _parse_faaliyet(sections["faaliyet"]) if "faaliyet" in sections else None
    sonuc = _parse_sonuc(sections["sonuc"]) if "sonuc" in sections else None
    return {"faaliyet": faaliyet, "sonuc": sonuc}


_TEXT_NODES_JS = """
() => {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const text = (node.nodeValue || "").replace(/\\s+/g, " ").trim();
    if (!text) continue;
    const el = node.parentElement;
    if (!el) continue;
    const tag = el.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "TEMPLATE") continue;
    if (el.getClientRects().length === 0) continue;   // görünmeyen öğeleri atla
    out.push(text);
  }
  return out.join("\\n");
}
"""


def _render_text(url: str, timeout_ms: int = 45000) -> str:
    """Sayfayı gerçek tarayıcıda açar ve görünen metni döndürür."""
    from playwright.sync_api import sync_playwright  # geç içe aktarma: paket yoksa diğer kaynaklar etkilenmesin

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(
                locale="tr-TR",
                ignore_https_errors=True,  # eski TLS yapılandırması; sadece herkese açık duyuru okunuyor
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                # Listeler API'den gelip çizilir: ekranda bir tarih belirene kadar bekle.
                page.wait_for_function(
                    "document.body && /\\d{2}\\.\\d{2}\\.\\d{4}/.test(document.body.innerText)",
                    timeout=25000,
                )
            except Exception:
                logger.warning("[Jandarma-Personel] tarih içeren liste beklenen sürede görünmedi.")
            # Her metin düğümü ayrı satır: CSS yerleşimi (satır içi / blok) fark etmez,
            # "Başlama Tarihi" ile tarih ya da sıra numarası ile başlık birbirine yapışmaz.
            return page.evaluate(_TEXT_NODES_JS)
        finally:
            browser.close()


def scrape(url: str = PAGE_URL, attempts: int = 3) -> dict:
    result = {"faaliyet": None, "sonuc": None}
    for attempt in range(1, attempts + 1):
        try:
            text = _render_text(url)
        except Exception as e:
            logger.warning(f"[Jandarma-Personel] sayfa açılamadı (deneme {attempt}/{attempts}): {e}")
            time.sleep(4 * attempt)
            continue

        parsed = parse_text(text)
        # Sonuç listesi her zaman dolu olur; boşsa sayfa tam yüklenmemiştir -> tekrar dene.
        if parsed["sonuc"]:
            result = parsed
            break

        preview = " ".join(text.split())[:300]
        logger.warning(
            f"[Jandarma-Personel] liste okunamadı (deneme {attempt}/{attempts}). "
            f"Metin önizleme: {preview}"
        )
        time.sleep(4 * attempt)

    if result["sonuc"] is None:
        logger.error("[Jandarma-Personel] sayfa okunamadı, tüm denemeler başarısız.")
        return {"faaliyet": None, "sonuc": None}

    logger.info(
        f"[Jandarma-Personel] {len(result['faaliyet'] or [])} faaliyet, "
        f"{len(result['sonuc'])} sonuç duyurusu okundu."
    )
    return result
