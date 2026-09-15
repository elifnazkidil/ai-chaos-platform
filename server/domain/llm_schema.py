"""
server/domain/llm_schema.py

Domain Katmanı — LLM Karar Çıktısı Şeması (Structured Output)
===============================================================
LLM'den beklenen yapılandırılmış (structured) çıktının Pydantic modeli.

Clean Architecture Notu:
  Bu model Domain katmanında çünkü bir iş sözleşmesidir (business contract).
  "LLM'den ne bekliyoruz?" sorusunun cevabı iş mantığıdır, altyapı detayı değil.
  Infrastructure (llm_adapter.py) bu modeli kullanır → bağımlılık yönü doğru.

Pydantic v2 (FastAPI ile birlikte gelir) kullanılıyor.

Öğrenilen Kavramlar:
  - BaseModel       : Pydantic'in temel sınıfı, otomatik validasyon sağlar
  - Literal         : Sadece belirli string değerlere izin verir (type-safe enum gibi)
  - field_validator : Belirli bir field için özel doğrulama mantığı
  - model_copy      : Mevcut modeli kopyalayıp bazı alanları değiştir (immutable update)
"""

from __future__ import annotations

from typing import Literal, Optional, List
from pydantic import BaseModel, field_validator


# ══════════════════════════════════════════════════════════════
# ANA ŞEMA: LLMDecisionOutput
# ══════════════════════════════════════════════════════════════

class LLMDecisionOutput(BaseModel):
    """
    LLM'den beklenen yapılandırılmış karar çıktısı.

    Neden Pydantic?
      - Tip güvenliği: risk_level "low"/"medium"/"high"/"critical" dışı gelirse
        anında ValidationError → fallback devreye girer
      - Otomatik dönüşüm: LLM "0.87" string verse float'a çevirir
      - Dokümantasyon: Schema FastAPI /docs'ta otomatik görünür

    Kullanım:
        output = LLMDecisionOutput(
            risk_level="high",
            prediction_summary="CPU kritik seviyede yükseldi.",
            recommended_action="Servisi yeniden başlat.",
            confidence_score=0.87
        )
        print(output.risk_level)           # "high"
        print(output.to_dict())            # JSON-hazır dict
    """

    risk_level: Literal["low", "medium", "high", "critical"]
    """
    Tespit edilen risk seviyesi. 4 sabit değerden biri.
    Literal → bu 4 string dışındaki bir değer ValidationError fırlatır.
    """

    prediction_summary: str
    """Durumun 1-2 cümlelik Türkçe özeti."""

    recommended_action: str
    """Önerilen aksiyon (kural motoruyla tutarlı olmalı)."""

    confidence_score: float
    """
    LLM'in bu karara olan güveni. 0.0 (belirsiz) ile 1.0 (çok güvenli) arası.
    Disk/Net verisi dummy ise dışarıdan 0.6'ya kapatılır (cap).
    """

    explanation: Optional[str] = None
    """
    LLM'in "neden bu tahmin yapıldı" açıklaması.
    Feature importance bilgisiyle zenginleştirilmiş.
    Optional: LLM yanit vermezse None kalır, skor diğer alanlardan okunur.
    """

    feature_impacts: Optional[List[dict]] = None
    """
    Hangi özelliğin tahmini ne kadar etkilediğini gösteren liste.
    Örn: [{"feature": "RAM", "impact": 0.87, "direction": "artış"}, ...]
    Optional: Explainability motoru çalışmazsa None kalır.
    """

    # ── Validators ──────────────────────────────────────────────
    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """
        0.0-1.0 aralığı dışındaki değerleri reddeder.

        @classmethod → self yerine cls alır çünkü nesne henüz oluşmadı.
        Bu validator nesne oluşturulmadan önce çalışır.
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"confidence_score 0.0-1.0 arasında olmalı, alınan: {v}"
            )
        return round(v, 4)  # 4 basamak hassasiyet (0.8734 gibi)

    @field_validator("prediction_summary", "recommended_action")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Boş veya sadece boşluk içeren string'leri reddeder."""
        if not v or not v.strip():
            raise ValueError("Bu alan boş olamaz.")
        return v.strip()

    # ── Yardımcı Metod ──────────────────────────────────────────
    def to_dict(self) -> dict:
        """API katmanına ve dashboard'a JSON-hazır temsil."""
        return self.model_dump()


# ══════════════════════════════════════════════════════════════
# FALLBACK ÜRETİCİ
# ══════════════════════════════════════════════════════════════
# LLM veya JSON parse başarısız olursa kural motorunun aksiyonuna göre
# deterministik bir LLMDecisionOutput üretilir.
# Bu sayede Ollama çöktüğünde sistem DURMAZ — sadece LLM kısmı devre dışı kalır.

_FALLBACK_MAP: dict[str, dict] = {
    "MONITOR": {
        "risk_level": "low",
        "prediction_summary": (
            "Sistem metrikleri normal sınırlar içinde. "
            "YSA anormallik tespit etmedi, izlemeye devam ediliyor."
        ),
        "recommended_action": "İzlemeye devam et, herhangi bir aksiyon gerekmiyor.",
        "confidence_score": 0.50,
    },
    "ALERT": {
        "risk_level": "medium",
        "prediction_summary": (
            "YSA hafif bir anomali tespit etti. "
            "Metrikler dikkat gerektiren seviyelere ulaşıyor."
        ),
        "recommended_action": "Operasyon ekibine bildirim gönder, trendi yakından izle.",
        "confidence_score": 0.55,
    },
    "SCALE_UP": {
        "risk_level": "medium",
        "prediction_summary": (
            "Kaynak tüketiminde belirgin artış eğilimi var. "
            "Mevcut kapasite yetersiz kalabilir."
        ),
        "recommended_action": "Kaynak kapasitesini artır veya yükü dağıt.",
        "confidence_score": 0.60,
    },
    "RESTART": {
        "risk_level": "high",
        "prediction_summary": (
            "YSA yüksek anomali skoru üretti. "
            "Sistemde ciddi anormallik mevcut, müdahale gerekiyor."
        ),
        "recommended_action": "İlgili servisi kontrollü şekilde yeniden başlat.",
        "confidence_score": 0.65,
    },
    "KILL_PROCESS": {
        "risk_level": "critical",
        "prediction_summary": (
            "Kritik seviyede anomali tespit edildi. "
            "Bellek sızıntısı yapan proses sistemi tehdit ediyor."
        ),
        "recommended_action": "Sızıntı yapan prosesi derhal sonlandır.",
        "confidence_score": 0.70,
    },
}


def fallback_output(action: str) -> LLMDecisionOutput:
    """
    LLM kullanılamadığında veya parse/validasyon başarısız olduğunda
    kural motorunun aksiyonuna göre deterministik LLMDecisionOutput üretir.

    :param action: DecisionEngine ACTION_TABLE'dan gelen aksiyon kodu
                   ("MONITOR", "ALERT", "SCALE_UP", "RESTART", "KILL_PROCESS")
    :return: Önceden tanımlanmış sabit değerli LLMDecisionOutput
    """
    data = _FALLBACK_MAP.get(action, _FALLBACK_MAP["MONITOR"])
    return LLMDecisionOutput(**data)
