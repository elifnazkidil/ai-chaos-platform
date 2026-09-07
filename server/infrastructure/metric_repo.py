"""
server/infrastructure/metric_repo.py

Infrastructure Katmanı — Metrik Repository (Veri Erişim Nesnesi)
=================================================================
Repository Pattern: Veritabanı işlemlerini (SQL) iş mantığından ayırır.
Use Cases katmanı sadece şunu bilir: "MetricRepository'ye .save() ya da
.get_recent() derim, nasıl çalıştığını bilmek zorunda değilim."

Clean Architecture Kuralı:
  Use Cases → MetricRepository (soyutlama)
                     ↓
             metric_repo.py (SQLite gerçeklemesi)

Öğrenilen Kavramlar (Gün 2):
  - INSERT OR IGNORE: Aynı primary key ile tekrar kayıt engellemesi
  - SELECT ... ORDER BY ... LIMIT: Son N kaydı çekme
  - sqlite3.Row: Dict-like satır erişimi (row["ram_percent"])
  - List comprehension: [... for row in rows]
"""

import sqlite3
from typing import List, Optional
from server.domain.entities import Metric
from server.infrastructure.database import DatabaseManager


class MetricRepository:
    """
    Metric domain entity'lerinin SQLite'a yazılmasını ve
    okunmasını sağlayan Repository sınıfı.

    Use Cases bu sınıfı kullanarak:
      1. Yeni metrik kaydeder: .save(metric)
      2. Son N metriği çeker: .get_recent_by_agent(agent_id, limit)
      3. Tüm metrikleri listeler: .get_all()
    """

    def __init__(self, db: DatabaseManager):
        """
        :param db: Aktif DatabaseManager bağlantısı
        """
        self.db = db

    def save(self, metric: Metric) -> bool:
        """
        Bir Metric domain entity'sini veritabanına kaydeder.

        INSERT OR IGNORE: Aynı metric_id (UUID) ile tekrar kayıt gelirse
        hata vermek yerine sessizce geçer. Bu sayede ağ tekrar gönderiminde
        duplicate kayıt oluşmaz.

        :param metric: Kaydedilecek Metric nesnesi
        :return: Kayıt başarıyla eklendiyse True, zaten varsa False
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO metrics
                (metric_id, agent_id, timestamp, cpu_percent, ram_percent, ram_used_gb, ram_total_gb)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric.metric_id,
                metric.agent_id,
                metric.timestamp.isoformat(),  # datetime → ISO 8601 string
                metric.cpu_percent,
                metric.ram_percent,
                metric.ram_used_gb,
                metric.ram_total_gb,
            )
        )
        conn.commit()

        # rowcount: Kaç satır etkilendi? 1 → yeni kayıt, 0 → zaten vardı
        was_inserted = cursor.rowcount > 0
        return was_inserted

    def get_recent_by_agent(self, agent_id: str, limit: int = 20) -> List[Metric]:
        """
        Belirli bir ajana ait en son N metriği döner (en yeni önce).

        PredictLeakUseCase bu metodu kullanır:
        "server-prod-01'in son 20 RAM ölçümünü ver, YSA'ya besleyeyim."

        SQL Açıklaması:
          WHERE agent_id = ?   → sadece bu ajanın kayıtları
          ORDER BY timestamp DESC → en yeni kayıt önce gelir
          LIMIT ?               → sadece istenen sayıda satır döner

        :param agent_id: Hangi ajanın metrikleri isteniyor
        :param limit: Kaç kayıt dönsün (varsayılan: 20)
        :return: Metric listesi (en yeni → en eski sırasıyla)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT metric_id, agent_id, timestamp, cpu_percent,
                   ram_percent, ram_used_gb, ram_total_gb
            FROM metrics
            WHERE agent_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (agent_id, limit)
        )

        rows = cursor.fetchall()

        # sqlite3.Row'u Metric domain entity'ye dönüştür
        # List comprehension: kısa ve pythonic döngü
        return [self._row_to_metric(row) for row in rows]

    def get_all(self, limit: int = 100) -> List[Metric]:
        """
        Tüm ajanların en son metriklerini döner. Dashboard için kullanılır.

        :param limit: Maksimum döndürülecek kayıt sayısı
        :return: Metric listesi
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT metric_id, agent_id, timestamp, cpu_percent,
                   ram_percent, ram_used_gb, ram_total_gb
            FROM metrics
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,)
        )

        rows = cursor.fetchall()
        return [self._row_to_metric(row) for row in rows]

    def count_by_agent(self, agent_id: str) -> int:
        """
        Bir ajana ait toplam metrik sayısını döner.
        PredictLeakUseCase'de "yeterli veri var mı?" kontrolü için kullanılır.

        :param agent_id: Ajan kimliği
        :return: Toplam metrik sayısı
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM metrics WHERE agent_id = ?",
            (agent_id,)
        )

        # fetchone() → tek satır döner, [0] → ilk (ve tek) sütun değeri
        result = cursor.fetchone()
        return result[0] if result else 0

    # ── Private Yardımcı Metod ────────────────────────────────
    @staticmethod
    def _row_to_metric(row: sqlite3.Row) -> Metric:
        """
        SQLite satırını (sqlite3.Row) Metric domain entity'ye dönüştürür.

        Bu dönüşüm işlemi "Adapter" (Adaptör) tasarım desenidir:
        Dış dünyadan (DB) gelen veriyi iç dünyaya (Domain) uyumlu hale getirir.

        :param row: sqlite3.Row nesnesi
        :return: Metric domain entity
        """
        from datetime import datetime

        return Metric(
            metric_id=row["metric_id"],
            agent_id=row["agent_id"],
            cpu_percent=row["cpu_percent"],
            ram_percent=row["ram_percent"],
            ram_used_gb=row["ram_used_gb"],
            ram_total_gb=row["ram_total_gb"],
            # ISO 8601 string'i datetime nesnesine geri çeviriyoruz
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
