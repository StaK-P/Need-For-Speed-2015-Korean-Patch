#!/usr/bin/env python3
"""Frosty .fbmod v1/v3/v5 read-and-v5-roundtrip tests on temporary files."""
from pathlib import Path
from collections import Counter
import hashlib
import tempfile
import unittest
from nfskr_fbmod_format import parse_mod,make_mod

ROOT=Path(__file__).resolve().parent.parent
MODS=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager/Mods/NFS16"
KOREAN=ROOT/"work/full-build/qa-v0.1.2/NFS16-Korean-QA-v0.1.2-local.fbmod"

class FormatTests(unittest.TestCase):
    def test_all_installed_mods_read_only(self):
        for path in sorted(MODS.glob("*.fbmod")):
            with self.subTest(mod=path.name):
                m=parse_mod(path)
                self.assertEqual(m.game_version,366510)
                self.assertGreaterEqual(len(m.entries),1)
                print("FORMAT_INPUT",path.name,"v"+str(m.version),
                      len(m.entries),len(set(x.identity() for x in m.entries)),
                      dict(Counter(x.kind for x in m.entries)))
    def test_old_handling_roundtrip(self):
        source=MODS/"Handling Overhaul 2.0.fbmod"
        original=hashlib.sha256(source.read_bytes()).hexdigest()
        m=parse_mod(source)
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"handling-as-v5.fbmod"
            make_mod(m.entries,dest,"Temporary unshipped tester")
            b=parse_mod(dest)
            self.assertEqual(len(b.entries),len(m.entries))
            self.assertEqual(b.version,5)
        self.assertEqual(original,hashlib.sha256(source.read_bytes()).hexdigest())
    def test_korean_roundtrip(self):
        m=parse_mod(KOREAN)
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"Korean-test.fbmod"
            make_mod(m.entries,dest,"Temporary QA test")
            self.assertEqual(len(parse_mod(dest).entries),9)
    def test_all_v5_normalize(self):
        files=[
            MODS/"UNITE NFS15 2.0.fbmod",
            MODS/"Lamborghini Aventador K.S Kit.fbmod",
            MODS/"Mercedes Benz AMG GT Prior Bodykit + Mansory Hood and GT Wing.fbmod",
            MODS/"Intro_Video_Remover.fbmod",
            MODS/"no letterbox.fbmod"
        ]
        with tempfile.TemporaryDirectory() as td:
            for index,source in enumerate(files):
                with self.subTest(mod=source.name):
                    m=parse_mod(source)
                    dest=Path(td)/f"mod{index}.fbmod"
                    make_mod(m.entries,dest,"Preview normalized")
                    self.assertEqual(len(parse_mod(dest).entries),len(m.entries))
                    dest.unlink()
if __name__=="__main__":
    unittest.main(verbosity=2)
