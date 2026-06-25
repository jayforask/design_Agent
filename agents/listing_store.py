"""
Emlak İlan Takip Sistemi — Veri Katmanı
SQLite ile ilan depolama, watchlist yönetimi ve filtre eşleştirme.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).parent.parent / "memory_store"
_DB_PATH = _DB_DIR / "listings.db"


# ---------------------------------------------------------------------------
# Veritabanı başlatma
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Veritabanı tablolarını oluşturur (yoksa)."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id          TEXT PRIMARY KEY,
                platform    TEXT NOT NULL,
                title       TEXT,
                price       INTEGER,
                currency    TEXT DEFAULT 'TRY',
                location    TEXT,
                district    TEXT,
                city        TEXT,
                url         TEXT,
                image_url   TEXT,
                seller_type TEXT DEFAULT 'unknown',
                room_type   TEXT,
                first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP,
                notified    INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                label        TEXT NOT NULL,
                city         TEXT,
                district     TEXT,
                listing_type TEXT DEFAULT 'kiralik',
                room_types   TEXT,          -- JSON: ["2+1","3+1"]
                min_price    INTEGER,
                max_price    INTEGER,
                owner_only   INTEGER DEFAULT 1,
                active       INTEGER DEFAULT 1,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_listings_platform
            ON listings(platform)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlists_user
            ON watchlists(user_id)
        """)
        conn.commit()
    logger.info("Listing DB başlatıldı: %s", _DB_PATH)


# ---------------------------------------------------------------------------
# İlan kaydetme
# ---------------------------------------------------------------------------

