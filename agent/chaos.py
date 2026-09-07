import time
import sys
import argparse
import multiprocessing
import os
import psutil

def simulate_memory_leak(duration_seconds=600, allocate_mb_per_sec=5, scenario_name=None):
    """
    duration_seconds: simülasyon süresi (saniye)
    allocate_mb_per_sec: saniyede ayrilacak RAM miktari (MB)
    scenario_name: senaryo adi  
    Sisteme yapay bir 'Memory Leak' (Bellek sizintisi) enjekte eder.
    Her saniye belirtilen MB kadar RAM'i dolduran bir liste olusturur.
    
    ai modeli bu yavas ve istikrarli RAM artisini (trendini)  erken safhada yakalamayi ogrenecektir.
    """
    if scenario_name is None:
        if allocate_mb_per_sec == 5:
            scenario_name = "Yavas Sizinti (Slow Leak)"
        elif allocate_mb_per_sec == 25:
            scenario_name = "Hizli Sizinti (Fast Leak)"
        else:
            scenario_name = f"Ozel Sizinti (Custom Leak - {allocate_mb_per_sec} MB/s)"

    print(f"!!! KAOS MODULU AKTIF !!!")
    print(f"Senaryo: {scenario_name}")
    print(f"Hedef: Her saniye {allocate_mb_per_sec} MB RAM tüketmek.")
    print(f"Süre: {duration_seconds} saniye.")
    print("Durdurmak için CTRL+C tuşlarina basin.\n")
    
    leaked_memory = [] # Bellekte verileri biriktireceğimiz BOŞ BİR KUTU açiyoruz.

    try:
        start_time = time.time() #Başlangiç zamanini kaydet
        while time.time() - start_time < duration_seconds: 
            #time.time() , anlik zamani verir.- başlangiç zamanindan anlik zamani çikarirsa aradaki geçen süreyi buluruz.
            # 1 MB'lik bir byte dizisi oluştur ve listeye ekle
            mb_chunk = b'A' * (1024 * 1024 * allocate_mb_per_sec) #5 x 1024 x 1024 = 5,242,880 karakterlik bir veri bloğu (5MB)
            leaked_memory.append(mb_chunk) # Bu bloğu RAM'de açik biraktiğimiz 'kutunun' içine koyuyoruz.
            allocated_total = len(leaked_memory) * allocate_mb_per_sec #leaked_memory , listedeki eleman sayisini verir.    
            process = psutil.Process(os.getpid())
            rss_mb = process.memory_info().rss / 1024 / 1024#neden 1024 e böldük?psutil bayt olarak verir biz mb olarak istediğimiz için 1024 e böldük. 
            print(f"[KAOS] Teorik sizdirilan: {allocated_total} MB | Gerçek RAM kullanimi: {rss_mb:.1f} MB")
            
            time.sleep(1) #1 saniye bekler.         
            
    except KeyboardInterrupt: 
        print("\nKaos modülü durduruldu. RAM temizleniyor...")
        leaked_memory.clear()
        sys.exit(0)
        
    print("\nKaos simülasyonu süresi doldu. RAM serbest birakiliyor...")
    leaked_memory.clear()

def cpu_stress():
    """Sonsuz döngü ile bir CPU çekirdeğini %100 kullanir."""
    while True:
        pass

def simulate_cpu_spike(duration_seconds=600):
    """
    Sisteme CPU Aşiri Yükleme (CPU Spike) sizdirir.
    Mevcut çekirdek sayisi kadar işlem başlatarak tüm çekirdekleri %100 doldurur.
    """
    print(f"!!! KAOS MODÜLÜ AKTİF !!!")
    print(f"Senaryo: CPU Spike (Aşiri Yükleme)")
    print(f"Süre: {duration_seconds} saniye.")
    print("Durdurmak için CTRL+C tuşlarina basin.\n")
    
    processes = []
    num_cores = multiprocessing.cpu_count()#sistemdeki çekirdek sayisini verir. 16 çekirdek varsa 16 process başlatir.  
    print(f"[KAOS] {num_cores} çekirdek tespit edildi. İşlemler başlatiliyor...")

    # Her çekirdek için bir process başlat
    for i in range(num_cores):
        p = multiprocessing.Process(target=cpu_stress)
        p.start()
        processes.append(p)

    try:
        start_time = time.time()
        while time.time() - start_time < duration_seconds:# başlangiçtan beri geçen süreyi bulmak için.Bunu  duration_seconds'ten çikarirsak kalan süreyi buluruz. 
            time.sleep(1)
            print(f"[KAOS] CPU Spike aktif... Kalan süre: {int(duration_seconds - (time.time() - start_time))} sn", end='\r')
            
    except KeyboardInterrupt:
        print("\nKaos modülü durduruldu. CPU işlemleri sonlandiriliyor...")
        for p in processes:
            p.terminate()#işlemi sonlandirir.
        for p in processes:
            p.join()#join metodu, process bitene kadar bekler. 
        sys.exit(0)
        
    print("\nKaos simülasyonu süresi doldu. CPU işlemleri sonlandiriliyor...")
    for p in processes:
        p.terminate()
    for p in processes:
        p.join()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="AI Chaos Platform - Bellek sizintisi Simülatörü")
    parser.add_argument(
        "--target", "-t",
        choices=["memory", "cpu"],
        default="memory",
        help="Kaos hedefi (memory veya cpu)"
    )
    parser.add_argument(
        "--scenario", "-s",
        choices=["slow", "fast", "custom"],
        default="slow",
        help="Kaos senaryosu seçimi (slow: 5 MB/s, fast: 25 MB/s, custom: belirtilen rate kullanilir)"
    )
    parser.add_argument(
        "--rate", "-r",
        type=int,
        help="Custom senaryo seçildiğinde saniyede ayrilacak RAM miktari (MB)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=600,
        help="Simülasyon süresi (saniye, varsayilan: 600)"
    )

    args = parser.parse_args() #bu satir, komut satirindan gelen argümanlari alir.  
    #böyle çaliştiriyoruz: komut satiri = python agent/chaos.py --target cpu --duration 600.     

    # Determine allocation rate and scenario name based on scenario parameter
    if args.target == "memory":
        if args.scenario == "slow":
            rate = 5
            scenario = "Yavaş sizinti (Slow Leak)"
        elif args.scenario == "fast":
            rate = 25
            scenario = "Hizli sizinti (Fast Leak)"
        elif args.scenario == "custom":
            if args.rate is None:
                parser.error("custom senaryo seçildiğinde --rate veya -r parametresi zorunludur.")
            rate = args.rate
            scenario = f"Ozel sizinti (Custom Leak - {rate} MB/s)"
        else:
            rate = 5
            scenario = "Yavas sizinti (Slow Leak)"

        simulate_memory_leak(duration_seconds=args.duration, allocate_mb_per_sec=rate, scenario_name=scenario)
    elif args.target == "cpu":
        simulate_cpu_spike(duration_seconds=args.duration)

