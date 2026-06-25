# DesignX — Telegram Tasarım Botu

7/24 çalışan, kullanıcıyı tanıyan ve öğrenen kişisel tasarım asistanı.

## Özellikler

- 🎨 Video düzenleme, grafik tasarım ve içerik üretimi desteği
- 🧠 Kullanıcı hafızası — seni tanır, öğrenir, hatırlar
- 🤖 Google Gemini AI ile güçlendirilmiş
- ⚡ Python 3.14 uyumlu (saf HTTP, protobuf bağımlılığı yok)

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `/start` | Botu başlat |
| `/help` | Yardım ve komutlar |
| `/video <soru>` | Video düzenleme modu |
| `/grafik <soru>` | Grafik tasarım modu |
| `/icerik <soru>` | İçerik üretimi modu |
| `/hakkimda` | Botun seni nasıl tanıdığını gör |
| `/reset` | Hafızayı sıfırla |

## Kurulum (Lokal)

```bash
# Bağımlılıkları kur
py -m pip install --only-binary=:all: -r requirements.txt

# .env dosyasını düzenle
copy .env.example .env
# .env içine TELEGRAM_BOT_TOKEN ve GEMINI_API_KEY ekle

# Botu başlat
py bot.py
```

## 7/24 Deploy — Railway (Ücretsiz)

Bilgisayarın kapalı olsa bile bot çalışmaya devam eder.

### Adım 1 — GitHub'a yükle

```bash
git init
git add .
git commit -m "DesignX bot"
git remote add origin https://github.com/KULLANICI_ADI/designx-bot.git
git push -u origin main
```

### Adım 2 — Railway'e bağla

1. [railway.app](https://railway.app) adresine git → **New Project**
2. **Deploy from GitHub repo** seç → repo'yu seç
3. **Variables** sekmesine git, şu değişkenleri ekle:

| Değişken | Değer |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan aldığın token |
| `GEMINI_API_KEY` | Google AI Studio'dan aldığın anahtar |
| `GEMINI_MODEL` | `gemini-2.0-flash` |
| `ALLOWED_USER_IDS` | Telegram kullanıcı ID'n (boş = herkese açık) |

4. **Deploy** butonuna bas — bot otomatik başlar.

### Adım 3 — Worker olarak ayarla

Railway'de **Settings → Start Command** alanına:
```
python bot.py
```

> Railway ücretsiz planda ayda 500 saat çalışma süresi verir. Sürekli çalışma için aylık ~5$ Hobby planı önerilir.

## Alternatif: Render (Ücretsiz, sınırsız)

1. [render.com](https://render.com) → **New Background Worker**
2. GitHub repo'yu bağla
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `python bot.py`
5. Environment variables'ı ekle → **Create**

## Proje Yapısı

```
design_agent/
├── bot.py              # Ana bot — komutlar ve mesaj işleyicileri
├── gemini_client.py    # Gemini REST API istemcisi
├── memory.py           # Kullanıcı hafızası (JSON tabanlı)
├── config.py           # Ortam değişkenleri
├── agents/
│   ├── video_agent.py  # Video düzenleme prompt'ları
│   ├── graphic_agent.py # Grafik tasarım prompt'ları
│   └── content_agent.py # İçerik üretimi prompt'ları
├── requirements.txt
├── Procfile            # Railway/Heroku için
└── railway.toml        # Railway yapılandırması
```

## .env Örneği

```env
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-1.5-flash
ALLOWED_USER_IDS=123456789
```
