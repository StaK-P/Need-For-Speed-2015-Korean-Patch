import os
from pathlib import Path
import json
R=Path(r"D:\Games\EA\nfs-2015-korean-patch")
cache=R/"work/merge-tests/portable-release-exe-qa"
os.environ["NFSKR_WORKSPACE_ROOT"]=str(cache)
from nfskr_setup_flow import build_and_optionally_install
result=build_and_optionally_install(
 manager=R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager",
 config=Path.home()/"AppData/Local/Frosty/manager_config.json",
 include_disabled=["Handling Overhaul 2.0.fbmod"],
 output_root=cache/"work/merge-tests/handling-test",
 install=False,log=lambda m:print(str(m),flush=True))
out=Path(result["output"])
data=json.loads((out/"composite-qa-report.json").read_text(encoding="utf8"))
assert data["reviewed_external_label_ids"]==62
assert data["final_strings"]==10249
print("PORTABLE_HANDLING_MERGE_PASS",data["resource_count"],
      data["reviewed_external_label_ids"],data["locale_merge"]["manual_review_count"],flush=True)
