"""
server/domain/exceptions.py

Domain Katmanı — Özel Exception'lar
=====================================
Clean Architecture'da hata tipleri de domain'e aittir.

NEDEN ÖZEL EXCEPTION?
  - ValueError çok geneldir → "ne tür hata?" belirsiz
  - InvalidMetricError → "metrik verisi geçersiz" → üst katman bunu yakalar
  - HTTP katmanı: InvalidMetricError → 400, RepositoryError → 500

HTTP Bilgisi Yok:
  Bu dosya ASLA fastapi, flask, http_status gibi şeyler import etmez.
  Hata → HTTP durum kodu çevirisi API katmanında yapılır.





Sınıf							Sizin Kodunuzdaki Karşılığı				Anlamı
 ValueError							InvalidMetricError						"Gelen veri formatı yanlış"
RuntimeError							RepositoryError							"Veritabanı çalışmıyor"


  
"""


class InvalidMetricError(ValueError):
    """
    Gelen payload doğrulama hatası.

    Fırlatılma koşulları:
      - Zorunlu alan eksik (agent_id, timestamp, metrics)
      - timestamp ISO 8601 formatında değil
      - metrics değerleri numeric değil
      - metrics değerleri mantıksal aralık dışında (örn: cpu > 100)

    API Katmanında Karşılığı: HTTP 400 Bad Request
    """
    pass


class RepositoryError(RuntimeError):
    """
    Veritabanı yazma/okuma hatası.

    Fırlatılma koşulları:
      - SQLite bağlantı hatası
      - Disk dolu
      - Şema uyuşmazlığı

    API Katmanında Karşılığı: HTTP 500 Internal Server Error
    """
    pass
