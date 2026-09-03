"""
server/infrastructure/database.py

Infrastructure Katmanı — SQLite Veritabanı Yöneticisi
=======================================================
Clean Architecture'da Infrastructure katmanı, dış dünyayla (DB, API, dosya sistemi)
konuşmaktan sorumludur. Domain ve Use Cases katmanları bu dosyadan habersizdir;
sadece Repository(kaydet ama sonrasi dgaf) arayüzlerini bilirler.

Öğrenilen Kavramlar (Gün 
  - Context Manager (__enter__ / __exit__): "with" bloklarında otomatik kaynak yönetimi
  - Singleton Pattern: Uygulama boyunca tek bir DatabaseManager örneği
  - CREATE TABLE IF NOT EXISTS: İdempotent (tekrar çalışsa hata vermez) tablo oluşturma
  - NOT NULL, PRIMARY KEY, TEXT/REAL: SQLite veri tipleri ve kısıtlamaları
"""

import sqlite3
import os
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# SORU: DB_PATH — nereye metrics.db yaratıyor?
#
# CEVAP: Path(__file__) bu dosyanın kendisinin tam yolunu verir.
#   Örnek: C:/proje/server/infrastructure/database.py
#
#   Yani PROJECT_ROOT = C:/proje
#   Ve   DB_PATH      = C:/proje/metrics.db
#
#   Bu sayede metrics.db her zaman projenin KÖK klasöründe oluşur,
#   hangi dizinden çalıştırırsan çalıştır fark etmez.
# ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "metrics.db"


# ─────────────────────────────────────────────────────────────
# SORU: CREATE_METRICS_TABLE — hangi sütunlar var, tipleri ne?
#
# CEVAP:
#   metric_id    → TEXT PRIMARY KEY : UUID string. PRIMARY KEY = her satır benzersiz,
#                                     aynı metric_id ile 2. kayıt giremez.
#   agent_id     → TEXT NOT NULL    : Hangi sunucudan geldi? Boş bırakılamaz.
#   timestamp    → TEXT NOT NULL    : Zaman damgası ISO 8601 string olarak saklanır.
#                                     Örn: "2026-08-11T08:00:00"
#   cpu_percent  → REAL NOT NULL    : CPU yüzdesi. REAL = ondalıklı sayı (float).
#   ram_percent  → REAL NOT NULL    : RAM yüzdesi. 0.0 ile 100.0 arası.
#   ram_used_gb  → REAL NOT NULL    : Kullanılan RAM miktarı gigabyte cinsinden.
#   ram_total_gb → REAL NOT NULL    : Toplam RAM kapasitesi gigabyte cinsinden.
#
#   SQLite'da sadece 5 tip var: TEXT, REAL, INTEGER, BLOB, NULL
#   Python'daki str  → TEXT
#   Python'daki float → REAL
#   Python'daki int  → INTEGER
#""" işaretleri koda dahildir ve içindeki SQL sorgusunu metin olarak paketlemeye yarar. Onları silersen veritabanı sorgusu bozulu ────────
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
#   work_order_id            → TEXT PRIMARY KEY : "WO-A1B2C3D4" formatında benzersiz ID.
#   agent_id                 → TEXT NOT NULL    : Hangi sunucu için açıldı?
#   risk_level               → TEXT NOT NULL    : "NORMAL", "ORTA", "YÜKSEK", "KRİTİK"
#   status                   → TEXT NOT NULL    : "BEKLEMEDE", "İŞLEMDE", "ÇÖZÜLDÜ"
#   description              → TEXT             : Açıklama metni. NOT NULL YOK = boş olabilir.
#   estimated_seconds_to_oom → REAL NOT NULL    : Tahmini çökme süresi (saniye).
#   ram_percent_at_trigger   → REAL NOT NULL    : Alarm anındaki RAM yüzdesi.
#   created_at               → TEXT NOT NULL    : İş emri oluşturulma zamanı. Her zaman dolu.
#   resolved_at              → TEXT             : Çözülme zamanı.

