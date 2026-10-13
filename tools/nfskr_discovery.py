"""Read-only Frosty/NFS16 discovery and symlink preflight for NFSKR Setup.

Avoids fixed developer paths and does not change the user's Frosty/game config.
On legacy Frosty 1.0.6.3, UTF-8 run.bat is read in the Windows OEM codepage,
so the pack's internal filename MUST be ASCII (e.g. NFSKR).
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import winreg


@dataclass
class Discovery:
    manager: Path | None
    game: Path | None
    config: Path
    current_pack: str
    source_pack: str
    mods_enabled: int
    mods_disabled: int
    notes: tuple[str, ...]


def config_path() -> Path:
    base=Path(os.environ.get("LOCALAPPDATA") or (Path.home()/"AppData/Local"))
    return base/"Frosty/manager_config.json"


def read_game_config(path:Path)->dict:
    if not path.is_file():return {}
    try:
        data=json.loads(path.read_text(encoding="utf-8-sig"))
        result=data.get("Games",{}).get("NFS16",{})
        return result if isinstance(result,dict) else {}
    except (ValueError, UnicodeError, OSError):
        return {}


def _running_manager()->list[Path]:
    """Look up running Frosty with Windows API, not a slow PowerShell process."""
    if os.name!="nt":return []
    try:
        from ctypes import wintypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        psapi=ctypes.WinDLL("psapi",use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes=[
            wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        processes=(wintypes.DWORD*4096)()
        written=wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(processes),ctypes.sizeof(processes),
                                   ctypes.byref(written)):
            return []
        result=[]
        for pid in list(processes)[:written.value//ctypes.sizeof(wintypes.DWORD)]:
            handle=kernel.OpenProcess(0x1000,False,pid)
            if not handle:continue
            try:
                buf=ctypes.create_unicode_buffer(32768)
                size=wintypes.DWORD(len(buf))
                if (kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size))
                    and buf.value.casefold().endswith("\\frostymodmanager.exe")):
                    result.append(Path(buf.value).parent)
            finally:
                kernel.CloseHandle(handle)
        return result
    except (AttributeError,OSError,ValueError):
        return []


def _shortcut_targets()->list[Path]:
    if os.name!="nt":return []
    folders=[
        Path.home()/"Desktop",
        Path(os.environ.get("PUBLIC","C:/Users/Public"))/"Desktop",
        Path(os.environ.get("APPDATA",str(Path.home()/"AppData/Roaming")))/"Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA","C:/ProgramData"))/"Microsoft/Windows/Start Menu/Programs",
    ]
    found=[]
    for folder in folders:
        if not folder.is_dir():continue
        # Only inspect matching Frosty shortcuts, no general user shortcuts.
        matches=[p for p in folder.glob("*Frosty*.lnk")]
        matches+=list(folder.glob("*/*Frosty*.lnk"))[:30]
        for link in matches[:40]:
            try:
                flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
                command=["powershell.exe","-NoProfile","-NonInteractive","-Command",
                        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('"+
                        str(link).replace("'","''")+"'); $s.TargetPath"]
                proc=subprocess.run(command,capture_output=True,timeout=6,
                                    text=True,encoding="utf-8-sig",errors="replace",
                                    creationflags=flags)
                target=Path(proc.stdout.strip())
                if target.name.lower()=="frostymodmanager.exe":found.append(target.parent)
            except (OSError,subprocess.TimeoutExpired):
                pass
    return found


def _prior_install_managers()->list[Path]:
    """Reuse only prior NFSKR-owned install journals, not arbitrary app data."""
    journal_root=config_path().parent.parent/"NFSKR/work/merge-tests/setup-gui"
    if not journal_root.is_dir():return []
    found=[]
    try:
        records=sorted(journal_root.glob("*/install-journal-*.json"),
                       key=lambda p:p.stat().st_mtime,reverse=True)
        for record in records[:16]:
            try:
                details=json.loads(record.read_text(encoding="utf-8"))
                mod=Path(details["installed_composite"])
                manager=mod.parents[2]
                if (manager/"FrostyModManager.exe").is_file():
                    found.append(manager)
            except (OSError,KeyError,ValueError,IndexError):
                continue
    except OSError:
        return found
    return found


def _scan_known_frosty_dirs()->list[Path]:
    home=Path.home()
    common=[
        home/"Downloads",home/"Desktop",home/"Documents",
        Path(os.environ.get("LOCALAPPDATA","C:/Users/Default/AppData/Local")),
        Path("C:/Program Files"),Path("C:/Program Files (x86)"),
    ]
    for letter in "CDEFG":
        root=Path(letter+":/")
        common.extend([root/"Games",root/"Games/EA",root/"Frosty",
                       root/"Tools",root/"Modding",root/"Apps"])
    results=[]
    # Bounded DFS: never walk an entire drive or large unrelated filesystem.
    for base in common:
        if not base.is_dir():continue
        queue=[(base,0)]
        visited=0
        while queue and visited<650:
            current,depth=queue.pop(0)
            visited+=1
            if (current/"FrostyModManager.exe").is_file():
                results.append(current)
                continue
            if depth>=7:continue
            try:
                for p in current.iterdir():
                    if not p.is_dir() or p.is_symlink():continue
                    low=p.name.lower()
                    if current==base and any(w in low for w in
                       ("node_modules","windows","python","microsoft","nvidia","anaconda",
                        "steamapps","packages","cache","temp","programdata","logs")):
                        continue
                    if depth>=2 and not any(t in low for t in
                       ("frosty","mod","manager","nfs","ea","tool","external",
                        "1.0.6","games","patch")):
                        continue
                    queue.append((p,depth+1))
            except (PermissionError,OSError):
                continue
    return results


def find_frosty(config:Path|None=None, preferred:Path|None=None)->Path|None:
    cfg=read_game_config(config or config_path())
    active=cfg.get("Packs",{}).get(cfg.get("Options",{}).get("SelectedPack",""),"")
    names=[part.rsplit(":",1)[0] for part in active.split("|") if ":" in part]
    choices=[]
    if preferred:choices.append(preferred)
    setting=os.environ.get("NFSKR_FROSTY_MANAGER")
    if setting:choices.append(Path(setting))
    choices+=_running_manager()
    choices+=_prior_install_managers()
    game_path=find_game(config)
    if game_path:
        choices.append(game_path/"NFSKR/FrostyModManager")
    # Most users already have an installed/running Frosty; skip expensive
    # directory searches when that executable and source-mod list are known.
    for item in choices:
        directory=Path(item)
        if directory.is_file():directory=directory.parent
        if not (directory/"FrostyModManager.exe").is_file():continue
        moddir=directory/"Mods/NFS16"
        if moddir.is_dir() and all((moddir/n).is_file() for n in names):
            return directory.resolve()
    choices+=_shortcut_targets()
    choices+=_scan_known_frosty_dirs()
    candidates={}
    for original in choices:
        p=Path(original)
        if p.is_file() and p.name.lower()=="frostymodmanager.exe":p=p.parent
        if not (p/"FrostyModManager.exe").is_file():continue
        try:p=p.resolve()
        except OSError:continue
        if p in candidates:continue
        score=(20 if (p/"Mods/NFS16").is_dir() else 0)
        for name in names[:30]:
            if (p/"Mods/NFS16"/name).is_file():score+=4
        if setting and str(p).casefold()==str(Path(setting).resolve()).casefold():
            score+=100
        if preferred and str(p).casefold()==str(Path(preferred).resolve()).casefold():
            score+=100
        candidates[p]=score
    if not candidates:return None
    return max(candidates,key=lambda q:candidates[q])


def find_game(cfg:Path|None=None)->Path|None:
    game=read_game_config(cfg or config_path())
    candidates=[]
    saved=game.get("GamePath")
    if isinstance(saved,str):candidates.append(Path(saved))
    reg_roots=(winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER)
    for hive in reg_roots:
        for key in (r"SOFTWARE\EA Games\Need for Speed",
                    r"SOFTWARE\WOW6432Node\EA Games\Need for Speed",
                    r"SOFTWARE\Electronic Arts\Need for Speed"):
            try:
                with winreg.OpenKey(hive,key) as ref:
                    for name in ("Install Dir","InstallDir","InstallLocation","Path"):
                        try:
                            candidate=winreg.QueryValueEx(ref,name)[0]
                            if isinstance(candidate,str):candidates.append(Path(candidate))
                        except OSError:pass
            except OSError:pass
    for letter in "CDEFG":
        root=Path(letter+":/")
        for prefix in ("Games/EA","EA Games","Origin Games","Program Files/EA Games",
                       "Program Files (x86)/Origin Games",
                       "Program Files (x86)/Steam/steamapps/common",
                       "SteamLibrary/steamapps/common"):
            for name in ("Need for Speed","Need for Speed 2015","Need For Speed"):
                candidates.append(root/prefix/name)
    for cand in candidates:
        if (cand/"NFS16.exe").is_file():
            return cand.resolve()
    return None


def selectable_source_packs(game:dict)->list[str]:
    """Frosty source packs that are safe merge inputs, in original UI order."""
    packs=game.get("Packs",{})
    if not isinstance(packs,dict):return []
    choices=[]
    for name,raw in packs.items():
        if not isinstance(name,str) or not isinstance(raw,str):
            continue
        # A previously merged NFSKR pack MUST NOT be fed back to the merger.
        if any(item.rsplit(":",1)[0].casefold().startswith("nfskr-composite-")
               for item in raw.split("|") if item):
            continue
        choices.append(name)
    return choices


def source_pack(game:dict, journal_dir:Path|None=None)->str:
    packs=game.get("Packs",{})
    if not isinstance(packs,dict) or not packs:return ""
    selected=game.get("Options",{}).get("SelectedPack","")
    def is_composite(name:str)->bool:
        return "nfskr-composite-" in packs.get(name,"").casefold()
    if selected in packs and not is_composite(selected):return selected
    if journal_dir and journal_dir.is_dir():
        for record in sorted(journal_dir.glob("*/install-journal-*.json"),
                             key=lambda p:p.stat().st_mtime,reverse=True):
            try:
                info=json.loads(record.read_text(encoding="utf-8"))
                if info.get("new_pack")==selected and info.get("source_pack") in packs:
                    return info["source_pack"]
            except (OSError,ValueError):pass
    if "Default" in packs and not is_composite("Default"):return "Default"
    return next((p for p in packs if not is_composite(p)),"")


def discover(*,config:Path|None=None,preferred_manager:Path|None=None,
             journal_dir:Path|None=None)->Discovery:
    config=config or config_path()
    game=read_game_config(config)
    manager=find_frosty(config,preferred_manager)
    exe=find_game(config)
    chosen=source_pack(game,journal_dir)
    active=game.get("Packs",{}).get(chosen,"")
    enabled=sum(a.endswith(":True") for a in active.split("|")
                if a and not a.casefold().startswith(("nfskr-composite-","nfs16-korean-")))
    disabled=sum(a.endswith(":False") for a in active.split("|"))
    notes=[]
    if not config.exists():notes.append("Frosty 설정 파일이 아직 생성되지 않았습니다.")
    if not manager:notes.append("Frosty Mod Manager의 설치 경로를 확인해야 합니다.")
    if not exe:notes.append("Need for Speed 2015의 설치 경로를 확인해야 합니다.")
    if not chosen:notes.append("Frosty에서 게임 프로필을 먼저 설정해 주세요.")
    return Discovery(manager,exe,config,
       game.get("Options",{}).get("SelectedPack",""),chosen,
       enabled,disabled,tuple(notes))


def safe_frosty_profile_name(existing:dict,preferred:str="NFSKR")->str:
    # Frosty 1.0.6.3 runs UTF-8 .BAT under OEM CP and corrupts Korean pack paths.
    if preferred not in existing:return preferred
    for n in range(2,1000):
        next_name=f"{preferred}-{n}"
        if next_name not in existing:return next_name
    raise ValueError("NFSKR 프로필 이름을 새로 만들 수 없습니다.")


def symlink_preflight(game:Path)->tuple[bool,str]:
    target=Path(game)/"ModData"
    try:
        target.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".nfskr-preflight-",dir=target) as folder:
            p=Path(folder)
            src=p/"original.cas";src.write_bytes(b"NFSKR_SYMLINK")
            dst=p/"copy.cas"
            os.symlink(src,dst)
            if not dst.is_symlink() or dst.read_bytes()!=src.read_bytes():
                return False,"심볼릭 링크의 실제 파일 접근을 확인하지 못했습니다."
        return True,"심볼릭 링크 생성 검사를 통과했습니다."
    except OSError as e:
        return False,f"게임 드라이브에서 심볼릭 링크를 만들 수 없습니다. {e}"


def start_manager(manager:Path,game:Path)->tuple[bool,str]:
    """Launch existing Frosty normally if links work, elevated only on failure.

    Never starts the game and never force-terminates an existing manager.
    """
    if os.name!="nt":return False,"Windows에서만 Frosty를 실행할 수 있습니다."
    exe=Path(manager)/"FrostyModManager.exe"
    if not exe.is_file():return False,"FrostyModManager.exe 파일을 찾을 수 없습니다."
    if _running_manager():
        return True,"Frosty Mod Manager가 이미 실행 중입니다."
    ok,reason=symlink_preflight(game)
    # Unicode source paths will also be corrupted by older Frosty's mklink BAT.
    ascii_paths=all(p.isascii() for p in (str(game),str(manager)))
    if not ascii_paths:
        return False,("Frosty 1.0.6.3은 한글 설치 경로에서도 심볼릭 링크 오류가 발생할 수 있습니다. "
                      "Frosty와 게임의 설치 경로를 영문 경로로 변경하셔야 합니다.")
    try:
        if ok:
            subprocess.Popen([str(exe)],cwd=str(manager),close_fds=True)
            return True,"Frosty Mod Manager를 실행했습니다."
        # Request elevation only from an explicit "Frosty 실행" button click.
        result=ctypes.windll.shell32.ShellExecuteW(None,"runas",str(exe),None,
                                                  str(manager),1)
        if result<=32:
            return False,reason+" 관리자 권한 실행이 취소되었거나 실패했습니다."
        return True,"링크 생성 권한이 필요하여 관리자 권한으로 Frosty 실행을 요청했습니다."
    except OSError as e:
        return False,f"Frosty 실행에 실패했습니다. {e}"
