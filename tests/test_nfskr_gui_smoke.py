from pathlib import Path
from nfskr_modern_ui import NFSKRApp
from nfskr_discovery import discover
from nfskr_installer_core import snapshot
root=Path(__file__).resolve().parent.parent
manager=root/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
app=NFSKRApp(root,auto_scan=False)
app.withdraw()
info=discover(preferred_manager=manager,journal_dir=root/"work/merge-tests/setup-gui")
snap=snapshot(info.config,info.manager,info.source_pack)
app.apply_scan(info,snap)
app.update_idletasks()
assert info.source_pack=="Default"
assert len(snap.enabled_mods)>=5
assert app.detect_dot.cget("text")=="●  확인 완료"
assert app.install_button.cget("text")=="설치"
assert app.restore_button.cget("text")=="복원"
assert app.frosty_button.cget("text")=="Frosty 실행"
assert app.frosty_link_checkbox.cget("text")=="Frosty 바탕화면 바로가기"
assert app.nfs_link_checkbox.cget("text")=="한국어 패치 적용 NFS 실행 바로가기"
assert bool(app.make_frosty_shortcut.get()) is True
assert bool(app.make_nfs_shortcut.get()) is True
from dataclasses import replace
missing=replace(info,manager=None,source_pack="",current_pack="")
app.apply_scan(missing,None)
assert "자동" in app.stage.cget("text")
assert app.snapshot is None
app.apply_scan(info,snap)
def collect_labels(widget):
    results=[]
    from tkinter import TclError
    for child in widget.winfo_children():
        try: results.append(str(child.cget("text")))
        except (ValueError,AttributeError,TclError):pass
        results.extend(collect_labels(child))
    return results
assert any("StaK_P" in label for label in collect_labels(app))
print("NFSKR_MODERN_GUI_SMOKE_PASS",info.source_pack,len(snap.enabled_mods),
      app.winfo_reqwidth(),app.winfo_reqheight())
app.destroy()
