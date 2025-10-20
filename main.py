from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from starlette.concurrency import run_in_threadpool
import sys
import logging
from contextlib import asynccontextmanager

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Biến global để lưu chatbot
chatbot_instance = None
app_module = None

# ---------------------------------------
# Lifespan Context Manager
# ---------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý lifecycle của ứng dụng (startup/shutdown)"""
    global chatbot_instance, app_module
    
    # STARTUP
    logger.info("🚀 FastAPI Server Starting...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"PORT: {os.environ.get('PORT', '10000')}")
    
    # Kiểm tra biến môi trường quan trọng
    required_env_vars = ["OPENAI__API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Thiếu biến môi trường: {', '.join(missing_vars)}")
        logger.error("⚠️ Chatbot sẽ không hoạt động đúng cách!")
    else:
        logger.info("✅ Tất cả biến môi trường cần thiết đã có")
    
    # Import và khởi tạo chatbot
    try:
        logger.info("📥 Đang import module app...")
        import app as app_module
        logger.info("✅ Import app module thành công")
        
        # Kiểm tra và load VectorDB
        if hasattr(app_module, 'load_vectordb'):
            logger.info("🔄 Đang load Pinecone VectorDB...")
            result = app_module.load_vectordb()
            
            if result is not None:
                logger.info("✅ VectorDB đã được load thành công")
                
                # Lấy thống kê
                if hasattr(app_module, 'get_vectordb_stats'):
                    stats = app_module.get_vectordb_stats()
                    logger.info(f"📊 Pinecone Index: {stats.get('name', 'N/A')}")
                    logger.info(f"📚 Total documents: {stats.get('total_documents', 0)}")
                    logger.info(f"📏 Dimension: {stats.get('dimension', 'N/A')}")
            else:
                logger.error("❌ Không thể load VectorDB từ Pinecone")
                logger.error("💡 Kiểm tra: PINECONE_API_KEY, PINECONE_INDEX_NAME, và Index có dữ liệu chưa")
        
        # Lấy chatbot instance
        if hasattr(app_module, 'chatbot'):
            chatbot_instance = app_module.chatbot
            logger.info("✅ Chatbot instance đã sẵn sàng")
        else:
            logger.error("❌ Không tìm thấy 'chatbot' trong module app")
            
    except ImportError as e:
        logger.error(f"❌ Không thể import module app: {e}")
        logger.error("⚠️ API sẽ chạy ở chế độ mock (không có chatbot thực)")
    except Exception as e:
        logger.error(f"❌ Lỗi khi khởi tạo chatbot: {e}", exc_info=True)
    
    logger.info("="*60)
    logger.info("✅ Server đã sẵn sàng nhận requests")
    logger.info("="*60)
    
    yield  # Server đang chạy
    
    # SHUTDOWN
    logger.info("🛑 Server đang shutdown...")

# ---------------------------------------
# Khởi tạo FastAPI App
# ---------------------------------------
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot tra cứu Luật Lao động & Khu công nghiệp Việt Nam",
    version="1.0.0",
    lifespan=lifespan
)

# ---------------------------------------
# Cấu hình CORS
# ---------------------------------------
origins = [
    "*",  # Cho phép tất cả domain (production nên giới hạn cụ thể)
]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# Pydantic Models
# ---------------------------------------
class Question(BaseModel):
    """Định nghĩa cấu trúc dữ liệu JSON đầu vào."""
    question: str

    class Config:
        json_schema_extra = {
            "example": {
                "question": "Luật lao động quy định thời gian làm việc như thế nào?"
            }
        }

# ---------------------------------------
# API Routes
# ---------------------------------------
@app_fastapi.get("/", summary="Root endpoint - API Info")
async def home():
    """Endpoint chính cung cấp thông tin về API"""
    return {
        "status": "healthy",
        "service": "Chatbot Luật Lao động API",
        "version": "1.0.0",
        "message": "✅ API đang hoạt động",
        "endpoints": {
            "chat": "POST /chat - Gửi câu hỏi cho chatbot",
            "health": "GET /health - Health check",
            "status": "GET /status - Kiểm tra trạng thái chatbot"
        },
        "chatbot_ready": chatbot_instance is not None
    }

