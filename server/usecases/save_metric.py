"""
server/usecases/save_metric.py

Use Cases Katmanı — SaveMetricUseCase (Clean Architecture Blok 3)
===================================================================
Bu use case, Blok 3'ün ana odağıdır.

Amaç:
  Ajanlardan gelen metrik verilerini:
    1. Doğrula (validate)   → InvalidMetricError
    2. Domain entity'e çevir → Metric dataclass
    3. Repository'ye yaz    → MetricRepositoryInterface.save()
    4. Sonucu döndür        → MetricResult dataclass

KATMAN KURALLARI (Bu dosya asla ihlal etmemelidir):
  ✅ from server.domain.entities    → İzinli (domain)
  ✅ from server.domain.exceptions  → İzinli (domain)
  ✅ from server.usecases.interfaces → İzinli (interface)
  ❌ from server.infrastructure     → YASAK (concrete impl)
  ❌ from fastapi / flask / django  → YASAK (HTTP katmanı)
  ❌ import sqlite3                 → YASAK (altyapı detayı)

NEDEN HTTP YASAK?
  Use Case katmanı "iş mantığını" bilir, "taşıma protokolünü" bilmez.
  Aynı use case:
    - REST API → HTTP 400/500
    - CLI      → sys.exit(1)
    - Message queue → NACK mesajı
  ... olarak kullanılabilir. Bu esneklik ancak HTTP'den bağımsızlıkla olur.

Öğrenilen Python Kavramları:
  - @dataclass              : MetricResult sonuç nesnesi
  - ABC inject              : Bağımlılık tersine çevirme (DIP)
  - datetime.fromisoformat  : ISO 8601 ayrıştırma
  - isinstance()            : Tip kontrolü
  - raise ... from e        : Exception chaining (hata zinciri)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from server.domain.entities import Metric
from server.domain.exceptions import InvalidMetricError, RepositoryError
from server.usecases.interfaces.metric_repository import MetricRepositoryInterface


# ─────────────────────────────────────────────────────────────
# RESULT PATTERN: MetricResult
# Use Case'in execute() metodu dict değil, tip-güvenli nesne döndürür.
# Bu sayede üst katman result.success, result.id ile erişir.
# ─────────────────────────────────────────────────────────────
@dataclass
class MetricResult:
    """
    SaveMetricUseCase.execute() çıktısı.

    Kullanım:
        result = use_case.execute(payload)
        if result.success:
            print(f"Kaydedildi: {result.metric_id}")
        else:
            print(f"Hata: {result.error_message}")
    """
    success: bool
    metric_id: Optional[str] = field(default=None)
    agent_id: Optional[str] = field(default=None)
    error_message: Optional[str] = field(default=None)

    def to_dict(self) -> dict:
        """API katmanına JSON-hazır temsil."""
        return {
            "success":       self.success,
            "metric_id":     self.metric_id,
            "agent_id":      self.agent_id,
            "error_message": self.error_message,
        }


# ─────────────────────────────────────────────────────────────
# ISO 8601 REGEX: Timestamp doğrulama
# datetime.fromisoformat() Python 3.6'da 'Z' suffix'i kabul etmez.
# Bu regex ile önce format kontrolü yapıyoruz.
# ─────────────────────────────────────────────────────────────
_ISO_8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}"          # YYYY-MM-DD (zorunlu)
    r"[T ]"                         # T veya boşluk ayraç
    r"\d{2}:\d{2}:\d{2}"           # HH:MM:SS (zorunlu)
    r"(\.\d+)?"                     # .microseconds (opsiyonel)
    r"(Z|[+-]\d{2}:\d{2})?$"       # timezone (opsiyonel)
)


# ─────────────────────────────────────────────────────────────
# ANA USE CASE: SaveMetricUseCase
# ─────────────────────────────────────────────────────────────
class SaveMetricUseCase:
    """
    Ajan payload'unu doğrulayıp kalıcı depoya kaydeden use case.

    Dependency Injection:
        repo = SQLiteMetricRepository(db)   # ya da FakeMetricRepository()
        use_case = SaveMetricUseCase(repo)
        result = use_case.execute(payload)

    Bu Use Case'i test etmek istersen:
        fake_repo = FakeMetricRepository()  # test_save_metric.py'de tanımlandı
        use_case = SaveMetricUseCase(fake_repo)
        result = use_case.execute(valid_payload)
        assert result.success is True
    """

    def __init__(self, repo: MetricRepositoryInterface) -> None:
        """
        :param repo: MetricRepositoryInterface implementasyonu.
                     Use Case, concrete tipi (SQLite vs Mock) bilmez.
        """
        self.repo = repo

    def execute(self, payload: dict) -> MetricResult:
        """
        Ana iş akışı:
          1. Payload → doğrula → Metric entity
          2. Metric  → repo.save() → kayıtlı Metric
          3. MetricResult döndür

        :param payload: Agent'tan gelen ham dict.
            Beklenen anahtarlar:
              - agent_id  : str          → "server-prod-01"
              - timestamp : str (ISO)    → "2026-08-12T08:00:00"
              - metrics   : dict         → {"cpu_percent": 45.2, ...}

        :return: MetricResult (success=True) veya (success=False + error)
        :raises InvalidMetricError: Payload doğrulama hatası (400)
        :raises RepositoryError:    Veritabanı hatası (500)

        NOT: Bu metod exception'ları YOK SAYMAZ.
             Use case hata tipini ÜRETIR, HTTP kodu API katmanı çevirir.
        """
        # ── Adım 1: Validation ───────────────────────────────
        metric = self._validate_and_parse(payload)

        # ── Adım 2: Repository'ye Kaydet ─────────────────────
        # RepositoryError burada propagate edilir (yakalanmaz).
        # Üst katman (API route/controller) yakalar → 500 döner.
        try:
            saved_metric = self.repo.save(metric)
        except Exception as e:
            # Infrastructure'dan gelen beklenmedik hataları sarmala
            raise RepositoryError(
                f"Metrik kaydedilemedi (agent_id={metric.agent_id}): {e}"
            ) from e

        # ── Adım 3: Başarı Sonucu ────────────────────────────

        return MetricResult(
            success=True,
            metric_id=saved_metric.metric_id,
            agent_id=saved_metric.agent_id,
        )

    # ── Private: Validation & Parsing ────────────────────────

    def _validate_and_parse(self, payload: dict) -> Metric:
        """
        Ham dict'i doğrulayıp Metric entity'sine dönüştürür.

        Doğrulama adımları:
          1. Zorunlu üst-düzey alanlar mevcut mu?
          2. timestamp ISO 8601 formatında mı?
          3. metrics bir dict mi?
          4. metrics değerleri numeric mi?
          5. Metric dataclass oluştur (domain validasyonu da çalışır)

        :raises InvalidMetricError: Herhangi bir doğrulama başarısız olursa
        """
        # ── 1. Zorunlu alan kontrolü ─────────────────────────
        required_top_level = {"agent_id", "timestamp", "metrics"}
        missing = required_top_level - payload.keys()
        if missing:
            raise InvalidMetricError(
                f"Zorunlu alan(lar) eksik: {', '.join(sorted(missing))}"
            )

        agent_id  = payload["agent_id"]
        ts_raw    = payload["timestamp"]
        metrics   = payload["metrics"]

        # ── 2. agent_id tip ve boşluk kontrolü ──────────────
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise InvalidMetricError(
                "agent_id boş olmayan bir string olmalıdır."
            )

        # ── 3. timestamp format kontrolü ────────────────────
        if not isinstance(ts_raw, str):
            raise InvalidMetricError(
                f"timestamp string olmalıdır, alınan tip: {type(ts_raw).__name__}"
            )
        if not _ISO_8601_PATTERN.match(ts_raw):
            raise InvalidMetricError(
                f"timestamp ISO 8601 formatında olmalıdır "
                f"(örn: '2026-08-12T08:00:00'), alınan: '{ts_raw}'"
            )
        # Z suffix'ini +00:00 ile değiştir
        ts_normalized = ts_raw.replace("Z", "+00:00")
        try:
            timestamp = datetime.fromisoformat(ts_normalized)
        except ValueError as e:
            raise InvalidMetricError(
                f"timestamp ayrıştırılamadı: {e}"
            ) from e

        # ── 4. metrics tip kontrolü ──────────────────────────
        if not isinstance(metrics, dict):
            raise InvalidMetricError(
                f"metrics bir dict olmalıdır, alınan: {type(metrics).__name__}"
            )

        # ── 5. metrics zorunlu alt-alanları ──────────────────
        required_metric_keys = {
            "cpu_percent", "ram_percent", "ram_used_gb", "ram_total_gb"
        }
        missing_metrics = required_metric_keys - metrics.keys()
        if missing_metrics:
            raise InvalidMetricError(
                f"metrics içinde zorunlu alan(lar) eksik: "
                f"{', '.join(sorted(missing_metrics))}"
            )

        # ── 6. metrics değerleri numeric mi? ─────────────────
        for key in required_metric_keys:
            val = metrics[key]
            if not isinstance(val, (int, float)):
                raise InvalidMetricError(
                    f"metrics['{key}'] numeric olmalıdır (int veya float), "
                    f"alınan: {type(val).__name__} = {val!r}"
                )

        #Domain seviyesinde değerleri kontrol ediyoruz. Eğer değerler
        #yoksa ya da sayısal değilse burada hata verir.
        # __post_init__ metodu da burada çalışır.               
        # cpu/ram aralık kontrolü yapar (0-100) 
        # Ra    m total gb sıfırdan büyük olmalı
        # Ram used gb ram total gb den küçük olmalı
        # Bu değerler yanlışsa burada hata verir.

        # ── 7. Metric entity oluştur (domain kuralları da çalışır) ──
        try:
            metric = Metric(
                agent_id=agent_id.strip(),
                cpu_percent=float(metrics["cpu_percent"]),
                ram_percent=float(metrics["ram_percent"]),
                ram_used_gb=float(metrics["ram_used_gb"]),
                ram_total_gb=float(metrics["ram_total_gb"]),
                timestamp=timestamp,
            )
        except ValueError as e:
            # Domain entity validasyonu başarısız (örn: cpu > 100)
            raise InvalidMetricError(
                f"Metrik domain doğrulaması başarısız: {e}"
            ) from e

        return metric
