"""
server/usecases/interfaces/metric_repository.py

Use Cases Katmanı — Repository Arayüzü (Soyut Sözleşme)
=========================================================
Clean Architecture'da Dependency Inversion Principle (DIP):

  Use Case → soyut arayüze (interface) bağımlıdır
  Concrete repo (SQLite, PostgreSQL, Mock) → bu interface'i uygular

NEDEN ABC (Abstract Base Class)?
  - Python'da interface yoktur; ABC bunu simüle eder
  - @abstractmethod → alt sınıf bu metodu ZORUNLU implement etmelidir
  - Use Case bu dosyayı import eder, infrastructure'ı asla görmez

BAĞIMLILIK KURALI:
  ┌─────────────┐     ┌──────────────────┐     ┌──────────────────────┐
  │  Use Case   │────▶│  <<Interface>>   │◀────│  Infrastructure      │
  │ (saveMetric)│     │ MetricRepository │     │ SQLiteMetricRepository│
  └─────────────┘     └──────────────────┘     └──────────────────────┘
  
  Ok yönü: Use Case → Interface ← Infrastructure
  Use Case, Infrastructure'ı ASLA doğrudan import etmez.

Öğrenilen Python Kavramları:
  - ABC (Abstract Base Class)  : Soyut temel sınıf
  - @abstractmethod            : Alt sınıfın implement etmesi zorunlu
  - Protocol (alternatif)      : Python 3.8+ structural subtyping
"""

from abc import ABC, abstractmethod
from server.domain.entities import Metric


class MetricRepositoryInterface(ABC):
    """
    Metrik kalıcı depolama sözleşmesi.

    Bu sınıfı doğrudan INSTANTIATE EDEMEZSINIZ:
      repo = MetricRepositoryInterface()  # ← TypeError fırlatır!

    Kullanım:
      class SQLiteMetricRepository(MetricRepositoryInterface):
          def save(self, metric: Metric) -> Metric:
              # Gerçek SQLite yazma işlemi buraya
              ...
    """

    @abstractmethod
    def save(self, metric: Metric) -> Metric:
        """
        Metric entity'sini kalıcı depoya yazar.

        :param metric: Doğrulanmış Metric domain nesnesi
        :return:      Kaydedilmiş Metric (id zaten entity'de var)
        :raises RepositoryError: Veritabanı yazma hatası durumunda
        """
        ...

    @abstractmethod
    def exists(self, metric_id: str) -> bool:
        """
        Verilen ID'ye sahip bir metrik var mı?

        :param metric_id: UUID string
        :return: True → kayıt var, False → yok
        """
        ...

    @abstractmethod
    def get_latest_metrics(self, limit: int = 50) -> list[Metric]:
        """
        En son eklenen metrikleri getirir.
        
        :param limit: Getirilecek maksimum metrik sayısı
        :return: Metric nesnelerinden oluşan bir liste
        """
        ...
