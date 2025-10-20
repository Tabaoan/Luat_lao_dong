from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from starlette.concurrency import run_in_threadpool
import traceback
import asyncio

# --- 1. Import module Chatbot ---
try:
    import app 
except ImportError:
    app = None
    print("⚠️ WARNING: Could not import 'app' module.")

# --- 2. Model dữ liệu đầu vào ---
class Question(BaseModel):
    question: str

# --- 3. Khởi tạo FastAPI App + CORS ---
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0"
)

# CORS Middleware - Cấu hình chi tiết hơn
app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# --- 4. Route kiểm tra (GET /) ---
@app_fastapi.get("/", summary="Health Check")
async def home():
    return {
        "status": "online",
        "message": "✅ Chatbot API đang hoạt động",
        "chatbot_loaded": bool(app and hasattr(app, "chatbot"))
    }

# --- 5. Route /chat (POST) với xử lý lỗi tốt hơn ---
@app_fastapi.post("/chat", summary="Chat endpoint")
async def predict(data: Question):
    try:
        question = data.question.strip()
        
        if not question:
            raise HTTPException(
                status_code=400, 
                detail="Câu hỏi không được để trống"
            )

        # Kiểm tra chatbot có tồn tại không
        if not app or not hasattr(app, "chatbot"):
            raise HTTPException(
                status_code=503,
                detail="Chatbot chưa được khởi tạo. Vui lòng kiểm tra backend."
            )

        session = "api_session"
        
        try:
            # Kiểm tra async/sync và gọi chatbot
            if asyncio.iscoroutinefunction(app.chatbot.invoke):
                response = await app.chatbot.invoke(
                    {"message": question},
                    config={"configurable": {"session_id": session}}
                )
            else:
                response = await run_in_threadpool(
                    app.chatbot.invoke,
                    {"message": question},
                    {"configurable": {"session_id": session}}
                )
            
            # Xử lý response
            if isinstance(response, dict):
                answer = response.get('output') or response.get('answer') or str(response)
            elif isinstance(response, str):
                answer = response
            else:
                answer = str(response)
            
            return {"answer": answer, "status": "success"}

        except TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Chatbot phản hồi quá chậm. Vui lòng thử lại."
            )
        except ConnectionError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Lỗi kết nối với dịch vụ chatbot: {str(e)}"
            )
        except Exception as e:
            print(f"❌ LỖI CHATBOT: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Lỗi xử lý câu hỏi: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ LỖI KHÔNG MONG ĐỢI: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Lỗi hệ thống. Vui lòng liên hệ quản trị viên."
        )

# --- 6. Khởi động Uvicorn ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(
        "main:app_fastapi", 
        host="0.0.0.0", 
        port=port, 
        log_level="info",
        reload=True,
        timeout_keep_alive=30,
        limit_concurrency=100
    )