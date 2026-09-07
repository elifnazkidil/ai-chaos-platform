"""
server/usecases/get_latest_metrics.py

Use Cases Katmanı — Son Metrikleri Getirme
===========================================
Dashboard veya istemcilerin veritabanındaki en son metrikleri
okumasını sağlayan Use Case.
"""

from server.usecases.interfaces.metric_repository import MetricRepositoryInterface
from server.domain.entities import Metric

class GetLatestMetricsUseCase:
    """
    En son metrikleri getirmekten sorumlu iş mantığı sınıfı.
    """

    def __init__(self, metric_repo: MetricRepositoryInterface):
        """
        Dependency Injection (DIP): Hangi DB kullanıldığını bilmez,
        sadece MetricRepositoryInterface'e güvenir.
        """
        self.metric_repo = metric_repo

    def execute(self, limit: int = 50) -> list[Metric]:
        """
        Son limit kadar metriği getirir.

        Bu metodun işlevi oldukça basittir: metric_repo.get_latest_metrics(limit)
        metodunu çağırarak veritabanından en son limit kadar metriği alır 
        ve bu metrikleri döndürür.
        """
        return self.metric_repo.get_latest_metrics(limit=limit)
        #Bu metrikleri API katmanına döndürür. API katmanı bu metrikleri alır, 
        #JSON formatına çevirir ve istemciye (dashboard) gönderir.
