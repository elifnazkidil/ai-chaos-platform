import time
import threading
import psutil
from ai.leak_detector import MemoryLeakDetector
from agent.chaos import simulate_memory_leak

def run_chaos_in_background():
    """Kaos sızıntısını arka planda başlatır."""
    print("\n--- [KAOS SIMULATORU] Arka planda 5 MB/sn bellek sizintisi baslatiliyor... ---")
    simulate_memory_leak(duration_seconds=15, allocate_mb_per_sec=5)

def run_prototype():
    print("=" * 65)
    print("FINTECH YSA RESILIENCE PLATFORM - PROTOTIP DEMO")
    print("RAM Metrik Toplayici + Bellek Sizintisi Tespit Sistemi")
    print("=" * 65)

    # Dedektörümüzü ilklendirelim
    detector = MemoryLeakDetector(window_size=4, min_slope_threshold=0.03)
    ram_history = []

    # Kaos simülasyonunu arka planda başlat
    chaos_thread = threading.Thread(target=run_chaos_in_background, daemon=True)
    chaos_thread.start()

    print("\n[METRIK TOPLAYICI] Sistem RAM kullanimi izleniyor...")
    print("-" * 65)

    try:
        for i in range(12):
            # 1. Metrik Oku (psutil)
            memory_info = psutil.virtual_memory()
            ram_percent = memory_info.percent
            ram_history.append(ram_percent)

            # 2. Analiz Et
            result = detector.analyze_metrics(ram_history)

            # 3. Canlı Rapor Yazdır
            timestamp = time.strftime("%H:%M:%S")
            status_symbol = "[SIZINTI / LEAK DETECTED]" if result["is_leak"] else "[STABIL / NORMAL]"
            
            print(f"[{timestamp}] Adim {i+1:02d} | RAM: %{ram_percent:.1f} | Durum: {status_symbol} | Risk: {result['risk_level']}")
            
            if result["is_leak"]:
                print(f"   [AI TESPITI] Sizinti Egimi: +%{result['slope_per_sec']}/sn | Tahmini Cokme Suresi: {result['estimated_seconds_to_oom']} sn")
            
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nPrototip durduruldu.")

    print("=" * 65)
    print("PROTOTIP DEMO TAMAMLANDI!")
    print("=" * 65)

if __name__ == "__main__":
    run_prototype()
