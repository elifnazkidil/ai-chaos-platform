import sys
import os
# IDE 'Run' butonu sorununu çözmek için
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from ai.neural_network import AnomalyTrainer

def create_test_data(num_samples=100):
    """
    Modeli test etmek için 100 adet sentetik (sahte) veri üretir.
    Verilerin yarısı NORMAL (label=0.0), yarısı ANOMALİ (label=1.0) olacak.
    """
    test_veri_listesi = []
    
    for i in range(num_samples):
        if i % 2 == 0:
            # NORMAL VERİ (Sınırlar içinde)
            cpu = np.random.uniform(10, 60)
            ram = np.random.uniform(20, 60)
            disk = np.random.uniform(10, 50)
            net = np.random.uniform(5, 40)
            gercek_etiket = 0.0 # Normal = 0
            risk = "NORMAL"
        else:
            # ANOMALİ VERİ (Sınırları aşmış, bellek sızıntısı veya CPU yorgunluğu)
            cpu = np.random.uniform(85, 100)
            ram = np.random.uniform(90, 100)
            disk = np.random.uniform(70, 100)
            net = np.random.uniform(50, 100)
            gercek_etiket = 1.0 # Anomali = 1
            risk = "KRITIK"
            
        test_veri_listesi.append({
            "features": [cpu, ram, disk, net],
            "actual_label": gercek_etiket,
            "actual_risk": risk
        })
        
    return test_veri_listesi

if __name__ == "__main__":
    print("="*60)
    print(" YSA MODEL BAŞARIM (EVALUATION) TESTİ")
    print("="*60)

    # 1. Modeli Yükle
    trainer = AnomalyTrainer(input_size=4, hidden_sizes=[64, 32, 16])
    try:
        trainer.load_model("ai/anomaly_model.pth")
    except FileNotFoundError:
        print("Model bulunamadı!")
        exit()

    # 2. 100 Tane Test Verisi Üret
    print("\n100 adet test verisi (50 Normal, 50 Anomali) oluşturuluyor...")
    test_verileri = create_test_data(100)
    
    # 3. Model ile Tahmin (Prediction) Yap
    sonuclar = []
    for test in test_verileri:
        X_test = np.array([test["features"]], dtype=np.float32)
        
        # classify fonksiyonu bize {"anomaly_score": 0.85, "risk_level": "KRITIK"} gibi bir sözlük döner
        tahmin_cikti = trainer.classify(X_test)[0]
        
        # Modelin skoru (0.0 ile 1.0 arası)
        model_skoru = tahmin_cikti["anomaly_score"]
        
        # Eğer skor 0.70'ten büyükse YSA buna "Anomali (1.0)" demiştir, küçükse "Normal (0.0)" demiştir
        model_tahmini_label = 1.0 if model_skoru >= 0.70 else 0.0
        
        sonuclar.append({
            "actual": test["actual_label"],           # Gerçekte neydi? (0 veya 1)
            "predicted_score": model_skoru,           # YSA'nın verdiği küsuratlı skor (örn: 0.85)
            "predicted_label": model_tahmini_label    # YSA'nın son kararı (0 veya 1)
        })

    print("Model tahminleri tamamlandı. Metrikler hesaplanıyor...\n")

    # ---------------------------------------------------------
    # GÜN 12 KONUSU: LAMBDA, FILTER ve MAP İLE HESAPLAMA
    # ---------------------------------------------------------
    
    # ACCURACY (Doğruluk Oranı) HESAPLAMA -> FILTER VE LAMBDA
    # Kural: Modelin tahmini (predicted_label) ile gerçek durum (actual) aynıysa DOĞRU BİLMİŞTİR.
    dogru_bilinenler = list(filter(lambda x: x["actual"] == x["predicted_label"], sonuclar))
    
    toplam_test_sayisi = len(sonuclar)
    dogru_sayisi = len(dogru_bilinenler)
    accuracy = (dogru_sayisi / toplam_test_sayisi) * 100
    
    print(f"ACCURACY (Doğruluk): %{accuracy:.2f} ({toplam_test_sayisi} testin {dogru_sayisi} tanesini doğru bildi)")

    # MAE (Mean Absolute Error - Ortalama Mutlak Hata) HESAPLAMA -> MAP VE LAMBDA
    # Kural: YSA'nın verdiği skor (0.85) ile Gerçek Değer (1.0) arasındaki farkın mutlak değerini(abs) bul.
    # map fonksiyonu 100 tane çıkarma işlemini tek satırda yapar!
    hatalar = list(map(lambda x: abs(x["actual"] - x["predicted_score"]), sonuclar))
    
    # Tüm hataların ortalamasını al
    mae = sum(hatalar) / len(hatalar)
    
    print(f"MAE (Hata Payı): {mae:.4f} (Model tahminlerinde ortalama {mae:.4f} puanlık sapma yapıyor)")
    
    print("\n="*60)
    print("Test Tamamlandı!")
