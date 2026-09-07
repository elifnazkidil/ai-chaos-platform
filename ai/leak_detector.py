import numpy as np
# ─ numpy        : Sayisal hesaplamalar icin. Veriyi Tensor'a cevirmeden once kullaniyoruz. 
#─ numpy polyfit(): Verilen noktalara en uygun dogruyu (line) bulmak icin kullanilir.

# ==============================================================================
# FARK 1: KUTUPHANE
# ==============================================================================
# leak_detector.py  --> Sadece numpy (basit matematik)
# neural_network.py --> numpy + PyTorch (torch, torch.nn) (sinir agi kutuphanesi)
#
# Neden? Bu dosya sadece dogru denklem cozuyor (y = mx + c).
# neural_network.py ise binlerce agirlik parametresini egitim ile ogreniyor.
# ==============================================================================


# ==============================================================================
# FARK 2: SINIF YAPISI
# ==============================================================================
# leak_detector.py  --> class MemoryLeakDetector (normal Python sinifi)
# neural_network.py --> class AnomalyMLP(nn.Module) (PyTorch sinir agi sinifi)
#
# nn.Module'den miras almak modele sunlari kazandirir:
#   - Otomatik gradient hesaplama (backpropagation)
#   - GPU destegi
#   - model.train() / model.eval() modlari
#   - model.parameters() ile tum agirliklara erisim
#
# Bu sinif ise hicbirine ihtiyac duymaz cunku OGRENME YAPMIYOR,
# sadece matematik formulu uyguluyor.
# ==============================================================================

