"""
ai/neural_network.py

Yapay Sinir Ağı Modeli — Anomali Tespit Sistemi
=================================================
Bu dosya, sistemden toplanan metrikleri (CPU, RAM, Disk, Network)
analiz ederek anomali tespiti yapan Çok Katmanlı Algılayıcı (MLP)
modelini içerir.

leak_detector.py'deki sabit eşik (threshold) yaklaşımının yerine,
bu model VERİDEN ÖĞRENEREK anomali tespiti yapar.

İş Akışı (Pipeline):
  1. chaos.py (veri üret)
  2. network.py (API'ye gönder)
  3. main.py (veritabanına kaydet)
  4. neural_network.py (AI ile analiz et ve tahmin yap - bu dosya)
  5. Dashboard (tahminleri ve anomalileri göster)

Kullanılan Kavramlar:
  - MLP (Multi-Layer Perceptron): Çok katmanlı tam bağlantılı sinir ağı
  - Forward Pass: Girdiden çıktıya hesaplama
  - Backpropagation: Hatayı geriye yayarak ağırlıkları güncelleme
"""

import torch
import torch.nn as nn
# ─ torch        : PyTorch kütüphanesi. Tensor işlemleri ve otomatik türev (autograd) sağlar.
# ─ torch.nn     : Sinir ağı katmanlarını (Linear, ReLU, vb.) içeren modül.
#                  Tüm modeller nn.Module'den miras alır.

import numpy as np
# ─ numpy        : Sayısal hesaplamalar için. Veriyi Tensor'a çevirmeden önce kullanıyoruz.


# ══════════════════════════════════════════════════════════════
# 1. MODEL MİMARİSİ — Çok Katmanlı Algılayıcı (MLP)
# ══════════════════════════════════════════════════════════════

