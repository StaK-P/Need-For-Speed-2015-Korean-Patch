"""Read-only v1.0 UI regression for actual progress and completion latch."""
from pathlib import Path
from unittest.mock import patch
from tkinter import TclError
from nfskr_modern_ui import NFSKRApp
from nfskr_discovery import discover
from nfskr_installer_core import snapshot
from nfskr_progress import MilestoneProgress

R=Path(__file__).resolve().parent.parent
manager=R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
info=discover(preferred_manager=manager,journal_dir=R/"work/merge-tests/setup-gui")
snap=snapshot(info.config,info.manager,info.source_pack)

history=[]
tracker=MilestoneProgress(lambda pct,label:history.append((pct,label)))
for pct in (12,20,24,28,32,35,38,44,49,52,55,58,61,64,68,83,92,94,98,99,100):
    tracker.report(pct,f"실제 완료 단계 {pct}")
assert history[0][0]==0 and history[-1][0]==100
assert all(a[0]<=b[0] for a,b in zip(history,history[1:]))

def labels(widget):
    results=[]
    for child in widget.winfo_children():
        try:results.append(str(child.cget("text")))
        except (ValueError,AttributeError,TclError):pass
        results.extend(labels(child))
    return results

app=NFSKRApp(R,auto_scan=False)
app.withdraw()
try:
    app.apply_scan(info,snap)
    assert "한국어 패치" in app.title()
    assert "v1.0" in labels(app)
    assert app.github_icon is not None and app.github_icon_label is not None
    assert app.github_repository_url is None
    assert app.percent_label.cget("text")=="0%"
    assert abs(app.progress.get())<0.000001
    assert app.nfs_link_checkbox.cget("text")=="한국어 패치 적용 NFS 실행 바로가기"

    app.running=True
    app._set_progress(64,"한국어 글꼴 검증을 완료했습니다.")
    assert app.percent_label.cget("text")=="64%"
    assert abs(app.progress.get()-.64)<0.000001
    app.msgs.put(("install_stage",(83,"모드 병합을 완료했습니다.")))
    app.msgs.put(("install_success",{
        "output":str(R/"work/installer-build"),
        "previous_profile":snap.selected_pack,
        "created_shortcuts":[],"shortcut_warnings":[]}))
    app._messages()
    assert app.percent_label.cget("text")=="100%"
    assert abs(app.progress.get()-1)<0.000001
    assert app.stage.cget("text")=="패치 완료"
    assert app.install_complete is True
    app.apply_scan(info,snap)  # exact refresh after installer success
    assert app.stage.cget("text")=="패치 완료"
    assert app.percent_label.cget("text")=="100%"
    assert abs(app.progress.get()-1)<0.000001

    if app.mod_checkboxes:
        first=next(iter(app.mod_vars.values()))
        first.set(not first.get())
        app._on_mod_toggled(user_action=True)
        assert app.install_complete is False
        assert app.percent_label.cget("text")=="0%"

    app.running=True
    app._set_progress(68,"한국어 패치 생성 완료")
    with patch("nfskr_modern_ui.messagebox.showerror"):
        app.msgs.put(("install_error",{
             "message":"샘플 오류","technical":"fixture test",
             "trace":"no game files modified"}))
        app._messages()
    assert app.percent_label.cget("text")=="68%"
    assert app.progress.get()<1
    assert app.stage.cget("text")=="설치가 중단되었습니다."
    print("NFSKR_V1_UI_GITHUB_COMPLETION_LATCH_PERCENT_PASS",
          "milestones",len(history),"github_url",app.github_repository_url,
          "failure_percent",app.percent_label.cget("text"))
finally:
    app.destroy()
