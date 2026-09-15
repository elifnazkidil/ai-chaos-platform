"""
test_llm_schema.py

LLM Structured Output şeması için birim testler.
================================================
Test edilen bileşenler:
  1. LLMDecisionOutput — Pydantic validasyon
  2. fallback_output()  — Her aksiyon için deterministik çıktı
  3. _strip_markdown_json() — Markdown temizleme

Çalıştırma:
    .venv\\Scripts\\pytest.exe test_llm_schema.py -v
"""

import json
import pytest

# ── Pydantic Schema Testleri ─────────────────────────────────
from server.domain.llm_schema import LLMDecisionOutput, fallback_output


class TestLLMDecisionOutput:
    """LLMDecisionOutput Pydantic modelinin validasyon testleri."""

    # ─── Geçerli Girdiler ───────────────────────────────────

    def test_valid_output_all_fields(self):
        """Tüm alanlar doğru → nesne başarıyla oluşur."""
        output = LLMDecisionOutput(
            risk_level="high",
            prediction_summary="CPU kritik seviyede.",
            recommended_action="Servisi yeniden başlat.",
            confidence_score=0.87,
        )
        assert output.risk_level == "high"
        assert output.confidence_score == 0.87
        assert output.prediction_summary == "CPU kritik seviyede."

    def test_all_risk_levels_accepted(self):
        """Dört geçerli risk_level değerinin hepsi kabul edilmeli."""
        for level in ("low", "medium", "high", "critical"):
            output = LLMDecisionOutput(
                risk_level=level,
                prediction_summary="Test.",
                recommended_action="Test aksiyon.",
                confidence_score=0.5,
            )
            assert output.risk_level == level

    def test_confidence_score_rounded_to_4_decimals(self):
        """confidence_score 4 basamağa yuvarlanmalı."""
        output = LLMDecisionOutput(
            risk_level="low",
            prediction_summary="Normal.",
            recommended_action="İzle.",
            confidence_score=0.123456789,
        )
        assert output.confidence_score == 0.1235

    def test_to_dict_returns_all_fields(self):
        """to_dict() tüm alanları içermeli."""
        output = LLMDecisionOutput(
            risk_level="medium",
            prediction_summary="Hafif anomali.",
            recommended_action="Bildir.",
            confidence_score=0.6,
        )
        d = output.to_dict()
        assert "risk_level" in d
        assert "prediction_summary" in d
        assert "recommended_action" in d
        assert "confidence_score" in d

    def test_leading_trailing_whitespace_stripped(self):
        """Baştaki/sondaki boşluklar temizlenmeli."""
        output = LLMDecisionOutput(
            risk_level="low",
            prediction_summary="  Durum normal.  ",
            recommended_action="  İzle.  ",
            confidence_score=0.5,
        )
        assert output.prediction_summary == "Durum normal."
        assert output.recommended_action == "İzle."

    # ─── Geçersiz Girdiler ─────────────────────────────────

    def test_invalid_risk_level_raises_error(self):
        """Tanımsız risk_level → ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMDecisionOutput(
                risk_level="extreme",  # Geçersiz! Sadece low/medium/high/critical
                prediction_summary="Test.",
                recommended_action="Test.",
                confidence_score=0.5,
            )

    def test_confidence_score_above_1_raises_error(self):
        """confidence_score > 1.0 → ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMDecisionOutput(
                risk_level="high",
                prediction_summary="Test.",
                recommended_action="Test.",
                confidence_score=1.5,  # Geçersiz!
            )

    def test_confidence_score_below_0_raises_error(self):
        """confidence_score < 0.0 → ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMDecisionOutput(
                risk_level="low",
                prediction_summary="Test.",
                recommended_action="Test.",
                confidence_score=-0.1,  # Geçersiz!
            )

    def test_empty_prediction_summary_raises_error(self):
        """Boş prediction_summary → ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMDecisionOutput(
                risk_level="low",
                prediction_summary="",  # Boş!
                recommended_action="Test.",
                confidence_score=0.5,
            )

    def test_whitespace_only_summary_raises_error(self):
        """Sadece boşluk içeren summary → ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMDecisionOutput(
                risk_level="low",
                prediction_summary="   ",  # Sadece boşluk!
                recommended_action="Test.",
                confidence_score=0.5,
            )

    def test_confidence_score_boundary_0_accepted(self):
        """confidence_score = 0.0 → geçerli (sınır değeri)."""
        output = LLMDecisionOutput(
            risk_level="low",
            prediction_summary="Test.",
            recommended_action="Test.",
            confidence_score=0.0,
        )
        assert output.confidence_score == 0.0

    def test_confidence_score_boundary_1_accepted(self):
        """confidence_score = 1.0 → geçerli (sınır değeri)."""
        output = LLMDecisionOutput(
            risk_level="critical",
            prediction_summary="Kritik!",
            recommended_action="Sonlandır.",
            confidence_score=1.0,
        )
        assert output.confidence_score == 1.0


# ── Fallback Testleri ─────────────────────────────────────────

class TestFallbackOutput:
    """fallback_output() fonksiyonunun deterministik çıktı testleri."""

    def test_all_known_actions_have_fallback(self):
        """Bilinen tüm aksiyonlar için fallback üretilmeli."""
        for action in ("MONITOR", "ALERT", "SCALE_UP", "RESTART", "KILL_PROCESS"):
            output = fallback_output(action)
            assert isinstance(output, LLMDecisionOutput), \
                f"fallback_output({action!r}) LLMDecisionOutput döndürmeli"

    def test_unknown_action_returns_monitor_fallback(self):
        """Tanımsız aksiyon → MONITOR fallback'i döner (güvenli varsayılan)."""
        output = fallback_output("UNKNOWN_ACTION")
        assert output.risk_level == "low"

    def test_kill_process_is_critical(self):
        """KILL_PROCESS → risk_level='critical' olmalı."""
        output = fallback_output("KILL_PROCESS")
        assert output.risk_level == "critical"

    def test_monitor_is_low_risk(self):
        """MONITOR → risk_level='low' olmalı."""
        output = fallback_output("MONITOR")
        assert output.risk_level == "low"

    def test_fallback_is_valid_pydantic_model(self):
        """Tüm fallback çıktıları geçerli Pydantic model olmalı (validasyon geçmeli)."""
        for action in ("MONITOR", "ALERT", "SCALE_UP", "RESTART", "KILL_PROCESS"):
            output = fallback_output(action)
            # to_dict() → JSON serialize edilebilmeli
            d = output.to_dict()
            assert 0.0 <= d["confidence_score"] <= 1.0

    def test_fallback_confidence_scores_increase_with_severity(self):
        """Daha şiddetli aksiyonların fallback confidence skoru daha yüksek olmalı."""
        monitor_conf = fallback_output("MONITOR").confidence_score
        kill_conf = fallback_output("KILL_PROCESS").confidence_score
        assert kill_conf > monitor_conf