class AnomalyMLP(nn.Module):
    """
    Sistem metriklerinden anomali tespit eden MLP modeli.

    Mimari:
        Girdi (4 metrik) → 64 nöron → 32 nöron → 16 nöron → 1 çıkış (anomali skoru)

        Girdi Katmanı        Gizli Katman 1    Gizli Katman 2    Gizli Katman 3    Çıkış
        ─────────────        ──────────────    ──────────────    ──────────────    ─────
        CPU %     (0-100)  →                                                    →
        RAM %     (0-100)  →   64 nöron    →    32 nöron    →    16 nöron    →  Anomali
        Disk %    (0-100)  →   + ReLU          + ReLU           + ReLU          Skoru
        Network % (0-100)  →                                                    (0-1)

    Neden 3 gizli katman?
        - Katman 1 (64): Her bir metriğin bireysel pattern'lerini öğrenir
        - Katman 2 (32): Metrikler arası ilişkileri yakalar (CPU+RAM birlikte artışı)
        - Katman 3 (16): Karmaşık anomali pattern'lerini birleştirir
    """

    def __init__(self, input_size=4, hidden_sizes=None, dropout_rate=0.2):
        """
        Modelin katmanlarını tanımlar (ama henüz hesaplama yapmaz).

        :param input_size: Girdi özellik sayısı (CPU, RAM, Disk, Network = 4)
        :param hidden_sizes: Gizli katmanlardaki nöron sayıları listesi
                             Varsayılan: [64, 32, 16]
        :param dropout_rate: Overfitting'i önlemek için rastgele nöron kapatma oranı
                             0.2 = her eğitim adımında nöronların %20'si rastgele kapatılır
        """
        super().__init__()
        # super().__init__() → nn.Module'ün kendi başlatma kodunu çalıştırır.
        # Bu ZORUNLUDUR, yoksa PyTorch modelin parametrelerini bulamaz.

        if hidden_sizes is None:
            hidden_sizes = [64, 32, 16]

        # ── Katmanları Tanımla ──────────────────────────────────
        # nn.Sequential: Katmanları sıralı bir boru hattı (pipeline) olarak birleştirir.
        # Veri sırasıyla her katmandan geçer: Linear → ReLU → Dropout → Linear → ...

        layers = []  # Katmanları bu listeye ekleyeceğiz

        # Girdi boyutu: ilk katmanın input_size'ı dışarıdan geliyor
        prev_size = input_size

        for hidden_size in hidden_sizes:
            # ── Tam Bağlantılı Katman (Fully Connected / Linear) ──
            # nn.Linear(giriş, çıkış): Her girdi nöronunu her çıktı nöronuna bağlar
            # Formül: çıkış = girdi × ağırlık_matrisi + bias
            # Parametreler: ağırlık matrisi (prev_size × hidden_size) + bias vektörü (hidden_size)
            layers.append(nn.Linear(prev_size, hidden_size))

            # ── Batch Normalization ──
            # Her katmanın çıktısını normalize eder (ortalama=0, std=1).
            # Eğitimi hızlandırır ve daha kararlı hale getirir.
            layers.append(nn.BatchNorm1d(hidden_size))

            # ── ReLU Aktivasyon ──
            # ReLU(x) = max(0, x)
            # Negatif değerleri sıfırlar, pozitif değerleri geçirir.
            # Bu olmadan ağ sadece doğrusal (düz çizgi) ilişkileri öğrenebilir.
            layers.append(nn.ReLU())

            # ── Dropout (Seyreltme) ──
            # Eğitim sırasında rastgele bazı nöronları kapatır.
            # Neden? Modelin tüm nöronlara "bağımlı" olmasını engeller → overfitting'i azaltır.
            # Test/tahmin sırasında otomatik olarak devre dışı kalır.
            layers.append(nn.Dropout(dropout_rate))

            prev_size = hidden_size  # Bir sonraki katmanın girdi boyutu = bu katmanın çıktı boyutu

        # ── Çıkış Katmanı ──
        # Son gizli katmandan (16 nöron) tek bir çıkışa (1 olma nedni) bağlanır.
        layers.append(nn.Linear(prev_size, 1))

        # ── Sigmoid Aktivasyon ──
        # Sigmoid(x) = 1 / (1 + e^(-x))
        # Çıkışı 0 ile 1 arasına sıkıştırır → anomali OLASILIĞI olarak yorumlanır.
        # 0.0 = kesinlikle normal, 1.0 = kesinlikle anomali
        layers.append(nn.Sigmoid())

        # Tüm katmanları nn.Sequential içine koy
        self.network = nn.Sequential(*layers) # listeyi açma (unpacking) operatörü.

    def forward(self, x):
        """
        İleri Geçiş (Forward Pass) — Modelin ana hesaplama fonksiyonu.

        Girdi verisini tüm katmanlardan sırasıyla geçirir ve anomali skorunu döndürür.
        PyTorch bu fonksiyonu model(x) çağrıldığında otomatik olarak çalıştırır.

        :param x: Girdi tensörü, boyut: (batch_size, 4)
                  Örn: [[85.0, 72.0, 45.0, 30.0],   ← 1. örnek
                        [20.0, 30.0, 10.0, 15.0]]    ← 2. örnek
        :return: Anomali skoru tensörü, boyut: (batch_size, 1)
                 Örn: [[0.87],   ← 1. örnek %87 anomali
                       [0.12]]   ← 2. örnek %12 anomali (normal)
        """
        return self.network(x)


# ══════════════════════════════════════════════════════════════
# 2. VERİ ÖN İŞLEME — Normalizasyon
# ══════════════════════════════════════════════════════════════

class MetricNormalizer:
    """
    Ham metrikleri 0-1 arasına normalize eden ön işlemci.

    Neden normalize etmeliyiz?
        CPU:     0 - 100   (%)
        RAM:     0 - 100   (%)
        Disk:    0 - 100   (%)
        Network: 0 - 10000 (Mbps)

        Network değeri CPU'dan 100 kat büyük. Normalize etmezsek
        model Network'e aşırı önem verip diğerlerini görmezden gelir.

    Min-Max Normalizasyon formülü:
        normalized = (değer - min) / (max - min)
        Sonuç her zaman 0 ile 1 arasında olur.
    """

    def __init__(self):
        # Her metrik için varsayılan min-max aralıkları
        self.feature_ranges = {
            "cpu_percent":  {"min": 0.0, "max": 100.0},
            "ram_percent":  {"min": 0.0, "max": 100.0},
            "disk_percent": {"min": 0.0, "max": 100.0},
            "net_percent":  {"min": 0.0, "max": 100.0},
        }
        self.is_fitted = False  # Gerçek veriden aralık öğrenildi mi?
        #Ben henüz bir şey öğrenmedim, bana veriyi
        # dönüştürtmeden önce mutlaka veriyi gösterip fit etmelisin    

    def fit(self, data):
        """
        Eğitim verisinden her özelliğin gerçek min-max aralıklarını öğrenir.

        :param data: numpy array, boyut: (örnek_sayısı, 4)
        """
        feature_names = list(self.feature_ranges.keys())
        for i, name in enumerate(feature_names):#enumerate kullanırsak bize hem sıra numarasını (index) hem de elemanın kendisini verir:
            # data[:, i]  ← NumPy slicing: tüm satırlar, i'inci sütun
