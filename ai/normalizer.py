"""
ai/normalizer.py

Metrik Normalizasyon Modulu
============================
YSA (Yapay Sinir Aglari) 0-1 arasindaki verilerle daha iyi ogrenir.
CPU %0-100, RAM GB 0-16 gibi farkli olcekler modeli yaniltir.
Normalizasyon tum metrikleri ayni dile cevirir.

Min-Max Scaling Formulu:
    normalized = (deger - min) / (max - min)

Ornek:
    CPU = 85, min = 0, max = 100
    normalized = (85 - 0) / (100 - 0) = 0.85

Bu dosya hem saf NumPy implementasyonu hem de
Scikit-Learn MinMaxScaler karsilastirmasi icerir.
"""

import numpy as np

# Scikit-learn yuklu mu kontrol et
try:
    from sklearn.preprocessing import MinMaxScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ======================================================================
# 1. SAF NUMPY IMPLEMENTASYONU
# ======================================================================

class MetricNormalizer:
    """
    Ham metrikleri 0-1 arasina normalize eden on islemci.

    Neden normalize etmeliyiz?
        CPU:     0 - 100   (%)
        RAM:     0 - 100   (%)
        Disk:    0 - 100   (%)
        Network: 0 - 10000 (Mbps)

        Network degeri CPU'dan 100 kat buyuk. Normalize etmezsek
        model Network'e asiri onem verip digerlerini gormezden gelir.

    Kullanim:
        normalizer = MetricNormalizer()
        normalized_data = normalizer.fit_transform(training_data)
        new_normalized = normalizer.transform(new_data)
        original_data = normalizer.inverse_transform(normalized_data)
    """

    def __init__(self):
        # Her metrik icin varsayilan min-max araliklari
        self.feature_ranges = {
            "cpu_percent":  {"min": 0.0, "max": 100.0},
            "ram_percent":  {"min": 0.0, "max": 100.0},
            "disk_percent": {"min": 0.0, "max": 100.0},
            "net_percent":  {"min": 0.0, "max": 100.0},
        }
        self.is_fitted = False  # Gercek veriden aralik ogrenildi mi?

    def fit(self, data):
        """
        Egitim verisinden her ozelligin gercek min-max araliklarini ogrenir.

        :param data: numpy array, boyut: (ornek_sayisi, 4)

        Ornek:
            data = [[85, 72, 45, 30],
                    [20, 30, 10, 15],
                    [95, 88, 60, 70]]

            Ogrenilen min/max:
                CPU:  min=20, max=95
                RAM:  min=30, max=88
                Disk: min=10, max=60
                Net:  min=15, max=70
        """
        feature_names = list(self.feature_ranges.keys())
        for i, name in enumerate(feature_names):
            self.feature_ranges[name]["min"] = float(np.min(data[:, i]))
            self.feature_ranges[name]["max"] = float(np.max(data[:, i]))
        self.is_fitted = True
        return self

    def transform(self, data):
        """
        Veriyi ogrenilen araliklara gore 0-1 arasina normalize eder.

        Formul: normalized = (deger - min) / (max - min)

        :param data: numpy array, boyut: (ornek_sayisi, 4)
        :return: numpy array, normalize edilmis veri (0-1 arasi)

        Ornek:
            CPU = 85, min = 20, max = 95
            normalized = (85 - 20) / (95 - 20) = 65 / 75 = 0.8667
        """
        if not self.is_fitted:
            raise ValueError("Normalizer henuz fit() edilmedi! Once fit() veya fit_transform() cagirilmali.")

        normalized = np.zeros_like(data, dtype=np.float32)
        feature_names = list(self.feature_ranges.keys())

        for i, name in enumerate(feature_names):
            min_val = self.feature_ranges[name]["min"]
            max_val = self.feature_ranges[name]["max"]
            range_val = max_val - min_val

            if range_val == 0:
                # Tum degerler ayniysa (orn: hep 50%), 0 dondur
                normalized[:, i] = 0.0
            else:
                normalized[:, i] = (data[:, i] - min_val) / range_val

        return normalized

    def fit_transform(self, data):
        """
        fit() ve transform()'u tek adimda yapar.
        Egitim verisi icin kullanilir.

        :param data: numpy array
        :return: numpy array, normalize edilmis veri
        """
        self.fit(data)
        return self.transform(data)

    def inverse_transform(self, normalized_data):
        """
        Normalize edilmis veriyi orijinal olcegine geri donusturur.

        Formul: original = normalized * (max - min) + min

        :param normalized_data: numpy array, 0-1 arasi degerler
        :return: numpy array, orijinal olcekteki degerler

        Neden gerekli?
            Model 0-1 arasi calisir ama kullaniciya "CPU: 0.85" degil
            "CPU: %85" gostermek isteriz.

        Ornek:
            normalized = 0.8667, min = 20, max = 95
            original = 0.8667 * (95 - 20) + 20 = 0.8667 * 75 + 20 = 85.0
        """
        if not self.is_fitted:
            raise ValueError("Normalizer henuz fit() edilmedi!")

        original = np.zeros_like(normalized_data, dtype=np.float32)
        feature_names = list(self.feature_ranges.keys())

        for i, name in enumerate(feature_names):
            min_val = self.feature_ranges[name]["min"]
            max_val = self.feature_ranges[name]["max"]
            range_val = max_val - min_val

            original[:, i] = normalized_data[:, i] * range_val + min_val

        return original

    def get_ranges(self):
        """Ogrenilen min-max araliklarini dondurur (debug icin)."""
        return self.feature_ranges


