#!/usr/bin/env python3
"""Freeze 1st-release Korean strings without EA source text or game fonts."""
from pathlib import Path
import json,hashlib,re
root=Path(__file__).resolve().parent.parent
p=root/"work/full-build/qa-v0.1.2/strings.json"
raw=json.loads(p.read_text(encoding="utf8"))
out=root/"translations/nfskr-first-release-v0.1.2.json"
if out.exists():raise FileExistsError(out)
mapping={}
for row in raw["entries"]:
    key=row["id"].upper()
    if not re.fullmatch("[0-9A-F]{8}",key) or key in mapping or not row["ko"]:
        raise ValueError("Malformed translated string")
    mapping[key]=row["ko"]
if len(mapping)!=8206:raise ValueError("Invalid first-release count")
payload={"schema":"nfskr-korean-strings-v1","version":"1.0.0-first-release",
         "source_qa":"v0.1.2","game_profile":"NFS16",
         "game_version":366510,
         "entries":[{"id":k,"ko":mapping[k]} for k in sorted(mapping,key=lambda n:int(n,16))]}
out.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf8")
hashval=hashlib.sha256(out.read_bytes()).hexdigest().upper()
print("NFSKR_FIRST_RELEASE_STRINGS_FROZEN",len(mapping),"SHA256",hashval,"BYTES",out.stat().st_size)
