import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

url = os.getenv("DATABASE_URL")
print("DATABASE_URL =", url)

try:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print("✅ Connected:", cur.fetchone())
    cur.close()
    conn.close()
except Exception as e:
    print("❌ Lỗi kết nối DB:", e)
