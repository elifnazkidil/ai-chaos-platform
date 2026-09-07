"""
llm_adapter.py — Ollama / Qwen 2.5 LLM Adapter (Infrastructure Katmanı)

Bu modül, Clean Architecture'ın Infrastructure katmanında yer alır.
Tek sorumluluğu: Ollama API'sine prompt göndermek ve cevabı döndürmek.

Ollama varsayılan olarak http://localhost:11434 adresinde çalışır.
Bu adapter, Ollama çalışmıyorsa sessizce fallback yapar (sistem durmamalı).
"""

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:0.5b"


def generate(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 60) -> str | None:
    """
    Ollama API'sine prompt gönderir ve LLM'in ürettiği metni döndürür.

    Args:
        prompt: LLM'e gönderilecek metin (Türkçe veya İngilizce)
        model: Kullanılacak Ollama modeli (varsayılan: qwen2.5:0.5b)
        timeout: Maksimum bekleme süresi (saniye)

    Returns:
        str: LLM'in ürettiği yanıt metni
        None: Ollama'ya ulaşılamazsa veya hata oluşursa
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False  # Tüm yanıtı tek seferde al (stream=True ise parça parça gelir)
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        return data.get("response") or None

    except requests.exceptions.ConnectionError:
        print("[LLM UYARI] Ollama sunucusuna ulaşılamıyor. 'ollama serve' komutunu çalıştırın.")
        return None
    except requests.exceptions.Timeout:
        print(f"[LLM UYARI] Ollama {timeout} saniye içinde yanıt vermedi.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[LLM HATA] Beklenmeyen hata: {e}")
        return None


if __name__ == "__main__":
    # Hızlı test: Ollama çalışıyorsa basit bir soru sor
    test_prompt = "Sen bir DevOps asistanısın. Şu olayı 2 cümleyle özetle: Sunucuda bellek sızıntısı tespit edildi, chaos_sim prosesi RAM'in %87'sini tüketiyordu, otomatik müdahale ile sonlandırıldı."
    print("Ollama'ya test prompt gönderiliyor...")
    result = generate(test_prompt)
    if result:
        print(f"\n[LLM YANIT]:\n{result}")
    else:
        print("\n[SONUÇ] Ollama'dan yanıt alınamadı.")
