from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional, Any
from starlette.concurrency import run_in_threadpool
import sys
import logging

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import chatbot module
try:
    import app
    logger.info("✅ Successfully imported 'app' module")
except ImportError as e:
    app = None
    logger.warning(f"⚠️ Could not import 'app' module: {e}")

# --- Khai báo Model cho dữ liệu đầu vào ---
class Question(BaseModel):
    """Định nghĩa cấu trúc dữ liệu JSON đầu vào."""
    question: str

# ---------------------------------------
# 1️⃣ Khởi tạo FastAPI App + bật CORS
# ---------------------------------------
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0"
)

# 🔹 Cấu hình CORS Middleware
origins = [
    "*",  # Cho phép tất cả domain gọi API này
]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# 2️⃣ Health Check Route (Quan trọng cho Render)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
    """Route kiểm tra xem API có hoạt động không."""
    return {
        "status": "healthy",
        "message": "✅ Chatbot Luật Lao động API đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_loaded": hasattr(app, "chatbot") if app else False
    }

@app_fastapi.get("/health", summary="Health check endpoint")
async def health_check():
    """Health check endpoint cho Render."""
    return {"status": "ok"}

# ---------------------------------------
# 3️⃣ Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Dự đoán/Trả lời câu hỏi từ Chatbot")
async def predict(data: Question):
    """
    Nhận câu hỏi và trả về câu trả lời từ mô hình chatbot.
    """
    question = data.question.strip()

    if not question:
        raise HTTPException(
            status_code=400, 
            detail="Thiếu trường 'question' trong JSON hoặc câu hỏi bị rỗng."
        )

    try:
        answer = None
        
        # ✅ Gọi chatbot thực tế nếu có
        if app and hasattr(app, "chatbot"):
            session = "api_session"
            
            # Kiểm tra xem có phải async function không
            import inspect
            if inspect.iscoroutinefunction(app.chatbot.invoke):
                # Nếu là async, dùng await
                response = await app.chatbot.invoke(
                    {"message": question},
                    config={"configurable": {"session_id": session}}
                )
            else:
                # Nếu là sync, chạy trong thread pool
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
                answer = str(response)
        else:
            # Nếu chưa có chatbot thật
            logger.warning("Chatbot not loaded, using mock response")
            answer = f"⚠️ Chatbot chưa được load. Bạn hỏi: '{question}'"

        return {"answer": answer}

    except Exception as e:
        logger.error(f"❌ Lỗi xử lý chatbot: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Lỗi xử lý Chatbot: {str(e)}"
        )

# ---------------------------------------
# 4️⃣ Startup Event (Log thông tin)
# ---------------------------------------
@app_fastapi.on_event("startup")
async def startup_event():
    """Log thông tin khi khởi động."""
    logger.info("🚀 FastAPI Server Starting...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Chatbot module loaded: {app is not None}")
    if app and hasattr(app, "chatbot"):
        logger.info("✅ Chatbot object found")
    else:
        logger.warning("⚠️ Chatbot object not found")

# ---------------------------------------
# 5️⃣ Khởi động server (chỉ cho local development)
# ---------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        "main:app_fastapi", 
        host="0.0.0.0", 
        port=port, 
        log_level="info"
    )