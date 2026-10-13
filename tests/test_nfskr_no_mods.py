import os,json
from pathlib import Path
dev=Path(r"D:\Games\EA\nfs-2015-korean-patch")
scratch=dev/"work/merge-tests/portable-release-exe-qa"
os.environ["NFSKR_WORKSPACE_ROOT"]=str(scratch)
from nfskr_setup_flow import build_and_optionally_install
manager=dev/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
config=scratch/"work/merge-tests/test-empty-pack-config.json"
if config.exists():raise FileExistsError(config)
config.parent.mkdir(parents=True,exist_ok=True)
config.write_text(json.dumps({"Games":{"NFS16":{"GamePath":r"D:\Games\EA\Need for Speed",
   "Options":{"SelectedPack":"Default"},"Packs":{"Default":""}}},
   "GlobalOptions":{"ApplyModOrder":"List"}},ensure_ascii=False),encoding="utf8")
result=build_and_optionally_install(manager=manager,config=config,
  output_root=scratch/"work/merge-tests/no-mod-case",install=False,
  log=lambda s:print(s,flush=True))
report=json.loads((Path(result["output"])/"composite-qa-report.json").read_text(encoding="utf8"))
assert report["preserved_source_assets"]==0
assert report["translated_ids"]==8206
assert report["resource_count"]==11
print("NFSKR_KOREAN_ONLY_PASS",report["resource_count"],report["final_strings"],flush=True)
