"""
ai/neural_net_intro.py

YSA Giris Scripti - Andrej Karpathy Micrograd Videosundan Ilhamla
===================================================================
Bu dosya yapay sinir aglarinin EN TEMEL yapilarini gosteriyor:

1. Tek bir noron nasil calisir? (NumPy ile)
2. Ayni noron PyTorch ile nasil yazilir?
3. Backpropagation (geri yayilim) nasil calisir?
4. NumPy vs PyTorch farklari neler?

Karpathy'nin videosundaki "Value" sinifinin basitlestirilmis hali.
Video: "The spelled-out intro to neural networks and backpropagation"
"""

import numpy as np

# PyTorch yuklu mu kontrol et
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# ======================================================================
# 1. NUMPY ILE BASIT BIR NORON
# ======================================================================

def numpy_neuron():
    """
    NumPy ile tek bir noronun calismasi.

    Noron formulu:
        y = activation(w1*x1 + w2*x2 + w3*x3 + bias)

    Analoji:
        Noron = karar verici
        Girdiler (x) = bilgiler
        Agirliklar (w) = her bilginin onemi
        Bias = on yargi
        Aktivasyon = son karar filtresi
    """
    print("=" * 60)
    print("  [NUMPY] Tek Noron Simulasyonu")
    print("=" * 60)

    # Girdiler (inputs) - Sistem metrikleri
    x = np.array([0.85, 0.72, 0.45])
    #              CPU    RAM    Disk
    #              %85    %72    %45
    print(f"\n  Girdiler (x): CPU={x[0]}, RAM={x[1]}, Disk={x[2]}")

    # Agirliklar (weights) - Her metrigin onemi
    w = np.array([0.5, 0.8, 0.2])
    #              CPU    RAM    Disk
    #              az     cok    biraz
    #              onemli onemli onemli
    print(f"  Agirliklar (w): CPU={w[0]}, RAM={w[1]}, Disk={w[2]}")
    print(f"  (RAM'a en cok onem veriliyor cunku bellek sizintisi ariyoruz)")

    # Bias - On yargi/kayma
    bias = -0.5
    print(f"  Bias: {bias}")

    # ADIM 1: Agirlikli toplam (weighted sum)
    weighted_sum = np.dot(x, w) + bias
    # np.dot = nokta carpim: x1*w1 + x2*w2 + x3*w3
    # = 0.85*0.5 + 0.72*0.8 + 0.45*0.2 + (-0.5)
    # = 0.425 + 0.576 + 0.09 + (-0.5)
    # = 0.591
    print(f"\n  Agirlikli toplam = x.w + b")
    print(f"    = ({x[0]}*{w[0]}) + ({x[1]}*{w[1]}) + ({x[2]}*{w[2]}) + ({bias})")
    print(f"    = {x[0]*w[0]:.3f} + {x[1]*w[1]:.3f} + {x[2]*w[2]:.3f} + ({bias})")
    print(f"    = {weighted_sum:.4f}")

    # ADIM 2: Aktivasyon fonksiyonu (ReLU)
    relu_output = max(0, weighted_sum)
    print(f"\n  ReLU({weighted_sum:.4f}) = max(0, {weighted_sum:.4f}) = {relu_output:.4f}")

    # ADIM 3: Sigmoid (olasiliga cevirme)
    sigmoid_output = 1 / (1 + np.exp(-weighted_sum))
    print(f"  Sigmoid({weighted_sum:.4f}) = 1/(1+e^(-{weighted_sum:.4f})) = {sigmoid_output:.4f}")
    print(f"\n  Yorum: %{sigmoid_output*100:.1f} olasilikla anomali")

    return weighted_sum, relu_output, sigmoid_output


# ======================================================================
# 2. PYTORCH ILE AYNI NORON
# ======================================================================

def pytorch_neuron():
    """
    PyTorch ile ayni noronun implementasyonu.
    Buyuk fark: PyTorch gradient'i OTOMATIK hesaplar (autograd).
    NumPy'da bunu ELLE yapmamiz gerekirdi.
    """
    if not TORCH_AVAILABLE:
        print("\n  [UYARI] PyTorch yuklu degil. Bu bolum atlaniyor.")
        print("  Yuklemek icin: pip install torch")
        return None, None, None

    print("\n" + "=" * 60)
    print("  [PYTORCH] Ayni Noron - Tensor Versiyonu")
    print("=" * 60)

    # Ayni degerler ama simdi Tensor olarak
    # requires_grad=True: "Bu degiskenlerin gradient'ini takip et"
    x = torch.tensor([0.85, 0.72, 0.45])
    w = torch.tensor([0.5, 0.8, 0.2], requires_grad=True)
    bias = torch.tensor(-0.5, requires_grad=True)

    print(f"\n  Girdiler (tensor):    {x.tolist()}")
    print(f"  Agirliklar (tensor):  {w.tolist()}")
    print(f"  Bias (tensor):        {bias.item()}")

    # Forward pass - NumPy ile AYNI hesaplama
    weighted_sum = torch.dot(x, w) + bias
    sigmoid_output = torch.sigmoid(weighted_sum)

    print(f"\n  Agirlikli toplam: {weighted_sum.item():.4f}")
    print(f"  Sigmoid cikti:    {sigmoid_output.item():.4f}")

    # BUYUK FARK: Backpropagation (geri yayilim)
    # NumPy'da bunu ELLE hesaplamamiz gerekirdi.
    # PyTorch'ta TEK SATIR:
    print(f"\n  --- Backpropagation (Geri Yayilim) ---")

    # Hedef deger: 1.0 (bu verinin anomali olmasi gerekiyor)
    target = torch.tensor(1.0)
    loss = (sigmoid_output - target) ** 2  # MSE loss
    print(f"  Hedef: {target.item()}")
    print(f"  Tahmin: {sigmoid_output.item():.4f}")
    print(f"  Loss (hata): {loss.item():.4f}")

    # Gradient hesapla - TEK SATIR!
    loss.backward()
    # Bu satir chain rule ile TUM gradient'leri otomatik hesaplar.
    # NumPy'da bu hesaplamayi elle yapmamiz gerekirdi.

    print(f"\n  Gradient'ler (otomatik hesaplandi):")
    print(f"    dL/dw = {w.grad.tolist()}")
    print(f"    dL/dbias = {bias.grad.item():.4f}")
    print(f"\n  Yorum: w.grad bize 'her agirligi hangi yone ne kadar")
    print(f"  degistirmemiz gerektigini' soyluyor.")
    print(f"  Negatif gradient = agirligi ARTIR (loss'u dusurur)")
    print(f"  Pozitif gradient = agirligi AZALT (loss'u dusurur)")

    return weighted_sum.item(), sigmoid_output.item(), loss.item()


# ======================================================================
# 3. NUMPY vs PYTORCH KARSILASTIRMASI
# ======================================================================

def compare_numpy_pytorch():
    """
    Iki kutuphanenin farkliligini gosteren karsilastirma tablosu.
    """
    print("\n" + "=" * 60)
    print("  NumPy vs PyTorch Karsilastirmasi")
    print("=" * 60)

    comparisons = [
        ("Veri tipi",          "np.array",              "torch.Tensor"),
        ("Olusturma",          "np.array([1,2,3])",     "torch.tensor([1,2,3])"),
        ("Carpim",             "np.dot(a, b)",          "torch.dot(a, b)"),
        ("GPU destegi",        "YOK",                   "VAR (.cuda())"),
        ("Gradient",           "ELLE hesapla",          "OTOMATIK (.backward())"),
        ("Backpropagation",    "Yuzlerce satir kod",    "loss.backward() TEK SATIR"),
        ("Hiz (CPU)",          "Hizli",                 "Benzer"),
        ("Hiz (GPU)",          "YOK",                   "10-100x hizli"),
        ("Kullanim alani",     "Genel bilimsel",        "Derin ogrenme"),
    ]

    print(f"\n  {'Ozellik':<22} {'NumPy':<25} {'PyTorch':<25}")
    print(f"  {'-'*22} {'-'*25} {'-'*25}")
    for feature, numpy_val, pytorch_val in comparisons:
        print(f"  {feature:<22} {numpy_val:<25} {pytorch_val:<25}")

    print(f"\n  Sonuc: NumPy = hesap makinesi, PyTorch = ogrenen hesap makinesi")
    print(f"  PyTorch, NumPy'in ustune 'otomatik turev' ve 'GPU' ekler.")


# ======================================================================
# 4. KARPATHY VIDEOSU NOTLARI
# ======================================================================

def karpathy_notes():
    """
    Andrej Karpathy'nin 'building micrograd' videosundan onemli notlar.
    """
    print("\n" + "=" * 60)
    print("  Karpathy Micrograd - Video Notlari")
    print("=" * 60)

    notes = """
    1. DEGER (VALUE) SINIFI:
       - Her sayi bir 'Value' nesnesi
       - Her Value kendi gradient'ini bilir
       - Islemler (toplama, carpma) yeni Value'lar olusturur
       - Bu islemler bir "computational graph" olusturur

    2. COMPUTATIONAL GRAPH (Hesaplama Grafi):
       - Her islem bir dugum (node)
       - Oklar veri akisini gosterir
       - Forward: soldan saga (hesaplama)
       - Backward: sagdan sola (gradient)

    3. CHAIN RULE (Zincir Kurali):
       - df/dx = df/dy * dy/dx
       - "Son sonucun degisimi = ara adimlarin degisimlerinin carpimi"
       - Backpropagation'in TEMELIDIR

    4. TOPOLOGICAL SORT:
       - Graph'taki dugtumleri SIRAYA koyma
       - Backward pass icin dogru sirayla gitmek gerekir
       - Cocuklar ebeveynlerden ONCE hesaplanmali

    5. NORON, KATMAN, MLP:
       - Noron = w*x + b + aktivasyon
       - Katman = birden fazla noron yan yana
       - MLP = birden fazla katman ust uste
       - Karpathy bunlari adim adim insa ediyor
    """
    print(notes)


# ======================================================================
# 5. DEMO
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  [YSA] Yapay Sinir Aglarina Giris")
    print("  Andrej Karpathy - Micrograd Ilhamli")
    print("=" * 60)

    # 1. NumPy ile noron
    np_ws, np_relu, np_sigmoid = numpy_neuron()

    # 2. PyTorch ile ayni noron
    pt_ws, pt_sigmoid, pt_loss = pytorch_neuron()

    # 3. Sonuclari karsilastir
    if pt_ws is not None:
        print("\n" + "-" * 60)
        print("  Sonuc Karsilastirmasi")
        print("-" * 60)
        print(f"  NumPy  agirlikli toplam: {np_ws:.4f}")
        print(f"  PyTorch agirlikli toplam: {pt_ws:.4f}")
        match = abs(np_ws - pt_ws) < 1e-4
        if match:
            print(f"  [OK] Sonuclar ESIT! Ayni hesaplamayi yapiyorlar.")
        else:
            print(f"  [FAIL] Sonuclar farkli!")

    # 4. Karsilastirma tablosu
    compare_numpy_pytorch()

    # 5. Karpathy notlari
    karpathy_notes()

    print("=" * 60)
    print("  [OK] Demo tamamlandi!")
    print("=" * 60)
