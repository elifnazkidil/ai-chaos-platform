"""
server/usecases/predict_leak.py

Use Cases Katmanı — Yapay Zeka Bellek Sızıntısı Tahmin İş Akışı
================================================================
Bu Use Case, AI modeli (MemoryLeakDetector) ile Repository'yi birbirine bağlar.
"Bir ajanın son N metriğini veritabanından çek, YSA'ya ver, sonucu döndür."

Domain ↔ AI ↔ Infrastructure arasındaki köprüdür.

Öğrenilen Kavramlar (Gün 2):
  - List comprehension ile veri dönüşümü: [m.ram_percent for m in metrics]
  - Early return: Yetersiz veri varsa erken çık, gereksiz hesaplama yapma
  - Type hints: -> dict, -> List[float]
"""

from typing import List
from server.domain.entities import Metric
from server.infrastructure.database import DatabaseManager
from server.infrastructure.metric_repo import MetricRepository
from ai.leak_detector import MemoryLeakDetector


# AI Dedektörünün pencere boyutu: son kaç ölçüm analiz edilsin?
# 10 saniye = makul bir trend tespiti için minimum veri
WINDOW_SIZE = 10

# Minimum kaç metrik olmalı ki tahmin güvenilir olsun?
MIN_METRICS_REQUIRED = 3


class PredictLeakUseCase:
    """
    Belirli bir ajana ait son metrikleri alıp YSA ile analiz eden Use Case.

    Bu Use Case şunları YAPMAZ:
      - Veriyi kaydetmez (IngestMetricUseCase'in işi)
      - İş emri oluşturmaz (GenerateWorkOrderUseCase'in işi)

    Single Responsibility Principle (SRP): Her sınıfın tek bir görevi olmalı!
    """

    def __init__(self, db: DatabaseManager):
        """
        :param db: Aktif DatabaseManager — MetricRepository oluşturmak için
        """
        self.metric_repo = MetricRepository(db)
        self.detector = MemoryLeakDetector(
            window_size=WINDOW_SIZE,
            min_slope_threshold=0.05  # Saniyede %0.05 RAM artışı → sızıntı sayılır
        )

    def execute(self, agent_id: str) -> dict:
        """
        Verilen ajan için bellek sızıntısı analizi yapar.

        Akış:
          1. MetricRepository'den son metrikleri çek
          2. RAM yüzdelerini bir listeye topla
          3. MemoryLeakDetector ile analiz et
          4. Sonucu döndür

        :param agent_id: Analiz edilecek ajanın kimliği (örn: "server-prod-01")
        :return: Analiz sonucu dict:
            {
              "agent_id": str,
              "is_leak": bool,
              "slope_per_sec": float,
              "current_ram_percent": float | None,
              "estimated_seconds_to_oom": float | None,
              "risk_level": str,
              "message": str,
              "data_points_used": int
            }
        """
        # ─── Adım 1: Son Metrikleri Veritabanından Çek ───────
        # En son WINDOW_SIZE kadar metriği al
        recent_metrics: List[Metric] = self.metric_repo.get_recent_by_agent(
            agent_id=agent_id,
            limit=WINDOW_SIZE
        )

        # ─── Adım 2: Yetersiz Veri Kontrolü ──────────────────
        # Early return: Yeterli veri yoksa AI analizi çalıştırma
        if len(recent_metrics) < MIN_METRICS_REQUIRED:
            return {
                "agent_id": agent_id,
                "is_leak": False,
                "slope_per_sec": 0.0,
                "current_ram_percent": None,
                "estimated_seconds_to_oom": None,
                "risk_level": "YETERSİZ VERİ",
                "message": (
                    f"Trend tespiti için en az {MIN_METRICS_REQUIRED} veri noktası gerekli. "
                    f"Mevcut: {len(recent_metrics)}"
                ),
                "data_points_used": len(recent_metrics)
            }

        # ─── Adım 3: RAM Yüzdelerini Listele ─────────────────
        # DB en yeni → en eski sırasıyla döndürüyor.
        # MemoryLeakDetector en eski → en yeni sırasıyla bekliyor (zaman sırası).
        # Bu yüzden reversed() ile ters çeviriyoruz.
        #
        # List comprehension açıklaması:
        #   [m.ram_percent for m in reversed(recent_metrics)]
        #   = her Metric nesnesinden sadece ram_percent değerini al, listeye koy
        ram_values: List[float] = [
            m.ram_percent for m in reversed(recent_metrics)
        ]

        # ─── Adım 4: YSA Analizi ─────────────────────────────
        analysis = self.detector.analyze_metrics(ram_values)

        # ─── Adım 5: Sonucu Zenginleştir ve Döndür ───────────
        return {
            "agent_id": agent_id,
            "is_leak": analysis["is_leak"],
            "slope_per_sec": analysis["slope_per_sec"],
            "current_ram_percent": analysis.get("current_ram_percent"),
            "estimated_seconds_to_oom": analysis["estimated_seconds_to_oom"],
            "risk_level": analysis["risk_level"],
            "message": analysis["message"],
            "data_points_used": len(recent_metrics)
        }
