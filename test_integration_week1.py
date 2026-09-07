"""
test_integration_week1.py

Hafta 1 — Uçtan Uca Entegrasyon Testi
=======================================
Bu test, tüm pipeline'ı tek bir dosyadan doğrular:

  1. POST /api/v1/metrics  → Metrik gönder (Agent simülasyonu)
  2. SQLite'a yazıldığını doğrula
  3. GET /api/v1/metrics/latest → Veriyi geri oku
  4. Gönderilen == Okunan? → Assert et

Kullanılan Araç: FastAPI TestClient
  - Gerçek bir sunucu başlatmaya gerek yok
  - httpx kütüphanesi üzerinden çalışır
  - Birim test kadar hızlı, entegrasyon testi kadar kapsamlı

Öğrenilen Kavramlar:
  - TestClient         : FastAPI'nin dahili test aracı
  - status_code        : HTTP yanıt kodu kontrolü (201, 200, 400)
  - response.json()    : JSON yanıtı Python dict'e çevirme
  - setUp / tearDown   : Her test öncesi/sonrası temizlik
"""

import unittest
import os
import sqlite3
from fastapi.testclient import TestClient
from server.api.main import app


class TestWeek1Integration(unittest.TestCase):
    """
    Hafta 1 Entegrasyon Testleri

    Bu test sınıfı, Agent → FastAPI → SQLite → API okuma
    pipeline'ının uçtan uca çalıştığını doğrular.
    """

    @classmethod
    def setUpClass(cls):
        """
        Tüm testlerden ÖNCE bir kez çalışır.
        TestClient oluşturur — gerçek sunucu başlatmaya gerek yok.
        """
        cls.client = TestClient(app)

    # ─────────────────────────────────────────────────────
    # Yardımcı: Geçerli test payload'u
    # ─────────────────────────────────────────────────────
    def _make_payload(
        self,
        agent_id="integration-test-agent",
        timestamp="2026-08-19T09:00:00",
        cpu_percent=35.5,
        ram_percent=52.3,
        ram_used_gb=8.37,
        ram_total_gb=16.0,
    ):
        """Test için geçerli bir metrik payload'u oluşturur."""
        return {
            "agent_id": agent_id,
            "timestamp": timestamp,
            "metrics": {
                "cpu_percent": cpu_percent,
                "ram_percent": ram_percent,
                "ram_used_gb": ram_used_gb,
                "ram_total_gb": ram_total_gb,
            },
        }

    # ═══════════════════════════════════════════════════════
    # ✅ TEST 1: Sağlık Kontrolü (Health Check)
    # ═══════════════════════════════════════════════════════
    def test_01_health_check(self):
        """
        GET / → API çalışıyor mu?
        Beklenen: 200 OK ve mesaj içermeli.
        """
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("message", data)
        print(f"  ✅ Sağlık kontrolü: {data['message']}")

    # ═══════════════════════════════════════════════════════
    # ✅ TEST 2: Metrik Gönderme (POST)
    # ═══════════════════════════════════════════════════════
    def test_02_post_metric_success(self):
        """
        POST /api/v1/metrics → Geçerli metrik gönder.
        Beklenen: 201 Created, success=True, metric_id dolu.
        """
        payload = self._make_payload()
        response = self.client.post("/api/v1/metrics", json=payload)

        self.assertEqual(response.status_code, 201)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data["metric_id"])
        self.assertEqual(data["agent_id"], "integration-test-agent")
        print(f"  ✅ Metrik kaydedildi: {data['metric_id'][:8]}...")

    # ═══════════════════════════════════════════════════════
    # ✅ TEST 3: Metrik Okuma (GET)
    # ═══════════════════════════════════════════════════════
    def test_03_get_latest_metrics(self):
        """
        GET /api/v1/metrics/latest → Kaydedilen verileri oku.
        Beklenen: 200 OK, success=True, data listesi dolu.
        """
        # Önce bir metrik gönder (bu test bağımsız çalışabilsin diye)
        payload = self._make_payload(
            agent_id="get-test-agent",
            timestamp="2026-08-19T10:00:00",
            cpu_percent=42.0,
            ram_percent=61.5,
        )
        self.client.post("/api/v1/metrics", json=payload)

        # Şimdi oku
        response = self.client.get("/api/v1/metrics/latest")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["count"], 0)
        self.assertIsInstance(data["data"], list)
        print(f"  ✅ {data['count']} metrik okundu")

    # ═══════════════════════════════════════════════════════
    # ✅ TEST 4: Gönder → Oku → Doğrula (Round-Trip)
    # ═══════════════════════════════════════════════════════
    def test_04_round_trip_verification(self):
        """
        Uçtan uca doğrulama:
          1. Bilinen değerlerle POST et
          2. GET ile geri oku
          3. Gönderilen == Okunan mı?

        Bu test, tüm pipeline'ın doğru çalıştığını kanıtlar.
        """
        # 1. Benzersiz bir agent_id ile gönder
        test_agent = "roundtrip-test-agent"
        payload = self._make_payload(
            agent_id=test_agent,
            timestamp="2026-08-19T12:34:56",
            cpu_percent=77.7,
            ram_percent=88.8,
            ram_used_gb=14.2,
            ram_total_gb=16.0,
        )

        post_response = self.client.post("/api/v1/metrics", json=payload)
        self.assertEqual(post_response.status_code, 201)
        sent_metric_id = post_response.json()["metric_id"]

        # 2. GET ile son metrikleri oku
        get_response = self.client.get("/api/v1/metrics/latest?limit=100")
        self.assertEqual(get_response.status_code, 200)

        metrics = get_response.json()["data"]

        # 3. Gönderdiğimiz metriği bul
        found = [m for m in metrics if m["metric_id"] == sent_metric_id]
        self.assertEqual(len(found), 1, "Gönderilen metrik bulunamadı!")

        received = found[0]

        # 4. Değerleri karşılaştır
        self.assertEqual(received["agent_id"], test_agent)
        self.assertAlmostEqual(received["cpu_percent"], 77.7, places=1)
        self.assertAlmostEqual(received["ram_percent"], 88.8, places=1)
        self.assertAlmostEqual(received["ram_used_gb"], 14.2, places=1)
        self.assertAlmostEqual(received["ram_total_gb"], 16.0, places=1)

        print(f"  ✅ Round-trip doğrulandı: POST → SQLite → GET eşleşti!")

    # ═══════════════════════════════════════════════════════
    # ❌ TEST 5: Geçersiz Payload (Validation)
    # ═══════════════════════════════════════════════════════
    def test_05_invalid_payload_returns_400(self):
        """
        Eksik agent_id ile POST → 400 Bad Request bekliyoruz.
        API katmanı, domain hatalarını HTTP hatasına çevirmeli.
        """
        bad_payload = {
            "timestamp": "2026-08-19T09:00:00",
            "metrics": {
                "cpu_percent": 50.0,
                "ram_percent": 60.0,
                "ram_used_gb": 9.6,
                "ram_total_gb": 16.0,
            },
        }

        response = self.client.post("/api/v1/metrics", json=bad_payload)
        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("error_message", data)
        print(f"  ✅ Geçersiz payload reddedildi: {data['error_message']}")

    # ═══════════════════════════════════════════════════════
    # ❌ TEST 6: CPU > 100 Domain Kuralı
    # ═══════════════════════════════════════════════════════
    def test_06_cpu_over_100_returns_400(self):
        """
        cpu_percent > 100 → Domain kuralı ihlali → 400.
        """
        payload = self._make_payload(cpu_percent=150.0)
        response = self.client.post("/api/v1/metrics", json=payload)
        self.assertEqual(response.status_code, 400)
        print(f"  ✅ CPU %150 reddedildi (domain kuralı)")

    # ═══════════════════════════════════════════════════════
    # ✅ TEST 7: Birden Fazla Metrik Gönder
    # ═══════════════════════════════════════════════════════
    def test_07_multiple_metrics_stored(self):
        """
        3 farklı metrik gönder → Hepsi kaydedilmeli.
        Entegrasyon testinde birden fazla kaydın düzgün
        tutulduğunu doğrular.
        """
        agent_ids = []
        for i in range(3):
            agent = f"multi-test-{i}"
            agent_ids.append(agent)
            payload = self._make_payload(
                agent_id=agent,
                timestamp=f"2026-08-19T{10+i}:00:00",
                cpu_percent=20.0 + i * 10,
                ram_percent=40.0 + i * 5,
            )
            resp = self.client.post("/api/v1/metrics", json=payload)
            self.assertEqual(resp.status_code, 201)

        # Hepsini oku
        response = self.client.get("/api/v1/metrics/latest?limit=100")
        data = response.json()["data"]
        found_agents = [m["agent_id"] for m in data]

        for agent in agent_ids:
            self.assertIn(agent, found_agents, f"{agent} bulunamadı!")

        print(f"  ✅ 3 metrik başarıyla kaydedildi ve okundu")

    # ═══════════════════════════════════════════════════════
    # ✅ TEST 8: Swagger Dökümantasyonu Erişimi
    # ═══════════════════════════════════════════════════════
    def test_08_swagger_docs_accessible(self):
        """
        GET /docs → Swagger UI erişilebilir olmalı.
        """
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        print(f"  ✅ Swagger UI erişilebilir")


# ─────────────────────────────────────────────────────────────
# ÇALIŞTIRMA
# python -m pytest test_integration_week1.py -v
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("HAFTA 1 — UÇTAN UCA ENTEGRASYON TESTİ")
    print("=" * 60)
    unittest.main(verbosity=2)
