from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
# Import thư viện cần thiết cho việc chạy hàm đồng bộ (nếu chatbot là đồng bộ)
from starlette.concurrency import run_in_threadpool 

# --- 1. Import module Chatbot thực tế (app.py) ---
try:
    # Giả định module chứa logic chatbot được đặt tên là 'app' (app.py)
    import app 
except ImportError:
    # Nếu không tìm thấy app.py, gán app = None để tránh lỗi crash
    app = None
    print("⚠️ WARNING: Could not import 'app' module. Using mock response if actual chatbot is missing.")

# --- 2. Khai báo Model cho dữ liệu đầu vào ---
class Question(BaseModel):
    """Định nghĩa cấu trúc dữ liệu JSON đầu vào."""
    question: str

# ---------------------------------------
# 3. Khởi tạo FastAPI App + bật CORS
# ---------------------------------------
# Khởi tạo ứng dụng FastAPI
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0"
)

# 🔹 Cấu hình CORS Middleware
# Cho phép tất cả các domain (origins=["*"]) hoặc domain cụ thể.
origins = [
    "*", # Cho phép tất cả các domain gọi API này
    # "https://chatbotlaodong.vn", # Nếu bạn chỉ muốn cho phép domain cụ thể
]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# 4. Route kiểm tra hoạt động (GET /)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
    """Route kiểm tra xem API có hoạt động không."""
    return {
        "message": "✅ Chatbot Luật Lao động API đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_status": "✅ Đã tải logic chatbot (app.chatbot) thành công." if app and hasattr(app, "chatbot") else "❌ Lỗi: Không tìm thấy app.chatbot. Chỉ trả lời giả lập.",
    }

# ---------------------------------------
# 5. Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Dự đoán/Trả lời câu hỏi từ Chatbot")
async def predict(data: Question):
    """
    Nhận câu hỏi và trả về câu trả lời từ mô hình chatbot.
    """
    question = data.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Thiếu trường 'question' trong JSON hoặc câu hỏi bị rỗng.")

    # ❗ Đảm bảo app được import và có đối tượng chatbot
    if app and hasattr(app, "chatbot"):
        try:
            answer = None
            session = "api_session" # ID session cố định cho API call
            
            # Kiểm tra xem app.chatbot.invoke có phải là hàm bất đồng bộ (coroutine) không
            # co_flags & 0x80 là cách kiểm tra nhanh hàm async tại runtime
            if app.chatbot.invoke.__code__.co_flags & 0x80:
                # Nếu là async (bất đồng bộ), dùng await trực tiếp
                response = await app.chatbot.invoke(
                    {"message": question},
                    config={"configurable": {"session_id": session}}
                )
            else:
                # Nếu là sync (đồng bộ), chạy nó trong thread pool để không chặn server chính
                response = await run_in_threadpool(
                    app.chatbot.invoke,
                    {"message": question},
                    config={"configurable": {"session_id": session}}
                )
            
            # Xử lý kết quả trả về
            if isinstance(response, dict) and 'output' in response:
                answer = response['output']
            elif isinstance(response, str):
                answer = response
            else:
                # Trường hợp không phải dict có 'output' hoặc string
                answer = f"Lỗi: Chatbot trả về định dạng không mong muốn (Type: {type(response)}). Vui lòng kiểm tra logic của app.chatbot."
            
            return {"answer": answer}

        except Exception as e:
            print(f"LỖI XỬ LÝ CHATBOT: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Lỗi xử lý Chatbot: {str(e)}. Vui lòng kiểm tra log backend của bạn (ví dụ: thiếu API key, lỗi kết nối)."
            )
    else:
        # Xử lý trường hợp không tìm thấy chatbot
        answer = f"(Chatbot mô phỏng - LỖI BACKEND: Không tìm thấy đối tượng app.chatbot) Bạn hỏi: '{question}'"
        return {"answer": answer}


# ---------------------------------------
# 6. Khởi động server Uvicorn (FastAPI)
# ---------------------------------------
if __name__ == "__main__":
    # CHÚ Ý QUAN TRỌNG: 
    # Nếu file này được lưu tên là main.py, thì uvicorn.run("main:app_fastapi", ...) là chính xác.
    # Nếu file này được lưu tên là api.py, bạn phải đổi thành uvicorn.run("api:app_fastapi", ...)
    
    port = int(os.environ.get("PORT", 10000))
    # Dùng "0.0.0.0" để đảm bảo hoạt động tốt trên cả local và deployment
    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, log_level="info", reload=True)