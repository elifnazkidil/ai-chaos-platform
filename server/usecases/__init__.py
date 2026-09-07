"""
server/usecases/__init__.py

Use Cases katmanının dışa aktardığı sınıflar.
Dışarıdan şöyle import edilebilir:

    from server.usecases import IngestMetricUseCase, PredictLeakUseCase, GenerateWorkOrderUseCase
    from server.usecases import SaveMetricUseCase, MetricResult
"""

from server.usecases.ingest_metric import IngestMetricUseCase
from server.usecases.predict_leak import PredictLeakUseCase
from server.usecases.generate_work_order import GenerateWorkOrderUseCase

# Gün 3 — Clean Architecture Use Case (timestamp + metrics doğrulama)
from server.usecases.save_metric import SaveMetricUseCase, MetricResult

__all__ = [
    "IngestMetricUseCase",
    "PredictLeakUseCase",
    "GenerateWorkOrderUseCase",
    # Gün 3
    "SaveMetricUseCase",
    "MetricResult",
]
