"""
server/domain/entities.py

Domain Katmanı — Saf İş Varlıkları (Pure Business Entities)
============================================================
Clean Architecture'ın kalbi. Bu dosya:
  - Hiçbir framework'e bağımlı DEĞİLDİR (FastAPI, SQLite, psutil YOK)
  - Sadece Python standart kütüphanesi kullanır
  - İş kurallarını (business rules) barındırır

Öğrenilen Python Kavramları (Gün 1):
  - dataclass : Otomatik __init__, __repr__, __eq__ üreten dekoratör
  - Optional[X]: Değer olabilir ya da None olabilir
  - @property  : Hesaplanmış özellik (read-only)

"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

class generete_id():
    def __init__(self):
        self.uuid = uuid.uuid4()
        self.id = str(self.uuid)

class RiskLevel(Enum):
    """
    Bellek kullanımının tehlike seviyesi.

    NEDEN ENUM?
    Düz string yerine Enum kullanmak:
      - Yazım hatalarını engeller  → "CRITIKAL" yerine RiskLevel.CRITICAL
      - IDE otomatik tamamlama sağlar
      - Karşılaştırmayı güvenli kılar
    """
    NORMAL            = "NORMAL"
    MEDIUM            = "ORTA (MEDIUM)"
    HIGH              = "YÜKSEK (HIGH)"
    CRITICAL          = "KRİTİK (CRITICAL)"
    INSUFFICIENT_DATA = "YETERSİZ VERİ"


class WorkOrderStatus(Enum):
    """ERP İş Emri'nin yaşam döngüsü durumları (State Machine)."""
    PENDING     = "BEKLEMEDE"
    IN_PROGRESS = "İŞLEMDE"
    RESOLVED    = "ÇÖZÜLDÜ"
    CANCELLED   = "İPTAL EDİLDİ"

# ─────────────────────────────────────────────────────────────
# ENTITY 1: Metric
# agent/monitor.py'dan gelen ham veriyi domain'in anlayacağı
# yapıya dönüştürür. Her sunucu anlık ölçümü bu sınıfla temsil edilir.
# ─────────────────────────────────────────────────────────────
@dataclass
class Metric:
    """
    Bir ajanın gönderdiği tek bir anlık sistem metriği.

    DATACLASS NEDİR?
    @dataclass dekoratörü, __init__ metodunu otomatik yazar.
    Şu iki kod tamamen aynı işi yapar:

    # Dataclass YOK (eski yol):
    class Metric:
        def __init__(self, agent_id, cpu_percent, ...):
            self.agent_id = agent_id
            self.cpu_percent = cpu_percent

    # Dataclass VAR (temiz yol):
    @dataclass
    class Metric:
        agent_id: str
        cpu_percent: float
    """

    # ── Zorunlu Alanlar ──────────────────────────────────────
    agent_id: str        # Hangi sunucudan geldi? (örn: "server-prod-01")
    cpu_percent: float   # CPU kullanım yüzdesi  (0.0 – 100.0)
    ram_percent: float   # RAM kullanım yüzdesi  (0.0 – 100.0)
    ram_used_gb: float   # Kullanılan RAM miktarı (GB)
    ram_total_gb: float  # Toplam RAM kapasitesi  (GB)

    # ── Otomatik Doldurulacak Alanlar ────────────────────────
    metric_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
#Lambda, fonksiyona isim vermeden onu kullanmanı sağlar.
# genetre_id.id cunku .id kismini yazmazasak direkt fonku str yapar biz id yi str istiyoz.str(uuid.uuid4) onu okunabilir string'e çevirir.
# JSON'a koymak için string gerekir
    )
    timestamp: datetime = field(
        default_factory=datetime.utcnow
    )
    # ── İŞ KURALI #1: Validasyon:Gelen verinin doğru/geçerli olup olmadığını kontrol etmek ─────────────────────────────
     # Domain katmanı, kendi verilerinin geçerliliğini kendisi kontrol eder.
    def __post_init__(self):
        if not (0.0 <= self.cpu_percent <= 100.0):
            raise ValueError( #raise = "Hata fırlat, programı durdur."
                f"CPU yüzdesi 0-100 aralığında olmalıdır, alınan: {self.cpu_percent}"
            )
        if not (0.0 <= self.ram_percent <= 100.0):
            raise ValueError(
                f"RAM yüzdesi 0-100 aralığında olmalıdır, alınan: {self.ram_percent}"
            )
        if self.ram_total_gb <= 0:
            raise ValueError("Toplam RAM sıfırdan büyük olmalıdır.")
        if self.ram_used_gb < 0:
            raise ValueError("Kullanılan RAM negatif olamaz.")

    # ── İŞ KURALI #2: Hesaplanmış Özellikler (@property) ─────
    @property
    def ram_free_gb(self) -> float:
        return round(self.ram_total_gb - self.ram_used_gb, 2) 
    #2 sayısı, virgülden (veya noktadan) sonra kaç basamak gösterileceğini belirler.   

    @property #Hesaplanmış değeri, kaydetmeden her zaman güncel tutmak için
    def is_high_cpu(self) -> bool:
        """CPU %80'in üzerindeyse yüksek yük altında demektir."""
        return self.cpu_percent > 80.0

    @property
    def is_high_ram(self) -> bool:
        """RAM %85'in üzerindeyse tehlikeli bölgede demektir."""
        return self.ram_percent > 85.0

    def to_dict(self) -> dict:
        """
        API katmanına JSON olarak gönderilecek temsil.
        Domain entity'si dışarıya çıkarken dict'e dönüşür.
        """
        return {
            "metric_id":    self.metric_id,
            "agent_id":     self.agent_id,
            "timestamp":    self.timestamp.isoformat(),
            "cpu_percent":  self.cpu_percent,
            "ram_percent":  self.ram_percent,
            "ram_used_gb":  self.ram_used_gb,
            "ram_total_gb": self.ram_total_gb,
            "ram_free_gb":  self.ram_free_gb,
            "is_high_cpu":  self.is_high_cpu,
            "is_high_ram":  self.is_high_ram,
        }

    def __repr__(self) -> str:
        return (
            f"Metric(agent='{self.agent_id}', "
            f"cpu={self.cpu_percent}%, "
            f"ram={self.ram_percent}%, "
            f"ts={self.timestamp.strftime('%H:%M:%S')})"
        )


