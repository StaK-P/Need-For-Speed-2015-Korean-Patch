from pathlib import Path
from nfskr_local_assets import bootstrap_local_assets
ROOT=Path(r"D:\Games\EA\nfs-2015-korean-patch")
scratch=ROOT/"work/merge-tests/portable-cold-v2"
manager=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
game=Path(r"D:\Games\EA\Need for Speed")
print("SCRATCH_BOOTSTRAP_START",str(scratch),flush=True)
result=bootstrap_local_assets(scratch,manager,game,lambda x:print(x,flush=True))
print("SCRATCH_BOOTSTRAP_SUCCESS",result,result.stat().st_size,flush=True)
