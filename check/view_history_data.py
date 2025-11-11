import os
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# tabulate là tùy chọn: nếu lỗi, sẽ in dữ liệu dạng thô
try:
    from tabulate import tabulate
    HAS_TABULATE = True
except Exception as e:
    print("⚠️ Không thể import tabulate, sẽ in dạng thô:", e)
    HAS_TABULATE = False

# ===== LOAD .ENV (tìm .env ở thư mục hiện tại hoặc thư mục cha) =====
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

def view_chat_history(limit=20, session_id=None):
    """Xem lịch sử hỏi đáp trong bảng chat_history (schema mới)."""
    if not DATABASE_URL:
        print("❌ Không tìm thấy DATABASE_URL trong môi trường. Kiểm tra file .env.")
        return

    try:
        # 1) Kết nối: KHÔNG truyền cursor_factory ở đây để tránh lỗi kỳ quặc
        # Nếu Render yêu cầu SSL bắt buộc, mở comment dòng dưới:
        # conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        conn = psycopg2.connect(DATABASE_URL)
        print("✅ Đã kết nối DB")

        # 2) Tạo cursor với RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        print("✅ Đã tạo cursor (RealDictCursor)")

        # 3) Xây SQL theo schema mới
        sql = """
            SELECT 
                id,
                COALESCE(user_id, 'N/A')     AS user_id,
                COALESCE(session_id, 'N/A')  AS session_id,
                COALESCE(user_ip, 'N/A')     AS user_ip,
                COALESCE(device_info, 'N/A') AS device_info,
                LEFT(question, 120)          AS question_preview,
                LEFT(answer, 120)            AS answer_preview,
                TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS time
            FROM chat_history
        """
        params = []
        if session_id:
            sql += " WHERE session_id = %s"
            params.append(session_id)
        sql += " ORDER BY id DESC LIMIT %s"
        params.append(limit)

        # 4) Thực thi
        cur.execute(sql, params)
        print("✅ Đã thực thi truy vấn")

        rows = cur.fetchall()
        print(f"✅ Đã lấy {len(rows)} dòng")

        cur.close()
        conn.close()

        if not rows:
            print("⚠️ Chưa có dữ liệu trong bảng chat_history.")
            return

        # Đưa về list[dict] “thuần” (tránh các vấn đề tương thích thư viện)
        data = [dict(r) for r in rows]

        print("\n📜 LỊCH SỬ CHATBOT GẦN NHẤT")
        if HAS_TABULATE:
            # Một số bản tabulate cũ không hỗ trợ maxcolwidths — nếu lỗi sẽ fallback
            try:
                print(tabulate(
                    data,
                    headers="keys",
                    tablefmt="fancy_grid",
                    stralign="left"
                ))
            except Exception as e:
                print(f"⚠️ Tabulate gặp lỗi ({e}), in dạng thô:")
                for row in data:
                    print(row)
        else:
            for row in data:
                print(row)

    except Exception as e:
        # In stacktrace để nhìn đúng dòng lỗi khi còn trục trặc môi trường
        import traceback
        print("❌ Lỗi khi xem bảng chat_history:", repr(e))
        traceback.print_exc()

if __name__ == "__main__":
    print(f"🔍 DATABASE_URL = {DATABASE_URL}")
    view_chat_history(15)
