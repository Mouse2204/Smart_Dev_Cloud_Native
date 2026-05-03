# How To Run – Smart Dev Platform

---

## 1. Setup once

```powershell
# Tạo và kích hoạt virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Cài dependencies Python
python -m pip install -r requirements.txt
```

---

## 2. Khởi động Kubernetes (Minikube)

```powershell
minikube start
```

```powershell
kubectl apply -f config/systems.yml
```

Nếu hive metastore chưa pull thành công có thể sử dụng
```
minikube image pull alexcpn/hivemetastore:3.1.3.5
```
hoặc
```
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

docker pull alexcpn/hivemetastore:3.1.3.5
```
để xem tiến độ pull


### Theo dõi pods cho đến khi Running:
```powershell
kubectl get pods -A -w
```

---

## 4. Ingest PDF (chạy pipeline embedding)

Đặt file PDF vào `data/books/` rồi chạy:

```powershell
# Multimodal (dành cho các tài liệu chứa hình ảnh và biểu đồ) – mặc định
bash ./k8s/build.sh pipeline --source-dir data/books

# Các tài liệu chỉ chứa plain text (nhanh hơn)
bash ./k8s/build.sh pipeline --source-dir data/books --no-multimodal
```

Nếu PDF đã có trong MinIO:
```powershell
bash ./k8s/build.sh pipeline --skip-upload
```

---

## 5. Crawl & tóm tắt blog

```powershell
bash ./k8s/build.sh crawl
```

Lấy bài mới từ dev.to, InfoQ, Medium, The New Stack. Bài đã index sẽ bị bỏ qua.

---

## 6. Khởi động giao diện Streamlit

```powershell
bash ./k8s/build.sh ui
```

Mở **http://localhost:8501**:
- Tab **Document RAG** – Hỏi đáp tài liệu PDF
- Tab **Tech Blog Insights** – Đọc tóm tắt blog AI

---

## 7. Hỏi qua CLI

```powershell
bash ./k8s/build.sh ask "What is the main architecture described?"
```

Với Groq API:
```powershell
$env:GROQ_API_KEY="gsk_your_key"; bash ./k8s/build.sh ask "Summarize the PDF"
```

---

## 9. Các lệnh tiện ích

```powershell
bash ./k8s/build.sh inspect --limit 5   # kiểm tra chunks đã index trong Qdrant
bash ./k8s/build.sh help                 # xem tất cả lệnh
kubectl top pods -A                      # mức dùng tài nguyên
kubectl get events -A --sort-by='.lastTimestamp'  # sự kiện gần nhất
```

---

## 9. Automated Testing
Chạy bộ unit test để đảm bảo code ổn định:
```powershell
bash ./k8s/build.sh test
```

---
```powershell
# Xóa cluster cũ
minikube delete
```

---

## 10. Endpoints

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| MinIO API | http://localhost:9000 |
| MinIO Console | http://localhost:9001 |
| Qdrant | http://localhost:6333 |
| Ollama | http://localhost:11434 |
| Spark UI | http://localhost:4040 |

MinIO: `minioadmin` / `minioadmin123` · Grafana: `admin` / `admin`

---

## 11. Biến môi trường tuỳ chọn

```powershell
$env:USE_GROQ="false"                          # dùng Ollama thay Groq
$env:LLM_MODEL="llama-3.3-70b-versatile"      # model Groq
$env:LLM_GENERATE_TIMEOUT_SECONDS="60"
$env:QDRANT_BLOG_COLLECTION="dev_docs_blogs"
```

---

## 12. Debug & Kiểm tra hệ thống

### A. Test Kafka
**Gửi test data thủ công vào Kafka:**
```bash
kubectl exec -n kafka-kraft -it kafka-0 -- kafka-console-producer \
  --bootstrap-server localhost:9092 \
  --topic document-events

# Gõ các dòng JSON sau để test Spark Streaming:
{"doc_id": "doc1", "chunk_id": "c1", "content": "Iceberg reliability", "timestamp": 1771146503}
```

### B. Mở ống nhòm xem Iceberg Data Lake
**Cách 1: Spark SQL trực tiếp**
```bash
kubectl exec -n spark -it deployment/spark-streaming -- /opt/spark/bin/spark-sql \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0 \
  --conf spark.sql.catalog.hive_prod=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.hive_prod.type=hive \
  --conf spark.sql.catalog.hive_prod.uri=thrift://metastore-service.hive:9083 \
  --conf spark.sql.catalog.hive_prod.warehouse=/opt/iceberg/warehouse \
  -e "SELECT * FROM hive_prod.db.doc_chunks;"
```

**Cách 2: Xác minh file tồn tại ở ổ cứng**
```bash
kubectl exec -n spark deployment/spark-streaming -- ls -la /opt/iceberg/warehouse/db/doc_chunks/data/
```

### C. Khám phá Ollama API (Kiểm tra Sinh Vector & Chat)
Trong nhánh Terminal riêng, port-forward trước:
```bash
kubectl port-forward -n ollama svc/ollama-service 11434:11434
```
Sau đó test bằng cURL:
```bash
# 1. Test xem model đã có trong bộ nhớ chưa
curl http://localhost:11434/api/tags

# 2. Test chat thử
curl http://localhost:11434/api/generate -d '{
  "model": "mistral:7b-instruct",
  "prompt": "What is Apache Iceberg?",
  "stream": false
}'
```

---

## 13. Xử lý lỗi phổ biến

- **Ollama bị "đơ"**: Khi gọi curl hoặc API ở lượt đầu, có thể tốn 100-120s để ném Model 4GB vào RAM. Xem log để chắc chắn nó không chết: `kubectl logs -f -n ollama deployment/ollama`
- **Spark bị lỗi Ivy cache (`timeout hoặc permission`)**: Thường do mount folder. Có thể khắc phục bằng thiết lập `IVY_CACHE_DIR=/tmp/.ivy2` trên file cấu hình của Spark
- **Mất mạng ngầm từ Kafka**: Để test xem máy chủ ảo khác có ping được Kafka không, dùng lệnh:
  ```bash
  kubectl run -n spark test-kafka --image=busybox:1.36 --rm -it --restart=Never -- sh -c "nc -zv kafka-service.kafka-kraft 9092"
  ```
