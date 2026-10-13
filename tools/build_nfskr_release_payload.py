#!/usr/bin/env python3
"""Build legally separated NFSKR Setup runtime payload.

Embeds NO user-specific EA font data, game archives, third-party FBMods,
original game strings or Frosty SDK libraries. Bundled EXEs are locally
compiled NFSKR's own helpers; Frosty SDK is read from installed manager.
"""
from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent.parent
DST=R/"work/installer-build/bundle_assets"
S={
"translation/nfskr-first-release-v1.1.json": R/"translations/nfskr-first-release-v1.1.json",
"translation/compat-handling-overhaul-v0.1.3.json": R/"translations/compat-handling-overhaul-v0.1.3.json",
"fonts/vendor/SUIT-Medium.ttf": R/".external/fonts/vendor/SUIT-Medium.ttf",
"fonts/vendor/SUITE-Heavy.ttf": R/".external/fonts/vendor/SUITE-Heavy.ttf",
"fonts/derived/NFSKR-UI-Text-SemiBold.ttf": R/".external/fonts/derived/NFSKR-UI-Text-SemiBold.ttf",
"licenses/SUIT-OFL-LICENSE.txt": R/".external/fonts/vendor/SUIT-OFL-LICENSE.txt",
"licenses/SUITE-OFL-LICENSE.txt": R/".external/fonts/vendor/SUITE-OFL-LICENSE.txt",
"licenses/pretendard-OFL-LICENSE.txt": R/".external/fonts/vendor/pretendard-OFL-LICENSE.txt",
}
S.update({"scripts/"+x:R/"tools"/x for x in (
"merge-game-fonts.py","build-korean-punctuation-qa.py","build-poc-mod.py")})
S.update({"native/"+x:R/"work/locale-extract/runtime"/x for x in (
"NfsLocaleDump.exe","DumpOriginalEnUsQA.exe","ExportFontQA011.exe",
"NfsKREbxRepack.exe","AuditNfsModResources.exe","NfsKRNativeLocaleCheck.exe")})
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def main():
 if DST.exists() and any(DST.iterdir()):
  raise FileExistsError("Build payload already staged; do not overwrite without inspection: "+str(DST))
 out=[]
 for name,source in S.items():
  if not source.is_file():raise FileNotFoundError(source)
  if name.lower().endswith((".fbmod",".fbpack",".archive",".cas",".ebx",".bin")):
   raise ValueError("Proprietary content forbidden in installer: "+name)
  dst=DST/name
  dst.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(source,dst)
  if digest(source)!=digest(dst):raise ValueError("Release asset changed while copied")
  out.append({"path":name,"sha256":digest(dst),"size":dst.stat().st_size})
 if len(out)!=len(S) or len(out)!=17:
  raise ValueError("Incomplete release pack "+str(len(out)))
 freeze=next(x for x in out if x["path"].endswith("nfskr-first-release-v1.1.json"))
 if freeze["sha256"]!="B488A0D396922E12A36C45EFA7988B60AEC3D7C704606855189EABD69EB22F7A":
  raise ValueError("Frozen Korean table unexpectedly changed")
 forbidden=["NFS16.exe","NFS16SDK.dll","FrostySdk.dll","FrostyCore.dll","FrostyHash.dll",
            "ui_fonts_dinoffcpro","NFSKR-Merged-","NFS16-Korean-FirstRelease-Local.fbmod"]
 for path in DST.rglob("*"):
  if path.is_file() and any(s.lower() in path.name.lower() for s in forbidden):
   raise ValueError("Contains proprietary/installed game content: "+str(path))
 manifest=R/"work/installer-build/release-payload-manifest.json"
 manifest.write_text(json.dumps({"release":"NFSKR Setup 1.1 preview","redistributable_payload_only":True,
    "contains_original_EA_assets":False,"contains_source_mods":False,
    "Frosty_library_provider":"User's installed Frosty Mod Manager",
    "assets":out},ensure_ascii=False,indent=2)+"\n",encoding="utf8")
 print("NFSKR_RELEASE_ASSET_BUNDLE_PREPARED",len(out),"assets",sum(x["size"] for x in out),"bytes")
 print("FROZEN_STRINGS",freeze["sha256"])
 print("MANIFEST",manifest)
if __name__=="__main__":main()
