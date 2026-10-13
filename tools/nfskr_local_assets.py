#!/usr/bin/env python3
"""NFSKR on-device licensed-font/base-localization preparation.

Public installer includes ONLY redistributable OFL donor fonts (and licenses),
user's Korean text translation, our own helper EXEs and Python code.
Game-owned DIN font and English source assets are generated locally from the
user's existing licensed NFS16 installation. No source mods or EA data are
ever uploaded or installed in game's original directories.
"""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

from nfskr_installer_core import digest_file,InstallerError
from nfskr_fbmod_format import parse_mod

SRCROOT=Path(__file__).resolve().parent.parent
FROZEN_SHA="B488A0D396922E12A36C45EFA7988B60AEC3D7C704606855189EABD69EB22F7A"
FROZEN_REL=Path("translations/nfskr-first-release-v1.1.json")
NATIVE=(
    "NfsLocaleDump.exe","DumpOriginalEnUsQA.exe","ExportFontQA011.exe",
    "NfsKREbxRepack.exe","AuditNfsModResources.exe","NfsKRNativeLocaleCheck.exe",
)
FONTS=(
  ("vendor","SUIT-Medium.ttf"),
  ("vendor","SUITE-Heavy.ttf"),
  ("derived","NFSKR-UI-Text-SemiBold.ttf"),
)
LICENSES=("SUITE-OFL-LICENSE.txt","SUIT-OFL-LICENSE.txt","pretendard-OFL-LICENSE.txt")
SCRIPTS=("merge-game-fonts.py","build-korean-punctuation-qa.py","build-poc-mod.py")
DEPENDENCIES=("FrostySdk.dll","FrostyHash.dll","FrostyCore.dll")
GENERATOR_VERSION=2
# Independent generated fonts and mod prevent reuse of v1.0 caches.
USER_LOCAL=Path("work/full-build/user-local/v1.1")
FINGERPRINT=Path("asset-source-fingerprint-v1.1.json")


def bundled_files()->Path:
    root=Path(getattr(sys,"_MEIPASS",SRCROOT))
    packaged=root/"bundle_assets"
    if packaged.is_dir():return packaged
    # Development-time source-only fallback. Never ship the original .external
    # game files as data in the frozen executable.
    return SRCROOT


def candidate_asset(src:Path,group:str,name:str)->Path:
    if (src/"bundle_assets").is_dir():
        return src/"bundle_assets"/group/name
    if (src/"fonts").is_dir():
        return src/"fonts"/group/name
    # User's dev source tree as fallback.
    if group=="fonts/vendor" or group=="fonts/derived":
        return src/".external"/group/name
    if group=="licenses":
        return src/".external/fonts/vendor"/name
    if group=="native":
        return src/"work/locale-extract/runtime"/name
    if group=="scripts":
        return src/"tools"/name
    if group=="translation":
        return src/"translations"/name
    raise InstallerError("No bundled source for "+group+"/"+name)


def locate(group:str,name:str)->Path:
    parent=bundled_files()
    if parent.name=="bundle_assets":
        location=parent/group/name
    else:
        location=candidate_asset(parent,group,name)
    if not location.is_file():
        raise InstallerError(f"Installer payload missing {group}/{name}: {location}")
    return location


def keep_copy(source:Path,target:Path)->None:
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if digest_file(source)!=digest_file(target):
            raise InstallerError("Local NFSKR cached asset does not match setup bundle: "+str(target))
        return
    temp=target.with_name(target.name+".tmp")
    if temp.exists():raise InstallerError("Stale temporary bootstrap file "+str(temp))
    try:
        shutil.copyfile(source,temp)
        if digest_file(source)!=digest_file(temp):raise InstallerError("Bootstrap asset copy checksum mismatch")
        temp.replace(target)
    finally:
        if temp.exists():temp.unlink()


