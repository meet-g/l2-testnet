import sqlite3
import struct

def parse_proto_fields(b):
    pos = 0
    fields = []
    while pos < len(b):
        # read varint key
        key = 0
        shift = 0
        while pos < len(b):
            byte = b[pos]
            pos += 1
            key |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                break
            shift += 7
        field_num = key >> 3
        wire_type = key & 0x07
        
        if wire_type == 0: # varint
            val = 0
            shift = 0
            while pos < len(b):
                byte = b[pos]
                pos += 1
                val |= (byte & 0x7F) << shift
                if not (byte & 0x80):
                    break
                shift += 7
            fields.append((field_num, "varint", val))
        elif wire_type == 1: # 64-bit
            val = b[pos:pos+8]
            pos += 8
            fields.append((field_num, "fixed64", val))
        elif wire_type == 2: # length-delimited
            length = 0
            shift = 0
            while pos < len(b):
                byte = b[pos]
                pos += 1
                length |= (byte & 0x7F) << shift
                if not (byte & 0x80):
                    break
                shift += 7
            val = b[pos:pos+length]
            pos += length
            fields.append((field_num, "bytes", val))
        elif wire_type == 5: # 32-bit
            val = b[pos:pos+4]
            pos += 4
            fields.append((field_num, "fixed32", val))
        else:
            fields.append((field_num, "unknown_wire", wire_type))
            break
    return fields

db_path = "C:/Users/M/.gemini/antigravity-cli/conversations/6c2dc10f-9b2f-4d24-b442-4fc8103b9c09.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT idx, data FROM gen_metadata LIMIT 3")
for idx, data in cur.fetchall():
    print(f"=== idx {idx} (len {len(data)}) ===")
    parsed = parse_proto_fields(data)
    for fnum, ftype, fval in parsed:
        if ftype == "bytes":
            # try to see if it's string or sub-message
            try:
                s = fval.decode('utf-8')
                print(f"  Field {fnum} [bytes->str]: {s[:80]}")
            except:
                sub = parse_proto_fields(fval)
                print(f"  Field {fnum} [bytes->submessage ({len(sub)} fields)]: {sub[:5]}")
        else:
            print(f"  Field {fnum} [{ftype}]: {fval}")
