import time
import sqlite3
import requests

SERVER_URL = "http://127.0.0.1:8000/api/v1/metrics"
AGENT_ID = "agent-01"

class ServerConnectionError(Exception):
    """
    Merkezi sunucuya bağlanılamadığında fırlatılan özel hata (Custom Exception).
    Not: İleride loglama veya Telegram bildirimi için url ve reason attributeları eklenebilir.
    """
    pass

def send_metrics():
    """
    SQLite veritabanındaki son metrikleri okur, JSON formatına dönüştürür ve merkezi sunucuya POST eder.
    """
    print(f"Sunucuya ({SERVER_URL}) veri gönderme servisi başlatıldı...")   
    while True: 
        try: 
            # 1. Veritabanından (en güncel) kaydı al
            with sqlite3.connect('metrics.db') as conn: # with bloğu çıkışında bağlantı otomatik kapanır
                cursor = conn.cursor() #cursor, db de islem yapmamizi saglar.
                cursor.execute('''
                    SELECT zaman, cpu_yuzde, ram_yuzde, ram_kullanilan_gb, ram_toplam_gb
                    FROM system_metrics
                    ORDER BY id DESC LIMIT 1
                ''')
                row = cursor.fetchone() # fetchone bir satır alır. (fetchall tüm satırları liste olarak döndürür)

            if row:
                # Gelen zaman damgasını ISO 8601 formatına dönüştürmek için boşluğu 'T' ile değiştiriyoruz.
                iso_timestamp = row[0].replace(" ", "T")
                
                payload = {
                    "agent_id": AGENT_ID,
                    "timestamp": iso_timestamp,
                    "metrics": {
                        "cpu_percent": float(row[1]),
                        "ram_percent": float(row[2]),
                        "ram_used_gb": float(row[3]),
                        "ram_total_gb": float(row[4])
                    }
                }
                
                try:
                    # 2. Veriyi Sunucuya Gönder (POST isteği)-suncuya baglanmama prob. burada ele alindigi icin serverconnectexception buraya eklnir
                    response = requests.post(SERVER_URL, json=payload, timeout=2)
                    response.raise_for_status()
                    print(f"[OK] Metrik sunucuya gönderildi: RAM %{row[2]}")
                except requests.exceptions.RequestException as e:
                    raise ServerConnectionError(f"FastAPI sunucusuna ulaşılamadı: {e}")
            
            # Her 5 saniyede bir gönder (Ağ trafiğini çok yormamak için)
            time.sleep(5)
            
        except ServerConnectionError as e:
            print(f"[UYARI] {e}")
            print("5 saniye sonra tekrar denenecek...")
            time.sleep(5)
        except Exception as e:
            print(f"[BEKLENMEYEN HATA]: {e}")
            time.sleep(5)

if __name__ == "__main__":
    send_metrics()
