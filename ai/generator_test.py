import random
import time

def canli_metrik_akisi():
    """Sonsuz bir metrik akışı sağlayan Jeneratör (Generator)"""
    print("Generator başlatıldı!")
    
    while True:
        # Temsili CPU, RAM, Disk, Ağ metrikleri üretiyoruz
        cpu = random.uniform(10.0, 95.0)
        ram = random.uniform(20.0, 99.0)
        disk = random.uniform(5.0, 80.0)
        net = random.uniform(1.0, 100.0)
        
        # return YERİNE yield KULLANIYORUZ!
        # yield, "al bu veriyi kullan, işin bitince ben kaldığım yerden devam edeceğim" der.
        yield [cpu, ram, disk, net]
        
        # Gerçekçilik katmak için her üretimde 0.5 saniye bekle
        time.sleep(0.5)

if __name__ == "__main__":
    print("Sisteme bağlanılıyor...")
    akim = canli_metrik_akisi() # Jeneratörü oluşturduk ama henüz ÇALIŞMADI!

    # next() veya for döngüsü ile veriyi damla damla çekiyoruz
    print("\n[VERİ ÇEKİLİYOR - İLK 5 METRİK]")
    for i in range(5):
        guncel_metrik = next(akim)
        print(f"{i+1}. Saniye -> CPU: %{guncel_metrik[0]:.1f}, RAM: %{guncel_metrik[1]:.1f}")

    print("\nBitti! Hafıza şişmedi çünkü tüm veriyi aynı anda listede tutmadık.")

