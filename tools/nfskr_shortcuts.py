"""Optional Windows desktop shortcuts for Frosty and the Korean-mod game.

The game shortcut ALWAYS launches FrostyModManager.exe -launch <ASCII pack>.
Direct NFS16.exe links would silently bypass the Korean patch.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import winreg

from nfskr_installer_core import InstallerError,digest_file

def desktop_directory()->Path:
    if os.name!="nt":raise InstallerError("바탕화면 바로가기는 Windows에서만 지원합니다.")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            value=winreg.QueryValueEx(key,"Desktop")[0]
            desktop=Path(os.path.expandvars(value))
            if desktop.is_dir():return desktop.resolve()
    except OSError:pass
    path=Path.home()/"Desktop"
    if not path.is_dir():raise InstallerError("바탕화면 폴더를 찾을 수 없습니다.")
    return path.resolve()

def _run_script(script:str)->str:
    process=subprocess.run(
        ["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",
         __import__("base64").b64encode(script.encode("utf-16-le")).decode("ascii")],
        cwd=str(Path.home()),capture_output=True,text=True,encoding="utf-8-sig",
        errors="replace",timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if process.returncode:
        raise InstallerError("바탕화면 바로가기를 만들지 못했습니다. "+
                             (process.stderr or process.stdout)[-600:])
    return process.stdout.strip()

def _ps_quote(value:str)->str:
    return "'"+str(value).replace("'","''")+"'"

def inspect_shortcut(path:Path)->dict:
    if not path.is_file():raise InstallerError("바탕화면 바로가기 파일이 없습니다.")
    script=(
      "$ErrorActionPreference='Stop';"+
      "$ws=New-Object -ComObject WScript.Shell;"+
      "$s=$ws.CreateShortcut("+_ps_quote(str(path))+");"+
      "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"+
      "@{target=$s.TargetPath;arguments=$s.Arguments;workdir=$s.WorkingDirectory}"+
      "|ConvertTo-Json -Compress"
    )
    return json.loads(_run_script(script))

def _safe_new_shortcut_path(dest:Path)->Path:
    if not dest.exists():return dest
    for index in range(2,300):
        alt=dest.with_name(dest.stem+f" ({index})"+dest.suffix)
        if not alt.exists():return alt
    raise InstallerError("바탕화면에 같은 이름의 바로가기가 너무 많습니다.")

def _create_shortcut(path:Path,target:Path,arguments:str,working_dir:Path,icon:Path)->dict:
    if not target.is_file():
        raise InstallerError("바로가기의 실행 파일을 찾을 수 없습니다.")
    if path.suffix.lower()!=".lnk":raise InstallerError("잘못된 바로가기 확장자입니다.")
    staged=path.with_name(path.stem+"-nfskr-temp.lnk")
    if staged.exists():raise InstallerError("다른 바로가기 작업이 진행 중입니다.")
    script=(
      "$ErrorActionPreference='Stop';"+
      "$ws=New-Object -ComObject WScript.Shell;"+
      "$s=$ws.CreateShortcut("+_ps_quote(str(staged))+");"+
      "$s.TargetPath="+_ps_quote(str(target))+";"+
      "$s.Arguments="+_ps_quote(arguments)+";"+
      "$s.WorkingDirectory="+_ps_quote(str(working_dir))+";"+
      "$s.IconLocation="+_ps_quote(str(icon)+",0")+";"+
      "$s.Description="+_ps_quote("NFSKR · by StaK_P")+";"+
      "$s.Save()"
    )
    try:
        _run_script(script)
        check=inspect_shortcut(staged)
        if (Path(check["target"]).resolve()!=target.resolve()
            or check["arguments"].strip()!=arguments.strip()
            or Path(check["workdir"]).resolve()!=working_dir.resolve()):
            raise InstallerError("바로가기 실행 정보 확인에 실패했습니다.")
        staged.replace(path)
        return {"path":str(path),"sha256":digest_file(path),
                "target":str(target),"arguments":arguments,"created":True}
    finally:
        if staged.exists():staged.unlink()

def _matching_shortcut(desktop:Path,filename:str,target:Path,arguments:str)->Path|None:
    """Reuse an existing link only if it launches exactly this profile."""
    prefix="Need for Speed 2015" if filename.startswith("Need for Speed") else "Frosty Mod Manager"
    for link in sorted(desktop.glob(prefix+"*.lnk"))[:60]:
        try:
            current=inspect_shortcut(link)
            if (Path(current["target"]).resolve()==target.resolve()
                and current["arguments"].strip()==arguments.strip()):
                return link
        except (InstallerError,OSError,ValueError,KeyError):
            continue
    return None


def create_shortcuts(*,manager:Path,game:Path,pack:str,
                     frosty:bool,game_shortcut:bool,reuse_existing:bool=False,
                     desktop:Path|None=None,log=print)->list[dict]:
    if not pack or not re.fullmatch(r"[A-Za-z0-9_-]+",pack):
        raise InstallerError("Frosty 실행 프로필 이름은 영문이어야 합니다.")
    manager=Path(manager).resolve(strict=True)
    game=Path(game).resolve(strict=True)
    exe=manager/"FrostyModManager.exe"
    game_exe=game/"NFS16.exe"
    if not exe.is_file() or not game_exe.is_file():
        raise InstallerError("Frosty 또는 NFS16 실행 파일을 확인할 수 없습니다.")
    desk=(Path(desktop) if desktop else desktop_directory()).resolve(strict=True)
    choices=[]
    if frosty:
        choices.append(("Frosty Mod Manager (NFSKR).lnk",exe,"",exe,manager))
    if game_shortcut:
        choices.append(("Need for Speed 2015 (한국어 패치).lnk",
                        exe,f"-launch {pack}",game_exe,manager))
    result=[]
    try:
        for filename,target,args,icon,wd in choices:
            existing=(_matching_shortcut(desk,filename,target,args)
                      if reuse_existing else None)
            if existing is not None:
                item={"path":str(existing),"sha256":digest_file(existing),
                      "target":str(target),"arguments":args,"created":False}
                result.append(item)
                log("기존 바탕화면 바로가기를 유지했습니다: "+existing.stem)
                continue
            dest=_safe_new_shortcut_path(desk/filename)
            item=_create_shortcut(dest,target,args,wd,icon)
            result.append(item)
            log("바탕화면 바로가기를 만들었습니다: "+dest.stem)
        return result
    except BaseException:
        # Remove only the shortcuts created by this batch.
        remove_owned_shortcuts(result)
        raise

def remove_owned_shortcuts(records:list[dict])->list[str]:
    cleaned=[]
    for item in records:
        path=Path(item["path"])
        if not path.exists():continue
        if not item.get("created") or digest_file(path)!=item.get("sha256"):
            continue
        path.unlink()
        cleaned.append(str(path))
    return cleaned

def save_shortcuts_in_journal(journal_path:Path,records:list[dict])->None:
    if not records:return
    original=json.loads(journal_path.read_text(encoding="utf-8"))
    if original.get("schema")!="nfskr-install-journal-v1":
        raise InstallerError("설치 기록을 확인할 수 없습니다.")
    original["desktop_shortcuts"]=records
    temp=journal_path.with_name(journal_path.name+".tmp")
    if temp.exists():raise InstallerError("이전 바로가기 저장 작업이 남아 있습니다.")
    try:
        temp.write_text(json.dumps(original,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(temp,journal_path)
    finally:
        temp.unlink(missing_ok=True)
