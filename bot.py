"""
DesignX Telegram Botu - Ana Giriş Noktası
7/24 çalışır; kullanıcıyı tanır, öğrenir ve tasarım konularında yardımcı olur.

Komutlar:
  /start   - Botu başlat ve karşılama mesajı al
  /help    - Yetenekler ve kullanım kılavuzu
  /reset   - Hafızayı ve sohbet geçmişini sıfırla
  /hakkimda - Botun seni nasıl tanıdığını göster
  /video   - Video düzenleme modu
  /grafik  - Grafik tasarım modu
  /icerik  - İçerik üretimi modu
"""

import logging
import sys
import os

# Proje kökünü Python yoluna ekle
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import config
import gemini_client as gemini
import memory as mem
from agents import video_agent, graphic_agent, content_agent, bannerbear_agent

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("designx.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def is_allowed(user_id: int) -> bool:
    """Kullanıcı erişim kontrolü. ALLOWED_USER_IDS boşsa herkese açık."""
    if not config.ALLOWED_USER_IDS:
        return True
    return user_id in config.ALLOWED_USER_IDS


def get_greeting(user_id: int) -> str:
    """Kullanıcıya özel karşılama mesajı oluşturur."""
    data = mem.load_memory(user_id)
    name = data.get("name")
    if name:
        return f"Tekrar hoş geldin, {name}! 👋"
    return "Merhaba! Ben DesignX 👋"


# ---------------------------------------------------------------------------
# Komut işleyicileri
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot başlangıç komutu — kullanıcıyı karşılar."""
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Bu bota erişim izniniz yok.")
        return

    # Telegram adını hafızaya kaydet (kullanıcı ismini henüz söylemediyse)
    data = mem.load_memory(user.id)
    if not data.get("name") and user.first_name:
        mem.set_user_name(user.id, user.first_name)

    greeting = get_greeting(user.id)
    text = (
        f"{greeting}\n\n"
        "Ben *DesignX* — senin kişisel tasarım ajanın 🎨\n\n"
        "📹 *Video düzenleme* konusunda rehberlik\n"
        "🖌️ *Grafik tasarım* tavsiyeleri\n"
        "✍️ *İçerik üretimi* desteği\n\n"
        "Sana özgün öneriler sunabilmek için seni tanıyacağım ve öğreneceğim.\n\n"
        "Ne üzerine çalışmak istersin? Doğrudan yazabilirsin veya /help komutuna bakabilirsin."
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    logger.info("Kullanıcı başlatıldı: %s (%d)", user.first_name, user.id)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Yardım ve kullanım kılavuzu."""
    text = (
        "🤖 *DesignX — Komutlar ve Kullanım*\n\n"
        "Bana direkt sorun yazabilirsin — konuyu otomatik algılarım.\n\n"
        "*Özel Modlar:*\n"
        "/video `<sorun>` — Video düzenleme\n"
        "/grafik `<sorun>` — Grafik tasarım\n"
        "/icerik `<sorun>` — İçerik üretimi\n\n"
        "*Bannerbear Görsel Üretimi:*\n"
        "/sablonlar — Mevcut şablonları listele\n"
        "/tasarim `<sablon_uid> <katman:değer, ...>` — Görsel oluştur\n\n"
        "*Hafıza Komutları:*\n"
        "/hakkimda — Seni nasıl tanıdığımı göster\n"
        "/reset — Hafızamı ve geçmişi sıfırla\n\n"
        "*Örnek Sorular:*\n"
        "• CapCut'ta renk tonu nasıl değiştirilir?\n"
        "• Instagram için minimalist logo nasıl tasarlanır?\n"
        "• Bir ürün için viral Reels scripti yazar mısın?\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_hakkimda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botun kullanıcı hakkında bildiklerini gösterir."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    data = mem.load_memory(user.id)
    lines = ["🧠 *Seni nasıl tanıdığım:*\n"]

    if data.get("name"):
        lines.append(f"👤 İsim: {data['name']}")
    if data.get("preferences"):
        for k, v in data["preferences"].items():
            lines.append(f"⚙️ {k}: {v}")
    if data.get("learned_facts"):
        lines.append("\n📝 *Öğrendiklerim:*")
        for fact in data["learned_facts"]:
            lines.append(f"  • {fact}")
    if data.get("last_seen"):
        lines.append(f"\n🕒 Son görüşme: {data['last_seen'][:16].replace('T', ' ')} UTC")

    chat_count = len(data.get("chat_history", []))
    lines.append(f"💬 Toplam mesaj geçmişi: {chat_count}")

    if len(lines) == 1:
        lines.append("Henüz seni tanımıyorum. Konuşmaya başla! 🙂")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcının hafızasını ve sohbet geçmişini sıfırlar."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    gemini.reset_memory(user.id)
    await update.message.reply_text(
        "🗑️ Hafızan ve sohbet geçmişin tamamen sıfırlandı. "
        "Seni yeniden tanımak için hazırım! /start ile başlayabilirsin."
    )
    logger.info("Hafıza sıfırlandı: %d", user.id)


async def cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/video <soru> — Video düzenleme modunu zorla aktif et."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "📹 Video düzenleme modundasın!\nSorunuzu yazın: `/video CapCut'ta slow motion nasıl yapılır?`",
            parse_mode="Markdown",
        )
        return

    await update.message.chat.send_action("typing")
    enriched = video_agent.build_video_prompt(
        query,
        skill_level=mem.load_memory(user.id).get("preferences", {}).get("skill_level", "orta"),
    )
    reply = gemini.ask(user.id, enriched)
    await _send_long_message(update, reply)


async def cmd_grafik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/grafik <soru> — Grafik tasarım modunu zorla aktif et."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "🖌️ Grafik tasarım modundasın!\nSorunuzu yazın: `/grafik minimalist logo tasarım ipuçları`",
            parse_mode="Markdown",
        )
        return

    await update.message.chat.send_action("typing")
    enriched = graphic_agent.build_graphic_prompt(
        query,
        skill_level=mem.load_memory(user.id).get("preferences", {}).get("skill_level", "orta"),
    )
    reply = gemini.ask(user.id, enriched)
    await _send_long_message(update, reply)


