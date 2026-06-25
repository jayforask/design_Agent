"""
Tasarım Ajanı - Konfigürasyon Modülü
Ortam değişkenlerini yükler ve merkezi ayarları sağlar.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Ayarları
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]

# Gemini API Ayarları
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Bannerbear API Ayarları
BANNERBEAR_API_KEY: str = os.getenv("BANNERBEAR_API_KEY", "")
BANNERBEAR_DEFAULT_TEMPLATE: str = os.getenv("BANNERBEAR_DEFAULT_TEMPLATE", "")

# Ajan Kişiliği
AGENT_NAME: str = "DesignX"
AGENT_SYSTEM_PROMPT: str = (
    "Sen uzman bir yaratıcı tasarım ajanısın. Adın DesignX. "
    "Video düzenleme, grafik tasarım ve içerik üretimi konularında derin bilgiye sahipsin. "
    "Kullanıcılara adım adım, pratik ve uygulanabilir tavsiyelerde bulunuyorsun. "
    "Türkçe konuşuyorsun. Yanıtların kısa, net ve aksiyona yönelik olmalı."
)

# Genel Ayarlar
MAX_MESSAGE_LENGTH: int = 4000  # Telegram mesaj limiti 4096 karakter
