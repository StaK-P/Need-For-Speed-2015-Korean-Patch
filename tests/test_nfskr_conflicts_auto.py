import csv,json
from pathlib import Path
from mod_merge_core import merge_localization,report
R=Path(__file__).resolve().parent.parent
with (R/"work/locale-extract/en-strings.csv").open(encoding="utf-8-sig",newline="") as f:
    base={v["string_id"].upper():v["source_text"] for v in csv.DictReader(f)}
data=json.loads((R/"work/second-pass-QA/handling-english-strings-diff.json").read_text(encoding="utf8"))
external={key:v["handling"] for key,v in data["changed"].items() if v["handling"] is not None}
ko={v["id"]:v["ko"] for v in json.loads((R/"translations/nfskr-first-release-v1.1.json").read_text(encoding="utf8"))["entries"]}
mapping=json.loads((R/"translations/compat-handling-overhaul-v0.1.3.json").read_text(encoding="utf8"))
reviewed={e["id"]:e["ko"] for e in mapping["entries"]}
merged,rows=merge_localization(base,external,ko,reviewed,base_deleted_ids=set(data["removed_keys"]))
s=report(rows)
print("AUTO_MERGE_COUNTS",s["decision_counts"],"UNRESOLVED",s["manual_review_count"])
for x in s["manual_review"]:
    print(x["id"],x["external"][:140].encode("unicode_escape").decode())
assert len(merged)==10249
assert merged["3D35E64E"]=="구동계"
assert s["manual_review_count"] <= 10
