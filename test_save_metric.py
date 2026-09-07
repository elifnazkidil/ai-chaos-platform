"""
test_save_metric.py

Gün 3 — SaveMetricUseCase Birim Testleri
=========================================
Fake/Mock repository ile use case'i test ediyoruz.
Veritabanı yok, ağ yok → hızlı, güvenilir, bağımsız.

Test Stratejisi:
  ✅ Geçerli payload → success=True, metric_id dolu
  ❌ Zorunlu alan eksik → InvalidMetricError
  ❌ timestamp format hatalı → InvalidMetricError
  ❌ metrics non-numeric → InvalidMetricError
  ❌ cpu_percent > 100 → InvalidMetricError (domain kuralı)
  ❌ repo.save() patlıyor → RepositoryError

NEDEN FAKE REPO?
  - Gerçek SQLiteMetricRepository kullanmak test'i yavaşlatır
  - Test, infrastructure'ı değil iş mantığını test etmeli
  - Fake repo, interface'i karşılayan minimal Python sınıfıdır

Öğrenilen Python Kavramları:
  - unittest / assert     : Birim test çerçevesi
  - in-memory list        : Fake storage
  - raise (içeride)       : Hata senaryosu simülasyonu
"""

import unittest
from server.domain.entities import Metric
from server.domain.exceptions import InvalidMetricError, RepositoryError
from server.usecases.interfaces.metric_repository import MetricRepositoryInterface
from server.usecases.save_metric import SaveMetricUseCase


# ─────────────────────────────────────────────────────────────
# FAKE REPOSITORY — Birim testlerde veritabanı yerine kullanılır
# ─────────────────────────────────────────────────────────────
class FakeMetricRepository(MetricRepositoryInterface):
    """
    MetricRepositoryInterface'in in-memory test implementasyonu.
    Gerçek SQLite yerine basit liste kullanır.

    Ayrıca 'force_error' bayrağı ile hata senaryosunu simüle edebiliriz.
    """

    def __init__(self, force_error: bool = False):
        self.saved: list[Metric] = []      # Kaydedilen metrikleri tut
        self.force_error = force_error     # True → save() patlasın

    def save(self, metric: Metric) -> Metric:
        if self.force_error:
            raise RuntimeError("Simüle edilmiş DB hatası!")
        self.saved.append(metric)
        return metric

    def exists(self, metric_id: str) -> bool:
        return any(m.metric_id == metric_id for m in self.saved)

    def get_latest_metrics(self, limit: int = 50) -> list[Metric]:
        return list(reversed(self.saved))[:limit]


# ─────────────────────────────────────────────────────────────
# YARDIMCI: Geçerli test payload'u
# ─────────────────────────────────────────────────────────────
def _valid_payload(
    agent_id="server-test-01",
    timestamp="2026-08-12T08:00:00",
    cpu_percent=45.2,
    ram_percent=62.1,
    ram_used_gb=9.9,
    ram_total_gb=16.0,
) -> dict:
    """Geçerli bir payload oluştur (testlerde override edilebilir)."""
    return {
        "agent_id":  agent_id,
        "timestamp": timestamp,
        "metrics": {
            "cpu_percent":  cpu_percent,
            "ram_percent":  ram_percent,
            "ram_used_gb":  ram_used_gb,
            "ram_total_gb": ram_total_gb,
        },
    }