@app_fastapi.get("/health", summary="Health check endpoint")
async def health_check():
    """
    Health check endpoint cho Render và các monitoring services.
    Trả về 200 OK nếu server đang chạy.
    """
    return {
        "status": "ok",
        "service": "chatbot-api",
        "healthy": True
    }

@app_fastapi.get("/status", summary="Kiểm tra trạng thái chi tiết")
async def status_check():
    """
    Kiểm tra trạng thái chi tiết của chatbot và VectorDB.
    """
    status_info = {
        "chatbot_loaded": chatbot_instance is not None,
        "app_module_loaded": app_module is not None,
        "environment": {
            "openai_key_set": bool(os.getenv("OPENAI__API_KEY")),
            "pinecone_key_set": bool(os.getenv("PINECONE_API_KEY")),
            "pinecone_index": os.getenv("PINECONE_INDEX_NAME", "Not set")
        }
    }
    
    # Lấy thông tin VectorDB nếu có
    if app_module and hasattr(app_module, 'get_vectordb_stats'):
        try:
            vectordb_stats = app_module.get_vectordb_stats()
            status_info["vectordb"] = vectordb_stats
        except Exception as e:
            status_info["vectordb"] = {"error": str(e)}
    
    return status_info

@app_fastapi.post("/chat", summary="Chat với Chatbot")
async def chat(data: Question):
    """
    Endpoint chính để chat với chatbot.
    
    Args:
        data: JSON object chứa câu hỏi
        
    Returns:
        JSON object chứa câu trả lời từ chatbot
        
    Raises:
        HTTPException: 400 nếu câu hỏi rỗng, 500 nếu có lỗi xử lý
    """
    question = data.question.strip()
    
    # Validate input
    if not question:
        raise HTTPException(
            status_code=400,
            detail="Câu hỏi không được để trống. Vui lòng nhập câu hỏi của bạn."
        )
    
    # Kiểm tra chatbot có sẵn sàng không
    if chatbot_instance is None:
        logger.error("Chatbot chưa được khởi tạo")
        raise HTTPException(
            status_code=503,
            detail="Chatbot chưa sẵn sàng. Vui lòng thử lại sau hoặc kiểm tra logs server."
        )
    
    try:
        logger.info(f"📩 Nhận câu hỏi: {question[:100]}...")
        
        # Session ID cho API (có thể customize theo user nếu cần)
        session_id = "api_session"
        
        # Gọi chatbot (chạy trong thread pool vì chatbot.invoke là sync)
        response = await run_in_threadpool(
            chatbot_instance.invoke,
            {"message": question},
            config={"configurable": {"session_id": session_id}}
        )
        
        # Xử lý response
        answer = None
        if isinstance(response, dict):
            # Nếu response là dict, tìm key 'output' hoặc 'answer'
            answer = response.get('output') or response.get('answer') or str(response)
        elif isinstance(response, str):
            answer = response
        else:
            answer = str(response)
        
        logger.info(f"✅ Trả lời thành công: {answer[:100]}...")
        
        return {
            "success": True,
            "answer": answer,
            "question": question
        }
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi xử lý chatbot: {e}", exc_info=True)
        
        # Log chi tiết để debug
        error_detail = str(e)
        
        # Kiểm tra các lỗi phổ biến
        if "API key" in error_detail or "authentication" in error_detail.lower():
            error_msg = "Lỗi xác thực API. Vui lòng kiểm tra OPENAI_API_KEY."
        elif "pinecone" in error_detail.lower():
            error_msg = "Lỗi kết nối Pinecone. Vui lòng kiểm tra PINECONE_API_KEY và Index."
        elif "rate limit" in error_detail.lower():
            error_msg = "Vượt quá giới hạn API. Vui lòng thử lại sau."
        else:
            error_msg = f"Lỗi xử lý câu hỏi: {error_detail}"
        
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )

# ---------------------------------------
# Run server (chỉ cho local development)
# ---------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Starting server on port {port}...")
    
    uvicorn.run(
        "main:app_fastapi",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )