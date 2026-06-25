"""
Tasarım Ajanı - Kalıcı Hafıza Modülü
Kullanıcıya ait bilgileri JSON dosyasına kaydeder ve yükler.
Bot, kullanıcıyı tanır, tercihlerini ve geçmiş bağlamı hatırlar.
"""

import json
import os
from datetime import datetime
from typing import Any

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory_store")
os.makedirs(MEMORY_DIR, exist_ok=True)


def _memory_path(user_id: int) -> str:
    """Kullanıcıya ait hafıza dosyasının yolunu döndürür."""
    return os.path.join(MEMORY_DIR, f"user_{user_id}.json")


def load_memory(user_id: int) -> dict[str, Any]:
    """
    Kullanıcının kalıcı hafızasını diskten yükler.
    Dosya yoksa boş bir hafıza yapısı döndürür.
    """
    path = _memory_path(user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "user_id": user_id,
        "name": None,
        "preferences": {},
        "learned_facts": [],
        "chat_history": [],
        "created_at": datetime.utcnow().isoformat(),
        "last_seen": None,
    }


def save_memory(user_id: int, data: dict[str, Any]) -> None:
    """Kullanıcının hafızasını diske kaydeder."""
    data["last_seen"] = datetime.utcnow().isoformat()
    path = _memory_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_to_history(user_id: int, role: str, text: str) -> None:
    """
    Sohbet geçmişine yeni bir mesaj ekler.
    Son 50 mesajı saklar (hafıza sınırı).

    Args:
        user_id: Telegram kullanıcı ID'si
        role: "user" veya "model"
        text: Mesaj içeriği
    """
    data = load_memory(user_id)
    data["chat_history"].append({
        "role": role,
        "text": text,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Son 50 mesajı tut
    data["chat_history"] = data["chat_history"][-50:]
    save_memory(user_id, data)


def learn_fact(user_id: int, fact: str) -> None:
    """
    Kullanıcı hakkında öğrenilen bir bilgiyi kaydeder.
    Örnek: isim, tercih ettiği araçlar, çalışma alanı vb.

    Args:
        user_id: Telegram kullanıcı ID'si
        fact: Öğrenilen bilgi
    """
    data = load_memory(user_id)
    if fact not in data["learned_facts"]:
        data["learned_facts"].append(fact)
        # Son 30 fact'i tut
        data["learned_facts"] = data["learned_facts"][-30:]
        save_memory(user_id, data)


def set_user_name(user_id: int, name: str) -> None:
    """Kullanıcının adını hafızaya kaydeder."""
    data = load_memory(user_id)
    data["name"] = name
    save_memory(user_id, data)


def set_preference(user_id: int, key: str, value: Any) -> None:
    """
    Kullanıcı tercihini kaydeder.
    Örnek: preferred_tool, design_style, skill_level vb.
    """
    data = load_memory(user_id)
    data["preferences"][key] = value
    save_memory(user_id, data)


def get_context_summary(user_id: int) -> str:
    """
    Gemini'ye gönderilecek kullanıcı bağlam özetini oluşturur.
    Bu özet, botun kullanıcıyı tanımasını sağlar.

    Returns:
        Kullanıcı bağlamını açıklayan metin
    """
    data = load_memory(user_id)
    lines = []

    if data.get("name"):
        lines.append(f"Kullanıcının adı: {data['name']}")

    if data.get("preferences"):
        prefs = ", ".join(f"{k}={v}" for k, v in data["preferences"].items())
        lines.append(f"Kullanıcı tercihleri: {prefs}")

    if data.get("learned_facts"):
        facts = "; ".join(data["learned_facts"])
        lines.append(f"Kullanıcı hakkında öğrenilen bilgiler: {facts}")

    if data.get("last_seen"):
        lines.append(f"Son görülme: {data['last_seen']}")

    if not lines:
        return ""

    return (
        "[KULLANICI BAĞLAMI - Bu bilgileri kullanarak kullanıcıyı tanı ve kişiselleştirilmiş yanıt ver]\n"
        + "\n".join(lines)
        + "\n[/KULLANICI BAĞLAMI]"
    )


def get_recent_history_text(user_id: int, last_n: int = 10) -> str:
    """
    Son N mesajı metin formatında döndürür.
    Gemini'ye bağlam olarak eklenebilir.
    """
    data = load_memory(user_id)
    history = data.get("chat_history", [])[-last_n:]
    if not history:
        return ""
    lines = []
    for msg in history:
        role_label = "Sen" if msg["role"] == "user" else "DesignX"
        lines.append(f"{role_label}: {msg['text']}")
    return "\n".join(lines)


def clear_memory(user_id: int) -> None:
    """Kullanıcının tüm hafızasını sıfırlar (sohbet geçmişi dahil)."""
    path = _memory_path(user_id)
    if os.path.exists(path):
        os.remove(path)
