import json
import glob
import os
import sqlite3

def inspect_transcript(path):
    print("=" * 60)
    print("Transcript:", path)
    with open(path, "r", encoding="utf-8") as f:
        for i in range(10):
            line = f.readline()
            if not line: break
            d = json.loads(line)
            print(f"Line {i}: keys={list(d.keys())}")
            # check any key that looks like token, usage, stats, etc
            for k, v in d.items():
                if any(x in k.lower() for x in ["token", "usage", "cost", "model", "meta"]):
                    print(f"  {k} ({type(v)}): {str(v)[:150]}")

current_t = "C:/Users/M/.gemini/antigravity-cli/brain/6c2dc10f-9b2f-4d24-b442-4fc8103b9c09/.system_generated/logs/transcript.jsonl"
if os.path.exists(current_t):
    inspect_transcript(current_t)
