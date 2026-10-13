#!/usr/bin/env python3
"""Local-only diagnostic search over the extracted original NFS16 strings."""
import argparse,csv,re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser()
parser.add_argument("--mode", choices=("uppercase","contains","short","regex"),default="uppercase")
parser.add_argument("--pattern",default="")
parser.add_argument("--offset",type=int,default=0)
parser.add_argument("--limit",type=int,default=200)
parser.add_argument("--maxlen",type=int,default=0)
parser.add_argument("--single-line",action="store_true")
args=parser.parse_args()
with (root/"work/locale-extract/en-strings.csv").open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
results=[]
for r in rows:
 v=r["source_text"]
 if not v.strip():continue
 if args.mode=="uppercase":
  ok=len(v)<=100 and "\n" not in v and bool(re.search("[A-Za-z]",v)) and v.upper()==v
 elif args.mode=="short":ok=len(v)<=72 and "\n" not in v
 elif args.mode=="contains":ok=args.pattern.casefold() in v.casefold()
 else:ok=bool(re.search(args.pattern,v,re.I))
 if ok and args.maxlen and len(v)>args.maxlen:ok=False
 if ok and args.single_line and ("\n" in v or "\r" in v):ok=False
 if ok:results.append(r)
print("TOTAL",len(rows),"MATCHED",len(results),"DISPLAY",args.offset,args.offset+args.limit)
for r in results[args.offset:args.offset+args.limit]:
 print(r["string_id"],repr(r["source_text"][:220]))
