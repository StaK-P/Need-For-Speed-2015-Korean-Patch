#!/usr/bin/env python3
"""NFSKR local-only FBMod composite builder, first working merge implementation.

- Consumes original enabled Frosty mods without altering them
- Converts supported v1/v3/v5 source mods to one deterministic v5 FBMod
- Rebuilds the en_us EBX and referenced binary/histogram chunks from NFS16
  game's licensed installation plus third-party mod changes plus frozen Korean
- Reuses Korean mod's 3 local font resources; fails on competing font edits
- Re-checks source resource coverage and writes a report, never touching
  Frosty manager config or ModData

This is private QA code, not yet a distributable automatic Windows installer.
"""
from __future__ import annotations
import argparse
import dataclasses
from pathlib import Path
from collections import defaultdict,Counter
import hashlib
import os
import json
import re
import struct
import subprocess
import tempfile
import time
import sys

from nfskr_fbmod_format import Entry,parse_mod,make_mod,ModFormatError
from nfskr_locale_codec import decompress_frostbite,compress_frostbite,read_strings,write_locale
from mod_merge_core import merge_localization,report as text_report
from nfskr_installer_core import snapshot,digest_file

ROOT=Path(os.environ.get("NFSKR_WORKSPACE_ROOT",str(Path(__file__).resolve().parent.parent))).resolve()
QA=ROOT/"work/second-pass-QA"
RT=ROOT/"work/locale-extract/runtime"
KOREAN=ROOT/"work/full-build/qa-v0.1.2/NFS16-Korean-QA-v0.1.2-local.fbmod"
KOREAN_HASH="A2C58D52E4DA982B1F87821D52C681DCF6CC35238C157D5DA64424C923ADC5DD"
FROZEN_TRANSLATIONS=ROOT/"translations/nfskr-first-release-v1.1.json"
FROZEN_TRANSLATIONS_SHA="B488A0D396922E12A36C45EFA7988B60AEC3D7C704606855189EABD69EB22F7A"
BIN_GUID="2d8c69ad-e5d6-645e-0c7b-797023592a91"
HIST_GUID="107e65aa-b390-6b4a-ae36-c31eaf4f6e1d"
EN_US="localization/textdbs/en_us"
FONTS={
    "ui/fonts/dinoffcpro-cond",
    "ui/fonts/dinoffcpro-condmedi",
    "ui/fonts/dinoffcpro-condbold",
}


class CompositeError(ValueError):
    pass


def djb_hash(name: str) -> int:
    v=5381
    for b in name.lower().encode("ascii"):
        v=((v*33)^b)&0xffffffff
    return v


def parse_fs_diff(data: bytes)->tuple[dict[str,str],set[str]]:
    at=data.index(b"\0")+1
    typ=data[:at].decode("ascii")
    if "ModifiedFsLocalizationAsset" not in typ or at+8>len(data):
        raise CompositeError("Unsupported localization handler payload type")
    magic,count=struct.unpack_from("<Ii",data,at);at+=8
    if magic!=0xABCD0001 or count<0 or count>50000:
        raise CompositeError("Only Flammenwerfer UTF16 localization merge is supported")
    changed={}
    for j in range(count):
        if at+4>len(data):raise CompositeError("Truncated Flammenwerfer string")
        sid=struct.unpack_from("<I",data,at)[0];at+=4
        start=at
        while at+2<=len(data) and data[at:at+2]!=b"\0\0":at+=2
        if at+2>len(data):raise CompositeError("Unterminated UTF16 string")
        text=data[start:at].decode("utf-16-le",errors="strict");at+=2
        key=f"{sid:08X}"
        if key in changed:raise CompositeError("Duplicate handler string ID")
        changed[key]=text
    deleted=set()
    if at<len(data):
        if at+12>len(data):raise CompositeError("Truncated Flammenwerfer extension")
        magic,v,n=struct.unpack_from("<IIi",data,at);at+=12
        if magic!=0xF1A88E22 or v not in (1,2) or n<0 or n>50000:
            raise CompositeError("Unsupported Flammenwerfer extension")
        for i in range(n):
            if at+4>len(data):raise CompositeError("Truncated Flammenwerfer deletion")
            deleted.add(f"{struct.unpack_from('<I',data,at)[0]:08X}");at+=4
        if v==2:
            n=struct.unpack_from("<i",data,at)[0];at+=4
            if n<0 or n>50000:raise CompositeError("Unbounded UTF8 extension")
            for i in range(n):
                sid,size=struct.unpack_from("<Ii",data,at);at+=8
                if size<0 or at+size>len(data):raise CompositeError("Invalid UTF8 override")
                value=data[at:at+size].decode("utf8");at+=size
                changed[f"{sid:08X}"]=value
        if at!=len(data):raise CompositeError("Unrecognized Flammenwerfer trailing section")
    if deleted & set(changed):
        raise CompositeError("Handler both removes and overwrites same string")
    return changed,deleted