class MemoryLeakDetector:
    #bu sinif memory leak detection yapiyor.
    #bellek sizintisi, bir programin kullandigi bellegin artmaya devam etmesi durumudur.   
    #burada egim hesabi ile sizinti tespiti yapiyor.  
    """

    Bellek metrikleri akisini inceleyen ve saniye bazli egim (slope) hesabi ile
    bellek sizintisi (Memory Leak) durumunu ve tahmini cokme suresini (Time-to-OOM)
    tespit eden prototip anomali dedektoru.

    Kullanim:
      detector = MemoryLeakDetector()
      results = detector.analyze_metrics(metrics_list) 
    
    """

    # ==========================================================================
    # FARK 3: PARAMETRELER
    # ==========================================================================
    # leak_detector.py  --> window_size, min_slope_threshold (2 sabit parametre)
    #                       Bunlari BIZ ELLE belirliyoruz. Degismez.
    #
    # neural_network.py --> input_size, hidden_sizes, dropout_rate, learning_rate
    #                       + binlerce agirlik (weight) ve bias parametresi
    #                       Bunlari MODEL KENDISI veriden ogreniyor.
    #
    # Ornek:
    #   Burada: min_slope_threshold=0.05 --> "Egim 0.05'ten buyukse sizinti var"
    #           Bu esigi BIZ sectik. Yanlis secersek yanlis sonuc verir.
    #
    #   MLP'de: Model 280 ornekten kendi esigini ogrendi.
    #           Hangi CPU+RAM+Disk+Net kombinasyonunun anomali oldugunu KENDISI buldu.
    # ==========================================================================

    def __init__(self, window_size=10, min_slope_threshold=0.05):
        #-- self.window_size : Son kac olcumun (saniyenin) trend analizinde kullanilacagi.
        #-- self.min_slope_threshold: Sizinti sayilmasi icin saniye basina minimum RAM % artis esigi.    
        #-- self.window_size:
            # Kac saniyelik veri setini baz aliyoruz.
            # Deger ne kadar yuksekse o kadar kararli trend analizi yapilir ancak sizinti tespiti gecikir.
        #-- self.min_slope_threshold:
            # Sizinti tespiti icin minimum esik degeri.
            # Deger ne kadar dusukse o kadar hassas analiz yapilir ancak gereksiz uyari (false positive) artar.   
        """
        :param window_size: Son kac olcumun (saniyenin) trend analizinde kullanilacagi.
        :param min_slope_threshold: Sizinti sayilmasi icin saniye basina minimum RAM % artis esigi.
        self.window_size:
            Kac saniyelik veri setini baz aliyoruz.
            Deger ne kadar yuksekse o kadar kararli trend analizi yapilir ancak sizinti tespiti gecikir.
        self.min_slope_threshold:
            Sizinti tespiti icin minimum esik degeri.
            Deger ne kadar dusukse o kadar hassas analiz yapilir ancak gereksiz uyari (false positive) artar.   
        """
        self.window_size = window_size
        self.min_slope_threshold = min_slope_threshold

    # ==========================================================================
    # FARK 4: GIRDI VERISI
    # ==========================================================================
    # leak_detector.py  --> Sadece RAM yuzdeleri listesi (TEK metrik)
    #                       [45.1, 45.3, 45.6, 46.0, ...]
    #
    # neural_network.py --> CPU + RAM + Disk + Network (4 metrik BIRLIKTE)
    #                       [[85, 72, 45, 30],
    #                        [20, 30, 10, 15], ...]
    #
    # Neden onemli?
    #   Burada: RAM tek basina artiyorsa --> sizinti der.
    #           Ama belki CPU da artiyor ve bu NORMAL bir is yuku?
    #           Bunu ANLAYAMAZ cunku sadece RAM'e bakiyor.
    #
    #   MLP'de: CPU+RAM+Disk+Net hepsine birlikte bakiyor.
    #           "CPU dusuk AMA RAM surekli artiyor" --> gercek sizinti!
    #           "CPU yuksek VE RAM yuksek" --> normal yogun is yuku.
    #           Bu FARKI ogrenebilir.
    # ==========================================================================

    def analyze_metrics(self, ram_percents):
        #-- ram_percents        : Analiz edilecek RAM yuzdeleri listesi.
        #-- :return             : Sizinti durumu, egim, cokme tahmini ve risk seviyesini iceren dict.
    
        """
        Gelen RAM yuzdeleri listesini analiz eder.
        :param ram_percents: Son N olcume ait RAM % degerleri listesi (Orn: [45.1, 45.3, 45.6, ...])
        :return: dict (is_leak, slope_per_sec, estimated_seconds_to_oom, risk_level)
        """
        if len(ram_percents) < 3:
            return {
                "is_leak": False,
                "slope_per_sec": 0.0,
                "estimated_seconds_to_oom": None,
                "risk_level": "YETERSIZ VERI",
                "message": "Trend tespiti icin en az 3 veri noktasi gereklidir."
            }

        # Son window_size kadar noktayi al
        recent_data = ram_percents[-self.window_size:]
        time_steps = np.arange(len(recent_data))

        # ==========================================================================
        # FARK 5: KARAR MEKANIZMASI (EN BUYUK FARK)
        # ==========================================================================
        # leak_detector.py  --> Dogrusal Regresyon (1 satir matematik)
        #                       y = m*x + c  -->  slope (egim) hesapla
        #                       slope > esik mi? --> Evet/Hayir
        #
        # neural_network.py --> MLP Forward Pass (3 katman, yuzlerce islem)
        #                       Girdi --> Linear(4,64) --> ReLU --> Linear(64,32) --> ReLU
        #                       --> Linear(32,16) --> ReLU --> Linear(16,1) --> Sigmoid
        #                       --> 0.0 ile 1.0 arasi anomali skoru
        #
        # Analoji:
        #   Bu dosya  = Termometre (ates var mi yok mu, tek sayi)
        #   MLP       = Doktor (tum belirtilere bakip teshis koyuyor)
        # ==========================================================================

        # Dogrusal Regresyon ile Egim Hesabi: y = m*x + c
        #-- y = m*x + c : Verilen noktalara en uygun dogruyu (line) bulmak icin kullanilir.       
        slope, intercept = np.polyfit(time_steps, recent_data, 1)

        current_ram = recent_data[-1]
        remaining_ram = 100.0 - current_ram

        # ==========================================================================
        # FARK 6: ESIK KARARI
        # ==========================================================================
        # leak_detector.py  --> SABIT esik: slope >= 0.05 ise sizinti
        #                       Bu 0.05 degerini BIZ sectik.
        #                       Yanlis secersek: ya cok alarm (false positive)
        #                       ya hic alarm yok (false negative)
        #
        # neural_network.py --> OGRENILMIS esik: Sigmoid ciktisi >= 0.5 ise anomali
        #                       0.5 sabit ama modelin IC agirliklari veriden ogrendi.
        #                       Yani "neyin anomali olduguna" model karar veriyor.
        # ==========================================================================

        is_leak = slope >= self.min_slope_threshold
        estimated_seconds = None

        if is_leak and slope > 0:
            # ==================================================================
            # FARK 7: EK BILGI (Time-to-OOM)
            # ==================================================================
            # leak_detector.py  --> Tahmini cokme suresi hesaplayabilir
            #                       (kalan RAM / egim)
            #                       Bu EKSTRA bilgi MLP'de yok!
            #                       MLP sadece "anomali mi degil mi" diyor.
            #
            # Bu, leak_detector'in AVANTAJI:
            #   Basit ama ACIKLANABILIR. "Neden alarm verdin?" sorusuna:
            #   "Cunku RAM saniyede %0.3 artiyor, 200 saniyeye cokecek" diyebilir.
            #
            #   MLP'ye "neden?" diye soramazsin. Sadece "skor: 0.93" der.
            #   Bu yuzden ikisini BIRLIKTE kullanmak en iyisi.
            # ==================================================================
            estimated_seconds = round(remaining_ram / slope, 1)

        # ==========================================================================
        # FARK 8: RISK SEVIYELERI
        # ==========================================================================
        # leak_detector.py  --> if/elif kurallari (elle yazilmis)
        #                       60 saniyeden az --> KRITIK
        #                       300 saniyeden az --> YUKSEK
        #                       Bunlar SABIT kurallar, degismez.
        #
        # neural_network.py --> Skor araligina gore (0.0 - 1.0)
        #                       < 0.3 --> NORMAL
        #                       < 0.5 --> DUSUK
        #                       < 0.7 --> ORTA
        #                       < 0.9 --> YUKSEK
        #                       >= 0.9 --> KRITIK
        #                       Skorun KENDISI ogrenilmis, araliklar sabit.
        # ==========================================================================

        if not is_leak:
            risk_level = "NORMAL"
        elif estimated_seconds and estimated_seconds < 60:
            risk_level = "KRITIK (CRITICAL)"
        elif estimated_seconds and estimated_seconds < 300:
            risk_level = "YUKSEK (HIGH)"
        else:
            risk_level = "ORTA (MEDIUM)"
            #-- risk_level: Algilanan risk seviyesi: NORMAL, KRITIK (CRITICAL), YUKSEK (HIGH), ORTA (MEDIUM).

        # ==========================================================================
        # FARK 9: CIKTI FORMATI
        # ==========================================================================
        # leak_detector.py  --> is_leak (True/False), slope, estimated_seconds_to_oom
        #                       Daha DETAYLI ve ACIKLANABILIR cikti
        #
        # neural_network.py --> anomaly_score (0.0-1.0), is_anomaly, risk_level
        #                       Daha BASIT ama daha AKILLI cikti
        # ==========================================================================

        return {
            "is_leak": is_leak,
            "slope_per_sec": round(slope, 4),
            "current_ram_percent": current_ram,
            "estimated_seconds_to_oom": estimated_seconds,
            "risk_level": risk_level,
            "message": f"Bellek sizintisi algilandi! Egim: +%{round(slope, 2)}/sn" if is_leak else "Bellek kullanimi kararli."
        }

# ==============================================================================
# OZET KARSILASTIRMA TABLOSU
# ==============================================================================
#
# Ozellik              | leak_detector.py         | neural_network.py
# ---------------------|--------------------------|---------------------------
# Yontem               | Dogrusal regresyon       | MLP (sinir agi)
# Kutuphane            | numpy                    | numpy + PyTorch
# Girdi                | Sadece RAM (1 metrik)    | CPU+RAM+Disk+Net (4 metrik)
# Ogrenme              | YOK (sabit kurallar)     | VAR (veriden ogrenir)
# Egitim gerekli mi?   | Hayir                    | Evet (epochs, backprop)
# Hiz                  | Cok hizli                | Daha yavas
# Aciklanabilirlik     | Yuksek ("egim %0.3/sn")  | Dusuk ("skor: 0.87")
# Karmasik pattern     | Yakalayamaz              | Yakalayabilir
# Time-to-OOM tahmini  | Var                      | Yok
# GPU destegi          | Yok                      | Var
#
# SONUC: Ikisi RAKIP degil, TAMAMLAYICI.
#   leak_detector  = hizli, basit, aciklanabilir on filtre
#   neural_network = akilli, karmasik, ogrenen derin analiz
# ==============================================================================
