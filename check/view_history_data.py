import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from tabulate import tabulate   

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def view_chat_history(limit=20):
    """Xem lịch sử hỏi đáp trong bảng chat_history"""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, session_id, role, LEFT(content, 200) AS content_preview, timestamp 
            FROM chat_history 
            ORDER BY id DESC 
            LIMIT %s;
        """, (limit,))

        rows = cur.fetchall()
        if not rows:
            print("⚠️ Chưa có dữ liệu trong bảng chat_history.")
        else:
            print(tabulate(rows, headers="keys", tablefmt="fancy_grid", stralign="left"))
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Lỗi khi xem bảng chat_history: {e}")

if __name__ == "__main__":
    view_chat_history(15)  # In ra 15 dòng mới nhất
