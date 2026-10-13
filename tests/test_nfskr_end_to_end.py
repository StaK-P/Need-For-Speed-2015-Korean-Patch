#!/usr/bin/env python3
"""Actual composite + Frosty native FBPack + profile-switch rollback in sandbox.

No writes to the real game, real Frosty mod install, or user profile.
"""
from pathlib import Path
import hashlib,json,os,shutil,tempfile,zipfile
from nfskr_installer_core import snapshot,digest_file,install_verified,rollback_install
from nfskr_shortcuts import create_shortcuts,save_shortcuts_in_journal

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager/Mods/NFS16"
COMBINED=ROOT/"work/merge-tests/default-active-20261012/NFSKR-Merged-ede606652367.fbmod"
REPORT=ROOT/"work/merge-tests/default-active-20261012/independent-validation-v2.json"
def main():
    report=json.loads(REPORT.read_text(encoding="utf8"))
    if digest_file(COMBINED)!=report["sha256"] or not report["native_frosty_reader"]:
        raise ValueError("Failed external Frosty reader verification required")
    with tempfile.TemporaryDirectory(prefix="nfskr-test-",dir=str(ROOT/"work/merge-tests")) as td:
        work=Path(td)
        manager=work/"FrostyModManager"
        mods=manager/"Mods/NFS16";mods.mkdir(parents=True)
        sources=report["source_mods"]
        for row in sources:
            src=SOURCE/row["filename"];dst=mods/src.name
            if digest_file(src)!=row["sha256"]:raise ValueError("Real source mod changed")
            try:os.link(src,dst)
            except OSError:shutil.copyfile(src,dst)
        cfg=work/"manager_config.json"
        pack_order="|".join(row["filename"]+":True" for row in sources)
        cfg.write_text(json.dumps({
            "Games":{"NFS16":{"GamePath":r"D:\Games\EA\Need for Speed",
                 "Packs":{"Default":pack_order,"Unchanged":"Other.fbmod:False"},
                 "Options":{"SelectedPack":"Default"}}},
            "GlobalOptions":{"ApplyModOrder":"List"}},ensure_ascii=False),encoding="utf8")
        original=cfg.read_bytes()
        snap=snapshot(cfg,manager)
        certificate=work/"verified-certificate.json"
        certificate.write_text(json.dumps({
            "schema":"nfskr-composite-v1",
            "status":"verified",
            "source_pack":"Default",
            "source_pack_list":pack_order,
            "config_sha256":snap.config_sha256,
            "enabled_mods":[{"filename":r.name,"sha256":r.sha256} for r in snap.enabled_mods],
            "verified_checks":{
               "frosty_reader":report["native_frosty_reader"],
               "locale_ebx_chunk_roundtrip":report["native_ebx_roundtrip"] and report["native_flammenwerfer_decoded"],
               "source_resource_coverage":report["source_gameplay_resource_count"]>3000,
               "font_resource_integrity":report["font_payload_identical_to_frozen_first_release"],
               "no_unresolved_conflicts":True
            },
            "merged_fbmod":str(COMBINED),
            "merged_sha256":digest_file(COMBINED)
        },ensure_ascii=False),encoding="utf8")
        output=work/"result"
        journal=install_verified(snap,certificate,output,is_busy=lambda:False)
        installed=json.loads(cfg.read_text(encoding="utf8"))
        assert installed["Games"]["NFS16"]["Options"]["SelectedPack"]=="NFSKR"
        assert installed["Games"]["NFS16"]["Packs"]["Default"]==pack_order
        archive=Path(journal["created_archive"])
        with zipfile.ZipFile(archive) as z:
            man=json.loads(z.read("manifest.json"))
            assert man["mods"]==[Path(journal["installed_composite"]).name]
            assert z.read(man["mods"][0])==COMBINED.read_bytes()
        journals=list(output.glob("install-journal-*.json"));assert len(journals)==1
        (manager/"FrostyModManager.exe").write_bytes(b"TEST_ONLY_FROSTY_EXE")
        shortcuts=create_shortcuts(manager=manager,game=snap.game_path,
               pack=journal["new_pack"],frosty=True,game_shortcut=True,
               desktop=work,log=lambda _:None)
        assert len(shortcuts)==2
        save_shortcuts_in_journal(journals[0],shortcuts)
        undone=rollback_install(journals[0],is_busy=lambda:False)
        assert len(undone["removed_desktop_shortcuts"])==2
        assert all(not Path(row["path"]).exists() for row in shortcuts)
        assert cfg.read_bytes()==original
        assert undone["restored_pack"]=="Default"
        for row in sources:
            assert digest_file(mods/row["filename"])==row["sha256"]
        print("NFSKR_E2E_SANDBOX_INSTALL_AND_ROLLBACK_PASS",
           json.dumps({"source_mods":len(sources),"fbpack_bytes":archive.stat().st_size,
             "old_profile_preserved":True,"game_unmodified":True,"shortcuts_created_and_rolled_back":2},ensure_ascii=True))
if __name__=="__main__":main()
