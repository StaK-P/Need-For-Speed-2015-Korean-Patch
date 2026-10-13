#!/usr/bin/env python3
"""Compile editable Korean menu CSVs into a Frosty-ready localization diff.

CSV is the source of truth. Editing ko_text or status is immediately reflected
after rebuilding the local mod. An imported Excel CSV should remain UTF-8.
Game archives/entire source-text dumps stay under ignored work/.
"""
from __future__ import annotations
import argparse,csv,json,re,collections
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/"work/locale-extract/en-strings.csv"
CSV_DIR=ROOT/"translations/menu"
TARGET=ROOT/"work/menu-build/merged-strings.json"
SCOPES=("main","settings","garage","events","social","system")
FIELDNAMES=("string_id","scope","source_text","ko_text","status","notes")
APPLY={"초벌","검수완료"}
SKIP={"보류","원문유지"}
ALL=APPLY | SKIP
TOKEN=re.compile(r"\{(?:\d+|[A-Za-z_][\w]*)(?::[^{}\r\n]+)?\}|<(?:[\w/][^<>\r\n]*)>|%(?:\d+\$)?[-+#0 ]*(?:\d+)?(?:\.\d+)?[A-Za-z]|[\uE000-\uF8FF]")
HEXSID=re.compile(r"0[xX][0-9A-Fa-f]{8}\Z")

def inventory(path=SOURCE):
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=["string_id","source_text"]:raise ValueError("Original CSV has unexpected columns")
        return {"0x"+row["string_id"].upper():row["source_text"] for row in reader}

def compile_tables(directory=CSV_DIR,source=SOURCE,selected=SCOPES):
    source_strings=inventory(source)
    result=[]
    counts=collections.Counter()
    used=set()
    for scope in selected:
        path=directory/(scope+".csv")
        if not path.exists():raise FileNotFoundError(f"Translation table missing: {path}")
        with path.open(encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f)
            if reader.fieldnames!=list(FIELDNAMES):
                raise ValueError(f"{path} header mismatch. Expected {FIELDNAMES}, got {reader.fieldnames}")
            for lineno,row in enumerate(reader,2):
                if any(key is None for key in row):
                    raise ValueError(f"{path}:{lineno} contains too many CSV columns")
                sid=row["string_id"].strip()
                if not HEXSID.fullmatch(sid):raise ValueError(f"{path}:{lineno} invalid ID: {sid!r}; keep 0x plus 8 hex digits")
                sid="0x"+sid[2:].upper()
                if sid in used:raise ValueError(f"Duplicate string ID {sid}")
                used.add(sid)
                if row["scope"]!=scope:raise ValueError(f"{path}:{lineno} mismatched scope {row['scope']!r}")
                orig=source_strings.get(sid)
                if orig is None:raise ValueError(f"{path}:{lineno} missing game string ID {sid}")
                if orig!=row["source_text"]:
                    raise ValueError(f"{path}:{lineno} {sid} original English mismatch. Do not edit source_text; only ko_text.")
                status=row["status"].strip()
                if status not in ALL:raise ValueError(f"{path}:{lineno} {sid}: invalid status {status!r}; use 초벌 / 검수완료 / 보류 / 원문유지")
                counts[status]+=1
                if status in SKIP:
                    continue
                target=row["ko_text"]
                if not target or not target.strip():
                    raise ValueError(f"{path}:{lineno} {sid} is marked {status} but has empty ko_text")
                if "\x00" in target:raise ValueError(f"{sid}: zero byte in translation")
                if any(ord(ch)>0xffff for ch in target):raise ValueError(f"{sid}: non-BMP char unsupported by Frostbite localization")
                original_tokens=collections.Counter(TOKEN.findall(orig))
                translated_tokens=collections.Counter(TOKEN.findall(target))
                if original_tokens!=translated_tokens:
                    raise ValueError(f"{sid}: lost/added placeholder tokens {dict(original_tokens)} -> {dict(translated_tokens)}. Preserve exact curly-brace tags and special symbols")
                if target==orig:
                    counts["원문동일_자동제외"]+=1
                    continue
                result.append({"id":sid[2:],"expected_original":orig,"ko":target,"scope":scope,"status":status})
    result.sort(key=lambda item:item["id"])
    return result,counts

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--csv-dir",type=Path,default=CSV_DIR)
    parser.add_argument("--output",type=Path,default=TARGET)
    parser.add_argument("--scopes",nargs="+",choices=SCOPES,default=list(SCOPES))
    args=parser.parse_args()
    entries,counts=compile_tables(args.csv_dir,SOURCE,args.scopes)
    if not entries:raise RuntimeError("No translated menu strings were selected")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    payload={"version":"0.0.4-menu-csv","origin":"translations/menu/*.csv","scopes":args.scopes,"entries":entries}
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("MENU_CSV_VALIDATED",len(entries),"translated strings",dict(counts),"file",args.output)
    for scope in args.scopes:
        print("  SCOPE",scope,"entries",sum(row["scope"]==scope for row in entries))

if __name__=="__main__":
    main()
