#!/usr/bin/env python3
"""Initialize and add newly discovered menu translations without overwriting CSV edits.

Edit translations/menu/*.csv in Excel (UTF-8 with BOM), preserving string_id.
An existing row's ko_text, status, scope and notes are never overwritten.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/"work/locale-extract/en-strings.csv"
SEED=ROOT/"tools/menu-translation-seed.json"
DEST=ROOT/"translations/menu"
GROUPS=("main","settings","garage","events","social","system")
LABELS={"main":"메인","settings":"설정","garage":"차고·튜닝","events":"이벤트","social":"소셜","system":"공통"}
FIELDS=("string_id","scope","source_text","ko_text","status","notes")

def orig_rows(path: Path=SOURCE) -> list[dict[str,str]]:
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def read_existing(directory: Path) -> dict[str,dict[str,str]]:
    rows={}
    for group in GROUPS:
        path=directory/f"{group}.csv"
        if not path.exists():continue
        with path.open(encoding="utf-8-sig",newline="") as f:
            rdr=csv.DictReader(f)
            if rdr.fieldnames!=list(FIELDS):
                raise ValueError(f"Unexpected columns in {path}: {rdr.fieldnames}")
            for row in rdr:
                raw_sid=row["string_id"].strip()
                if not raw_sid.lower().startswith("0x") or len(raw_sid)!=10:
                    raise ValueError(f"Invalid CSV string_id {raw_sid!r}")
                sid="0x"+raw_sid[2:].upper()
                if sid in rows:
                    raise ValueError(f"Duplicate string_id {sid} between CSVs")
                row["string_id"]=sid
                rows[sid]=row
    return rows

def generate() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=DEST)
    parser.add_argument("--source",type=Path,default=SOURCE)
    args=parser.parse_args()
    originals=orig_rows(args.source)
    seed=json.loads(SEED.read_text(encoding="utf-8"))
    glossary={}
    matched=defaultdict(set)
    for group in GROUPS:
        for raw,ko in seed["groups"][group].items():
            normalized=raw.strip().casefold()
            if normalized in glossary:
                continue  # first declared group owns ambiguous/common UI labels
            glossary[normalized]=(group,ko)
    old=read_existing(args.output)
    bygroup=defaultdict(list)
    count_new=0
    for original in originals:
        normalized=original["source_text"].strip().casefold()
        if normalized not in glossary:
            continue
        group,translation=glossary[normalized]
        sid="0x"+original["string_id"].upper().removeprefix("0X")
        matched[group].add(normalized)
        if sid in old:
            item=old.pop(sid)
            if item["source_text"]!=original["source_text"]:
                raise ValueError(f"CSV source was modified or source game changed for {sid}")
            if item["scope"] not in GROUPS:
                raise ValueError(f"Unknown scope in existing {sid}: {item['scope']}")
            group=item["scope"]
        else:
            item={
                "string_id":sid,"scope":group,"source_text":original["source_text"],
                "ko_text":translation,
                "status":"원문유지" if original["source_text"].strip()==translation else "초벌",
                "notes":"",
            }
            count_new+=1
        bygroup[group].append(item)
    if old:
        # Preserve manual additions, too, as long as the ID is from the installed game.
        origins={"0x"+row["string_id"].upper():row["source_text"] for row in originals}
        for sid,item in old.items():
            if sid not in origins:
                raise ValueError(f"Existing edited translation ID missing from source: {sid}")
            if item["source_text"]!=origins[sid]:
                raise ValueError(f"Existing CSV source mismatched: {sid}")
            bygroup[item["scope"]].append(item)
    args.output.mkdir(parents=True,exist_ok=True)
    count=0
    for group in GROUPS:
        rows=sorted(bygroup[group],key=lambda row:(row["source_text"].casefold(),row["string_id"]))
        target=args.output/f"{group}.csv"
        with target.open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS,lineterminator="\r\n",quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(rows)
        count+=len(rows)
        print(f"CSV_READY {group} {len(rows)} -> {target}")
    print("TOTAL_ROWS",count,"NEW_ROWS",count_new,"ORIGINAL_TEXTS",len(originals),"GLOSSARY_TERMS",len(glossary))
    unknown=[(group,key) for group in GROUPS for key in seed["groups"][group]
             if key.strip().casefold() not in
             {r["source_text"].strip().casefold() for r in originals}]
    print("GLOSSARY_TERMS_NOT_IN_SOURCE",len(unknown))
    for group,key in unknown[:35]:print("  NOT_FOUND",group,repr(key))

if __name__=="__main__":
    generate()
