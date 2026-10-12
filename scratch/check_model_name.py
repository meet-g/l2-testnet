import sqlite3

conn = sqlite3.connect("C:/Users/M/.gemini/antigravity-cli/conversations/6c2dc10f-9b2f-4d24-b442-4fc8103b9c09.db")
cur = conn.cursor()
cur.execute("SELECT id, data FROM trajectory_metadata_blob")
for r in cur.fetchall():
    print("blob:", r[0], repr(r[1])[:300])

cur.execute("SELECT idx, step_payload FROM steps LIMIT 10")
for idx, pl in cur.fetchall():
    for word in [b"gemini", b"claude", b"gpt", b"model"]:
        if word in pl.lower():
            pos = pl.lower().find(word)
            print(f"step {idx} keyword {word}: {pl[max(0, pos-20):pos+60]}")