#feature_names listesi şu şekilde: ["cpu_percent", "ram_percent", "disk_percent", "net_percent"]    
            self.feature_ranges[name]["min"] = float(np.min(data[:, i]))
            self.feature_ranges[name]["max"] = float(np.max(data[:, i]))
        self.is_fitted = True

    def transform(self, data):
        """
        Veriyi öğrenilen aralıklara göre 0-1 arasına normalize eder.

        :param data: numpy array, boyut: (örnek_sayısı, 4)
        :return: numpy array, normalize edilmiş veri
        """
        normalized = np.zeros_like(data, dtype=np.float32)
        feature_names = list(self.feature_ranges.keys())

        for i, name in enumerate(feature_names):
            min_val = self.feature_ranges[name]["min"]
            max_val = self.feature_ranges[name]["max"]
            range_val = max_val - min_val

            if range_val == 0:
                # Tüm değerler aynıysa (örn: hep 50%), 0 döndür
                normalized[:, i] = 0.0
            else:
                normalized[:, i] = (data[:, i] - min_val) / range_val

        return normalized

    def fit_transform(self, data):
        """fit() ve transform()'u tek adımda yapar."""
        self.fit(data)
        return self.transform(data)


# ══════════════════════════════════════════════════════════════
# 3. EĞİTİM MOTORU — Model Eğitici (Trainer)
# ══════════════════════════════════════════════════════════════