def prepare_bundle(root:Path,manager:Path,log:Callable[[str],None]=print,
                   *,game:Path|None=None,install_fonts:bool=False,
                   progress:Callable[[int,str],None]|None=None):
    if not manager.joinpath("FrostyModManager.exe").is_file():
        raise InstallerError("No FrostyModManager.exe found in "+str(manager))
    font_sources={}
    if install_fonts and game is not None:
        from nfskr_fonts import install_game_fonts as prepare_game_fonts
        font_sources=prepare_game_fonts(game,root,log=log,progress=progress)
    for group,name in FONTS:
        source=font_sources.get(name) or locate("fonts/"+group,name)
        keep_copy(source,root/".external/fonts"/group/name)
    for name in LICENSES:
        keep_copy(locate("licenses",name),root/".external/fonts/vendor"/name)
    keep_copy(locate("translation",FROZEN_REL.name),root/FROZEN_REL)
    keep_copy(locate("translation","compat-handling-overhaul-v0.1.3.json"),
              root/"translations/compat-handling-overhaul-v0.1.3.json")
    if digest_file(root/FROZEN_REL)!=FROZEN_SHA:
        raise InstallerError("First release translation data checksum mismatch")
    for name in SCRIPTS:
        keep_copy(locate("scripts",name),root/"tools"/name)
    rt=root/"work/locale-extract/runtime"
    for name in NATIVE:
        keep_copy(locate("native",name),rt/name)
    keep_copy(manager/"Profiles/NFS16SDK.dll",rt/"Profiles/NFS16SDK.dll")
    for name in DEPENDENCIES:
        keep_copy(manager/name,rt/name)
    extras=manager/"ThirdParty"
    if not extras.is_dir():raise InstallerError("Frosty ThirdParty dependencies missing")
    third=rt/"ThirdParty"
    third.mkdir(parents=True,exist_ok=True)
    for dll in extras.glob("*.dll"):
        keep_copy(dll,third/dll.name)
    # Frosty native DLL loader sometimes resolves NewtonSoft relative to cwd.
    newton=third/"Newtonsoft.Json.dll"
    if newton.exists():keep_copy(newton,rt/newton.name)
    log("Frosty 라이브러리와 한글 글꼴, 변환 도구를 준비했습니다.")
    if progress:progress(38,"글꼴과 Frosty 변환 도구 준비를 완료했습니다.")


def load_script(path:Path,alias:str):
    spec=importlib.util.spec_from_file_location(alias,path)
    if spec is None or spec.loader is None:raise InstallerError("Cannot load bundled font utility "+str(path))
    mod=importlib.util.module_from_spec(spec)
    sys.modules[alias]=mod
    spec.loader.exec_module(mod)
    return mod


