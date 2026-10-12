import sys, os
sys.path.insert(0, os.path.abspath("."))
import sqlite3
from scratch.parse_proto import parse_proto_fields

db_path = "C:/Users/M/.gemini/antigravity-cli/conversations/6c2dc10f-9b2f-4d24-b442-4fc8103b9c09.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT idx, data FROM gen_metadata LIMIT 5")
for idx, data in cur.fetchall():
    print(f"=== Record {idx} ===")
    top_fields = parse_proto_fields(data)
    for tf_num, tf_type, tf_val in top_fields:
        if tf_num == 1 and tf_type == "bytes":
            f1_sub = parse_proto_fields(tf_val)
            for f_num, f_type, f_val in f1_sub:
                if f_type == "bytes":
                    sub = parse_proto_fields(f_val)
                    print(f"  F1.{f_num} [bytes len {len(f_val)}]:")
                    for sf_num, sf_type, sf_val in sub:
                        if sf_type == "bytes":
                            try:
                                print(f"    .{sf_num}: {sf_val.decode('utf-8')[:60]}")
                            except:
                                print(f"    .{sf_num} [raw bytes len {len(sf_val)}]: {repr(sf_val)[:40]}")
                        else:
                            print(f"    .{sf_num} [{sf_type}]: {sf_val}")
                else:
                    print(f"  F1.{f_num} [{f_type}]: {f_val}")
