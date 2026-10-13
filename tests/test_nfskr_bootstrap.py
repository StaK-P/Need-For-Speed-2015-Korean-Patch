"""Secure official Frosty install and new NFS16 config tests in a sandbox only."""
import json
from pathlib import Path
import tempfile
import zipfile
from nfskr_bootstrap import (ensure_frosty,valid_frosty,ensure_profile,
                             _safe_extract,requirements_status,RELEASE_SHA256)
from nfskr_installer_core import snapshot,digest_file
R=Path(__file__).resolve().parent.parent
original=R/"work/installer-build/frosty-official-release-QA.zip"
if digest_file(original)!=RELEASE_SHA256:raise ValueError("Official ZIP hash differs")
with tempfile.TemporaryDirectory(prefix="nfskr-game-frosty-test-",dir=str(R/"work")) as temp:
    base=Path(temp)
    game=base/"Need for Speed"
    game.mkdir()
    (game/"NFS16.exe").write_bytes(b"dummy nfs16 executable - not run")
    config=base/"LOCALAPPDATA/Frosty/manager_config.json"
    loaded,first=ensure_frosty(game,None,archive_override=original,log=lambda _:None)
    assert first and valid_frosty(loaded)
    assert loaded==(game/"NFSKR/FrostyModManager").resolve()
    reread,second=ensure_frosty(game,None,log=lambda _:None)
    assert not second and reread==loaded
    fresh=ensure_profile(config,game,loaded,log=lambda _:None)
    assert fresh
    clean=snapshot(config,loaded)
    assert clean.selected_pack=="Default" and clean.enabled_mods==()
    assert clean.game_path==game.resolve()
    raw=config.read_bytes()
    assert not ensure_profile(config,game,loaded,log=lambda _:None)
    assert config.read_bytes()==raw
    # Existing user config is backed up, while all unrelated keys survive.
    info=json.loads(raw.decode("utf8"))
    info["OtherUserData"]={"keep":"123"}
    info["GlobalOptions"].pop("ApplyModOrder")
    config.write_text(json.dumps(info,ensure_ascii=False),encoding="utf8")
    assert ensure_profile(config,game,loaded,log=lambda _:None)
    assert json.loads(config.read_text(encoding="utf8"))["OtherUserData"]=={"keep":"123"}
    assert config.with_name("manager_config.json.NFSKR-before-bootstrap.bak").is_file()
    # Deliberately malicious ZIP cannot write outside staging directory.
    bad=base/"malicious.zip"
    with zipfile.ZipFile(bad,"w") as arc:
        arc.writestr("FrostyModManager/../../escape.exe",b"evil")
        arc.writestr("FrostyModManager/FrostyModManager.exe",b"fake")
    try:
        _safe_extract(bad,base/"sandbox-extract")
        raise AssertionError("Unsafe ZIP was accepted")
    except Exception:
        assert not (base/"escape.exe").exists()
    status=requirements_status()
    print("NFSKR_FROSTY_BOOTSTRAP_QA_PASS",
          json.dumps({"installed":str(loaded),"files":len(list(loaded.rglob("*"))),
                      "runtime":status},ensure_ascii=True),flush=True)
