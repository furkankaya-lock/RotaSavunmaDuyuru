# Telegram Duyuru Botu (MSB & Jandarma)

Jandarma ve MSB Personel Temin sitelerindeki yeni duyuruları Telegram kanalına
otomatik gönderir. **GitHub Actions** üzerinde ücretsiz çalışır; sunucu gerekmez.

## Takip edilen kaynaklar

| Kaynak | Adres |
|---|---|
| Jandarma Duyurular | https://www.jandarma.gov.tr/duyurular |
| MSB Güncel Duyurular + Güncel Teminler | https://personeltemin.msb.gov.tr/ |

## Mesaj biçimi

```
🚨 Yeni Duyuru!
📌 Başlık: ...
🌐 Site: MSB / Jandarma
🔗 Link: ...
🕒 Tarih: 14.10.2026
```

## Nasıl çalışır

1. `.github/workflows/duyuru-kontrol.yml` her 30 dakikada bir botu **tek tur** çalıştırır.
2. Bot üç kaynağı tarar, daha önce gönderilmemiş duyuruları Telegram'a atar.
3. Gönderilen duyuruların kaydı `state/seen.json` dosyasında tutulur ve her turdan
   sonra repoya otomatik commit edilir (aynı duyuru ikinci kez gitmez).
4. İlk çalıştırmada her kaynaktan sadece **en güncel** duyuru gönderilir, gerisi
   sessizce "görüldü" sayılır.
5. Bir kaynak okunamazsa veya Telegram'a gönderim başarısız olursa çalıştırma
   **kırmızı** biter (GitHub e-posta ile haber verir). Gönderilemeyen duyuru
   bir sonraki turda tekrar denenir.

## Kurulum

1. Repo ayarları → **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_BOT_TOKEN` : BotFather'dan aldığın token
   - `TELEGRAM_CHANNEL_ID` : `@kanaladi` veya `-100...` ile başlayan sayısal id
2. Botun kanalda **yönetici** olduğundan emin ol.
3. **Actions** sekmesi → *Duyuru Kontrol* → **Run workflow** ile ilk turu elle başlat.
4. Logda `Tur bitti: 3 kaynak okundu ...` satırını ve kanalda 3 baseline mesajını gör.

## Bilinmesi gerekenler

- GitHub zamanlayıcısı birkaç dakika gecikebilir.
- Public repoda **60 gün** hiç hareket olmazsa zamanlanmış görev GitHub tarafından
  otomatik kapatılır. Kapanırsa Actions sekmesinden tekrar etkinleştirilir.
- `state/seen.json` herkese açık repoda görünür; içinde sadece duyuru başlık/linkleri vardır.
- Token'ı **asla** koda yazma; sadece Secrets'a ekle.

## Yerelde deneme

```bash
pip install -r requirements.txt
python scrape_test.py                # sadece okur, mesaj atmaz
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHANNEL_ID=@kanaladi \
RUN_ONCE=1 STATE_FILE=state/seen.json python main.py
```

Ortam değişkenleri: `RUN_ONCE`, `STATE_FILE`, `CHECK_INTERVAL_MINUTES` (sürekli mod),
`DATABASE_URL` / `SQLITE_PATH` (sürekli mod için alternatif kayıt), `LOG_LEVEL`.

## Dosya yapısı

```
main.py                 # tur mantığı (tek tur / sürekli mod)
config.py               # ortam değişkenleri
storage.py              # JSON / SQLite / Postgres kayıt
telegram_notifier.py    # Telegram'a gönderim (token maskeleme dahil)
scrape_test.py          # mesaj atmadan okuma testi
scrapers/               # base.py, jandarma.py, msb.py
.github/workflows/      # duyuru-kontrol.yml
state/seen.json         # (otomatik oluşur) görülen duyurular
```
