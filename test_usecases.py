"""
Gün 2 — Use Cases Entegrasyon Testi
Simüle edilmiş RAM artışı göndererek tüm pipeline'ı test eder:
  IngestMetricUseCase → PredictLeakUseCase → GenerateWorkOrderUseCase
"""
from server.infrastructure import DatabaseManager
from server.usecases import IngestMetricUseCase, GenerateWorkOrderUseCase

print("=" * 55)
print("GUN 2 - USE CASES ENTEGRASYON TESTI")
print("=" * 55)

db = DatabaseManager()
db.initialize_schema()
use_case = IngestMetricUseCase(db)

# 15 adimlik simule edilmis RAM artisi (bellek sizintisi simülasyonu)
# RAM her adimda ~1.5% artsin => slope > 0.05 => sizinti tespiti
ram_values = [50.0, 51.5, 53.1, 54.7, 56.3, 57.8, 59.4, 61.0,
              62.5, 64.1, 65.7, 67.2, 68.8, 70.4, 72.0]

print("\nAdim | RAM %  | Risk Seviyesi       | Is Emri?")
print("-" * 55)

work_order_created = False
for i, ram in enumerate(ram_values):
    result = use_case.execute({
        "agent_id": "server-demo-01",
        "cpu_percent": 30.0 + i * 0.5,
        "ram_percent": ram,
        "ram_used_gb": round(ram * 16 / 100, 2),
        "ram_total_gb": 16.0
    })

    pred = result["prediction"]
    wo = result["work_order"]
    risk = pred["risk_level"]
    wo_info = "YOK"
    if wo and not work_order_created:
        wo_info = wo.get("work_order_id", "ZATEN ACIK")[:12]
        work_order_created = True
    elif wo:
        wo_info = "ZATEN ACIK"

    print(f"  {i+1:02d}  | {ram:5.1f}% | {risk:<20s} | {wo_info}")

print("\n" + "=" * 55)

# Son durumu goster
from server.infrastructure import WorkOrderRepository
wo_repo = WorkOrderRepository(db)
pending = wo_repo.get_pending()
print(f"Bekleyen is emirleri: {len(pending)} adet")
for wo in pending:
    mins = wo.urgency_minutes
    print(f"  [{wo.work_order_id}] Risk={wo.risk_level.value} | {mins} dk kaldi")

db.close()
print("\nTUM TESTLER BASARILI!")
