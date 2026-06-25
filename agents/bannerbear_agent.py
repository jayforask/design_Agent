"""
Tasarım Ajanı - Bannerbear API Entegrasyonu
Şablon bazlı görsel üretir ve Telegram'a gönderir.

Bannerbear API Docs: https://developers.bannerbear.com
"""

import json
import time
import logging
import httpx

logger = logging.getLogger(__name__)

# Bannerbear REST API base URL
_BASE_URL = "https://api.bannerbear.com/v2"

# Varsayılan bekleme ve yeniden deneme ayarları
_POLL_INTERVAL = 3   # saniye
_MAX_RETRIES = 15    # maksimum bekleme döngüsü (~45 saniye)

# API istekleri için header'lar — Accept-Encoding yok, httpx kendi decompress eder
_DEFAULT_HEADERS = {
    "User-Agent": "DesignX-TelegramBot/1.0",
    "Accept": "application/json",
}


def _build_headers(api_key: str) -> dict:
    headers = dict(_DEFAULT_HEADERS)
    headers["Authorization"] = f"Bearer {api_key}"
    headers["Content-Type"] = "application/json"
    return headers


def list_templates(api_key: str) -> list[dict]:
    """
    Hesaptaki tüm şablonları listeler.

    Returns:
        Şablon listesi (uid, name, width, height içerir)
    """
    url = f"{_BASE_URL}/templates"
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        resp = client.get(url, headers=_build_headers(api_key))
        if resp.status_code != 200:
            raise RuntimeError(
                f"Bannerbear şablon listesi hatası {resp.status_code}: {resp.text}"
            )
        return resp.json()


def get_template(api_key: str, template_uid: str) -> dict:
    """
    Belirli bir şablonun detaylarını (available_modifications) getirir.
    """
    url = f"{_BASE_URL}/templates/{template_uid}"
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        resp = client.get(url, headers=_build_headers(api_key))
        if resp.status_code != 200:
            raise RuntimeError(
                f"Bannerbear şablon detay hatası {resp.status_code}: {resp.text}"
            )
        return resp.json()


def create_image(
    api_key: str,
    template_uid: str,
    modifications: list[dict],
    webhook_url: str | None = None,
) -> dict:
    """
    Bannerbear'a görsel oluşturma isteği gönderir.

    Args:
        api_key: Bannerbear API anahtarı
        template_uid: Kullanılacak şablon UID'si
        modifications: [{"name": "layer_adı", "text": "...", "color": "#hex"}, ...]
        webhook_url: Tamamlandığında bildirim gönderilecek URL (opsiyonel)

    Returns:
        Bannerbear image nesnesi (uid, status, image_url_png içerir)
    """
    url = f"{_BASE_URL}/images"
    payload: dict = {
        "template": template_uid,
        "modifications": modifications,
    }
    if webhook_url:
        payload["webhook_url"] = webhook_url

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.post(url, headers=_build_headers(api_key), json=payload)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Bannerbear görsel oluşturma hatası {resp.status_code}: {resp.text}"
            )
        return resp.json()


