#!/usr/bin/env python3
"""Regression suite: in-place NFSKR version/mod updates and safe rollback.

Runs only on TemporaryDirectory fixtures, NOT the user's Frosty install.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from test_nfskr_installer_core import fixture
from nfskr_installer_core import (
    InstallerError,digest_file,install_verified,rollback_install,snapshot,
    update_target,
)

class ReinstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.conf,self.manager,self.mods=fixture(self.root)
        self.counter=0
    def read(self):
        return json.loads(self.conf.read_text(encoding="utf8"))
    def write(self,d):
        self.conf.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    def cert(self,snap,tag,chosen=None):
        self.counter+=1
        merged=self.root/f"merged-{tag}-{self.counter}.fbmod"
        # Fixture base is an approved *test* header, not native in-game QA.
        merged.write_bytes((self.mods/"active.fbmod").read_bytes()+tag.encode("ascii"))
        file=self.root/f"certificate-{tag}-{self.counter}.json"
        inputs=list(snap.enabled_mods if chosen is None else chosen)
        data={
            "schema":"nfskr-composite-v1","status":"verified",
            "source_pack":snap.selected_pack,
            "source_pack_list":snap.source_pack_list,
            "config_sha256":snap.config_sha256,
            "enabled_mods":[{"filename":m.name,"sha256":m.sha256} for m in inputs],
            "verified_checks":{
                "frosty_reader":True,"locale_ebx_chunk_roundtrip":True,
                "source_resource_coverage":True,"font_resource_integrity":True,
                "no_unresolved_conflicts":True
            },
            "merged_fbmod":str(merged),
            "merged_sha256":digest_file(merged),
        }
        file.write_text(json.dumps(data,ensure_ascii=False),encoding="utf8")
        return file
    def install(self,tag,chosen=None):
        snap=snapshot(self.conf,self.manager,"Default")
        cert=self.cert(snap,tag,chosen=chosen)
        out=self.root/f"out-{tag}-{self.counter}"
        journal=install_verified(snap,cert,out,
                                 selected_sources=chosen,is_busy=lambda:False)
        return journal,out
    def change_sources(self):
        # Simulates importing a new third-party FBMod into original Default.
        info=self.read()
        (self.mods/"NEW-CAR.fbmod").write_bytes((self.mods/"active.fbmod").read_bytes())
        info["Games"]["NFS16"]["Packs"]["Default"]+="|NEW-CAR.fbmod:True"
        self.write(info)

    def test_update_reuses_selected_profile_and_preserves_old_fbmod(self):
        initial,firstout=self.install("v10")
        original=self.conf.read_bytes()
        previous=Path(initial["installed_composite"])
        old_sha=digest_file(previous)
        self.change_sources()
        second,secondout=self.install("v11")
        self.assertEqual(second["operation"],"update")
        self.assertEqual(second["new_pack"],"NFSKR")
        self.assertEqual(second["replaced_pack_entry"],previous.name+":True")
        self.assertEqual(second["previous_composite_sha256"],old_sha)
        cfg=self.read()["Games"]["NFS16"]
        self.assertEqual([x for x in cfg["Packs"] if x.startswith("NFSKR")],["NFSKR"])
        self.assertIn("NEW-CAR.fbmod:True",cfg["Packs"]["Default"])
        self.assertEqual(len(second["merged_source_mods"]),2)
        self.assertEqual(digest_file(previous),old_sha)
        self.assertTrue(Path(second["installed_composite"]).exists())
        self.assertEqual(cfg["Options"]["SelectedPack"],"NFSKR")
        recovered=rollback_install(
            secondout/("install-journal-"+second["installed_composite_sha256"][:12]+".json"),
            is_busy=lambda:False)
        self.assertTrue(recovered["restored_previous_version"])
        self.assertEqual(self.read()["Games"]["NFS16"]["Packs"]["NFSKR"],previous.name+":True")
        self.assertEqual(digest_file(previous),old_sha)
        self.assertFalse(Path(second["installed_composite"]).exists())
        # The older journal must still be reversible after one-version rollback.
        self.assertEqual(recovered["restored_pack"],"NFSKR")
        backup=secondout/("manager_config.before-"+second["installed_composite_sha256"][:12]+".json")
        self.assertEqual(self.conf.read_bytes(),backup.read_bytes())
        self.assertNotEqual(original,self.conf.read_bytes())

    def test_repeated_same_binary_keeps_referenced_old_file(self):
        first,_=self.install("SAME")
        oldfile=Path(first["installed_composite"])
        original=self.conf.read_bytes()
        newer,out=self.install("SAME")
        self.assertEqual(newer["operation"],"update")
        self.assertEqual(newer["installed_composite"],str(oldfile))
        self.assertFalse(newer["created_composite"])
        journal=next(out.glob("install-journal-*.json"))
        rollback_install(journal,is_busy=lambda:False)
        self.assertEqual(self.conf.read_bytes(),original)
        self.assertTrue(oldfile.exists())

    def test_previous_pack_stays_available_when_active_switched_to_default(self):
        first,_=self.install("OLDA")
        info=self.read()
        info["Games"]["NFS16"]["Options"]["SelectedPack"]="Default"
        self.write(info)
        update,out=self.install("NEWB")
        self.assertEqual(update["operation"],"update")
        self.assertEqual(update["new_pack"],"NFSKR")
        self.assertEqual(update["previous_pack"],"Default")
        rollback_install(next(out.glob("install-journal-*.json")),is_busy=lambda:False)
        after=self.read()["Games"]["NFS16"]
        self.assertEqual(after["Options"]["SelectedPack"],"Default")
        self.assertEqual(after["Packs"]["NFSKR"],Path(first["installed_composite"]).name+":True")

    def test_latest_existing_suffix_selected_without_new_profile(self):
        first,_=self.install("ORIGA")
        info=self.read()
        info["Games"]["NFS16"]["Packs"]["NFSKR-2"]=info["Games"]["NFS16"]["Packs"]["NFSKR"]
        info["Games"]["NFS16"]["Options"]["SelectedPack"]="NFSKR-2"
        self.write(info)
        upgrade,_=self.install("UPD2")
        self.assertEqual(upgrade["new_pack"],"NFSKR-2")
        self.assertNotIn("NFSKR-3",self.read()["Games"]["NFS16"]["Packs"])

    def test_update_does_not_overwrite_manual_mixed_profile(self):
        first,_=self.install("SAFEA")
        info=self.read()
        info["Games"]["NFS16"]["Packs"]["NFSKR"]+="|disabled.fbmod:True"
        self.write(info)
        previous=self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            self.install("SAFEB")
        self.assertEqual(self.conf.read_bytes(),previous)
        self.assertEqual([p.name for p in self.mods.glob("NFSKR-Composite-*.fbmod")],
                         [Path(first["installed_composite"]).name])

    def test_corrupted_existing_generated_asset_blocks(self):
        first,_=self.install("ORA")
        Path(first["installed_composite"]).write_bytes(b"TAMPER")
        previous=self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            self.install("ORB")
        self.assertEqual(self.conf.read_bytes(),previous)

    def test_mod_changed_after_certificate_blocks(self):
        first,_=self.install("ORIGINAL")
        snap=snapshot(self.conf,self.manager,"Default")
        cert=self.cert(snap,"NEXT")
        before=self.conf.read_bytes()
        (self.mods/"active.fbmod").write_bytes(b"TAMPER")
        with self.assertRaises(InstallerError):
            install_verified(snap,cert,self.root/"out-failed",
                             is_busy=lambda:False)
        self.assertEqual(self.conf.read_bytes(),before)

    def test_update_rollback_refuses_later_user_frosty_edit(self):
        self.install("START")
        newer,out=self.install("END")
        info=self.read()
        info["Games"]["NFS16"]["Packs"]["Other"]="active.fbmod:False"
        self.write(info)
        before=self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            rollback_install(next(out.glob("install-journal-*.json")),
                             is_busy=lambda:False)
        self.assertEqual(before,self.conf.read_bytes())

    def test_rollback_refuses_missing_old_binary(self):
        first,_=self.install("OLD")
        second,out=self.install("NEW")
        Path(first["installed_composite"]).unlink()
        before=self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            rollback_install(next(out.glob("install-journal-*.json")),
                             is_busy=lambda:False)
        self.assertEqual(self.conf.read_bytes(),before)
        self.assertTrue(Path(second["installed_composite"]).exists())

    def test_selected_profile_is_preferred_over_latest_suffix(self):
        self.install("ORIGA")
        info=self.read()
        entry=info["Games"]["NFS16"]["Packs"]["NFSKR"]
        info["Games"]["NFS16"]["Packs"]["NFSKR-2"]=entry
        info["Games"]["NFS16"]["Options"]["SelectedPack"]="NFSKR"
        self.write(info)
        second,_=self.install("UPDT")
        self.assertEqual(second["new_pack"],"NFSKR")

    def test_shortcut_reuse_does_not_create_or_delete_another_link(self):
        from unittest.mock import patch
        from nfskr_shortcuts import create_shortcuts
        exe=self.manager/"FrostyModManager.exe"
        exe.write_bytes(b"fixture")
        desktop=self.root/"desktop"
        desktop.mkdir()
        old=desktop/"Need for Speed 2015 (한국어 패치 v1.1).lnk"
        old.write_bytes(b"intact-owned-shortcut")
        with patch("nfskr_shortcuts.inspect_shortcut",return_value={
            "target":str(exe),"arguments":"-launch NFSKR-2",
            "workdir":str(self.manager),
        }) as inspected,patch("nfskr_shortcuts._create_shortcut") as created:
            records=create_shortcuts(manager=self.manager,
                      game=self.root/"game",pack="NFSKR-2",
                      frosty=False,game_shortcut=True,reuse_existing=True,
                      desktop=desktop,log=lambda _:None)
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]["path"],str(old))
            self.assertFalse(records[0]["created"])
            self.assertEqual(old.read_bytes(),b"intact-owned-shortcut")
            created.assert_not_called()
            self.assertEqual(inspected.call_count,1)

    def test_failed_transaction_leaves_old_pack_and_config_unchanged(self):
        from unittest.mock import patch
        import nfskr_installer_core as core
        first,_=self.install("PREVIOUS")
        old=self.conf.read_bytes()
        oldmod=Path(first["installed_composite"])
        snap=snapshot(self.conf,self.manager,"Default")
        certificate=self.cert(snap,"NEXT")
        original_replace=core.os.replace
        def fail_commit(source,destination):
            if Path(destination)==self.conf:
                raise OSError("Simulated Windows config write failure")
            return original_replace(source,destination)
        with patch.object(core.os,"replace",side_effect=fail_commit):
            with self.assertRaises(OSError):
                install_verified(snap,certificate,self.root/"failed-next",
                                 is_busy=lambda:False)
        self.assertEqual(self.conf.read_bytes(),old)
        self.assertTrue(oldmod.is_file())
        self.assertFalse(list(self.mods.glob("NFSKR-Composite-*.nfskr-staging")))
        self.assertEqual(
            [p.name for p in self.mods.glob("NFSKR-Composite-*.fbmod")],
            [oldmod.name])
        self.assertFalse(list((self.root/"failed-next").glob("install-journal-*")))

    def test_numerically_latest_suffix_and_manual_existing_pack(self):
        first,_=self.install("OLDC")
        info=self.read()
        existing=info["Games"]["NFS16"]["Packs"]["NFSKR"]
        for number in (2,3,10):
            info["Games"]["NFS16"]["Packs"][f"NFSKR-{number}"]=existing
        info["Games"]["NFS16"]["Options"]["SelectedPack"]="Default"
        self.write(info)
        target,updating=update_target(info["Games"]["NFS16"]["Packs"],
                                     self.mods,"Default")
        self.assertTrue(updating)
        self.assertEqual(target,"NFSKR-10")
        actual,_=self.install("NEWC")
        self.assertEqual(actual["new_pack"],"NFSKR-10")


if __name__=="__main__":
    unittest.main(verbosity=2)
