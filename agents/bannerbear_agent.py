"""
Tasarım Ajanı - Bannerbear API Entegrasyonu
Şablon bazlı görsel üretir ve Telegram'a gönderir.

Bannerbear API Docs: https://developers.bannerbear.com
"""

import json
import time
import logging
import httpx
import urllib.request
import urllib.error

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


def parse_design_intent_with_gemini(
    user_request: str,
    templates: list[dict],
    gemini_api_key: str,
    gemini_model: str,
) -> dict | None:
    """
    Kullanıcının doğal dil isteğini Gemini ile analiz eder ve Bannerbear parametrelerine çevirir.

    Args:
        user_request: Kullanıcının serbest metin isteği
        templates: Bannerbear şablon listesi (list_templates çıktısı)
        gemini_api_key: Gemini API anahtarı
        gemini_model: Kullanılacak Gemini modeli

    Returns:
        {
            "template_uid": "...",
            "modifications": [{"name": "...", "text": "..."}]
        }
        veya None (tasarım isteği değilse)
    """
    if not templates:
        return None

    # Gemini'ye gönderilecek prompt
    template_info = "\n".join([
        f"- {t['name']} (UID: {t['uid']})\n  Katmanlar: {', '.join([m['name'] for m in t.get('available_modifications', [])])}"
        for t in templates[:3]  # İlk 3 şablon
    ])

    prompt = f"""Kullanıcı bir görsel tasarım istiyor. Aşağıdaki Bannerbear şablonlarından uygun olanı seç ve katman değerlerini belirle.

ŞABLONLAR:
{template_info}

KULLANICI İSTEĞİ:
"{user_request}"

GÖREV:
1. En uygun şablonu seç
2. Katman adlarına göre değerleri belirle
3. JSON formatında döndür

ÇIKTI FORMATI (sadece JSON, başka metin yok):
{{
  "template_uid": "seçilen_şablon_uid",
  "modifications": [
    {{"name": "katman_adı", "text": "değer"}},
    {{"name": "başka_katman", "text": "başka_değer"}}
  ]
}}

Eğer bu bir tasarım isteği değilse, boş {{}} döndür."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        gemini_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()

        # JSON parse et
        # Gemini bazen ```json ... ``` ile sarabilir, temizle
        if gemini_text.startswith("```"):
            gemini_text = gemini_text.split("```")[1]
            if gemini_text.startswith("json"):
                gemini_text = gemini_text[4:].strip()

        parsed = json.loads(gemini_text)
        
        # Boş veya geçersiz JSON ise None döndür
        if not parsed or not parsed.get("template_uid"):
            return None

        return parsed

    except (urllib.error.HTTPError, KeyError, json.JSONDecodeError, IndexError) as exc:
        logger.error("Gemini tasarım parse hatası: %s", exc)
        return None


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
