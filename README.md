# Teams Chatbot Orchestrator

FastAPI orchestrator định tuyến yêu cầu tới các Dify agent. Toàn bộ ngữ cảnh hội
thoại được lưu bền vững trong MongoDB và bộ project chạy bằng Docker Compose.

## Thành phần

- `app`: FastAPI, web chat, router/composer dùng Qwen và các Dify adapter.
- `mongodb`: lưu một document cho mỗi `conversation_id`, gồm lịch sử chat,
  session riêng của từng bot và orchestration trace.
- `mongodb_data`: Docker named volume, giữ dữ liệu sau khi container restart.

## Chạy bằng Docker

1. Nếu chưa có `.env`, tạo từ file mẫu:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Điền `QWEN_BEARER` và các `DIFY_*_API_KEY` cần sử dụng. Với môi trường thật,
   đổi `MONGO_ROOT_USERNAME` và `MONGO_ROOT_PASSWORD`. App tự tạo connection
   string từ hai giá trị này; không cần nhập lại mật khẩu trong URI.

3. Build và chạy:

   ```powershell
   docker compose up --build -d
   ```

4. Mở `http://localhost:8000`. Kiểm tra trạng thái:

   ```powershell
   Invoke-RestMethod http://localhost:8000/health
   docker compose ps
   docker compose logs -f app
   ```

Kiểm tra riêng vòng ghi/đọc MongoDB (bản ghi test được tự động xóa):

```powershell
docker compose exec -T app python -m src.scripts.smoke_mongo
```

Tắt dịch vụ nhưng giữ dữ liệu:

```powershell
docker compose down
```

Chỉ dùng lệnh sau khi thực sự muốn xóa toàn bộ dữ liệu hội thoại:

```powershell
docker compose down --volumes
```

## Xem dữ liệu MongoDB

```powershell
docker compose exec mongodb mongosh `
  --username orchestrator `
  --password orchestrator-dev-password `
  --authenticationDatabase admin `
  orchestrator
```

Trong `mongosh`:

```javascript
db.conversations.find({}, { conversation_id: 1, updated_at: 1 })
```

## Chạy app ngoài Docker

Cần Python 3.10+ và một MongoDB đang hoạt động. Từ thư mục cha của thư mục
`src` này:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r src\requirements.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Thiết lập `MONGODB_URI` trong `src/.env` trỏ tới MongoDB tương ứng. Image Docker cố
định một Uvicorn worker để các lượt chat cùng `conversation_id` được tuần tự hóa
đúng thứ tự.
