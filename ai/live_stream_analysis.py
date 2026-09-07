import time
import numpy as np
import sys
import os
# Proje ana dizinini Python'un arama yoluna ekleyelim (IDE 'Run' butonu için gerekli)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import deque # queue, son 5 veriyi tutar. kuyruğa 6. elemanı eklersen en baştaki (en eski) elemanı otomatik olarak siler! 
from ai.neural_network import AnomalyTrainer
from ai.leak_detector import MemoryLeakDetector

def simule_edilmis_sizinti_akisi():
    """Bilerek 'Memory Leak' (Bellek Sızıntısı) yaratan Jeneratör"""
    print("Bellek sızıntısı simülasyonu başlatıldı...")
    
    
    cpu = 40.0
    ram = 30.0  # RAM düşükten başlıyor
    disk = 20.0
    net = 15.0
    
    while True:
        # RAM her saniye tehlikeli şekilde %1-2 arası artıyor (Sızıntı)
        ram += np.random.uniform(1.0, 2.0)
        
        # Diğer metrikler sabit/hafif dalgalı (Normal iş yükü)
        cpu += np.random.uniform(-2.0, 2.0)
        
        # Sınırları aşmasın
        cpu = min(max(cpu, 0.0), 100.0)
        ram = min(ram, 100.0)
        
        yield [cpu, ram, disk, net]
        time.sleep(0.5)

if __name__ == "__main__":
    print("="*60)
    print(" YSA ve Leak Detector Entegrasyonu (Canlı Akış)")
    print("="*60)

    # 1. Modülleri Başlat
    print("1. Modüller yükleniyor...")
    
    # Doğrusal Regresyon (Matematiksel) Dedektörümüz
    # window_size=5: Son 5 saniyeye bakarak eğim hesaplayacak
    leak_detector = MemoryLeakDetector(window_size=5, min_slope_threshold=0.5)
    
    # Yapay Sinir Ağı Modelimiz
    nn_trainer = AnomalyTrainer(input_size=4, hidden_sizes=[64, 32, 16])
    try:
        nn_trainer.load_model("ai/anomaly_model.pth")
    except FileNotFoundError:
        print("Model bulunamadı! Lütfen önce neural_network.py dosyasını çalıştırın.")
        exit()

    # 2. Canlı Akışı Başlat
    akim = simule_edilmis_sizinti_akisi()
    
    # RAM geçmişini tutacağımız kova (Sadece son 5 veriyi tutar - Jeneratör felsefesine uygun)
    ram_gecmisi = deque(maxlen=5)

    print("\n[ANALİZ BAŞLIYOR]")
    print(f"{'ZAMAN':<10} | {'RAM %':<10} | {'YSA SKORU':<15} | {'TIME-TO-OOM':<15}")
    print("-" * 60)

    for i in range(15):
        # Hortumdan 1 damla metrik al
        metrikler = next(akim)
        cpu, ram, disk, net = metrikler
        
        # RAM geçmişini güncelle
        ram_gecmisi.append(ram)
        
        # --- A) Leak Detector Analizi (Matematiksel) ---
        ld_result = leak_detector.analyze_metrics(list(ram_gecmisi))
        
        # --- B) Yapay Sinir Ağı Analizi (AI) ---
        # Modeli beslemek için veriyi numpy array'e çeviriyoruz
        X_test = np.array([metrikler], dtype=np.float32)
        nn_result = nn_trainer.classify(X_test)[0]
        
        # Çıktıları Formatla
        ysa_skor = f"{nn_result['anomaly_score']:.2f} ({nn_result['risk_level']})"
        
        if ld_result["is_leak"]:
            oom_sure = f"{ld_result['estimated_seconds_to_oom']} sn"
        else:
            oom_sure = "Güvende"
            
        print(f"{i+1}. Saniye | %{ram:<8.1f} | {ysa_skor:<15} | {oom_sure:<15}")
        
    print("\n[OK] Sistem OOM (Out Of Memory) olmadan müdahale edildi!")
