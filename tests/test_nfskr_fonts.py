"""Verify official SUIT/SUITE downloads in sandbox only (no global font install)."""
from pathlib import Path
import tempfile
from nfskr_fonts import install_game_fonts,UPSTREAM,DERIVED
from nfskr_installer_core import digest_file
from nfskr_local_assets import locate
R=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="nfskr-font-install-test-",dir=str(R/"work")) as path:
    game=Path(path)/"Need for Speed"
    game.mkdir()
    (game/"NFS16.exe").write_bytes(b"test game executable")
    done=install_game_fonts(game,R,log=lambda t:print(t,flush=True),prefer_download=True)
    assert len(done)==3
    for name,(url,hashval,size) in UPSTREAM.items():
        assert done[name].stat().st_size==size
        assert digest_file(done[name])==hashval
    for name,sha in DERIVED.items():
        assert digest_file(done[name])==sha
    local=install_game_fonts(game,R,log=lambda _:None,prefer_download=False)
    assert local==done
    print("NFSKR_FONT_AUTO_DOWNLOAD_QA_PASS",sum(v.stat().st_size for v in local.values()),
          "font_files",len(local),flush=True)
