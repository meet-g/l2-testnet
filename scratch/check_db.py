import sqlite3
import glob
import os

def check_db(path):
    print("=" * 60)
    print("DB:", path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print("Tables:", tables)
    for t in tables:
        tname = t[0]
        cur.execute(f"PRAGMA table_info({tname})")
        cols = cur.fetchall()
        print(f"  Table {tname}:", [c[1] for c in cols])
        try:
            cur.execute(f"SELECT COUNT(*) FROM {tname}")
            cnt = cur.fetchone()[0]
            print(f"    Count: {cnt}")
            cur.execute(f"SELECT * FROM {tname} LIMIT 1")
            row = cur.fetchone()
            print(f"    Sample: {str(row)[:150]}")
        except Exception as e:
            print("    Error reading sample:", e)

check_db("C:/Users/M/.gemini/antigravity-cli/conversation_summaries.db")

dbs = glob.glob("C:/Users/M/.gemini/antigravity-cli/conversations/*.db")
if dbs:
    check_db(dbs[0])
