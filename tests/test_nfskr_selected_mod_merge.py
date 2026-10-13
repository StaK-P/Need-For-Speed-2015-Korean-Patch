"""QA-only end-to-end: selected source pack and only checked source mods.

No actual Frosty install, no game launch, no game or existing mod modifications.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json,hashlib

from nfskr_setup_flow import build_and_optionally_install
from nfskr_discovery import discover
from nfskr_installer_core import snapshot,digest_file
from nfskr_composite import selected_mod_order

R=Path(__file__).resolve().parent.parent
manager=R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
info=discover(preferred_manager=manager,journal_dir=R/"work/merge-tests/setup-gui")
config=info.config
before=hashlib.sha256(config.read_bytes()).hexdigest().upper()
first=snapshot(config,manager,"Default")
all_active=[x.name for x in first.enabled_mods]
assert len(all_active)>=6,all_active
handling=next(n for n in all_active if "Handling Overhaul" in n)
intro=next(n for n in all_active if "Intro_Video_Remover" in n)
chosen=[intro,handling]
selected=selected_mod_order(first,chosen)
assert [m.name for m in selected]==[handling,intro], "Frosty order must be preserved"

with TemporaryDirectory(prefix="nfskr-selected-merges-",dir=str(R/"work/merge-tests")) as t:
    folder=Path(t)
    result=build_and_optionally_install(manager=manager,config=config,
         source_pack="Default",selected_mod_names=chosen,
         output_root=folder/"filtered",install=False,log=lambda message:None)
    report=json.loads((Path(result["output"])/"composite-qa-report.json").read_text(encoding="utf8"))
    assert report["resource_count"]<4378
    assert report["original_gameplay_mods"]==[
        {"filename":x.name,"sha256":x.sha256} for x in selected]
    assert [x["filename"] for x in report["original_gameplay_mods"]]==[handling,intro]
    assert result["source_mods"]==[handling,intro]
    print("FILTERED_MERGE_PASS",result["source_mods"],report["resource_count"],flush=True)

    # No checked mod is a supported Korean-only merger, still a Frosty v5 FBMod.
    empty=build_and_optionally_install(manager=manager,config=config,
         source_pack="UNITE NFS15",selected_mod_names=[],
         output_root=folder/"empty",install=False,log=lambda message:None)
    report2=json.loads((Path(empty["output"])/"composite-qa-report.json").read_text(encoding="utf8"))
    assert empty["source_mods"]==[]
    assert report2["original_gameplay_mods"]==[]
    assert report2["resource_count"]==11 and report2["translated_ids"]==8206
    print("PROFILE_ALTERNATIVE_KOREAN_ONLY_PASS",report2["resource_count"],flush=True)

assert hashlib.sha256(config.read_bytes()).hexdigest().upper()==before
print("SELECTED_MOD_QA_ORIGINAL_FROSTY_UNCHANGED",before,flush=True)
