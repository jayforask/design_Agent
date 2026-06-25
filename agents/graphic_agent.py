"""
Tasarım Ajanı - Grafik Tasarım Modülü
Kullanıcının grafik tasarım sorularına özel prompt şablonları sağlar.
"""

GRAPHIC_TOPICS = {
    "logo": "Logo tasarımı",
    "poster": "Poster ve afiş tasarımı",
    "sosyal medya": "Sosyal medya görseli",
    "banner": "Banner ve reklam görseli",
    "tipografi": "Tipografi ve font seçimi",
    "renk paleti": "Renk paleti ve renk teorisi",
    "ui": "UI/UX ve arayüz tasarımı",
    "mockup": "Mockup ve sunum görseli",
    "illüstrasyon": "İllüstrasyon ve ikon tasarımı",
}

GRAPHIC_TOOLS = [
    "Canva", "Adobe Photoshop", "Adobe Illustrator",
    "Figma", "GIMP", "Inkscape", "Affinity Designer", "Procreate",
]

DESIGN_PRINCIPLES = [
    "Hizalama (Alignment)",
    "Tekrar (Repetition)",
    "Kontrast (Contrast)",
    "Yakınlık (Proximity)",
    "Beyaz alan (White space)",
    "Hiyerarşi (Hierarchy)",
]


def build_graphic_prompt(user_query: str, skill_level: str = "orta") -> str:
    """
    Grafik tasarım sorusu için zenginleştirilmiş prompt oluşturur.

    Args:
        user_query: Kullanıcının sorusu
        skill_level: "başlangıç", "orta" veya "ileri"

    Returns:
        Gemini'ye gönderilecek gelişmiş prompt
    """
    return (
        f"[GRAFİK TASARIM MODU]\n"
        f"Kullanıcı seviyesi: {skill_level}\n"
        f"Kullanılabilir araçlar: {', '.join(GRAPHIC_TOOLS)}\n"
        f"Temel tasarım ilkeleri: {', '.join(DESIGN_PRINCIPLES)}\n\n"
        f"Kullanıcı sorusu: {user_query}\n\n"
        "Lütfen şu formatta yanıt ver:\n"
        "1. Önerilen araç ve neden\n"
        "2. Tasarım yaklaşımı (hangi ilkeler uygulanmalı)\n"
        "3. Adım adım uygulama\n"
        "4. Renk / font önerisi (varsa)\n"
        "5. İlham kaynakları veya referans stil\n"
    )


def detect_graphic_topic(text: str) -> str | None:
    """
    Kullanıcı mesajından grafik konusunu tespit eder.

    Returns:
        Tespit edilen konu etiketi veya None
    """
    lower = text.lower()
    for key in GRAPHIC_TOPICS:
        if key in lower:
            return key
    graphic_keywords = [
        "tasarım", "görsel", "grafik", "renk", "font", "yazı tipi",
        "çizim", "illüstrasyon", "ikon", "figma", "photoshop", "canva",
    ]
    if any(kw in lower for kw in graphic_keywords):
        return "poster"
    return None
