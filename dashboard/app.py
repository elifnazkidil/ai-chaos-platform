"""
dashboard/app.py

4. Hafta: Streamlit FinTech Web Dashboard
======================================================

FastAPI sunucusu: uvicorn server.api.main:app --reload (opsiyonel, DB fallback var)
"""

import streamlit as st
import os
import sqlite3
import pandas as pd
import requests
import plotly.graph_objects as go
import plotly.express as px
from streamlit_autorefresh import st_autorefresh  




st.set_page_config(
    page_title="AI Chaos Platform - FinTech Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

#  time.sleep+st.rerun yerine st_autorefresh — 5sn'de bir yeniler, sayfa donmaz
st_autorefresh(interval=5000, key="dashboard_autorefresh")

# ── Sabitler ───────────────────────────────────────────────────
API_BASE = "http://localhost:8000"
DB_PATH  = "metrics.db"


# ── Veritabanı & API Yardımcı Fonksiyonları ────────────────────

def get_db_connection():
    """metrics.db bağlantısını döner; dosya yoksa None."""
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)


#  FastAPI /api/v1/metrics/latest'ten veri çekme
@st.cache_data(ttl=5)
def get_metrics_from_api(limit: int = 100) -> pd.DataFrame:
    """
    Önce FastAPI'dan, erişilemezse doğrudan DB'den okur.
    Bu sayede API kapalıyken bile dashboard çalışır (DB fallback).
    """
    # --- FastAPI Denemesi ---
    try:
        resp = requests.get(f"{API_BASE}/api/v1/metrics/latest?limit={limit}", timeout=2)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                df = pd.DataFrame(data)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                return df
    except requests.exceptions.RequestException:
        pass  # API kapalı, DB'ye düş

    # --- DB Fallback ---
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    df = pd.read_sql_query(
        "SELECT * FROM metrics ORDER BY timestamp DESC LIMIT ?", conn,
        params=(limit,)
    )
    conn.close()
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    return df


@st.cache_data(ttl=5)
def get_work_orders() -> pd.DataFrame:
    """İş emirlerini DB'den okur."""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM work_orders ORDER BY created_at DESC", conn)
    conn.close()
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], format="ISO8601")
        if "resolved_at" in df.columns:
            df["resolved_at"] = pd.to_datetime(df["resolved_at"], errors="coerce", format="ISO8601")
    return df


# /api/v1/predictions endpoint'inden YSA tahminleri
@st.cache_data(ttl=5)
def get_predictions() -> list:
    """FastAPI /api/v1/predictions'tan YSA tahminlerini çeker."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/predictions?limit=1", timeout=2)
        if resp.status_code == 200:
            return resp.json().get("predictions", [])
    except requests.exceptions.RequestException:
        pass
    return []


#event_logs'u API'den çek
@st.cache_data(ttl=5)
def get_event_logs() -> pd.DataFrame:
    """self-healing event_logs'u FastAPI üzerinden çeker; yoksa DB'den."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/events?limit=200", timeout=2)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            return pd.DataFrame(data) if data else pd.DataFrame()
    except requests.exceptions.RequestException:
        pass
    # DB fallback
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            "SELECT id, timestamp, action, detail FROM event_logs ORDER BY timestamp DESC LIMIT 200", conn
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def call_chaos_api(endpoint: str) -> str:
    """Kaos API endpoint'ini çağırır, sonuç mesajını döner."""
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("message", "Başarılı.")
        return f"Hata: {resp.status_code}"
    except requests.exceptions.RequestException:
        return "❌ FastAPI'ye ulaşılamadı. Sunucu çalışıyor mu? (uvicorn server.api.main:app --reload)"


def resolve_work_order_api(work_order_id: str) -> bool:
    """İş emrini ÇÖZÜLDÜ olarak işaretler."""
    try:
        resp = requests.patch(
            f"{API_BASE}/api/v1/work-orders/{work_order_id}/resolve", timeout=3
        )
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


