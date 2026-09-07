"""
Telegram Bot Bildirim Modülü
=============================
Bu modül, sistem metrikleri veya uyarıları Telegram üzerinden
gerçek zamanlı olarak bildirmek için kullanılır.

Kullanım:
    1. Telegram'da @BotFather ile yeni bir bot oluştur
    2. Bot token'ını al
    3. Botunuza bir mesaj gönderin, sonra chat_id'nizi öğrenin
    4. Ortam değişkenlerini ayarlayın:
       set TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
       set TELEGRAM_CHAT_ID=987654321
"""

import os
import requests

# Ortam değişkenlerinden Telegram ayarlarını oku
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def is_telegram_configured():
    """Telegram bot ayarlarının yapılıp yapılmadığını kontrol eder."""
    return TELEGRAM_BOT_TOKEN is not None and TELEGRAM_CHAT_ID is not None

def send_telegram_message(message: str) -> bool:
    """
    Telegram bot üzerinden mesaj gönderir.

    Args:
        message: Gönderilecek mesaj metni

    Returns:
        bool: Mesaj başarıyla gönderildiyse True, aksi halde False
    """
    if not is_telegram_configured():
        print("[TELEGRAM] Bot ayarları yapılmamış. TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ortam değişkenlerini ayarlayın.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"  # HTML formatında mesaj gönderebiliriz (kalın, italik vs.)
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[TELEGRAM OK] Mesaj gönderildi.")
            return True
        else:
            print(f"[TELEGRAM HATA] Yanıt kodu: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("[TELEGRAM HATA] Telegram API'ye bağlanılamadı.")
        return False
    except requests.exceptions.Timeout:
        print("[TELEGRAM HATA] Zaman aşımı (timeout).")
        return False
    except Exception as e:
        print(f"[TELEGRAM HATA] Beklenmeyen hata: {e}")
        return False


def send_metric_alert(cpu_percent: float, ram_percent: float, ram_used_gb: float, ram_total_gb: float):
    """
    Sistem metriklerini Telegram'a bildirim olarak gönderir.
    CPU %80+ veya RAM %90+ ise uyarı emojisi kullanır.

    Args:
        cpu_percent: CPU kullanım yüzdesi
        ram_percent: RAM kullanım yüzdesi
        ram_used_gb: Kullanılan RAM (GB)
        ram_total_gb: Toplam RAM (GB)
    """
    # Uyarı seviyesini belirle
    if cpu_percent >= 90 or ram_percent >= 95:
        emoji = "🚨"
        level = "KRİTİK"
    elif cpu_percent >= 80 or ram_percent >= 90:
        emoji = "⚠️"
        level = "UYARI"
    else:
        emoji = "✅"
        level = "NORMAL"

    message = (
        f"{emoji} <b>Sistem Durumu: {level}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 CPU: <b>%{cpu_percent}</b>\n"
        f"🧠 RAM: <b>%{ram_percent}</b> ({ram_used_gb}/{ram_total_gb} GB)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 Agent: agent-01"
    )

    return send_telegram_message(message)


def send_chaos_alert(scenario_name: str, duration: int, current_ram_percent: float):
    """
    Chaos senaryosu başladığında veya bellek sızıntısı tespit edildiğinde
    Telegram'a uyarı gönderir.

    Args:
        scenario_name: Çalışan senaryo adı (örn: "Yavaş Sızıntı")
        duration: Senaryonun süresi (saniye)
        current_ram_percent: Şu anki RAM yüzdesi
    """
    message = (
        f"🔥 <b>CHAOS SENARYOSU BAŞLADI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Senaryo: <b>{scenario_name}</b>\n"
        f"⏱ Süre: <b>{duration} saniye</b>\n"
        f"🧠 Şu anki RAM: <b>%{current_ram_percent}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Dikkat: Bellek sızıntısı simüle ediliyor!"
    )

    return send_telegram_message(message)


# Doğrudan çalıştırılırsa test mesajı gönder
if __name__ == "__main__":
    print("Telegram Bot Test Ediliyor...")
    print(f"  Token ayarlı mı: {'Evet' if TELEGRAM_BOT_TOKEN else 'Hayır'}")
    print(f"  Chat ID ayarlı mı: {'Evet' if TELEGRAM_CHAT_ID else 'Hayır'}")

    if is_telegram_configured():
        send_telegram_message("🤖 AI Chaos Platform - Telegram botu aktif!")
        send_metric_alert(cpu_percent=45.2, ram_percent=67.8, ram_used_gb=5.43, ram_total_gb=8.0)
    else:
        print("\nTelegram ayarları yapılmamış. Şu komutları çalıştırın:")
        print('  set TELEGRAM_BOT_TOKEN=botfather_dan_aldiginiz_token')
        print('  set TELEGRAM_CHAT_ID=sizin_chat_id_niz')
        print("\nChat ID öğrenmek için:")
        print("  1. Botunuza Telegram'dan bir mesaj gönderin")
        print("  2. Tarayıcıda şu URL'yi açın:")
        print("     https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("  3. JSON yanıtında 'chat' -> 'id' değerini bulun")
