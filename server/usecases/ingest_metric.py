"""
server/usecases/ingest_metric.py

Use Cases Katmanı — Metrik Yutma (Ingestion) İş Akışı
=======================================================
Clean Architecture'da Use Cases = "Ne yapılacağını" belirleyen orkestratör.
"Nasıl yapılacağı" Infrastructure katmanında (Repository) gizlidir.

Bu Use Case'in sorumluluğu:
  1. Dış dünyadan (API veya Agent) gelen ham dict verisini al
  2. Domain Metric entity'sine dönüştür (validasyon dahil)
  3. Veritabanına kaydet
  4. AI tahmin sürecini tetikle → sızıntı varsa iş emri üret

Öğrenilen Kavramlar (Gün 2):
  - dataclass composition: Use Case sınıfı bağımlılıklarını __init__'te alır
  - Result pattern: Başarı/hata bilgisini dict ile döndürme
  - Exception handling: Domain validasyon hatalarını yakalama
  - Lazy import: Döngüsel bağımlılığı önlemek için içeride import
"""

from typing import Optional
from server.domain.entities import Metric
from server.infrastructure.database import DatabaseManager
from server.infrastructure.metric_repo import MetricRepository


class IngestMetricUseCase:
    """
    Bir Agent'tan gelen metrik verisini işleyip sisteme alan Use Case.

    Akış:
      Dış Dünya (JSON dict)
           ↓
      Metric domain entity oluştur (validasyonlu)
           ↓
      MetricRepository.save() → SQLite'a yaz
           ↓
      PredictLeakUseCase'i tetikle → risk var mı?
           ↓
      Sonucu döndür (başarı + tahmin + work_order?)

    Bağımlılık Enjeksiyonu (Dependency Injection):
      Use Case, bağımlılıklarını (Repository) kendisi oluşturmaz.
      Dışarıdan alır. Bu sayede testlerde sahte (mock) Repository verilebilir.
    """

    def __init__(self, db: DatabaseManager):
        """
        :param db: Aktif DatabaseManager — Repository'leri buradan oluşturuyoruz.
        """
        self.metric_repo = MetricRepository(db)
        self._db = db

    def execute(self, raw_data: dict) -> dict:
        """
        Ana iş akışını çalıştırır.

        :param raw_data: Agent'tan gelen ham metrik dict'i.
                         Beklenen anahtarlar:
                           - agent_id   : str  (örn: "server-prod-01")
                           - cpu_percent: float
                           - ram_percent: float
                           - ram_used_gb: float
                           - ram_total_gb: float

        :return: Sonuç dict'i:
            {
              "success": bool,
              "metric_id": str | None,
              "was_new": bool,          # True: yeni kayıt, False: zaten vardı
              "prediction": dict | None, # AI tahmin sonucu
              "work_order": dict | None, # Üretilen ERP İş Emri
              "error": str | None        # Hata mesajı
            }
        """
        # ─── Adım 1: Domain Entity Oluştur ───────────────────
        try:
            metric = self._build_metric(raw_data)
        except (ValueError, KeyError) as e:
            # Domain validasyonu başarısız (örn: CPU > 100, eksik alan)
            return {
                "success": False,
                "metric_id": None,
                "was_new": False,
                "prediction": None,
                "work_order": None,
                "error": f"Geçersiz metrik verisi: {str(e)}"
            }

        # ─── Adım 2: Veritabanına Kaydet ─────────────────────
        was_new = self.metric_repo.save(metric)

        # ─── Adım 3: AI Tahminini Tetikle ────────────────────
        # Lazy import: Döngüsel bağımlılığı önlemek için burada import ediyoruz
        from server.usecases.predict_leak import PredictLeakUseCase

        predictor = PredictLeakUseCase(self._db)
        prediction_result = predictor.execute(agent_id=metric.agent_id)

        # ─── Adım 4: Gerekirse İş Emri Üret ──────────────────
        work_order_data = None

        if prediction_result.get("is_leak"):
            from server.usecases.generate_work_order import GenerateWorkOrderUseCase

            wo_creator = GenerateWorkOrderUseCase(self._db)
            work_order_data = wo_creator.execute(
                agent_id=metric.agent_id,
                prediction=prediction_result
            )

        return {
            "success": True,
            "metric_id": metric.metric_id,
            "was_new": was_new,
            "prediction": prediction_result,
            "work_order": work_order_data,
            "error": None
        }

    # ── Private Yardımcı Metod ────────────────────────────────
    @staticmethod
    def _build_metric(raw_data: dict) -> Metric:
        """
        Ham dict'i Metric domain entity'sine dönüştürür.

        dict.get() vs dict[]: dict.get("key", default) → KeyError fırlatmaz,
        yoksa default döner. Zorunlu alanlar için [] kullanıyoruz ki
        eksikse anlamlı hata alsın.

        :param raw_data: API veya agent'tan gelen dict
        :return: Doğrulanmış Metric entity
        :raises ValueError: Domain validasyonu başarısızsa
        :raises KeyError: Zorunlu alan eksikse
        """
        return Metric(
            agent_id=raw_data["agent_id"],
            cpu_percent=float(raw_data["cpu_percent"]),
            ram_percent=float(raw_data["ram_percent"]),
            ram_used_gb=float(raw_data["ram_used_gb"]),
            ram_total_gb=float(raw_data["ram_total_gb"]),
        )
        # Not: metric_id ve timestamp otomatik üretilir (entities.py'deki field defaults)
