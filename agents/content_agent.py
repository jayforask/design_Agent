"""
Tasarım Ajanı - İçerik Üretimi Modülü
Sosyal medya, caption, senaryo, hashtag ve içerik stratejisi konularında
özel prompt şablonları sağlar.
"""

CONTENT_TOPICS = {
    "caption": "Sosyal medya caption/altyazı yazımı",
    "hashtag": "Hashtag stratejisi",
    "senaryo": "Video senaryo ve script yazımı",
    "strateji": "İçerik stratejisi ve planlama",
    "hook": "Dikkat çekici giriş (hook) yazımı",
    "cta": "Call-to-action (harekete geçirici mesaj)",
    "hikaye": "Instagram/WhatsApp hikaye içeriği",
    "reel script": "Reels/TikTok video scripti",
    "bio": "Sosyal medya profil bio yazımı",
}

PLATFORMS = {
    "instagram": {"max_caption": 2200, "hashtag_limit": 30, "tone": "görsel odaklı, etkileşim yüksek"},
    "tiktok": {"max_caption": 2200, "hashtag_limit": 10, "tone": "eğlenceli, trend odaklı"},
    "linkedin": {"max_caption": 3000, "hashtag_limit": 5, "tone": "profesyonel, değer odaklı"},
    "twitter": {"max_caption": 280, "hashtag_limit": 2, "tone": "kısa, net, tartışma açıcı"},
    "youtube": {"max_caption": 5000, "hashtag_limit": 15, "tone": "bilgilendirici, SEO dostu"},
}


def build_content_prompt(user_query: str, platform: str = "instagram", tone: str = "profesyonel") -> str:
    """
    İçerik üretimi sorusu için zenginleştirilmiş prompt oluşturur.

    Args:
        user_query: Kullanıcının sorusu
        platform: Hedef platform (instagram, tiktok, linkedin vb.)
        tone: İçerik tonu

    Returns:
        Gemini'ye gönderilecek gelişmiş prompt
    """
    platform_info = PLATFORMS.get(platform.lower(), PLATFORMS["instagram"])
    return (
        f"[İÇERİK ÜRETİMİ MODU]\n"
        f"Platform: {platform.upper()}\n"
        f"Ton: {tone} ({platform_info['tone']})\n"
        f"Maksimum karakter: {platform_info['max_caption']}\n"
        f"Hashtag limiti: {platform_info['hashtag_limit']}\n\n"
        f"Kullanıcı isteği: {user_query}\n\n"
        "Lütfen şu formatta yanıt ver:\n"
        "1. Ana içerik metni (platform limitine uygun)\n"
        "2. Hook cümlesi (ilk 1-2 satır dikkat çekici olmalı)\n"
        "3. CTA önerisi\n"
        f"4. {platform_info['hashtag_limit']} adet hashtag önerisi\n"
        "5. En iyi paylaşım zamanı önerisi\n"
    )


def build_script_prompt(topic: str, duration_seconds: int = 60, platform: str = "reels") -> str:
    """
    Video senaryo promptu oluşturur.

    Args:
        topic: Video konusu
        duration_seconds: Hedef video süresi (saniye)
        platform: Hedef platform

    Returns:
        Senaryo yazımı için Gemini promptu
    """
    word_count = duration_seconds * 2  # Yaklaşık konuşma hızı: 2 kelime/saniye
    return (
        f"[SENARYO YAZIMI - {platform.upper()}]\n"
        f"Konu: {topic}\n"
        f"Süre: {duration_seconds} saniye\n"
        f"Hedef kelime sayısı: ~{word_count}\n\n"
        "Şu formatta bir video senaryosu yaz:\n"
        "🎬 HOOK (ilk 3 saniye — izleyiciyi yakala)\n"
        "📖 ANA İÇERİK (değer ver, merak uyandır)\n"
        "💡 DEĞER NOKTASI (öğretici veya eğlendirici an)\n"
        "📣 CTA (son 3 saniye — ne yapmalılar?)\n\n"
        "Her bölüm için konuşma metnini ve varsa görsel önerisi ekle.\n"
    )


def detect_content_topic(text: str) -> str | None:
    """
    Kullanıcı mesajından içerik konusunu tespit eder.

    Returns:
        Tespit edilen konu etiketi veya None
    """
    lower = text.lower()
    for key in CONTENT_TOPICS:
        if key in lower:
            return key
    content_keywords = [
        "caption", "metin", "yazı", "içerik", "post", "paylaşım",
        "senaryo", "script", "hashtag", "etiket", "bio", "profil",
    ]
    if any(kw in lower for kw in content_keywords):
        return "caption"
    return None


def detect_platform(text: str) -> str:
    """
    Kullanıcı mesajından hedef platformu tespit eder.
    Bulunamazsa varsayılan olarak 'instagram' döndürür.
    """
    lower = text.lower()
    for platform in PLATFORMS:
        if platform in lower:
            return platform
    return "instagram"
