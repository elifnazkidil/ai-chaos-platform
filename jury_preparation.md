# FinTech YSA Platformu — Jüri Hazırlık Dokümanı

Her fonksiyon, her parametre, her mimari karar. Koda bakınca anlamadığın yer kalmaması için hazırlanmış nihai master rehber.

## İÇİNDEKİLER
1. [Sistem Mimarisi — Büyük Resim](#1-sistem-mimarisi)
2. [neural_network.py — Satır Satır](#2-neural_networkpy)
3. [decision_engine.py — Satır Satır](#3-decision_enginepy)
4. [monitor.py — Satır Satır](#4-monitorpy)
5. [chaos.py — Satır Satır](#5-chaospy)
6. [self_healing.py — Satır Satır](#6-self_healingpy)
7. [llm_adapter.py — Satır Satır](#7-llm_adapterpy)
8. [main.py (FastAPI) — Satır Satır](#8-mainpy-fastapi)
9. [explainability.py (XAI - Açıklanabilir Yapay Zeka)](#9-explainabilitypy-xai---açıklanabilir-yapay-zeka)
10. [dashboard/app.py (Streamlit)](#10-dashboardapppy-streamlit)
11. [Ölçeklenebilirlik (Scalability) ve Gelecek Vizyonu](#11-ölçeklenebilirlik-scalability-ve-gelecek-vizyonu)
12. [Jüri Soruları ve Cevaplar](#12-jüri-soruları-ve-cevaplar)
13. [Kavram Sözlüğü](#13-kavram-sözlüğü)
14. [Kaynaklar](#14-kaynaklar)

---

## 1. Sistem Mimarisi

**Veri Akışı (Kim kimi çağırıyor?)**
- **monitor.py** → Her saniye CPU/RAM ölçer → metrics.db'ye yazar → CPU>85 veya RAM>80 olunca → POST /api/v1/evaluate 
- **chaos.py** → Kasıtlı bellek sızıntısı / CPU spike üretir → monitor.py bunu yüksek metrik olarak görür 
- **main.py (FastAPI)** → HTTP isteklerini karşılar 
  - /api/v1/metrics → SQLite'a kaydeder 
  - /api/v1/evaluate → DecisionEngine'i çağırır 
  - /api/v1/predictions → YSA modelini çalıştırır 
- **decision_engine.py** → YSA skoru alır → Kural Motoru → LLM açıklar → Telegram 
- **neural_network.py** → Eğitim (AnomalyTrainer.train) ve tahmin (predict) yapar 
- **self_healing.py** → Anomali varsa psutil ile prosesi öldürür, n8n'e webhook atar 
- **llm_adapter.py** → Ollama'ya HTTP POST atar, cevabı döner

**Clean Architecture Katmanları**
```text
server/ 
├── domain/ → Saf Python. Dış dünyadan bağımsız. Sadece iş kuralları. │ (Metric entity, WorkOrder entity, özel Exception sınıfları) 
├── usecases/ → İş akışları. Domain'i kullanır, altyapıyı bilmez. │ (SaveMetricUseCase, DecisionEngine, self_healing) 
├── infrastructure/ → Dış dünyayla bağlantı. Veritabanı, LLM, HTTP. │ (SQLiteMetricRepository, llm_adapter, database) 
└── api/ → HTTP katmanı. FastAPI endpoint'leri buradadır. (main.py)
```
Neden bu mimari? İş mantığını (YSA, karar motoru) dış teknolojilerden (SQLite, Telegram, Ollama) ayırıyorsun. Yarın SQLite yerine PostgreSQL koysun istersen sadece infrastructure katmanını değiştirirsin, karar motoru hiç bozulmaz.

---

## 2. neural_network.py

**Genel Yapı: 3 Sınıf**
- **AnomalyMLP**: Sinir ağının katman yapısını tanımlar (mimari)
- **MetricNormalizer**: Ham verileri 0-1 arasına normalize eder
- **AnomalyTrainer**: Eğitim döngüsünü yönetir, tahmin yapar

**AnomalyMLP — Sinir Ağı Mimarisi**
`nn.Module`'den miras almak neden zorunlu? PyTorch'un tüm modelleri bu sınıftan türetilir. `nn.Module` sayesinde PyTorch modelin ağırlıklarını (parametrelerini) otomatik takip eder. Bunu yapmazsan `model.parameters()` ve `model.save()` çalışmaz.
`super().__init__()` — `nn.Module`'ün kendi başlatma kodunu çalıştırır. ZORUNLUDUR, yazmazsan PyTorch parametreleri bulamaz.

`input_size=4` — 4 özellik: CPU%, RAM%, Disk%, Network%. Disk ve Network şu an sabit değer (10.0) giriyor çünkü DB'de bu sütunlar yok.
`hidden_sizes=[64, 32, 16]` — 3 gizli katman:
- 64 nöron: Her metriğin bireysel pattern'ini öğrenir
- 32 nöron: Metrikler arası ilişkileri öğrenir (CPU ve RAM aynı anda yükseldi mi?)
- 16 nöron: Karmaşık anomali pattern'lerini birleştirir

`dropout_rate=0.2` — Eğitim sırasında nöronların %20'si rastgele kapatılır. Neden? Modelin belirli nöronlara "bağımlı" olmasını engellemek için. Bu olmadan model eğitim verisini ezberler (overfitting), ama yeni veriyle başarısız olur.

**Katman Yapısı (`nn.Sequential` içindeki sıra)**
Her gizli katman için şu 4 şey eklenir:
- `nn.Linear(prev_size, hidden_size)` Tam bağlantılı katman. Her girdi nöronu her çıktı nöronuna bağlı. Formül: çıkış = girdi × ağırlık_matrisi + bias
- `nn.BatchNorm1d` Her katmanın çıktısını normalize eder (ortalama≈0, std≈1). Eğitimi hızlandırır ve kararsız gradientleri (exploding/vanishing gradient) önler.
- `nn.ReLU()` ReLU(x) = max(0, x) — negatif değerleri sıfırlar. Bu olmadan model sadece doğrusal (düz çizgi) ilişkileri öğrenebilir. ReLU sayesinde eğrisel, karmaşık ilişkileri öğrenir.
- `nn.Dropout(0.2)` Eğitim sırasında aktif, tahmin sırasında otomatik kapanır. `model.eval()` çağrıldığında Dropout devre dışı kalır.

Çıkış katmanı:
- `nn.Linear(prev_size, 1)`
- `nn.Sigmoid()` — 1 / (1 + e^(-x)) formülü. Çıkışı 0 ile 1 arasına sıkıştırır. Bu çıkış "anomali olasılığı" olarak yorumlanır. 0.87 → %87 ihtimalle anomali.

**MetricNormalizer — Neden Normalize Ediyoruz?**
Network değeri CPU'dan 100 kat büyük olabilir. Normalize etmezsek sinir ağı Network'e aşırı önem verip diğerlerini görmezden gelir. Bu yanlış tahmine yol açar.
- **fit vs transform (Simetri):** `fit_transform()` sadece eğitim verisinde kullanılır. Tahmin (inference) sırasında SADECE `transform()` çağrılır. Çünkü model test verisini değil, eğitim verisinin min-max aralıklarını referans almalıdır.

**AnomalyTrainer — Eğitim Motoru**
- `self.criterion = nn.BCELoss()`: Binary Cross-Entropy Loss. İkili sınıflandırma için kullanılır. Formül: `-[y·log(ŷ) + (1-y)·log(1-ŷ)]`
- `self.optimizer = torch.optim.Adam()`: Adam Optimizer — Gradient descent'in akıllı versiyonu. Her parametre için öğrenme hızını otomatik ayarlar.

**Eğitim Döngüsü (Önemli Detaylar)**
- **`shuffle_idx = np.random.permutation(len(X_train))`:** Eğitim verisini karıştırır. Karıştırılmazsa model verinin sırasını ezberler (örn. ilk 200 satır normal, son 80 satır anomali). Bu da öğrenmeyi bozar.
- **Forward Pass:** Tahmin üret.
- **Loss Hesabı:** Tahmin ne kadar yanlış hesapla.
- **Backward Pass:** `zero_grad()` ZORUNLU — PyTorch gradient'leri biriktirdiği için, sıfırlamazsak yanlış güncelleme olur. Sonra `loss.backward()`.
- **Optimizer Step:** `optimizer.step()` ile ağırlıkları güncelle.

**Model Kaydetme (`torch.save`)**
`state_dict()` — Modelin tüm ağırlıklarını ve bias'larını içeren sözlük.
- **Neden optimizer_state kaydediliyor?** Yalnızca model ağırlıklarını değil, optimizer durumunu da (örn. momentum değerleri) kaydediyoruz ki, eğitime daha sonra kalınan yerden aynı optimizasyon ivmesiyle devam edilebilsin.

---

## 3. decision_engine.py

**Genel Akış**
`evaluate(cpu, ram, ...)` çağrılır
↓ `_get_anomaly_score()` → YSA'dan 0-1 arası skor al
↓ `_select_action()` → ACTION_TABLE'dan aksiyon seç (deterministik)
↓ `_generate_explanation()` → Qwen'e prompt at, Türkçe açıklama al
↓ `_send_notification()` → Telegram'a formatlı mesaj gönder
↓ `_log_decision()` → event_logs tablosuna kaydet

**ACTION_TABLE — Kural Motoru**
Neden 1.1 son eşik? Sigmoid çıkışı maksimum 1.0 olabilir. 1.1 kullanmak, skorun her zaman bu eşiğin altında kalmasını ve dolayısıyla KILL_PROCESS'in yakalanmasını garanti eder.
`_select_action()` neden `@staticmethod`? `self`'e ihtiyacı yok, sadece skoru alıp tablo üzerinde işlem yapıyor.

**_get_anomaly_score() — Fallback Mantığı**
Model yüklü değilse basit bir ağırlıklı formülle skor hesaplar. RAM'e daha yüksek ağırlık (0.6) verilmiş çünkü bellek sızıntısı bu projede ana senaryo.
Disk ve Network için 10.0 sabit değer verilir.

**_generate_explanation() — LLM + Fallback**
Prompt İngilizce çünkü Qwen 0.5b küçük model, İngilizce'de daha tutarlı yanıt veriyor.
Fallback sözlüğü: LLM yanıt vermezse aksiyon koduna göre statik Türkçe mesaj döner. Bu sayede Ollama çöktüğünde DecisionEngine çökmez, sistem çalışmaya devam eder.

---

## 4. monitor.py

**init_db() — Neden Bağlantıyı Dışarıda Tutuyoruz?**
init_db() bağlantıyı açar ve döner. Bu bağlantı db_conn değişkeninde hayatta kalır. Program çalıştığı sürece aynı bağlantı kullanılır. Alternatif olarak her saniye yeni bağlantı aç/kapat performansı mahvederdi.

**get_system_metrics()**
`interval=1` — 1 saniye boyunca CPU aktivitesini ölçer. Bu parametresiz çağrılırsa anlık snapshot alınır ve ilk çağrıda her zaman 0.0 döner.
`virtual_memory()` RAM bilgisini döner. GB'a çevirmek için 1024**3'e bölüyoruz.

**API Entegrasyonu — Threshold Mantığı**
Her saniye evaluate çağrılırsa Qwen her saniye çalışır, Telegram spam olur, sistem yavaşlar. `timeout=30` kullanıldı çünkü Qwen 0.5b RAM'e yüklenirken zaman alabilir.

---

## 5. chaos.py

**simulate_memory_leak()**
Neden bu çalışıyor? Python'da bir nesneye referans varsa o nesne GC (Garbage Collector) tarafından temizlenmez. leaked_memory listesi bu referansları tutuyor. Liste clear() edilmediği sürece bellek serbest bırakılmaz.
`rss (Resident Set Size)` — işletim sisteminin bu process'e tahsis ettiği gerçek RAM miktarı.

**simulate_cpu_spike()**
Neden thread değil process? Python'da GIL (Global Interpreter Lock) vardır. Aynı anda sadece bir thread Python kodu çalıştırabilir. multiprocessing.Process her biri ayrı Python yorumlayıcısında çalışır, GIL'den etkilenmez.
`p.join()` — Process bitene kadar bekle. zombie process oluşumunu önler.

---

## 6. self_healing.py

**mitigate_memory_leak() — Proses Öldürme**
`process_iter(['pid', 'name', 'memory_percent'])` — Tüm özellikleri çekmek ağır bir sistem çağrısıdır, sadece bunları önceden çekeriz.
Öldürme mantığı koşulları: İsmi "chaos" ise veya (RAM %80 üstü VE whitelist'te değilse).
- `p.terminate()` — SIGTERM: nazikçe kapat.
- `p.kill()` — SIGKILL: zorla kapat.

**process_iter Exception Üçlüsü (Önemli!):**
- `psutil.NoSuchProcess`: İşlemi öldürmek isterken o işlem çoktan kapanmış olabilir.
- `psutil.AccessDenied`: Root/Admin yetkisi gerektiren bir işlemi öldürmeye çalışınca alınır.
- `psutil.ZombieProcess`: İşlem ölmüştür ancak ebeveyn (parent) süreci onu sistemden temizlememiştir. Bu 3 hatanın yönetilmesi stabilitenin kalbidir.

**trigger_n8n_webhook()**
`timeout=2` çok kısa, kasıtlı. n8n yoksa hemen hata verir ve `WEBHOOK_FAILED` loglar.

---

## 7. llm_adapter.py

**generate() Fonksiyonu**
- `stream: False` — Tüm yanıtı tek seferde al. (SSE yerine)
- `num_predict: max_tokens` — Üretilecek maksimum token sayısı.
- `temperature: 0.7` — Yaratıcılık seviyesi. 0.0 deterministik, 1.0 rastgele, 0.7 dengeli.
- `response.raise_for_status()` — HTTP 4xx veya 5xx gelirse otomatik exception fırlatır.

---

## 8. main.py (FastAPI)

**Uygulama Başlangıcı — Global Scope**
Nesneler sunucu başlarken bir kez oluşturulur ve RAM'de kalır. "Dependency Injection" benzeri bir pattern.
**CORS Middleware**: Tarayıcılar güvenlik nedeniyle Streamlit (8501) üzerinden API'ye (8000) istek atılmasını engeller. CORS buna izin verir.

**/api/v1/metrics — status_code=202**
202 Accepted — "İsteği aldım, arka planda işliyorum." 200 yerine 202 kullanılıyor çünkü metrik kaydetme BackgroundTasks ile arka planda devam ediyor.

**/api/v1/train — ProcessPoolExecutor**
YSA eğitimi CPU-bound bir iştir. ProcessPoolExecutor bunu ayrı bir process'te çalıştırır, FastAPI event loop'u bloke olmaz.
- **`asyncio.ensure_future` vs `await`:** Burada `await` kullanılmadı çünkü bu bir "fire-and-forget" (ateşle ve unut) işlemidir. İstemci eğitim bitene kadar dakikalarca beklemez.

**daemon=True**
Ana thread (FastAPI) kapanırsa chaos thread'i otomatik kapanır.

---

## 9. explainability.py (XAI - Açıklanabilir Yapay Zeka)

- **Permutation Importance (Ablation Study)**: Modelin "kara kutu" olmaktan çıkıp, kararlarını neye göre verdiğini kanıtlayan matematiksel bir testtir.
- **Nasıl Çalışır?**: Sisteme %100 CPU ve RAM gibi bilinen bir anomali verisi verilir. Sonra sırayla "Sadece CPU'yu sıfırlarsam skor ne kadar düşer?", "Sadece RAM'i sıfırlarsam skor ne kadar düşer?" soruları sorulur. Skordaki düşüş miktarı, o değişkenin model için "Önem Katsayısı"dır.
- **Neden Önemli?**: Jüriye modelin ezber yapmadığını, CPU ve RAM yükseldiğinde gerçekten onlara bakarak anomali tespiti yaptığını ispatlamak için kullanılır.

---

## 10. dashboard/app.py (Streamlit)

- **Streamlit**: Python ile yazılmış saf veri bilimi ve makine öğrenmesi modellerini hızlıca interaktif web arayüzlerine dönüştüren bir kütüphanedir. Frontend (HTML/JS) yazmaya gerek bırakmaz.
- **Canlı Veri Akışı**: Dashboard, bir veritabanı bağlantısı açmak yerine doğrudan `FastAPI` uç noktalarına (`/api/v1/metrics/latest` ve `/api/v1/predictions`) HTTP `GET` isteği atarak verileri çeker. Bu da mikroservis mantığına (ayrık mimari) uygundur.

---

## 11. Ölçeklenebilirlik (Scalability) ve Gelecek Vizyonu

Jüri genellikle *"Bu sistem 10 değil, 10,000 sunucu bağlandığında ne olur?"* diye soracaktır. Cevaplarınız:
- **Veritabanı Limitleri**: Şu an kullanılan SQLite, çoklu yazma işlemlerinde kilitlenme (lock) yaşar. 10,000 ajan bağlandığında veritabanı altyapısı doğrudan **PostgreSQL** veya **TimescaleDB** (Zaman Serisi DB) ile değiştirilmelidir. Clean Architecture sayesinde bu değişiklik sadece `infrastructure` klasörünü etkiler, sistemi bozmaz.
- **Mesaj Kuyrukları (Message Queues)**: API'ye aynı saniyede 10,000 istek gelirse FastAPI çökebilir. Gelecek vizyonu olarak mimarinin arasına bir **RabbitMQ** veya **Apache Kafka** kuyruğu eklenmeli, agent'lar metrikleri Kafka'ya atmalıdır.
- **Agent İletişimi**: Ajanlar HTTP yerine **gRPC** veya **WebSockets** ile çift yönlü iletişim kuracak şekilde güncellenebilir.

---

## 12. Jüri Soruları ve Cevaplar

### Mimari Sorular
**S: Clean Architecture neden kullandın, basit bir Flask uygulaması yetmez miydi?**
**C:** Yeterdi ama sürdürülebilir olmazdı. Şu an SQLite kullanıyorum; yarın PostgreSQL'e geçmek istersem sadece `SQLiteMetricRepository`'yi değiştiririm, `DecisionEngine` hiç bozulmaz. 

**S: Repository Pattern nedir?**
**C:** Veri kaynağını soyutlar. Use case'ler SQLite mi PostgreSQL mi olduğunu bilmez.

### YSA ve Veri Soruları
**S: 887 kayıt nasıl üretildi, sentetik veri güvenilir mi?**
**C:** `np.random.uniform` ile FinTech sunucularındaki davranışlara yakın mantıklı aralıklar tanımlanarak üretildi. Gerçek hayatta bu aralıklar domain uzmanları tarafından belirlenir. Amacımız pipeline'ın uçtan uca çalıştığını kanıtlamaktır.

**S: Model evaluation metric'lerin neler? Accuracy hesapladın mı?**
**C:** Model bir regresyon çıktısı (0-1 arası sürekli değer) veriyor, bu yüzden öncelikle BCELoss izlendi. Sınıflandırma (Classification) threshold'a (0.5) göre yapıldığı için PoC aşamasında Loss yeterlidir. Üretim aşamasında Precision, Recall ve F1-Score eklenecektir.

### LLM ve Araç Soruları
**S: Neden Streamlit, React değil?**
**C:** Projenin odak noktası yapay zeka, mimari ve altyapı güvenliğidir. Streamlit, Python ekosistemiyle %100 entegre çalışır. Üretim ortamında frontend ekibi React ile özel bir UI yazabilir, ancak mimarim zaten API tabanlı olduğu için bu değişim kusursuz olur.

**S: LLM neden karar vermiyor?**
**C:** Halüsinasyon riski var. Karar deterministik kural motorunda, LLM sadece kararı insan diline çeviriyor. Bu Explainable AI prensibinin ta kendisi.

### Altyapı ve Güvenlik Soruları
**S: n8n gerçekten çalışıyor mu?**
**C:** Şu an sunucuda n8n kurulu değil, webhook "fallback" mantığına düşerek durumu logluyor. Mimari tasarım entegrasyona tamamen hazır; n8n sunucusu ayağa kaldırıldığı saniye SAP vb. sistemlere iş emri açabilecek durumdadır.

**S: Telegram token güvenliği nerede sağlanıyor?**
**C:** Hardcoded (koda gömülü) değil, `.env` dosyasından okunuyor. `.env` dosyası da `.gitignore` içinde yer alıyor, yani GitHub'a pushlanmıyor. Bu temel bir siber güvenlik prensibidir.

**S: Fallback neden önemli?**
**C:** "Dayanıklılık" (Resilience) projesinde kendi sisteminin dışa bağımlılıklar yüzünden çökmesi tutarsız olurdu. Ollama kapanırsa sistem statik mesajla devam ediyor.

---

## 13. Kavram Sözlüğü
- **MLP (Multi-Layer Perceptron):** Birden fazla katmanlı tam bağlantılı sinir ağı.
- **BCELoss:** Binary Cross-Entropy Loss. İkili sınıflandırma (var/yok) için kayıp fonksiyonu.
- **Dropout:** Eğitim sırasında rastgele nöronları kapatma. Overfitting'i önler.
- **Adam Optimizer:** Adaptif öğrenme hızlı optimizasyon algoritması.
- **Clean Architecture:** İş mantığını dış teknolojilerden izole eden mimari (Uncle Bob).
- **GIL (Global Interpreter Lock):** Python'da aynı anda tek thread'in CPU çalıştırmasını sağlayan mekanizma.
- **SIGTERM / SIGKILL:** Nazikçe kapatma (Term) ve zorla öldürme (Kill) sinyalleri.
- **XAI (Explainable AI):** Yapay zekanın kararlarını insan anlayacağı şekilde açıklama prensibi.
- **RSS (Resident Set Size):** Process'in gerçekte kullandığı fiziksel RAM miktarı.
- **CORS:** Cross-Origin Resource Sharing. Tarayıcının farklı portlar arası isteklere izin vermesi.

---

## 14. Kaynaklar
- **Sinir Ağları ve PyTorch**: `pytorch.org/docs`, *3Blue1Brown - Neural Networks (YouTube)*
- **Clean Architecture**: *"Clean Architecture" — Robert C. Martin (Uncle Bob)*
- **Chaos Engineering**: *Principles of Chaos Engineering — Netflix*
- **FastAPI**: `fastapi.tiangolo.com`
- **XAI**: *"What is Explainable AI?" — IBM Research Blog*
- **Multiprocessing**: *"GIL Python" — realpython.com*

---

## 15. İleri Düzey Kavramsal Savunmalar (X10THINK)

### 1. Veri Bilimi Temelleri
- **Train/Test Split Neden Yapılmadı?** Bu proje bir *Proof of Concept (PoC)* çalışmasıdır. Amaç modelin devasa verilerle generalization (genelleme) yapmasından ziyade, mevcut uçtan uca mimarinin (Pipeline) çalıştığını kanıtlamaktır.
- **Dengesiz Veri (Class Imbalance - 200 Normal, 80 Anomali):** Gerçek dünyada anomali verisi (çökmeler) her zaman azınlıktadır. Modeli bilerek bu dengesizlikle eğittik ki gerçek hayatın dağılımını yansıtsın. Normal durumlara bias (eğilim) olması, gereksiz alarmları (False Positive) önler.

### 2. Güvenlik
- **API Authentication Eksikliği:** PoC aşamasında hızlı entegrasyon için JWT veya API Key eklenmedi. Üretim ortamında (Production) FastAPI `Depends(OAuth2)` ile kilitlenmelidir.
- **CORS `allow_origins=["*"]` Riski:** Sadece yerel geliştirme (localhost) için eklendi. Üretimde sadece Dashboard'un yayınlandığı domain ismine izin verilir.
- **SQL Injection:** SQLite entegrasyonunda Python'un güvenli veri bağlama (parametrized queries) yöntemleri kullanıldığı için SQL Injection riski sıfırdır.

### 3. Testing ve Kalite
- **Kodu Nasıl Test Ettin?** `test_integration_week3.py` gibi uçtan uca (E2E) entegrasyon testleri yazdım. Özellikle YSA'nın RAM metriklerine verdiği tepkileri otomatik test eden modüller mevcut. `pytest` ile tüm kritik iş kuralları (Use Case'ler) test edilebilir durumda.

### 4. Deployment ve Canlıya Alma
- **Sistem Production'a Nasıl Taşınır?** Tüm bileşenler Dockerize edilir. `uvicorn` tek worker yerine `gunicorn` arkasında çoklu worker ile ayağa kaldırılarak eşzamanlı istek kapasitesi artırılır.

### 5. Monitoring Paradoksu
- **İzleme Sistemi Çökerse Ne Olur? (Who monitors the monitor?)** Şu an ajanlar doğrudan FastAPI'ye bağımlı. API çökerse ajanlar veriyi iletemez. Gelecek vizyonunda ajanların verileri API yerine doğrudan bir **Message Broker'a (Kafka)** atması, böylece API çökse bile verilerin kaybolmaması sağlanmalıdır.

### 6. Matematiksel Temeller
- **Backpropagation ve Chain Rule:** Hatanın (Loss) çıkış katmanından giriş katmanına doğru türevler çarpımı (Zincir Kuralı) ile geriye yayılmasıdır. Modelin "öğrenmesi" matematiksel olarak budur.
- **Learning Rate (0.001):** Optimizasyon adımlarının büyüklüğüdür. Çok büyük olursa hedefi ıskalar (diverge), çok küçük olursa eğitilmesi günler sürer. 0.001 literatürdeki en optimal başlangıç değeridir.

### 7. Proje Yönetimi
- **En Zor Kısım:** Birçok farklı teknolojiyi (PyTorch, LLM, FastAPI, SQLite, psutil) Clean Architecture prensiplerini bozmadan, spagetti koda çevirmeden birleştirmekti.
- **1 Ay Daha Zamanım Olsaydı:** Ajanlara otomatik güncelleme mekanizması, çoklu sunucu desteği için Docker Swarm ve gerçek bir n8n sunucusu entegre ederdim.

### 8. Domain Bilgisi (FinTech Etkisi)
- **Memory Leak Neden Kritik?** FinTech sistemleri 7/24 çalışmak zorundadır (SLA - Service Level Agreement). Sistemin çökmesi (Downtime) anlık borsa veya EFT işlemlerinin kesilmesi, dolayısıyla saniyede milyonlarca lira para kaybı ve itibar zedelenmesi demektir.

### 9. Teknolojik Karşılaştırmalar
- **Neden YSA vs Basit Threshold?** CPU > %90 ise alarm ver demek basittir ama "CPU %70, RAM %80, Disk I/O %90 iken bu üçlünün kombinasyonu tehlikeli mi?" sorusunu if-else ile yazamazsınız. YSA bu çok boyutlu ilişkileri yakalar.
- **Neden Ollama vs OpenAI API?** Finansal sunucu logları ve metrikleri **Kişisel veya Ticari Sır (Gizli Veri)** içerir. Bu verilerin internet üzerinden 3. parti bulut şirketlerine (OpenAI) gönderilmesi yasadışıdır. Bu yüzden %100 yerel çalışan Ollama zorunludur.

### 10. Edge Case'ler (Sınır Durumlar)
- **0.4999 vs 0.5001 Anomali Skoru:** Eşik 0.50 olduğu için biri normal, diğeri alarm kabul edilir. Bu tür sınır durumlarında False Positive riskini azaltmak için arka arkaya 3 kez 0.5 üzerinde değer gelmesi koşulu (Debounce) eklenebilir.
- **Timeout Durumları:** Gece 3'te Ollama çökerse sistem bekleyip kilitlenmez, 30 saniyelik timeout süresi dolar dolmaz **Statik Fallback** metnine geçer ve Telegram alarmı her halükarda ulaştırılır. İşleyiş asla durmaz.
