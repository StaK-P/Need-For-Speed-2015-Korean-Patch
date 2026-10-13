#!/usr/bin/env python3
"""Compile user-approved FULL NFS2015 Korean localization CSVs for a PRIVATE QA FBMod.

All 10,250 IDs must be uniquely registered, and source text must match game
extraction exactly. Include only status 검수완료 where Korean actually differs.
Preserve timing markers, $ currency, in-game glyphs and formatting placeholders.
Do not distribute output with a local proprietary DIN composite font.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
import argparse,csv,json,re,hashlib
R=Path(__file__).resolve().parent.parent
MENU=R/"translations/menu"
CATEGORY=R/"translations/categories"
ORIGINAL=R/"work/locale-extract/en-strings.csv"
DEFAULT=R/"work/full-build/first-pass-all-strings.json"
REPORT=R/"work/full-build/COMPILER_AUDIT.json"
COLS=("string_id","scope","source_text","ko_text","status","notes")
ID=re.compile(r"0[xX][0-9a-fA-F]{8}\Z")
FORMATS=re.compile(r"\{(?:\d+|[A-Za-z_][A-Za-z_0-9]*)(?::[^{}\r\n]+)?\}|<[^<>\r\n]+>|%(?:\d+\$)?[-+#0]*(?:\d+)?(?:\.\d+)?[sduifxXeEgG]|[\ue000-\uf8ff]")
TIMED=re.compile(r"\{\d+(?:\.\d+)?-\d+(?:\.\d+)?\}")
def load(p):
 with p.open(encoding="utf-8-sig",newline="") as f:
  reader=csv.DictReader(f)
  if tuple(reader.fieldnames)!=COLS:raise ValueError("CSV schema mismatch "+str(p))
  return list(reader)
def diff(original: str,translated: str,scope: str,sid: str,warnings:list):
 if not translated.strip():raise ValueError("Empty confirmed Korean: "+sid)
 if "\x00" in translated:raise ValueError("NUL in localized string: "+sid)
 if any(ord(c)>0xffff for c in translated):raise ValueError("Non-BMP UCS2 char: "+sid)
 original_formats=Counter(FORMATS.findall(original))
 translation_formats=Counter(FORMATS.findall(translated))
 if original_formats!=translation_formats:
  raise ValueError(f"Preserved game markup differs {sid} {scope}: {dict(original_formats)} -> {dict(translation_formats)}")
 if TIMED.findall(original)!=TIMED.findall(translated):
  raise ValueError("Game timing markers changed "+sid)
 for symbol in ("$","™","®","©"):
  if original.count(symbol)!=translated.count(symbol):
   raise ValueError("Currency/trademark changed: "+sid+" symbol "+symbol)
 if original.count("\r")!=translated.count("\r"):
  raise ValueError("CR changed "+sid)
 if original.count("\n")!=translated.count("\n"):
  warnings.append({"id":sid,"scope":scope,"type":"NEWLINE_DIFFERENCE",
    "english_newlines":original.count("\n"),"korean_newlines":translated.count("\n")})
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--output",type=Path,default=DEFAULT)
 parser.add_argument("--report",type=Path,default=REPORT)
 args=parser.parse_args()
 with ORIGINAL.open(encoding="utf-8-sig",newline="") as f:
  english={"0x"+r["string_id"].upper():r["source_text"] for r in csv.DictReader(f)}
 if len(english)!=10250:raise ValueError("Source extraction is not full 10,250 IDs")
 inputs=[*sorted(MENU.glob("*.csv")),*sorted(CATEGORY.glob("*.csv"))]
 if len(inputs)!=24:raise ValueError("Expected 6 menus + 18 category tables, found "+str(len(inputs)))
 ids=set();c=Counter();changed=[];warnings=[];table_audit=[]
 for path in inputs:
  rows=load(path)
  file_count=Counter()
  for row in rows:
   sid=row["string_id"].strip().upper()
   if not ID.fullmatch(sid):
    raise ValueError("Bad game ID "+repr(row["string_id"])+" "+str(path))
   sid="0x"+sid[2:].upper()
   if sid in ids:raise ValueError("Duplicate ID across CSVs "+sid)
   ids.add(sid)
   original=english.get(sid)
   if original is None or original!=row["source_text"]:
    raise ValueError("Mismatch from extracted EN resource "+sid+" "+str(path))
   if row["scope"]!=path.stem:
    raise ValueError("Scope/file mismatch "+repr(row["scope"])+" "+str(path))
   status=row["status"].strip()
   if status not in ("검수완료","원문유지"):raise ValueError("Not final status "+sid+" "+repr(status))
   file_count[status]+=1;c[status]+=1
   if status=="원문유지":
    if row["ko_text"]!=original:raise ValueError("Supposed original-only data changed "+sid)
    continue
   target=row["ko_text"]
   diff(original,target,row["scope"],sid,warnings)
   if target!=original:
    changed.append({"id":sid[2:],"expected_original":original,"ko":target,
      "scope":row["scope"],"status":status})
   else:c["approved_same_original_skipped"]+=1
  table_audit.append({"file":str(path),"total":len(rows),"status":dict(file_count)})
 if ids!=set(english):
  raise ValueError("Full ID coverage broken; absent "+str(len(set(english)-ids))+" unknown "+str(len(ids-set(english))))
 assert len(ids)==10250
 assert c["검수완료"]==8239 and c["원문유지"]==2011
 changed.sort(key=lambda r:int(r["id"],16))
 assert len(changed)>7500 and len(changed)<=8239
 if any(change["id"].startswith("0X") for change in changed):raise AssertionError
 data={"version":"0.1.0-private-full-first-pass","origin":"translations/menu and categories including 10_story",
   "game":"NFS16 v366510","private_local_only":True,
   "entries":changed}
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
 analysis={
  "game":"NFS16","date":"2026-10-10","game_original_ids":len(ids),
  "confirmed_Korean_ids":c["검수완료"],"preserved_original_ids":c["원문유지"],
  "changed_localized_resources":len(changed),
  "confirmed_but_unchanged_excluded":c["approved_same_original_skipped"],
  "gameplay_layout_newline_warnings":len(warnings),
  "linebreak_examples":warnings[:150],
  "tables":table_audit,
  "private_local_only":True,"config_sha256":hashlib.sha256(args.output.read_bytes()).hexdigest().upper()
 }
 args.report.parent.mkdir(parents=True,exist_ok=True)
 args.report.write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
 print("ALL_NFS2015_TRANSLATION_CSV_COMPILED",json.dumps({k:v for k,v in analysis.items() if k not in ("tables","linebreak_examples")},ensure_ascii=True))
if __name__=="__main__":main()
