"""
server/usecases/erp_usecase.py

Use Cases Katmanı — Dış ERP Sistemi Entegrasyonu
=================================================
Bu modül, GenerateWorkOrderUseCase tarafından oluşturulan iş emirlerini
dış bir ERP sistemine (SAP PM, ServiceNow vb.) göndermeyi simüle eder.

Gerçek dünya karşılığı:
  - SAP PM'e REST API ile otomatik iş emri göndermek
  - ServiceNow'a Incident Ticket açmak
  - Jira Service Desk'e Issue oluşturmak

"""

import time
from datetime import datetime
from typing import Optional

from server.domain.entities import WorkOrder, RiskLevel
from server.infrastructure.database import DatabaseManager
from server.infrastructure.work_order_repo import WorkOrderRepository
from server.usecases.generate_work_order import GenerateWorkOrderUseCase
from server.api.decorators import log_execution_time


# ═══════════════════════════════════════════════════════════════
# ANA SINIF: ERPUseCase
# ═══════════════════════════════════════════════════════════════
class ERPUseCase:
    """
    Sistemimizde oluşan yüksek riskli iş emirlerini (Work Order) dış bir ERP
    sistemine (örn: SAP PM, ServiceNow) göndermeyi simüle eden Use Case.

    İş Akışı (Pipeline):
      1. AI tahmin yap → risk_level belirle
      2. GenerateWorkOrderUseCase → iş emri oluştur & DB'ye kaydet
      3. ERPUseCase → iş emrini dış ERP sistemine gönder (bu dosya)
      4. Başarılıysa log kaydı tut, başarısızsa retry (yeniden dene)
    """

    # ── Sınıf Sabitleri (Class Constants) ─────────────────────
    # Dış ERP sistemine bağlanamazsa kaç kere yeniden deneyecek?
    MAX_RETRY_COUNT = 3
    # Her yeniden denemede kaç saniye bekleyecek?
    RETRY_DELAY_SECONDS = 2.0

    def __init__(self, db: DatabaseManager):
        """
        :param db: Aktif DatabaseManager — iş emri repository'sine erişim için
        """
        self.work_order_repo = WorkOrderRepository(db)
        self.generate_wo_uc = GenerateWorkOrderUseCase(db)

        # Gönderilen iş emirlerinin logunu tutar (in-memory)
        self.dispatch_log: list[dict] = []

    # ── Ana Metod: Dış ERP'ye Gönder ─────────────────────────
    @log_execution_time
    def send_to_erp(self, work_order_data: dict) -> dict:
        """
        Oluşturulmuş bir iş emrini dış ERP sistemine gönderir (Simülasyon).

        Biz burada ağ gecikmesini time.sleep() ile simüle ediyoruz.

        :param work_order_data: İş emrinin dict temsili (WorkOrder.to_dict() çıktısı)
        Dış Sistemler Nesne Değil, JSON (Dict) Anlar
        :return: Gönderim sonucu dict'i (başarı/hata bilgisi)
        """
        wo_id = work_order_data.get("work_order_id", "BİLİNMİYOR")
        risk = work_order_data.get("risk_level", "BİLİNMİYOR")

        print(f"[ERP] Sisteme baglaniliyor... Is Emri: {wo_id} | Risk: {risk}")

        # ─── Retry Pattern (Yeniden Deneme Mantığı) ───────────
        # Dış sistemler her zaman cevap vermeyebilir (ağ hatası, timeout vb.)
        # Bu yüzden başarısız olursa belirli sayıda yeniden deneriz
        for attempt in range(1, self.MAX_RETRY_COUNT + 1):
            try:
                # Gerçek dünyada: requests.post(...) olurdu
                # Simülasyon: 0.5 saniye ağ gecikmesi
                time.sleep(0.5)

                # Simüle başarılı yanıt
                erp_response = {
                    "erp_ticket_id": f"SAP-PM-{wo_id}",
                    "status": "CREATED",
                    "timestamp": datetime.utcnow().isoformat(),
                }

                print(f"[OK] ERP yaniti alindi: {erp_response['erp_ticket_id']} (Deneme {attempt}/{self.MAX_RETRY_COUNT})")

                # Başarılı gönderimi logla
                log_entry = {
                    "work_order_id": wo_id,
                    "erp_ticket_id": erp_response["erp_ticket_id"],
                    "dispatched_at": erp_response["timestamp"],
                    "attempt": attempt,
                    "success": True,
                }
                self.dispatch_log.append(log_entry)

                return {
                    "success": True,
                    "erp_response": erp_response,
                    "attempts": attempt,
                }

            except Exception as e:
                print(f"[UYARI] Deneme {attempt}/{self.MAX_RETRY_COUNT} basarisiz: {e}")
                if attempt < self.MAX_RETRY_COUNT:
                    print(f"[BEKLEME] {self.RETRY_DELAY_SECONDS} saniye sonra yeniden denenecek...")
                    time.sleep(self.RETRY_DELAY_SECONDS)

        # Tüm denemeler başarısız
        fail_entry = {
            "work_order_id": wo_id,
            "erp_ticket_id": None,
            "dispatched_at": datetime.utcnow().isoformat(),
            "attempt": self.MAX_RETRY_COUNT,
            "success": False,
        }
        self.dispatch_log.append(fail_entry)

        return {
            "success": False,
            "error": f"{self.MAX_RETRY_COUNT} deneme sonrası ERP sistemine ulaşılamadı.",
            "attempts": self.MAX_RETRY_COUNT,
        }

    # ── Tam Akış: Tahmin → İş Emri → ERP Gönderimi ──────────
    @log_execution_time
    def trigger_full_pipeline(self, agent_id: str, prediction: dict) -> dict:
        """
        Tüm ERP iş emri akışını tek bir metod ile tetikler:
          1. prediction verisinden iş emri oluştur (GenerateWorkOrderUseCase)
          2. Oluşturulan iş emrini ERP'ye gönder (send_to_erp)
          3. Sonucu döndür

        :param agent_id: Hangi sunucu/ajan için
        :param prediction: AI tahmin sonucu dict'i
        :return: Tam pipeline sonucu
        """
        # Adım 1: İş emri oluştur
        wo_result = self.generate_wo_uc.execute(
            agent_id=agent_id,
            prediction=prediction,
        )

        # Guard Clause: İş emri oluşturulmadıysa (risk düşük veya zaten mevcut)
        if wo_result is None:
            return {
                "pipeline": "SKIPPED",
                "reason": "Risk seviyesi düşük veya sızıntı tespit edilmedi.",
            }

        # Zaten açık iş emri varsa ERP'ye tekrar gönderme
        if wo_result.get("already_existed"):
            return {
                "pipeline": "SKIPPED",
                "reason": "Bu ajan için zaten açık bir iş emri mevcut.",
                "existing_order": wo_result,
            }

        # Adım 2: Yeni iş emrini ERP'ye gönder
        erp_result = self.send_to_erp(wo_result)

        return {
            "pipeline": "COMPLETED" if erp_result["success"] else "FAILED",
            "work_order": wo_result,
            "erp_dispatch": erp_result,
        }

    # ── Log Sorgulama ─────────────────────────────────────────
    def get_dispatch_history(self) -> list[dict]:
        """Bugüne kadar ERP'ye gönderilen tüm iş emirlerinin logunu döndürür."""
        return self.dispatch_log