# ── Plotly Confidence Gauge ──────────────────────────
def render_confidence_gauge(score: float, title: str = "YSA Anomali Skoru"):
    """
    plotly.graph_objects.Indicator ile 0-1 arası anomali skorunu
    ibre (gauge) olarak gösterir.
    """
    color = "#2ecc71" if score < 0.4 else ("#f39c12" if score < 0.7 else "#e74c3c")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=round(score * 100, 1),
        title={"text": title, "font": {"size": 16}},
        delta={"reference": 50, "suffix": "%"},
        number={"suffix": "%", "font": {"size": 28}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 40],  "color": "#d5f5e3"},
                {"range": [40, 70], "color": "#fef9e7"},
                {"range": [70, 100],"color": "#fadbd8"},
            ],
            "threshold": {
                "line": {"color": "#c0392b", "width": 4},
                "thickness": 0.8,
                "value": 70
            }
        }
    ))
    fig.update_layout(height=250, margin=dict(t=40, b=10, l=20, r=20))
    return fig


# ── Ana Uygulama ───────────────────────────────────────────────
def main():
    # ── Sidebar ────────────────────────────────────────────────
    with st.sidebar:
        st.title("AI Chaos Platform")
        st.markdown("---")
        menu = st.radio(
            "Navigasyon",
            [
                "🏠 Ana Sayfa",
                "📊 Sistem Durumu",
                "🧠 YSA Tahmin Paneli",
                "📋 ERP İş Emirleri",
                "🕐 Anomaly Timeline",
                "💥 Kaos Kontrol",
            ]
        )
        st.markdown("---")


        st.caption("v2.0 | streamlit-autorefresh ✓")

    # ── Verileri Çek ───────────────────────────────────────────
    metrics_df    = get_metrics_from_api()
    work_orders_df = get_work_orders()
    events_df      = get_event_logs()

    # ══════════════════════════════════════════════════════════
    # SAYFA 1: ANA SAYFA
    # ══════════════════════════════════════════════════════════
    if menu == "🏠 Ana Sayfa":
        st.title("Ana Sayfa — Sisteme Genel Bakış")
        st.markdown("""
        AI Chaos Platform Yönetim Paneline Hoş Geldiniz.

        Finansal altyapıların kırılganlıklarını, sistemler çökmeden önce keşfeden;
        **Yapay Zeka (YSA)** ve **Qwen 2.5/Ollama LLM** destekli, otonom bir
        **Chaos Engineering** ekosistemidir.
        """)

        # Canlı Metrik Kartları
        latest_cpu    = metrics_df.iloc[0]["cpu_percent"]  if not metrics_df.empty else 0.0
        latest_ram    = metrics_df.iloc[0]["ram_percent"]  if not metrics_df.empty else 0.0
        latest_used_gb = metrics_df.iloc[0]["ram_used_gb"] if not metrics_df.empty else 0.0

        st.subheader("Canlı Sistem Göstergeleri")
        mcol1, mcol2, mcol3 = st.columns(3)
        mcol1.metric("🖥️ CPU Kullanımı",   f"{latest_cpu:.1f} %")
        mcol2.metric("🧠 RAM Kullanımı",   f"{latest_ram:.1f} %")
        mcol3.metric("💾 Kullanılan Bellek", f"{latest_used_gb:.2f} GB")

        st.markdown("---")
        st.subheader("Platform Özeti")

        active_agents   = metrics_df["agent_id"].nunique() if not metrics_df.empty else 0
        total_wo        = len(work_orders_df) if not work_orders_df.empty else 0
        if not work_orders_df.empty and "risk_level" in work_orders_df.columns:
            anomalies_count = len(work_orders_df[
                work_orders_df["risk_level"].isin(["YÜKSEK (HIGH)", "KRİTİK (CRITICAL)"])
            ])
        else:
            anomalies_count = 0

        col1, col2, col3 = st.columns(3)
        col1.info(    f"Aktif Ajan Sayısı: **{active_agents}**")
        col2.warning( f"Toplam Anomali / Risk: **{anomalies_count}**")
        col3.success( f"Oluşturulan İş Emri: **{total_wo}**")

        st.markdown("---")
        st.subheader("AI Model — Ablation Study")
        img_path = "ai/permutation_importance.png"
        if os.path.exists(img_path):
            from PIL import Image
            img = Image.open(img_path)
            st.image(img, caption="YSA Permutation Importance", use_container_width=False)
        else:
            st.info("Grafik henüz üretilmedi. → `python ai/explainability.py`")

    # ══════════════════════════════════════════════════════════
    # SAYFA 2: SİSTEM DURUMU (FastAPI + line_chart)
    # ══════════════════════════════════════════════════════════
    elif menu == "📊 Sistem Durumu":
        st.title("📊 Canlı Sistem Durumu")

        if metrics_df.empty:
            st.warning("Henüz metrik yok. FastAPI veya agent çalışıyor mu?")
        else:
            # Kaynak göstergesi
            api_ok = False
            try:
                r = requests.get(f"{API_BASE}/", timeout=1)
                api_ok = r.status_code == 200
            except Exception:
                pass
            st.caption(
                f"🟢 FastAPI bağlı — veriler API'den" if api_ok
                else "🟡 FastAPI kapalı — veriler doğrudan DB'den"
            )

            chart_data = metrics_df.sort_values("timestamp").set_index("timestamp")

            #  st.line_chart ile canlı zaman serisi — CPU + RAM aynı grafikte
            st.subheader("📈 CPU & RAM Zaman Serisi (Canlı)")
            st.line_chart(
                chart_data[["cpu_percent", "ram_percent"]],
                color=["#FF4B4B", "#0068C9"]
            )

            col_cpu, col_ram = st.columns(2)
            with col_cpu:
                st.subheader("CPU Kullanımı (%)")
                st.line_chart(chart_data[["cpu_percent"]], color="#FF4B4B")
            with col_ram:
                st.subheader("RAM Kullanımı (%)")
                st.area_chart(chart_data[["ram_percent"]], color="#0068C9")

            st.subheader("Ham Veri Tablosu")
            st.dataframe(metrics_df, use_container_width=True)

    # ══════════════════════════════════════════════════════════
    # SAYFA 3: YSA TAHMİN PANELİ 
    # ══════════════════════════════════════════════════════════
    elif menu == "🧠 YSA Tahmin Paneli":
        st.title("🧠 YSA Tahmin Paneli")

        predictions = get_predictions()

        if not predictions:
            st.warning(
                "YSA tahmini alınamadı. FastAPI çalışıyor mu ve model eğitildi mi?\n\n"
                "`uvicorn server.api.main:app --reload`"
            )
        else:
            pred = predictions[0]  # En son tahmin
            score     = pred.get("anomaly_score", 0.0)
            is_anomaly = pred.get("is_anomaly", False)
            risk_level = pred.get("risk_level", "NORMAL")
            ram_pct    = pred.get("ram_percent", 0.0)
            cpu_pct    = pred.get("cpu_percent", 0.0)

            # Risk Durumu Gösterimi — st.error / st.warning / st.success
            st.subheader("Anlık Risk Durumu")
            if "CRITICAL" in risk_level or score >= 0.8:
                st.error(f"🚨 KRİTİK RİSK! Anomali skoru: {score:.2f} — Sistem müdahale gerektirebilir!")
            elif "HIGH" in risk_level or score >= 0.6:
                st.warning(f"⚠️ YÜKSEK RİSK. Anomali skoru: {score:.2f} — Dikkatli izleme gerekli.")
            elif score >= 0.4:
                st.warning(f"🟡 ORTA RİSK. Anomali skoru: {score:.2f}")
            else:
                st.success(f"✅ Normal. Anomali skoru: {score:.2f} — Sistem sağlıklı.")

            st.markdown("---")

            # Confidence Gauge + TTF
            gauge_col, ttf_col = st.columns([2, 1])

            with gauge_col:
                st.subheader("Confidence Gauge")
                fig_gauge = render_confidence_gauge(score)
                st.plotly_chart(fig_gauge, use_container_width=True)

            with ttf_col:
                st.subheader("⏱️ TTF (Çökmeye Kalan Süre)")
                # En son metrikten estimated_seconds_to_oom bul
                ttf_seconds = None
                if not work_orders_df.empty and "estimated_seconds_to_oom" in work_orders_df.columns:
                    ttf_row = work_orders_df[work_orders_df["status"] != "ÇÖZÜLDÜ"]
                    if not ttf_row.empty:
                        ttf_seconds = ttf_row.iloc[0]["estimated_seconds_to_oom"]

                if ttf_seconds is not None and ttf_seconds > 0:
                    mins = int(ttf_seconds // 60)
                    secs = int(ttf_seconds % 60)
                    if ttf_seconds < 300:
                        st.error(f"🔴 {mins}dk {secs}sn")
                    elif ttf_seconds < 600:
                        st.warning(f"🟡 {mins}dk {secs}sn")
                    else:
                        st.info(f"🟢 {mins}dk {secs}sn")
                    st.caption("Tahmin edilen çökme süresi (OOM)")
                else:
                    st.success("♾️ Çökme riski yok")

                st.markdown("---")
                st.metric("RAM", f"{ram_pct:.1f}%")
                st.metric("CPU", f"{cpu_pct:.1f}%")
                st.caption(f"Risk: **{risk_level}**")

            # Tüm tahmin skoru geçmişi
            all_preds = get_predictions.__wrapped__(100) if hasattr(get_predictions, "__wrapped__") else []
            if len(predictions) > 1:
                st.subheader("Anomali Skor Geçmişi")
                pred_df = pd.DataFrame(predictions)
                if "timestamp" in pred_df.columns:
                    pred_df["timestamp"] = pd.to_datetime(pred_df["timestamp"])
                    pred_df = pred_df.sort_values("timestamp").set_index("timestamp")
                    st.line_chart(pred_df[["anomaly_score"]], color="#8A2BE2")

    # ══════════════════════════════════════════════════════════
    # SAYFA 4: ERP İŞ EMİRLERİ — resolve butonu)
    # ══════════════════════════════════════════════════════════
    elif menu == "📋 ERP İş Emirleri":
        st.title("📋 ERP İş Emirleri")

        if work_orders_df.empty:
            st.success("Sistemde açık bir iş emri bulunmuyor.")
        else:
            # Açık iş emirleri
            open_wo = work_orders_df[work_orders_df["status"] != "ÇÖZÜLDÜ"] \
                if "status" in work_orders_df.columns else work_orders_df
            closed_wo = work_orders_df[work_orders_df["status"] == "ÇÖZÜLDÜ"] \
                if "status" in work_orders_df.columns else pd.DataFrame()

            st.subheader(f"Açık İş Emirleri ({len(open_wo)})")
            if open_wo.empty:
                st.success("Açık iş emri yok.")
            else:
                for _, row in open_wo.iterrows():
                    wo_id  = row.get("work_order_id", "?")
                    risk   = row.get("risk_level", "?")
                    agent  = row.get("agent_id", "?")
                    ram_t  = row.get("ram_percent_at_trigger", 0)
                    ttf_s  = row.get("estimated_seconds_to_oom", 0)
                    desc   = row.get("description", "")

                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(
                            f"**{wo_id}** | Risk: `{risk}` | Ajan: `{agent}` | "
                            f"RAM: `{ram_t:.0f}%` | TTF: `{ttf_s:.0f}sn`"
                        )
                        if desc:
                            st.caption(desc)
                    with col_btn:
                        #: st.button ile durumcelleme
                        if st.button("✅ Çözüldü", key=f"resolve_{wo_id}"):
                            success = resolve_work_order_api(wo_id)
                            if success:
                                st.toast(f"{wo_id} çözüldü olarak işaretlendi!", icon="✅")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.toast("Güncelleme başarısız - FastAPI çalışıyor mu?", icon="❌")
                    st.divider()

            if not closed_wo.empty:
                with st.expander(f"Çözülmüş İş Emirleri ({len(closed_wo)})"):
                    st.dataframe(
                        closed_wo,
                        use_container_width=True,
                        column_config={
                            "work_order_id": "İş Emri ID",
                            "agent_id":      "Ajan",
                            "risk_level":    "Risk",
                            "status":        "Durum",
                            "created_at":    "Oluşturulma",
                            "resolved_at":   "Çözülme",
                        },
                        hide_index=True
                    )

    # ══════════════════════════════════════════════════════════
    # SAYFA 5: ANOMALY TIMELINE )
    # ══════════════════════════════════════════════════════════
    elif menu == "🕐 Anomaly Timeline":
        st.title("🕐 Anomaly Timeline — Olay Zaman Çizelgesi")
        st.markdown("Tüm anomali tespitleri, ERP iş emirleri ve self-healing aksiyonları kronolojik sırayla.")

        # İş emirlerinden olaylar oluştur
        timeline_rows = []

        if not work_orders_df.empty:
            for _, row in work_orders_df.iterrows():
                risk = row.get("risk_level", "NORMAL")
                color = (
                    "red" if "CRITICAL" in str(risk)
                    else "orange" if "HIGH" in str(risk)
                    else "blue"
                )
                start = row.get("created_at", pd.Timestamp.now())
                end   = row.get("resolved_at", pd.NaT)
                if pd.isna(end):
                    end = start + pd.Timedelta(minutes=5)

                timeline_rows.append({
                    "Görev":    f"İş Emri: {row.get('work_order_id','?')}",
                    "Başlangıç": start,
                    "Bitiş":     end,
                    "Kategori":  f"ERP ({risk})",
                    "Renk":      color,
                })

        # Self-healing event_logs
        if not events_df.empty:
            for _, row in events_df.iterrows():
                ts = pd.to_datetime(row.get("timestamp"), errors="coerce")
                if pd.isna(ts):
                    continue
                timeline_rows.append({
                    "Görev":    f"Self-Heal: {row.get('action','?')}",
                    "Başlangıç": ts,
                    "Bitiş":     ts + pd.Timedelta(minutes=1),
                    "Kategori":  "Self-Healing",
                    "Renk":      "green",
                })

        if not timeline_rows:
            st.info(
                "Henüz olay kaydı yok.\n\n"
                "İş emirleri ve self-healing aksiyonları burada görünecek."
            )
        else:
            #: plotly.express.timeline
            tl_df = pd.DataFrame(timeline_rows)
            fig = px.timeline(
                tl_df,
                x_start="Başlangıç",
                x_end="Bitiş",
                y="Kategori",
                text="Görev",
                color="Kategori",
                title="Anomali & Self-Healing Olay Zaman Çizelgesi",
            )
            fig.update_yaxes(categoryorder="total ascending")
            fig.update_layout(height=400, margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Ham Olay Logu")
            if not events_df.empty:
                st.dataframe(events_df, use_container_width=True, hide_index=True)
            else:
                st.info("event_logs tablosu boş (self-healing henüz çalışmadı).")

    # ══════════════════════════════════════════════════════════
    # SAYFA 6: KAOS KONTROL PANELİ  
    # ══════════════════════════════════════════════════════════
    elif menu == "💥 Kaos Kontrol":
        st.title("💥 Kaos Test Kontrol Paneli")
        st.markdown("""
        Bu panel, **FastAPI** üzerinden kaos senaryolarını başlatıp durdurmanı sağlar.
        FastAPI sunucusu çalışıyor olmalı: `uvicorn server.api.main:app --reload`
        """)

        st.warning("⚠️ Kaos testleri gerçek bellek ve CPU kullanır. Dikkatli kullan!")
        st.markdown("---")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("🔴 Bellek Sızıntısı")
            st.markdown(
                "**agent/chaos.py** üzerinden RAM'i adım adım doldurur. "
                "YSA'nın anomali tespitini test etmek için kullan."
            )
            if st.button("▶️ Bellek Sızıntısı Başlat", use_container_width=True, type="primary"):
                msg = call_chaos_api("/api/v1/chaos/start-leak")
                st.info(msg)

        with col2:
            st.subheader("🟠 CPU Stress")
            st.markdown(
                "**30 saniye** boyunca CPU'yu maksimuma çeker. "
                "Yüksek CPU altında YSA davranışını gözlemler."
            )
            if st.button("▶️ CPU Stress Başlat", use_container_width=True):
                msg = call_chaos_api("/api/v1/chaos/start-cpu")
                st.info(msg)

        with col3:
            st.subheader("⬛ Kaos Durdur")
            st.markdown(
                "Çalışan kaos senaryosunu durdurur. "
                "Daemon thread'ler otomatik olarak sonlanır."
            )
            if st.button("⏹️ Tüm Kaos'u Durdur", use_container_width=True):
                msg = call_chaos_api("/api/v1/chaos/stop")
                st.info(msg)

        st.markdown("---")
        st.subheader("📡 FastAPI Bağlantı Durumu")
        try:
            r = requests.get(f"{API_BASE}/", timeout=2)
            if r.status_code == 200:
                st.success(f"✅ FastAPI çalışıyor — {API_BASE}")
            else:
                st.error(f"❌ API erişilebilir ama hata döndü: {r.status_code}")
        except requests.exceptions.RequestException:
            st.error(
                f"❌ FastAPI'ye ulaşılamıyor ({API_BASE})\n\n"
                "Terminalde şunu çalıştır: `uvicorn server.api.main:app --reload`"
            )

        st.markdown("---")
        st.subheader("📜 Son Self-Healing Olayları")
        if events_df.empty:
            st.info("Henüz self-healing aksiyonu kaydedilmemiş.")
        else:
            st.dataframe(events_df.head(10), use_container_width=True, hide_index=True)


# ── Giriş Noktası ──────────────────────────────────────────────
if __name__ == "__main__":
    main()
