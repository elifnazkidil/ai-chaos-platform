"""
server/infrastructure/erp_adapter.py

ERP Adaptör Katmanı
===================
Dış sistemlere (ServiceNow, SAP vb.) verileri göndermeden önce 
anomali veya bellek sızıntısı detaylarını SQL ile analiz eden katmandır.
"""

import sqlite3
from server.infrastructure.database import DatabaseManager

class ERPAdapter:
    def __init__(self, db: DatabaseManager):
        self._db = db

    def calculate_leak_rate(self, agent_id: str) -> float:
        """
        Belirli bir ajanın (sunucunun) son metriklerindeki bellek (RAM)
        sızıntı hızını hesaplar.
        
        KULLANILAN MANTIK:
        Şimdiki RAM miktarı - Bir önceki RAM miktarı = Sızıntı miktarı (Büyüme)

        SQL WINDOW FUNCTION:
        LAG(ram_used_gb, 1) OVER (PARTITION BY agent_id ORDER BY timestamp)
        
        PARTITION BY agent_id çok önemlidir! Yoksa farklı sunucuların 
        ram değerleri birbirine karışıp saçma sonuçlar üretir.
        """
        try:
            conn = self._db.get_connection()
            # Not: Kullanıcının kuralında 'system_metrics' tablosu ve 'server_id'
            # belirtilmiş ancak bizim SQLite şemamızda tablonun adı 'metrics',
            # sütunun adı ise 'agent_id'. Bu yüzden projemize uygun haliyle yazıyoruz.
            cursor = conn.execute(
                """
                SELECT leak_rate_gb
                FROM (
                    SELECT 
                        ram_used_gb - LAG(ram_used_gb, 1) OVER (
                            PARTITION BY agent_id 
                            ORDER BY timestamp
                        ) AS leak_rate_gb,
                        timestamp
                    FROM metrics
                    WHERE agent_id = ?
                )
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (agent_id,)
            )
            row = cursor.fetchone()
            
            # Yeterli veri yoksa (ilk satırsa) LAG null dönebilir.
            if row is None or row["leak_rate_gb"] is None:
                return 0.0
                
            return float(row["leak_rate_gb"])
            
        except sqlite3.Error as e:
            print(f"[ERP_ADAPTER] Sızıntı hızı hesaplanırken SQL hatası: {e}")
            return 0.0
