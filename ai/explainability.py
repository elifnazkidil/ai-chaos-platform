"""
ai/explainability.py

Permutation Importance (Ablation Study)
=======================================
Bu betik, YSA modelinin hangi girdiye (CPU, RAM, Disk, Network)
daha çok önem verdiğini analiz eder.

Yöntem: Her bir girdi özelliğini sıfırlar (veya karıştırır) ve
bunun modelin anomali skorundaki düşüşe etkisini hesaplar.
Sonuçlar matplotlib ile bar grafiği olarak kaydedilir.
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import copy
from neural_network import AnomalyTrainer

def run_ablation_study():
    print("=" * 60)
    print(" AI Explainability - Ablation Study (Permutation Importance)")
    print("=" * 60)

    # 1. Modeli Yükle
    trainer = AnomalyTrainer()
    model_path = "ai/anomaly_model.pth"
    
    if os.path.exists(model_path):
        trainer.load_model(model_path)
    elif os.path.exists("anomaly_model.pth"): # Çalışma dizini farkı için
        trainer.load_model("anomaly_model.pth")
    else:
        print(f"[UYARI] Model bulunamadı. Geçici bir model eğitiliyor...")
        X = np.random.uniform(20, 100, (200, 4)).astype(np.float32)
        y = np.random.randint(0, 2, (200,)).astype(np.float32)
        trainer.train(X, y, epochs=10, verbose=False)

    # 2. Referans Anomali Verisi Oluştur (Gerçekte anomali olan bir durum)
    # [CPU, RAM, Disk, Network]
    base_sample = np.array([[85.0, 95.0, 70.0, 60.0]], dtype=np.float32)
    
    # Referans skor (Tüm özellikler mevcutken)
    base_score = trainer.predict(base_sample)[0]
    print(f"\n[REFERANS] Orijinal Anomali Skoru: {base_score:.4f}")

    # Özellik isimleri (Sırayla)
    features = ["CPU", "RAM", "Disk", "Network"]
    importance_scores = []

    # 3. Ablation Döngüsü (Her bir özelliği tek tek sıfırla/değiştir)
    print("\n[ANALIZ] Her bir ozellik sifirlanarak etkisi hesaplaniyor...")
    for i, feature_name in enumerate(features):
        ablated_sample = copy.deepcopy(base_sample)
        
        # O özelliği sıfırla (veya normal bir seviyeye çek, örn: 20)
        ablated_sample[0, i] = 20.0
        
        # Yeni skor hesapla
        ablated_score = trainer.predict(ablated_sample)[0]
        
        # Düşüş (Drop) miktarı, bu özelliğin önemidir.
        drop = max(0, base_score - ablated_score)
        importance_scores.append(drop)
        
        print(f"  - {feature_name} kaldirildiginda skor: {ablated_score:.4f} (Dusus: {drop:.4f})")

    # 4. Bar Grafiği (Bar Chart) ile Görselleştirme
    plt.figure(figsize=(8, 5))
    
    # Renklendirme
    colors = ['skyblue', 'lightgreen', 'salmon', 'gold']
    
    # Barlar
    bars = plt.bar(features, importance_scores, color=colors, edgecolor='black')
    
    # Değerleri barların üzerine yaz
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval + 0.01, f"{yval:.3f}", ha='center', va='bottom', fontsize=10)

    plt.title("Permutation Importance (Model Karar Etkisi)")
    plt.xlabel("Girdi Degiskenleri (Metrikler)")
    plt.ylabel("Anomali Skorundaki Dusus (Orijinal Skordan)")
    plt.ylim(0, max(importance_scores) * 1.2 if max(importance_scores) > 0 else 1.0)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Grafiği Kaydet
    output_path = "ai/permutation_importance.png"
    plt.savefig(output_path)
    print(f"\n[OK] Ozet Grafik kaydedildi: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    run_ablation_study()