def resource_key(entry:Entry)->tuple[int,str]:
    return entry.kind,entry.name.lower()


def selectable_source_mods(snap):
    """Third-party mods only, in the stored original Frosty pack order."""
    candidates={x.name.casefold():x for x in (*snap.enabled_mods,*snap.disabled_mods)}
    order=[]
    for chunk in snap.source_pack_list.split("|"):
        if not chunk:continue
        name,state=chunk.rsplit(":",1)
        lowered=name.casefold()
        # Never merge an old Korean translation or a derived NFSKR composite.
        if lowered.startswith(("nfs16-korean-", "nfskr-composite-")):
            continue
        if lowered in candidates:
            order.append(candidates[lowered])
    if len(order)!=len(candidates):
        raise CompositeError("Frosty source profile has unresolved mod entries")
    return order


def selected_mod_order(snap,selected:list[str]):
    """Preserve native Frosty ordering, but let users check ANY subset.

    Supports enabling originally disabled mods and excluding originally
    enabled mods, including selecting no other mods (Korean-only).
    Does NOT edit saved source pack flags/order.
    """
    if not isinstance(selected,(list,tuple)) or any(not isinstance(x,str) for x in selected):
        raise CompositeError("Invalid selected mod filenames")
    requested={name.casefold() for name in selected}
    if len(requested)!=len(selected):
        raise CompositeError("Duplicate selected mod in setup")
    sources=selectable_source_mods(snap)
    known={x.name.casefold() for x in sources}
    missing=requested-known
    if missing:
        raise CompositeError("Selected files are missing in chosen Frosty pack: "+", ".join(sorted(missing)))
    return [item for item in sources if item.name.casefold() in requested]


def corrected_order(snap,additional:list[str]):
    """Legacy API: keep all enabled source mods, optionally enable disabled."""
    chosen=[x.name for x in snap.enabled_mods]
    known={x.casefold() for x in chosen}
    for name in additional:
        if name.casefold() not in known:
            chosen.append(name)
            known.add(name.casefold())
    return selected_mod_order(snap,chosen)


def build_resource_stage(mods):
    """Equivalent of ordered Frosty ordinary asset mods with explicit warnings.

    A later ordinary source mod wins for identical asset names, matching
    current Frosty file application. Unknown handler/raw collisions fail
    closed instead of discarding a custom handler.
    """
    stage:dict[tuple[int,str],Entry]={}
    collisions=[]
    source_raw_enus=None
    source_enus_handler=[]
    raw_locale_changes=[]
    parsed=[]
    for mod_input in mods:
        parsedmod=parse_mod(mod_input.file)
        if parsedmod.sha256!=mod_input.sha256:
            raise CompositeError(f"Source mod changed during read: {mod_input.name}")
        parsed.append(parsedmod)
        for entry in parsedmod.entries:
            if entry.kind==0:continue
            if entry.kind==1 and entry.name.lower()==EN_US:
                if entry.handler:
                    changes,removals=parse_fs_diff(entry.payload)
                    source_enus_handler.append((mod_input.name,changes,removals))
                    raw_locale_changes.append((mod_input.name,"handler",changes,removals))
                    continue
                elif entry.payload:
                    source_raw_enus=entry
            if entry.kind==3 and entry.name.lower() in (BIN_GUID,HIST_GUID):
                if entry.handler:
                    raise CompositeError("Unknown custom chunk handler modifies English localization: "+mod_input.name)
            if entry.kind==2 and entry.name.lower() in FONTS:
                raise CompositeError("This mod edits a Korean font resource and requires a font-level glyph merge: "+mod_input.name)
            key=resource_key(entry)
            prev=stage.get(key)
            if prev is not None:
                if prev.handler or entry.handler:
                    raise CompositeError("Cannot merge two custom/ordinary handlers for asset "+entry.identity())
                if prev.payload is not None and entry.payload is not None:
                    if prev.payload!=entry.payload:
                        collisions.append({"asset":entry.identity(),"previous":prev.source,
                          "winner":str(mod_input.file),"resolution":"source-native-list-order-last-wins"})
            if entry.payload is not None or prev is None:
                stage[key]=entry
    return stage,parsed,source_raw_enus,collisions


