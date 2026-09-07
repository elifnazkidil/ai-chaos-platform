"""
incident(olay)_reporter.py — Akıllı Olay Raporlama (Use Case Katmanı)

Self-healing mekanizması bir prosesi sonlandırdıktan SONRA çağrılır.
Olay verilerini alır, LLM'e (Ollama/Qwen) göndererek Türkçe zengin bir
olay raporu ürettirir ve bu raporu Telegram/n8n'e iletir + event_logs'a yazar.

Akış:
  self_healing.py (proses öldürür)
    → incident_reporter.py (bu dosya - LLM'den rapor ister)
      → llm_adapter.py (Ollama'ya POST atar)
        → Zengin Türkçe rapor → log + bildirim
"""

import datetime
from server.infrastructure.llm_adapter import generate
# TODO: log_event ve trigger_n8n_webhook şu an self_healing.py içinde tanımlı.
# Circular import riski var. İleride bunları infrastructure katmanına taşı:
#   from server.infrastructure.database import log_event
#   from server.infrastructure.notifier import trigger_n8n_webhook
from server.usecases.self_healing import log_event, trigger_n8n_webhook


def build_prompt(event_detail: str) -> str:
    """
    Olay verilerini LLM'e gönderilecek Türkçe bir prompt'a dönüştürür.
    """
    return f"""Sen bir FinTech DevOps asistanısın. Aşağıdaki olay verilerini analiz et ve Türkçe bir olay raporu oluştur.

Olay Verileri:
{event_detail}

Raporun şu başlıkları içersin:
1. Olay Özeti (2-3 cümle)
2. Aciliyet Seviyesi (Düşük / Orta / Yüksek / Kritik)
3. Önerilen Aksiyon (Kök neden analizi gerekli mi?)

Kısa ve net yaz. Maksimum 5 cümle."""


def generate_incident_report(event_detail: str) -> str | None:
    """
    LLM'den olay raporu üretir. Ollama çalışmıyorsa None döner.

    Args:
        event_detail: Self-healing'den gelen olay detayı
                      (örn: "Killed PID: 1234, Name: chaos_sim, Mem: 87.32%")

    Returns:
        str: LLM'in ürettiği Türkçe olay raporu
        None: LLM'e ulaşılamazsa
    """
    prompt = build_prompt(event_detail)
    report = generate(prompt)
    return report


def report_incident(event_detail: str):
    """
    Ana fonksiyon: self_healing.py tarafından çağrılır.

    1. LLM'den rapor üretir
    2. Raporu event_logs'a yazar
    3. n8n webhook'a gönderir (Telegram/Slack bildirimi)
    4. LLM çalışmıyorsa ham veriyi gönderir (fallback)
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RAPOR] {timestamp} — Olay raporu oluşturuluyor...")

    # LLM'den zengin rapor iste
    report = generate_incident_report(event_detail)

    if report:
        print(f"[RAPOR] LLM raporu hazır:\n{report}")
        log_event("INCIDENT_REPORT", report)
        trigger_n8n_webhook("INCIDENT_REPORT", report)
    else:
        # Fallback: LLM yoksa ham veriyi gönder
        print("[RAPOR] LLM'e ulaşılamadı, ham veri ile devam ediliyor.")
        fallback_report = f"[Otomatik Rapor] {timestamp} — {event_detail}"
        log_event("INCIDENT_REPORT_FALLBACK", fallback_report)
        trigger_n8n_webhook("INCIDENT_REPORT_FALLBACK", fallback_report)


if __name__ == "__main__":
    # Test: Sahte bir olay verisi ile rapor üret
    test_event = "Killed PID: 12345, Name: chaos_sim, Mem: 87.32% | Self-healing tarafından sonlandırıldı."
    report_incident(test_event)
