import sqlite3, os

p = r"G:/My Drive/AI Projects/AI-QnA-App2/data/crmB.db"
print("Exists:", os.path.exists(p))

try:
    sqlite3.connect(p).close()
    print("✅ SQLite opened it OK")
except Exception as e:
    print("❌", e)
