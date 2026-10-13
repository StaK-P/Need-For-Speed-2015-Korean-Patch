"""Automatic SUIT/SUITE donor font download and private local installation.

Uses pinned upstream GitHub commit hashes and SHA256 verification. The NFSKR
derived Hangul font is bundled under SIL OFL and installed locally. The user
does NOT need to change Windows system fonts or install an unrelated font app.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import shutil
from typing import Callable

from nfskr_installer_core import InstallerError,digest_file
from nfskr_bootstrap import _download

UPSTREAM={
    "SUIT-Medium.ttf":(
        "https://raw.githubusercontent.com/sun-typeface/SUIT/"
        "55118d981336d8fce005eb62888c12c0568ef7b0/fonts/static/ttf/SUIT-Medium.ttf",
        "06BE0060927642883B9027B275744FC8234826E6563015EBE3324F3802AE005F",
        592832),
    "SUITE-Heavy.ttf":(
        "https://raw.githubusercontent.com/sun-typeface/SUITE/"
        "a114fec078bfcbdc93a7b2190510ab83de2a2d40/fonts/static/ttf/SUITE-Heavy.ttf",
        "2FABA391890DC5327A593E928FB4AA507D9FACFFC8AB59628FDACB0550B1B2D3",
        566472),
}
DERIVED={
    "NFSKR-UI-Text-SemiBold.ttf":"D3C8358F8EF2D6B1C9A058C3B11E387A0CD0C5594E519E1A5B459C562BABBD0B",
}

def _verify(path:Path,expected:str)->bool:
    return path.is_file() and digest_file(path)==expected

def install_game_fonts(game:Path,workspace:Path,*,log=print,
                       prefer_download:bool=True,
                       progress:Callable[[int,str],None]|None=None)->dict[str,Path]:
    """Populate the game's separate NFSKR/Fonts folder, not the Windows registry."""
    from nfskr_local_assets import locate
    game=Path(game).resolve(strict=True)
    root=game/"NFSKR/Fonts"
    root.mkdir(parents=True,exist_ok=True)
    output={}
    for name,(url,sha,size) in UPSTREAM.items():
        target=root/name
        if target.is_file():
            if not _verify(target,sha):
                raise InstallerError("게임 폴더의 한글 폰트 파일이 예상과 달라 덮어쓰지 않았습니다: "+name)
        else:
            fetched=False
            if prefer_download:
                try:
                    _download(url,target,sha,size,log=lambda _:None,timeout=14)
                    fetched=True
                    log("공식 저장소에서 "+name+" 글꼴을 내려받고 검증했습니다.")
                except (OSError,Exception) as error:
                    # The standalone installer also contains an offline OFL
                    # donor. Network failures never force an invalid file.
                    if target.exists():
                        raise InstallerError("폰트 다운로드 무결성 확인에 실패했습니다: "+name) from error
                    log("다운로드 연결을 사용할 수 없어 포함된 검증 글꼴을 사용합니다: "+name)
            if not fetched:
                bundled=locate("fonts/vendor",name)
                if not _verify(bundled,sha):
                    raise InstallerError("내장 한글 글꼴의 체크섬이 올바르지 않습니다.")
                shutil.copyfile(bundled,target)
                if not _verify(target,sha):
                    target.unlink(missing_ok=True)
                    raise InstallerError("한글 글꼴 설치 후 검증에 실패했습니다.")
        output[name]=target
        if progress:
            percent=32 if name=="SUIT-Medium.ttf" else 35
            progress(percent,f"{name} 글꼴 확인을 완료했습니다.")
    for name,sha in DERIVED.items():
        target=root/name
        if not target.exists():
            bundled=locate("fonts/derived",name)
            if not _verify(bundled,sha):
                raise InstallerError("한국어 패치 전용 글꼴의 체크섬이 올바르지 않습니다.")
            shutil.copyfile(bundled,target)
        if not _verify(target,sha):
            raise InstallerError("한국어 패치 전용 글꼴 파일을 확인할 수 없습니다.")
        output[name]=target
    # Install legal notices alongside fonts. These are shipped unchanged.
    from nfskr_local_assets import LICENSES
    for name in LICENSES:
        dest=root/name
        source=locate("licenses",name)
        if not dest.exists():
            shutil.copyfile(source,dest)
        if digest_file(dest)!=digest_file(source):
            raise InstallerError("폰트 라이선스 파일이 변경되어 설치를 중단했습니다.")
    log("게임 폴더에 한국어 패치용 글꼴 3종을 준비했습니다. 시스템 글꼴은 변경하지 않았습니다.")
    return output
