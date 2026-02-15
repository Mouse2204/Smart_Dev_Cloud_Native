# Smart Dev-Docs Platform - Hướng dẫn sử dụng

## 📋 Tổng quan

Hệ thống **Smart Dev-Docs Platform** là một nền tảng xử lý dữ liệu streaming kết hợp với AI, được triển khai trên Kubernetes (Minikube). Hệ thống bao gồm:

- **Kafka** (KRaft mode) - Tiếp nhận dữ liệu streaming
- **Spark Streaming** - Xử lý real-time và ghi vào Iceberg
- **Iceberg** + **Hive Metastore** - Lưu trữ dữ liệu dạng bảng với ACID
- **Ollama** - Tạo embeddings và suy luận với models AI
- **PostgreSQL** - Metadata store cho Hive

## 🚀 Bắt đầu nhanh

### 1. Triển khai hệ thống

```bash
# Áp dụng tất cả cấu hình
kubectl apply -f config/systems.yml

# Kiểm tra các pods đã chạy
kubectl get pods -A
```

### 2. Kiểm tra trạng thái các services

```bash
# Kiểm tra tất cả pods
kubectl get pods -A

# Xem logs của Spark Streaming
kubectl logs -f -n spark deployment/spark-streaming

# Kiểm tra Kafka topics
kubectl exec -n kafka-kraft kafka-0 -- kafka-topics --bootstrap-server localhost:9092 --list
```

## 📤 Gửi dữ liệu vào Kafka

### Tạo topic và gửi test data

```bash
# Tạo topic document-events
kubectl exec -n kafka-kraft kafka-0 -- kafka-topics \
  --bootstrap-server localhost:9092 \
  --create \
  --topic document-events \
  --partitions 1 \
  --replication-factor 1

# Gửi test messages
kubectl exec -n kafka-kraft -it kafka-0 -- kafka-console-producer \
  --bootstrap-server localhost:9092 \
  --topic document-events
```

Paste các messages sau (mỗi dòng một message):
```json
{"doc_id": "doc1", "chunk_id": "chunk1", "content": "Apache Iceberg is a high-performance format for huge analytic tables", "timestamp": 1771146503}
{"doc_id": "doc1", "chunk_id": "chunk2", "content": "Iceberg brings SQL reliability to data lakes", "timestamp": 1771146504}
{"doc_id": "doc2", "chunk_id": "chunk1", "content": "Spark Streaming processes real-time data from Kafka", "timestamp": 1771146505}
```

## 🔍 Kiểm tra dữ liệu trong Iceberg

### Cách 1: Đọc trực tiếp file Parquet

```bash
# Vào Spark Shell
kubectl exec -n spark -it deployment/spark-streaming -- /opt/spark/bin/spark-shell

# Trong Spark Shell, đọc file Parquet
spark.read.parquet("/opt/iceberg/warehouse/db/doc_chunks/data/*.parquet").show(false)

# Thoát
:quit
```

### Cách 2: Query qua Iceberg catalog

```bash
kubectl exec -n spark -it deployment/spark-streaming -- /opt/spark/bin/spark-sql \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0 \
  --conf spark.sql.catalog.hive_prod=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.hive_prod.type=hive \
  --conf spark.sql.catalog.hive_prod.uri=thrift://metastore-service.hive:9083 \
  --conf spark.sql.catalog.hive_prod.warehouse=/opt/iceberg/warehouse \
  -e "SELECT * FROM hive_prod.db.doc_chunks;"
```

## 🤖 Sử dụng Ollama AI

### Port-forward Ollama service

```bash
# Terminal 1
kubectl port-forward -n ollama svc/ollama-service 11434:11434
```

### Kiểm tra models đã được pull

```bash
curl http://localhost:11434/api/tags
```

Kết quả mong đợi:
```json
{
  "models": [
    {"name": "nomic-embed-text:latest", ...},
    {"name": "mistral:7b-instruct", ...}
  ]
}
```

### Tạo embeddings

```bash
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "Apache Iceberg is a table format for data lakes"
}'
```

