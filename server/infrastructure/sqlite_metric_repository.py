"""
server/infrastructure/sqlite_metric_repository.py

Infrastructure Katmanı — SQLite Concrete Repository
====================================================
Bu dosya MetricRepositoryInterface'i SQLite ile somutlaştırır.

KATMAN KURALI:
  - Use Case bu dosyayı ASLA import etmez
  - API katmanı veya DI container bunu oluşturur → use case'e inject eder

Bağımlılık Akışı:
  API/main.py
      │
      ├── db = DatabaseManager()
      ├── repo = SQLiteMetricRepository(db)      ← burada oluşturulur
      └── use_case = SaveMetricUseCase(repo)     ← inject edilir
"""

import sqlite3
from server.domain.entities import Metric
from server.domain.exceptions import RepositoryError
from server.infrastructure.database import DatabaseManager
from server.usecases.interfaces.metric_repository import MetricRepositoryInterface
from server.api.decorators import log_execution_time


class SQLiteMetricRepository(MetricRepositoryInterface):
    """
    MetricRepositoryInterface'in SQLite implementasyonu.

    Var olan DatabaseManager ve metrics tablosunu kullanır
    (Gün 1-2'de oluşturulan infrastructure korunur).
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @log_execution_time
    def save(self, metric: Metric) -> Metric:
        """
        Metric entity'sini metrics tablosuna yazar.

        :param metric: Doğrulanmış Metric domain nesnesi
        :return: Aynı metric (id değişmez, veritabanı primary key olarak metric_id kullanılır)
        :raises RepositoryError: SQLite hatası durumunda
        """
        try:
            conn = self._db.get_connection()
            conn.execute(
                """
                INSERT OR IGNORE INTO metrics
                  (metric_id, agent_id, timestamp,
                   cpu_percent, ram_percent, ram_used_gb, ram_total_gb)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric.metric_id,
                    metric.agent_id,
                    metric.timestamp.isoformat(),
                    metric.cpu_percent,
                    metric.ram_percent,
                    metric.ram_used_gb,
                    metric.ram_total_gb,
                ),
            )
            conn.commit()
            return metric
        except sqlite3.Error as e:
            raise RepositoryError(
                f"SQLite yazma hatası (agent={metric.agent_id}): {e}"
            ) from e

    def exists(self, metric_id: str) -> bool:
        """
        Verilen metric_id veritabanında var mı?

        :param metric_id: UUID string
        :return: True → kayıt var, False → yok
        """
        try:
            conn = self._db.get_connection()
            cursor = conn.execute(
                "SELECT 1 FROM metrics WHERE metric_id = ? LIMIT 1",
                (metric_id,),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            raise RepositoryError(
                f"SQLite okuma hatası (metric_id={metric_id}): {e}"
            ) from e

    @log_execution_time
    def get_latest_metrics(self, limit: int = 50) -> list[Metric]:
        """
        En son eklenen metrikleri getirir.
        
        :param limit: Getirilecek maksimum metrik sayısı
        :return: Metric nesnelerinden oluşan bir liste
        """
        from datetime import datetime
        try:
            conn = self._db.get_connection()
            cursor = conn.execute(
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
            return [
                Metric(
                    metric_id=row["metric_id"],
                    agent_id=row["agent_id"],
                    cpu_percent=row["cpu_percent"],
                    ram_percent=row["ram_percent"],
                    ram_used_gb=row["ram_used_gb"],
                    ram_total_gb=row["ram_total_gb"],
                    timestamp=datetime.fromisoformat(row["timestamp"])
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            raise RepositoryError(f"SQLite okuma hatası: {e}") from e
