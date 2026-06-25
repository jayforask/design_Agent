"""
Emlak İlan Takip Sistemi — Alert Katmanı
Watchlist'leri tarar, yeni ilanları filtreler ve Telegram bildirimi gönderir.
"""

import logging
from typing import TYPE_CHECKING

from agents import scraper_agent, listing_store

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bildirim formatı
# ---------------------------------------------------------------------------

_PLATFORM_ICONS = {
    "sahibinden": "🏷️",
    "hepsiemlak": "🏘️",
    "emlakjet": "✈️",
}


def format_alert(listing: dict, watchlist_label: str = "") -> str:
    """
    Tek bir ilanı Telegram mesaj formatına çevirir.

    Örnek çıktı:
        🏷️ *Yeni İlan — sahibinden.com*
        👤 Sahibinden (Bireysel)

        📍 Antalya / Konyaaltı
        🛏 3+1 | 💰 15.000 ₺/ay
        📝 3+1 Daire Fırsat Konyaaltı

        🔔 Takip: Konyaaltı Kiralık
        🔗 İlanı Gör
    """
    platform = listing.get("platform", "")
    icon = _PLATFORM_ICONS.get(platform, "🏠")
    platform_label = f"{platform}.com" if platform else "İlan"

    seller = listing.get("seller_type", "")
    seller_line = "👤 *Sahibinden (Bireysel)*" if seller == "owner" else ("🏢 Emlakçı" if seller == "agency" else "")

    city = listing.get("city", "")
    district = listing.get("district", "")
    location = listing.get("location", "") or (f"{city} / {district}" if district else city)

    room = listing.get("room_type", "")
    price = listing.get("price")
    price_str = f"{price:,} ₺".replace(",", ".") if price else "Fiyat belirtilmemiş"

    title = listing.get("title", "İsimsiz İlan")
    url = listing.get("url", "")

    lines = [
        f"{icon} *Yeni İlan — {platform_label}*",
    ]
    if seller_line:
        lines.append(seller_line)
    lines.append("")
    lines.append(f"📍 {location}")
    detail = []
    if room:
        detail.append(f"🛏 {room}")
    detail.append(f"💰 {price_str}")
    lines.append(" | ".join(detail))
    lines.append(f"📝 {title}")
    if watchlist_label:
        lines.append("")
        lines.append(f"🔔 _Takip: {watchlist_label}_")
    if url:
        lines.append("")
        lines.append(f"[🔗 İlanı Gör]({url})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tarama döngüsü
# ---------------------------------------------------------------------------

async def run_scrape_cycle(app: "Application") -> None:
    """
    Tüm aktif watchlist'leri tarar, yeni ilanları tespit eder
    ve ilgili kullanıcılara Telegram bildirimi gönderir.

    APScheduler tarafından saatte bir çağrılır.
    """
    logger.info("Tarama döngüsü başladı...")

    watchlists = listing_store.list_all_active_watchlists()
    if not watchlists:
        logger.info("Aktif watchlist yok, tarama atlandı.")
        return

    total_new = 0

    for wl in watchlists:
        user_id = wl["user_id"]
        try:
            # Watchlist parametreleriyle scrape et
            raw_listings = scraper_agent.scrape_all(
                city=wl.get("city", ""),
                district=wl.get("district", ""),
                listing_type=wl.get("listing_type", "kiralik"),
                owner_only=bool(wl.get("owner_only", True)),
            )

            new_count = 0
            for listing in raw_listings:
                # Filtre eşleştir
                if not listing_store.match_listing(wl, listing):
                    continue

                # Yeni mi?
                is_new = listing_store.save_listing(listing)
                if not is_new:
                    continue

                # Bildirim gönder
                msg = format_alert(listing, watchlist_label=wl.get("label", ""))
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode="Markdown",
                        disable_web_page_preview=False,
                    )
                    listing_store.mark_notified(listing["id"])
                    new_count += 1
                    total_new += 1
                    logger.info(
                        "Bildirim gönderildi: user=%d, ilan=%s", user_id, listing["id"]
                    )
                except Exception as send_exc:
                    logger.error(
                        "Bildirim gönderilemedi (user=%d): %s", user_id, send_exc
                    )

            if new_count == 0:
                logger.info(
                    "Watchlist #%d ('%s'): yeni ilan yok", wl["id"], wl.get("label")
                )

        except Exception as exc:
            logger.error(
                "Watchlist #%d tarama hatası: %s", wl.get("id", "?"), exc
            )
            # Kullanıcıya scraper hatası bildirimi (opsiyonel, sadece ciddi hatalarda)
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"⚠️ _{wl.get('label', 'Takip')}_ için tarama sırasında hata oluştu.\n"
                        f"`{str(exc)[:200]}`"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    logger.info("Tarama döngüsü tamamlandı. Toplam %d yeni ilan bildirildi.", total_new)
