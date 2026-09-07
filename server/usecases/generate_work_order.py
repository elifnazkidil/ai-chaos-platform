"""
server/usecases/generate_work_order.py

Use Cases Katmanı — ERP İş Emri Üretme İş Akışı
================================================
Yapay zeka yüksek risk tespit ettiğinde otomatik ERP bilet oluşturur.

Gerçek dünya karşılığı:
  SAP Plant Maintenance → Otomatik PM Order oluşturma
  ServiceNow → Otomatik Incident Ticket açma

Öğrenilen Kavramlar (Gün 2):
  - Guard Clause: "Şart sağlanmıyorsa erken çık" — deep nesting'i önler
  - Enum'dan değer okuma: RiskLevel(risk_level_str)
  - Domain metod çağrısı: work_order nesnesinin iş kurallarını tetikle
  - Duplicate prevention: Aynı ajan için zaten açık iş emri varsa yeni açma
"""

from typing import Optional
from server.domain.entities import WorkOrder, RiskLevel, WorkOrderStatus
from server.infrastructure.database import DatabaseManager
from server.infrastructure.work_order_repo import WorkOrderRepository


# Hangi risk seviyelerinde iş emri oluşturulsun?
# NORMAL → İş emri açma
# MEDIUM ve üzeri → İş emri aç
TRIGGER_RISK_LEVELS = {
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
}


class GenerateWorkOrderUseCase:
    """
    AI tahmin sonucuna göre otomatik ERP İş Emri üreten Use Case.

    İş Akışı (Pipeline):
      1. PredictLeakUseCase → Agent metriklerinden tahminde bulunur
      2. GenerateWorkOrderUseCase → Tahmin sızıntı/risk gösteriyorsa iş emri oluşturur (bu dosya)
      3. Veritabanına kaydet → Duplicate kontrolüyle DB'ye ekler
      4. ERPUseCase → Dış ERP sistemine iletir

    İş Kuralları (Business Rules):
      1. Sadece MEDIUM, HIGH, CRITICAL risk seviyelerinde tetiklenir
      2. Aynı ajan için zaten PENDING/IN_PROGRESS iş emri varsa yeni açmaz
         (Duplicate flood prevention — gerçek sistemlerde kritik!)
      3. Oluşturulan iş emrini hem DB'ye kaydeder hem döndürür
    """

    def __init__(self, db: DatabaseManager):
        """
        :param db: Aktif DatabaseManager
        """
        self.work_order_repo = WorkOrderRepository(db)

    def execute(self, agent_id: str, prediction: dict) -> Optional[dict]:
        """
        Tahmin sonucuna göre iş emri oluşturur.

        :param agent_id: İş emri hangi ajan için açılacak
        :param prediction: PredictLeakUseCase'den gelen tahmin dict'i
                           Beklenen alanlar:
                             - risk_level: str
                             - estimated_seconds_to_oom: float | None
                             - current_ram_percent: float | None
                             - is_leak: bool

        :return: Oluşturulan WorkOrder'ın dict temsili, veya None (oluşturulmadıysa)
        """
        # ─── Guard Clause 1: Sızıntı Tespit Edilmedi mi? ─────
        # Sızıntı yoksa iş emri açmaya gerek yok, erken çık
        if not prediction.get("is_leak"):
            return None

        # ─── Guard Clause 2: Risk Seviyesi Tetikleme Eşiği ───
        risk_level_str = prediction.get("risk_level", "NORMAL")

        # String'i RiskLevel Enum'una dönüştür
        # Bilinmeyen risk_level string gelirse güvenli varsayılan: NORMAL
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            # "YETERSİZ VERİ" veya tanımlanmamış bir değer gelirse iş emri açma
            return None

        if risk_level not in TRIGGER_RISK_LEVELS:
            return None

        # ─── Guard Clause 3: Duplicate Flood Prevention ───────
        # Bu ajan için zaten açık (PENDING/IN_PROGRESS) iş emri var mı?
        existing_pending = self.work_order_repo.get_pending()
        agent_already_has_open_order = any(
            wo.agent_id == agent_id for wo in existing_pending
        )

        if agent_already_has_open_order:
            # Zaten açık iş emri var, yeni açma — mevcut olanı döndür
            existing = next(
                (wo for wo in existing_pending if wo.agent_id == agent_id),
                None
            )
            return {
                "already_existed": True,
                **(existing.to_dict() if existing else {})
            }

        # ─── İş Emri Oluştur ─────────────────────────────────
        # estimated_seconds_to_oom yoksa (None) güvenli bir default ata
        estimated_seconds = prediction.get("estimated_seconds_to_oom") or 999.0
        current_ram = prediction.get("current_ram_percent") or 0.0

        work_order = WorkOrder(
            agent_id=agent_id,
            risk_level=risk_level,
            estimated_seconds_to_oom=estimated_seconds,
            ram_percent_at_trigger=current_ram,
            # description → __post_init__ otomatik oluşturur (entities.py iş kuralı)
        )

        # ─── Veritabanına Kaydet ──────────────────────────────
        self.work_order_repo.save(work_order)

        # ─── Sonucu Döndür ────────────────────────────────────
        result = work_order.to_dict()
        result["already_existed"] = False

        print(
            f"[ERP IS EMRI OLUSTURULDU] "
            f"ID: {work_order.work_order_id} | "
            f"Ajan: {agent_id} | "
            f"Risk: {risk_level.value} | "
            f"Kalan: {work_order.urgency_minutes} dk"
        )

        return result

    def resolve_work_order(self, work_order_id: str) -> bool:
        """
        Bir iş emrini 'Çözüldü' olarak işaretler.

        Domain iş kuralını uygular (entities.py → .mark_resolved())
        ve değişikliği veritabanına yansıtır.

        :param work_order_id: Çözülecek iş emrinin ID'si
        :return: Başarılıysa True
        """
        work_order = self.work_order_repo.get_by_id(work_order_id)

        if not work_order:
            return False

        # Domain iş kuralı: sadece uygun durumlar geçiş yapabilir
        # Hatalı geçiş → ValueError (entities.py'deki state machine)
        work_order.mark_resolved()

        # DB'ye yansıt
        return self.work_order_repo.update_status(
            work_order_id=work_order_id,
            new_status=WorkOrderStatus.RESOLVED,
            resolved_at=work_order.resolved_at,
        )
