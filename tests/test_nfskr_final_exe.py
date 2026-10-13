"""Windows stand-alone EXE integrity and first-use end-to-end QA.

Never installs into the real Frosty manager or writes game original files.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

R=Path(__file__).resolve().parent.parent
out=R/"work/installer-build/release-candidate"
exe=out/"NFSKR-Setup.exe"
mode=sys.argv[1] if len(sys.argv)>1 else "self"
if mode=="self":
    result=out/"selftest-v1.1-stage-result.json"
    args=["--self-test",str(result)]
    env=os.environ.copy()
elif mode=="cold":
    result=out/"qa-v1.1-stage-all-result.json"
    args=["--qa-build",str(result),
       str(R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"),
       str(Path.home()/"AppData/Local/Frosty/manager_config.json")]
    env=os.environ.copy()
    env["NFSKR_WORKSPACE_ROOT"]=str(R/"work/merge-tests/portable-final-exe-qa")
elif mode=="selected":
    result=out/"qa-v1.1-stage-selected-result.json"
    names=["Handling Overhaul 2.0.fbmod","Intro_Video_Remover.fbmod"]
    args=["--qa-selected-build",str(result),
       str(R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"),
       str(Path.home()/"AppData/Local/Frosty/manager_config.json"),
       "Default",json.dumps(names)]
    env=os.environ.copy()
    env["NFSKR_WORKSPACE_ROOT"]=str(R/"work/merge-tests/portable-final-exe-qa")
else:
    raise ValueError("Expected mode self, cold or selected")
if result.exists():raise FileExistsError(result)
if not exe.is_file():raise FileNotFoundError(exe)
start=time.monotonic()
print("NFSKR_FINAL_EXE_TEST_START",mode,str(exe),flush=True)
proc=subprocess.run([str(exe),*args],env=env,capture_output=True,text=True,
                    encoding="utf-8",errors="replace",timeout=490)
print("FINISHED",proc.returncode,round(time.monotonic()-start,2),flush=True)
if not result.is_file():
    print("STDERR",proc.stderr[-2000:])
    raise RuntimeError("EXE did not write QA result file")
data=json.loads(result.read_text(encoding="utf8"))
print("QA_RESULT",json.dumps(data,ensure_ascii=True)[:6000],flush=True)
if proc.returncode!=0 or data.get("status")!="passed":
    raise RuntimeError("EXE diagnostic mode failed: "+str(data.get("error")))
if mode=="cold":
    report=json.loads((Path(data["qa_output"]["output"])/"composite-qa-report.json").read_text(encoding="utf8"))
    assert report["resource_count"]>=4000,report["resource_count"]
    assert report["reviewed_external_label_ids"]==62,report["reviewed_external_label_ids"]
    assert report["locale_merge"]["manual_review_count"]==5,report["locale_merge"]["manual_review_count"]
    assert report["translated_ids"]==8206
    assert report["frosty_profile_modified"] is False
    print("COLD_END_TO_END_6_MODS_PASS",
        json.dumps({"resources":report["resource_count"],
          "reviewed":report["reviewed_external_label_ids"],
          "fallback_english":report["locale_merge"]["manual_review_count"]},ensure_ascii=True))
if mode=="selected":
    report=json.loads((Path(data["qa_output"]["output"])/"composite-qa-report.json").read_text(encoding="utf8"))
    assert [r["filename"] for r in report["original_gameplay_mods"]]==names
    assert data["qa_output"]["source_mods"]==names
    assert 11<report["resource_count"]<4378
    assert report["frosty_profile_modified"] is False
    print("FROSTY_PROFILE_CHECKBOX_NATIVE_MERGE_PASS",
          json.dumps({"mods":names,"resources":report["resource_count"]},ensure_ascii=True),flush=True)
print("NFSKR_FINAL_EXE_TEST_PASS",mode,flush=True)
