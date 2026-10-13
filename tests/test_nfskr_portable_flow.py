import os
from pathlib import Path
from time import time
dev=Path(r"D:\Games\EA\nfs-2015-korean-patch")
scratch=dev/"work/merge-tests/portable-cold-v2"
os.environ["NFSKR_WORKSPACE_ROOT"]=str(scratch)
from nfskr_setup_flow import build_and_optionally_install
manager=dev/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
config=Path.home()/"AppData/Local/Frosty/manager_config.json"
print("PORTABLE_QA_FLOW_START",str(scratch),flush=True)
result=build_and_optionally_install(manager=manager,config=config,
          output_root=scratch/"work/merge-tests/flow-test",
          install=False,log=lambda s:print(s,flush=True))
print("PORTABLE_QA_FLOW_SUCCESS",result,flush=True)