async def cmd_icerik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/icerik <soru> — İçerik üretimi modunu zorla aktif et."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "✍️ İçerik üretimi modundasın!\nSorunuzu yazın: `/icerik Instagram için ürün tanıtım caption yaz`",
            parse_mode="Markdown",
        )
        return

    await update.message.chat.send_action("typing")
    platform = content_agent.detect_platform(query)
    enriched = content_agent.build_content_prompt(query, platform=platform)
    reply = gemini.ask(user.id, enriched)
    await _send_long_message(update, reply)


# ---------------------------------------------------------------------------
# Bannerbear komut işleyicileri
# ---------------------------------------------------------------------------

async def cmd_sablonlar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/sablonlar — Bannerbear hesabındaki şablonları listeler."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    if not config.BANNERBEAR_API_KEY:
        await update.message.reply_text(
            "⚠️ Bannerbear API anahtarı ayarlanmamış. "
            "BANNERBEAR\\_API\\_KEY ortam değişkenini ekle.",
            parse_mode="Markdown",
        )
        return

    await update.message.chat.send_action("typing")
    try:
        templates = bannerbear_agent.list_templates(config.BANNERBEAR_API_KEY)
        text = bannerbear_agent.format_template_list(templates)
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as exc:
        logger.error("Bannerbear şablon listesi hatası: %s", exc)
        await update.message.reply_text("⚠️ Şablonlar alınamadı. API anahtarını kontrol et.")