def read_base_locale(directory:Path)->tuple[dict[str,str],bytes,bytes,bytes,str]:
    en_ebx=(directory/"en_us-original.ebx").read_bytes()
    bn=(directory/"en_us-original.binchunk").read_bytes()
    hi=(directory/"en_us-original.histchunk").read_bytes()
    initial=read_strings(bn,hi)
    if len(initial)<9000 or b"FsUITextDatabase" not in en_ebx:
        raise CompositeError("Not a valid NFS16 English localization extraction")
    tag=bn[20:bn.index(b"\0",20)].decode("ascii")
    return initial,en_ebx,bn,hi,tag


def make_translated_en_us(mods,base_dir:Path,korean_mod):
    original,vanilla_ebx,bin_raw,hist_raw,tag=read_base_locale(base_dir)
    initial_bin=bin_raw;initial_hist=hist_raw
    effective=original.copy()
    chosen_ebx=vanilla_ebx
    action_log=[]
    removed=set()
    for source in mods:
        parsed=parse_mod(source.file)
        if parsed.sha256!=source.sha256:raise CompositeError("Mod changed while merging")
        changed_bin=changed_hist=False
        handler_diffs=[]
        for item in parsed.entries:
            name=item.name.lower()
            if item.kind==1 and name==EN_US:
                if item.handler:
                    if item.payload is None:raise CompositeError("Missing UTF16 text handler payload")
                    handler_diffs.append(parse_fs_diff(item.payload))
                elif item.payload is not None:
                    chosen_ebx=decompress_frostbite(item.payload)
            elif item.kind==3 and name==BIN_GUID:
                if item.handler:raise CompositeError("Unsupported English binary chunk handler")
                if item.payload is not None:
                    bin_raw=decompress_frostbite(item.payload)
                    changed_bin=True
            elif item.kind==3 and name==HIST_GUID:
                if item.handler:raise CompositeError("Unsupported English histogram chunk handler")
                if item.payload is not None:
                    hist_raw=decompress_frostbite(item.payload)
                    changed_hist=True
        if changed_bin or changed_hist:
            effective=read_strings(bin_raw,hist_raw)
            removed=set(original)-set(effective)
            action_log.append({"source":source.name,"strategy":"raw_locale_rebased",
                "effective_ids":len(effective),"removed_ids":len(removed)})
        for changes,deletions in handler_diffs:
            effective.update(changes)
            for sid in deletions:effective.pop(sid,None)
            removed=set(original)-set(effective)
            action_log.append({"source":source.name,"strategy":"Flammenwerfer_UTF16_merge",
               "replaced_ids":len(changes),"removed_ids":len(deletions)})
    source_ko=[x for x in korean_mod.entries if x.kind==1 and x.name.lower()==EN_US]
    if len(source_ko)!=1 or source_ko[0].handler==0:
        raise CompositeError("Input Korean mod must contain one UTF16 locale handler")
    korean,deleted=parse_fs_diff(source_ko[0].payload)
    if deleted:raise CompositeError("Frozen Korean 1st release unexpectedly removes text IDs")
    if len(korean)!=8206:raise CompositeError("Frozen 1st release translation count changed")
    reviewed={}
    rule_path=ROOT/"translations/compat-handling-overhaul-v0.1.3.json"
    if rule_path.exists():
        rules=json.loads(rule_path.read_text(encoding="utf8"))
        if any(x.sha256==rules["source_mod_sha256"] for x in mods):
            reviewed={e["id"].upper():e["ko"] for e in rules["entries"]}
            action_log.append({"strategy":"reviewed_mod_localization_rules","rule_count":len(reviewed)})
    merged,details=merge_localization(original,effective,korean,reviewed,
        base_deleted_ids=removed)
    out_bin,out_hist=write_locale(merged,section=tag)
    return {
        "merged_strings":merged,
        "decoded_source_ids":len(original),
        "source_ebx":chosen_ebx,
        "string_bin":out_bin,
        "hist_bin":out_hist,
        "mod_actions":action_log,
        "report":text_report(details),
        "reviewed_ids":len(reviewed),
        "translation_count":len(korean),
        "effective_source_ids":len(effective),
        "source_removed_ids":sorted(removed),
    }


