#!/usr/bin/env python3
"""On-device source-font/locale reproduction smoke test. NO Frosty install."""
from pathlib import Path
import os
from nfskr_local_assets import bootstrap_local_assets
from nfskr_fbmod_format import parse_mod
from nfskr_installer_core import digest_file
ROOT=Path(__file__).resolve().parent.parent
DEST=ROOT/"work/merge-tests/portable-bootstrap-20261012"
MANAGER=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
GAME=Path(r"D:\Games\EA\Need for Speed")
os.environ["NFSKR_WORKSPACE_ROOT"]=str(DEST)
def main():
    result=bootstrap_local_assets(DEST,MANAGER,GAME,print)
    mod=parse_mod(result)
    print("PORTABLE_BOOTSTRAP_SUCCESS",result,mod.version,len(mod.entries),digest_file(result))
    a=DEST/"work/full-build/user-local/punctuation-fonts"
    b=ROOT/"work/full-build/qa-v0.1.1/punctuation-fonts"
    names=("cond","condmedi","condbold")
    for name in names:
        file=f"nfs16-din-{name}-ko-local.ttf"
        print("FROZEN_FONT_REPRO",name,digest_file(a/file)==digest_file(b/file),
              digest_file(a/file))
        assert digest_file(a/file)==digest_file(b/file)
if __name__=="__main__":
    main()