def run_exe(exe:Path,params:list,rt:Path,name:str,log):
    proc=subprocess.run([str(exe),*[str(p) for p in params]],
        cwd=str(rt),stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,encoding="utf8",errors="replace",timeout=420,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if proc.returncode:
        raise InstallerError(name+" 실행 실패: "+(proc.stdout+"\n"+proc.stderr)[-2300:])
    tail=proc.stdout.strip().splitlines()
    if tail:log(f"{name}을(를) 완료했습니다.")


def exported_translation_config(root:Path)->Path:
    freeze=json.loads((root/FROZEN_REL).read_text(encoding="utf8"))
    if freeze["game_version"]!=366510 or freeze["game_profile"]!="NFS16":
        raise InstallerError("Wrong release localization table version")
    gamecsv=root/"work/locale-extract/en-strings.csv"
    with gamecsv.open(encoding="utf-8-sig",newline="") as stream:
        original={row["string_id"].upper():row["source_text"] for row in csv.DictReader(stream)}
    entries=[]
    for row in freeze["entries"]:
        sid=row["id"].upper()
        if sid not in original:raise InstallerError(f"Installed game missing translated ID {sid}")
        entries.append({"id":sid,"expected_original":original[sid],"ko":row["ko"]})
    if len(entries)!=8206 or len(original)!=10250:raise InstallerError("NFS16 source/release string count mismatch")
    config=root/USER_LOCAL/"ko-strings.json"
    config.parent.mkdir(parents=True,exist_ok=True)
    config.write_text(json.dumps({"entries":entries},ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf8")
    return config


def synthesize_local_mod(root:Path,game:Path,log,
                         progress:Callable[[int,str],None]|None=None)->Path:
    rt=root/"work/locale-extract/runtime"
    base=root/"work/locale-extract"
    qa=root/"work/second-pass-QA"
    base.mkdir(parents=True,exist_ok=True);qa.mkdir(parents=True,exist_ok=True)
    english=base/"en-strings.csv"
    if not english.is_file():
        run_exe(rt/"NfsLocaleDump.exe",[game,english],rt,"게임 원본 문자열·DIN 폰트 추출",log)
    if not english.is_file():raise InstallerError("게임 문자열 파일을 확인할 수 없습니다.")
    if progress:progress(44,"게임 원본 문자열 추출을 완료했습니다.")
    orig_ebx=qa/"en_us-original.ebx"
    if not orig_ebx.is_file():
        run_exe(rt/"DumpOriginalEnUsQA.exe",[game,orig_ebx],rt,"원본 EBX·텍스트 청크 추출",log)
    for name in ("en_us-original.binchunk","en_us-original.histchunk"):
        if not (qa/name).is_file():raise InstallerError("Required original locale chunk missing "+name)
    if progress:progress(49,"원본 EBX와 문자열 청크 확인을 완료했습니다.")
    config=exported_translation_config(root)
    if progress:progress(52,"원본 문자열과 한국어 번역 대조를 완료했습니다.")
    # First-released fonts have to be reproduced from each player's own DIN
    # outlines, never distributed from this developer's licensed installation.
    fonts=root/USER_LOCAL
    basefonts=fonts/"base-fonts"
    finalfonts=fonts/"punctuation-fonts"
    if not (finalfonts/"punctuation-QA-manifest.json").is_file():
        util=load_script(root/"tools/merge-game-fonts.py","nfskr_merge_game_fonts")
        util.ROOT=root
        util.ORIGINAL=root/"work/locale-extract/font-files"
        util.DERIVED=root/".external/fonts/derived"
        util.VENDOR=root/".external/fonts/vendor"
        util.SOURCES=(
            ("cond","ui_fonts_dinoffcpro-cond.bin",util.DERIVED/"NFSKR-UI-Text-SemiBold.ttf"),
            ("condmedi","ui_fonts_dinoffcpro-condmedi.bin",util.VENDOR/"SUIT-Medium.ttf"),
            ("condbold","ui_fonts_dinoffcpro-condbold.bin",util.VENDOR/"SUITE-Heavy.ttf"),
        )
        wanted=util.get_required_codepoints(config,False)
        for font_index,(label,src_name,donor) in enumerate(util.SOURCES,1):
            basefonts.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="nfskr-font-",dir=str(fonts)) as td:
                output=basefonts/f"nfs16-din-{label}-ko-local.ttf"
                if not output.exists():
                    result=util.build_one(label,util.ORIGINAL/src_name,donor,wanted,output,Path(td))
                    log(f"{label} 글꼴에 한글 {result['korean_codepoints']:,}자를 추가했습니다.")
                if progress:progress(52+font_index*3,f"한국어 글꼴 {font_index}/3개를 합성했습니다.")
        qa_font=load_script(root/"tools/build-korean-punctuation-qa.py","nfskr_punctuation")
        qa_font.ROOT=root
        qa_font.DERIVED=root/".external/fonts/derived/NFSKR-UI-Text-SemiBold.ttf"
        qa_font.VENDOR=root/".external/fonts/vendor"
        qa_font.SOURCES=(
            ("cond",util.ORIGINAL/"ui_fonts_dinoffcpro-cond.bin",qa_font.DERIVED),
            ("condmedi",util.ORIGINAL/"ui_fonts_dinoffcpro-condmedi.bin",qa_font.VENDOR/"SUIT-Medium.ttf"),
            ("condbold",util.ORIGINAL/"ui_fonts_dinoffcpro-condbold.bin",qa_font.VENDOR/"SUITE-Heavy.ttf"),
        )
        saved=sys.argv
        try:
            sys.argv=["build-korean-punctuation-qa.py","--base-dir",str(basefonts),"--output",str(finalfonts)]
            qa_font.main()
        finally:
            sys.argv=saved
        log("한글 문장부호와 원본 영문 글꼴의 무결성 검증을 완료했습니다.")
    if progress:progress(64,"한국어 문장부호와 글꼴 검증을 완료했습니다.")
    final_ko=fonts/"NFS16-Korean-FirstRelease-Local.fbmod"
    if not final_ko.is_file():
        exports=fonts/"font-assets"
        run_exe(rt/"ExportFontQA011.exe",[game,root,exports,finalfonts],rt,"한글 폰트 Frosty RES 생성",log)
        builder=load_script(root/"tools/build-poc-mod.py","nfskr_local_mod_builder")
        builder.ROOT=root
        records=builder.load_translation_records(english,config)
        resources=[builder.Resource(0,"Icon")]+[builder.Resource(0,f"Screenshot{i}") for i in range(4)]
        resources.append(builder.Resource(1,"localization/textdbs/en_us",
              payload=builder.make_fs_diff(records),handler=builder.frost_fvn1("fsuitextdatabase")))
        total=builder.append_font_assets(resources,exports/"font-assets.tsv")
        if total!=3:raise InstallerError("Expected 3 merged Korean fonts")
        builder.build_mod(resources,final_ko,"NFSKR First Release (local assets)","1.1.0-offline")
        log("게임 원본을 이용한 한국어 패치 FBMod 생성을 완료했습니다.")
    from nfskr_composite import parse_fs_diff
    korean=parse_mod(final_ko)
    en=[x for x in korean.entries if x.kind==1 and x.name.lower()=="localization/textdbs/en_us"]
    if len(en)!=1 or not en[0].handler:raise InstallerError("Local Korean FBMod missing localization handler")
    actual,deleted=parse_fs_diff(en[0].payload)
    freeze=json.loads((root/FROZEN_REL).read_text(encoding="utf8"))
    expected={x["id"]:x["ko"] for x in freeze["entries"]}
    if actual!=expected or deleted:raise InstallerError("Regenerated Korean strings differ from frozen 1st release")
    if progress:progress(68,"한국어 패치 리소스 생성 및 검증을 완료했습니다.")
    return final_ko


def bootstrap_local_assets(root:Path,manager:Path,game:Path,log=print,
                           *,install_fonts:bool=False,
                           progress:Callable[[int,str],None]|None=None)->Path:
    root=Path(root).resolve()
    manager=Path(manager).resolve(strict=True)
    game=Path(game).resolve(strict=True)
    root.mkdir(parents=True,exist_ok=True)
    prepare_bundle(root,manager,log,game=game,install_fonts=install_fonts,progress=progress)
    # Detect obvious game-data changes in cached output; force rescan from
    # clean cache instead of mixing data from different patch versions.
    cache=root/FINGERPRINT
    gamefiles=[game/"NFS16.exe",game/"Data/cas.cat"]
    missing=[str(p) for p in gamefiles if not p.is_file()]
    if missing:raise InstallerError("Missing required NFS16 files: "+", ".join(missing))
    fingerprint={"game":str(game),"game_hashes":[digest_file(p) for p in gamefiles],
                 "freeze":FROZEN_SHA,"format":GENERATOR_VERSION}
    if cache.is_file():
        prior=json.loads(cache.read_text(encoding="utf8"))
        if prior!=fingerprint:
            raise InstallerError("NFS16 install differs from prior NFSKR cached assets. Remove only the old NFSKR local cache after backing it up, then retry.")
    result=synthesize_local_mod(root,game,log,progress=progress)
    if not cache.exists():
        cache.write_text(json.dumps(fingerprint,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    return result
