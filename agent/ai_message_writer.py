import requests
from agent.telegram_notifier import send_telegram_message

OLLAMA_URL = "http://localhost:11434/api/generate"
QWEN_MODEL = "qwen2.5:0.5b"


def _ask_qwen(prompt: str, max_tokens: int = 200) -> str:
    payload = {
        "model": QWEN_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.7}
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
        if r.status_code == 200:
            return r.json().get("response", "").strip()
        print(f"[QWEN HATA] {r.status_code}")
        return ""
    except requests.exceptions.ConnectionError:
        print("[QWEN HATA] Ollama calismıyor. 'ollama serve' calistirin.")
        return ""
    except Exception as e:
        print(f"[QWEN HATA] {e}")
        return ""


def send_ai_metric_alert(cpu: float, ram: float, ram_used_gb: float, ram_total_gb: float) -> bool:
    if cpu >= 90 or ram >= 95:
        seviye = "KRITIK"
    elif cpu >= 80 or ram >= 90:
        seviye = "UYARI"
    else:
        seviye = "NORMAL"

    prompt = (
        f"You are a system monitoring assistant. "
        f"CPU: {cpu}%, RAM: {ram}% ({ram_used_gb}/{ram_total_gb} GB), Status: {seviye}. "
        f"Write a short comment in Turkish (max 2 sentences). Only write the comment."
    )
    ai_yorum = _ask_qwen(prompt, 100)

    mesaj = f"<b>Sistem Durumu: {seviye}</b>\nCPU: <b>%{cpu}</b>\nRAM: <b>%{ram}</b> ({ram_used_gb}/{ram_total_gb} GB)"
    if ai_yorum:
        mesaj += f"\n\n<i>{ai_yorum}</i>"

    return send_telegram_message(mesaj)


def send_ai_chaos_alert(senaryo: str, sure: int, ram: float) -> bool:
    prompt = (
        f"You are a chaos engineering assistant. "
        f"A chaos test '{senaryo}' has started, duration: {sure} seconds, current RAM: {ram}%. "
        f"Write a short technical warning in Turkish (1-2 sentences). Only write the warning."
    )
    ai_yorum = _ask_qwen(prompt, 120)

    mesaj = f"CHAOS BASLIYOR\nSenaryo: <b>{senaryo}</b>\nSure: <b>{sure}s</b> | RAM: <b>%{ram}</b>"
    if ai_yorum:
        mesaj += f"\n\n<i>{ai_yorum}</i>"

    return send_telegram_message(mesaj)


def send_custom_ai_message(konu: str) -> bool:
    prompt = (
        f"You are an AI assistant for a system monitoring platform. "
        f"Write a short Telegram notification message in Turkish (2-3 sentences) about: {konu}. "
        f"Only write the message, nothing else."
    )
    ai_mesaj = _ask_qwen(prompt, 150)
    if not ai_mesaj:
        ai_mesaj = konu

    mesaj = f"<b>AI Mesaji</b>\n{ai_mesaj}"
    return send_telegram_message(mesaj)


if __name__ == "__main__":
    print("Qwen + Telegram test basliyor...")
    send_custom_ai_message("AI Chaos Platform aktif, sistem izleme devrede.")
    print("Tamam! Telegram kontrol et.")
