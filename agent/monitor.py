
#psutil: Bilgisayarın donanım bilgilerini almamızı sağlar.  Örneğin CPU ve RAM kullanımını.
#datetime: Bu modül, tarih ve saat işlemlerini yönetir. Zaman damgalarını oluşturmak için kullanırız.
#sqlite3: Bu modül, SQLite veritabanı ile etkileşim kurmamızı sağlar. Metrik verilerini yerel olarak saklamak için kullanılır.

import psutil
import time
from datetime import datetime

# ────────────────────────────────────────────────────────────────
# Ağ Trafiği Hızı (önceki okuma saklanır, fark hesaplanır)
# psutil.net_io_counters() kümülatif bayt sayısı döner.
# MB/s = (bu_anki_toplam - önceki_toplam) / geçen_süre
# ────────────────────────────────────────────────────────────────
_prev_net_io = None     # Önceki okuma
_prev_net_time = None   # Önceki okuma zamanı


def _get_net_mbps() -> float:
    """
    Ağ trafiğini MB/s cinsinden hesaplar.

    Nasıl çalışır?
      - psutil.net_io_counters(): tüm NIC'lerdeki toplam byte sayısını döner.
      - Bu kümülatif bir sayıçtır (bilgisayar açılışından bu yana).
      - İki okuma arasındaki fark / geçen süre = MB/s
      - İlk çağrıda önceki okuma yok → 0.0 döner (ilk ölçüm atlanır).

    Returns:
        float: 0.0 ile 100.0 arası normalize edilmiş değer
    """
    global _prev_net_io, _prev_net_time

    now = time.time()
    net_io = psutil.net_io_counters()

    if _prev_net_io is None or _prev_net_time is None:
        # İlk çağrı: referans noktasını kaydet, 0.0 dön
        _prev_net_io = net_io
        _prev_net_time = now
        return 0.0

    elapsed = now - _prev_net_time
    if elapsed <= 0:
        return 0.0

    bytes_diff = (
        (net_io.bytes_sent + net_io.bytes_recv)
        - (_prev_net_io.bytes_sent + _prev_net_io.bytes_recv)
    )
    mbps = bytes_diff / (1024 * 1024 * elapsed)  # Byte/s → MB/s

    # Referans noktasını güncelle
    _prev_net_io = net_io
    _prev_net_time = now

    # 100.0 MB/s sınırı (ağ kartların pratikte ulaşabileği makul üst sınır)
    return min(round(mbps, 3), 100.0)


def get_system_metrics():
    """İşletim sisteminden CPU, RAM, Disk ve Ağ bilgilerini okuyan fonksiyon."""
    cpu_percent = psutil.cpu_percent(interval=1)#1 saniye aralıklarla CPU kullanımını ölçer.
    #bu sayede daha doğru sonuçlar elde ederiz. 
    memory = psutil.virtual_memory()#RAM bilgilerini alır.  
    
    # Disk kullanım yüzdesi (kök dizin → Windows'ta C:\ döner)
    disk = psutil.disk_usage('/')
    disk_percent = round(disk.percent, 1)
    
    # Ağ trafiği MB/s (bir önceki okumaya göre fark hesaplanır)
    net_mbps = _get_net_mbps()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")#şu anki zamanı yazar.SQLite'taki TEXT sütununa uygun şekilde 2026-08-18 11:33:24 formatında biçimlendirir.  
    
    return {
        "zaman": timestamp,
        "cpu_yuzde": cpu_percent,
        "ram_yuzde": memory.percent,
        "ram_kullanilan_gb": round(memory.used / (1024 ** 3), 2),
        "ram_toplam_gb": round(memory.total / (1024 ** 3), 2),
        "disk_yuzde": disk_percent,
        "net_mbps": net_mbps,
    }

if __name__ == "__main__":
    print("Agent başlatıldı. API'ye (FastAPI) veri gönderilecek...")
    print("Veritabanı hazır! Metrikler toplanıp kaydediliyor... (Durdurmak için CTRL+C)")
    '''
    Ajan (Monitor) Clean Architecture kuralları gereği veritabanına doğrudan yazmaz.
    Metrikler HTTP POST ile /api/v1/metrics endpoint'ine iletilir.
    '''
    try:
        while True:
            metrics = get_system_metrics()
            
            print(f"[{metrics['zaman']}] CPU: %{metrics['cpu_yuzde']} | RAM: %{metrics['ram_yuzde']} | Disk: %{metrics['disk_yuzde']} | Net: {metrics['net_mbps']} MB/s")
            
            # Her durumda API'ye metrikleri gönder (Dashboard'da görebilmek için)
            payload_metrics = {
                "agent_id": "server-prod-01",
                "timestamp": metrics['zaman'].replace(' ', 'T'), # ISO 8601 formatına çevir
                "metrics": {
                    "cpu_percent": metrics['cpu_yuzde'],
                    "ram_percent": metrics['ram_yuzde'],
                    "ram_used_gb": metrics['ram_kullanilan_gb'],
                    "ram_total_gb": metrics['ram_toplam_gb'],
                    "disk_percent": metrics['disk_yuzde'],
                    "net_mbps": metrics['net_mbps']
                }
            }
            try:
                import requests
                # Ana metrik akışı
                requests.post("http://127.0.0.1:8000/api/v1/metrics", json=payload_metrics, timeout=2)
                
                # ─── API ENTEGRASYONU (Sadece riskli durumlarda AI tetiklemesi) ───
                if metrics['cpu_yuzde'] > 70.0 or metrics['ram_yuzde'] > 70.0:
                    print(f"[!] Yüksek kaynak kullanımı tespit edildi. AI Decision Engine'e gönderiliyor...")
                    # Evaluate endpoint'i düz (flat) payload bekliyor olabilir
                    payload_eval = {
                        "cpu_percent": metrics['cpu_yuzde'],
                        "ram_percent": metrics['ram_yuzde'],
                        "ram_used_gb": metrics['ram_kullanilan_gb'],
                        "ram_total_gb": metrics['ram_toplam_gb'],
                        "agent_id": "server-prod-01",
                        # Gerçek disk/net → YSA'ya 4 feature gider, confidence cap kalkar
                        "disk_percent": metrics['disk_yuzde'],
                        "net_mbps": metrics['net_mbps'],
                    }
                    resp = requests.post("http://127.0.0.1:8000/api/v1/evaluate", json=payload_eval, timeout=30)
                    print(f"    -> AI Yanıtı: {resp.status_code}")
            except Exception as e:
                print(f"    -> API Hatası: {e}")
            
            # psutil.cpu_percent zaten 1 saniye beklediği için ekstra sleep koymuyoruz, saniyede 1 kayıt alır.
    except KeyboardInterrupt:
        print("\nAgent durduruldu.")
