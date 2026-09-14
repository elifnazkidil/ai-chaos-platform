"""
server/infrastructure/database.py

Infrastructure Katmani — SQLite Veritabani Yöneticisi
=======================================================
Clean Architecture'da Infrastructure katmani, diş dünyayla (DB, API, dosya sistemi)
konuşmaktan sorumludur. Domain ve Use Cases katmanlari bu dosyadan habersizdir;
sadece Repository(kaydet ama sonrasi dgaf) arayüzlerini bilirler.

Öğrenilen Kavramlar 
  - Context Manager (__enter__ / __exit__): "with" bloklarinda otomatik kaynak yönetimi
  - Singleton Pattern: Uygulama boyunca tek bir DatabaseManager örneği
  - NOT NULL, PRIMARY KEY, TEXT/REAL: SQLite veri tipleri ve kisitlamalari
"""

import sqlite3
import os
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# SORU: DB_PATH — nereye metrics.db yaratiyor?
#
# CEVAP: Path(__file__) bu dosyanin kendisinin tam yolunu verir.
#   Örnek: C:/proje/server/infrastructure/database.py
#
#   Yani PROJECT_ROOT = C:/proje
#   Ve   DB_PATH      = C:/proje/metrics.db
#
#   Bu sayede metrics.db her zaman projenin KÖK klasöründe oluşur,
#   hangi dizinden çaliştirirsan çaliştir fark etmez.
# ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "metrics.db"


# ─────────────────────────────────────────────────────────────
# SORU: CREATE_METRICS_TABLE — hangi sütunlar var, tipleri ne?
#
# CEVAP:
#   metric_id    → TEXT PRIMARY KEY : UUID string. PRIMARY KEY = her satir benzersiz,
#                                     ayni metric_id ile 2. kayit giremez.
#   agent_id     → TEXT NOT NULL    : Hangi sunucudan geldi? Boş birakilamaz.
#   timestamp    → TEXT NOT NULL    : Zaman damgasi ISO 8601 string olarak saklanir.
#                                     Örn: "2026-08-11T08:00:00"
#   cpu_percent  → REAL NOT NULL    : CPU yüzdesi. REAL = ondalikli sayi (float).
#   ram_percent  → REAL NOT NULL    : RAM yüzdesi. 0.0 ile 100.0 arasi.
#   ram_used_gb  → REAL NOT NULL    : Kullanilan RAM miktari gigabyte cinsinden.
#   ram_total_gb → REAL NOT NULL    : Toplam RAM kapasitesi gigabyte cinsinden.
#
#   SQLite'da sadece 5 tip var: TEXT, REAL, INTEGER, BLOB, NULL
#   Python'daki str  → TEXT
#   Python'daki float → REAL
#   Python'daki int  → INTEGER
#   işaretleri koda dahildir ve içindeki SQL sorgusunu metin olarak paketlemeye yarar. Onlari silersen veritabani sorgusu bozulu ────────
# ─────────────────────────────────────────────────────
CREATE_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS metrics (
    metric_id     TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    cpu_percent   REAL NOT NULL,
    ram_percent   REAL NOT NULL,
    ram_used_gb   REAL NOT NULL,
    ram_total_gb  REAL NOT NULL
);
"""

# ─────────────────────────────────────────────────────────────
# SORU: CREATE_WORK_ORDERS_TABLE — hangi sütunlar var,
#       resolved_at neden NULL olabilir?
#
# CEVAP:
#   work_order_id            → TEXT PRIMARY KEY : "WO-A1B2C3D4" formatinda benzersiz ID.
#   agent_id                 → TEXT NOT NULL    : Hangi sunucu için açildi?
#   risk_level               → TEXT NOT NULL    : "NORMAL", "ORTA", "YÜKSEK", "KRİTİK"
#   status                   → TEXT NOT NULL    : "BEKLEMEDE", "İŞLEMDE", "ÇÖZÜLDÜ"
#   description              → TEXT             : Açiklama metni. NOT NULL YOK = boş olabilir.
#   estimated_seconds_to_oom → REAL NOT NULL    : Tahmini çökme süresi (saniye).
#   ram_percent_at_trigger   → REAL NOT NULL    : Alarm anindaki RAM yüzdesi.
#   created_at               → TEXT NOT NULL    : İş emri oluşturulma zamani. Her zaman dolu.
#   resolved_at              → TEXT             : Çözülme zamani.

# entities.py
#@dataclass
#class Metric:
#    agent_id: str
#    cpu_percent: float
#    ram_percent: float
#    ... 
#
#   resolved_at neden NULL olabilir?
#   Çünkü iş emri henüz çözülmemiş olabilir! Bir alarm açildiğinda resolved_at = NULL başlar.
#   Ancak iş emri ÇÖZÜLDÜ durumuna geçince bu sütuna zaman damgasi yazilir.
#   NULL = "henüz gerçekleşmemiş" anlamina gelir.
#   NOT NULL yazsaydik, iş emri açilirken bile bir tarih vermek zorunda kalirdik — saçma olurdu.
# ─────────────────────────────────────────────────────────────
CREATE_WORK_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS work_orders (
    work_order_id            TEXT PRIMARY KEY,
    agent_id                 TEXT NOT NULL,
    risk_level               TEXT NOT NULL,
    status                   TEXT NOT NULL,
    description              TEXT,
    estimated_seconds_to_oom REAL NOT NULL,
    ram_percent_at_trigger   REAL NOT NULL,
    created_at               TEXT NOT NULL,
    resolved_at              TEXT
);
"""


