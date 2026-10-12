import sys, os, glob, sqlite3
sys.path.insert(0, os.path.abspath("."))
from scratch.parse_proto import parse_proto_fields

def get_summaries_map():
    db_path = "C:/Users/M/.gemini/antigravity-cli/conversation_summaries.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT conversation_id, title, preview, last_modified_time, step_count, workspace_uris FROM conversation_summaries")
    res = {}
    for cid, title, prev, lmt, sc, ws in cur.fetchall():
        res[cid] = {
            "title": title or prev or "Untitled",
            "last_modified": lmt[:19] if lmt else "",
            "step_count": sc,
            "workspace": ws
        }
    return res

def analyze_conversation_tokens(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata'")
    if not cur.fetchone():
        return None
    cur.execute("SELECT idx, data FROM gen_metadata")
    rows = cur.fetchall()
    
    total_prompt = 0
    total_output = 0
    total_cached = 0
    calls_count = 0
    model_counts = {}
    
    for idx, data in rows:
        top_fields = parse_proto_fields(data)
        for tf_num, tf_type, tf_val in top_fields:
            if tf_num == 1 and tf_type == "bytes":
                f1_sub = parse_proto_fields(tf_val)
                for f_num, f_type, f_val in f1_sub:
                    if f_num == 4 and f_type == "bytes":
                        sub = parse_proto_fields(f_val)
                        d = dict((k, v) for k, t, v in sub)
                        prompt = d.get(2, 0)
                        output = d.get(3, 0)
                        cached = d.get(5, 0)
                        model = d.get(1, 0)
                        
                        total_prompt += prompt
                        total_output += output
                        total_cached += cached
                        calls_count += 1
                        model_counts[model] = model_counts.get(model, 0) + 1
                        
    return {
        "calls": calls_count,
        "prompt_tokens": total_prompt,
        "output_tokens": total_output,
        "cached_tokens": total_cached,
        "models": model_counts
    }

summaries = get_summaries_map()
dbs = glob.glob("C:/Users/M/.gemini/antigravity-cli/conversations/*.db")

results = []
grand_calls = 0
grand_prompt = 0
grand_output = 0
grand_cached = 0

for db in dbs:
    cid = os.path.basename(db).replace(".db", "")
    data = analyze_conversation_tokens(db)
    if not data or data["calls"] == 0:
        continue
    sm = summaries.get(cid, {})
    title = sm.get("title", "Active / Recent Session")
    lmt = sm.get("last_modified", "")
    
    grand_calls += data["calls"]
    grand_prompt += data["prompt_tokens"]
    grand_output += data["output_tokens"]
    grand_cached += data["cached_tokens"]
    
    tot = data["prompt_tokens"] + data["output_tokens"] + data["cached_tokens"]
    cache_rate = (data["cached_tokens"] / (data["prompt_tokens"] + data["cached_tokens"]) * 100.0) if (data["prompt_tokens"] + data["cached_tokens"]) > 0 else 0.0
    
    results.append({
        "cid": cid,
        "title": title,
        "last_modified": lmt,
        "calls": data["calls"],
        "prompt": data["prompt_tokens"],
        "output": data["output_tokens"],
        "cached": data["cached_tokens"],
        "total": tot,
        "cache_rate": cache_rate,
        "models": data["models"]
    })

results.sort(key=lambda x: x["last_modified"], reverse=True)

print("=" * 100)
print(f"ALL-TIME TOKEN USAGE SUMMARY (Total Sessions: {len(results)})")
print("=" * 100)
grand_total = grand_prompt + grand_output + grand_cached
grand_cache_rate = (grand_cached / (grand_prompt + grand_cached) * 100.0) if (grand_prompt + grand_cached) > 0 else 0.0
print(f"Total API Invocations (Turns): {grand_calls:,}")
print(f"Total Uncached Input Tokens:   {grand_prompt:,}")
print(f"Total Context Cached Tokens:   {grand_cached:,} ({grand_cache_rate:.1f}% cache hit efficiency)")
print(f"Total Output Tokens:           {grand_output:,}")
print(f"Grand Total Processed Tokens:  {grand_total:,}")
print("-" * 100)
print(f"{'Date':<20} | {'Title / Context':<35} | {'Turns':<6} | {'Prompt':<11} | {'Output':<9} | {'Cached':<12} | {'Total':<12}")
print("-" * 100)
for r in results:
    t_short = (r['title'][:32] + '...') if len(r['title']) > 32 else r['title']
    print(f"{r['last_modified']:<20} | {t_short:<35} | {r['calls']:<6} | {r['prompt']:<11,d} | {r['output']:<9,d} | {r['cached']:<12,d} | {r['total']:<12,d}")

all_models = {}
for r in results:
    for m, c in r["models"].items():
        all_models[m] = all_models.get(m, 0) + c
print("-" * 100)
print(f"Model Calls Distribution: {all_models}")
