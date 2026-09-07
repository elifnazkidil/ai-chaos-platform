
# ─ @wraps(func) : 
#                  Örn: Basit bir zaman ölçme dekoratörü
# 
#                  import time
#                  from functools import wraps
# 
#                  def zaman_olc(func):
#                      @wraps(func)
#                      def wrapper(*args, **kwargs):
#                          baslangic = time.time()
#                          sonuc = func(*args, **kwargs)   # Orijinal fonksiyon çalışır
#                          bitis = time.time()
#                          print(f"{func.__name__} {bitis - baslangic:.4f} saniye surdu")
#                          return sonuc
#                      return wrapper
# 
#                  @zaman_olc
#                  def topla(a, b):
#                      return a + b
# 
#                  topla(2, 3)  # Çıktı: topla 0.0000 saniye surdu
# 
#                  @wraps(func) ne işe yarar? 
#                  Dekoratör olmadan wrapper fonksiyonunun adı 'wrapper' olarak görünür.
#                  @wraps sayesinde orijinal fonksiyonun __name__ ve __doc__ bilgisi korunur.
#                  Böylece (debugging) sırasında doğru fonksiyon adını görürsün.

"""
server/api/decorators.py

API ve Use Case katmanlarında kullanılan dekoratörleri içerir.
"""

import time
from functools import wraps
import asyncio

def log_execution_time(func):
    """
    Bir fonksiyonun çalışma süresini ölçen ve terminale yazdıran dekoratör.
    Hem senkron (def) hem asenkron (async def) fonksiyonları destekler.

    Nasıl çalışır:
      1. func çağrılmadan ÖNCE başlangıç zamanını kaydeder
      2. func'ı çalıştırır ve sonucunu tutar
      3. func bittikten SONRA bitiş zamanını alır
      4. Aradaki farkı (geçen süre) hesaplayıp terminale yazdırır

    """
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            baslangic_zamani = time.time()
            print(f"[TIMER] [{func.__name__}] (async) islemi baslatiliyor...")
            sonuc = await func(*args, **kwargs)
            bitis_zamani = time.time()
            gecen_sure = bitis_zamani - baslangic_zamani
            print(f"[OK] [{func.__name__}] islemi tamamlandi. Toplam sure: {gecen_sure:.4f} saniye.\n")
            return sonuc
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            baslangic_zamani = time.time()
            print(f"[TIMER] [{func.__name__}] (sync) islemi baslatiliyor...")
            sonuc = func(*args, **kwargs)
            bitis_zamani = time.time()
            gecen_sure = bitis_zamani - baslangic_zamani
            print(f"[OK] [{func.__name__}] islemi tamamlandi. Toplam sure: {gecen_sure:.4f} saniye.\n")
            return sonuc
        return sync_wrapper
