"""
Tasarım Ajanı - Gemini API İstemcisi (REST tabanlı)
google-generativeai SDK yerine doğrudan HTTP kullanır → Python 3.14 uyumlu.
"""

import urllib.request
import urllib.error
import json

from config import GEMINI_API_KEY, GEMINI_MODEL, AGENT_SYSTEM_PROMPT
import memory as mem

# Gemini REST API endpoint — v1beta sistem promptunu destekler
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def init_gemini() -> None:
    """API anahtarını doğrular."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY ortam değişkeni ayarlanmamış!")


def _call_gemini(prompt: str) -> str:
    """
    Gemini REST API'sine istek gönderir ve metin yanıtı döndürür.

    Args:
        prompt: Gönderilecek tam prompt metni

    Returns:
        Gemini'nin ürettiği metin
    """
    url = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{AGENT_SYSTEM_PROMPT}\n\n{prompt}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"Gemini API hatası {e.code}: {error_body}") from e

    # Yanıtı çıkar
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Beklenmedik Gemini yanıt formatı: {result}") from e


def ask(user_id: int, user_text: str) -> str:
    """
    Kullanıcının mesajını Gemini'ye gönderir; hafıza bağlamını ekler ve yanıtı döndürür.

    Args:
        user_id: Telegram kullanıcı ID'si
        user_text: Kullanıcının mesajı

    Returns:
        Gemini'nin metin yanıtı
    """
    context_summary = mem.get_context_summary(user_id)
    recent_history = mem.get_recent_history_text(user_id, last_n=8)

    parts = []
    if context_summary:
        parts.append(context_summary)
    if recent_history:
        parts.append(f"[SON SOHBET GEÇMİŞİ]\n{recent_history}\n[/SON SOHBET GEÇMİŞİ]")
    parts.append(f"Kullanıcı: {user_text}")

    full_prompt = "\n\n".join(parts)

    reply = _call_gemini(full_prompt)

    # Hafızaya kaydet
    mem.add_to_history(user_id, "user", user_text)
    mem.add_to_history(user_id, "model", reply)

    # İsimden öğrenme
    _try_learn_name(user_id, user_text)

    return reply


def _try_learn_name(user_id: int, text: str) -> None:
    """Mesajdan kullanıcı adını çıkarmaya çalışır ve hafızaya kaydeder."""
    lower = text.lower()
    triggers = ["benim adım ", "adım ", "ismim ", "bana ", "ben "]
    for trigger in triggers:
        if trigger in lower:
            idx = lower.index(trigger) + len(trigger)
            candidate = text[idx:].split()[0].strip(".,!?")
            if len(candidate) >= 2 and candidate.isalpha():
                mem.set_user_name(user_id, candidate.capitalize())
            break


def reset_memory(user_id: int) -> None:
    """Kullanıcının tüm hafızasını ve sohbet geçmişini temizler."""
    mem.clear_memory(user_id)
