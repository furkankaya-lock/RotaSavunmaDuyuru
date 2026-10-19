"""
Telegram'a HİÇ mesaj göndermez; sadece her kaynaktan neler okunabildiğini yazdırır.

    pip install -r requirements.txt
    python scrape_test.py

Bir kaynak "SONUÇ YOK" derse: o site bu ortamdan erişilemiyor (engel/yönlendirme)
ya da sayfa yapısı değişmiş olabilir.
"""
from scrapers import jandarma_personel, msb


def show(name, items):
    print(f"\n=== {name} ===")
    if not items:
        print("SONUÇ YOK")
        return
    for item in items[:5]:
        print(f"- [{item['date']}] {item['title']}")
        print(f"  {item['url']}")
    print(f"(toplam {len(items)} kayıt, ilk 5 tanesi gösterildi)")


if __name__ == "__main__":
    msb_result = msb.scrape_home()
    show("MSB - GÜNCEL DUYURULAR", msb_result["duyuru"])
    show("MSB - GÜNCEL TEMİNLER", msb_result["temin"])
    jp = jandarma_personel.scrape()
    show("JANDARMA PERSONEL - GÜNCEL FAALİYETLER", jp["faaliyet"])
    show("JANDARMA PERSONEL - GÜNCEL SONUÇ DUYURULARI", jp["sonuc"])