### Chat với Mistral

```bash
# Non-streaming
curl http://localhost:11434/api/generate -d '{
  "model": "mistral:7b-instruct",
  "prompt": "What is Apache Iceberg?",
  "stream": false
}'

# Streaming (real-time response)
curl http://localhost:11434/api/generate -d '{
  "model": "mistral:7b-instruct",
  "prompt": "Explain Spark Streaming in 2 sentences"
}'
```

## 📊 Spark UI

```bash
# Port-forward Spark UI
kubectl port-forward -n spark spark-streaming-xxxxx 4040:4040
```

Mở browser: http://localhost:4040

## 🛠 Các lệnh hữu ích

### Xem logs

```bash
# Spark Streaming
kubectl logs -f -n spark deployment/spark-streaming

# Kafka
kubectl logs -f -n kafka-kraft kafka-0

# Ollama
kubectl logs -f -n ollama deployment/ollama

# Hive Metastore
kubectl logs -f -n hive deployment/metastore
```

### Exec vào containers

```bash
# Spark
kubectl exec -n spark -it deployment/spark-streaming -- /bin/bash

# Kafka
kubectl exec -n kafka-kraft -it kafka-0 -- /bin/bash

# Ollama
kubectl exec -n ollama -it deployment/ollama -- /bin/sh
```

### Xóa resources

```bash
# Xóa deployment cụ thể
kubectl delete deployment spark-streaming -n spark

# Xóa tất cả trong namespace
kubectl delete all --all -n spark

# Xóa toàn bộ hệ thống
kubectl delete -f config/systems.yml
```

## 📁 Cấu trúc dữ liệu

### Iceberg Warehouse
```
/opt/iceberg/warehouse/
├── db/
│   └── doc_chunks/
│       ├── data/          # File Parquet chứa dữ liệu
│       └── metadata/       # Metadata của Iceberg
```

### Kafka Topics
- `document-events` - Topic chính nhận dữ liệu documents

## 🔄 Data Flow

1. **Source** → Gửi JSON messages vào Kafka topic `document-events`
2. **Spark Streaming** đọc từ Kafka, parse JSON
3. **Spark** ghi vào Iceberg table `hive_prod.db.doc_chunks`
4. **Ollama** sẵn sàng để tạo embeddings hoặc chat
5. **Streamlit/API** (tùy chọn) truy vấn dữ liệu và sử dụng AI

## 🐛 Troubleshooting

### 1. Spark không tìm thấy spark-submit
```bash
# Dùng image apache/spark:3.5.7-python3
sed -i 's|.*image:.*|          image: apache/spark:3.5.7-python3|g' config/systems.yml
```

### 2. Lỗi Ivy cache
```bash
# Thêm env variables
env:
- name: IVY_CACHE_DIR
  value: /tmp/.ivy2
```

### 3. Ollama không pull được models
```bash
# Pull trực tiếp từ pod
kubectl exec -n ollama -it deployment/ollama -- ollama pull nomic-embed-text
kubectl exec -n ollama -it deployment/ollama -- ollama pull mistral:7b-instruct
```

### 4. Không kết nối được đến Kafka
```bash
# Kiểm tra service
kubectl get svc -n kafka-kraft
kubectl get endpoints -n kafka-kraft

# Test kết nối
kubectl run -n spark test-kafka --image=busybox:1.36 --rm -it --restart=Never -- sh -c "nc -zv kafka-service.kafka-kraft 9092"
```

## 📈 Monitoring

### Kiểm tra resource usage
```bash
kubectl top pods -A
kubectl top nodes
```

### Xem events
```bash
kubectl get events -A --sort-by='.lastTimestamp'
```

## 🎯 Kết luận

Hệ thống đã sẵn sàng để:
- ✅ Nhận dữ liệu streaming qua Kafka
- ✅ Xử lý real-time với Spark
- ✅ Lưu trữ ACID với Iceberg
- ✅ Tạo embeddings và chat với Ollama

**Chúc bạn thành công!** 🚀
