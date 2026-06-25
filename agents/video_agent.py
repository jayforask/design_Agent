"""
Tasarım Ajanı - Video Düzenleme Modülü
Kullanıcının video düzenleme sorularına özel prompt şablonları sağlar.
"""

VIDEO_TOPICS = {
    "reels": "Instagram Reels / TikTok kısa video",
    "youtube": "YouTube uzun form video",
    "montaj": "Genel video montaj ve kurgu",
    "renk": "Renk düzeltme ve grading",
    "ses": "Ses düzenleme ve mix",
    "efekt": "Görsel efektler ve geçişler",
    "altyazi": "Altyazı ve metin animasyonu",
}

VIDEO_TOOLS = [
    "CapCut", "DaVinci Resolve", "Adobe Premiere Pro",
    "Final Cut Pro", "After Effects", "iMovie", "Kdenlive",
]


def build_video_prompt(user_query: str, skill_level: str = "orta") -> str:
    """
    Video düzenleme sorusu için zenginleştirilmiş prompt oluşturur.

    Args:
        user_query: Kullanıcının sorusu
        skill_level: "başlangıç", "orta" veya "ileri"

    Returns:
        Gemini'ye gönderilecek gelişmiş prompt
    """
    return (
        f"[VIDEO DÜZENLEME MODU]\n"
        f"Kullanıcı seviyesi: {skill_level}\n"
        f"Kullanılabilir araçlar: {', '.join(VIDEO_TOOLS)}\n\n"
        f"Kullanıcı sorusu: {user_query}\n\n"
        "Lütfen şu formatta yanıt ver:\n"
        "1. Hangi aracı kullanması gerektiği\n"
        "2. Adım adım uygulama yöntemi\n"
        "3. Pro ipucu (kısa, pratik)\n"
        "4. Kaçınması gereken yaygın hata\n"
    )


def detect_video_topic(text: str) -> str | None:
    """
    Kullanıcı mesajından video konusunu tespit eder.

    Returns:
        Tespit edilen konu etiketi veya None
    """
    lower = text.lower()
    for key, label in VIDEO_TOPICS.items():
        if key in lower or label.lower() in lower:
            return key
    # Genel video anahtar kelimeleri
    video_keywords = ["video", "düzenle", "kurgu", "montaj", "klip", "sahne", "kare", "fps", "render"]
    if any(kw in lower for kw in video_keywords):
        return "montaj"
    return None
