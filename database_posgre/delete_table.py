import psycopg2
import os
from dotenv import load_dotenv

# Nạp biến môi trường từ .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def drop_chat_history_table():
    if not DATABASE_URL:
        print("❌ Thiếu DATABASE_URL trong .env")
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Xóa bảng chat_history (nếu có)
        cur.execute("DROP TABLE IF EXISTS chat_history CASCADE;")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Đã xóa bảng chat_history trong database Render thành công.")
        
    except Exception as e:
        print(f"❌ Lỗi khi xóa bảng: {e}")

if __name__ == "__main__":
    drop_chat_history_table()
