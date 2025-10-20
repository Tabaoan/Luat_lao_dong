from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional
from starlette.concurrency import run_in_threadpool
import logging

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import module chatbot
try:
    import app
    CHATBOT_AVAILABLE = hasattr(app, "chatbot")
    if CHATBOT_AVAILABLE:
        logger.info("✅ Module 'app' đã được import thành công")
    else:
        logger.warning("⚠️ Module 'app' không có object 'chatbot'")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    logger.error(f"❌ Không thể import module 'app': {e}")

# ============================================================
# PYDANTIC MODELS
# ============================================================
class Question(BaseModel):
    """Model cho request đầu vào"""
    question: str

class HealthResponse(BaseModel):
    """Model cho health check response"""
    status: str
    message: str
    chatbot_available: bool

class ChatResponse(BaseModel):
    """Model cho chat response"""
    answer: str

# ============================================================
# FASTAPI APP INITIALIZATION
# ============================================================
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho hệ thống chatbot tra cứu luật lao động và dân sự Việt Nam",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================================
# CORS MIDDLEWARE
# ============================================================
origins = [
    "*",  # Cho phép tất cả domains trong môi trường development
    # Trong production, nên chỉ định cụ thể:
    # "https://yourdomain.com",
    # "https://www.yourdomain.com",
]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# HELPER FUNCTIONS
# ============================================================
async def invoke_chatbot(question: str, session_id: str = "api_session") -> str:
    """
    Gọi chatbot và xử lý response
    
    Args:
        question: Câu hỏi từ người dùng
        session_id: ID của session (mặc định là "api_session")
    
    Returns:
        str: Câu trả lời từ chatbot
    """
    try:
        # Kiểm tra chatbot có khả dụng không
        if not CHATBOT_AVAILABLE:
            raise ValueError("Chatbot không khả dụng")
        
        # Chuẩn bị input cho chatbot
        chatbot_input = {"message": question}
        config = {"configurable": {"session_id": session_id}}
        
        # Kiểm tra xem invoke có phải là async function không
        import inspect
        if inspect.iscoroutinefunction(app.chatbot.invoke):
            # Nếu là async, gọi trực tiếp với await
            response = await app.chatbot.invoke(chatbot_input, config=config)
        else:
            # Nếu là sync, chạy trong threadpool
            response = await run_in_threadpool(
                app.chatbot.invoke,
                chatbot_input,
                config=config
            )
        
        # Xử lý response
        if isinstance(response, dict):
            if 'output' in response:
                return str(response['output'])
            elif 'answer' in response:
                return str(response['answer'])
            else:
                # Nếu response là dict nhưng không có key mong muốn
                return str(response.get('content', str(response)))
        elif isinstance(response, str):
            return response
        else:
            # Fallback cho các trường hợp khác
            return str(response)
            
    except Exception as e:
        logger.error(f"Lỗi khi gọi chatbot: {e}", exc_info=True)
        raise

# ============================================================
# API ROUTES
# ============================================================

@app_fastapi.get("/", response_model=HealthResponse)
async def root():
    """
    Health check endpoint
    
    Returns:
        HealthResponse: Trạng thái của API
    """
    return HealthResponse(
        status="online",
        message="✅ Chatbot Luật Lao động API đang hoạt động",
        chatbot_available=CHATBOT_AVAILABLE
    )

@app_fastapi.get("/health")
async def health_check():
    """
    Endpoint kiểm tra sức khỏe của service (cho deployment platforms)
    
    Returns:
        dict: Trạng thái chi tiết của service
    """
    return {
        "status": "healthy",
        "service": "Chatbot Luật Lao động API",
        "chatbot_available": CHATBOT_AVAILABLE,
        "version": "1.0.0"
    }

@app_fastapi.post("/chat", response_model=ChatResponse)
async def chat(data: Question):
    """
    Endpoint chính để chat với bot
    
    Args:
        data: Question object chứa câu hỏi từ người dùng
    
    Returns:
        ChatResponse: Câu trả lời từ chatbot
    
    Raises:
        HTTPException: 400 nếu câu hỏi rỗng, 500 nếu có lỗi server, 503 nếu chatbot không khả dụng
    """
    # Validate input
    question = data.question.strip()
    
    if not question:
        raise HTTPException(
            status_code=400,
            detail="Câu hỏi không được để trống"
        )
    
    # Kiểm tra chatbot có sẵn sàng không
    if not CHATBOT_AVAILABLE:
        logger.error("Chatbot không khả dụng")
        raise HTTPException(
            status_code=503,
            detail="Chatbot hiện không khả dụng. Vui lòng kiểm tra cấu hình server."
        )
    
    try:
        # Gọi chatbot
        logger.info(f"Nhận câu hỏi: {question[:100]}...")
        answer = await invoke_chatbot(question)
        logger.info(f"Trả lời thành công: {answer[:100]}...")
        
        return ChatResponse(answer=answer)
        
    except ValueError as ve:
        # Lỗi từ logic nghiệp vụ
        logger.error(f"Lỗi nghiệp vụ: {ve}")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi xử lý: {str(ve)}"
        )
    except Exception as e:
        # Lỗi không xác định
        logger.error(f"Lỗi không xác định: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi server: Không thể xử lý câu hỏi. Chi tiết: {str(e)}"
        )

# ============================================================
# STARTUP EVENT
# ============================================================
@app_fastapi.on_event("startup")
async def startup_event():
    """
    Event được gọi khi server khởi động
    """
    logger.info("=" * 60)
    logger.info("🚀 KHỞI ĐỘNG CHATBOT API")
    logger.info("=" * 60)
    logger.info(f"📋 Chatbot available: {CHATBOT_AVAILABLE}")
    
    if CHATBOT_AVAILABLE:
        logger.info("✅ Server sẵn sàng nhận request")
    else:
        logger.warning("⚠️ Server đang chạy nhưng chatbot KHÔNG khả dụng")
    
    logger.info("=" * 60)

# ============================================================
# MAIN ENTRY POINT (CHỈ CHO LOCAL DEVELOPMENT)
# ============================================================
if __name__ == "__main__":
    # Lấy port từ biến môi trường hoặc dùng 8000 làm mặc định
    port = int(os.environ.get("PORT", 8000))
    
    logger.info(f"🔧 Chạy ở chế độ development trên port {port}")
    
    # Chạy server với uvicorn
    uvicorn.run(
        "main:app_fastapi",
        host="0.0.0.0",
        port=port,
        reload=True,  # Auto-reload khi code thay đổi (chỉ dùng trong dev)
        log_level="info"
    )