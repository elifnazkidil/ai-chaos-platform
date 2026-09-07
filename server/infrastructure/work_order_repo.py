"""
server/infrastructure/work_order_repo.py

Infrastructure Katmanı — WorkOrder Repository
==============================================
ERP İş Emirlerinin SQLite üzerinde yaşam döngüsünü yöneten Repository.

Öğrenilen Kavramlar (Gün 2):
  - UPDATE ... WHERE: Belirli satırı güncelleme
  - Enum ↔ String dönüşümü: .value ile string'e, Enum() ile geri
  - Optional[WorkOrder]: Bulunamayan kayıt için None dönebiliriz
"""

import sqlite3
from typing import List, Optional
from server.domain.entities import WorkOrder, RiskLevel, WorkOrderStatus
from server.infrastructure.database import DatabaseManager


class WorkOrderRepository:
    """
    WorkOrder domain entity'lerinin SQLite'a yazılmasını,
    okunmasını ve güncellenmesini sağlayan Repository sınıfı.
    """

    def __init__(self, db: DatabaseManager):
        """
        :param db: Aktif DatabaseManager bağlantısı
        """
        self.db = db

    def save(self, work_order: WorkOrder) -> bool:
        """
        Yeni bir WorkOrder kaydeder.

        INSERT OR IGNORE: Aynı work_order_id ile tekrar gönderim olursa
        sessizce geçer — idempotent davranış.

        :param work_order: Kaydedilecek WorkOrder nesnesi
        :return: Başarıyla eklendiyse True
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO work_orders
                (work_order_id, agent_id, risk_level, status, description,
                 estimated_seconds_to_oom, ram_percent_at_trigger, created_at, resolved_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_order.work_order_id,
                work_order.agent_id,
                work_order.risk_level.value,      # Enum → string (.value)
                work_order.status.value,           # Enum → string (.value)
                work_order.description,
                work_order.estimated_seconds_to_oom,
                work_order.ram_percent_at_trigger,
                work_order.created_at.isoformat(),
                work_order.resolved_at.isoformat() if work_order.resolved_at else None,
            )
        )
        conn.commit()
        return cursor.rowcount > 0

    def update_status(self, work_order_id: str, new_status: WorkOrderStatus,
                      resolved_at=None) -> bool:
        """
        Mevcut bir iş emrinin durumunu günceller.

        Domain katmanında .mark_resolved() çağrıldıktan sonra,
        bu değişikliği veritabanına yansıtmak için kullanılır.

        UPDATE ... WHERE: Sadece belirtilen satırı değiştir.

        :param work_order_id: Güncellenecek iş emrinin ID'si
        :param new_status: Yeni durum (WorkOrderStatus Enum)
        :param resolved_at: Çözüm zamanı (sadece RESOLVED için)
        :return: Güncelleme başarılıysa True
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE work_orders
            SET status = ?, resolved_at = ?
            WHERE work_order_id = ?
            """,
            (
                new_status.value,
                resolved_at.isoformat() if resolved_at else None,
                work_order_id,
            )
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_by_id(self, work_order_id: str) -> Optional[WorkOrder]:
        """
        ID'ye göre tek bir iş emri döner.

        Optional[WorkOrder]: Bulunamazsa None döner.
        Bu, Python'da "bulunamama" durumunu temsil etmenin idiomatik yoludur.

        :param work_order_id: Aranacak iş emri ID'si
        :return: WorkOrder nesnesi veya None
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM work_orders
            WHERE work_order_id = ?
            """,
            (work_order_id,)
        )

        row = cursor.fetchone()
        return self._row_to_work_order(row) if row else None

    def get_pending(self) -> List[WorkOrder]:
        """
        Henüz çözülmemiş (PENDING veya IN_PROGRESS) tüm iş emirlerini döner.
        Dashboard'da "Aktif Alarmlar" paneli bu metodu kullanır.

        SQL IN Operatörü: WHERE status IN ('BEKLEMEDE', 'İŞLEMDE')

        :return: Bekleyen WorkOrder listesi
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM work_orders
            WHERE status IN (?, ?)
            ORDER BY created_at DESC
            """,
            (WorkOrderStatus.PENDING.value, WorkOrderStatus.IN_PROGRESS.value)
        )

        rows = cursor.fetchall()
        return [self._row_to_work_order(row) for row in rows]

    def get_all(self, limit: int = 50) -> List[WorkOrder]:
        """
        Tüm iş emirlerini (en yeni önce) döner.

        :param limit: Maksimum kayıt sayısı
        :return: WorkOrder listesi
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM work_orders
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )

        rows = cursor.fetchall()
        return [self._row_to_work_order(row) for row in rows]

    def count_by_agent(self, agent_id: str) -> int:
        """
        Bir ajana ait toplam iş emri sayısı.

        :param agent_id: Ajan kimliği
        :return: Toplam iş emri sayısı
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM work_orders WHERE agent_id = ?",
            (agent_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0

    # ── Private Yardımcı Metod ────────────────────────────────
    @staticmethod
    def _row_to_work_order(row: sqlite3.Row) -> WorkOrder:
        """
        SQLite satırını WorkOrder domain entity'ye dönüştürür.

        Enum Geri Dönüşümü:
          DB'de "KRİTİK (CRITICAL)" stringi saklı.
          RiskLevel(row["risk_level"]) → RiskLevel.CRITICAL Enum'una dönüştürür.
          Enum değeri eşleşmezse ValueError fırlatır.

        :param row: sqlite3.Row nesnesi
        :return: WorkOrder domain entity
        """
        from datetime import datetime

        return WorkOrder(
            work_order_id=row["work_order_id"],
            agent_id=row["agent_id"],
            risk_level=RiskLevel(row["risk_level"]),           # string → Enum
            status=WorkOrderStatus(row["status"]),             # string → Enum
            description=row["description"],
            estimated_seconds_to_oom=row["estimated_seconds_to_oom"],
            ram_percent_at_trigger=row["ram_percent_at_trigger"],
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"] else None
            ),
        )