async def cmd_tasarim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tasarim <sablon_uid> <baslik: Metin, alt_baslik: Metin> — Görsel oluşturur ve gönderir."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    if not config.BANNERBEAR_API_KEY:
        await update.message.reply_text(
            "⚠️ Bannerbear API anahtarı ayarlanmamış. "
            "BANNERBEAR\\_API\\_KEY ortam değişkenini ekle.",
            parse_mode="Markdown",
        )
        return

    args = context.args
    # İlk arg şablon UID, geri kalanı modifikasyon promptu
    if not args:
        default_uid = config.BANNERBEAR_DEFAULT_TEMPLATE
        if not default_uid:
            await update.message.reply_text(
                "📋 Kullanım:\n"
                "`/tasarim <sablon_uid> baslik: Metin, alt_baslik: Alt Metin`\n\n"
                "Mevcut şablonları görmek için /sablonlar komutunu kullan.",
                parse_mode="Markdown",
            )
            return
        template_uid = default_uid
        prompt = ""
    else:
        template_uid = args[0]
        prompt = " ".join(args[1:])

    await update.message.chat.send_action("upload_photo")
    await update.message.reply_text("🎨 Görsel oluşturuluyor, lütfen bekle...")

    try:
        # Şablon detaylarını al
        template_info = bannerbear_agent.get_template(config.BANNERBEAR_API_KEY, template_uid)

        # Prompttan modifikasyonları oluştur
        if prompt:
            modifications = bannerbear_agent.build_modifications_from_prompt(prompt, template_info)
        else:
            # Modifikasyon yoksa boş liste ile dene (varsayılan şablon değerleri kullanılır)
            modifications = []

        # Görseli oluştur ve URL'yi bekle
        image_url = bannerbear_agent.generate_and_get_url(
            config.BANNERBEAR_API_KEY, template_uid, modifications
        )

        # Telegram'a fotoğraf olarak gönder
        await update.message.reply_photo(
            photo=image_url,
            caption=f"✅ Görsel hazır!\n🔗 [PNG İndir]({image_url})",
            parse_mode="Markdown",
        )
        logger.info("Bannerbear görsel gönderildi: %s → %s", template_uid, user.id)

    except Exception as exc:
        logger.error("Bannerbear görsel oluşturma hatası: %s", exc)
        await update.message.reply_text(
            f"⚠️ Görsel oluşturulamadı:\n`{exc}`\n\n"
            "Şablon UID'sini `/sablonlar` ile kontrol et.",
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# Serbest mesaj işleyicisi (ajan yönlendirmesi)
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Serbest metin mesajlarını alır, konuyu otomatik tespit eder
    ve uygun ajan promptuyla Gemini'ye yönlendirir.
    """
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Bu bota erişim izniniz yok.")
        return

    text = update.message.text.strip()
    if not text:
        return

    await update.message.chat.send_action("typing")

    # Konu tespiti — sırayla dene
    skill = mem.load_memory(user.id).get("preferences", {}).get("skill_level", "orta")

    video_topic = video_agent.detect_video_topic(text)
    graphic_topic = graphic_agent.detect_graphic_topic(text)
    content_topic = content_agent.detect_content_topic(text)

    if video_topic:
        enriched = video_agent.build_video_prompt(text, skill_level=skill)
        mem.learn_fact(user.id, f"Video konularıyla ilgileniyor: {video_topic}")
    elif graphic_topic:
        enriched = graphic_agent.build_graphic_prompt(text, skill_level=skill)
        mem.learn_fact(user.id, f"Grafik konularıyla ilgileniyor: {graphic_topic}")
    elif content_topic:
        platform = content_agent.detect_platform(text)
        enriched = content_agent.build_content_prompt(text, platform=platform)
        mem.learn_fact(user.id, f"İçerik üretimiyle ilgileniyor: {content_topic} / {platform}")
    else:
        # Konu tespit edilemezse direkt sor
        enriched = text

    try:
        reply = gemini.ask(user.id, enriched)
        await _send_long_message(update, reply)
    except Exception as exc:
        logger.error("Gemini hatası: %s", exc)
        await update.message.reply_text(
            "⚠️ Bir hata oluştu. Lütfen tekrar deneyin veya /reset yapın."
        )


# ---------------------------------------------------------------------------
# Yardımcı: uzun mesajları bölerek gönder
# ---------------------------------------------------------------------------

async def _send_long_message(update: Update, text: str) -> None:
    """
    4000 karakterden uzun Gemini yanıtlarını parçalara bölerek gönderir.
    """
    limit = config.MAX_MESSAGE_LENGTH
    if len(text) <= limit:
        await update.message.reply_text(text)
        return
    chunks = [text[i : i + limit] for i in range(0, len(text), limit)]
    for chunk in chunks:
        await update.message.reply_text(chunk)


# ---------------------------------------------------------------------------
# Uygulama başlatma
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    """Bot komutlarını Telegram'a kaydet (menüde görünür)."""
    commands = [
        BotCommand("start", "Botu başlat"),
        BotCommand("help", "Yardım ve komutlar"),
        BotCommand("video", "Video düzenleme sorusu sor"),
        BotCommand("grafik", "Grafik tasarım sorusu sor"),
        BotCommand("icerik", "İçerik üretimi sorusu sor"),
        BotCommand("sablonlar", "Bannerbear şablonlarını listele"),
        BotCommand("tasarim", "Görsel oluştur ve gönder"),
        BotCommand("hakkimda", "Seni nasıl tanıdığımı göster"),
        BotCommand("reset", "Hafızayı sıfırla"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot komutları Telegram'a kaydedildi.")


def main() -> None:
    """Botu başlatır ve polling modunda çalıştırır."""
    import asyncio

    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN ayarlanmamış! .env dosyasını kontrol et.")
        sys.exit(1)

    gemini.init_gemini()
    logger.info("Gemini API başlatıldı. Model: %s", config.GEMINI_MODEL)

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Komut işleyicileri
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("hakkimda", cmd_hakkimda))
    app.add_handler(CommandHandler("video", cmd_video))
    app.add_handler(CommandHandler("grafik", cmd_grafik))
    app.add_handler(CommandHandler("icerik", cmd_icerik))
    app.add_handler(CommandHandler("sablonlar", cmd_sablonlar))
    app.add_handler(CommandHandler("tasarim", cmd_tasarim))

    # Serbest metin mesajları
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("DesignX botu başlatılıyor — polling modu...")

    # Python 3.14 uyumlu event loop başlatma
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