# ─────────────────────────────────────────────────────────────
# ENTITY 2: WorkOrder
# Yapay zeka bir bellek sızıntısı tespit ettiğinde otomatik
# üretilen ERP İş Emri. Gerçek dünya karşılığı: SAP PM bileti.
# ─────────────────────────────────────────────────────────────
@dataclass
class WorkOrder:
    """
    Yapay zeka tarafından otomatik üretilen ERP İş Emri.

    Gerçek dünya karşılığı:
      SAP Plant Maintenance (PM) veya ServiceNow üzerindeki
      otomatik ticket/bilet sistemi.
    """
    agent_id: str                      # Hangi sunucu için üretildi?
    risk_level: RiskLevel              # Hangi tehlike seviyesinde tetiklendi?
    estimated_seconds_to_oom: float    # Tahmini çökme süresi (saniye)
    ram_percent_at_trigger: float      # Tetiklendiğindeki RAM yüzdesi

    # ── Otomatik Doldurulacak Alanlar ────────────────────────
    work_order_id: str = field(
        default_factory=lambda: f"WO-{str(uuid.uuid4())[:8].upper()}"
    )
    created_at: datetime = field( 
        default_factory=datetime.utcnow #UTC saati, zaman dilimi farklılıklarını engellemek için kullanılır.
    )
    status: WorkOrderStatus = field(
        default=WorkOrderStatus.PENDING #başlangıçta beklemede olcak.   
    )
    description: str = field(default="")
    resolved_at: Optional[datetime] = field(default=None)

    def __post_init__(self):
        """İş emri oluşturulduğunda açıklamayı otomatik üret."""
        if not self.description: #eğer açıklama yoksa
            mins = round(self.estimated_seconds_to_oom / 60, 1)
            #estimated_seconds_to_oom → çökmeye kaç saniye kaldı
            self.description = (  #f string : süslü parantez içindeki değişkenleri otomatik olarak string'e çevirip metne ekler.
                f"[OTOMATİK] {self.agent_id} sunucusunda bellek sızıntısı tespit edildi. "
                f"Mevcut RAM kullanımı: %{self.ram_percent_at_trigger:.1f}. "
                f"Tahmini çökme süresi: {mins} dakika. "
                f"Risk Seviyesi: {self.risk_level.value}. "
                f"Acil müdahale gereklidir!"
            )
            # risk_level ve status Enum olduğu için .value ile string'e çevrilir.
    # ── İŞ KURALI: Durum Geçişleri (State Machine) ───────────
    # WorkOrder sadece belirli durumlara geçiş yapabilir.
    # Çözülmüş bir iş emri tekrar işleme alınamaz!
    def mark_in_progress(self) -> None:
        """İş emrini 'İşlemde' durumuna geçir."""
        if self.status != WorkOrderStatus.PENDING:
            raise ValueError(
                f"Sadece 'Beklemede' olan iş emirleri işleme alınabilir. "
                f"Mevcut durum: {self.status.value}"
            )
        self.status = WorkOrderStatus.IN_PROGRESS

    def mark_resolved(self) -> None:
        """İş emrini 'Çözüldü' olarak işaretle ve zamanı kaydet."""
        if self.status not in (WorkOrderStatus.PENDING, WorkOrderStatus.IN_PROGRESS):
            raise ValueError(
                "Sadece bekleyen veya işlemdeki iş emirleri çözülebilir."
            )
        self.status = WorkOrderStatus.RESOLVED
        self.resolved_at = datetime.utcnow()

    def mark_cancelled(self) -> None:
        """İş emrini iptal et (sadece tamamlanmamış olanlar)."""
        if self.status == WorkOrderStatus.RESOLVED:
            raise ValueError("Çözülmüş bir iş emri iptal edilemez.")
        self.status = WorkOrderStatus.CANCELLED

    # ── Hesaplanmış Özellikler ────────────────────────────────
    @property
    def urgency_minutes(self) -> float:
        """Aciliyet: kaç dakika kaldı (okunabilir form)."""
        return round(self.estimated_seconds_to_oom / 60, 1)

    @property
    def is_critical(self) -> bool:
        """Bu iş emri KRİTİK seviyede mi?"""
        return self.risk_level == RiskLevel.CRITICAL

    def to_dict(self) -> dict:
        """JSON serileştirme — API katmanına hazır temsil."""
        return {
            "work_order_id":            self.work_order_id,
            "agent_id":                 self.agent_id,
            "risk_level":               self.risk_level.value,
            "status":                   self.status.value,
            "description":              self.description,
            "estimated_minutes_to_oom": self.urgency_minutes,
            "ram_percent_at_trigger":   self.ram_percent_at_trigger,
            "created_at":               self.created_at.isoformat(),
            "resolved_at":              self.resolved_at.isoformat() if self.resolved_at else None,
            "is_critical":              self.is_critical,
        }

    def __repr__(self) -> str:
        return (
            f"WorkOrder(id='{self.work_order_id}', "
            f"agent='{self.agent_id}', "
            f"risk={self.risk_level.value}, "
            f"status={self.status.value}, "
            f"oom_in={self.urgency_minutes}dk)"
        )
