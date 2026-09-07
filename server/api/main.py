"""
server/api/main.py

API Katmanı — FastAPI Uygulaması
================================
Gelen istekleri (HTTP) alır, Use Case'lere iletir ve HTTP
yanıtlarına çevirir.

İş Akışı (Pipeline):
  1. Ajan (chaos.py/monitor.py) metrik toplar ve POST /api/v1/metrics'e gönderir
  2. main.py gelen veriyi doğrular (Exception Handlers)
  3. Veriler SaveMetricUseCase üzerinden SQLite'a yazılır
  4. GET /api/v1/predictions çağrıldığında YSA modeli tahminde bulunur
  5. Sonuçlar JSON olarak Streamlit Dashboard'a sunulur
"""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
# Exception handler'larda isteğin detaylarina erismek icin parametre olarak alinir.


from fastapi.middleware.cors import CORSMiddleware   

from fastapi.responses import JSONResponse  
# HTTP yanıtini JSON formatinda döndürmek icin kullanilan özel yaniit sinifi.
#   Normalde FastAPI otomatik JSON döner, ama exception_handler içinde kendi status_code ve
#   content'imizi belirlemek istediğimizde JSONResponse'u elle oluşturuyoruz.
#   Örn: return JSONResponse(status_code=400, content={"error": "Geçersiz veri"})

from server.api.decorators import log_execution_time

from typing import Dict, Any

from server.infrastructure.database import get_db

from server.infrastructure.sqlite_metric_repository import SQLiteMetricRepository
# ─ SQLiteMetricRepository : Metrik verilerini(metric gpu85%) SQLite veritabanına kaydeden/okuyan somut sınıf.
#   Repository Pattern(veriyi kaydeder nasil kaydettigini bilmez) 'in SQLite için yazılmış implementasyonu. INSERT, SELECT gibi SQL işlerini yapar.

from server.usecases.save_metric import SaveMetricUseCase
# ─ SaveMetricUseCase : "Metrik Kaydet" iş kuralı motoru. Gelen veriyi doğrular (validation),
#   domain entity(Identity ve iş kurallarını (davranışlarını) barındıran nesnedir.)'sine çevirir ve repository aracılığıyla veritabanına kaydeder.

from server.usecases.get_latest_metrics import GetLatestMetricsUseCase

from server.domain.exceptions import InvalidMetricError, RepositoryError
#projenin başka bir dosyasında (server/domain/exceptions.py
# InvalidMetricError : Gelen metrik verisi geçersiz olduğunda fırlatılan özel hata sınıfı (400 Bad Request).
#   Örn: CPU yüzdesi negatif gelirse veya agent_id(Bu metrik HANGİ bilgisayardan/sunucudan geldi) boşsa bu hata fırlatılır.
# RepositoryError : Veritabanı işlemlerinde bir sorun olduğunda fırlatılan hata sınıfı (500 Internal Error).
#   Örn: SQLite dosyası kilitliyse veya disk doluysa bu hata fırlatılır.

#Bu veritabanındaki kaçıncı kayıt=metric_id

executor = ProcessPoolExecutor(max_workers=2)

# FastAPI uygulamasını oluştur
app = FastAPI(
    title="AI Chaos Platform API",
    description="Agent metriklerini toplayan ve analiz eden platform.",
    version="1.0.0",
)

@app.on_event("shutdown")
def shutdown_event():
    executor.shutdown(wait=False)

# CORS (Cross-Origin Resource Sharing) Ayarları
# Dashboard'un bu API ile konuşabilmesi için (farklı portlarda çalışacaklar)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Geliştirme aşamasında her yerden gelen isteklere izin veriyoruz
    allow_credentials=True, #İsteklerle birlikte çerezlerin (cookies), oturum ve kimlik doğrulama (credentials) bilgilerinin iletilmesine onay verir.
    allow_methods=["*"], # İzin verilen HTTP metotları (GET, POST, PUT, DELETE, vb.).
    allow_headers=["*"], # İzin verilen HTTP header'ları.
)

# ── Hata Yakalayıcılar (Exception Handlers) ─────────────
# Use Case'lerin fırlattığı domain/repo hatalarını HTTP cevaplarına çeviririz.
#because of this, the client gets a understandable error message.
# Bu exception handler'lar, "InvalidMetricError" ve "RepositoryError" isimli özel hata türlerini yakalar 
# ve bunlara özel HTTP yanıtları döner.  

@app.exception_handler(InvalidMetricError)# InvalidMetricError fırlatırsa (raise ederse), sakın uygulamayı çökertme ve standart hata ekranı gösterme!
#(@app.exception_handler)=> hatayı YAKALA ve dashboard'un beklediği  JSON formatına ({"success": False, ...}) çevirerek geri gonder
async def invalid_metric_exception_handler(request: Request, exc: InvalidMetricError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "error_message": str(exc)},
    )

@app.exception_handler(RepositoryError)
async def repository_exception_handler(request: Request, exc: RepositoryError):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error_message": "Veritabanı hatası oluştu."},
    )

# ── Dependency Injection  ─────
# Gerçek dünyada bu kısım için 'Depends' yapısı kullanılabilir,
# şimdilik global oluşturup endpoints içinde kullanıyoruz.


db_manager = get_db()#Veritabanı ile fiziki bağlantıyı kuran en alt seviyedeki aracı (db_manager) çağırır.              
metric_repo = SQLiteMetricRepository(db_manager) #Bu, depoyu (repository) oluşturur. Depo, verilerin kalıcı olarak nerede (bu durumda SQLite) tutulacağını bilen yerdir.