class AnomalyTrainer:
    """
    MLP modelini eğiten ve tahmin yapan ana sınıf.

    Eğitim Döngüsü (Training Loop):
        Her epoch'ta (tam tur) şu 4 adım tekrarlanır:

        1. Forward Pass  : Veriyi modelden geçir → tahmin üret
        2. Loss Hesabı   : Tahmin ile gerçek değeri karşılaştır → hata hesapla
        3. Backward Pass : Hatayı geriye yayarak gradient'leri hesapla
        4. Optimizer Step: Gradient'lere göre ağırlıkları güncelle

        Bu döngü her tekrarda modeli biraz daha iyi yapar.
    """

    def __init__(self, input_size=4, hidden_sizes=None, learning_rate=0.001):
        """
        :param learning_rate: Öğrenme hızı — her adımda ağırlıklar ne kadar değişsin?
                              Çok büyük = hedefi atlar, çok küçük = çok yavaş öğrenir
        """
        # ── Model ──
        self.model = AnomalyMLP(input_size=input_size, hidden_sizes=hidden_sizes)

        # BCELoss = Binary Cross-Entropy Loss
        # İkili sınıflandırma (normal/anomali) için en uygun loss fonksiyonu.
        # Modelin tahmini gerçek değere ne kadar yakınsa loss o kadar düşük olur.
        self.criterion = nn.BCELoss()

        # ── Optimizer (Optimizasyon Algoritması) ──
        # Adam = Adaptive Moment Estimation
        # Gradient descent'in geliştirilmiş versiyonu.
        # Her parametre için öğrenme hızını otomatik ayarlar.
        # model.parameters() → modelin tüm öğrenilebilir ağırlıklarını verir.
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=learning_rate
        )

        # ── Normalizer ──
        self.normalizer = MetricNormalizer()

        # ── Eğitim geçmişi ──
        self.train_history = []  # Her epoch'taki loss değerini kaydet

    def prepare_data(self, features, labels):
        """
        Numpy array'leri PyTorch Tensor'larına çevirir.

        Neden Tensor? PyTorch sadece Tensor'lar üzerinde gradient hesaplayabilir.
        Numpy array'ler "hesap makinesi", Tensor'lar "akıllı hesap makinesi" gibidir.

        :param features: Girdi verileri (CPU, RAM, Disk, Net) - numpy array
        :param labels: Etiketler (0=normal, 1=anomali) - numpy array
        :return: (X_tensor, y_tensor) çifti
        """
        # Normalizasyon: ham değerleri 0-1 arasına çek
        if not self.normalizer.is_fitted:
            features_normalized = self.normalizer.fit_transform(features)
        else:
            features_normalized = self.normalizer.transform(features)

        # Numpy → Tensor dönüşümü
        X_tensor = torch.FloatTensor(features_normalized)
        # FloatTensor: 32-bit float tipinde tensor oluşturur
        # Neden float32? GPU'lar bu tipte en hızlı çalışır.

        y_tensor = torch.FloatTensor(labels).reshape(-1, 1)
        # reshape(-1, 1): [0, 1, 1, 0] → [[0], [1], [1], [0]]
        # Modelin çıktısı (batch, 1) boyutunda, etiketler de aynı boyutta olmalı

        return X_tensor, y_tensor

    def train(self, features, labels, epochs=100, verbose=True):
        """
        Modeli eğitir.

        :param verbose: Her 10 epoch'ta loss değerini yazdırsın mı?
        :return: Eğitim geçmişi (her epoch'un loss değeri)

        """
        # Veriyi hazırla
        X, y = self.prepare_data(features, labels)

        # Modeli eğitim moduna al
        # Eğitim modunda: Dropout aktif, BatchNorm eğitim istatistiklerini kullanır
        #r (self.model.train()), modele "Şu an eğitim (öğrenme) aşamasındayız, ona göre davran" diyor. 
        # Bunun tam tersi self.model.eval() (değerlendirme/test) modudur.
        #dropout katmanı modelin aşırı öğrenmesini (overfitting) engeller.
        #batchnorm (toplu normalizasyon), katmanların içindeki verileri normalleştirerek 
        # modelin daha hızlı ve kararlı öğrenmesini sağlar.
        
        self.model.train()

        for epoch in range(epochs):
            # ═══ EĞİTİM DÖNGÜSÜNÜN 4 ADIMI ═══

            # ADIM 1: Forward Pass (İleri Geçiş)
            # Veriyi modelden geçir → tahmin üret
            predictions = self.model(X)
            # model(X) çağrısı otomatik olarak model.forward(X)'i çalıştırır.
            # PyTorch arkaplanda computational graph oluşturur (backprop için).

            # ADIM 2: Loss Hesabı (Hata Hesabı)
            # Tahmin ile gerçek değeri karşılaştır
            loss = self.criterion(predictions, y)
            # BCELoss formülü: -[y·log(ŷ) + (1-y)·log(1-ŷ)]
            # y=1, ŷ=0.9 → loss düşük (iyi tahmin)
            # y=1, ŷ=0.1 → loss yüksek (kötü tahmin)

            # ADIM 3: Backward Pass (Geri Yayılım)
            self.optimizer.zero_grad()
            # zero_grad(): Önceki adımın gradient'lerini sıfırla.
            # Bunu yapmazsak gradient'ler birikir ve yanlış güncelleme olur!

            loss.backward()
            # backward(): Chain Rule ile her parametrenin gradient'ini hesapla.
            # "Bu ağırlığı artırsam loss artar mı azalır mı, ne kadar?"

            # ADIM 4: Optimizer Step (Ağırlık Güncelleme)
            self.optimizer.step()
            # step(): Her ağırlığı gradient'in TERSİ yönünde güncelle.
            # yeni_ağırlık = eski_ağırlık - learning_rate × gradient
            # Gradient pozitifse → ağırlığı azalt (loss'u düşürmek için)
            # Gradient negatifse → ağırlığı artır

            # ═══════════════════════════════════

            # Loss değerini kaydet
            current_loss = loss.item()
            # .item(): Tensor'dan Python float'a çevirir (tek elemanlı tensor için)
            self.train_history.append(current_loss)

            # Her 10 epoch'ta ilerlemeyi yazdır
            if verbose and (epoch + 1) % 10 == 0:
                print(f"  Epoch [{epoch+1:3d}/{epochs}] -> Loss: {current_loss:.4f}")

        if verbose:
            print(f"\n  [OK] Egitim tamamlandi! Son loss: {self.train_history[-1]:.4f}")

        return self.train_history

    def predict(self, features):
        """
        Eğitilmiş model ile tahmin yapar.
        :return: Anomali skorları - numpy array (0.0 ile 1.0 arası)
        """
        # Modeli değerlendirme (evaluation) moduna al
        # Eval modunda: Dropout kapalı, BatchNorm test istatistiklerini kullanır
        self.model.eval()

        # Normalize et
        features_normalized = self.normalizer.transform(features)
        X = torch.FloatTensor(features_normalized)

        # torch.no_grad(): Gradient hesaplamasını kapat
        # Tahmin sırasında gradient'e ihtiyaç yok, bu sayede:
        # - Bellek tasarrufu sağlar
        # - Hesaplama hızlanır
        with torch.no_grad():
            scores = self.model(X)

        # Tensor → Numpy array'e çevir
        return scores.numpy().flatten()
        # .numpy(): Tensor → numpy
        # .flatten(): [[0.87], [0.12]] → [0.87, 0.12]

    def classify(self, features, threshold=0.5):
        """
        Anomali skorlarını ikili sınıflandırmaya çevirir.
        classify fonksiyonu bu ham sayıyı alıp insan diline
        (ve API'nin kullanabileceği bir formata) çevirir.

        """
        scores = self.predict(features)
        results = []
        #skorların üzerinden geçeriz.   
    
        for score in scores:
            # Risk seviyesi belirleme
            if score < 0.3:
                risk_level = "NORMAL"
            elif score < 0.5:
                risk_level = "DÜŞÜK (LOW)"
            elif score < 0.7:
                risk_level = "ORTA (MEDIUM)"
            elif score < 0.9:
                risk_level = "YÜKSEK (HIGH)"
            else:
                risk_level = "KRİTİK (CRITICAL)"

            results.append({
                "anomaly_score": round(float(score), 4),
                "is_anomaly": bool(score >= threshold),
                "risk_level": risk_level,
                "label": "ANOMALİ" if score >= threshold else "NORMAL"
            })

        return results

    def save_model(self, filepath="ai/anomaly_model.pth"):
        """
        Eğitilmiş modeli dosyaya kaydeder.
        .pth = PyTorch model dosyası formatı

        :param filepath: Kayıt yolu
        """
        torch.save({
            "model_state_dict": self.model.state_dict(),
            # state_dict(): Modelin tüm ağırlıklarını ve bias'larını içeren sözlük
            "optimizer_state_dict": self.optimizer.state_dict(),
            # Optimizer'ın durumu (momentum, learning rate (ogrenme hizi.modelin adimlarini ne kadar guncelleyecegi)vb.)
            "train_history": self.train_history,
            "normalizer_ranges": self.normalizer.feature_ranges,
            "normalizer_fitted": self.normalizer.is_fitted,
        }, filepath)
        print(f"  [SAVE] Model kaydedildi: {filepath}")

    def load_model(self, filepath="ai/anomaly_model.pth"):
        """
        Kaydedilmiş modeli dosyadan yükler.

        :param filepath: Model dosyasının yolu
        """
        checkpoint = torch.load(filepath, weights_only=False)
        #kayıtlı modelin ağırlıklarını yükle.           
        self.model.load_state_dict(checkpoint["model_state_dict"])
        #optimizer'ın durumunu yükle
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        #training geçmişini yükle
        self.train_history = checkpoint["train_history"]
        #normalizer'ın durumunu yükle
        self.normalizer.feature_ranges = checkpoint["normalizer_ranges"]
        #normalizer'ın eğitilip eğitilmediğini kontrol et
        self.normalizer.is_fitted = checkpoint["normalizer_fitted"]
        #modeli eğitim moduna al
        self.model.train()
        #modelin durumunu yazdır
        print(f"  [LOAD] Model yuklendi: {filepath}")


