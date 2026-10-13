"""Secure on-demand Frosty and prerequisites setup, within the NFS 2015 game.

The installer does not bundle third-party Frosty. It downloads the ORIGINAL,
unmodified official FrostyToolsuite 1.0.6.3 release only when missing and
extracts it to the game's NFSKR/FrostyModManager folder.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import urllib.request
import winreg
import zipfile
from typing import Callable

from nfskr_installer_core import InstallerError,digest_file,read_config

RELEASE_URL="https://github.com/CadeEvs/FrostyToolsuite/releases/download/v1.0.6.3/FrostyModManager.zip"
RELEASE_SHA256="C7CF94239BCFEB9203330DEBE7C68C8A02C07BB24DF44DDE8D69ACE934C69B19"
RELEASE_BYTES=83316582
REQUIRED=(
    "FrostyModManager.exe","FrostySdk.dll","FrostyCore.dll",
    "FrostyHash.dll","FrostyModSupport.dll","Profiles/NFS16SDK.dll"
)
SOURCE_VERSION="1.0.6.3"


def valid_frosty(manager:Path|None)->bool:
    if not manager:return False
    parent=Path(manager)
    return (all((parent/file).is_file() for file in REQUIRED)
            and (parent/"ThirdParty").is_dir()
            and (parent/"Plugins").is_dir())


def _download(source:str,dest:Path,expected_sha:str,expected_size:int,
              *,log=print,timeout:int=45,
              downloaded:Callable[[int,int],None]|None=None)->None:
    if dest.is_file():
        if (dest.stat().st_size==expected_size
            and digest_file(dest).upper()==expected_sha.upper()):
            log("다운로드한 설치 파일의 무결성을 확인했습니다.")
            return
        raise InstallerError("기존 다운로드 파일의 체크섬이 일치하지 않아 중단했습니다.")
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name(dest.name+".download")
    if temp.exists():raise InstallerError("이전 다운로드가 진행 중입니다. 잠시 후 다시 시도해 주세요.")
    request=urllib.request.Request(source,headers={
        "User-Agent":"NFSKR-Setup/1.0 (+official GitHub release)",
        "Accept":"application/octet-stream"})
    sha=hashlib.sha256()
    count=0
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response, temp.open("xb") as handle:
            if response.status!=200:raise InstallerError("공식 파일 다운로드에 실패했습니다.")
            final=__import__("urllib.parse",fromlist=["urlparse"]).urlparse(response.geturl())
            if final.scheme!="https" or not (
               final.hostname=="github.com" or final.hostname=="release-assets.githubusercontent.com"
               or final.hostname=="objects.githubusercontent.com"
               or final.hostname=="raw.githubusercontent.com"
               or final.hostname=="media.githubusercontent.com"):
                raise InstallerError("예상하지 못한 다운로드 서버로 이동했습니다.")
            while True:
                block=response.read(1024*1024)
                if not block:break
                count+=len(block)
                if count>expected_size:raise InstallerError("공식 다운로드 용량이 예상과 다릅니다.")
                handle.write(block);sha.update(block)
                if downloaded:downloaded(count,expected_size)
        if count!=expected_size or sha.hexdigest().upper()!=expected_sha.upper():
            raise InstallerError("공식 다운로드 파일의 무결성 검증에 실패했습니다.")
        temp.replace(dest)
    finally:
        if temp.exists():temp.unlink()
    log(f"Frosty 공식 설치 파일을 내려받아 검증했습니다. ({count//1048576}MiB)")


def _safe_extract(zip_file:Path,working:Path)->Path:
    with zipfile.ZipFile(zip_file) as archive:
        members=archive.infolist()
        if not 5<len(members)<300 or sum(e.file_size for e in members)>300000000:
            raise InstallerError("Frosty 압축 파일의 내용이 예상과 다릅니다.")
        if archive.testzip() is not None:
            raise InstallerError("Frosty 다운로드 ZIP 검증에 실패했습니다.")
        root="FrostyModManager/"
        all_entries=[]
        for item in members:
            norm=item.filename.replace("\\","/")
            path=PurePosixPath(norm)
            if (not norm.startswith(root) or path.is_absolute() or ".." in path.parts
                or ":" in norm or "\x00" in norm or len(norm)>360):
                raise InstallerError("Frosty ZIP에 유효하지 않은 경로가 있습니다.")
            # ZipInfo external_attr UNIX filesystem mode, disallow symlink payload.
            if (item.external_attr>>16)&0o170000==0o120000:
                raise InstallerError("압축 파일 내부에 심볼릭 링크가 포함되어 있습니다.")
            all_entries.append(norm)
        for name in REQUIRED:
            if root+name not in all_entries:
                raise InstallerError("공식 Frosty ZIP에 필수 라이브러리가 없습니다: "+name)
        # The staging directory is privately owned and exists only here.
        archive.extractall(working)
    manager=working/"FrostyModManager"
    if not valid_frosty(manager):raise InstallerError("Frosty 설치 파일의 필수 구성 확인에 실패했습니다.")
    return manager


def ensure_frosty(game:Path,current_manager:Path|None=None,*,
                  archive_override:Path|None=None,log=print,
                  progress:Callable[[int,str],None]|None=None)->tuple[Path,bool]:
    """Return existing Frosty unchanged, or atomically install new official one.

    archive_override is ONLY for independent regression testing with the pinned
    original archive. It must match RELEASE_SHA256 even in tests.
    """
    game=Path(game).resolve(strict=True)
    if not (game/"NFS16.exe").is_file():
        raise InstallerError("Need for Speed 2015의 게임 폴더를 찾을 수 없습니다.")
    if valid_frosty(current_manager):
        log("기존 Frosty Mod Manager를 확인하여 그대로 사용합니다.")
        return Path(current_manager).resolve(),False
    if current_manager and Path(current_manager).exists():
        raise InstallerError("기존 Frosty가 일부 손상되었습니다. 해당 폴더를 임의로 덮어쓰지 않습니다.")
    home=game/"NFSKR"
    installed=home/"FrostyModManager"
    if valid_frosty(installed):
        log("게임 폴더에 설치된 Frosty Mod Manager를 재사용합니다.")
        return installed.resolve(),False
    if installed.exists():
        raise InstallerError("게임 폴더에 불완전한 Frosty 설치가 있어 자동 덮어쓰기를 중단했습니다.")
    home.mkdir(parents=True,exist_ok=True)
    download_dir=home/"Downloads"
    download_dir.mkdir(parents=True,exist_ok=True)
    archive_path=download_dir/"FrostyModManager-v1.0.6.3.zip"
    if archive_override is not None:
        candidate=Path(archive_override)
        if candidate.stat().st_size!=RELEASE_BYTES or digest_file(candidate)!=RELEASE_SHA256:
            raise InstallerError("테스트용 Frosty 다운로드 원본이 공식 파일과 일치하지 않습니다.")
        if not archive_path.exists():
            shutil.copyfile(candidate,archive_path)
    def on_downloaded(received,total):
        if progress:
            progress(1+int(9*received/total),
                     f"Frosty 다운로드 중입니다. {received*100//total}% 수신했습니다.")
    _download(RELEASE_URL,archive_path,RELEASE_SHA256,RELEASE_BYTES,
              log=log,downloaded=on_downloaded)
    with tempfile.TemporaryDirectory(prefix=".FrostyStaging-",dir=home) as staging:
        staged=_safe_extract(archive_path,Path(staging))
        # This rename is within the game's own NFSKR/ folder, never touching
        # any original EA assets or an existing Frosty directory.
        if installed.exists():raise InstallerError("Frosty 설치 경로가 이미 사용 중입니다.")
        staged.replace(installed)
    (installed/"Mods/NFS16").mkdir(parents=True,exist_ok=True)
    if not valid_frosty(installed):
        raise InstallerError("Frosty 자동 설치 확인에 실패했습니다.")
    log("Frosty Mod Manager 1.0.6.3을 게임 폴더 안에 설치했습니다.")
    return installed.resolve(),True


def ensure_profile(config:Path,game:Path,manager:Path,*,log=print)->bool:
    """Create only missing Frosty NFS16 settings, without clobbering others."""
    config=Path(config)
    game=Path(game).resolve(strict=True)
    if not valid_frosty(manager):
        raise InstallerError("Frosty 구성 요소를 확인할 수 없습니다.")
    (Path(manager)/"Mods/NFS16").mkdir(parents=True,exist_ok=True)
    if config.is_file():
        original,parsed=read_config(config)
    else:
        original=b""
        parsed={}
    if not isinstance(parsed.get("Games",{}),dict):
        raise InstallerError("기존 Frosty 게임 설정 구조가 잘못되었습니다.")
    before=json.loads(json.dumps(parsed,ensure_ascii=False))
    games=parsed.setdefault("Games",{})
    profile=games.setdefault("NFS16",{})
    if not isinstance(profile,dict):
        raise InstallerError("기존 Frosty NFS16 설정을 읽지 못했습니다.")
    saved=profile.get("GamePath")
    if saved and Path(saved).resolve()!=game:
        raise InstallerError("Frosty에 설정된 게임 경로가 실제 설치 경로와 다릅니다.")
    profile.setdefault("GamePath",str(game))
    options=profile.setdefault("Options",{})
    if not isinstance(options,dict):raise InstallerError("기존 Frosty 옵션의 형식이 잘못되었습니다.")
    packs=profile.setdefault("Packs",{})
    if not isinstance(packs,dict):raise InstallerError("기존 Frosty 모드 목록이 잘못되었습니다.")
    if not packs:packs["Default"]=""
    if options.get("SelectedPack") not in packs:
        options["SelectedPack"]="Default" if "Default" in packs else next(iter(packs))
    globalopts=parsed.setdefault("GlobalOptions",{})
    if not isinstance(globalopts,dict):raise InstallerError("Frosty 전역 설정이 잘못되었습니다.")
    globalopts.setdefault("ApplyModOrder","List")
    if before==parsed and original:
        return False  # Never reformat or overwrite an unchanged user Frosty config.
    final=(json.dumps(parsed,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    config.parent.mkdir(parents=True,exist_ok=True)
    if config.exists():
        # Preserve the exact original bytes for manual recovery; a prior backup
        # is never overwritten.
        backup=config.with_name(config.name+".NFSKR-before-bootstrap.bak")
        if backup.exists():
            if backup.read_bytes()!=original:
                raise InstallerError("기존 Frosty 설정 백업이 달라 자동 수정하지 않았습니다.")
        else:
            backup.write_bytes(original)
    tmp=config.with_name(config.name+".NFSKR-initialize.tmp")
    if tmp.exists():raise InstallerError("이전 Frosty 구성 작업이 남아 있습니다.")
    try:
        tmp.write_bytes(final)
        if original and config.read_bytes()!=original:
            raise InstallerError("다른 프로그램이 Frosty 설정을 수정했습니다.")
        if not original and config.exists():
            raise InstallerError("다른 프로그램에서 새로운 Frosty 설정을 생성했습니다.")
        os.replace(tmp,config)
    finally:
        if tmp.exists():tmp.unlink()
    log("Frosty에 Need for Speed 2015 기본 프로필을 자동 설정했습니다.")
    return True


def net48_installed()->bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
           r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as key:
            return int(winreg.QueryValueEx(key,"Release")[0])>=528040
    except (OSError,ValueError):
        return False


def vc_redist_installed()->bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64") as key:
            return int(winreg.QueryValueEx(key,"Installed")[0])==1
    except (OSError,ValueError):
        return False


def requirements_status()->dict:
    return {"dotnet_framework_48":net48_installed(),
            "vc_redistributable_x64":vc_redist_installed()}


# Only Microsoft's official websites and a valid Microsoft Authenticode signature
# are accepted for optional system runtime installers.
MICROSOFT_RUNTIME={
    "dotnet_framework_48":(
      "https://go.microsoft.com/fwlink/?linkid=2088631",
      "Microsoft .NET Framework 4.8",
      ["/q","/norestart"],
      130000000),
    "vc_redistributable_x64":(
      "https://aka.ms/vc14/vc_redist.x64.exe",
      "Microsoft Visual C++ x64 런타임",
      ["/install","/quiet","/norestart"],
      60000000),
}

def _download_signed_microsoft(url:str,target:Path,max_bytes:int)->None:
    """Fetch Microsoft EXE over HTTPS without accepting non-Microsoft redirects."""
    import urllib.parse
    req=urllib.request.Request(url,headers={"User-Agent":"NFSKR-Setup/1.0"})
    pending=target.with_name(target.name+".downloading")
    if pending.exists():raise InstallerError("Microsoft 런타임 다운로드가 이미 진행 중입니다.")
    total=0
    try:
        with urllib.request.urlopen(req,timeout=35) as response:
            if response.status!=200:raise InstallerError("Microsoft 설치 파일 다운로드에 실패했습니다.")
            hostname=urllib.parse.urlparse(response.geturl()).hostname or ""
            if not (hostname.casefold().endswith(".microsoft.com")
                    or hostname.casefold().endswith(".microsoftdownload.com")
                    or hostname.casefold().endswith(".windowsupdate.com")
                    or hostname.casefold() in ("download.microsoft.com","go.microsoft.com")):
                raise InstallerError("Microsoft 공식 다운로드 서버가 아닙니다.")
            target.parent.mkdir(parents=True,exist_ok=True)
            with pending.open("xb") as stream:
                while True:
                    block=response.read(1048576)
                    if not block:break
                    total+=len(block)
                    if total>max_bytes:
                        raise InstallerError("Microsoft 런타임 설치 파일이 예상보다 큽니다.")
                    stream.write(block)
        if total<300000:raise InstallerError("Microsoft 런타임 설치 파일이 불완전합니다.")
        os.replace(pending,target)
    finally:
        pending.unlink(missing_ok=True)

def _valid_microsoft_signature(path:Path)->bool:
    import base64
    script=(
      "$ErrorActionPreference='Stop';"+
      "$s=Get-AuthenticodeSignature -LiteralPath "+
      "'"+str(path).replace("'","''")+"'"+ ";"+
      "if($s.Status -ne 'Valid') {exit 3};"+
      "if($s.SignerCertificate.Subject -notlike '*Microsoft Corporation*') {exit 4}"
    )
    code=base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    p=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",code],
          capture_output=True,timeout=25,
          creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return p.returncode==0

def ensure_windows_prerequisites(game:Path,log=print,*,install:bool=True)->dict:
    """Install only *missing* Microsoft-signed runtimes after user clicked Install.

    Users may see Windows UAC. On cancellation we fail closed; no unverified
    third-party executable may be started as administrator.
    """
    status=requirements_status()
    if all(status.values()):return status
    if not install:return status
    folder=Path(game).resolve(strict=True)/"NFSKR/Downloads"
    folder.mkdir(parents=True,exist_ok=True)
    for key,is_ready in list(status.items()):
        if is_ready:continue
        url,title,arguments,cap=MICROSOFT_RUNTIME[key]
        log(title+"이(가) 없어 Microsoft 공식 설치 파일을 내려받습니다.")
        filepath=folder/("NFSKR-Microsoft-"+key+".exe")
        if not filepath.exists():
            _download_signed_microsoft(url,filepath,cap)
        if not _valid_microsoft_signature(filepath):
            raise InstallerError(title+" 설치 파일의 Microsoft 전자서명을 검증하지 못했습니다.")
        import base64
        ps=("$ErrorActionPreference='Stop';"+
            "$p=Start-Process -FilePath '"+str(filepath).replace("'","''")+
            "' -ArgumentList '"+(" ".join(arguments))+
            "' -Verb RunAs -Wait -PassThru;"+
            "exit $p.ExitCode")
        encoded=base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        proc=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
                  "-EncodedCommand",encoded],capture_output=True,timeout=420,
                  creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if proc.returncode not in (0,3010):
            raise InstallerError(title+" 자동 설치를 완료하지 못했습니다. Windows 권한을 확인해 주세요.")
        status=requirements_status()
        if not status.get(key):
            raise InstallerError(title+" 설치 후에도 필수 런타임이 감지되지 않았습니다. Windows 재시작 후 다시 실행해 주세요.")
        log(title+" 설치와 검증을 완료했습니다.")
    return status
