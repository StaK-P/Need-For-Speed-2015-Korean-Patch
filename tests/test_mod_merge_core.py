#!/usr/bin/env python3
"""Tests for the release-bound NFSKR text merge policy (no game actions)."""
import csv
import json
from pathlib import Path
import unittest
from mod_merge_core import merge_localization, report, preserves_markup

ROOT=Path(__file__).resolve().parent.parent
class TextMerge(unittest.TestCase):
    def test_independent_mod_data(self):
        out,items=merge_localization({"00000001":"Spring","00000002":"Sway Bar"},
                                     {"00000001":"Spring","00000002":"Final Drive"},
                                     {"00000001":"스프링","00000002":"스웨이 바"})
        self.assertEqual(out["00000001"],"스프링")
        self.assertEqual(out["00000002"],"Final Drive")
        self.assertTrue(any(x.needs_translation for x in items))
    def test_curated_mod_variant(self):
        out,items=merge_localization({"00000002":"Sway Bar"},
                                     {"00000002":"Final Drive"},
                                     {"00000002":"스웨이 바"},
                                     {"00000002":"종감속비"})
        self.assertEqual(out["00000002"],"종감속비")
        self.assertEqual(items[0].decision,"reviewed_mod_translation")
    def test_cosmetic_punctuation(self):
        out,items=merge_localization({"00000002":"Hey…{1.0-1.5}"},
                                     {"00000002":"Hey?{1.0-1.5}"},
                                     {"00000002":"안녕…{1.0-1.5}"})
        self.assertEqual(out["00000002"],"안녕…{1.0-1.5}")
        self.assertEqual(items[0].decision,"safe_typography_or_icon_normalization")
    def test_trademark_diacritic_changes_preserve_korean(self):
        out, items=merge_localization(
            {"00000001":"Need for Speed™ Network",
             "00000002":"Performed by Trentemøller"},
            {"00000001":"Need for Speed Network",
             "00000002":"Performed by Trentemoller"},
            {"00000001":"Need for Speed™ 네트워크",
             "00000002":"아티스트: Trentemøller"})
        self.assertEqual(out["00000001"],"Need for Speed™ 네트워크")
        self.assertEqual(out["00000002"],"아티스트: Trentemøller")
        self.assertEqual([x.decision for x in items],
                         ["safe_typography_or_icon_normalization"]*2)

    def test_corrupted_rep_icon_is_restored(self):
        out, items=merge_localization(
            {"00000001":"1000\ue000 Earned","00000002":"EARNING REPUTATION \ue000"},
            {"00000001":"1000 REP Earned","00000002":"EARNING REPUTATION "},
            {"00000001":"1000\ue000 획득","00000002":"REP 획득 중 \ue000"})
        self.assertEqual(out["00000001"],"1000\ue000 획득")
        self.assertEqual(out["00000002"],"REP 획득 중 \ue000")

    def test_external_added_id_preserved(self):
        output,items=merge_localization({"00000001":"a"},{"FFFFFFFF":"b"},{})
        self.assertEqual(output["FFFFFFFF"],"b")
        self.assertEqual(items[0].decision,"external_new_id")
    def test_reviewed_rule_cannot_drop_variables(self):
        with self.assertRaises(ValueError):
            merge_localization({"00000001":"More {0:s}"},
                {"00000001":"Faster {0:s}"},{"00000001":"더 보기 {0:s}"},
                {"00000001":"빨라짐"})
    def test_original_removed_id_respected(self):
        out,items=merge_localization({"00000001":"A"},{"00000001":"A"},{"00000001":"가"},base_deleted_ids={"00000001"})
        self.assertNotIn("00000001",out)
        self.assertEqual(items[0].decision,"removed_by_external")
    def test_handling_overhaul_real_fixture(self):
        src=ROOT/"work/locale-extract/en-strings.csv"
        diff=ROOT/"work/second-pass-QA/handling-english-strings-diff.json"
        ko_cfg=ROOT/"work/full-build/qa-v0.1.2/strings.json"
        if not src.exists() or not diff.exists() or not ko_cfg.exists():
            self.skipTest("Local licensed game fixtures unavailable")
        with src.open(encoding="utf-8-sig",newline="") as f:
            base={r["string_id"].upper():r["source_text"] for r in csv.DictReader(f)}
        obj=json.loads(diff.read_text(encoding="utf8"))
        external={k:val["handling"] for k,val in obj["changed"].items() if val["handling"] is not None}
        patches=json.loads(ko_cfg.read_text(encoding="utf8"))
        korean={e["id"].upper():e["ko"] for e in patches["entries"]}
        out,items=merge_localization(base,external,korean,base_deleted_ids=set(obj["removed_keys"]))
        self.assertEqual(len(out),10249)
        self.assertNotIn("FFF69B89",out)
        self.assertEqual(out["3D35E64E"],"Drivetrain ")
        self.assertEqual(out["319FED3F"]," ")
        self.assertEqual(out["660C5CB2"]," 버튼을 눌러 계속")
        self.assertGreater(report(items)["manual_review_count"],30)
        self.assertIn("unresolved_semantic_collision",report(items)["decision_counts"])
        self.assertEqual(obj["source_mod_sha256"],
            "94BD4658692020624F704FB9E24F29D1A64893B72D94971E9548361EBFB8A2D8")
if __name__=="__main__":unittest.main()