# ─────────────────────────────────────────────────────────────
# TEST SINIFI
# ─────────────────────────────────────────────────────────────
class TestSaveMetricUseCase(unittest.TestCase):

    # ── setUp: Her test öncesi çalışır ──────────────────────
    def setUp(self):
        """Her test için temiz bir repo ve use case oluştur."""
        self.repo     = FakeMetricRepository()
        self.use_case = SaveMetricUseCase(self.repo)

    # ═══════════════════════════════════════════════════════
    # ✅ BAŞARI SENARYOLARI
    # ═══════════════════════════════════════════════════════

    def test_valid_payload_returns_success(self):
        """Geçerli payload → success=True ve metric_id dolu."""
        result = self.use_case.execute(_valid_payload())

        self.assertTrue(result.success)
        self.assertIsNotNone(result.metric_id)
        self.assertEqual(result.agent_id, "server-test-01")
        self.assertIsNone(result.error_message)

    def test_valid_payload_saves_to_repo(self):
        """Geçerli payload → repo.save() çağrılmış olmalı."""
        self.use_case.execute(_valid_payload())

        self.assertEqual(len(self.repo.saved), 1)
        saved = self.repo.saved[0]
        self.assertEqual(saved.agent_id, "server-test-01")
        self.assertAlmostEqual(saved.cpu_percent, 45.2)

    def test_timestamp_with_z_suffix(self):
        """'Z' soneki (UTC) kabul edilmeli."""
        result = self.use_case.execute(
            _valid_payload(timestamp="2026-08-12T08:00:00Z")
        )
        self.assertTrue(result.success)

    def test_timestamp_with_timezone_offset(self):
        """'+03:00' gibi timezone offset kabul edilmeli."""
        result = self.use_case.execute(
            _valid_payload(timestamp="2026-08-12T11:00:00+03:00")
        )
        self.assertTrue(result.success)

    def test_integer_metrics_accepted(self):
        """metrics değerleri int de olabilir (float gibi işlenir)."""
        result = self.use_case.execute(
            _valid_payload(cpu_percent=45, ram_percent=62,
                           ram_used_gb=10, ram_total_gb=16)
        )
        self.assertTrue(result.success)

    # ═══════════════════════════════════════════════════════
    # ❌ VALIDATION HATALARI — InvalidMetricError bekliyoruz
    # ═══════════════════════════════════════════════════════

    def test_missing_agent_id_raises_error(self):
        """agent_id eksik → InvalidMetricError."""
        payload = _valid_payload()
        del payload["agent_id"]
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(payload)

    def test_missing_timestamp_raises_error(self):
        """timestamp eksik → InvalidMetricError."""
        payload = _valid_payload()
        del payload["timestamp"]
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(payload)

    def test_missing_metrics_raises_error(self):
        """metrics alanı eksik → InvalidMetricError."""
        payload = _valid_payload()
        del payload["metrics"]
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(payload)

    def test_empty_agent_id_raises_error(self):
        """Boş string agent_id → InvalidMetricError."""
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(_valid_payload(agent_id=""))

    def test_whitespace_only_agent_id_raises_error(self):
        """Sadece boşluk agent_id → InvalidMetricError."""
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(_valid_payload(agent_id="   "))

    def test_bad_timestamp_format_raises_error(self):
        """Geçersiz timestamp formatı → InvalidMetricError."""
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(
                _valid_payload(timestamp="12/08/2026 08:00")
            )

    def test_non_string_timestamp_raises_error(self):
        """timestamp int ise → InvalidMetricError."""
        payload = _valid_payload()
        payload["timestamp"] = 1234567890   # Unix epoch, kabul edilmez
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(payload)

    def test_non_dict_metrics_raises_error(self):
        """metrics list ise → InvalidMetricError."""
        payload = _valid_payload()
        payload["metrics"] = [45.2, 62.1]
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(payload)

    def test_string_cpu_in_metrics_raises_error(self):
        """metrics['cpu_percent'] string → InvalidMetricError."""
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(
                _valid_payload(cpu_percent="yüksek")
            )

    def test_missing_metric_subfield_raises_error(self):
        """metrics içinde ram_total_gb eksik → InvalidMetricError."""
        payload = _valid_payload()
        del payload["metrics"]["ram_total_gb"]
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(payload)

    def test_cpu_over_100_raises_error(self):
        """cpu_percent > 100 → domain kuralı → InvalidMetricError."""
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(_valid_payload(cpu_percent=150.0))

    def test_negative_ram_raises_error(self):
        """ram_percent < 0 → domain kuralı → InvalidMetricError."""
        with self.assertRaises(InvalidMetricError):
            self.use_case.execute(_valid_payload(ram_percent=-5.0))

    # ═══════════════════════════════════════════════════════
    # ❌ REPOSITORY HATALARI — RepositoryError bekliyoruz
    # ═══════════════════════════════════════════════════════

    def test_repo_error_propagates(self):
        """repo.save() patlıyorsa → RepositoryError üst katmana çıkar."""
        failing_repo = FakeMetricRepository(force_error=True)
        use_case     = SaveMetricUseCase(failing_repo)

        with self.assertRaises(RepositoryError):
            use_case.execute(_valid_payload())

    def test_repo_not_called_on_validation_failure(self):
        """Validation başarısızsa repo.save() çağrılmamalı."""
        payload = _valid_payload()
        del payload["agent_id"]

        try:
            self.use_case.execute(payload)
        except InvalidMetricError:
            pass

        # Repo'ya hiçbir şey yazılmamış olmalı
        self.assertEqual(len(self.repo.saved), 0)

    # ═══════════════════════════════════════════════════════
    # ✅ RESULT PATTERN TESTİ
    # ═══════════════════════════════════════════════════════

    def test_result_to_dict_structure(self):
        """MetricResult.to_dict() doğru anahtarları içermeli."""
        result = self.use_case.execute(_valid_payload())
        d = result.to_dict()

        self.assertIn("success",       d)
        self.assertIn("metric_id",     d)
        self.assertIn("agent_id",      d)
        self.assertIn("error_message", d)
        self.assertTrue(d["success"])


# ─────────────────────────────────────────────────────────────
# ÇALIŞTIRMA
# python test_save_metric.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)
