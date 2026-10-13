#!/usr/bin/env python3
"""Lint project-wide NFS2015 Korean terminology across all editable CSVs.

Never automatically replaces Outlaw inside workshop/product names, hashtags,
dialogue or internal text IDs. General 'Outlaw' REP style category -> '무법',
human/persona -> '무법자', original brands/tags -> unchanged.
"""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
TERMS=ROOT/"translations/terminology.json"
TRANSLATIONS=ROOT/"translations"
SCORES={
 "0xBE4D8692":"무법 +{0:s} REP",
 "0x538F453D":"무법 {0:s}%",
 "0x4A080DF0":"{0:s} 무법 REP"
}
BAD=("아웃로","올드라이브")

def main():
 policy=json.loads(TERMS.read_text(encoding="utf-8"))
 if policy["game"]!="Need for Speed (2015)":
  raise ValueError("Wrong game terminology policy")
 categories={x["context"]:x["korean"] for x in policy["category_rules"]}
 if not any("reputation category" in context and value=="무법" for context,value in categories.items()):
  raise ValueError("Outlaw=무법 rule not present")
 if categories.get("NFS multiplayer game mode")!="AllDrive":
  raise ValueError("AllDrive spelling policy missing")
 if categories.get("mountain-pass / Touge racing event and mission objective")!="고갯길":
  raise ValueError("User-approved Touge=고갯길 policy missing")
 names={r["source"]:r["korean"] for r in policy["category_rules"]}
 for source,ko in (
  ("Kumho Tire","금호타이어"),
  ("Hankook Tire","한국타이어"),
  ("Aftermarket Equipment Manufacturer (AEM)","애프터마켓 (AEM)")
 ):
  if names.get(source)!=ko:
   raise ValueError("A user-approved tire/AEM localization rule is missing: "+source)

 entries={}
 files=0
 for p in sorted(TRANSLATIONS.rglob("*.csv")):
  if p.name=="category-overrides.csv":continue
  with p.open(encoding="utf-8-sig",newline="") as f:
   rd=csv.DictReader(f)
   if not rd.fieldnames or not {"string_id","source_text","ko_text","status"}.issubset(rd.fieldnames):
    continue
   files+=1
   for row in rd:
    ko=row["ko_text"]
    for bad in BAD:
     if bad in ko:
      raise ValueError(f"Obsolete term {bad} found at {row['string_id']} in {p}")
    sid=row["string_id"]
    if sid in entries:
     raise ValueError("Duplicate string ID across CSVs: "+sid)
    entries[sid]=row
 touge={"0x67D21883","0xBE455A44","0xA13AA783","0x3A4EA933","0x22E9BA54"}
 for sid in touge:
  if sid not in entries:raise ValueError("Expected user-reviewed Touge source missing "+sid)
  row=entries[sid]
  if "touge" not in row["source_text"].casefold() or "고갯길" not in row["ko_text"] or "토우게" in row["ko_text"]:
   raise ValueError("Touge term inconsistency at "+sid)
 for sid,korean in {
  "0xB7238FD6":"애프터마켓 (AEM)",
  "0x71173279":"금호타이어 일반 타이어",
  "0xDCA1A7CD":"금호타이어 스트레치 타이어",
  "0x4029B320":"한국타이어 일반 타이어",
  "0xBA56EE34":"한국타이어 스트레치 타이어"
 }.items():
  if sid not in entries or entries[sid]["ko_text"]!=korean:
   raise ValueError("NFS 2015 user-approved tire/AEM text drift at "+sid)
 for sid,korean in SCORES.items():
  if sid not in entries:
   raise ValueError("Expected Outlaw REP UI source missing: "+sid)
  if entries[sid]["ko_text"]!=korean:
   raise ValueError(f"Outlaw REP translation drift: {sid}: {entries[sid]['ko_text']!r}")
 # Context coverage for every original Outlaw ID, including the 53 phrases
 # belonging to unfinished categories. A blanket substitution would damage
 # the Urban Outlaw brand, Fifteen52 52Outlaw wheel, tags and internal IDs.
 full=policy.get("outlaw_full_corpus")
 if full is None or full.get("source_outlaw_occurrence_ids")!=56:
  raise ValueError("The original game's 56 Outlaw occurrences have not all been categorized")
 contexts=full["id_context"]
 original=ROOT/"work/locale-extract/en-strings.csv"
 with original.open(encoding="utf-8-sig",newline="") as f:
  originals={("0x"+row["string_id"].upper()):row["source_text"]
             for row in csv.DictReader(f) if "outlaw" in row["source_text"].casefold()}
 if len(originals)!=56 or set(originals)!=set(contexts):
  raise ValueError("Outlaw policy no longer matches game source IDs")
 if sum(context=="rep_category" for context in contexts.values())!=16:
  raise ValueError("Outlaw REP category count drifted")
 if sum(context=="proper_name_or_product" for context in contexts.values())!=7:
  raise ValueError("Known Outlaw brand / product classification changed")
 if sum(context=="username_or_hashtag" for context in contexts.values())!=5:
  raise ValueError("Known Outlaw online handles / hashtags classification changed")
 if sum(context=="internal_id_or_markup" for context in contexts.values())!=5:
  raise ValueError("Known Outlaw internal IDs classification changed")
 if sum(context=="person_or_narrative" for context in contexts.values())!=23:
  raise ValueError("Known narrative/persona Outlaw classification changed")
 for sid,context in contexts.items():
  if sid not in entries:continue  # Untranslated category, check when that CSV is added.
  row=entries[sid]
  if row["source_text"]!=originals[sid]:
   raise ValueError(f"Original Outlaw string altered {sid}")
  ko=row["ko_text"]
  if not ko:continue
  if context=="rep_category" and row["status"]!="원문유지" and "무법" not in ko:
   raise ValueError(f"Outlaw REP must be translated as 무법: {sid}")
  if context=="proper_name_or_product":
   # Proper-name labels must remain intact, even if surrounding prose is localized.
   for brand in ("Urban Outlaw","52Outlaw"):
    if brand in originals[sid] and brand not in ko:
     raise ValueError(f"Brand damaged in translated text {sid}: {brand}")
  if context=="username_or_hashtag":
   for match in re.findall(r"#Outlaw\w+|VenturaOutlaw404", originals[sid]):
    if match not in ko:
     raise ValueError(f"Outlaw user ID/hashtag damaged {sid}: {match}")
  if context=="internal_id_or_markup" and row["status"] not in ("원문유지","보류"):
   if ko!=originals[sid]:
    raise ValueError(f"Internal game resource identifier translated at {sid}")
 print("OUTLAW_ALL_56_SOURCE_CONTEXTS_VERIFIED")
 print("OUTLAW_REMAINING_FUTURE_CATEGORY_IDS",sum(sid not in entries for sid in contexts))
 print("TERMINOLOGY_POLICY_OK")
 print("TRANSLATION_CSV_SCANNED",files)
 print("EDITABLE_STRING_IDS",len(entries))
 print("OUTLAW_REP_CATEGORY_TRANSLATIONS_CONFIRMED",len(SCORES))
 print("OUTLAW_PERSONA_AND_BRAND_EXCEPTIONS_PRESERVED")
 print("NO_LEGACY_TRANSCRIPTIONS",",".join(BAD))
if __name__=="__main__":
 try:main()
 except Exception as e:
  print("TERMINOLOGY_CHECK_FAILED",str(e),file=sys.stderr)
  sys.exit(1)
