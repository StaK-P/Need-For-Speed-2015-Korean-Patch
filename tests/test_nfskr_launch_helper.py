"""Only sandbox tests of the actual 'Frosty 실행' action: no real launch."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from nfskr_discovery import start_manager,symlink_preflight,source_pack,safe_frosty_profile_name
with TemporaryDirectory(prefix="nfskr-launch-",dir=r"D:\Games\EA\nfs-2015-korean-patch\work") as base:
    root=Path(base)
    manager=root/"FrostyModManager"
    manager.mkdir()
    exe=manager/"FrostyModManager.exe"
    exe.write_bytes(b"Test executable placeholder")
    game=root/"Need for Speed"
    game.mkdir()
    (game/"NFS16.exe").write_bytes(b"Test game placeholder")
    passed,text=symlink_preflight(game)
    assert passed,text
    with patch("nfskr_discovery._running_manager",return_value=[]),\
         patch("nfskr_discovery.subprocess.Popen") as runner:
        ok,msg=start_manager(manager,game)
        assert ok,msg
        runner.assert_called_once()
        assert runner.call_args.args[0]==[str(exe)]
    with patch("nfskr_discovery._running_manager",return_value=[manager]),\
         patch("nfskr_discovery.subprocess.Popen") as runner:
        ok,msg=start_manager(manager,game)
        assert ok and "이미 실행" in msg
        runner.assert_not_called()
    assert source_pack(
        {"Options":{"SelectedPack":"한글패치"},
         "Packs":{"Default":"mod.fbmod:True","한글패치":"NFSKR-Composite-x.fbmod:True"}}
        )=="Default"
    assert safe_frosty_profile_name({"한글패치":"a"})=="NFSKR"
    assert safe_frosty_profile_name({"NFSKR":"a"})=="NFSKR-2"
print("NFSKR_FROSTY_BUTTON_AND_ASCII_SYMLINK_QA_PASS")
