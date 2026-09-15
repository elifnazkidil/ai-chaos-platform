"""
ai/explainability.py

Yapay Zeka Açıklanabilirlik Motoru (Feature Importance / XAI)
=============================================================
Clean Architecture — AI Katmanı

Bu modül, anomali tahminini etkileyen metriklerin göreli önemini hesaplar
ve bu bilgiyi LLM prompt'una bağlam olarak ekler.

Yöntem: Ablation (Bozma) Analizi
  Temel fikir:
    1. Tüm özellikler mevcutken anomali skorunu al (base_score).
    2. Her özelliği sırayla "normal" seviyeye çek (ablate).
    3. Skordaki düşüş = o özelliğin önemi.
    Skor çok düşüyorsa → o özellik kritik.
    Skor hiç düşmüyorsa → o özellik önemsiz.

Neden SHAP değil bu?
  - SHAP kütüphane bağımlılığı gerektirir (ek kurulum).
  - polyfit / MLP modelimiz için ablation analizi matematiksel olarak
    eşdeğer ve çok daha hafif.
  - "Overcomplicate etme" kuralına uyar.

Performans:
  - FeatureExplainer, TTL (saniye cinsinden yaşam süresi) ile sonuçları
    önbelleğe alır.
  - Aynı girdi profili (yüksek/düşük) için LLM her çağrıda YSA'yı
    tekrar çalıştırmaz → gecikme düşer.

Öğrenilen Kavramlar:
  - dataclass           : Sonuç nesnesi (FeatureImpact)
  - functools.lru_cache : Hafıza tabanlı önbellekleme
  - time.monotonic()    : Süre ölçümü için güvenilir saat
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import numpy as np


# ══════════════════════════════════════════════════════════════
# VERİ YAPISI: FeatureImpact
# ══════════════════════════════════════════════════════════════

@dataclass
class FeatureImpact:
    """
    Tek bir özelliğin anomali skoruna katkısını temsil eder.

    Kullanım:
        fi = FeatureImpact(feature="RAM", impact=0.87, direction="artış")
        print(fi)  # RAM → etki: 0.87 (artış)
    """
    feature: str      # Özellik adı ("CPU", "RAM", "Disk", "Net")
    impact: float     # Normalize edilmiş etki skoru 0.0-1.0
    direction: str    # "artış" | "azalış" | "nötr"

    def __repr__(self) -> str:
        return f"{self.feature} -> etki: {self.impact:.2f} ({self.direction})"

    def to_dict(self) -> dict:
        return {"feature": self.feature, "impact": round(self.impact, 4), "direction": self.direction}


# ══════════════════════════════════════════════════════════════
# ANA SINIF: FeatureExplainer
# ══════════════════════════════════════════════════════════════

class FeatureExplainer:
    """
    YSA modeline ablation analizi uygulayarak feature importance hesaplar
    ve sonuçları LLM için metin özetine dönüştürür.

    Kullanım:
        explainer = FeatureExplainer(trainer, cache_ttl_seconds=30)
        impacts = explainer.explain_decision(cpu=88, ram=91, disk=45, net=2.1)
        prompt_text = explainer.format_for_prompt(impacts)
    """

    # Ablation için "normal" referans değerleri.
    # Bir özelliği ablate ederken bu değerlere çekeriz.
    # (Gerçek idle sistem metrikleri baz alındı)
    _NORMAL_VALUES = {
        "CPU":  20.0,
        "RAM":  40.0,
        "Disk": 20.0,
        "Net":  0.5,
    }

    # İnsan tarafından okunabilir yön etiketleri
    _DIRECTION_LABELS = {
        "CPU":  "yüksek CPU kullanımı",
        "RAM":  "yüksek RAM tüketimi",
        "Disk": "yoğun disk aktivitesi",
        "Net":  "yoğun ağ trafiği",
    }

    def __init__(
        self,
        trainer,
        cache_ttl_seconds: int = 30,
        model_loaded: bool = False,
    ):
        """
        :param trainer: AnomalyTrainer nesnesi (load_model() çağrılmış olmalı)
        :param cache_ttl_seconds: Önbelleğ geçerlilik süresi (saniye).
               Bu süre içinde aynı profil için hesaplama tekrarlanmaz.
        :param model_loaded: AnomalyTrainer modeli yüklendi mi?
               True ise ablation analizi yapılır, False ise sezgisel mod.
        """
        self._trainer = trainer
        self._cache_ttl = cache_ttl_seconds
        self._model_loaded = model_loaded

        # Önbelleğk: (cpu_bin, ram_bin, disk_bin, net_bin) → (timestamp, List[FeatureImpact])
        # Değerleri 10'arlık gruplara (bin) ayırarak benzer metrik setlerini
        # aynı önbelleğk girişine eşliyoruz.
        # Ör: cpu=87 ve cpu=89 → aynı bin (80) → aynı önbelleğk.
        self._cache: dict = {}

    # ─── Ana Metod: explain_decision() ─────────────────────

    def explain_decision(
        self,
        cpu: float,
        ram: float,
        disk: float = 10.0,
        net: float = 10.0,
    ) -> List[FeatureImpact]:
        """
        Verilen metrik seti için feature importance hesaplar.

        Cache mantığı:
          Metrikler 10'luk gruplara (bin) yuvarlanır.
          Aynı grupta TTL süresi dolmamışsa → önbellek döner.
          Böylece her saniye gelen metrik için YSA tekrar çalışmaz.

        :param cpu:  CPU kullanım yüzdesi
        :param ram:  RAM kullanım yüzdesi
        :param disk: Disk kullanım yüzdesi (varsayılan: 10.0)
        :param net:  Ağ trafiği MB/s (varsayılan: 10.0)
        :return: FeatureImpact listesi (etkiye göre azalan sırada)
        """
        # Önbellek anahtarı — 10'arlık gruplara yuvarlayarak hassas eşleşme gereksiniminini kaldır
        cache_key = (
            int(cpu  // 10) * 10,
            int(ram  // 10) * 10,
            int(disk // 10) * 10,
            int(net  // 10) * 10,
        )

        # Önbellekte taze sonuç var mı?
        if cache_key in self._cache:
            cached_time, cached_result = self._cache[cache_key]
            if time.monotonic() - cached_time < self._cache_ttl:
                return cached_result  # ← Önbellekten döner, YSA çalışmaz

        # Taze değil veya hiç yok → hesapla
        result = self._compute_importance(cpu, ram, disk, net)

        # Önbelleğe kaydet
        self._cache[cache_key] = (time.monotonic(), result)
        return result

    # ─── LLM Prompt Metni ───────────────────────────────────

    def format_for_prompt(
        self,
        impacts: List[FeatureImpact],
        max_features: int = 3,
    ) -> str:
        """
        FeatureImpact listesini LLM prompt'una eklenecek kısa metne çevirir.

        max_features=3 → en önemli 3 özellik gösterilir.
        Prompt çok uzamasın diye sınır var.

        Örnek çıktı:
          "En etkili faktörler:
           1. RAM: yüksek RAM tüketimi (etki: 0.87)
           2. CPU: yüksek CPU kullanımı (etki: 0.45)
           3. Disk: yoğun disk aktivitesi (etki: 0.12)"

        :param impacts: explain_decision() çıktısı
        :param max_features: Gösterilecek maksimum özellik sayısı
        :return: Prompt'a eklenecek string
        """
        if not impacts:
            return ""

        lines = ["En etkili faktörler:"]
        for i, fi in enumerate(impacts[:max_features], start=1):
            label = self._DIRECTION_LABELS.get(fi.feature, fi.feature)
            lines.append(f"  {i}. {fi.feature}: {label} (etki: {fi.impact:.2f})")

        return "\n".join(lines)

    # ─── Private: Ablation Hesabı ────────────────────────────

    def _compute_importance(
        self,
        cpu: float,
        ram: float,
        disk: float,
        net: float,
    ) -> List[FeatureImpact]:
        """
        Ablation analizi ile feature importance hesaplar.

        Adımlar:
          1. Tüm özelliklerle base_score al.
          2. Her özelliği NORMAL_VALUE'ya çekerek ablated_score al.
          3. drop = max(0, base_score - ablated_score)
          4. Tüm drop değerlerini normalize et (toplam = 1.0).
          5. FeatureImpact listesi döndür (azalan sırada).

        Model yüklü değilse → varsayılan ağırlıklar döner (sistem çalışmaya devam eder).

        :return: Normalize edilmiş FeatureImpact listesi
        """
        # Model yüklü değilse hızlı fallback
        if not self._model_loaded:
            return self._heuristic_importance(cpu, ram, disk, net)

        base_sample = np.array([[cpu, ram, disk, net]], dtype=np.float32)
        try:
            base_score = float(self._trainer.predict(base_sample)[0])
        except Exception:
            return self._heuristic_importance(cpu, ram, disk, net)

        feature_names = ["CPU", "RAM", "Disk", "Net"]
        normal_vals   = [
            self._NORMAL_VALUES["CPU"],
            self._NORMAL_VALUES["RAM"],
            self._NORMAL_VALUES["Disk"],
            self._NORMAL_VALUES["Net"],
        ]
        current_vals  = [cpu, ram, disk, net]

        drops = []
        for i in range(len(feature_names)):
            ablated = base_sample.copy()
            ablated[0, i] = normal_vals[i]  # Bu özelliği "normal" seviyeye çek
            try:
                ablated_score = float(self._trainer.predict(ablated)[0])
            except Exception:
                ablated_score = base_score
            drop = max(0.0, base_score - ablated_score)
            drops.append(drop)

        return self._build_impacts(feature_names, current_vals, normal_vals, drops)

    def _heuristic_importance(
        self,
        cpu: float,
        ram: float,
        disk: float,
        net: float,
    ) -> List[FeatureImpact]:
        """
        Model yüklü değilken kullanılan sezgisel (heuristic) önem tahmini.
        Normal değerden sapma miktarına göre sıralama yapar.
        """
        feature_names = ["CPU", "RAM", "Disk", "Net"]
        current_vals  = [cpu, ram, disk, net]
        normal_vals   = [
            self._NORMAL_VALUES["CPU"],
            self._NORMAL_VALUES["RAM"],
            self._NORMAL_VALUES["Disk"],
            self._NORMAL_VALUES["Net"],
        ]
        # Sapma = (mevcut - normal) / 100
        drops = [max(0.0, (c - n) / 100.0) for c, n in zip(current_vals, normal_vals)]
        return self._build_impacts(feature_names, current_vals, normal_vals, drops)

    @staticmethod
    def _build_impacts(
        feature_names: List[str],
        current_vals: List[float],
        normal_vals: List[float],
        drops: List[float],
    ) -> List[FeatureImpact]:
        """
        Ham drop değerlerini normalize ederek FeatureImpact listesi üretir.
        """
        total = sum(drops)
        impacts = []
        for name, cur, norm, drop in zip(feature_names, current_vals, normal_vals, drops):
            normalized = round(drop / total, 4) if total > 0 else 0.0
            direction = "artış" if cur > norm else ("azalış" if cur < norm else "nötr")
            impacts.append(FeatureImpact(
                feature=name,
                impact=normalized,
                direction=direction,
            ))

        # Azalan etki sırasına göre sırala
        impacts.sort(key=lambda x: x.impact, reverse=True)
        return impacts


# ══════════════════════════════════════════════════════════════
# Doğrudan çalıştırılırsa — hızlı test
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from pathlib import Path
    import sys

    # Proje kökünü sys.path'e ekle
    _root = str(Path(__file__).resolve().parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from ai.neural_network import AnomalyTrainer

    print("=" * 55)
    print(" FeatureExplainer — Hızlı Test")
    print("=" * 55)

    trainer = AnomalyTrainer(input_size=4, hidden_sizes=[64, 32, 16])
    model_path = Path(__file__).parent / "anomaly_model.pth"
    if model_path.exists():
        trainer.load_model(str(model_path))
        print(f"Model yüklendi: {model_path}")
    else:
        print("[UYARI] Model bulunamadı, sezgisel mod kullanılacak.")

    explainer = FeatureExplainer(trainer, cache_ttl_seconds=30)

    test_cases = [
        {"cpu": 25.0, "ram": 40.0, "disk": 15.0, "net": 0.5, "label": "Normal Durum"},
        {"cpu": 88.0, "ram": 91.0, "disk": 45.0, "net": 2.1, "label": "Kritik Durum"},
        {"cpu": 30.0, "ram": 87.0, "disk": 20.0, "net": 0.3, "label": "Bellek Sızıntısı"},
    ]

    for case in test_cases:
        label = case.pop("label")
        print(f"\n--- {label} ---")
        impacts = explainer.explain_decision(**case)
        for fi in impacts:
            bar = "█" * int(fi.impact * 20)
            print(f"  {fi.feature:6} {bar:<20} {fi.impact:.3f}  ({fi.direction})")
        print(f"\n  Prompt özeti:\n  {explainer.format_for_prompt(impacts)}")
