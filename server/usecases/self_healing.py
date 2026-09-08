import psutil
import datetime
import requests
import sqlite3
#bu dosya ysa ile sistemdeki bellek sızıntısı tespit edildikten sonra devreye girer.
#psutil kütüphanesi ile sistemdeki prosesleri izler.

# n8n otomasyon sunucusu adresi 
N8N_WEBHOOK_URL = "http://localhost:5678/webhook/self-healing"
#normalde n8n kurulu degil.bu adrese istek attginda error aliriz  
#bu yüzden kodda try/except ile sardık ve hata durumunda log_event("WEBHOOK_FAILED", ...) ile logladık.

# Güvenli proseslerin listesi (Öldürülmemesi gerekenler)
WHITELIST = {'postgres', 'java', 'python', 'mysqld', 'redis-server'}

def init_db():
    """Veritabanı tablolarını oluşturur (Başlangıçta bir kez çağrılmalı)."""
    try:
        with sqlite3.connect('metrics.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS event_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    action TEXT,
                    detail TEXT
                )
            ''')
    except Exception as e:
        print(f"[DB HATA] Tablolar oluşturulamadı: {e}")

def log_event(action, detail):
    timestamp = datetime.datetime.now().isoformat()#Yapılan self-healing aksiyonunu zaman damgalı olarak (event log) kaydeder.
    try:
        with sqlite3.connect('metrics.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO event_logs (timestamp, action, detail)
                VALUES (?, ?, ?)
            ''', (timestamp, action, detail))
    except Exception as e:
        print(f"[LOG HATA] Olay loglanamadı: {e}")

def trigger_n8n_webhook(action, detail):
    """
    n8n otomasyon platformuna HTTP POST atarak bildirim motorunu (Slack/Telegram) tetikler.
    """
    payload = {
        "event": "Self-Healing Triggered",
        "action": action,
        "detail": detail,
        "timestamp": datetime.datetime.now().isoformat()
    }
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=2)
        if response.status_code == 200:
            print("[BİLDİRİM] n8n webhook tetiklendi.")
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        print(f"[UYARI] n8n webhook'una ulaşılamadı. Sunucu çalışmıyor olabilir: {error_msg}")
        log_event("WEBHOOK_FAILED", error_msg)

def mitigate_memory_leak():
    """
    YSA kritik risk (Time-to-OOM < 5 dk vs.) algiladiginda cagirilir.
    Sistemi kurtarmak için bellek sizintisi yapan kaos prosesini bulur ve öldürür.
    """
    print("[MÜDAHALE] Kritik risk algılandı! Self-Healing devreye giriyor...")
    
    killed_processes = []
    
    # Tüm çalışan prosesleri iterasyona sok (psutil)
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):#osde o an çalışan tüm prosesleri tek tek dolaşmayı sağlar.
#tüm aktif süreçleri bir döngüde dolaşırken, system call maliyetini düşürmek için sadece (pid, name, memory_percent) önceden önbelleğe alarak çeker.
        try:
            name = proc.info.get('name', '').lower()
            mem_pct = proc.info.get('memory_percent', 0.0)
            
            # Senaryo: Eğer RAM'in büyük bölümünü tüketen (ve whitelist'te olmayan) veya doğrudan 'chaos' ismiyle çalışan bir proses bulursak
            if 'chaos' in name or (mem_pct is not None and mem_pct > 80.0 and name not in WHITELIST):
                pid = proc.info['pid']
                p = psutil.Process(pid)
                
                # Önce nazikçe (SIGTERM) sonlandırmayı dene
                p.terminate()#isleme sonlandirma sinyali gönderir.3 saniye bekler.  
                import time
                time.sleep(3)
                
                # Eğer hala çalışıyorsa zorla (SIGKILL) kapat
                if p.is_running():#hala çalışıyorsa
                    p.kill() 
                
                detail = f"Killed PID: {pid}, Name: {name}, Mem: {mem_pct:.2f}%"
                killed_processes.append(detail)
                
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if killed_processes:
        action = "KILLED_PROCESS"
        detail_str = " | ".join(killed_processes)
        print(f"[BAŞARILI] Sistem kurtarıldı. Detay: {detail_str}")
        
        # 1. Veritabanına Logla
        log_event(action, detail_str)
        # 2. n8n üzerinden bildirim at
        trigger_n8n_webhook(action, detail_str)
        
        return True
    else:
        print("[BİLGİ] Müdahale edilecek belirgin bir proses bulunamadı.")
        return False
