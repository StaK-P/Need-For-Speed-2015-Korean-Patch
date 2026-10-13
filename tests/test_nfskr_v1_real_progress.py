"""Real (but read-only game/Frosty) v1.0 milestone progress integration QA."""
from pathlib import Path
import hashlib,json,time
from nfskr_setup_flow import build_and_optionally_install
R=Path(__file__).resolve().parent.parent
cfg=Path.home()/"AppData/Local/Frosty/manager_config.json"
manager=R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
destination=R/"work/merge-tests/v1-milestone-progress-qa"
if destination.exists():raise FileExistsError(destination)
old_sha=hashlib.sha256(cfg.read_bytes()).hexdigest().upper()
milestones=[]
start=time.monotonic()
def callback(percent,description):
    milestones.append((percent,description))
    print(f"PROGRESS_REAL {percent:3d}% {description}",flush=True)
result=build_and_optionally_install(
 manager=manager,config=cfg,source_pack="Default",
 selected_mod_names=["Handling Overhaul 2.0.fbmod","Intro_Video_Remover.fbmod"],
 output_root=destination,install=False,
 log=lambda line:None,progress=callback)
assert milestones[0][0]==0
assert milestones[-1][0]==100
assert all(a[0]<=b[0] for a,b in zip(milestones,milestones[1:]))
assert sum(v==100 for v,_ in milestones)==1
assert all(v<100 for v,_ in milestones[:-1])
assert {12,24,28,38,44,49,52,64,68,83,92,94,100} <= {x[0] for x in milestones}
assert result["mode"]=="qa_only"
report=json.loads((Path(result["output"])/"composite-qa-report.json").read_text(encoding="utf8"))
assert report["resource_count"]==617
assert hashlib.sha256(cfg.read_bytes()).hexdigest().upper()==old_sha
print("NFSKR_REAL_MILESTONE_PROGRESS_QA_PASS",
      "steps",len(milestones),"resources",report["resource_count"],
      "seconds",round(time.monotonic()-start,2),
      "config_sha256_unchanged",old_sha,flush=True)