def reserialize_ebx_with_sdk(raw:bytes,new_bin:int,new_hist:int,work:Path)->bytes:
    exe=RT/"NfsKREbxRepack.exe"
    if not exe.is_file():raise CompositeError("Frosty SDK EBX compiler missing")
    source=work/"source_en_us.ebx"
    target=work/"merged_en_us.ebx"
    source.write_bytes(raw)
    proc=subprocess.run([str(exe),str(source),str(new_bin),str(new_hist),str(target)],
                        cwd=str(RT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        text=True,encoding="utf8",errors="replace",timeout=90,
                        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if proc.returncode!=0 or not target.is_file():
        raise CompositeError("NFS16 EBX SDK roundtrip failed: "+(proc.stdout+proc.stderr)[:1500])
    ids=re.search(r"chunk=([0-9a-f-]+) hist=([0-9a-f-]+)",proc.stdout,re.I)
    if not ids or ids.group(1).lower()!=BIN_GUID or ids.group(2).lower()!=HIST_GUID:
        raise CompositeError("A source mod redirected English locale to unknown chunk GUIDs")
    return target.read_bytes()


def locale_resources(raw_ebx:bytes,raw_binary:bytes,raw_hist:bytes)->list[Entry]:
    hash32=djb_hash(EN_US)
    out=[
        Entry(1,EN_US,compress_frostbite(raw_ebx),size=len(raw_ebx)),
    ]
    for guid,data in ((BIN_GUID,raw_binary),(HIST_GUID,raw_hist)):
        meta=struct.pack("<IIIIii",0,0,0,len(data),
                         hash32 if hash32<0x80000000 else hash32-0x100000000,-1)
        out.append(Entry(3,guid,compress_frostbite(data),size=len(data),
                         flags=2,chunk_meta=meta))
    return out


def enforce_asset_coverage(stage,composite:list[Entry],korean_fonts:list[Entry]):
    found={resource_key(x):x for x in composite}
    omitted={resource_key(x) for x in composite if x.name.lower() in (EN_US,BIN_GUID,HIST_GUID)}
    for key,entry in stage.items():
        if key in omitted:continue
        if key not in found:raise CompositeError("Source gameplay asset dropped: "+str(key))
        output=found[key]
        if (entry.payload!=output.payload or entry.kind!=output.kind or entry.added_bundles!=output.added_bundles
            or entry.flags!=output.flags or entry.chunk_meta!=output.chunk_meta
            or entry.res_meta!=output.res_meta or entry.handler!=output.handler):
            raise CompositeError("Source game-mod resource altered: "+entry.identity())
    for item in korean_fonts:
        out=found.get(resource_key(item))
        if out is None or out.payload!=item.payload:
            raise CompositeError("Korean font glyph assets missing or altered")
    return len(stage)-sum(1 for k in stage if k in omitted)


def build_composite(sources:list,output_dir:Path,korean_file:Path=KOREAN,
                    base_dir:Path=QA)->dict:
    if digest_file(FROZEN_TRANSLATIONS)!=FROZEN_TRANSLATIONS_SHA:
        raise CompositeError("Frozen first-release translation payload changed")
    korean_mod=parse_mod(korean_file)
    locale=[x for x in korean_mod.entries if x.kind==1 and x.name.lower()==EN_US]
    if len(locale)!=1 or not locale[0].handler:
        raise CompositeError("Invalid locally generated Korean translation payload")
    actual,_deleted=parse_fs_diff(locale[0].payload)
    expected={x["id"]:x["ko"] for x in json.loads(FROZEN_TRANSLATIONS.read_text(encoding="utf8"))["entries"]}
    if _deleted or actual!=expected:
        raise CompositeError("Generated Korean strings do not match frozen first-release translation")
    stage,parsed,ebx_source,source_conflicts=build_resource_stage(sources)
    locale=make_translated_en_us(sources,base_dir,korean_mod)
    fonts=[x for x in korean_mod.entries if x.kind==2 and x.name.lower() in FONTS]
    if len(fonts)!=3:raise CompositeError("Missing Korean font asset")
    output_dir=Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CompositeError("Use an empty output directory for deterministic QA")
    output_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nfskr-merge-",dir=output_dir) as temp:
        raw_ebx=reserialize_ebx_with_sdk(locale["source_ebx"],
                        len(locale["string_bin"]),len(locale["hist_bin"]),Path(temp))
    raw_locale=locale_resources(raw_ebx,locale["string_bin"],locale["hist_bin"])
    # Source mod resources remain identical, except three locale resources which
    # are REPLACED by rebuilt EBX and chunks that incorporate both source and KO.
    final_entries=[
      Entry(0,"Icon",None),
      Entry(0,"Screenshot0",None),Entry(0,"Screenshot1",None),
      Entry(0,"Screenshot2",None),Entry(0,"Screenshot3",None),
    ]
    for key,entry in stage.items():
        if entry.name.lower() in (EN_US,BIN_GUID,HIST_GUID) and entry.kind in (1,3):
            continue
        final_entries.append(entry)
    final_entries.extend(raw_locale)
    final_entries.extend(fonts)
    current_korean_hash=digest_file(korean_file)
    fingerprint=hashlib.sha256(("|".join(
        f"{x.name}@{x.sha256}" for x in sources)+current_korean_hash).encode()).hexdigest()[:12]
    dest=output_dir/f"NFSKR-Merged-{fingerprint}.fbmod"
    make_mod(final_entries,dest,"NFS 2015 Korean Merge 1st Release "+fingerprint,
        version_label="1.1-preview-offline")
    observed=parse_mod(dest)
    if len(observed.entries)!=len(final_entries):
        raise CompositeError("Composite parse count differs")
    coverage=enforce_asset_coverage(stage,observed.entries,fonts)
    results={
      "status":"static_QA_only",
      "merged_fbmod":str(dest),
      "merged_sha256":digest_file(dest),
      "original_gameplay_mods":[{"filename":s.name,"sha256":s.sha256} for s in sources],
      "source_mod_versions":{x.path.name:x.version for x in parsed},
      "resource_count":len(observed.entries),
      "preserved_source_assets":coverage,
      "external_asset_priority_collisions":source_conflicts,
      "korean_fonts_preserved":3,
      "original_strings":locale["decoded_source_ids"],
      "effective_source_strings":locale["effective_source_ids"],
      "final_strings":len(locale["merged_strings"]),
      "translated_ids":locale["translation_count"],
      "reviewed_external_label_ids":locale["reviewed_ids"],
      "source_removed_ids":locale["source_removed_ids"],
      "locale_merge":locale["report"],
      "locale_mod_actions":locale["mod_actions"],
      "encrypted_or_unsupported_assets_skipped":0,
      "game_executable_modified":False,"frosty_profile_modified":False,
      "ingame_compatibility_verified":False,
      "warning":"Composite source+KO file must pass independent official-reader and in-game verification before release."
    }
    report_path=output_dir/"composite-qa-report.json"
    report_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("NFSKR_COMPOSITE_QA_BUILT",json.dumps(
       {k:v for k,v in results.items() if k not in ("locale_merge","locale_mod_actions","external_asset_priority_collisions","source_removed_ids")},
       ensure_ascii=True))
    print("SOURCE_PRIORITY_COLLISIONS",len(source_conflicts),
          "UNREVIEWED_SEMANTIC_STRINGS",results["locale_merge"]["manual_review_count"])
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manager",type=Path,default=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager")
    parser.add_argument("--config",type=Path,default=Path.home()/"AppData/Local/Frosty/manager_config.json")
    parser.add_argument("--include-disabled",action="append",default=[],help="QA-only explicit inclusion of saved disabled source FBMod")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    current=snapshot(args.config,args.manager)
    sources=corrected_order(current,args.include_disabled)
    print("SOURCE_PACK",current.selected_pack,"ORDER",current.order_setting,
          "ACTIVE_MODS",len(sources),"KOREAN_REPLACED",len(current.replaced_korean_mods))
    result=build_composite(sources,args.output)
    if args.include_disabled:
        print("QA_ONLY_SELECTED_DISABLED",args.include_disabled,
              "Cannot install into original Frosty config without explicit UI selection.")
    return 0


if __name__=="__main__":
    try:sys.exit(main())
    except Exception as error:
        print("NFSKR_COMPOSITE_FAILED",str(error),file=sys.stderr)
        raise