class DatabaseManager:
    """
    SQLite bağlantisini ve tablo şemasini yöneten merkezi sinif.

    KULLANIM (Context Manager ile):
        with DatabaseManager() as db:
            cursor = db.cursor()
            cursor.execute("SELECT ...")

    Context Manager nedir?
    Python'da "with" bloğu ile kullanilan nesneler.
    __enter__: Blok başladiğinda çalişir (bağlantiyi açar)
    __exit__:  Blok bittiğinde çalişir (bağlantiyi kapatir, hata da olsa)
    """

    def __init__(self, db_path: str = None):
        """
        :param db_path: Veritabani dosya yolu. None ise varsayilan proje DB'si kullanilir.
        """
        self.db_path = str(db_path or DB_PATH)
        self._connection: sqlite3.Connection = None
#       def get_connection(self):
#    if self._connection is None:  # henüz bağlanti yoksa
#        self._connection = sqlite3.connect(...)  # oluştur
#    return self._connection

# Alt çizgi _connection → "bu değişkene dişaridan doğrudan erişme, sinif içinde kullan" anlaminda konvansiyon.

    def get_connection(self) -> sqlite3.Connection:
        """
        Aktif SQLite bağlantisini döner; yoksa yenisini oluşturur.

        check_same_thread=False: Farkli thread'lerden ayni bağlantiya erişime izin verir.
        Bu FastAPI gibi asenkron frameworkler için gereklidir.
        """
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            # ─────────────────────────────────────────────────────
            # SORU: row_factory ne işe yariyor?
            #
            # CEVAP: Normalde SQLite sorgusundan dönen satirlar tuple'dir:
            #   row = (0.0, 45.2, 8.0, 16.0)
            #   row[0] = metric_id  ← hangi index ne anlama geliyor? Bilinmez!
            #
            # sqlite3.Row atarsak satirlar hem index hem de SÜTUN ADIYLA erişilebilir:
            #   row["ram_percent"]  ← çok daha okunabilir!
            #   row["cpu_percent"]  ← hangi değer olduğu açik
            #   row[3]              ← eski yöntem hâlâ çalişir
            #
            # Özetle: row_factory = sqlite3.Row, SQL sonuçlarini
            # sözlük gibi (dict-like) erişilebilir yapar.
            # ─────────────────────────────────────────────────────
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def initialize_schema(self) -> None:
        """
        Veritabani tablolarini oluşturur (yoksa).
        Uygulama ilk başladiğinda bir kez çağrilir.

        IF NOT EXISTS sayesinde tablolar zaten varsa hata vermez — idempotent!
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Metrik tablosunu oluştur
        cursor.execute(CREATE_METRICS_TABLE)

        # İş emri tablosunu oluştur
        cursor.execute(CREATE_WORK_ORDERS_TABLE)

        # Değişiklikleri diske yaz
        conn.commit()
        print(f"[DB] Sema basariyla baslatildi -> {self.db_path}")

    def close(self) -> None:
        """Bağlantiyi güvenli şekilde kapatir."""
        if self._connection:
            self._connection.close()
            self._connection = None

    # ─────────────────────────────────────────────────────────
    # SORU: __enter__ / __exit__ — context manager nasil çalişiyor?
    #
    # CEVAP: Python'da "with" anahtar kelimesi kullanildiğinda
    #
    #   Örnek kullanim:
    #     with DatabaseManager() as db:   ← __enter__ çalişir, db = self döner
    #         db.get_connection()          ← normal kodun çaliştiği yer
    #     ← buraya gelince __exit__ çalişir, bağlanti kapatilir
    #
    #   Context Manager'in avantaji:
    #     Normalde şöyle yazman gerekirdi:
    #       db = DatabaseManager()
    #       db.initialize_schema()
    #       try:
    #   Python otomatik olarak __enter__ ve __exit__ metodlarini çağirir.
    #           ... kod ...
    #       finally:
    #           db.close()    ← hata olsa bile kapat!
    #
    #     Context Manager bunu otomatik yapar. "finally" bloğunu
    #     sen yazmak zorunda kalmazsin, __exit__ her zaman çalişir.
    #
    #   __exit__ parametreleri:
    #     exc_type → Hata varsa hata sinifi (ValueError gibi), yoksa None
    #     exc_val  → Hata varsa hata mesaji, yoksa None
    #     exc_tb   → Hata varsa traceback bilgisi, yoksa None
    #     False döndürmek → Hata olursa onu bastirma, yukariya ilet
    # ─────────────────────────────────────────────────────────
    def __enter__(self) -> "DatabaseManager":
        """'with DatabaseManager() as db:' bloğu başladiğinda çalişir."""
        self.initialize_schema()
        return self  # "as db" kismina atanan değer bu: self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """'with' bloğu bittiğinde — hata olsa da olmasa da — çalişir."""
        self.close()
        return False  # Hatalari bastirma, yukari ilet


# ─────────────────────────────────────────────────────────────
# SORU: get_db() — singleton pattern nedir, neden tek instance?
#
#
#   Neden tek instance?
#   Her seferinde yeni DatabaseManager() açsaydik:
#     - Her istek için yeni SQLite bağlantisi açilir → yavaş
#     - Birden fazla bağlanti ayni dosyayi yazarsa çakişma riski
#     - Her bağlantiyi ayri ayri kapatmak gerekir → kaynak sizintisi
#
#   Singleton ile:
#     - Bağlanti bir kez açilir, hep aynisi kullanilir → hizli
#     - Tüm Repository'ler ayni bağlantiyi paylaşir → tutarli
#Tek SQLite dosya bağlantisi, iki repo tarafindan kullanilir.
#
#   Nasil çalişir?
#     _db_manager = None    ← başta yok
#
#     get_db() ilk kez çağrilinca:
#       _db_manager is None → True → yeni oluştur, şemayi başlat
#
#     get_db() ikinci kez çağrilinca:
#       _db_manager is None → False → var olani döndür, yenisini açma!
#
#   "global _db_manager" satiri neden var?
#   Python'da fonksiyon içinde global bir değişkene YAZMAk için
#   "global" bildirimi şarttir. Okumak için gerekmez ama değiştirmek için gerekir.
# ─────────────────────────────────────────────────────────────
_db_manager: DatabaseManager = None


def get_db() -> DatabaseManager:
    global _db_manager          # Bu fonksiyon _db_manager'i değiştireceğini Python'a bildir
    if _db_manager is None:     # İlk kez mi çağriliyor?
        _db_manager = DatabaseManager()   # Evet → yeni nesne oluştur
        _db_manager.initialize_schema()   # Tablolari yarat (yoksa)
    return _db_manager          # Her zaman ayni nesneyi döndür
