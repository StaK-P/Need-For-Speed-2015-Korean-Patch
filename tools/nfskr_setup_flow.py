#!/usr/bin/env python3
"""NFSKR Setup full QA/install pipeline, without modifying source game/mods.

A native GUI or CLI can call build_and_optionally_install() after explicitly
selecting the existing Frosty source pack. This is the developer-stage first
release pipeline. Public packaging must first add on-device font generation
and SDK bootstrap, not embed game-derived original DIN font assets.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import datetime
import os
import json
import tempfile

from nfskr_installer_core import (
    snapshot,digest_file,install_verified,installed_processes_running,
    InstallerError, ModInput
)
from nfskr_composite import (
    build_composite,corrected_order,selected_mod_order,KOREAN,QA
)
from verify_nfskr_composite import run_checks
from nfskr_local_assets import bootstrap_local_assets
from nfskr_bootstrap import valid_frosty,ensure_frosty,ensure_profile,ensure_windows_prerequisites
from nfskr_shortcuts import create_shortcuts,save_shortcuts_in_journal
from nfskr_progress import MilestoneProgress

ROOT=Path(os.environ.get("NFSKR_WORKSPACE_ROOT",str(Path(__file__).resolve().parent.parent))).resolve()
DEFAULT_MANAGER=ROOT/".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
DEFAULT_CONFIG=Path.home()/"AppData/Local/Frosty/manager_config.json"


def certificate(snap,selected:list[ModInput],build:dict,
                verified:dict,output:Path,
                conflict_policy:str="preserve_mod_text")->Path:
    checks={
        "frosty_reader":verified["native_frosty_reader"],
        "locale_ebx_chunk_roundtrip":verified["native_flammenwerfer_decoded"] and verified["native_ebx_roundtrip"],
        "source_resource_coverage":verified["source_gameplay_resource_count"]==build["preserved_source_assets"],
        "font_resource_integrity":verified["font_payload_identical_to_frozen_first_release"],
        "no_unresolved_conflicts":build["encrypted_or_unsupported_assets_skipped"]==0,
    }
    if not all(checks.values()) or verified["sha256"]!=build["merged_sha256"]:
        raise InstallerError("Merged Frosty resource validation did not pass")
    cert={
        "schema":"nfskr-composite-v1",
        "status":"verified",
        "verification":"static_native_not_ingame",
        "source_pack":snap.selected_pack,
        "source_pack_list":snap.source_pack_list,
        "config_sha256":snap.config_sha256,
        "enabled_mods":[{"filename":s.name,"sha256":s.sha256} for s in selected],
        "verified_checks":checks,
        "merged_fbmod":build["merged_fbmod"],
        "merged_sha256":build["merged_sha256"],
        "user_gameplay_test_required":True,
        "untranslated_fallback_count":build["locale_merge"]["manual_review_count"],
        "semantic_conflict_policy":conflict_policy,
    }
    f=output/"merge-certificate.json"
    if f.exists():raise FileExistsError(f)
    f.write_text(json.dumps(cert,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    return f


def build_and_optionally_install(
    *, manager:Path|None=DEFAULT_MANAGER, config:Path=DEFAULT_CONFIG,
    game:Path|None=None,
    source_pack:str|None=None,
    desktop_frosty:bool=False,
    desktop_game:bool=False,
    include_disabled:list[str]|None=None,
    selected_mod_names:list[str]|None=None,
    output_root:Path|None=None,
    install:bool=False,
    log:Callable[[str],None]=print,
    progress:Callable[[int,str],None]|None=None
) -> dict:
    """Runs only on authorized local Windows PC. Does not ever auto-launch NFS16.

    include_disabled is explicit opt-in; the stored original Frosty profile
    remains unmodified either way.
    """
    reporter=MilestoneProgress(progress)
    include_disabled=include_disabled or []
    config=Path(config)
    manager=Path(manager) if manager is not None else None
    if game is None:
        from nfskr_discovery import find_game
        game=find_game(config)
    if game is None or not (Path(game)/"NFS16.exe").is_file():
        raise InstallerError("Need for Speed 2015 설치 경로를 확인할 수 없습니다.")
    game=Path(game).resolve()
    if install and installed_processes_running():
        raise InstallerError("Frosty Mod Manager와 게임을 정상 종료한 후 설치를 다시 시도해 주세요.")
    if not valid_frosty(manager):
        if not install:
            raise InstallerError("Frosty가 아직 없어 병합을 실행할 수 없습니다. 먼저 설치를 진행해 주세요.")
        manager,newly_installed=ensure_frosty(game,manager,log=log,
                                               progress=reporter.report)
        if newly_installed:
            log("게임 폴더 안에 공식 Frosty Mod Manager 설치를 완료했습니다.")
    reporter.report(12,"Frosty 설치 환경 확인을 완료했습니다.")
    if install:
        ensure_windows_prerequisites(game,log,install=True)
        reporter.report(20,"필수 Windows 런타임 확인을 완료했습니다.")
        ensure_profile(config,game,manager,log=log)
    reporter.report(24,"게임과 Frosty 프로필 확인을 완료했습니다.")
    if source_pack is None:
        # When the current Frosty pack is a previously generated "한국어 패치"
        # (old UTF-8 profile or new ASCII NFSKR), use the original source
        # instead of feeding the composite back into itself.
        from nfskr_discovery import read_game_config,source_pack as locate_source_pack
        source_pack=locate_source_pack(read_game_config(config),
                          ROOT/"work/merge-tests/setup-gui") or None
    snap=snapshot(config,manager,source_pack)
    inputs=(selected_mod_order(snap,selected_mod_names)
            if selected_mod_names is not None else corrected_order(snap,include_disabled))
    reporter.report(28,"선택한 원본 모드의 적용 순서를 확인했습니다.")
    log(f"원본 Frosty 프로필 '{snap.selected_pack}'을(를) 불러왔습니다.")
    log(f"원본 모드 {len(inputs)}개를 확인했고, 기존 한국어 패치 {len(snap.replaced_korean_mods)}개는 교체 대상으로 분류했습니다.")
    if output_root is None:
        output_root=ROOT/"work/merge-tests/setup-flow"
    output_root=Path(output_root)
    output_root.mkdir(parents=True,exist_ok=True)
    tag=datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest=output_root/("NFSKR-"+tag)
    if dest.exists():raise InstallerError("출력 폴더가 이미 존재해. 새 설치를 다시 시작해줘.")
    log("게임 원문과 DIN 글꼴을 검사하여 한국어 패치를 생성하고 있습니다.")
    local_korean=bootstrap_local_assets(ROOT,manager,snap.game_path,log,
              install_fonts=install,progress=reporter.report)
    log("기존 모드를 검사하고 EBX·CHUNK·폰트 리소스를 병합하고 있습니다.")
    build=build_composite(inputs,dest,local_korean,ROOT/"work/second-pass-QA")
    reporter.report(83,"원본 모드와 한국어 패치 리소스 병합을 완료했습니다.")
    log(f"통합 FBMod 생성이 완료되었습니다. 리소스 {build['resource_count']:,}개를 포함했습니다.")
    log("Frosty 리더와 문자열·EBX의 무결성을 검증하고 있습니다.")
    run_checks(Path(build["merged_fbmod"]),build["final_strings"],
               dest/"composite-qa-report.json",dest,
               korean_file=local_korean,manager_path=manager)
    reporter.report(92,"Frosty 리더와 문자열·EBX 무결성 검증을 완료했습니다.")
    verified=json.loads((dest/"independent-validation-v2.json").read_text(encoding="utf8"))
    saved=certificate(snap,inputs,build,verified,dest)
    reporter.report(94,"병합 파일 검증 인증서를 생성했습니다.")
    log("병합 결과의 정적 무결성 검사를 통과했습니다.")
    unresolved=build["locale_merge"]["manual_review_count"]
    if unresolved:
        log(f"의미가 달라진 모드 전용 문구 {unresolved}개는 원문을 유지하여 자동 처리했습니다.")
    if not install:
        reporter.report(100,"병합 파일의 정적 검증을 완료했습니다.")
        return {
            "mode":"qa_only","status":"static_verified",
            "output":str(dest),"fbmod":build["merged_fbmod"],"certificate":str(saved),
            "source_mods":[i.name for i in inputs],
            "in_game_verified":False,
        }
    # Last barrier: user selected mods + config all still exactly match snapshot.
    log("검증한 한국어 패치를 기존 NFSKR 프로필에 업데이트하거나 새로 설치하고 있습니다.")
    journal=install_verified(snap,saved,dest,
         selected_sources=inputs,is_busy=installed_processes_running)
    updated_existing=journal.get("operation")=="update"
    reporter.report(98,("기존 NFSKR 프로필 갱신을 완료했습니다." if updated_existing
                       else "새 NFSKR 프로필 설치를 완료했습니다."))
    link_entries=[]
    link_errors=[]
    if desktop_frosty or desktop_game:
        try:
            link_entries=create_shortcuts(manager=manager,game=snap.game_path,
                                          pack=journal["new_pack"],
                                          frosty=desktop_frosty,
                                          game_shortcut=desktop_game,
                                          reuse_existing=updated_existing,log=log)
            journal_files=list(dest.glob("install-journal-*.json"))
            if len(journal_files)!=1:
                raise InstallerError("바로가기를 기록할 설치 내역을 찾지 못했습니다.")
            save_shortcuts_in_journal(journal_files[0],link_entries)
        except Exception as error:
            from nfskr_shortcuts import remove_owned_shortcuts
            remove_owned_shortcuts(link_entries)
            link_errors.append(str(error))
            log("한국어 패치 설치는 완료되었지만 바탕화면 바로가기를 만들지 못했습니다.")
    reporter.report(99,"바탕화면 바로가기 처리와 설치 기록 저장을 완료했습니다.")
    log(("기존 NFSKR 프로필을 갱신했습니다. 이전 합본 모드는 복원용으로 보존됩니다."
         if updated_existing else
         "새 NFSKR 프로필을 설치했습니다. 기존 Frosty 원본 프로필은 보존됩니다."))
    reporter.report(100,"패치 완료")
    return {
        "mode":"installed","status":"installed_static_verified",
        "operation":journal["operation"],
        "output":str(dest),"fbpack":journal["created_archive"],
        "installed_profile":journal["new_pack"],
        "previous_profile":journal["previous_pack"],
        "installed_fbmod":journal["installed_composite"],
        "source_mods":[i.name for i in inputs],
        "created_shortcuts":[item["path"] for item in link_entries if item.get("created")],
        "reused_shortcuts":[item["path"] for item in link_entries if not item.get("created")],
        "shortcut_warnings":link_errors,
        "in_game_verified":False
    }