# entities.py
#@dataclass
#class Metric:
#    agent_id: str
#    cpu_percent: float
#    ram_percent: float
#    ... 
#
#   resolved_at neden NULL olabilir?
#   Çünkü iş emri henüz çözülmemiş olabilir! Bir alarm açıldığında resolved_at = NULL başlar.
#   Ancak iş emri ÇÖZÜLDÜ durumuna geçince bu sütuna zaman damgası yazılır.
#   NULL = "henüz gerçekleşmemiş" anlamına gelir.
#   NOT NULL yazsaydık, iş emri açılırken bile bir tarih vermek zorunda kalırdık — saçma olurdu.
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
    SQLite bağlantısını ve tablo şemasını yöneten merkezi sınıf.

    KULLANIM (Context Manager ile):
        with DatabaseManager() as db:
            cursor = db.cursor()
            cursor.execute("SELECT ...")

    Context Manager nedir?
    Python'da "with" bloğu ile kullanılan nesneler.
    __enter__: Blok başladığında çalışır (bağlantıyı açar)
    __exit__:  Blok bittiğinde çalışır (bağlantıyı kapatır, hata da olsa)
    """

    def __init__(self, db_path: str = None):
        """
        :param db_path: Veritabanı dosya yolu. None ise varsayılan proje DB'si kullanılır.
        """
        self.db_path = str(db_path or DB_PATH)
        self._connection: sqlite3.Connection = None
#       def get_connection(self):
#    if self._connection is None:  # henüz bağlantı yoksa
#        self._connection = sqlite3.connect(...)  # oluştur
#    return self._connection

# Alt çizgi _connection → "bu değişkene dışarıdan doğrudan erişme, sınıf içinde kullan" anlamında konvansiyon.

    def get_connection(self) -> sqlite3.Connection:
        """
        Aktif SQLite bağlantısını döner; yoksa yenisini oluşturur.

        check_same_thread=False: Farklı thread'lerden aynı bağlantıya erişime izin verir.
        Bu FastAPI gibi asenkron frameworkler için gereklidir.
        """
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            # ─────────────────────────────────────────────────────
            # SORU: row_factory ne işe yarıyor?
            #
            # CEVAP: Normalde SQLite sorgusundan dönen satırlar tuple'dır:
            #   row = (0.0, 45.2, 8.0, 16.0)
            #   row[0] = metric_id  ← hangi index ne anlama geliyor? Bilinmez!
            #
            # sqlite3.Row atarsak satırlar hem index hem de SÜTUN ADIYLA erişilebilir:
            #   row["ram_percent"]  ← çok daha okunabilir!
            #   row["cpu_percent"]  ← hangi değer olduğu açık
            #   row[3]              ← eski yöntem hâlâ çalışır
            #
            # Özetle: row_factory = sqlite3.Row, SQL sonuçlarını
            # sözlük gibi (dict-like) erişilebilir yapar.
            # ─────────────────────────────────────────────────────
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def initialize_schema(self) -> None:
        """
        Veritabanı tablolarını oluşturur (yoksa).
        Uygulama ilk başladığında bir kez çağrılır.

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
        """Bağlantıyı güvenli şekilde kapatır."""
        if self._connection:
            self._connection.close()
            self._connection = None

    # ─────────────────────────────────────────────────────────
    # SORU: __enter__ / __exit__ — context manager nasıl çalışıyor?
    #
    # CEVAP: Python'da "with" anahtar kelimesi kullanıldığında
    #
    #   Örnek kullanım:
    #     with DatabaseManager() as db:   ← __enter__ çalışır, db = self döner
    #         db.get_connection()          ← normal kodun çalıştığı yer
    #     ← buraya gelince __exit__ çalışır, bağlantı kapatılır
    #
    #   Context Manager'ın avantajı:
    #     Normalde şöyle yazman gerekirdi:
    #       db = DatabaseManager()
    #       db.initialize_schema()
    #       try:
    #   Python otomatik olarak __enter__ ve __exit__ metodlarını çağırır.
    #           ... kod ...
    #       finally:
    #           db.close()    ← hata olsa bile kapat!
    #
    #     Context Manager bunu otomatik yapar. "finally" bloğunu
    #     sen yazmak zorunda kalmazsın, __exit__ her zaman çalışır.
    #
    #   __exit__ parametreleri:
    #     exc_type → Hata varsa hata sınıfı (ValueError gibi), yoksa None
    #     exc_val  → Hata varsa hata mesajı, yoksa None
    #     exc_tb   → Hata varsa traceback bilgisi, yoksa None
    #     False döndürmek → Hata olursa onu bastırma, yukarıya ilet
    # ─────────────────────────────────────────────────────────
    def __enter__(self) -> "DatabaseManager":
        """'with DatabaseManager() as db:' bloğu başladığında çalışır."""
        self.initialize_schema()
        return self  # "as db" kısmına atanan değer bu: self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """'with' bloğu bittiğinde — hata olsa da olmasa da — çalışır."""
        self.close()
        return False  # Hataları bastırma, yukarı ilet


# ─────────────────────────────────────────────────────────────
# SORU: get_db() — singleton pattern nedir, neden tek instance?
#
#
#   Neden tek instance?
#   Her seferinde yeni DatabaseManager() açsaydık:
#     - Her istek için yeni SQLite bağlantısı açılır → yavaş
#     - Birden fazla bağlantı aynı dosyayı yazarsa çakışma riski
#     - Her bağlantıyı ayrı ayrı kapatmak gerekir → kaynak sızıntısı
#
#   Singleton ile:
#     - Bağlantı bir kez açılır, hep aynısı kullanılır → hızlı
#     - Tüm Repository'ler aynı bağlantıyı paylaşır → tutarlı
#Tek SQLite dosya bağlantısı, iki repo tarafından kullanılır.
#
#   Nasıl çalışır?
#     _db_manager = None    ← başta yok
#
#     get_db() ilk kez çağrılınca:
#       _db_manager is None → True → yeni oluştur, şemayı başlat
#
#     get_db() ikinci kez çağrılınca:
#       _db_manager is None → False → var olanı döndür, yenisini açma!
#
#   "global _db_manager" satırı neden var?
#   Python'da fonksiyon içinde global bir değişkene YAZMAk için
#   "global" bildirimi şarttır. Okumak için gerekmez ama değiştirmek için gerekir.
# ─────────────────────────────────────────────────────────────
_db_manager: DatabaseManager = None


def get_db() -> DatabaseManager:
    global _db_manager          # Bu fonksiyon _db_manager'ı değiştireceğini Python'a bildir
    if _db_manager is None:     # İlk kez mi çağrılıyor?
        _db_manager = DatabaseManager()   # Evet → yeni nesne oluştur
        _db_manager.initialize_schema()   # Tabloları yarat (yoksa)
    return _db_manager          # Her zaman aynı nesneyi döndür
