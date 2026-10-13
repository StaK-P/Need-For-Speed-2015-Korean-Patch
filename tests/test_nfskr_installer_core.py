#!/usr/bin/env python3
"""Tests on temporary local fixtures only; never mutates real Frosty."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from nfskr_installer_core import (
    InstallerError, digest_file, install_verified, preview,
    rollback_install, snapshot, validate_composite_header, write_fbpack,
)

ROOT = Path(__file__).resolve().parent.parent
REAL_FBM = ROOT / "work/full-build/qa-v0.1.2/NFS16-Korean-QA-v0.1.2-local.fbmod"


def fixture(work: Path):
    game = work / "game"
    game.mkdir()
    (game / "NFS16.exe").write_bytes(b"mock, not actually executable")
    manager = work / "frosty" / "FrostyModManager"
    mods = manager / "Mods" / "NFS16"
    mods.mkdir(parents=True)
    # Use a legal local user's real Frosty mod binary for header/pack tests.
    if REAL_FBM.exists():
        source = REAL_FBM.read_bytes()
    else:
        # Test header is not an in-game valid merged mod, only a mocked input.
        import struct
        data = bytearray(struct.pack("<QIqiB", 0x01005954534F5246,5,40,1,5))
        data += b"NFS16" + struct.pack("<i",366510) + b"A" * 64
        source=bytes(data)
    (mods/"active.fbmod").write_bytes(source)
    (mods/"disabled.fbmod").write_bytes(source)
    (mods/"NFS16-Korean-QA-old.fbmod").write_bytes(source)
    conf = work / "manager_config.json"
    conf.write_text(json.dumps({
        "Games":{"NFS16":{
            "GamePath":str(game),
            "Options":{"SelectedPack":"Default"},
            "Packs":{"Default":"active.fbmod:True|disabled.fbmod:False|NFS16-Korean-QA-old.fbmod:True",
                     "Other":"active.fbmod:True"}
        }},
        "GlobalOptions":{"ApplyModOrder":"List"}
    },indent=2),encoding="utf8")
    return conf, manager, mods


class InstallerCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.conf,self.manager,self.mods=fixture(self.root)
        self.snap=snapshot(self.conf,self.manager)

    def tearDown(self):
        self.tmp.cleanup()

    def certificate(self):
        merged=self.root/"merged.fbmod"
        merged.write_bytes((self.mods/"active.fbmod").read_bytes())
        return self.root/"merged-certificate.json", merged

    def full_certificate(self):
        name, merged=self.certificate()
        data={
            "schema":"nfskr-composite-v1","status":"verified",
            "source_pack":self.snap.selected_pack,
            "source_pack_list":self.snap.source_pack_list,
            "config_sha256":self.snap.config_sha256,
            "enabled_mods":[{"filename":m.name,"sha256":m.sha256} for m in self.snap.enabled_mods],
            "verified_checks":{
                "frosty_reader":True,"locale_ebx_chunk_roundtrip":True,
                "source_resource_coverage":True,"font_resource_integrity":True,
                "no_unresolved_conflicts":True,
            },
            "merged_fbmod":str(merged),"merged_sha256":digest_file(merged),
        }
        name.write_text(json.dumps(data),encoding="utf8")
        return name,merged

    def test_empty_mod_profile_supported(self):
        config = json.loads(self.conf.read_text(encoding="utf8"))
        config["Games"]["NFS16"]["Packs"]["Default"] = ""
        self.conf.write_text(json.dumps(config), encoding="utf8")
        empty=snapshot(self.conf,self.manager)
        self.assertEqual(len(empty.enabled_mods),0)
        self.assertEqual(empty.selected_pack,"Default")

    def test_snapshot_enabled_order_and_disabled(self):
        self.assertEqual(self.snap.selected_pack,"Default")
        self.assertEqual([x.name for x in self.snap.enabled_mods],["active.fbmod"])
        self.assertEqual([x.name for x in self.snap.disabled_mods],["disabled.fbmod"])
        self.assertEqual(len(preview(self.snap)["enabled_mods"]),1)
        self.assertEqual([x.name for x in self.snap.replaced_korean_mods],["NFS16-Korean-QA-old.fbmod"])

    def test_incomplete_certificate_blocks_changes(self):
        path,merged=self.certificate()
        path.write_text('{"schema":"nfskr-composite-v1","status":"unverified"}')
        original=self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            install_verified(self.snap,path,self.root/"out",is_busy=lambda:False)
        self.assertEqual(self.conf.read_bytes(),original)

    def test_unsupported_semantic_policy_blocks_install(self):
        cert, merged = self.full_certificate()
        values = json.loads(cert.read_text(encoding="utf8"))
        values["untranslated_fallback_count"] = 3
        values["semantic_conflict_policy"] = "unknown"
        cert.write_text(json.dumps(values), encoding="utf8")
        before = self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            install_verified(self.snap, cert, self.root/"out", is_busy=lambda:False)
        self.assertEqual(before, self.conf.read_bytes())

    def test_automatic_semantic_fallback_install(self):
        cert, merged = self.full_certificate()
        values = json.loads(cert.read_text(encoding="utf8"))
        values["untranslated_fallback_count"] = 3
        values["semantic_conflict_policy"] = "preserve_mod_text"
        cert.write_text(json.dumps(values), encoding="utf8")
        journal = install_verified(self.snap, cert, self.root/"out", is_busy=lambda:False)
        self.assertTrue(Path(journal["created_archive"]).is_file())
        self.assertTrue(journal["new_pack"].isascii())

    def test_frosty_running_prevents_install(self):
        cert,merged=self.full_certificate()
        original=self.conf.read_bytes()
        with self.assertRaises(InstallerError):
            install_verified(self.snap,cert,self.root/"out",is_busy=lambda:True)
        self.assertEqual(self.conf.read_bytes(),original)

    def test_tampered_mod_blocks_install(self):
        cert,merged=self.full_certificate()
        (self.mods/"active.fbmod").write_bytes(b"mutated")
        with self.assertRaises(InstallerError):
            install_verified(self.snap,cert,self.root/"out",is_busy=lambda:False)
        self.assertEqual(json.loads(self.conf.read_text())["Games"]["NFS16"]["Options"]["SelectedPack"],"Default")

    def test_changed_profile_blocks_install(self):
        cert,merged=self.full_certificate()
        info=json.loads(self.conf.read_text(encoding="utf8"))
        info["Games"]["NFS16"]["Options"]["SelectedPack"]="Other"
        self.conf.write_text(json.dumps(info),encoding="utf8")
        with self.assertRaises(InstallerError):
            install_verified(self.snap,cert,self.root/"out",is_busy=lambda:False)

    def test_local_fbpack_roundtrip(self):
        cert,merged=self.full_certificate()
        validate_composite_header(merged)
        import zipfile
        out=self.root/"pack.fbpack"
        result=write_fbpack(out,merged,pack_name="NFSKR")
        self.assertEqual(result,digest_file(out))
        with zipfile.ZipFile(out) as archive:
            manifest=json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["name"],"NFSKR")
            self.assertEqual(manifest["mods"],["merged.fbmod"])

    def test_transaction_changes_new_pack_only(self):
        cert,merged=self.full_certificate()
        original=self.conf.read_bytes()
        output=self.root/"out"
        journal=install_verified(self.snap,cert,output,is_busy=lambda:False)
        updated=json.loads(self.conf.read_text(encoding="utf8"))
        self.assertEqual(updated["Games"]["NFS16"]["Packs"]["Default"],
                         "active.fbmod:True|disabled.fbmod:False|NFS16-Korean-QA-old.fbmod:True")
        self.assertEqual(updated["Games"]["NFS16"]["Options"]["SelectedPack"],"NFSKR")
        self.assertEqual(updated["Games"]["NFS16"]["Packs"]["Other"],"active.fbmod:True")
        self.assertEqual((output/("manager_config.before-"+digest_file(merged)[:12]+".json")).read_bytes(),original)
        self.assertTrue(Path(journal["installed_composite"]).exists())
        self.assertTrue(Path(journal["created_archive"]).exists())

    def test_reinstall_requires_original_source_pack(self):
        cert, merged = self.full_certificate()
        install_verified(self.snap,cert,self.root/"out",is_busy=lambda:False)
        with self.assertRaises(InstallerError):
            snapshot(self.conf,self.manager)
        old_source=snapshot(self.conf,self.manager,source_pack="Default")
        self.assertEqual(old_source.selected_pack,"Default")
        self.assertEqual([v.name for v in old_source.enabled_mods],["active.fbmod"])

    def test_upgrade_old_korean_pack_rolls_back_to_original_source(self):
        # The old Frosty Unicode-named pack triggers broken UTF-8 mklink BAT.
        # Installing the new ASCII NFSKR pack must keep the old entry but
        # offer rollback to the original Default source, not old broken pack.
        info=json.loads(self.conf.read_text(encoding="utf8"))
        info["Games"]["NFS16"]["Packs"]["한글패치"]="NFSKR-Composite-old.fbmod:True"
        info["Games"]["NFS16"]["Options"]["SelectedPack"]="한글패치"
        self.conf.write_text(json.dumps(info,ensure_ascii=False),encoding="utf8")
        self.snap=snapshot(self.conf,self.manager,source_pack="Default")
        cert,merged=self.full_certificate()
        output=self.root/"out"
        journal=install_verified(self.snap,cert,output,is_busy=lambda:False)
        self.assertEqual(journal["original_selected_pack"],"한글패치")
        self.assertEqual(journal["previous_pack"],"Default")
        self.assertEqual(journal["new_pack"],"NFSKR")
        token=digest_file(merged)[:12]
        result=rollback_install(output/f"install-journal-{token}.json",
                                is_busy=lambda:False)
        self.assertEqual(result["restored_pack"],"Default")
        current=json.loads(self.conf.read_text(encoding="utf8"))["Games"]["NFS16"]
        self.assertEqual(current["Options"]["SelectedPack"],"Default")
        self.assertIn("한글패치",current["Packs"])

    def test_checked_subset_can_include_previously_disabled_mod(self):
        cert,merged=self.full_certificate()
        chosen=[self.snap.disabled_mods[0]]
        info=json.loads(cert.read_text(encoding="utf8"))
        info["enabled_mods"]=[{"filename":m.name,"sha256":m.sha256} for m in chosen]
        cert.write_text(json.dumps(info),encoding="utf8")
        original=self.conf.read_bytes()
        journal=install_verified(self.snap,cert,self.root/"out",
                                 selected_sources=chosen,is_busy=lambda:False)
        assert [x["filename"] for x in journal["merged_source_mods"]]==["disabled.fbmod"]
        cfg=json.loads(self.conf.read_text(encoding="utf8"))
        assert cfg["Games"]["NFS16"]["Packs"]["Default"]=="active.fbmod:True|disabled.fbmod:False|NFS16-Korean-QA-old.fbmod:True"
        token=digest_file(merged)[:12]
        rollback_install(self.root/"out"/f"install-journal-{token}.json",is_busy=lambda:False)
        assert self.conf.read_bytes()==original

    def test_checked_empty_mods_valid_for_korean_only(self):
        cert,merged=self.full_certificate()
        info=json.loads(cert.read_text(encoding="utf8"))
        info["enabled_mods"]=[]
        cert.write_text(json.dumps(info),encoding="utf8")
        journal=install_verified(self.snap,cert,self.root/"out",
                                 selected_sources=[],is_busy=lambda:False)
        assert journal["merged_source_mods"]==[]
        cfg=json.loads(self.conf.read_text(encoding="utf8"))
        assert cfg["Games"]["NFS16"]["Packs"]["Default"].startswith("active.fbmod:True")

    def test_unique_ascii_profile_when_previous_nfskr_exists(self):
        original=json.loads(self.conf.read_text(encoding="utf8"))
        original["Games"]["NFS16"]["Packs"]["NFSKR"]="active.fbmod:True"
        self.conf.write_text(json.dumps(original),encoding="utf8")
        self.snap=snapshot(self.conf,self.manager)
        cert,merged=self.full_certificate()
        journal=install_verified(self.snap,cert,self.root/"out",is_busy=lambda:False)
        assert journal["new_pack"]=="NFSKR-2",journal["new_pack"]
        assert journal["new_pack"].isascii()
        assert " " not in journal["new_pack"]

    def test_rollback_restores_original_default(self):
        cert, merged = self.full_certificate()
        original = self.conf.read_bytes()
        output = self.root / "out"
        journal = install_verified(self.snap, cert, output, is_busy=lambda: False)
        token = digest_file(merged)[:12]
        result = rollback_install(output / f"install-journal-{token}.json", is_busy=lambda: False)
        self.assertEqual(result["restored_pack"], "Default")
        self.assertEqual(self.conf.read_bytes(), original)
        self.assertFalse(Path(journal["installed_composite"]).exists())
        self.assertTrue(Path(journal["created_archive"]).exists())

    def test_rollback_rejects_user_changed_config(self):
        cert, merged = self.full_certificate()
        output = self.root / "out"
        journal = install_verified(self.snap, cert, output, is_busy=lambda: False)
        token = digest_file(merged)[:12]
        modified = json.loads(self.conf.read_text(encoding="utf8"))
        modified["Games"]["NFS16"]["Packs"]["Other"] = "disabled.fbmod:True"
        self.conf.write_text(json.dumps(modified),encoding="utf8")
        with self.assertRaises(InstallerError):
            rollback_install(output / f"install-journal-{token}.json", is_busy=lambda: False)
        self.assertTrue(Path(journal["installed_composite"]).exists())


if __name__=="__main__":
    unittest.main(verbosity=2)