# ======================================================================
# 2. SCIKIT-LEARN KARSILASTIRMASI
# ======================================================================

def compare_with_sklearn(data):
    """
    Bizim MetricNormalizer'imiz ile Scikit-Learn'un MinMaxScaler'ini
    karsilastirir. Sonuclarin AYNI oldugunu dogrular.

    :param data: numpy array, ham metrik verileri
    """
    print("=" * 60)
    print("  NumPy vs Scikit-Learn Karsilastirmasi")
    print("=" * 60)

    # --- Bizim implementasyonumuz ---
    our_normalizer = MetricNormalizer()
    our_result = our_normalizer.fit_transform(data)

    print("\n[NUMPY] Bizim MetricNormalizer:")
    print(f"  Ilk 3 satir:\n{our_result[:3]}")

    # --- Scikit-Learn ---
    if SKLEARN_AVAILABLE:
        sklearn_scaler = MinMaxScaler()
        # MinMaxScaler: Scikit-Learn'un hazir normalizasyon sinifi
        # Ayni formulu kullaniyor: (X - X.min) / (X.max - X.min)
        sklearn_result = sklearn_scaler.fit_transform(data)

        print(f"\n[SKLEARN] MinMaxScaler:")
        print(f"  Ilk 3 satir:\n{sklearn_result[:3].astype(np.float32)}")

        # Sonuclar ayni mi?
        # allclose: Iki array'in TUM elemanlarinin birbirine yakin olup olmadigini kontrol eder
        # atol=1e-6: 0.000001'e kadar fark kabul edilir (kayan nokta hassasiyeti)
        is_equal = np.allclose(our_result, sklearn_result.astype(np.float32), atol=1e-6)
        if is_equal:
            print(f"\n  [OK] Sonuclar ESIT! Bizim implementasyonumuz dogru.")
        else:
            print(f"\n  [FAIL] Sonuclar FARKLI! Kontrol edilmeli.")
    else:
        print("\n  [UYARI] scikit-learn yuklu degil. Karsilastirma yapilamiyor.")
        print("  Yuklemek icin: pip install scikit-learn")

    # --- Inverse Transform testi ---
    print("\n" + "-" * 60)
    print("  Inverse Transform (Geri Donusum) Testi")
    print("-" * 60)

    geri_donusmus = our_normalizer.inverse_transform(our_result)

    # Orijinal veri ile geri donusturulmus veri ayni mi?
    is_inverse_correct = np.allclose(data.astype(np.float32), geri_donusmus, atol=1e-4)

    print(f"\n  Orijinal ilk satir:      {data[0]}")
    print(f"  Normalize edilmis:       {our_result[0]}")
    print(f"  Geri donusturulmus:      {geri_donusmus[0]}")

    if is_inverse_correct:
        print(f"\n  [OK] Geri donusum DOGRU! Orijinal veriye geri donebildik.")
    else:
        print(f"\n  [FAIL] Geri donusum HATALI!")


# ======================================================================
# 3. DEMO
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  [NORM] Metrik Normalizasyon Demo")
    print("=" * 60)

    # Ornek metrik verileri olustur
    np.random.seed(42)

    # Farkli olceklerde veriler:
    # CPU: 0-100, RAM: 0-100, Disk: 0-100, Network: 0-10000
    sample_data = np.array([
        [85.0,  72.0,  45.0,  3500.0],   # Yuksek CPU, normal RAM, dusuk Disk, orta Net
        [20.0,  30.0,  10.0,   500.0],   # Dusuk her sey
        [95.0,  88.0,  60.0,  8000.0],   # Yuksek her sey
        [45.0,  50.0,  35.0,  2000.0],   # Orta her sey
        [10.0,  25.0,   5.0,   100.0],   # Minimum civari
    ], dtype=np.float32)

    print("\n[HAM VERI] Normalize edilmemis (farkli olcekler):")
    print(f"  {'CPU':>8} {'RAM':>8} {'Disk':>8} {'Network':>8}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for row in sample_data:
        print(f"  {row[0]:8.1f} {row[1]:8.1f} {row[2]:8.1f} {row[3]:8.1f}")

    print(f"\n  Problem: Network (100-8000) degerler CPU'dan (10-95) cok buyuk!")
    print(f"  Model Network'e asiri onem verip digerlerini gormezden gelir.")

    # Normalize et
    normalizer = MetricNormalizer()
    normalized = normalizer.fit_transform(sample_data)

    print(f"\n[NORMALIZE] Min-Max Scaling sonrasi (0-1 arasi):")
    print(f"  {'CPU':>8} {'RAM':>8} {'Disk':>8} {'Network':>8}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for row in normalized:
        print(f"  {row[0]:8.4f} {row[1]:8.4f} {row[2]:8.4f} {row[3]:8.4f}")

    print(f"\n  Simdi tum degerler 0-1 arasi! Model hepsine ESIT onem verir.")

    # Geri donusum
    original_back = normalizer.inverse_transform(normalized)

    print(f"\n[GERI DONUSUM] inverse_transform sonrasi:")
    print(f"  {'CPU':>8} {'RAM':>8} {'Disk':>8} {'Network':>8}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for row in original_back:
        print(f"  {row[0]:8.1f} {row[1]:8.1f} {row[2]:8.1f} {row[3]:8.1f}")

    # Sklearn karsilastirmasi
    print()
    compare_with_sklearn(sample_data)

    print("\n" + "=" * 60)
    print("  [OK] Demo tamamlandi!")
    print("=" * 60)
