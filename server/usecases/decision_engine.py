"""
server/usecases/decision_engine.py

Karar Açıklama Motoru (Decision Explanation Engine)
====================================================
YSA anomali tespiti sonrası kural motoruyla aksiyon seçer,
ardından Qwen LLM ile bu kararın nedenini yapılandırılmış (structured)
JSON formatında alır ve Telegram'a zengin bildirim gönderir.

3 Aşamalı AI Pipeline:
  1. YSA (AnomalyTrainer.predict) → anomali skoru üretir
  2. Kural Motoru → skora göre aksiyon seçer
  3. LLM (Qwen 2.5) → seçilen aksiyonu Pydantic schema ile yapılandırılmış açıklar

Mimari Notu:
  LLM karar VERMIYOR, kararı AÇIKLIYOR.
  Karar kural motorunda (deterministik), açıklama LLM'de (generatif).
  Bu sayede LLM çöktüğünde sistem yine çalışır (fallback).

Structured Output Notu:
  _generate_explanation() artık serbest metin yerine LLMDecisionOutput döndürüyor.
  evaluate() sonuç dict'inde HEM llm_explanation (str, eski uyumluluk) HEM llm_structured
  (dict, yeni) var → dashboard bozulmadan yeni özellik eklendi.
"""

import datetime
from pathlib import Path
from ai.neural_network import AnomalyTrainer
from ai.explainability import FeatureExplainer
from server.infrastructure.llm_adapter import generate_structured
from agent.telegram_notifier import send_telegram_message
from server.usecases.self_healing import log_event, init_db

# ═══════════════════════════════════════════════════════════════
# Proje kök dizini (model dosyasını bulmak için)
# ═══════════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = PROJECT_ROOT / "ai" / "anomaly_model.pth"

# ═══════════════════════════════════════════════════════════════
# Kural Motoru: Skor → Aksiyon Eşleme Tablosu
# ═══════════════════════════════════════════════════════════════
# Bu tablo DETERMINİSTİK — her zaman aynı sonucu verir.
# LLM'e bağımlılık yok, güvenilir.
ACTION_TABLE = [
    # (üst_sınır, aksiyon_kodu, aksiyon_açıklaması_tr)
    (0.3, "MONITOR",      "İzlemeye devam et"),
    (0.5, "ALERT",         "Uyarı bildirimi gönder"),
    (0.7, "SCALE_UP",      "Kaynak kapasitesini artır"),
    (0.9, "RESTART",       "İlgili servisi yeniden başlat"),
    (1.1, "KILL_PROCESS",  "Sızıntı yapan prosesi sonlandır"),  # 1.1 = her zaman yakalanır
]