# ══════════════════════════════════════════════════════════════
# 4. DEMO — Modeli Test Et
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(" AI Chaos Platform - Anomali Tespit Modeli (MLP)")
    print("=" * 60)

    # ── Sentetik Eğitim Verisi Oluştur ──────────────────────
    # Gerçek metriklerimiz henüz yeterli olmadığı için
    # yapay (sentetik) veri ile modeli test ediyoruz.
    print("\n[DATA] Sentetik egitim verisi olusturuluyor...")

    np.random.seed(42)  # Tekrarlanabilirlik için sabit seed

    # Normal durumlar (label=0): Düşük-orta metrik değerleri
    normal_samples = np.random.uniform(
        low=[10, 20, 5, 5],       # Min: CPU=10%, RAM=20%, Disk=5%, Net=5%
        high=[50, 55, 40, 50],    # Max: CPU=50%, RAM=55%, Disk=40%, Net=50%
        size=(200, 4)              # 200 normal örnek, her biri 4 metrik
    )

    # Anomali durumları (label=1): Yüksek metrik değerleri
    anomaly_samples = np.random.uniform(
        low=[70, 75, 60, 60],     # Min: CPU=70%, RAM=75%, Disk=60%, Net=60%
        high=[100, 100, 100, 100], # Max: hepsi %100'e kadar
        size=(80, 4)               # 80 anomali örneği
    )

    # Verileri birleştir
    X_train = np.vstack([normal_samples, anomaly_samples]).astype(np.float32)
    y_train = np.array(
        [0] * 200 + [1] * 80,     # İlk 200 → normal (0), son 80 → anomali (1)
        # eğitim verilerini hiçbir yerden çekmiyoruz, kendimiz uyduruyoruz (sentetik veri üretiyoruz).=Prototipleme 
        dtype=np.float32
    )
    """

        Gerçekte nasıl olacak?
        Pipeline sistemini (Boru hattını) tam olarak kurduğumuzda şöyle olacak:

        chaos.py (Ajan) sürekli gerçek metrikleri toplayacak.
        network.py bu verileri API'ye gönderecek.
        server/api/main.py bu verileri bir veritabanına (veya bir dosyaya, örneğin metrics.json veya SQLite) kaydedecek.
        Bizim Neural Network'ümüz işte o zaman np.random kullanmayacak; gidip o veritabanından aylarca/günlerce toplanmış 
        GERÇEK verileri çekecek ve kendi üzerinde eğitecek.


    """
    # Veriyi karıştır (shuffle) — modelin sırayı ezberlemesini engelle
    shuffle_idx = np.random.permutation(len(X_train))
    X_train = X_train[shuffle_idx]
    y_train = y_train[shuffle_idx]

    print(f"  Normal ornekler : {(y_train == 0).sum()}")
    print(f"  Anomali ornekler: {(y_train == 1).sum()}")
    print(f"  Toplam          : {len(y_train)}")

    # ── Modeli Eğit ─────────────────────────────────────────
    print("\n[TRAIN] Model egitimi basliyor...\n")

    trainer = AnomalyTrainer(
        input_size=4,                    # 4 metrik girdi
        hidden_sizes=[64, 32, 16],       # 3 gizli katman
        learning_rate=0.001              # Öğrenme hızı
    )

    history = trainer.train(
        features=X_train,
        labels=y_train,
        epochs=100,                      # 100 tur eğitim
        verbose=True
    )

    # ── Test Tahminleri ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  [TEST] Test Tahminleri")
    print("=" * 60)

    test_cases = np.array([
        [25, 30, 15, 20],    # Normal: düşük değerler
        [85, 90, 75, 80],    # Anomali: yüksek değerler
        [45, 50, 35, 40],    # Normal: orta değerler
        [95, 98, 90, 95],    # Anomali: çok yüksek
        [30, 82, 20, 25],    # Karışık: sadece RAM yüksek
    ], dtype=np.float32)