def wait_for_image(api_key: str, image_uid: str) -> str:
    """
    Görsel hazır olana kadar polling yapar ve PNG URL'sini döndürür.

    Args:
        api_key: Bannerbear API anahtarı
        image_uid: create_image'dan dönen UID

    Returns:
        Hazır görsel URL'si (image_url_png)

    Raises:
        RuntimeError: Görsel belirli sürede tamamlanamazsa
    """
    url = f"{_BASE_URL}/images/{image_uid}"

    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for attempt in range(_MAX_RETRIES):
            resp = client.get(url, headers=_build_headers(api_key))
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Bannerbear görsel sorgulama hatası {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            status = data.get("status", "pending")
            logger.info(
                "Bannerbear görsel durumu [%s]: %s (deneme %d)",
                image_uid, status, attempt + 1
            )

            if status == "completed":
                image_url = data.get("image_url_png") or data.get("image_url")
                if not image_url:
                    raise RuntimeError(
                        "Bannerbear görsel tamamlandı fakat URL bulunamadı."
                    )
                return image_url

            if status == "failed":
                raise RuntimeError(f"Bannerbear görsel oluşturma başarısız: {data}")

            time.sleep(_POLL_INTERVAL)

    raise RuntimeError(
        f"Bannerbear görsel {_MAX_RETRIES * _POLL_INTERVAL} saniye içinde tamamlanamadı."
    )


def generate_and_get_url(
    api_key: str,
    template_uid: str,
    modifications: list[dict],
) -> str:
    """
    Görsel oluştur ve hazır URL'yi döndür (create + poll birleşimi).

    Args:
        api_key: Bannerbear API anahtarı
        template_uid: Şablon UID'si
        modifications: Katman değişiklik listesi

    Returns:
        PNG görsel URL'si
    """
    result = create_image(api_key, template_uid, modifications)
    image_uid = result["uid"]
    status = result.get("status", "pending")

    # Senkron modda hemen hazırsa doğrudan döndür
    if status == "completed":
        url = result.get("image_url_png") or result.get("image_url")
        if url:
            return url

    return wait_for_image(api_key, image_uid)


def build_modifications_from_prompt(user_prompt: str, template_info: dict) -> list[dict]:
    """
    Kullanıcının serbest metin promptunu şablon katmanlarına dönüştürür.

    İki mod:
    1. 'katman_adı: değer' formatında → eşleştirme ile
    2. Serbest metin → tüm metin ilk text katmanına yazılır

    Args:
        user_prompt: Kullanıcının tasarım isteği
        template_info: get_template() çıktısı

    Returns:
        modifications listesi (en az 1 eleman)
    """
    available = template_info.get("available_modifications", [])
    modifications = []

    # Kullanıcı promptundan anahtar:değer çiftlerini parse et
    user_data = _parse_user_prompt(user_prompt)

    if user_data:
        # 'anahtar: değer' formatı — katman adıyla eşleştir
        for layer in available:
            layer_name = layer.get("name", "")
            layer_name_lower = layer_name.lower()

            matched_value = None
            for key, value in user_data.items():
                # Tam eşleşme veya kısmi eşleşme
                if key == layer_name_lower or key in layer_name_lower or layer_name_lower in key:
                    matched_value = value
                    break

            if matched_value:
                mod = {"name": layer_name, "text": matched_value}
                modifications.append(mod)

    if not modifications and available:
        # Eşleşme olmadıysa — tüm metni ilk text katmanına yaz
        first_layer = available[0]
        modifications.append({
            "name": first_layer.get("name", ""),
            "text": user_prompt.strip() if user_prompt.strip() else "DesignX",
        })

    return modifications


def _parse_user_prompt(prompt: str) -> dict[str, str]:
    """
    'başlık: Yaz İndirimi, alt yazı: %50 indirim' gibi promptları
    {'başlık': 'Yaz İndirimi', 'alt yazı': '%50 indirim'} dict'ine çevirir.
    """
    result = {}
    for part in prompt.replace("\n", ",").split(","):
        if ":" in part:
            key, _, value = part.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key and value:
                result[key] = value
    return result


def format_template_list(templates: list[dict]) -> str:
    """
    Şablon listesini Telegram'da okunabilir formata çevirir.
    Katman adlarını da gösterir.
    """
    if not templates:
        return "Hesabında henüz şablon yok. Bannerbear panelinden şablon ekle."

    lines = ["📋 *Mevcut Bannerbear Şablonları:*\n"]
    for i, t in enumerate(templates[:10], 1):
        name = t.get("name", "İsimsiz")
        uid = t.get("uid", "?")
        width = t.get("width", "?")
        height = t.get("height", "?")
        lines.append(f"{i}. *{name}*")
        lines.append(f"   UID: `{uid}` | {width}×{height}px")

        # Katman adlarını listele
        mods = t.get("available_modifications", [])
        if mods:
            layer_names = [m.get("name", "?") for m in mods]
            lines.append(f"   Katmanlar: `{'`, `'.join(layer_names)}`")
        lines.append("")

    if len(templates) > 10:
        lines.append(f"_...ve {len(templates) - 10} şablon daha_")

    lines.append("💡 Kullanım: `/tasarim katman\\_adı: Değer`")
    return "\n".join(lines)
