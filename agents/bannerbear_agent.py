"""
Tasarım Ajanı - Bannerbear API Entegrasyonu
Şablon bazlı görsel üretir ve Telegram'a gönderir.

Bannerbear API Docs: https://developers.bannerbear.com
"""

import urllib.request
import urllib.error
import json
import time
import logging

logger = logging.getLogger(__name__)

# Bannerbear REST API base URL
_BASE_URL = "https://api.bannerbear.com/v2"

# Varsayılan bekleme ve yeniden deneme ayarları
_POLL_INTERVAL = 3   # saniye
_MAX_RETRIES = 15    # maksimum bekleme döngüsü (~45 saniye)


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def list_templates(api_key: str) -> list[dict]:
    """
    Hesaptaki tüm şablonları listeler.

    Returns:
        Şablon listesi (uid, name, width, height içerir)
    """
    url = f"{_BASE_URL}/templates"
    req = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Bannerbear şablon listesi hatası {e.code}: {e.read().decode()}") from e


def get_template(api_key: str, template_uid: str) -> dict:
    """
    Belirli bir şablonun detaylarını (available_modifications) getirir.
    """
    url = f"{_BASE_URL}/templates/{template_uid}"
    req = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Bannerbear şablon detay hatası {e.code}: {e.read().decode()}") from e


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

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(api_key), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Bannerbear görsel oluşturma hatası {e.code}: {e.read().decode()}") from e


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
    req = urllib.request.Request(url, headers=_headers(api_key), method="GET")

    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Bannerbear görsel sorgulama hatası {e.code}: {e.read().decode()}") from e

        status = data.get("status", "pending")
        logger.info("Bannerbear görsel durumu [%s]: %s (deneme %d)", image_uid, status, attempt + 1)

        if status == "completed":
            image_url = data.get("image_url_png") or data.get("image_url")
            if not image_url:
                raise RuntimeError("Bannerbear görsel tamamlandı fakat URL bulunamadı.")
            return image_url

        if status == "failed":
            raise RuntimeError(f"Bannerbear görsel oluşturma başarısız: {data}")

        time.sleep(_POLL_INTERVAL)

    raise RuntimeError(f"Bannerbear görsel {_MAX_RETRIES * _POLL_INTERVAL} saniye içinde tamamlanamadı.")


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
    Şablondaki available_modifications listesini kullanarak akıllıca eşleştirir.

    Args:
        user_prompt: Kullanıcının tasarım isteği (örn: "başlık: Yaz İndirimi, renk: mavi")
        template_info: get_template() çıktısı

    Returns:
        modifications listesi
    """
    available = template_info.get("available_modifications", [])
    modifications = []

    # Kullanıcı promptundan anahtar:değer çiftlerini parse et
    user_data = _parse_user_prompt(user_prompt)

    for layer in available:
        name = layer.get("name", "").lower()
        layer_type = layer.get("type", "")  # text, image vb.

        if layer_type == "text":
            # Eşleşen anahtar kelime ara
            matched_value = None
            for key, value in user_data.items():
                if key in name or name in key:
                    matched_value = value
                    break

            # Eşleşme yoksa varsayılan veya boş bırak
            if matched_value:
                modifications.append({
                    "name": layer["name"],
                    "text": matched_value,
                })

    return modifications


def _parse_user_prompt(prompt: str) -> dict[str, str]:
    """
    'başlık: Yaz İndirimi, alt yazı: %50 indirim' gibi promptları
    {'başlık': 'Yaz İndirimi', 'alt yazı': '%50 indirim'} dict'ine çevirir.
    """
    result = {}
    # Virgül veya yeni satırla ayrılmış 'anahtar: değer' çiftleri
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
    """
    if not templates:
        return "Hesabında henüz şablon yok. Bannerbear panelinden şablon ekle."

    lines = ["📋 *Mevcut Bannerbear Şablonları:*\n"]
    for i, t in enumerate(templates[:10], 1):  # İlk 10'u göster
        name = t.get("name", "İsimsiz")
        uid = t.get("uid", "?")
        width = t.get("width", "?")
        height = t.get("height", "?")
        lines.append(f"{i}. *{name}*\n   UID: `{uid}` | {width}×{height}px")

    if len(templates) > 10:
        lines.append(f"\n_...ve {len(templates) - 10} şablon daha_")

    return "\n".join(lines)
