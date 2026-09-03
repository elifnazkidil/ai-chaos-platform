"""
ai/train.py
Model Eğitim Scripti (Gün 10 Pratik)

Bu script, metrics.db veritabanından toplanan gerçek verileri okur,
label'larını (etiketlerini) mantıksal olarak belirler ve 
Yapay Sinir Ağı'nı (AnomalyTrainer) eğitip kaydeder.
"""
import sqlite3
import numpy as np
import os
from pathlib import Path
import sys

# Proje kök dizinini Python path'ine ekle
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from ai.neural_network import AnomalyTrainer

def load_data_from_db():
    db_path = PROJECT_ROOT / "metrics.db"
    if not db_path.exists():
        print(f"[HATA] Veritabanı bulunamadı: {db_path}")
        return None, None
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Tüm verileri çek (Tabloda cpu_percent ve ram_percent var)
    cursor.execute("SELECT cpu_percent, ram_percent FROM metrics")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("[HATA] Veritabanında henüz metrik yok.")
        return None, None
        
    print(f"[DATA] {len(rows)} adet metrik okundu.")
    
    X = []
    y = []
    
    for row in rows:
        cpu = row[0]
        ram = row[1]
        # Disk ve Net şimdilik DB'de yok, sentetik üretiyoruz.
        disk = np.random.uniform(5, 40) 
        net = np.random.uniform(5, 50)  
        
        # Etiketleme Mantığı (Labeling Logic):
        # RAM > 80% veya CPU > 85% ise Anomali (1), yoksa Normal (0)
        is_anomaly = 1.0 if (ram > 80.0 or cpu > 85.0) else 0.0
        
        X.append([cpu, ram, disk, net])
        y.append(is_anomaly)
        
    # Eğer hep aynı label varsa eğitim çökebilir (sadece normal veri geldiyse),
    # bu yüzden sentetik anomali ve normal veri ekleyerek veri setini zenginleştirelim.
    if sum(y) == 0:
        print("[UYARI] Hiç anomali verisi bulunamadı, eğitim için sentetik anomali ekleniyor...")
        X.extend([
            [95.0, 90.0, 80.0, 85.0],
            [88.0, 92.0, 75.0, 80.0]
        ])
        y.extend([1.0, 1.0])
        
    if sum(y) == len(y):
        print("[UYARI] Sadece anomali verisi bulundu, eğitim için sentetik normal ekleniyor...")
        X.extend([
            [15.0, 20.0, 10.0, 15.0],
            [25.0, 30.0, 15.0, 20.0]
        ])
        y.extend([0.0, 0.0])
        
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def main():
    print("=" * 60)
    print(" AI Chaos Platform - Model Eğitim Scripti")
    print("=" * 60)
    
    X_train, y_train = load_data_from_db()
    
    if X_train is None:
        print("Egitim iptal edildi. (Veritabanında veri yoksa agent'ı çalıştırıp veri üretin.)")
        return
        
    print(f"\n[TRAIN] Egitim basliyor... (Veri boyutu: {len(X_train)})")
    print(f"Normal (0): {(y_train == 0).sum()} adet | Anomali (1): {(y_train == 1).sum()} adet")
    
    trainer = AnomalyTrainer(
        input_size=4,
        hidden_sizes=[64, 32, 16],
        learning_rate=0.001
    )
    
    trainer.train(
        features=X_train,
        labels=y_train,
        epochs=100,
        verbose=True
    )
    
    # Modeli diske kaydet
    model_path = PROJECT_ROOT / "ai" / "anomaly_model.pth"
    trainer.save_model(filepath=str(model_path))
    
    print("\n[OK] Egitim tamamlandi. Model basariyla kaydedildi.")
    
if __name__ == "__main__":
    main()
