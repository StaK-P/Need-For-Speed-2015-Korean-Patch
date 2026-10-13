#!/usr/bin/env python3
"""NFSKR Windows one-file installer entrypoint, by StaK_P.

GUI: three actions (Install, Restore, Launch Frosty), a source-pack dropdown
and mod checkboxes. Console-free --self-test/--qa-build/--qa-selected-build
modes are internal QA only, and never
install into the user's real Frosty profile.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys


def find_workspace()->Path:
    if getattr(sys,"frozen",False):
        base=os.environ.get("LOCALAPPDATA") or str(Path.home()/"AppData/Local")
        return Path(os.environ.get("NFSKR_WORKSPACE_ROOT",
                        str(Path(base)/"NFSKR"))).resolve()
    root=Path(os.environ.get("NFSKR_WORKSPACE_ROOT",
                            str(Path(__file__).resolve().parent.parent)))
    return root.resolve()


def cli_diagnostics()->int|None:
    if len(sys.argv)<3 or sys.argv[1] not in ("--self-test","--qa-build","--qa-selected-build"):
        return None
    mode=sys.argv[1]
    result_path=Path(sys.argv[2]).resolve()
    result_path.parent.mkdir(parents=True,exist_ok=True)
    root=find_workspace()
    result={"mode":mode,"frozen":bool(getattr(sys,"frozen",False)),
            "root":str(root),"status":"error"}
    try:
        if mode=="--self-test":
            from nfskr_local_assets import (
                locate,FROZEN_REL,FROZEN_SHA,FONTS,SCRIPTS,NATIVE,LICENSES)
            from nfskr_installer_core import digest_file
            from fontTools.ttLib import TTFont
            from nfskr_modern_ui import NFSKRApp, friendly_error
            from nfskr_credits import CREDITS, show_credits
            if len(CREDITS)!=12 or not callable(show_credits) or any(
                not x.source.startswith("https://") or
                not x.license_url.startswith("https://") for x in CREDITS
            ):
                raise RuntimeError("크레딧 데이터 검증에 실패했습니다.")
            from nfskr_discovery import safe_frosty_profile_name,selectable_source_packs
            from nfskr_composite import selected_mod_order
            from nfskr_bootstrap import RELEASE_SHA256,RELEASE_URL
            from nfskr_fonts import UPSTREAM,DERIVED
            from nfskr_shortcuts import create_shortcuts,save_shortcuts_in_journal
            import customtkinter
            if len(RELEASE_SHA256)!=64 or "github.com" not in RELEASE_URL:
                raise RuntimeError("Frosty 공식 설치 소스 검증에 실패했습니다.")
            if len(UPSTREAM)!=2 or len(DERIVED)!=1 or not callable(create_shortcuts):
                raise RuntimeError("폰트 또는 바로가기 자동 설치 구성 확인에 실패했습니다.")
            import lz4.block
            if safe_frosty_profile_name({})!="NFSKR":
                raise RuntimeError("Frosty 심볼릭 링크 대응 프로필 검증에 실패했습니다.")
            if not callable(NFSKRApp) or not callable(friendly_error):
                raise RuntimeError("설치 프로그램 UI를 로드하지 못했습니다.")
            if selectable_source_packs({"Packs":{"Default":"","NFSKR":"NFSKR-Composite-x.fbmod:True"}})!=["Default"]:
                raise RuntimeError("모드 병합 프로필 선택 검증에 실패했습니다.")
            if not callable(selected_mod_order):
                raise RuntimeError("모드 선택 병합 기능을 로드하지 못했습니다.")
            required=[("translation",FROZEN_REL.name)]
            required.append(("translation","compat-handling-overhaul-v0.1.3.json"))
            required.extend(("fonts/"+group,name) for group,name in FONTS)
            required.extend(("licenses",name) for name in LICENSES)
            required.extend(("scripts",name) for name in SCRIPTS)
            required.extend(("native",name) for name in NATIVE)
            files=[locate(folder,name) for folder,name in required]
            if len(files)!=17 or digest_file(files[0])!=FROZEN_SHA:
                raise RuntimeError("패치 배포 데이터의 무결성 확인에 실패했습니다.")
            freeze=json.loads(files[0].read_text(encoding="utf8"))
            if freeze["version"]!="1.1.0-first-release" or len(freeze["entries"])!=8206:
                raise RuntimeError("패치 v1.1 번역 데이터 버전이 올바르지 않습니다.")
            normalized={r["id"]:r["ko"] for r in freeze["entries"]}
            if (not all("엠마누엘" in normalized[k] for k in ("624BC5A4","624BC5A5"))
                or any(("에마누엘" in s or "이매뉴얼" in s) for s in normalized.values())):
                raise RuntimeError("v1.1 인물 이름 표기가 통일되지 않았습니다.")
            if any(p.suffix.lower() in (".fbmod",".fbpack",".cas",".ebx") for p in files):
                raise RuntimeError("배포 파일에 게임 원본 데이터가 포함되어 있습니다.")
            result.update({"status":"passed","payload_files":len(files),
                "payload_bytes":sum(p.stat().st_size for p in files),
                "frozen_korean_sha256":FROZEN_SHA,
                "original_EA_assets_bundled":False})
        else:
            if len(sys.argv)<4:
                raise RuntimeError("Frosty 경로를 인자로 입력해야 합니다.")
            os.environ["NFSKR_WORKSPACE_ROOT"]=str(root)
            from nfskr_setup_flow import build_and_optionally_install
            manager=Path(sys.argv[3])
            cfg=(Path(sys.argv[4]) if len(sys.argv)>4
                 else Path.home()/"AppData/Local/Frosty/manager_config.json")
            source=None
            selection=None
            if mode=="--qa-selected-build":
                if len(sys.argv)<7:
                    raise RuntimeError("선택한 원본 프로필 및 모드 목록이 필요합니다.")
                source=sys.argv[5]
                selection=json.loads(sys.argv[6])
            output=build_and_optionally_install(manager=manager,config=cfg,
                    source_pack=source,selected_mod_names=selection,
                    output_root=root/"work/merge-tests/compiled-exe-qa",
                    install=False,log=lambda _:None)
            result.update({"status":"passed","qa_output":output,
                           "chosen_pack":source,"chosen_mods":selection})
    except Exception as error:
        result["error"]=str(error)
    result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                           encoding="utf8")
    return 0 if result["status"]=="passed" else 1


def main()->None:
    root=find_workspace()
    os.environ["NFSKR_WORKSPACE_ROOT"]=str(root)
    from nfskr_modern_ui import NFSKRApp
    app=NFSKRApp(root)
    app.mainloop()


if __name__=="__main__":
    result=cli_diagnostics()
    if result is not None:sys.exit(result)
    main()