def save_listing(listing: dict) -> bool:
    """
    İlanı kaydeder. Yeni bir ilansa True, zaten mevcutsa False döner.

    listing dict anahtarları:
        id, platform, title, price, currency, location, district, city,
        url, image_url, seller_type, room_type
    """
    init_db()
    listing_id = listing.get("id")
    if not listing_id:
        return False

    with sqlite3.connect(_DB_PATH) as conn:
        existing = conn.execute(
            "SELECT id FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()

        if existing:
            return False  # Zaten var

        conn.execute("""
            INSERT INTO listings
                (id, platform, title, price, currency, location, district, city,
                 url, image_url, seller_type, room_type, first_seen, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            listing_id,
            listing.get("platform", ""),
            listing.get("title", ""),
            listing.get("price"),
            listing.get("currency", "TRY"),
            listing.get("location", ""),
            listing.get("district", ""),
            listing.get("city", ""),
            listing.get("url", ""),
            listing.get("image_url", ""),
            listing.get("seller_type", "unknown"),
            listing.get("room_type", ""),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()

    logger.debug("Yeni ilan kaydedildi: %s", listing_id)
    return True


def mark_notified(listing_id: str) -> None:
    """İlanı bildirildi olarak işaretle."""
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            "UPDATE listings SET notified = 1 WHERE id = ?", (listing_id,)
        )
        conn.commit()


def get_listing(listing_id: str) -> Optional[dict]:
    """Belirli bir ilanı döndürür."""
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Watchlist yönetimi
# ---------------------------------------------------------------------------

def add_watchlist(
    user_id: int,
    label: str,
    city: str,
    district: str = "",
    listing_type: str = "kiralik",
    room_types: Optional[list] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    owner_only: bool = True,
) -> int:
    """Yeni watchlist ekler, oluşturulan ID'yi döndürür."""
    init_db()
    room_types_json = json.dumps(room_types or [], ensure_ascii=False)
    with sqlite3.connect(_DB_PATH) as conn:
        cursor = conn.execute("""
            INSERT INTO watchlists
                (user_id, label, city, district, listing_type,
                 room_types, min_price, max_price, owner_only)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, label, city, district, listing_type,
            room_types_json, min_price, max_price, 1 if owner_only else 0,
        ))
        conn.commit()
        return cursor.lastrowid


def list_watchlists(user_id: int) -> list[dict]:
    """Kullanıcının aktif watchlist'lerini döndürür."""
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM watchlists
            WHERE user_id = ? AND active = 1
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["room_types"] = json.loads(d["room_types"] or "[]")
        result.append(d)
    return result


def list_all_active_watchlists() -> list[dict]:
    """Tüm kullanıcıların aktif watchlist'lerini döndürür (scheduler için)."""
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM watchlists WHERE active = 1
        """).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["room_types"] = json.loads(d["room_types"] or "[]")
        result.append(d)
    return result


def delete_watchlist(user_id: int, watchlist_id: int) -> bool:
    """Watchlist'i pasif yapar. Başarılıysa True döner."""
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        cursor = conn.execute("""
            UPDATE watchlists SET active = 0
            WHERE id = ? AND user_id = ?
        """, (watchlist_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def format_watchlist_list(watchlists: list[dict]) -> str:
    """Watchlist listesini Telegram formatında döndürür."""
    if not watchlists:
        return (
            "📭 Aktif takibiniz yok.\n\n"
            "/takip komutuyla yeni ilan takibi başlatın."
        )

    lines = ["🔔 *Aktif Takipleriniz:*\n"]
    for wl in watchlists:
        rooms = ", ".join(wl["room_types"]) if wl["room_types"] else "Tümü"
        owner_tag = "👤 Sahibinden" if wl["owner_only"] else "🏢 Hepsi"
        price_range = ""
        if wl.get("min_price") or wl.get("max_price"):
            lo = f"{wl['min_price']:,}" if wl.get("min_price") else "0"
            hi = f"{wl['max_price']:,}" if wl.get("max_price") else "∞"
            price_range = f" | {lo}–{hi} ₺"

        lines.append(f"*#{wl['id']} — {wl['label']}*")
        lines.append(
            f"📍 {wl['city']}"
            + (f" / {wl['district']}" if wl.get("district") else "")
        )
        lines.append(
            f"🏠 {wl['listing_type'].capitalize()} | "
            f"🛏 {rooms} | {owner_tag}{price_range}"
        )
        lines.append(f"_Sil: /takipsil {wl['id']}_")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Filtre eşleştirme
# ---------------------------------------------------------------------------

def match_listing(watchlist: dict, listing: dict) -> bool:
    """
    Bir ilanın bir watchlist filtresine uyup uymadığını kontrol eder.
    True döner → bildirim gönder.
    """
    # Şehir kontrolü (zorunlu)
    wl_city = (watchlist.get("city") or "").lower().strip()
    lst_city = (listing.get("city") or listing.get("location") or "").lower()
    if wl_city and wl_city not in lst_city:
        return False

    # İlçe kontrolü (opsiyonel)
    wl_district = (watchlist.get("district") or "").lower().strip()
    lst_location = (listing.get("location") or "").lower()
    if wl_district and wl_district not in lst_location:
        return False

    # Kiralık/Satılık kontrolü
    wl_type = (watchlist.get("listing_type") or "kiralik").lower()
    lst_title = (listing.get("title") or "").lower()
    lst_url = (listing.get("url") or "").lower()
    type_hint = lst_title + " " + lst_url
    if wl_type == "kiralik" and "satilik" in type_hint:
        return False
    if wl_type == "satilik" and "kiralik" in type_hint:
        return False

    # Oda sayısı kontrolü (opsiyonel)
    wl_rooms = watchlist.get("room_types") or []
    if wl_rooms:
        lst_room = (listing.get("room_type") or "").strip()
        if lst_room and lst_room not in wl_rooms:
            return False

    # Fiyat aralığı kontrolü (opsiyonel)
    lst_price = listing.get("price")
    if lst_price is not None:
        if watchlist.get("min_price") and lst_price < watchlist["min_price"]:
            return False
        if watchlist.get("max_price") and lst_price > watchlist["max_price"]:
            return False

    # Sahibinden filtresi
    if watchlist.get("owner_only"):
        if listing.get("seller_type") == "agency":
            return False

    return True
