import sys, os, glob, sqlite3
sys.path.insert(0, os.path.abspath("."))
from scratch.parse_proto import parse_proto_fields

def analyze_conversation_tokens(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Check if gen_metadata table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata'")
    if not cur.fetchone():
        return None
        
    cur.execute("SELECT idx, data FROM gen_metadata")
    rows = cur.fetchall()
    
    total_prompt_tokens = 0
    total_candidates_tokens = 0
    total_cached_tokens = 0
    calls_count = 0
    
    records = []
    
    for idx, data in rows:
        top_fields = parse_proto_fields(data)
        for tf_num, tf_type, tf_val in top_fields:
            if tf_num == 1 and tf_type == "bytes":
                f1_sub = parse_proto_fields(tf_val)
                for f_num, f_type, f_val in f1_sub:
                    if f_num == 4 and f_type == "bytes":
                        sub = parse_proto_fields(f_val)
                        d = dict((k, v) for k, t, v in sub)
                        # field 2: prompt tokens
                        # field 3: output tokens
                        # field 5: cached tokens (if any)
                        prompt = d.get(2, 0)
                        output = d.get(3, 0)
                        cached = d.get(5, 0)
                        
                        total_prompt_tokens += prompt
                        total_candidates_tokens += output
                        total_cached_tokens += cached
                        calls_count += 1
                        records.append({
                            "idx": idx,
                            "prompt": prompt,
                            "output": output,
                            "cached": cached,
                            "model": d.get(1, 0)
                        })
    return {
        "calls": calls_count,
        "prompt_tokens": total_prompt_tokens,
        "output_tokens": total_candidates_tokens,
        "cached_tokens": total_cached_tokens,
        "total_tokens": total_prompt_tokens + total_candidates_tokens + total_cached_tokens,
        "records": records
    }

dbs = glob.glob("C:/Users/M/.gemini/antigravity-cli/conversations/*.db")
print(f"Found {len(dbs)} conversation databases.")
for db in sorted(dbs):
    cid = os.path.basename(db).replace(".db", "")
    res = analyze_conversation_tokens(db)
    if res and res["calls"] > 0:
        print(f"DB {cid[:8]}...: {res['calls']:3d} calls | Prompt: {res['prompt_tokens']:,} | Output: {res['output_tokens']:,} | Cached: {res['cached_tokens']:,} | Total: {res['total_tokens']:,}")
