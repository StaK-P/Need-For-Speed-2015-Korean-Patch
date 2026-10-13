"""Profile dropdown / mod checkbox QA on actual Frosty pack data.

Original config, installed game, saved mod files are READ-ONLY.
"""
from pathlib import Path
import hashlib
import json
import tempfile
from dataclasses import replace

from nfskr_modern_ui import NFSKRApp
from nfskr_discovery import discover, read_game_config, selectable_source_packs
from nfskr_composite import selected_mod_order, selectable_source_mods, CompositeError
from nfskr_installer_core import snapshot

R=Path(__file__).resolve().parent.parent
manager=R/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
info=discover(preferred_manager=manager,journal_dir=R/"work/merge-tests/setup-gui")
source_bytes=info.config.read_bytes()
source_sha=hashlib.sha256(source_bytes).hexdigest().upper()
cfg=read_game_config(info.config)
packs=selectable_source_packs(cfg)
assert "Default" in packs and "UNITE NFS15" in packs and "KO_ISOLATED_QA" in packs
assert "한글패치" not in packs, "Generated Korean composite must not be selectable"

main=snapshot(info.config,info.manager,"Default")
mods=selectable_source_mods(main)
assert len(mods)==6
assert len(main.replaced_korean_mods)==1

app=NFSKRApp(R,auto_scan=False)
app.withdraw()
try:
    app.apply_scan(info,main,packs,"Default")
    app.update_idletasks()
    assert app.profile_choice.get()=="Default"
    assert app.profile_names==packs
    assert len(app.mod_checkboxes)==6
    assert len(app._selected_mod_names())==6
    handling=next(m.name for m in mods if m.name.startswith("Handling Overhaul"))
    app.mod_vars[handling].set(False)
    app._on_mod_toggled()
    chosen=app._selected_mod_names()
    assert handling not in chosen and len(chosen)==5
    selected=selected_mod_order(main,chosen)
    assert [m.name for m in selected]==chosen
    assert [m.name for m in selected]==[m.name for m in mods if m.name!=handling]
    # Deliberately select no third-party mods: Korean-only must remain valid.
    for variable in app.mod_vars.values():variable.set(False)
    app._on_mod_toggled()
    assert app._selected_mod_names()==[]
    assert selected_mod_order(main,[])==[]
    for var in app.mod_vars.values():var.set(True)
    app._on_mod_toggled()
    assert len(app._selected_mod_names())==6
    try:
        selected_mod_order(main,["NFSKR-Composite-2EE3FE3A769B.fbmod"])
        raise AssertionError("Generated NFSKR composite was selectable")
    except CompositeError:
        pass

    # Switch the dropdown by applying a different Frosty pack; defaults follow
    # that pack's ACTUAL enabled/disabled flags, not the old pack selection.
    unity=snapshot(info.config,info.manager,"UNITE NFS15")
    app.apply_scan(info,unity,packs,"UNITE NFS15")
    app.update_idletasks()
    assert app.profile_choice.get()=="UNITE NFS15"
    assert app._selected_mod_names()==[m.name for m in selectable_source_mods(unity) if m.enabled]
    app.apply_scan(info,main,packs,"Default")
    assert len(app._selected_mod_names())==6, "Previously selected pack remembered"

    # Synthetic config shows a disabled mod being explicitly opted in; native
    # Frosty Config is not changed even for this test.
    with tempfile.TemporaryDirectory(prefix="nfskr-profile-picker-",dir=str(R/"work")) as folder:
        testconfig=Path(folder)/"manager_config.json"
        obj=json.loads(source_bytes.decode("utf-8-sig"))
        original=obj["Games"]["NFS16"]["Packs"]["Default"]
        obj["Games"]["NFS16"]["Packs"]["Default"]=original.replace(
            "Handling Overhaul 2.0.fbmod:True",
            "Handling Overhaul 2.0.fbmod:False")
        testconfig.write_text(json.dumps(obj,ensure_ascii=False),encoding="utf8")
        fakeinfo=replace(info,config=testconfig)
        fake=snapshot(testconfig,info.manager,"Default")
        app.apply_scan(fakeinfo,fake,packs,"Default")
        assert app.mod_vars[handling].get() is False
        app.mod_vars[handling].set(True)
        app._on_mod_toggled()
        chosen=app._selected_mod_names()
        assert handling in chosen and len(chosen)==6
        assert {m.name for m in selected_mod_order(fake,chosen)}==set(chosen)
        # Frosty keeps the source pack's enable-state disabled.
        assert "Handling Overhaul 2.0.fbmod:False" in testconfig.read_text(encoding="utf8")
    # Exercise the actual dropdown callback + asynchronous reload.
    import time
    app._on_source_profile_changed("UNITE NFS15")
    until=time.monotonic()+18
    while time.monotonic()<until:
        app.update()
        if app.snapshot and not app.busy and app.snapshot.selected_pack=="UNITE NFS15":
            break
        time.sleep(.05)
    assert app.snapshot is not None
    assert app.snapshot.selected_pack=="UNITE NFS15", "Dropdown did not reload source pack"
    assert app.profile_choice.get()=="UNITE NFS15"
    assert app._selected_mod_names()==[
        m.name for m in selectable_source_mods(app.snapshot) if m.enabled]

    print("NFSKR_GUI_PROFILE_MOD_PICKER_PASS",
          json.dumps({"packs":packs,"default_source_mods":len(mods),
                      "selectively_excluded":handling,
                      "korean_only_accepted":True,"disabled_mod_opt_in":True},ensure_ascii=True))
finally:
    app.destroy()
assert hashlib.sha256(info.config.read_bytes()).hexdigest().upper()==source_sha
print("FROSTY_ORIGINAL_CONFIG_UNCHANGED",source_sha)
