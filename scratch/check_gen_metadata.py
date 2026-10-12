import sqlite3

db_path = "C:/Users/M/.gemini/antigravity-cli/conversations/6c2dc10f-9b2f-4d24-b442-4fc8103b9c09.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM steps")
print("Steps count:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM gen_metadata")
print("gen_metadata count:", cur.fetchone()[0])

cur.execute("SELECT idx, data, size FROM gen_metadata LIMIT 5")
for r in cur.fetchall():
    print("idx:", r[0], "size:", r[2])
    print("data:", repr(r[1])[:200])

cur.execute("SELECT idx, metadata, step_payload FROM steps LIMIT 3")
for r in cur.fetchall():
    print("step idx:", r[0])
    print("metadata:", repr(r[1])[:200])
    print("payload:", repr(r[2])[:200])
