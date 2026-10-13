#!/usr/bin/env python3
"""Independent decoded NFSKR combined-FBMod QA (no real install/game launch).

Uses our Frosty format reader + native .NET Frosty Flammenwerfer local decoder
and SDK EBX reader as independent checks. This does not certify in-game
gameplay and must not be mistaken for it.
"""
from __future__ import annotations
import argparse,hashlib,json,struct,subprocess, tempfile
from pathlib import Path
from nfskr_fbmod_format import parse_mod
from nfskr_locale_codec import decompress_frostbite,read_strings
from nfskr_composite import RT,QA,ROOT,BIN_GUID,HIST_GUID,EN_US,FONTS,build_resource_stage,enforce_asset_coverage,KOREAN,KOREAN_HASH
from nfskr_installer_core import digest_file,snapshot

def run_checks(fbmod:Path,expected:int,report:Path,output:Path,
               korean_file:Path=KOREAN,manager_path:Path|None=None):
    original=json.loads(report.read_text(encoding="utf8"))
    parsed=parse_mod(fbmod)
    entries={(r.kind,r.name.lower()):r for r in parsed.entries}
    ebx=entries[(1,EN_US)]
    bn=entries[(3,BIN_GUID)]
    hist=entries[(3,HIST_GUID)]
    raw_ebx=decompress_frostbite(ebx.payload)
    raw_bin=decompress_frostbite(bn.payload)
    raw_hist=decompress_frostbite(hist.payload)
    values=read_strings(raw_bin,raw_hist)
    if len(values)!=expected:raise ValueError("Decoded string count mismatch")
    if values["660C5CB2"]!=" 버튼을 눌러 계속":
        raise ValueError("Title hint is not frozen Korean 1st release")
    if expected==10249:
        if values["3D35E64E"]!="구동계":
            raise ValueError("Handling driveline translation absent")
        if values["B2FFF70A"]!="구동계":
            raise ValueError("Handling gameplay metadata absent")
        if "FFF69B89" in values:
            raise ValueError("Handling deleted text ID resurrected")
    fonts=[e for e in parsed.entries if e.kind==2 and e.name.lower() in FONTS]
    if len(fonts)!=3:raise ValueError("Missing Korean fonts")
    frozen=parse_mod(korean_file)
    frozen_fonts={e.name.lower():e.payload for e in frozen.entries if e.kind==2 and e.name.lower() in FONTS}
    if any(e.payload!=frozen_fonts.get(e.name.lower()) for e in fonts):
        raise ValueError("Korean font bytes changed in composite")
    with tempfile.TemporaryDirectory(prefix="nfskr-verify-",dir=output) as td:
        location=Path(td)
        (location/"merged.enus.ebx").write_bytes(raw_ebx)
        (location/"strings.bin").write_bytes(raw_bin)
        (location/"hist.bin").write_bytes(raw_hist)
        decoder=RT/"NfsKRNativeLocaleCheck.exe"
        if not decoder.is_file():raise FileNotFoundError("Frosty native decoder not installed")
        c=subprocess.run([str(decoder),str(location/"hist.bin"),str(location/"strings.bin"),str(expected)],
            cwd=str(RT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            encoding="utf8",errors="replace",timeout=100,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if c.returncode or "NFSKR_NATIVE_LOCALE_DECODE_PASS" not in c.stdout:
            raise ValueError("Independent C# NFS16 localization decoder failed: "+c.stdout+c.stderr)
        packer=RT/"NfsKREbxRepack.exe"
        c=subprocess.run([str(packer),str(location/"merged.enus.ebx"),str(len(raw_bin)),
                str(len(raw_hist)),str(location/"repacked-check.ebx")],
            cwd=str(RT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            encoding="utf8",errors="replace",timeout=100,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if c.returncode or "NFSKR_EBX_ROUNDTRIP_PASS" not in c.stdout:
            raise ValueError("Frosty NFS16 EBX reader verification failed: "+c.stdout+c.stderr)
    # Re-read source files rather than trusting the merger audit report.
    from nfskr_installer_core import ModInput
    manager=manager_path if manager_path is not None else ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
    sources=[]
    for item in original["original_gameplay_mods"]:
        path=manager/"Mods"/"NFS16"/item["filename"]
        if digest_file(path)!=item["sha256"]:raise ValueError("Source mod hash changed")
        sources.append(ModInput(item["filename"],path,item["sha256"],path.stat().st_size,True))
    expected_stage,_,_,_=build_resource_stage(sources)
    source_coverage=enforce_asset_coverage(expected_stage,parsed.entries,fonts)
    if source_coverage!=original["preserved_source_assets"]:
        raise ValueError("Source gameplay asset coverage changed")
    native_reader=RT/"AuditNfsModResources.exe"
    c=subprocess.run([str(native_reader),str(fbmod)],cwd=str(RT),stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,encoding="utf8",errors="replace",timeout=180,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    expected_marker=f"RESOURCES={len(parsed.entries)}"
    if c.returncode!=0 or expected_marker not in c.stdout or "FORMAT=5 VERSION=366510" not in c.stdout:
        raise ValueError("Frosty native FBMod reader rejected composite: "+c.stdout+c.stderr)
    out={
     "state":"static_verified_not_ingame",
     "combined_fbmod":str(fbmod),
     "sha256":digest_file(fbmod),
     "Frosty_game_version":parsed.game_version,
     "Frosty_format_version":parsed.version,
     "resource_count":len(parsed.entries),
     "locale_strings":len(values),
     "locale_bin_bytes":len(raw_bin),
     "locale_hist_bytes":len(raw_hist),
     "raw_ebx_bytes":len(raw_ebx),
     "native_flammenwerfer_decoded":True,
     "native_independent_csharp_locale_decoder":True,
     "native_ebx_roundtrip":True,
     "font_resource_count":3,
     "source_gameplay_resource_count":source_coverage,
     "native_frosty_reader":True,
     "font_payload_identical_to_frozen_first_release":True,
     "source_mods":original["original_gameplay_mods"],
     "ingame_verified":False,
     "frosty_profile_modified":False,
    }
    outpath=output/"independent-validation-v2.json"
    if outpath.exists():raise FileExistsError(outpath)
    outpath.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("NFSKR_INDEPENDENT_NATIVE_VALIDATION_PASS",json.dumps(out,ensure_ascii=True))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dir",type=Path,required=True)
    parser.add_argument("--expected",type=int,required=True)
    args=parser.parse_args()
    roots=list(args.dir.glob("NFSKR-Merged-*.fbmod"))
    if len(roots)!=1:raise ValueError("Expected exactly one generated FBMod")
    run_checks(roots[0],args.expected,args.dir/"composite-qa-report.json",args.dir)
if __name__=="__main__":
    main()