# ── Markdown Temizleme Testleri ───────────────────────────────

class TestStripMarkdownJson:
    """llm_adapter._strip_markdown_json() fonksiyonunun testleri."""

    def setup_method(self):
        """Her test öncesi fonksiyonu import et."""
        from server.infrastructure.llm_adapter import _strip_markdown_json
        self.strip = _strip_markdown_json

    def test_plain_json_unchanged(self):
        """Saf JSON → olduğu gibi döner."""
        raw = '{"risk_level": "high", "confidence_score": 0.9}'
        result = self.strip(raw)
        parsed = json.loads(result)
        assert parsed["risk_level"] == "high"

    def test_strips_json_code_block(self):
        """```json...``` bloğu soyulur."""
        raw = '```json\n{"risk_level": "medium"}\n```'
        result = self.strip(raw)
        parsed = json.loads(result)
        assert parsed["risk_level"] == "medium"

    def test_strips_plain_code_block(self):
        """```...``` bloğu soyulur."""
        raw = '```\n{"risk_level": "low"}\n```'
        result = self.strip(raw)
        parsed = json.loads(result)
        assert parsed["risk_level"] == "low"

    def test_extracts_json_from_surrounding_text(self):
        """Etrafında metin olan JSON → sadece JSON objesi çıkarılır."""
        raw = 'Here is my answer: {"risk_level": "critical"} Hope this helps!'
        result = self.strip(raw)
        parsed = json.loads(result)
        assert parsed["risk_level"] == "critical"


# ── JSON'dan LLMDecisionOutput Oluşturma ─────────────────────

class TestLLMOutputFromJSON:
    """LLM'den gelen JSON string'in LLMDecisionOutput'a dönüşümünü test eder."""

    def test_valid_json_string_to_output(self):
        """Geçerli JSON string → LLMDecisionOutput oluşturulabilmeli."""
        json_str = json.dumps({
            "risk_level": "high",
            "prediction_summary": "RAM kritik seviyede artıyor.",
            "recommended_action": "Servisi yeniden başlat.",
            "confidence_score": 0.85,
        })
        data = json.loads(json_str)
        output = LLMDecisionOutput(**data)
        assert output.risk_level == "high"
        assert output.confidence_score == 0.85

    def test_string_confidence_coerced_to_float(self):
        """LLM '0.85' string olarak verse bile Pydantic float'a çevirir."""
        output = LLMDecisionOutput(
            risk_level="medium",
            prediction_summary="Test.",
            recommended_action="Test.",
            confidence_score="0.85",  # String → float'a coerce edilmeli
        )
        assert isinstance(output.confidence_score, float)
        assert output.confidence_score == 0.85
