#!/usr/bin/env python3
"""Actual licensed NFS2015 original + Handling Overhaul local fixtures."""
import csv
import json
from pathlib import Path
import unittest
import nfskr_locale_codec as c
from nfskr_fbmod_format import parse_mod

ROOT=Path(__file__).resolve().parent.parent
QA=ROOT/"work/second-pass-QA"
MODS=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager/Mods/NFS16"

class CodecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=(QA/"en_us-original.binchunk").read_bytes()
        cls.h=(QA/"en_us-original.histchunk").read_bytes()
        cls.section=cls.b[20:cls.b.find(b"\0",20)].decode("ascii")
    def test_vanilla_original_against_extracted_csv(self):
        o=c.read_strings(self.b,self.h)
        with (ROOT/"work/locale-extract/en-strings.csv").open(encoding="utf-8-sig",newline="") as f:
            baseline={r["string_id"].upper():r["source_text"] for r in csv.DictReader(f)}
        self.assertEqual(o,baseline)
        print("ORIGINAL_DECODE_MATCHES_CSV",len(o),"section",repr(self.section))
    def test_merged_hangul_histogram(self):
        src=c.read_strings(self.b,self.h)
        ko=json.loads((ROOT/"work/full-build/qa-v0.1.2/strings.json").read_text(encoding="utf-8"))
        for entry in ko["entries"]:src[entry["id"]]=entry["ko"]
        b,h=c.write_locale(src,section=self.section)
        self.assertEqual(c.read_strings(b,h),src)
        self.assertTrue(any("한글" in s for s in src.values()) or any("계속" in s for s in src.values()))
        print("KOREAN_DB_ENCODE_ROUNDTRIP",len(src),"binary",len(b),"hist",len(h))
    def test_frostbite_lz4_frames(self):
        handling=parse_mod(MODS/"Handling Overhaul 2.0.fbmod")
        chunks=[e for e in handling.entries if e.kind==3 and e.name.lower()=="2d8c69ad-e5d6-645e-0c7b-797023592a91"]
        self.assertEqual(len(chunks),1)
        decoded=c.decompress_frostbite(chunks[0].payload)
        self.assertEqual(len(decoded),589205)
        packed=c.compress_frostbite(decoded)
        self.assertEqual(c.decompress_frostbite(packed),decoded)
        print("HANDLING_FROSTBITE_REPACK",len(chunks[0].payload),len(packed))
    def test_frostbite_framed_raw(self):
        import os
        original=bytes(range(256))*300
        packed=c.compress_frostbite(original)
        self.assertEqual(c.decompress_frostbite(packed),original)

if __name__=="__main__":unittest.main(verbosity=2)
