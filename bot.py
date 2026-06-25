"""
DesignX Telegram Botu - Ana Giriş Noktası
7/24 çalışır; kullanıcıyı tanır, öğrenir ve tasarım konularında yardımcı olur.

Komutlar:
  /start    - Botu başlat ve karşılama mesajı al
  /help     - Yetenekler ve kullanım kılavuzu
  /reset    - Hafızayı ve sohbet geçmişini sıfırla
  /hakkimda - Botun seni nasıl tanıdığını göster
  /video    - Video düzenleme modu
  /grafik   - Grafik tasarım modu
  /icerik   - İçerik üretimi modu
  /tablolar - Yüklü tabloları listele
  /tablosil - Tablo sil
  /takip    - Yeni emlak ilanı takibi başlat
  /takipler - Aktif takipleri listele
  /takipsil - Takibi durdur
"""

import logging
import sys
import os

# Proje kökünü Python yoluna ekle
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import config
import gemini_client as gemini
import memory as mem
from agents import (
    video_agent, graphic_agent, content_agent,
    bannerbear_agent, table_agent,
    listing_store, alert_agent,
)

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
    """/tasarim [sablon_uid] <metin veya baslik: Deger, alt_baslik: Deger> — Görsel oluşturur."""
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

    # İlk argüman Bannerbear UID formatına benziyorsa (harf+rakam, 10+ karakter) UID olarak al
    # Benzimiyorsa tüm metin prompt, şablon listeden otomatik seç
    def _looks_like_uid(s: str) -> bool:
        return len(s) >= 10 and s.isalnum()

    if not args:
        # Hiç argüman yok — şablon listesi göster
        try:
            templates = bannerbear_agent.list_templates(config.BANNERBEAR_API_KEY)
            if not templates:
                await update.message.reply_text(
                    "📋 Bannerbear hesabında şablon yok.\n"
                    "https://app.bannerbear.com adresinden şablon oluştur."
                )
                return
            # İlk şablonu varsayılan olarak kullan
            template_uid = templates[0]["uid"]
            prompt = ""
            await update.message.reply_text(
                f"💡 Şablon seçilmedi. Varsayılan şablon kullanılıyor: *{templates[0].get('name', template_uid)}*\n"
                f"Örnek: `/tasarim baslik: Merhaba, alt\\_baslik: Dünya`",
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Bannerbear şablon listesi hatası: %s", exc)
            await update.message.reply_text("⚠️ Şablon listesi alınamadı.")
            return
    elif _looks_like_uid(args[0]):
        # İlk arg UID gibi görünüyor
        template_uid = args[0]
        prompt = " ".join(args[1:])
    else:
        # İlk arg UID değil — tüm metni prompt yap, ilk şablonu kullan
        prompt = " ".join(args)
        try:
            templates = bannerbear_agent.list_templates(config.BANNERBEAR_API_KEY)
            if not templates:
                await update.message.reply_text(
                    "📋 Bannerbear hesabında şablon yok.\n"
                    "https://app.bannerbear.com adresinden şablon oluştur."
                )
                return
            template_uid = templates[0]["uid"]
        except Exception as exc:
            logger.error("Bannerbear şablon listesi hatası: %s", exc)
            await update.message.reply_text("⚠️ Şablon listesi alınamadı.")
            return

    await update.message.chat.send_action("upload_photo")
    await update.message.reply_text("🎨 Görsel oluşturuluyor, lütfen bekle...")

    try:
        # Şablon detaylarını al
        template_info = bannerbear_agent.get_template(config.BANNERBEAR_API_KEY, template_uid)

        # Prompttan modifikasyonları oluştur
        if prompt:
            modifications = bannerbear_agent.build_modifications_from_prompt(prompt, template_info)
        else:
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
            f"⚠️ Görsel oluşturulamadı:\n`{str(exc)[:300]}`\n\n"
            "Şablon UID'sini `/sablonlar` ile kontrol et.",
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# Tablo analizi komut işleyicileri
# ---------------------------------------------------------------------------

async def cmd_tablolar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tablolar — Kullanıcının yüklediği tabloları listeler."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    await update.message.chat.send_action("typing")
    tables = table_agent.list_user_tables(user.id)
    text = table_agent.format_table_list(tables)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_tablosil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tablosil <tablo_id> — Belirtilen tabloyu siler."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    if not context.args:
        # Argüman verilmemişse mevcut tabloları listele
        tables = table_agent.list_user_tables(user.id)
        if not tables:
            await update.message.reply_text(
                "📭 Silinecek tablo yok.\n\nÖnce bir Excel veya CSV dosyası gönderin."
            )
            return
        text = table_agent.format_table_list(tables)
        await update.message.reply_text(
            f"Silmek istediğiniz tablonun ID'sini yazın:\n\n{text}\n"
            f"Örnek: `/tablosil {tables[0]['table_name']}`",
            parse_mode="Markdown",
        )
        return

    table_name = context.args[0]
    success = table_agent.delete_table(user.id, table_name)

    if success:
        await update.message.reply_text(
            f"🗑️ Tablo silindi: `{table_name}`", parse_mode="Markdown"
        )
        logger.info("Tablo silindi: %s (user: %d)", table_name, user.id)
    else:
        await update.message.reply_text(
            f"⚠️ Tablo bulunamadı: `{table_name}`\n\n"
            "Mevcut tablolarınız için /tablolar komutunu kullanın.",
            parse_mode="Markdown",
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Excel/CSV dosyalarını alır, parse eder ve SQLite'a kaydeder."""
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Bu bota erişim izniniz yok.")
        return

    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or "dosya"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in table_agent.SUPPORTED_EXTENSIONS:
        # Desteklenmeyen format — sessizce geç (fotoğraf/video gibi diğer dosyalar)
        return

    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"📂 *{filename}* alındı, işleniyor...", parse_mode="Markdown"
    )

    try:
        tg_file = await doc.get_file()
        file_bytes = await tg_file.download_as_bytearray()
        result = table_agent.parse_and_save(user.id, bytes(file_bytes), filename)
        await update.message.reply_text(result["summary"], parse_mode="Markdown")
        logger.info(
            "Tablo yüklendi: %s → %s (%d satır, user: %d)",
            filename, result["table_name"], result["row_count"], user.id,
        )
    except Exception as exc:
        logger.error("Tablo yükleme hatası: %s", exc)
        await update.message.reply_text(
            f"⚠️ Dosya işlenemedi: `{str(exc)[:300]}`", parse_mode="Markdown"
        )


# ---------------------------------------------------------------------------
# Emlak ilan takip komut işleyicileri (ConversationHandler)
# ---------------------------------------------------------------------------

# ConversationHandler adım sabitleri
(
    TAKIP_SEHIR,
    TAKIP_TIP,
    TAKIP_ODA,
    TAKIP_FIYAT,
    TAKIP_SAHIP,
    TAKIP_ONAYLA,
) = range(6)


async def cmd_takip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/takip — İlan takibi başlatır, şehir/ilçe sorar."""
    user = update.effective_user
    if not is_allowed(user.id):
        return ConversationHandler.END

    context.user_data["takip"] = {}
    await update.message.reply_text(
        "🏠 *Yeni İlan Takibi*\n\n"
        "Takip etmek istediğin şehir ve ilçeyi yaz.\n"
        "Örnek: `Antalya Konyaaltı` veya sadece `Antalya`\n\n"
        "_İptal için /iptal_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TAKIP_SEHIR


async def takip_sehir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Şehir/ilçe alır, ilan tipi sorar."""
    text = update.message.text.strip()
    parts = text.split(None, 1)
    context.user_data["takip"]["city"] = parts[0]
    context.user_data["takip"]["district"] = parts[1] if len(parts) > 1 else ""

    keyboard = [["🔑 Kiralık", "💰 Satılık"]]
    await update.message.reply_text(
        f"📍 *{text}* seçildi.\n\nNe arıyorsun?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return TAKIP_TIP


async def takip_tip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kiralık/Satılık alır, oda sayısı sorar."""
    text = update.message.text.strip().lower()
    listing_type = "satilik" if "satılık" in text or "satilik" in text else "kiralik"
    context.user_data["takip"]["listing_type"] = listing_type

    keyboard = [["1+1", "2+1", "3+1"], ["4+1", "5+1", "🔀 Tümü"]]
    await update.message.reply_text(
        "🛏 Oda sayısı? (Birden fazla seçmek için virgülle yaz: `2+1, 3+1`)\n"
        "Ya da düğmelerden birini seç:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return TAKIP_ODA


async def takip_oda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Oda sayısı alır, fiyat aralığı sorar."""
    text = update.message.text.strip()
    if "tüm" in text.lower() or text == "🔀 Tümü":
        room_types = []
    else:
        # "2+1, 3+1" veya "3+1" formatını parse et
        room_types = [r.strip() for r in text.replace("🛏", "").split(",") if r.strip()]
        # Geçersiz formatları temizle (sadece N+N formatı)
        import re as _re
        room_types = [r for r in room_types if _re.match(r"^\d+\+\d+$", r)]

    context.user_data["takip"]["room_types"] = room_types

    keyboard = [["⏭ Atla"]]
    await update.message.reply_text(
        "💰 Fiyat aralığı? (min-max, örn: `5000-15000`)\n"
        "Filtrelemek istemiyorsan *Atla*'ya bas.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return TAKIP_FIYAT


async def takip_fiyat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fiyat aralığı alır, sahibinden filtresi sorar."""
    text = update.message.text.strip()
    min_price = max_price = None

    if "atla" not in text.lower() and text != "⏭ Atla":
        import re as _re
        m = _re.search(r"(\d+)\D+(\d+)", text)
        if m:
            min_price = int(m.group(1))
            max_price = int(m.group(2))
        else:
            single = _re.sub(r"\D", "", text)
            if single:
                max_price = int(single)

    context.user_data["takip"]["min_price"] = min_price
    context.user_data["takip"]["max_price"] = max_price

    keyboard = [["👤 Sadece Sahibinden", "🏢 Hepsi (Emlakçı dahil)"]]
    await update.message.reply_text(
        "👤 İlanlar kimden gelsin?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return TAKIP_SAHIP


async def takip_sahip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sahibinden filtresi alır, özet gösterir."""
    text = update.message.text.strip().lower()
    owner_only = "emlakçı" not in text and "hepsi" not in text

    td = context.user_data["takip"]
    td["owner_only"] = owner_only

    city = td.get("city", "")
    district = td.get("district", "")
    listing_type = td.get("listing_type", "kiralik")
    room_types = td.get("room_types", [])
    min_p = td.get("min_price")
    max_p = td.get("max_price")

    rooms_str = ", ".join(room_types) if room_types else "Tümü"
    price_str = ""
    if min_p or max_p:
        lo = f"{min_p:,}" if min_p else "0"
        hi = f"{max_p:,}" if max_p else "∞"
        price_str = f"\n💰 Fiyat: {lo} – {hi} ₺"
    owner_str = "👤 Sadece sahibinden" if owner_only else "🏢 Emlakçı dahil"

    label = f"{city}{(' / ' + district) if district else ''} {listing_type.capitalize()}"
    td["label"] = label

    summary = (
        f"📋 *Takip Özeti*\n\n"
        f"📍 {city}{(' / ' + district) if district else ''}\n"
        f"🏠 {listing_type.capitalize()}\n"
        f"🛏 Oda: {rooms_str}{price_str}\n"
        f"{owner_str}\n\n"
        f"Her saat sahibinden.com, hepsiemlak.com ve emlakjet.com taranacak."
    )

    keyboard = [["✅ Onayla", "❌ İptal"]]
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return TAKIP_ONAYLA


async def takip_onayla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Onay alır, watchlist kaydeder."""
    text = update.message.text.strip().lower()
    if "iptal" in text or "❌" in text:
        await update.message.reply_text(
            "❌ Takip iptal edildi.",
            reply_markup=ReplyKeyboardRemove(),
        )
        context.user_data.pop("takip", None)
        return ConversationHandler.END

    user = update.effective_user
    td = context.user_data.get("takip", {})

    wl_id = listing_store.add_watchlist(
        user_id=user.id,
        label=td.get("label", "Takip"),
        city=td.get("city", ""),
        district=td.get("district", ""),
        listing_type=td.get("listing_type", "kiralik"),
        room_types=td.get("room_types", []),
        min_price=td.get("min_price"),
        max_price=td.get("max_price"),
        owner_only=td.get("owner_only", True),
    )

    await update.message.reply_text(
        f"✅ Takip #{wl_id} oluşturuldu!\n\n"
        "Her saat kontrol edilecek, yeni ilan geldiğinde seni haberdar edeceğim 🔔\n\n"
        "/takipler ile tüm takiplerine bakabilirsin.",
        reply_markup=ReplyKeyboardRemove(),
    )
    logger.info("Watchlist oluşturuldu: #%d (user: %d)", wl_id, user.id)
    context.user_data.pop("takip", None)
    return ConversationHandler.END


async def cmd_takip_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/iptal — Aktif konuşmayı iptal eder."""
    context.user_data.pop("takip", None)
    await update.message.reply_text(
        "❌ İptal edildi.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def cmd_takipler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/takipler — Aktif takipleri listeler."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    watchlists = listing_store.list_watchlists(user.id)
    text = listing_store.format_watchlist_list(watchlists)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_takipsil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/takipsil <id> — Belirtilen takibi durdurur."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    if not context.args:
        watchlists = listing_store.list_watchlists(user.id)
        if not watchlists:
            await update.message.reply_text(
                "📭 Aktif takibiniz yok."
            )
            return
        text = listing_store.format_watchlist_list(watchlists)
        await update.message.reply_text(
            f"Silmek istediğiniz takibin ID'sini yazın:\n\n{text}\n"
            f"Örnek: `/takipsil {watchlists[0]['id']}`",
            parse_mode="Markdown",
        )
        return

    try:
        wl_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Geçersiz ID. Örnek: `/takipsil 3`", parse_mode="Markdown")
        return

    success = listing_store.delete_watchlist(user.id, wl_id)
    if success:
        await update.message.reply_text(f"🗑️ Takip #{wl_id} durduruldu.")
        logger.info("Watchlist silindi: #%d (user: %d)", wl_id, user.id)
    else:
        await update.message.reply_text(
            f"⚠️ #{wl_id} numaralı takip bulunamadı.\n/takipler ile listeni kontrol et."
        )


# ---------------------------------------------------------------------------
# Serbest mesaj işleyicisi (ajan yönlendirmesi)
# ---------------------------------------------------------------------------

# Tasarım isteği anahtar kelimeleri
_DESIGN_KEYWORDS = [
    "görsel yap", "görsel oluştur", "tasarım yap", "banner yap", "banner oluştur",
    "afiş yap", "poster yap", "resim yap", "resim oluştur", "görseli oluştur",
    "görsel hazırla", "tasarla", "tasarım oluştur", "görsel çiz",
    "görsel istiyorum", "tasarım istiyorum", "bana bir görsel",
    "instagram görseli", "sosyal medya görseli", "reklam görseli",
]


def _detect_design_request(text: str) -> bool:
    """Kullanıcı metninin görsel tasarım isteği olup olmadığını tespit eder."""
    lower = text.lower()
    return any(kw in lower for kw in _DESIGN_KEYWORDS)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Serbest metin mesajlarını alır, konuyu otomatik tespit eder
    ve uygun ajan promptuyla Gemini'ye yönlendirir.

    Tasarım isteği tespit edilirse Bannerbear ile görsel üretir.
    """
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Bu bota erişim izniniz yok.")
        return

    text = update.message.text.strip()
    if not text:
        return

    await update.message.chat.send_action("typing")

    # ── Tasarım isteği tespiti (Bannerbear entegrasyonu) ──────────────────────
    if config.BANNERBEAR_API_KEY and _detect_design_request(text):
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("🎨 Tasarım isteğin alındı, görsel oluşturuluyor...")
        try:
            templates = bannerbear_agent.list_templates(config.BANNERBEAR_API_KEY)
            if templates:
                design = bannerbear_agent.parse_design_intent_with_gemini(
                    user_request=text,
                    templates=templates,
                    gemini_api_key=config.GEMINI_API_KEY,
                    gemini_model=config.GEMINI_MODEL,
                )
                if design and design.get("template_uid"):
                    image_url = bannerbear_agent.generate_and_get_url(
                        config.BANNERBEAR_API_KEY,
                        design["template_uid"],
                        design.get("modifications", []),
                    )
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=f"✅ Görsel hazır!\n🔗 [PNG İndir]({image_url})",
                        parse_mode="Markdown",
                    )
                    mem.learn_fact(user.id, f"Görsel tasarım isteğinde bulundu: {text[:60]}")
                    return
        except Exception as exc:
            logger.error("Bannerbear akıllı tasarım hatası: %s", exc)
            await update.message.reply_text(
                f"⚠️ Görsel oluşturulamadı: `{str(exc)[:200]}`",
                parse_mode="Markdown",
            )
            return

    # ── Tablo sorusu tespiti (table_agent entegrasyonu) ───────────────────────
    if table_agent.detect_table_question(text):
        latest = table_agent.get_latest_table(user.id)
        if latest:
            await update.message.chat.send_action("typing")
            result = table_agent.query_with_gemini(
                user.id, text, config.GEMINI_API_KEY, config.GEMINI_MODEL
            )
            await _send_long_message(update, result["answer"])
            if result.get("chart_path"):
                try:
                    with open(result["chart_path"], "rb") as img:
                        await update.message.reply_photo(
                            photo=img,
                            caption=f"📊 {result.get('chart_type', 'Grafik').capitalize()} grafiği",
                        )
                    import os as _os
                    _os.unlink(result["chart_path"])
                except Exception as exc:
                    logger.error("Grafik gönderilemedi: %s", exc)
            return

    # ── Normal ajan yönlendirmesi ─────────────────────────────────────────────
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
    """Bot komutlarını Telegram'a kaydet ve scheduler başlat."""
    # Veritabanları başlat
    table_agent.init_db()
    listing_store.init_db()
    logger.info("Veritabanları başlatıldı.")

    # APScheduler — saatlik emlak taraması
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")
        scheduler.add_job(
            alert_agent.run_scrape_cycle,
            trigger="interval",
            hours=1,
            args=[app],
            id="emlak_tarama",
            name="Emlak İlan Taraması",
            misfire_grace_time=300,
        )
        scheduler.start()
        logger.info("APScheduler başlatıldı — saatlik emlak taraması aktif.")
    except Exception as exc:
        logger.error("APScheduler başlatılamadı: %s", exc)

    commands = [
        BotCommand("start", "Botu başlat"),
        BotCommand("help", "Yardım ve komutlar"),
        BotCommand("video", "Video düzenleme sorusu sor"),
        BotCommand("grafik", "Grafik tasarım sorusu sor"),
        BotCommand("icerik", "İçerik üretimi sorusu sor"),
        BotCommand("sablonlar", "Bannerbear şablonlarını listele"),
        BotCommand("tasarim", "Görsel oluştur ve gönder"),
        BotCommand("tablolar", "Yüklü tabloları listele"),
        BotCommand("tablosil", "Tablo sil"),
        BotCommand("takip", "Yeni emlak ilanı takibi başlat"),
        BotCommand("takipler", "Aktif takipleri listele"),
        BotCommand("takipsil", "Takibi durdur"),
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

    # ConversationHandler — /takip adım adım kurulum
    takip_conv = ConversationHandler(
        entry_points=[CommandHandler("takip", cmd_takip_start)],
        states={
            TAKIP_SEHIR:  [MessageHandler(filters.TEXT & ~filters.COMMAND, takip_sehir)],
            TAKIP_TIP:    [MessageHandler(filters.TEXT & ~filters.COMMAND, takip_tip)],
            TAKIP_ODA:    [MessageHandler(filters.TEXT & ~filters.COMMAND, takip_oda)],
            TAKIP_FIYAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, takip_fiyat)],
            TAKIP_SAHIP:  [MessageHandler(filters.TEXT & ~filters.COMMAND, takip_sahip)],
            TAKIP_ONAYLA: [MessageHandler(filters.TEXT & ~filters.COMMAND, takip_onayla)],
        },
        fallbacks=[CommandHandler("iptal", cmd_takip_iptal)],
        allow_reentry=True,
    )
    app.add_handler(takip_conv)

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
    app.add_handler(CommandHandler("tablolar", cmd_tablolar))
    app.add_handler(CommandHandler("tablosil", cmd_tablosil))
    app.add_handler(CommandHandler("takipler", cmd_takipler))
    app.add_handler(CommandHandler("takipsil", cmd_takipsil))

    # Dosya (Excel/CSV) mesajları
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

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
