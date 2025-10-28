from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import uvicorn
from datetime import datetime
from starlette.concurrency import run_in_threadpool

# ===============================
# 1️⃣ Google Sheet Setup
# ===============================
import gspread
from google.oauth2.service_account import Credentials

# Lấy đường dẫn đến credentials.json từ biến môi trường
GOOGLE_SERVICE_ACCOUNT_FILE = r"./laoslanguage-0ff33088fe81.json"
GOOGLE_SHEET_ID = "11uz6CmRLKO1yL1dHCMBcQtpl_lbtgM8BEf2ycJRS-UA"

# Phạm vi quyền truy cập Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_file(
    GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1  # Sheet đầu tiên

# ===============================
# 2️⃣ Khai báo cấu trúc dữ liệu
# ===============================
class Question(BaseModel):
    question: str
    phone: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None

# ===============================
# 3️⃣ Cấu hình FastAPI
# ===============================
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0",
)

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hoặc domain cụ thể
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# 4️⃣ Route kiểm tra hoạt động
# ===============================
@app_fastapi.get("/")
async def home():
    return {"message": "✅ Chatbot Luật Lao động API đang hoạt động."}

# ===============================
# 5️⃣ Route /chat
# ===============================
@app_fastapi.post("/chat")
async def predict(data: Question):
    question = data.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")

    try:
        # ✅ Trả lời mặc định nếu không có trong lĩnh vực
        answer = "Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ."

        # ✅ Nếu người dùng có nhập số điện thoại → ghi vào Google Sheet
        if data.phone:
            time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([
                data.question,
                data.phone,
                data.name or "",
                time_now,
                data.url or "",
            ])

        return {"answer": answer}

    except Exception as e:
        print(f"Lỗi xử lý chatbot: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi: {str(e)}")

# ===============================
# 6️⃣ Chạy server local
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, reload=True)
