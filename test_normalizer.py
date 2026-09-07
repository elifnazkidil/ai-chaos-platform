"""
test_normalizer.py

Normalizasyon Testleri
========================
MetricNormalizer sinifinin dogru calistigini dogrulayan testler:
1. Min-Max Scaling dogruluk testi
2. Inverse transform geri donusum testi
3. Gercek metrik verileriyle entegrasyon testi
"""

import numpy as np
import sys
import os

# Proje kokunu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.normalizer import MetricNormalizer


# ======================================================================
# TEST 1: Min-Max Scaling Dogruluk Testi
# ======================================================================

def test_min_max_scaling():
    """
    Normalize edilen degerlerin 0-1 arasinda oldugunu dogrular.
    """
    print("\n[TEST 1] Min-Max Scaling Dogruluk Testi")
    print("-" * 40)

    data = np.array([
        [10.0, 20.0,  5.0,  100.0],
        [50.0, 60.0, 30.0, 5000.0],
        [90.0, 95.0, 80.0, 9000.0],
    ], dtype=np.float32)

    normalizer = MetricNormalizer()
    normalized = normalizer.fit_transform(data)

    # Tum degerler 0-1 arasinda olmali
    all_in_range = np.all(normalized >= 0.0) and np.all(normalized <= 1.0)

    # Min degerler 0, max degerler 1 olmali
    min_is_zero = np.allclose(np.min(normalized, axis=0), 0.0)
    max_is_one = np.allclose(np.max(normalized, axis=0), 1.0)

    if all_in_range and min_is_zero and max_is_one:
        print("  [PASSED] Tum degerler 0-1 arasinda")
        print("  [PASSED] Min degerler = 0")
        print("  [PASSED] Max degerler = 1")
        return True
    else:
        print(f"  [FAILED] Degerler: min={np.min(normalized)}, max={np.max(normalized)}")
        return False


# ======================================================================
# TEST 2: Inverse Transform Geri Donusum Testi
# ======================================================================

def test_inverse_transform():
    """
    Normalize edilen verinin geri donusturuldugunde
    orijinal veriye esit oldugunu dogrular.
    """
    print("\n[TEST 2] Inverse Transform Geri Donusum Testi")
    print("-" * 40)

    data = np.array([
        [85.0,  72.0,  45.0, 3500.0],
        [20.0,  30.0,  10.0,  500.0],
        [95.0,  88.0,  60.0, 8000.0],
    ], dtype=np.float32)

    normalizer = MetricNormalizer()
    normalized = normalizer.fit_transform(data)
    restored = normalizer.inverse_transform(normalized)

    # Orijinal ve geri donusturulmus veri ayni olmali
    is_equal = np.allclose(data, restored, atol=1e-4)

    if is_equal:
        print("  [PASSED] Geri donusum orijinal veriye esit")
        print(f"  Orjinal:  {data[0]}")
        print(f"  Restored: {restored[0]}")
        return True
    else:
        print(f"  [FAILED] Fark var!")
        print(f"  Orjinal:  {data[0]}")
        print(f"  Restored: {restored[0]}")
        return False


# ======================================================================
# TEST 3: Gercek Metrik Verileriyle Entegrasyon Testi
# ======================================================================

