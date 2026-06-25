"""
Emlak İlan Takip Sistemi — Scraper Katmanı
sahibinden.com, hepsiemlak.com ve emlakjet.com ilanlarını çeker.
Sahibinden (bireysel) filtresi, oda tipi ve konum parametreleri desteklenir.
"""

import logging
import re
import time
import random
from typing import Optional
from urllib.parse import urlencode, quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP istemcisi — Cloudflare bypass için gerçekçi başlıklar
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


def _get_headers(referer: str = "https://www.google.com/") -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _fetch(url: str, referer: str = "https://www.google.com/") -> Optional[str]:
    """HTTP GET isteği gönderir, HTML string veya None döner."""
    try:
        with httpx.Client(
            timeout=20,
            follow_redirects=True,
            http2=False,
        ) as client:
            resp = client.get(url, headers=_get_headers(referer))
            if resp.status_code == 200:
                return resp.text
            logger.warning("HTTP %d: %s", resp.status_code, url)
            return None
    except Exception as exc:
        logger.error("Fetch hatası (%s): %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Yardımcı: fiyat parse
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> Optional[int]:
    """'15.000 TL/ay' → 15000 gibi sayıya çevirir."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_room_type(text: str) -> str:
    """
    Başlık veya oda alanından oda tipini çıkarır.
    '3+1 Daire Konyaaltı' → '3+1'
    """
    match = re.search(r"\b(\d+\+\d+)\b", text or "")
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# sahibinden.com scraper
# ---------------------------------------------------------------------------

def scrape_sahibinden(
    city: str,
    district: str = "",
    listing_type: str = "kiralik",
    owner_only: bool = True,
    page: int = 1,
) -> list[dict]:
    """
    sahibinden.com'dan ilan çeker.

    listing_type: "kiralik" | "satilik"
    owner_only: True → sadece sahibinden (bireysel) ilanlar
    """
    # sahibinden.com kategori kodları: 322 = kiralık daire, 224 = satılık daire
    category = "322" if listing_type == "kiralik" else "224"

    # Konum query parametresi
    location_q = f"{city}+{district}" if district else city

    params = {
        "query": location_q,
        "pagingSize": "20",
        "pagingOffset": str((page - 1) * 20),
    }
    if owner_only:
        params["userType"] = "1"  # 1 = sahibinden

    base_url = f"https://www.sahibinden.com/kategori/{category}"
    url = f"{base_url}?{urlencode(params)}"

    logger.info("sahibinden taranıyor: %s", url)
    html = _fetch(url, referer="https://www.sahibinden.com/")

    if not html:
        logger.warning("sahibinden: HTML alınamadı")
        return []

    soup = BeautifulSoup(html, "lxml")
    listings = []

    # İlan kartları
    rows = soup.select("tr.searchResultsItem") or soup.select("div.classifiedInfo")

    for row in rows:
        try:
            # Başlık
            title_el = row.select_one("td.classifiedTitle a") or row.select_one("h3 a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.sahibinden.com" + href

            # ID
            listing_id = None
            if href:
                m = re.search(r"/(\d{6,})", href)
                if m:
                    listing_id = f"sahibinden_{m.group(1)}"
            if not listing_id:
                continue

            # Fiyat
            price_el = row.select_one("td.searchResultsPriceValue") or row.select_one(".price")
            price = _parse_price(price_el.get_text() if price_el else "")

            # Konum
            loc_el = row.select_one("td.searchResultsLocationValue") or row.select_one(".location")
            location = loc_el.get_text(strip=True) if loc_el else f"{city} / {district}"

            # Satıcı tipi
            seller_tag = row.select_one(".userTypeBadge") or row.select_one("[class*='user-type']")
            seller_text = seller_tag.get_text(strip=True).lower() if seller_tag else ""
            seller_type = "agency" if any(w in seller_text for w in ["emlakçı", "ofis", "kurumsal"]) else "owner"

            # Oda tipi
            room_type = _parse_room_type(title)

            # Görsel
            img_el = row.select_one("img")
            image_url = img_el.get("data-src") or img_el.get("src") if img_el else ""

            listings.append({
                "id": listing_id,
                "platform": "sahibinden",
                "title": title,
                "price": price,
                "currency": "TRY",
                "location": location,
                "district": district,
                "city": city,
                "url": href,
                "image_url": image_url or "",
                "seller_type": seller_type,
                "room_type": room_type,
            })

        except Exception as exc:
            logger.debug("sahibinden ilan parse hatası: %s", exc)
            continue

    logger.info("sahibinden: %d ilan bulundu", len(listings))
    return listings


# ---------------------------------------------------------------------------
# hepsiemlak.com scraper
# ---------------------------------------------------------------------------

def scrape_hepsiemlak(
    city: str,
    district: str = "",
    listing_type: str = "kiralik",
    owner_only: bool = True,
    page: int = 1,
) -> list[dict]:
    """hepsiemlak.com'dan ilan çeker."""
    listing_path = "kiralik-daire" if listing_type == "kiralik" else "satilik-daire"

    location_slug = city.lower().replace("ı", "i").replace("ğ", "g").replace("ş", "s")
    location_slug = location_slug.replace("ç", "c").replace("ö", "o").replace("ü", "u")
    if district:
        dist_slug = district.lower().replace("ı", "i").replace("ğ", "g").replace("ş", "s")
        dist_slug = dist_slug.replace("ç", "c").replace("ö", "o").replace("ü", "u")
        location_part = f"{location_slug}-{dist_slug}"
    else:
        location_part = location_slug

    url = f"https://www.hepsiemlak.com/{location_part}/{listing_path}"
    params = {"page": str(page)}
    if owner_only:
        params["listingFrom"] = "individual"

    full_url = f"{url}?{urlencode(params)}"
    logger.info("hepsiemlak taranıyor: %s", full_url)
    html = _fetch(full_url, referer="https://www.hepsiemlak.com/")

    if not html:
        logger.warning("hepsiemlak: HTML alınamadı")
        return []

    soup = BeautifulSoup(html, "lxml")
    listings = []

    cards = soup.select("li.listing-item") or soup.select("div.listing-card")

    for card in cards:
        try:
            # Link ve ID
            link_el = card.select_one("a[href]")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.hepsiemlak.com" + href

            m = re.search(r"-(\d{6,})(?:\?|$|/)", href)
            listing_id = f"hepsiemlak_{m.group(1)}" if m else None
            if not listing_id:
                # ID'yi başlıktan türet
                title_raw = link_el.get_text(strip=True)[:30]
                listing_id = "hepsiemlak_" + re.sub(r"\W+", "_", title_raw).lower()

            # Başlık
            title_el = card.select_one("h3") or card.select_one(".listing-title") or link_el
            title = title_el.get_text(strip=True) if title_el else ""

            # Fiyat
            price_el = card.select_one(".listing-price") or card.select_one("[class*='price']")
            price = _parse_price(price_el.get_text() if price_el else "")

            # Konum
            loc_el = card.select_one(".listing-location") or card.select_one("[class*='location']")
            location = loc_el.get_text(strip=True) if loc_el else f"{city} / {district}"

            # Satıcı tipi (hepsiemlak genellikle badge gösterir)
            badge = card.select_one("[class*='individual']") or card.select_one("[class*='bireysel']")
            corp = card.select_one("[class*='corporate']") or card.select_one("[class*='kurumsal']")
            if corp:
                seller_type = "agency"
            elif badge:
                seller_type = "owner"
            else:
                seller_type = "unknown"

            # Oda tipi
            room_type = _parse_room_type(title)
            if not room_type:
                room_el = card.select_one("[class*='room']") or card.select_one("[class*='oda']")
                if room_el:
                    room_type = _parse_room_type(room_el.get_text())

            # Görsel
            img_el = card.select_one("img")
            image_url = img_el.get("data-src") or img_el.get("src") if img_el else ""

            listings.append({
                "id": listing_id,
                "platform": "hepsiemlak",
                "title": title,
                "price": price,
                "currency": "TRY",
                "location": location,
                "district": district,
                "city": city,
                "url": href,
                "image_url": image_url or "",
                "seller_type": seller_type,
                "room_type": room_type,
            })

        except Exception as exc:
            logger.debug("hepsiemlak ilan parse hatası: %s", exc)
            continue

    logger.info("hepsiemlak: %d ilan bulundu", len(listings))
    return listings


# ---------------------------------------------------------------------------
# emlakjet.com scraper
# ---------------------------------------------------------------------------

def scrape_emlakjet(
    city: str,
    district: str = "",
    listing_type: str = "kiralik",
    owner_only: bool = True,
    page: int = 1,
) -> list[dict]:
    """emlakjet.com'dan ilan çeker."""
    listing_path = "kiralik-daireler" if listing_type == "kiralik" else "satilik-daireler"

    def _slug(s: str) -> str:
        s = s.lower()
        for old, new in [("ı","i"),("ğ","g"),("ş","s"),("ç","c"),("ö","o"),("ü","u"),(" ","-")]:
            s = s.replace(old, new)
        return re.sub(r"[^a-z0-9\-]", "", s)

    if district:
        location_part = f"{_slug(city)}/{_slug(district)}"
    else:
        location_part = _slug(city)

    # emlakjet'te sahibinden filtresi path üzerinden
    owner_prefix = "sahibinden/" if owner_only else ""
    url = f"https://www.emlakjet.com/{owner_prefix}{listing_path}/{location_part}/"
    params = {"page": str(page)} if page > 1 else {}
    full_url = url + (f"?{urlencode(params)}" if params else "")

    logger.info("emlakjet taranıyor: %s", full_url)
    html = _fetch(full_url, referer="https://www.emlakjet.com/")

    if not html:
        logger.warning("emlakjet: HTML alınamadı")
        return []

    soup = BeautifulSoup(html, "lxml")
    listings = []

    cards = (
        soup.select("div.listing-item-wrapper")
        or soup.select("article.listing")
        or soup.select("[class*='ListingCard']")
    )

    for card in cards:
        try:
            link_el = card.select_one("a[href]")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.emlakjet.com" + href

            m = re.search(r"/(\d{5,})", href)
            listing_id = f"emlakjet_{m.group(1)}" if m else None
            if not listing_id:
                continue

            # Başlık
            title_el = (
                card.select_one("h2") or card.select_one("h3")
                or card.select_one("[class*='title']") or link_el
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Fiyat
            price_el = card.select_one("[class*='price']") or card.select_one("[class*='Price']")
            price = _parse_price(price_el.get_text() if price_el else "")

            # Konum
            loc_el = (
                card.select_one("[class*='location']") or card.select_one("[class*='Location']")
                or card.select_one("[class*='adres']")
            )
            location = loc_el.get_text(strip=True) if loc_el else f"{city} / {district}"

            # Satıcı tipi (emlakjet sahibinden path ile zaten filtreli)
            seller_type = "owner" if owner_only else "unknown"

            # Oda tipi
            room_type = _parse_room_type(title)

            # Görsel
            img_el = card.select_one("img")
            image_url = img_el.get("data-src") or img_el.get("src") if img_el else ""

            listings.append({
                "id": listing_id,
                "platform": "emlakjet",
                "title": title,
                "price": price,
                "currency": "TRY",
                "location": location,
                "district": district,
                "city": city,
                "url": href,
                "image_url": image_url or "",
                "seller_type": seller_type,
                "room_type": room_type,
            })

        except Exception as exc:
            logger.debug("emlakjet ilan parse hatası: %s", exc)
            continue

    logger.info("emlakjet: %d ilan bulundu", len(listings))
    return listings


# ---------------------------------------------------------------------------
# Tüm platformları birleştiren ana fonksiyon
# ---------------------------------------------------------------------------

def scrape_all(
    city: str,
    district: str = "",
    listing_type: str = "kiralik",
    owner_only: bool = True,
) -> list[dict]:
    """
    3 platformu paralel olarak tarar, sonuçları birleştirir.
    Duplicate ID'leri temizler.
    """
    all_listings: list[dict] = []
    seen_ids: set[str] = set()

    scrapers = [
        ("sahibinden", scrape_sahibinden),
        ("hepsiemlak", scrape_hepsiemlak),
        ("emlakjet", scrape_emlakjet),
    ]

    for name, scraper_fn in scrapers:
        try:
            # Scraper çağrıları arasında kısa bekleme (rate-limit önlemi)
            time.sleep(random.uniform(0.5, 1.5))
            results = scraper_fn(
                city=city,
                district=district,
                listing_type=listing_type,
                owner_only=owner_only,
            )
            for listing in results:
                lid = listing.get("id")
                if lid and lid not in seen_ids:
                    seen_ids.add(lid)
                    all_listings.append(listing)
        except Exception as exc:
            logger.error("%s scraper hatası: %s", name, exc)

    logger.info("Toplam %d benzersiz ilan toplandı", len(all_listings))
    return all_listings
