"""No real desktop modifications: exercise shortcut COM in temporary folder."""
from pathlib import Path
import json
import tempfile
from nfskr_shortcuts import create_shortcuts,inspect_shortcut,remove_owned_shortcuts
R=Path(__file__).resolve().parent.parent
manager=R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
game=Path(r"D:\Games\EA\Need for Speed")
with tempfile.TemporaryDirectory(prefix="nfskr-shortcut-qa-",dir=R/"work") as directory:
    desk=Path(directory)
    first=create_shortcuts(manager=manager,game=game,pack="NFSKR",
          frosty=True,game_shortcut=True,desktop=desk,log=lambda _:None)
    assert len(first)==2
    for record in first:
        result=inspect_shortcut(Path(record["path"]))
        print("CREATED_LNK",Path(record["path"]).name,
               result["target"],result["arguments"],flush=True)
        assert result["target"].lower().endswith("frostymodmanager.exe")
        if "Need for Speed" in Path(record["path"]).name:
            assert result["arguments"]=="-launch NFSKR"
        else:
            assert not result["arguments"]
    second=create_shortcuts(manager=manager,game=game,pack="NFSKR-2",
          frosty=False,game_shortcut=True,desktop=desk,log=lambda _:None)
    assert len(second)==1
    assert "(2)" in Path(second[0]["path"]).stem
    assert inspect_shortcut(Path(second[0]["path"]))["arguments"]=="-launch NFSKR-2"
    edited=Path(first[0]["path"])
    original_sha=first[0]["sha256"]
    edited.write_bytes(edited.read_bytes()+b"modified")
    removed=remove_owned_shortcuts(first+second)
    assert edited.exists()
    assert len(removed)==2
    print("NFSKR_SHORTCUTS_QA_PASS",len(removed),"preserved_modified",edited.name,flush=True)