save_metric_uc = SaveMetricUseCase(metric_repo)#(Use Case).
get_latest_metrics_uc = GetLatestMetricsUseCase(metric_repo)

#Global Scope riskleri:veritabanı bağlantısı koparsa, o global nesne bozuk kalır ve API'ye gelen tüm istekler hata vermeye başlar
#Bu değişkenler hiçbir def (fonksiyon) veya class içine yazılmamış.
#Dosyanın en dış seviyesine, yazılmış. buna Global Scope (Evrensel Kapsam) denir.
#Bunun anlamı şudur: FastAPI sunucusu (Uvicorn) çalışmaya başladığı ilk saniye bu 4 nesne sadece 1 kez oluşturulur ve hafızaya (RAM) kazınır. 
#Sunucu açık kaldığı sürece hep oradadırlar.

# ── Rotalar (Endpoints) ─────────────────────────────────

def process_metric_task(payload: Dict[str, Any]):
    """Arka planda metriği işler."""
    try:
        save_metric_uc.execute(payload)
    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] Metrik kaydedilemedi: {e}")

@app.post("/api/v1/metrics", status_code=202)
@log_execution_time
async def create_metric(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    background_tasks.add_task(process_metric_task, payload)
    return {"success": True, "message": "Metrik işleme kuyruğuna eklendi"}

@app.get("/api/v1/metrics/latest")
@log_execution_time
async def get_latest_metrics(limit: int = 50):#limit:kaç tane kayit istersin
    metrics = get_latest_metrics_uc.execute(limit=limit)
    
    # Domain entity=metric ozellikleri'lerini dict'e çevir.Metric bir Entity(Kendi Kimliği (ID'si) Olan Nesnelerdir)dir
    #Her bir metrik kaydının kendine has bir metric_id'si vardır.
    return {
        "success": True,
        "count": len(metrics),
        "data": [
            {
                "metric_id": m.metric_id,
                "agent_id": m.agent_id,
                "cpu_percent": m.cpu_percent,
                "ram_percent": m.ram_percent,
                "ram_used_gb": m.ram_used_gb,
                "ram_total_gb": m.ram_total_gb,
                "timestamp": m.timestamp.isoformat()
            }
            for m in metrics
        ]
    }

@app.get("/api/v1/predictions")
async def get_predictions(limit: int = 50):
    metrics = get_latest_metrics_uc.execute(limit=limit)
    if not metrics:
        return {"success": True, "count": 0, "predictions": []}
    
    try:
        import os
        from ai.neural_network import AnomalyTrainer
        import numpy as np
        
        # Proje kök dizinindeki modeli bul
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(os.path.dirname(current_dir))
        model_path = os.path.join(root_dir, "ai", "anomaly_model.pth")
        
        trainer = AnomalyTrainer(input_size=4, hidden_sizes=[64, 32, 16])
        trainer.load_model(model_path)
        
        # Tahmin için özellikleri çıkar (CPU, RAM, Disk, Net)
        # Metrik tablosunda disk ve net olmadığından şimdilik rastgele/sabit değer gönderebiliriz
        features = []
        for m in metrics:
            cpu = m.cpu_percent
            ram = m.ram_percent
            disk = 20.0 # dummy
            net = 10.0 # dummy
            features.append([cpu, ram, disk, net])
            
        features_np = np.array(features, dtype=np.float32)
        results = trainer.classify(features_np)
        
        predictions = []
        for i, m in enumerate(metrics):
            predictions.append({
                "metric_id": m.metric_id,
                "agent_id": m.agent_id,
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "ram_percent": m.ram_percent,
                "anomaly_score": results[i]["anomaly_score"],
                "is_anomaly": results[i]["is_anomaly"],
                "risk_level": results[i]["risk_level"],
                "label": results[i]["label"]
            })
            
        return {
            "success": True,
            "count": len(predictions),
            "predictions": predictions
        }
    except FileNotFoundError:
         return JSONResponse(
            status_code=404,
            content={"success": False, "error_message": "Model dosyası (anomaly_model.pth) bulunamadı. Lütfen önce modeli eğitin."}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_message": f"Model hatası: {str(e)}"}
        )

def train_model_process():
    import sys
    import os
    from pathlib import Path
    
    # Proje kök dizinini ekle
    current_dir = os.path.dirname(os.path.abspath(__file__))#__file__ bulunduğumuz dosyanın adıdır.dirname=ana dizindir.   
    root_dir = os.path.dirname(os.path.dirname(current_dir))#root_dir , projenin kök dizinidir.
    if root_dir not in sys.path:
        sys.path.append(root_dir)
        
    try:
        from ai.train import main as train_main
        train_main()
    except Exception as e:
        print(f"[TRAIN ERROR] {e}")

@app.post("/api/v1/train")
async def train_model_endpoint():
    """
    YSA Model Eğitimi (CPU-bound) için ProcessPoolExecutor kullanır. (Gün 20)
    """
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(
        loop.run_in_executor(executor, train_model_process)
    )
    return {"success": True, "status": "training started"}

@app.get("/")#Uygulamanın “sağlık durumu” nu kontrol etmek için kullanılan temel bir GET endpoint’idir.  
# / (root) URL'ine bir istek geldiğinde (örneğin tarayıcıya http://localhost:8000/ yazıldığında) çalışır   
async def root():
    return {"message": "AI Chaos Platform API çalışıyor. /docs adresinden Swagger arayüzüne ulaşabilirsiniz."}
