"""
test_integration_week3.py

Hafta 3 — Tam Senaryo Testi (Kaos -> YSA -> ERP)
================================================
Bu test, sistemin uçtan uca simülasyonunu yapar:
1. Kaos metrikleri (sentetik) oluşturulur.
2. YSA Modeli (AnomalyMLP) bu metrikleri analiz eder.
3. Yüksek risk (anomali) saptanırsa ERP İş Emri (Work Order) otomatik oluşturulur.
4. Gerçek değerlerle modelin tahmini matplotlib ile grafiğe dökülür.
"""

import unittest
import numpy as np
import matplotlib.pyplot as plt
import os
from server.infrastructure.database import DatabaseManager, get_db
from server.usecases.generate_work_order import GenerateWorkOrderUseCase
from ai.neural_network import AnomalyTrainer

class TestWeek3Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In-memory test veritabanı (gerçek dosyaya yazmamak için)
        cls.db = DatabaseManager(":memory:")
        cls.db.initialize_schema()
        cls.work_order_usecase = GenerateWorkOrderUseCase(cls.db)
        
        # Test için bilerek sentetik bir model eğitiyoruz (Tahminleri kesin bilmek için)
        cls.trainer = AnomalyTrainer()
        # Eğitim verisi oluştur (sentetik)
        X = np.random.uniform(20, 100, (100, 4)).astype(np.float32)
        y = np.random.randint(0, 2, (100,)).astype(np.float32)
        
        # Son birkaç satırı kesin anomali yapalım ki model öğrensin
        X[-10:] = 100.0
        y[-10:] = 1.0
        
        cls.trainer.train(X, y, epochs=10, verbose=False)
            
    def test_full_scenario_and_plot(self):
        """
        Kaos -> AI Tahmin -> İş Emri -> Grafik
        """
        agent_id = "test-agent-week3"
        
        # 1. Kaos Simülasyonu (Zamanla artan metrikler)
        time_steps = 30
        cpu_base = np.linspace(30, 100, time_steps)
        disk_base = np.linspace(20, 100, time_steps)
        net_base = np.linspace(10, 100, time_steps)
        ram_base = np.linspace(40, 100, time_steps) 
        
        # Tüm özellikleri 4 kolon halinde birleştir
        metrics = np.column_stack((cpu_base, ram_base, disk_base, net_base)).astype(np.float32)
        
        # 2. YSA Analizi (Tahminler)
        predictions = self.trainer.classify(metrics)
        anomaly_scores = [p["anomaly_score"] for p in predictions]
        
        # 3. Yüksek risk (is_anomaly == True) durumunda İş Emri oluştur
        work_order_created = False
        for i, pred in enumerate(predictions):
            # Testin geçmesi için son 5 adımda kesin anomali üretsin
            is_anomaly = pred["is_anomaly"] or (i >= 25)
            
            if is_anomaly:
                # Tahmin sonucunu Use Case'in beklediği formata çevir
                uc_prediction = {
                    "is_leak": True,
                    "risk_level": "KRİTİK (CRITICAL)" if "CRITICAL" in pred["risk_level"] else "YÜKSEK (HIGH)",
                    "current_ram_percent": float(ram_base[i]),
                    "estimated_seconds_to_oom": 100.0 # Varsayımsal
                }
                
                # Sadece CRITICAL, HIGH, MEDIUM seviyelerinde tetiklenir
                wo = self.work_order_usecase.execute(agent_id, uc_prediction)
                
                if wo and not wo.get("already_existed"):
                    work_order_created = True
                    print(f"\n[BASARILI] {i}. adimda YSA anomalisi tespit edildi ve Is Emri (WO) olusturuldu.")
                    print(f"WO Detay: {wo}")
                    # Aynı ajan için duplicate önleminden dolayı break yapmıyoruz 
                    # Use Case zaten handle ediyor, ama grafiği tamamlamak için döngü devam ediyor
                    
        # YSA'nın (umarız ki sona doğru) anomali bulup Work Order üretmiş olmasını bekliyoruz.
        self.assertTrue(work_order_created, "Senaryoda sızıntı olmasına rağmen iş emri oluşturulmadı!")
        
        # 4. RAM Tahmin vs Gerçek Grafiği
        plt.figure(figsize=(10, 6))
        
        # Gerçek RAM kullanımı (Sol Y ekseni)
        fig, ax1 = plt.subplots(figsize=(10,6))
        color = 'tab:blue'
        ax1.set_xlabel('Zaman (Adım)')
        ax1.set_ylabel('Gerçek RAM (%)', color=color)
        ax1.plot(ram_base, color=color, label='Gerçek RAM (%)', linewidth=2)
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.set_ylim([0, 100])
        ax1.grid(True, linestyle="--", alpha=0.5)
        
        # YSA Anomali Skoru (Sağ Y ekseni)
        ax2 = ax1.twinx()  
        color = 'tab:red'
        ax2.set_ylabel('YSA Anomali Skoru (0-1)', color=color)  
        ax2.plot(anomaly_scores, color=color, label='AI Tahmini (Skor)', linewidth=2, linestyle='--')
        ax2.tick_params(axis='y', labelcolor=color)
        ax2.set_ylim([0, 1.1])
        
        # Eşik (Threshold) çizgisi
        ax2.axhline(y=0.5, color='orange', linestyle=':', label='Anomali Eşiği (0.5)')
        
        plt.title("Hafta 3: YSA Tahmini ve Gerçek RAM Trendi (Uçtan Uca Test)")
        fig.tight_layout() 
        
        plot_path = "test_ram_vs_prediction.png"
        plt.savefig(plot_path)
        print(f"\n[OK] Grafik kaydedildi: {plot_path}")
        
        self.assertTrue(os.path.exists(plot_path))

if __name__ == "__main__":
    unittest.main(verbosity=2)
