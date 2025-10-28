from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional, Any
from datetime import datetime
# Import thư viện cần thiết cho việc chạy hàm đồng bộ (nếu chatbot là đồng bộ)
from starlette.concurrency import run_in_threadpool 

# ===============================
# Import Chatbot từ app.py
# ===============================
try:
    import app
    CHATBOT_AVAILABLE = True
except ImportError:
    app = None
    CHATBOT_AVAILABLE = False
    print("WARNING: Could not import 'app' module. Using mock response.")

# ===============================
# Import Google Sheet Setup
# ===============================
try:
    import gspread
    from google.oauth2.service_account import Credentials
    
    # Lấy đường dẫn đến credentials.json từ biến môi trường
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    
    # Phạm vi quyền truy cập Google Sheets
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    if GOOGLE_SERVICE_ACCOUNT_FILE and GOOGLE_SHEET_ID:
        credentials = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        gc = gspread.authorize(credentials)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1  # Sheet đầu tiên
        SHEET_AVAILABLE = True
    else:
        SHEET_AVAILABLE = False
        sheet = None
        print("WARNING: Google Sheet credentials not found. Sheet logging disabled.")
        
except ImportError:
    SHEET_AVAILABLE = False
    sheet = None
    print("WARNING: Could not import gspread. Google Sheet logging disabled.")

# --- Khai báo Model cho dữ liệu đầu vào ---
# FastAPI sử dụng Pydantic để định nghĩa cấu trúc dữ liệu
class Question(BaseModel):
    """Định nghĩa cấu trúc dữ liệu JSON đầu vào."""
    question: str
    phone: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None

# ---------------------------------------
# 1️⃣ Khởi tạo FastAPI App + bật CORS
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
    "*", # Cho phép tất cả domain gọi API này
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
# 2️⃣ Route kiểm tra hoạt động (GET /)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
    """Route kiểm tra xem API có hoạt động không."""
    return {
        "message": "✅ Chatbot Luật Lao động API đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_status": "Available" if CHATBOT_AVAILABLE else "Not Available",
        "sheet_status": "Available" if SHEET_AVAILABLE else "Not Available"
    }

# ---------------------------------------
# 3️⃣ Route chính: /chat (POST)
# ---------------------------------------
# Đã đổi từ /predict sang /chat để khớp với client
@app_fastapi.post("/chat", summary="Dự đoán/Trả lời câu hỏi từ Chatbot")
async def predict(data: Question):
    """
    Nhận câu hỏi và trả về câu trả lời từ mô hình chatbot.
    Nếu có số điện thoại, ghi thông tin vào Google Sheet.
    """
    question = data.question.strip()

    if not question:
        # FastAPI tự động validate JSON theo Pydantic, nhưng kiểm tra thêm trường hợp rỗng
        raise HTTPException(status_code=400, detail="Thiếu trường 'question' trong JSON hoặc câu hỏi bị rỗng.")

    try:
        answer = None
        
        # ✅ Gọi chatbot thực tế nếu có (Giả định app.py có chứa đối tượng chatbot)
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            session = "api_session" # ID session cố định cho API call
            
            # Kiểm tra xem app.chatbot.invoke có phải là hàm bất đồng bộ (coroutine) không
            if hasattr(app.chatbot.invoke, '__code__') and app.chatbot.invoke.__code__.co_flags & 0x80:
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
                 answer = f"Lỗi: Chatbot trả về định dạng không mong muốn: {repr(response)}"

        else:
            # Nếu chưa có chatbot thật hoặc import thất bại, trả về giả lập
            answer = f"(Chatbot mô phỏng - LỖI BACKEND: Không tìm thấy đối tượng app.chatbot) Bạn hỏi: '{question}'"

        # ✅ Nếu người dùng có nhập số điện thoại → ghi vào Google Sheet
        if data.phone and SHEET_AVAILABLE and sheet:
            try:
                time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Chạy trong threadpool vì gspread là đồng bộ
                await run_in_threadpool(
                    sheet.append_row,
                    [
                        question,
                        data.phone,
                        data.name or "",
                        time_now,
                        data.url or "",
                    ]
                )
                print(f"✅ Đã ghi thông tin vào Google Sheet: {data.phone}")
            except Exception as sheet_error:
                # Log lỗi nhưng vẫn trả về câu trả lời cho user
                print(f"⚠️ Lỗi ghi Google Sheet: {sheet_error}")

        return {"answer": answer}

    except Exception as e:

        print(f"LỖI CHATBOT: {e}")
        # Ghi log chi tiết (ví dụ: nếu do thiếu API key, lỗi sẽ nằm ở đây)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý Chatbot: {str(e)}. Vui lòng kiểm tra log backend của bạn.")


# ---------------------------------------
# 4️⃣ Khởi động server Uvicorn (FastAPI)
# ---------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, log_level="info", reload=True)


