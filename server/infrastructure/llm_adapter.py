"""
llm_adapter.py — Ollama / Qwen 2.5 LLM Adapter (Infrastructure Katmanı)

Bu modül, Clean Architecture'ın Infrastructure katmanında yer alır.
Tek sorumluluğu: Ollama API'sine prompt göndermek ve cevabı döndürmek.

Ollama varsayılan olarak http://localhost:11434 adresinde çalışır.
Bu adapter, Ollama çalışmıyorsa sessizce fallback yapar (sistem durmamalı).

İKİ FONKSİYON:
  generate()            → Serbest metin döndürür (str | None)
  generate_structured() → Pydantic schema ile doğrulanmış LLMDecisionOutput döndürür

Structured Output Akışı:
  1. Prompt'a JSON talimatı ekle (prompt engineering)
  2. Ollama'ya gönder (generate() ile)
  3. Markdown code block'ları soy (```json ... ```)
  4. json.loads() ile parse et
  5. Pydantic ile validate et
  6. Disk/Net dummy ise confidence_score'u 0.6'ya kapt
  7. Her hatada → fallback_output() döndür (sistem durmamalı)
"""

import json
import re
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:0.5b"

# Prompt'a eklenen JSON talimatı — LLM'i yapılandırılmış cevap vermeye yönlendirir.
# "IMPORTANT" ile başlıyoruz çünkü küçük modeller talimatı gözden kaçırabilir.
_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Your response MUST be a single valid JSON object only. "
    "No extra text before or after. No markdown. No explanation. "
    "Use exactly these fields:\n"
    '{"risk_level": "low" or "medium" or "high" or "critical", '
    '"prediction_summary": "1-2 sentence Turkish summary", '
    '"recommended_action": "what to do next in Turkish", '
    '"confidence_score": 0.0 to 1.0}\n'
    "Example: {\"risk_level\": \"high\", \"prediction_summary\": \"RAM kritik seviyede.\", "
    "\"recommended_action\": \"Servisi yeniden başlat.\", \"confidence_score\": 0.85}"
)

# Dummy feature varken confidence'a uygulanan üst sınır.
# Disk veya Network verisi sahte (sabit 10.0) ise modelin güveni sınırlıdır.
# Gerçek veri gelince bu sınır kaldırılır (has_full_features=True).
_CONFIDENCE_CAP_DUMMY = 0.6


def generate(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 60, max_tokens: int = 200) -> str | None:
    """
    Ollama API'sine prompt gönderir ve LLM'in ürettiği metni döndürür.

    Args:
        prompt: LLM'e gönderilecek metin (Türkçe veya İngilizce)
        model: Kullanılacak Ollama modeli (varsayılan: qwen2.5:0.5b)
        timeout: Maksimum bekleme süresi (saniye)
        max_tokens: Maksimum üretilecek token sayısı

    Returns:
        str: LLM'in ürettiği yanıt metni
        None: Ollama'ya ulaşılamazsa veya hata oluşursa
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,  # Tüm yanıtı tek seferde al (stream=True ise parça parça gelir)
        "options": {"num_predict": max_tokens, "temperature": 0.7}
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


def generate_structured(
    prompt: str,
    action: str = "MONITOR",
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
    max_tokens: int = 300,
    has_full_features: bool = False,
) -> "LLMDecisionOutput":
    """
    Ollama'ya prompt gönderir ve cevabı LLMDecisionOutput schema'sına göre
    parse edip döndürür.

    generate() ile farkı:
      - Cevap serbest metin değil, Pydantic ile doğrulanmış nesne.
      - Her hata durumunda fallback_output() döner → sistem DURMAZ.

    Args:
        prompt      : LLM'e gönderilecek içerik (JSON talimatı otomatik eklenir)
        action      : Kural motorunun verdiği aksiyon kodu (fallback için gerekli)
        model       : Ollama model adı
        timeout     : Zaman aşımı (saniye)
        max_tokens  : Üretilecek maksimum token sayısı
        has_full_features: True → disk/net gerçek veri, confidence cap kaldırılır
                           False → disk/net dummy, confidence max 0.6 ile kapatılır

    Returns:
        LLMDecisionOutput: Başarılı parse ve validasyon
        fallback_output(action): Herhangi bir hata durumunda

    Hata Akışı:
        Ollama bağlantı hatası → fallback
        Timeout               → fallback
        JSON parse hatası      → fallback (LLM markdown ekledi vs.)
        Pydantic ValidationError → fallback (eksik/yanlış alan)
    """
    # Import burada — döngüsel bağımlılığı önlemek için (domain → infra değil)
    from server.domain.llm_schema import LLMDecisionOutput, fallback_output

    # ─── Adım 1: JSON talimatını prompt'a ekle ────────────────
    full_prompt = prompt + _JSON_INSTRUCTION

    # ─── Adım 2: Ollama'ya gönder ─────────────────────────────
    raw = generate(full_prompt, model=model, timeout=timeout, max_tokens=max_tokens)

    if raw is None:
        # Ollama çalışmıyor veya timeout — sessizce fallback
        return fallback_output(action)

    # ─── Adım 3: Markdown code block soy ─────────────────────
    # LLM bazen ```json\n{...}\n``` formatında döner — bunu temizleriz
    cleaned = _strip_markdown_json(raw)

    # ─── Adım 4: JSON parse ───────────────────────────────────
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"[LLM UYARI] JSON parse başarısız. Ham yanıt: {raw[:120]!r}")
        return fallback_output(action)

    # ─── Adım 5: Pydantic validasyon ─────────────────────────
    try:
        output = LLMDecisionOutput(**data)
    except Exception as e:
        # risk_level yanlış, confidence dışı değer, boş alan vs.
        print(f"[LLM UYARI] Schema doğrulama hatası: {e}")
        return fallback_output(action)

    # ─── Adım 6: Confidence cap (dummy feature var ise) ───────
    # Disk ve Network verisi dummy (sabit 10.0) iken YSA'nın gördüğü tablo
    # eksiktir. Bu durumda LLM'in ürettiği yüksek güven skoru yanıltıcı olur.
    # has_full_features=True geldiğinde (gerçek disk/net var) cap kaldırılır.
    if not has_full_features and output.confidence_score > _CONFIDENCE_CAP_DUMMY:
        output = output.model_copy(
            update={"confidence_score": _CONFIDENCE_CAP_DUMMY}
        )
        print(
            f"[LLM] Disk/Net dummy → confidence_score {_CONFIDENCE_CAP_DUMMY} ile kapat."
        )

    return output


# ── Yardımcı: Markdown Temizleyici ──────────────────────────────

def _strip_markdown_json(text: str) -> str:
    """
    LLM'in yanıtından markdown JSON sarmalayıcısını söker.

    Ele alınan durumlar:
      1. ```json\\n{...}\\n``` → {....} döner
      2. ```\\n{...}\\n```    → {...} döner
      3. Yanıt sadece JSON    → olduğu gibi döner
      4. Yanıt etrafında metin var → regex ile JSON objesini bulur

    :param text: LLM'den gelen ham yanıt
    :return: Temizlenmiş JSON string
    """
    text = text.strip()

    # Durum 1 & 2: markdown code block içinde JSON
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Durum 4: Yanıt içinde JSON objesi gömülü
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()

    # Durum 3: Zaten temiz JSON (veya tanımsız format — olduğu gibi bırak)
    return text


# ── Test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Hızlı test: Ollama çalışıyorsa serbest metin dene
    test_prompt = (
        "Sen bir DevOps asistanısın. Şu olayı 2 cümleyle özetle: "
        "Sunucuda bellek sızıntısı tespit edildi, chaos_sim prosesi RAM'in %87'sini "
        "tüketiyordu, otomatik müdahale ile sonlandırıldı."
    )
    print("=== Serbest Metin Testi ===")
    result = generate(test_prompt)
    print(f"Yanıt: {result}\n" if result else "Ollama'dan yanıt alınamadı.\n")

    print("=== Structured Output Testi ===")
    structured_prompt = (
        "System: server-prod-01. CPU=88%, RAM=91%. "
        "Anomaly score: 0.87. Action: RESTART."
    )
    structured = generate_structured(
        structured_prompt,
        action="RESTART",
        has_full_features=False
    )
    print(f"risk_level       : {structured.risk_level}")
    print(f"confidence_score : {structured.confidence_score}")
    print(f"summary          : {structured.prediction_summary}")
    print(f"action           : {structured.recommended_action}")
