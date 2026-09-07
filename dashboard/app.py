"""
dashboard/app.py

4. Hafta: Streamlit FinTech Web Dashboard
=========================================
Bu dosya Streamlit uygulamasının giriş noktasıdır.
Çalıştırma: streamlit run dashboard/app.py
"""

import streamlit as st
import os
import sqlite3
import pandas as pd
import time

st.set_page_config(
    page_title="AI Chaos Platform - FinTech Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Veritabanı Yardımcı Fonksiyonları ---

def get_db_connection():
    """metrics.db bağlantısını döner; dosya yoksa None."""
    db_path = "metrics.db"
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(db_path)

# ttl=5: Verileri 5 saniyede bir önbellekte (cache) tutar.
# Bu sayede her saniye veritabanına sorgu atıp sistemi yormayız.
@st.cache_data(ttl=5)
def get_metrics_data():
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()

    # Pandas'ın SQL okuma fonksiyonu ile doğrudan DataFrame (Tablo) oluşturuyoruz.
    df = pd.read_sql_query("SELECT * FROM metrics ORDER BY timestamp DESC LIMIT 100", conn)
    #timestamp'e göre sırala ve son 100 veriyi getir.
    conn.close()    

    if not df.empty:
        # Tarih formatını daha düzgün okunabilir hale getirelim
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    return df

@st.cache_data(ttl=5)#st,Streamlit kütüphanesidir. @ ise dekoratör anlamındadır. Fonksiyonun çıktısını bellekte tutar.
def get_work_orders():
    conn = get_db_connection()#metriklerdeki get_db_connection ile aynı fonksiyon.
    if conn is None:
        return pd.DataFrame()

    df = pd.read_sql_query("SELECT * FROM work_orders ORDER BY created_at DESC", conn)
    conn.close()

    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], format="ISO8601")
        if "resolved_at" in df.columns:
            df["resolved_at"] = pd.to_datetime(df["resolved_at"], format="ISO8601")
    return df

def main():
    # 2. Sidebar (Sol Menü)
    with st.sidebar:
        st.title(" AI Chaos Platform")
        st.markdown("---")
        menu = st.radio(
            "Navigasyon",
            ["Ana Sayfa", "Sistem Durumu (Metrikler)", "Geçmiş İş Emirleri"]
        )
        st.markdown("---")
        st.caption("v1.0 - FinTech Edition")

    # Verileri çek
    metrics_df = get_metrics_data()
    work_orders_df = get_work_orders()

    # 3. Ana Sayfa İçeriği
    if menu == "Ana Sayfa":
        st.title("Ana Sayfa - Sisteme Genel Bakış")
        st.markdown("""
        AI Chaos Platform Yönetim Paneline Hoş Geldiniz.
        
        Finansal altyapıların kırılganlıklarını, sistemler çökmeden önce keşfeden; 
        **Yapay Zeka (YSA)** destekli, otonom bir **Chaos Engineering** ekosistemidir. 
        Geleceğin FinTech mimarilerini bugünden güvence altına alır.
        """)
        
        # Dinamik İstatistik Hesaplamaları
        active_agents = metrics_df["agent_id"].nunique() if not metrics_df.empty else 0
        total_work_orders = len(work_orders_df) if not work_orders_df.empty else 0
        
        # Risk seviyesi yüksek olanları anomali sayalım
        # Guard: risk_level sütunu yoksa KeyError'dan korunuyoruz
        if not work_orders_df.empty and "risk_level" in work_orders_df.columns:
            anomalies_count = len(work_orders_df[work_orders_df["risk_level"].isin(["YÜKSEK (HIGH)", "KRİTİK (CRITICAL)"])])
        else:
            anomalies_count = 0

        # Son Güncel Metrikleri Çek
        latest_cpu = metrics_df.iloc[0]["cpu_percent"] if not metrics_df.empty else 0.0
        latest_ram = metrics_df.iloc[0]["ram_percent"] if not metrics_df.empty else 0.0
        latest_used_gb = metrics_df.iloc[0]["ram_used_gb"] if not metrics_df.empty else 0.0

        st.subheader("Canlı Sistem Göstergeleri")
        mcol1, mcol2, mcol3 = st.columns(3)
        mcol1.metric("CPU Kullanımı", f"{latest_cpu:.1f} %")
        mcol2.metric("RAM Kullanımı", f"{latest_ram:.1f} %")
        mcol3.metric("Kullanılan Bellek", f"{latest_used_gb:.2f} GB")
        
        st.markdown("---")
        st.subheader("Platform Özeti")

        # Özet İstatistik Kartları
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"Aktif Ajan Sayısı: **{active_agents}**")
        with col2:
            st.warning(f"Toplam Anomali / Risk: **{anomalies_count}**")
        with col3:
            st.success(f"Oluşturulan İş Emri: **{total_work_orders}**")
            
        st.markdown("---")
        st.subheader("Son Gelişmeler: AI Model Ablation Study")
        
        img_path = "ai/permutation_importance.png"
        if os.path.exists(img_path):
            st.image(img_path, caption="YSA Permutation Importance (Hangi metrik daha etkili?)", use_container_width=False)
        else:
            st.info("Ablation Study grafiği henüz oluşturulmamış. (python ai/explainability.py)")

    elif menu == "Sistem Durumu (Metrikler)":
        st.title("Canlı Sistem Durumu")
        
        if metrics_df.empty:
            st.warning("Veritabanında henüz metrik bulunmuyor.")
        else:
            st.write("Son 100 metrik ölçümü gösterilmektedir.")
            
            # Zaman çizelgesi için grafiği tersine çeviriyoruz (eskiden yeniye)
            chart_data = metrics_df.sort_values(by="timestamp").set_index("timestamp")
            
            # Sütunlara bölelim
            col_cpu, col_ram = st.columns(2)
            
            with col_cpu:
                st.subheader("📈 CPU Kullanımı (%)")
                st.line_chart(chart_data[["cpu_percent"]], color="#FF4B4B") # Kırmızı renk
                
            with col_ram:
                st.subheader("📉 RAM Kullanımı (%)")
                st.area_chart(chart_data[["ram_percent"]], color="#0068C9") # Mavi renk
                
            st.subheader("Ham Veriler Tablosu")
            st.dataframe(metrics_df, use_container_width=True)
        
    elif menu == "Geçmiş İş Emirleri":
        st.title("ERP İş Emirleri")
        
        if work_orders_df.empty:
            st.success("Tebrikler! Sistemde açık veya geçmiş bir iş emri bulunmuyor.")
        else:
            st.write("YSA tarafından otomatik oluşturulmuş iş emirleri listesi:")
            
            # Dataframe'i ekranda interaktif olarak göster (Sıralama, filtreleme dahil)
            st.dataframe(
                work_orders_df,
                use_container_width=True,
                column_config={
                    "work_order_id": "İş Emri ID",
                    "agent_id": "Etkilenen Ajan",
                    "risk_level": "Risk Seviyesi",
                    "status": "Durum",
                    "description": "Açıklama / Uyarı",
                    "estimated_seconds_to_oom": "Çökmeye Kalan Süre (Sn)",
                    "ram_percent_at_trigger": "Tetiklenme RAM'i (%)",
                    "created_at": "Oluşturulma Zamanı"
                },
                hide_index=True
            )

    # if/elif bloklarının DIŞINDA, main() sonunda
    # Sayfa her 5 saniyede bir otomatik yenilenir (cache TTL ile senkronize)
    time.sleep(5)
    st.rerun()

if __name__ == "__main__":
    main()