class DecisionEngine:
    """
    YSA + Kural Motoru + LLM'i birleştiren orkestratör.

    Kullanım:
        engine = DecisionEngine()
        result = engine.evaluate(cpu=92, ram=94, ram_used_gb=7.5, ram_total_gb=8.0, agent_id="srv-01")
    """

    def __init__(self):
        """
        YSA modelini yükler. Model dosyası yoksa uyarı verir.
        """
        self.trainer = AnomalyTrainer(
            input_size=4,
            hidden_sizes=[64, 32, 16],
            learning_rate=0.001
        )
        self._model_loaded = False

        if MODEL_PATH.exists():
            try:
                self.trainer.load_model(filepath=str(MODEL_PATH))
                self._model_loaded = True
            except Exception as e:
                print(f"[DECISION ENGINE] Model yüklenemedi: {e}")
        else:
            print(f"[DECISION ENGINE] Model dosyası bulunamadı: {MODEL_PATH}")

        # FeatureExplainer: Ablation analizi ile feature importance
        # Cache TTL 30 sn — her saniye gelen metrik için YSA tekrar çalışmaz
        self.explainer = FeatureExplainer(
            trainer=self.trainer,
            cache_ttl_seconds=30,
            model_loaded=self._model_loaded,
        )


    # ───────────────────────────────────────────────────────
    # ANA METOD: evaluate()
    # ───────────────────────────────────────────────────────
    def evaluate(
        self,
        cpu: float,
        ram: float,
        ram_used_gb: float,
        ram_total_gb: float,
        agent_id: str = "agent-01",
        disk: float | None = None,
        net: float | None = None,
    ) -> dict:
        """
        Tam AI pipeline'ı çalıştırır:
          1. YSA → anomali skoru (disk/net gerçek ise 4 özellik, dummy ise 2)
          2. Kural Motoru → aksiyon seç
          3. LLM → Pydantic schema ile structured output (Türkçe)
          4. Telegram → bildirim gönder
          5. DB → event_logs'a kaydet

        Args:
            cpu: CPU kullanım yüzdesi
            ram: RAM kullanım yüzdesi
            ram_used_gb: Kullanılan RAM (GB)
            ram_total_gb: Toplam RAM (GB)
            agent_id: Ajan kimliği
            disk: Disk kullanım yüzdesi (None → dummy 10.0 kullanılır)
            net: Ağ trafiği MB/s (None → dummy 10.0 kullanılır)

        Returns:
            dict: Pipeline sonucu.
                  llm_explanation → str (eski uyumluluk, prediction_summary)
                  llm_structured  → dict (yeni, tam LLMDecisionOutput)
        """
        # Gerçek disk/net var mı?
        has_full_features = disk is not None and net is not None
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ─── AŞAMA 1: YSA Anomali Skoru ──────────────────
        anomaly_score = self._get_anomaly_score(cpu, ram, disk=disk, net=net)

        # ─── AŞAMA 2: Kural Motoru → Aksiyon Seç ─────────
        action, action_desc = self._select_action(anomaly_score)

        # ─── AŞAMA 2.5: Feature Importance (XAI) ─────────
        # Hangi özellik bu tahmini ne kadar etkiledi?
        # Cache'li: 30 sn içinde aynı profil için YSA tekrar çalışmaz.
        disk_val = disk if disk is not None else 10.0
        net_val  = net  if net  is not None else 10.0
        feature_impacts = self.explainer.explain_decision(
            cpu=cpu, ram=ram, disk=disk_val, net=net_val
        )
        # LLM prompt'una eklenecek özet metin (çok uzamasın diye max 3 özellik)
        feature_importance_text = self.explainer.format_for_prompt(feature_impacts)

        # ─── AŞAMA 3: LLM Structured Output ──────────────
        # LLMDecisionOutput: risk_level, prediction_summary,
        #                    recommended_action, confidence_score,
        #                    explanation (feature importance ile)
        llm_output = self._generate_explanation(
            cpu=cpu, ram=ram, ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb, agent_id=agent_id,
            anomaly_score=anomaly_score, action=action,
            has_full_features=has_full_features,
            feature_importance_text=feature_importance_text,
        )

        # Feature impacts'i llm_output nesnesine de ekle (API'de erişilebilsin)
        llm_output = llm_output.model_copy(update={
            "feature_impacts": [fi.to_dict() for fi in feature_impacts]
        })

        # Eski alanla uyumluluk: llm_explanation = prediction_summary string'i
        llm_explanation = llm_output.prediction_summary

        # ─── AŞAMA 4: Telegram Bildirimi ─────────────────
        telegram_sent = self._send_notification(
            agent_id=agent_id, cpu=cpu, ram=ram,
            ram_used_gb=ram_used_gb, ram_total_gb=ram_total_gb,
            anomaly_score=anomaly_score, action=action,
            action_desc=action_desc, explanation=llm_explanation
        )

        # ─── AŞAMA 5: Event Log'a Kaydet ─────────────────
        self._log_decision(
            agent_id=agent_id, anomaly_score=anomaly_score,
            action=action, explanation=llm_explanation
        )

        # ─── Sonuç ───────────────────────────────────────
        result = {
            "timestamp": timestamp,
            "agent_id": agent_id,
            "metrics": {
                "cpu_percent": cpu,
                "ram_percent": ram,
                "ram_used_gb": ram_used_gb,
                "ram_total_gb": ram_total_gb,
                "disk_percent": disk,       # None ise dummy kullanıldı
                "net_mbps": net,            # None ise dummy kullanıldı
            },
            "ysa_score": round(anomaly_score, 4),
            "action": action,
            "action_description": action_desc,
            # llm_explanation → eski alan, string (geriye dönük uyumlu)
            "llm_explanation": llm_explanation,
            # llm_structured → yeni alan, tam Pydantic schema dict
            "llm_structured": llm_output.to_dict(),
            "telegram_sent": telegram_sent,
            "model_loaded": self._model_loaded,
            "has_full_features": has_full_features,
        }

        print(f"[DECISION] Skor: {anomaly_score:.4f} -> Aksiyon: {action}")
        return result

    # ───────────────────────────────────────────────────────
    # AŞAMA 1: YSA'dan anomali skoru al
    # ───────────────────────────────────────────────────────
    def _get_anomaly_score(
        self,
        cpu: float,
        ram: float,
        disk: float | None = None,
        net: float | None = None,
    ) -> float:
        """
        Eğitilmiş YSA modeline metrikleri verip anomali skoru alır.
        Model yüklü değilse basit kural tabanlı fallback kullanır.

        disk/net parametresi:
          None   → dummy değer (10.0) kullanılır — eski davranış
          float  → gerçek veri — YSA daha doğru sonuç üretir

        Returns:
            float: 0.0 (normal) ile 1.0 (kritik anomali) arası skor
        """
        if not self._model_loaded:
            # Fallback: Model yoksa basit hesaplama
            return min((cpu / 100 * 0.4) + (ram / 100 * 0.6), 1.0)

        import numpy as np
        # Gerçek disk/net varsa kullan, yoksa dummy değer (10.0)
        disk_val = disk if disk is not None else 10.0
        net_val  = net  if net  is not None else 10.0

        features = np.array([[cpu, ram, disk_val, net_val]], dtype=np.float32)
        scores = self.trainer.predict(features)
        return float(scores[0])

    # ───────────────────────────────────────────────────────
    # AŞAMA 2: Kural motoru — skor → aksiyon
    # ───────────────────────────────────────────────────────
    @staticmethod
    def _select_action(score: float) -> tuple:
        """
        Deterministik kural motoru. Her zaman aynı girdi → aynı çıktı.
        LLM'e bağımlı DEĞİL.

        Returns:
            tuple: (aksiyon_kodu, aksiyon_açıklaması)
        """
        for threshold, action, description in ACTION_TABLE:
            if score < threshold:
                return action, description
        return "KILL_PROCESS", "Sızıntı yapan prosesi sonlandır"

    # ───────────────────────────────────────────────────────
    # AŞAMA 3: LLM açıklama üret
    # ───────────────────────────────────────────────────────
    def _generate_explanation(
        self,
        cpu,
        ram,
        ram_used_gb,
        ram_total_gb,
        agent_id,
        anomaly_score,
        action,
        has_full_features: bool = False,
        feature_importance_text: str = "",
    ) -> "LLMDecisionOutput":
        """
        Qwen LLM'e İngilizce prompt gönderir, Pydantic schema ile doğrulanmış
        LLMDecisionOutput döndürür.

        feature_importance_text:
          FeatureExplainer.format_for_prompt() çıktısı.
          Prompt'a "En etkili faktörler: ..." olarak eklenir.
          LLM bu bağlamla "neden bu tahmin yapıldı" sorusunu yanıtlar.

        Ollama çalışmıyorsa veya JSON parse/validasyon başarısız olursa
        fallback_output(action) döner — sistem DURMAZ.

        Returns:
            LLMDecisionOutput: Structured output (LLM veya fallback)
        """
        from server.domain.llm_schema import LLMDecisionOutput

        # Feature importance bağlamını prompt'a ekle (max 3-5 satır)
        importance_context = (
            f"\n{feature_importance_text}" if feature_importance_text else ""
        )

        prompt = (
            f"System: '{agent_id}'. CPU={cpu}%, RAM={ram}%. "
            f"Anomaly score: {anomaly_score:.2f}. Recommended action: {action}."
            f"{importance_context}\n"
            f"Explain the situation and recommendation in Turkish. "
            f"Include which factor contributed most to this decision."
        )

        # generate_structured: JSON talimatı ekler, markdown soyar,
        # Pydantic doğrular, hata → fallback_output(action) döner
        return generate_structured(
            prompt=prompt,
            action=action,
            max_tokens=350,
            has_full_features=has_full_features,
        )


    # ───────────────────────────────────────────────────────
    # AŞAMA 4: Telegram bildirimi
    # ───────────────────────────────────────────────────────
    @staticmethod
    def _send_notification(agent_id, cpu, ram, ram_used_gb, ram_total_gb,
                           anomaly_score, action, action_desc, explanation) -> bool:
        """
        Formatlı Telegram bildirimi gönderir.
        """
        # Emoji seç
        if anomaly_score >= 0.9:
            emoji, seviye = "🚨", "KRİTİK"
        elif anomaly_score >= 0.7:
            emoji, seviye = "🔴", "YÜKSEK"
        elif anomaly_score >= 0.5:
            emoji, seviye = "🟠", "ORTA"
        elif anomaly_score >= 0.3:
            emoji, seviye = "🟡", "DÜŞÜK"
        else:
            emoji, seviye = "🟢", "NORMAL"

        message = (
            f"{emoji} <b>AI Karar Raporu — {seviye}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Agent:</b> {agent_id}\n"
            f"<b>CPU:</b> %{cpu} | <b>RAM:</b> %{ram} ({ram_used_gb}/{ram_total_gb} GB)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>YSA Skoru:</b> {anomaly_score:.4f}\n"
            f"<b>Aksiyon:</b> {action} — {action_desc}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>{explanation}</i>"
        )

        return send_telegram_message(message)

    # ───────────────────────────────────────────────────────
    # AŞAMA 5: Event log kaydet
    # ───────────────────────────────────────────────────────
    @staticmethod
    def _log_decision(agent_id, anomaly_score, action, explanation):
        """
        Kararı event_logs tablosuna yazar.
        """
        try:
            init_db()
            detail = (
                f"Agent: {agent_id} | "
                f"YSA Skor: {anomaly_score:.4f} | "
                f"Aksiyon: {action} | "
                f"Aciklama: {explanation[:200]}"
            )
            log_event("AI_DECISION", detail)
        except Exception as e:
            print(f"[DECISION LOG HATA] {e}")


# ═══════════════════════════════════════════════════════════════
# DOĞRUDAN ÇALIŞTIRILIRSA TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print(" Decision Engine — YSA + Kural Motoru + LLM Test")
    print("=" * 60)

    engine = DecisionEngine()

    # Test 1: Normal metrikler
    print("\n--- Test 1: Normal Metrikler ---")
    r1 = engine.evaluate(cpu=25, ram=40, ram_used_gb=3.2, ram_total_gb=8.0, agent_id="test-normal")
    print(f"  Skor: {r1['ysa_score']} -> Aksiyon: {r1['action']}")

    # Test 2: Yüksek risk
    print("\n--- Test 2: Yüksek Risk ---")
    r2 = engine.evaluate(cpu=92, ram=95, ram_used_gb=7.6, ram_total_gb=8.0, agent_id="test-critical")
    print(f"  Skor: {r2['ysa_score']} -> Aksiyon: {r2['action']}")

    print("\n" + "=" * 60)
    print(" Telegram'ı kontrol et!")
    print("=" * 60)