#"Bu nedir?" diye sormuyoruz, sadece "Bunu al ve bana tahminini söyle"
    labels = ["Normal (dusuk)", "Anomali (yuksek)", "Normal (orta)",
              "Anomali (kritik)", "Karisik (RAM spike)"]

    results = trainer.classify(test_cases)#classify fonksiyonu bu ham sayıyı alıp 
    #insan diline (ve API'nin kullanabileceği bir formata) çevirir.

    for i, (result, label) in enumerate(zip(results, labels)):
        marker = "[ALERT]" if result["is_anomaly"] else "[OK]   "
        print(f"\n  {marker} Test {i+1}: {label}")
        print(f"     Metrikler -> CPU:{test_cases[i][0]:.0f}% RAM:{test_cases[i][1]:.0f}% "
              f"Disk:{test_cases[i][2]:.0f}% Net:{test_cases[i][3]:.0f}%")
        print(f"     Skor: {result['anomaly_score']:.4f} | "
              f"Karar: {result['label']} | Risk: {result['risk_level']}")

    # ── 5. Egitim Loss Grafigini Cizdir (Training Loss Curve) ──
    print("\n Training Loss Curve (Egitim Hata Grafigi) cizdiriliyor...")
    try:
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(10, 5))
        plt.plot(history, label="Training Loss (BCE)", color="blue", linewidth=2)
        plt.title("Yapay Sinir Agi - Egitim Hata Gecmisi (Training Loss Curve)")
        plt.xlabel("Epoch (Egitim Turu)")
        plt.ylabel("Loss (Hata Miktari)")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.legend()
        
        # Grafiği dosyaya kaydet
        plt.savefig("ai/training_loss_curve.png")
        print(" Grafik 'ai/training_loss_curve.png' olarak kaydedildi.")
        
        # Ekranda göster
        plt.show()
        
    except ImportError:
        print("  [UYARI] 'matplotlib' kütüphanesi yüklü değil. Grafik çizilemedi.")
        print("  Yüklemek için terminale yaziniz: pip install matplotlib")

    print("\n" + "=" * 60)
    print(" Demo tamamlandi")
    print("=" * 60)