def test_real_metrics_integration():
    """
    Gercek dunya metrik degerlerini simule ederek
    normalizer'in dogru calistigini dogrular.
    """
    print("\n[TEST 3] Gercek Metrik Entegrasyon Testi")
    print("-" * 40)

    # Gercek dunya benzeri metrikler
    training_data = np.array([
        [25.0, 40.0, 15.0, 20.0],   # Normal
        [30.0, 45.0, 20.0, 25.0],   # Normal
        [85.0, 92.0, 70.0, 80.0],   # Anomali
        [90.0, 95.0, 75.0, 85.0],   # Anomali
        [40.0, 50.0, 30.0, 35.0],   # Normal
    ], dtype=np.float32)

    normalizer = MetricNormalizer()
    normalized_train = normalizer.fit_transform(training_data)

    # Yeni veri (daha once gorulmemis)
    new_data = np.array([
        [50.0, 60.0, 40.0, 45.0],   # Orta - daha once gorulmemis
    ], dtype=np.float32)

    normalized_new = normalizer.transform(new_data)

    # Yeni veri de 0-1 arasinda olmali (ama min-max disinda olabilir)
    all_valid = normalized_new is not None and normalized_new.shape == (1, 4)

    # Orta degerler yaklasik 0.3-0.5 arasinda olmali
    reasonable = np.all(normalized_new > 0.1) and np.all(normalized_new < 0.9)

    if all_valid and reasonable:
        print("  [PASSED] Yeni veri basariyla normalize edildi")
        print(f"  Ham:        {new_data[0]}")
        print(f"  Normalize:  {normalized_new[0]}")
        return True
    else:
        print(f"  [FAILED] Normalize sonucu beklenmedik!")
        return False


# ======================================================================
# TEST 4: Fit Edilmeden Transform Hatasi
# ======================================================================

def test_transform_without_fit():
    """
    fit() cagirilmadan transform() cagrildiginda
    hata firlatildigini dogrular.
    """
    print("\n[TEST 4] Fit Edilmeden Transform Hatasi Testi")
    print("-" * 40)

    normalizer = MetricNormalizer()
    data = np.array([[50.0, 60.0, 40.0, 45.0]], dtype=np.float32)

    try:
        normalizer.transform(data)
        print("  [FAILED] Hata firlatilmadi!")
        return False
    except ValueError as e:
        print(f"  [PASSED] Beklenen hata yakalandi: {e}")
        return True


# ======================================================================
# TEST 5: Scikit-Learn Karsilastirmasi
# ======================================================================

def test_sklearn_comparison():
    """
    Bizim implementasyonumuzun Scikit-Learn ile ayni
    sonuclari verdigini dogrular.
    """
    print("\n[TEST 5] Scikit-Learn Karsilastirmasi")
    print("-" * 40)

    try:
        from sklearn.preprocessing import MinMaxScaler
    except ImportError:
        print("  [SKIP] scikit-learn yuklu degil, test atlaniyor")
        return True  # Atlanan test basarisiz sayilmaz

    data = np.array([
        [10.0, 20.0,  5.0,  100.0],
        [50.0, 60.0, 30.0, 5000.0],
        [90.0, 95.0, 80.0, 9000.0],
    ], dtype=np.float32)

    # Bizim normalizer
    our_normalizer = MetricNormalizer()
    our_result = our_normalizer.fit_transform(data)

    # Scikit-Learn
    sklearn_scaler = MinMaxScaler()
    sklearn_result = sklearn_scaler.fit_transform(data).astype(np.float32)

    is_equal = np.allclose(our_result, sklearn_result, atol=1e-6)

    if is_equal:
        print("  [PASSED] NumPy ve Scikit-Learn sonuclari ESIT")
        return True
    else:
        print("  [FAILED] Sonuclar farkli!")
        print(f"  Bizim:   {our_result[0]}")
        print(f"  Sklearn: {sklearn_result[0]}")
        return False


# ======================================================================
# ANA TEST CALISTIRICISI
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  [TEST] Normalizasyon Test Suite")
    print("=" * 60)

    tests = [
        ("Min-Max Scaling Dogruluk", test_min_max_scaling),
        ("Inverse Transform Geri Donusum", test_inverse_transform),
        ("Gercek Metrik Entegrasyon", test_real_metrics_integration),
        ("Fit Edilmeden Transform Hatasi", test_transform_without_fit),
        ("Scikit-Learn Karsilastirmasi", test_sklearn_comparison),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            results.append((name, False))

    # Ozet
    print("\n" + "=" * 60)
    print("  TEST SONUCLARI")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "[PASSED]" if result else "[FAILED]"
        print(f"  {status} {name}")

    print(f"\n  Sonuc: {passed}/{total} test BASARILI")

    if passed == total:
        print("  Tum testler GECTI!")
    else:
        print("  Bazi testler BASARISIZ!")

    print("=" * 60)
