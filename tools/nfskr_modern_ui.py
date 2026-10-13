"""Modern, three-action Windows installer interface for NFSKR 1st release.

All user-facing guidance and logs use polite Korean. Handles automatic
Frosty/game discovery and never changes the actual game or source FBMods.
"""
from __future__ import annotations
import json
from datetime import datetime
import os
from pathlib import Path
import queue
import threading
from tkinter import filedialog, messagebox
import traceback

import customtkinter as ctk
from PIL import Image

from nfskr_discovery import (
    discover, start_manager, config_path, safe_frosty_profile_name,
    read_game_config, selectable_source_packs
)
from nfskr_installer_core import (
    InstallerError, snapshot, read_config, rollback_install,
    installed_processes_running, update_target
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
# Keep the installer at a consistent physical size on 125%/150% Windows DPI,
# rather than letting the 900-point-high interface exceed a 1080p display.
if os.name=="nt":
    try:
        import ctypes
        dpi=ctypes.windll.user32.GetDpiForSystem()
        density=min(1.0,max(0.72,96.0/max(96,dpi)))
        ctk.set_widget_scaling(density)
        ctk.set_window_scaling(density)
    except (OSError,AttributeError):
        pass

BGCOLOR="#0B101B"
PANEL="#121A2A"
PANEL2="#172136"
BORDER="#263249"
TEXT="#F3F6FD"
MUTED="#99A8C0"
SUBTLE="#75859F"
ACCENT="#53A9FF"
ACCENT_HOVER="#3188DE"
GOOD="#79D9B2"
WARN="#F7C878"
PROJECT_REPOSITORY_URL="https://github.com/StaK-P/Need-For-Speed-2015-Korean-Patch"
TRANSLATION_FEEDBACK_URL=PROJECT_REPOSITORY_URL+"/issues/new?template=translation-feedback.yml"

def font(size:int,weight:str="normal"):
    return ctk.CTkFont(family="Malgun Gothic",size=size,weight=weight)


def compact_path(path:Path|str|None,max_length:int=94)->str:
    if not path:return "경로를 확인하고 있습니다."
    value=str(path)
    if len(value)<=max_length:return value
    return value[:30]+"  ···  "+value[-(max_length-38):]


def friendly_error(message:str)->str:
    """Convert untrusted/native exceptions to respectful Korean UI messages."""
    raw=str(message)
    lower=raw.casefold()
    if any(s in lower for s in ("frostymodmanager.exe", "frosty or nfs16", "close frosty",
                                "frosty is running","nfs16.exe is running")) and "running" in lower:
        return "Frosty Mod Manager와 게임을 정상 종료한 뒤 다시 시도해 주세요."
    if any(s in lower for s in ("game executable missing", "nfs16 game executable missing",
                                "nfs16.exe not found")):
        return "Need for Speed 2015의 설치 경로를 확인하지 못했습니다. Frosty에서 게임 경로를 먼저 지정해 주세요."
    if any(s in lower for s in ("missing mod", "frosty pack contains missing",
                                "mod source changed","source mod hash")):
        return "선택된 모드 파일에 변경 또는 누락이 있습니다. Frosty에서 원본 모드를 확인한 뒤 다시 실행해 주세요."
    if any(s in lower for s in ("configuration changed", "frosty changed",
                                "config changed","mod enable states or order changed")):
        return "작업 중 Frosty 설정이 변경되었습니다. Frosty를 종료한 뒤 설치를 다시 시작해 주세요."
    if any(s in lower for s in ("permission denied","access is denied","winerror 5",
                                "액세스가 거부되었습니다")):
        return "파일 접근 권한이 부족합니다. Frosty를 종료하고 설치 폴더 권한을 확인한 뒤 다시 시도해 주세요."
    if any(s in lower for s in ("symlink", "symbolic", "mklink")):
        return "심볼릭 링크 생성에 실패했습니다. 게임 드라이브와 Windows 권한을 확인해 주세요."
    if any(s in lower for s in ("unsupported", "conflict", "custom handler", "collision")):
        return "일부 모드 리소스를 안전하게 병합할 수 없어 설치를 중단했습니다. 기존 모드는 변경되지 않았습니다."
    return "설치 중 문제가 발생했습니다. 상세 진단 로그를 확인하신 뒤 다시 시도해 주세요."


def journal_files(root:Path)->list[Path]:
    base=root/"work/merge-tests/setup-gui"
    if not base.is_dir():return []
    return sorted(base.glob("*/install-journal-*.json"),
                  key=lambda p:p.stat().st_mtime,reverse=True)


class NFSKRApp(ctk.CTk):
    def __init__(self,root:Path,auto_scan:bool=True):
        super().__init__(fg_color=BGCOLOR)
        import sys
        base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent.parent))
        self.brand_assets_root=base
        icons=[base/"nfskr.ico",Path(__file__).resolve().parent.parent/"work/installer-build/nfskr.ico"]
        try:
            for icon in icons:
                if icon.is_file():
                    self.iconbitmap(str(icon))
                    break
        except (OSError,RuntimeError):
            pass
        self.root_dir=Path(root).resolve()
        self.support_log=self.root_dir/"logs"/("NFSKR-Setup-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".log")
        os.environ["NFSKR_WORKSPACE_ROOT"]=str(self.root_dir)
        self.title("NFSKR | Need for Speed 2015 한국어 패치")
        self.geometry("800x810")
        self.minsize(780,780)
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(1,weight=1)
        self.msgs=queue.Queue()
        self.running=False
        self.busy=False
        self.discovery=None
        self.snapshot=None
        self.profile_choice=ctk.StringVar(value="")
        self.profile_names=[]
        self.selection_cache={}
        self.last_source_config_hash=None
        self.mod_vars={}
        self.mod_checkboxes=[]
        self.scan_generation=0
        self.manager_override=None
        self.game_override=None
        self.latest_output=None
        self.make_frosty_shortcut=ctk.BooleanVar(value=True)
        self.make_nfs_shortcut=ctk.BooleanVar(value=True)
        self.all_source_mods=[]
        self.last_error=None
        self.update_existing=False
        self.target_profile="NFSKR"
        self.update_error=None
        self.process_state="idle"
        self.install_complete=False
        self.install_progress=0
        self.protocol("WM_DELETE_WINDOW",self._close)

        self._build_interface()
        self.after(90,self._messages)
        self.after(140,self._dark_titlebar)
        if auto_scan:
            self.after(190,self.reload)

    def _dark_titlebar(self):
        if os.name!="nt":return
        try:
            import ctypes
            hwnd=ctypes.windll.user32.GetParent(self.winfo_id())
            val=ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,20,ctypes.byref(val),ctypes.sizeof(val))
        except Exception:pass

    def _panel(self,parent,**kwargs):
        return ctk.CTkFrame(parent,fg_color=PANEL,height=1,
                            corner_radius=18,
                            border_width=1,border_color=BORDER,**kwargs)

    def _section_heading(self,parent,text):
        ctk.CTkLabel(parent,text=text,height=22,font=font(14,"bold"),
                     text_color=TEXT).pack(side="left")

    def _build_interface(self):
        self.main=ctk.CTkFrame(self,fg_color="transparent",height=1)
        self.main.grid(row=0,column=0,sticky="nsew",padx=26,pady=(13,13))
        self.main.grid_columnconfigure(0,weight=1)

        # Brand identity
        head=ctk.CTkFrame(self.main,fg_color="transparent",height=64)
        head.pack(fill="x",pady=(0,9))
        # Use the exact user-approved NFSKR logo. No synthetic blue "N" tile.
        logo_file=next((p for p in (
            self.brand_assets_root/"nfskr-logo.png",
            Path(__file__).resolve().parent.parent/"work/installer-build/nfskr-logo.png"
        ) if p.is_file()),None)
        if logo_file is not None:
            with Image.open(logo_file) as logo_image:
                art=logo_image.convert("RGBA")
                if art.getpixel((0,0))[3]!=0:
                    raise ValueError("The NFSKR icon background must be transparent")
                self.brand_logo=ctk.CTkImage(
                    light_image=art,dark_image=art,size=(50,50))
            self.brand_logo_widget=ctk.CTkLabel(
                head,text="",image=self.brand_logo,
                width=50,height=50,fg_color="transparent")
            self.brand_logo_widget.pack(side="left",padx=(0,14))
        else:
            # Development-only fallback if assets were not built yet.
            self.brand_logo_widget=ctk.CTkLabel(head,text="NFSKR",
                 width=50,height=50,font=ctk.CTkFont(size=11,weight="bold"),
                 text_color=ACCENT)
            self.brand_logo_widget.pack(side="left",padx=(0,14))
        names=ctk.CTkFrame(head,fg_color="transparent",height=1)
        names.pack(side="left",fill="y")
        brand_row=ctk.CTkFrame(names,fg_color="transparent",height=30)
        brand_row.pack(anchor="w")
        ctk.CTkLabel(brand_row,text="NFSKR",font=ctk.CTkFont(
            family="Segoe UI",size=24,weight="bold"),
                     text_color=TEXT,height=30).pack(side="left")
        # Published repository; the GitHub mark opens the official project page.
        github_file=next((path for path in (
            self.brand_assets_root/"github-mark.png",
            Path(__file__).resolve().parent.parent/"work/installer-build/github-mark.png"
        ) if path.is_file()),None)
        self.github_icon=None
        self.github_icon_label=None
        self.github_repository_url=PROJECT_REPOSITORY_URL
        if github_file is not None:
            with Image.open(github_file) as github_source:
                mark=github_source.convert("RGBA")
            self.github_icon=ctk.CTkImage(
                light_image=mark,dark_image=mark,size=(23,23))
            self.github_icon_label=ctk.CTkLabel(
                brand_row,text="",image=self.github_icon,
                width=28,height=29,fg_color="transparent")
            self.github_icon_label.pack(side="left",padx=(12,0))
            self.github_icon_label.configure(cursor="hand2")
            self.github_icon_label.bind(
                "<Button-1>",lambda _event:self._open_project_repository())
        ctk.CTkLabel(names,text="Need for Speed 2015 · 한국어 패치",
                     font=font(12),text_color=MUTED).pack(anchor="w")
        release=ctk.CTkFrame(head,fg_color="transparent",height=1)
        release.pack(side="right",anchor="n")
        ctk.CTkLabel(release,text="v1.1",
                     font=ctk.CTkFont(family="Segoe UI",size=10,weight="bold"),
                     text_color=ACCENT).pack(anchor="e",pady=(5,2))
        ctk.CTkLabel(release,text="by StaK_P",
                     font=ctk.CTkFont(family="Segoe UI",size=11),
                     text_color=MUTED).pack(anchor="e")

        # Installation destinations (read-only, auto-detected)
        env=self._panel(self.main)
        env.pack(fill="x",pady=(0,8))
        heading=ctk.CTkFrame(env,fg_color="transparent",height=1)
        heading.pack(fill="x",padx=19,pady=(8,0))
        self._section_heading(heading,"설치 환경")
        self.detect_dot=ctk.CTkLabel(heading,text="●  확인 중",
                    font=font(11),text_color=WARN)
        self.detect_dot.pack(side="right")
        row1=ctk.CTkFrame(env,fg_color="transparent",height=1)
        row1.pack(fill="x",padx=19,pady=(0,0))
        ctk.CTkLabel(row1,text="게임",width=74,anchor="w",font=font(11),
                     text_color=SUBTLE,height=22).pack(side="left")
        self.game_label=ctk.CTkLabel(row1,text="Need for Speed 2015 검색 중...",
                                    anchor="w",height=22,font=ctk.CTkFont(family="Segoe UI",size=11),text_color=TEXT)
        self.game_label.pack(side="left",fill="x",expand=True)
        row2=ctk.CTkFrame(env,fg_color="transparent",height=1)
        row2.pack(fill="x",padx=19,pady=(0,9))
        ctk.CTkLabel(row2,text="Frosty",width=74,anchor="w",font=font(11),
                     text_color=SUBTLE,height=22).pack(side="left")
        self.manager_label=ctk.CTkLabel(row2,text="Frosty Mod Manager 검색 중...",
                     anchor="w",height=22,font=ctk.CTkFont(family="Segoe UI",size=11),text_color=TEXT)
        self.manager_label.pack(side="left",fill="x",expand=True)

        # Original game mods
        sources=self._panel(self.main)
        sources.configure(height=289)
        sources.pack(fill="x",pady=(0,8))
        sources.pack_propagate(False)
        row=ctk.CTkFrame(sources,fg_color="transparent",height=1)
        row.pack(fill="x",padx=19,pady=(8,0))
        self._section_heading(row,"적용할 기존 모드")
        self.mod_count=ctk.CTkLabel(row,text="확인 중",font=font(11),
                                    text_color=ACCENT)
        self.mod_count.pack(side="right")
        selector=ctk.CTkFrame(sources,fg_color="transparent",height=35)
        selector.pack(fill="x",padx=19,pady=(1,6))
        self.pack_title=ctk.CTkLabel(
            selector,text="병합 기준 프로필",width=114,anchor="w",
            font=font(11),text_color=MUTED)
        self.pack_title.pack(side="left",padx=(0,7))
        self.profile_dropdown=ctk.CTkOptionMenu(
            selector,variable=self.profile_choice,
            values=["프로필을 확인하는 중입니다."],height=32,
            corner_radius=9,width=290,font=font(11),
            fg_color="#263349",button_color="#345074",
            button_hover_color="#41678F",
            dropdown_fg_color=PANEL2,dropdown_hover_color="#29405C",
            dropdown_text_color=TEXT,text_color=TEXT,
            command=self._on_source_profile_changed)
        self.profile_dropdown.pack(side="left",fill="x",expand=True)
        self.mod_list=ctk.CTkScrollableFrame(sources,height=172,
            fg_color=PANEL2,corner_radius=11,
            scrollbar_button_color="#3D516E",
            scrollbar_button_hover_color="#537296")
        self.mod_list.pack(fill="both",expand=True,padx=17,pady=(0,4))
        self._mod_lines([])
        ctk.CTkLabel(sources,
            text="체크한 모드만 병합됩니다. 새 모드는 원본 프로필에 추가한 뒤 업데이트하세요.",
            font=font(10),text_color=MUTED,
            height=18,anchor="w").pack(fill="x",padx=19,pady=(0,5))

        # Progress and human-readable log
        prog=self._panel(self.main)
        prog.configure(height=209)
        prog.pack(fill="x",pady=(0,8))
        prog.pack_propagate(False)
        band=ctk.CTkFrame(prog,fg_color="transparent",height=1)
        band.pack(fill="x",padx=19,pady=(8,2))
        ctk.CTkLabel(band,text="진행 상태",font=font(13,"bold"),
                     text_color=TEXT).pack(side="left")
        self.stage=ctk.CTkLabel(band,text="환경을 확인하는 중입니다.",
                     font=font(11),text_color=ACCENT)
        self.percent_label=ctk.CTkLabel(
            band,text="0%",font=ctk.CTkFont(family="Segoe UI",size=11,weight="bold"),
            text_color=ACCENT,width=42)
        self.percent_label.pack(side="right",padx=(11,0))
        self.stage.pack(side="right")
        self.progress=ctk.CTkProgressBar(prog,height=5,
            progress_color=ACCENT,fg_color="#2A354A",corner_radius=5)
        self.progress.pack(fill="x",padx=19,pady=(0,7))
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self.log=ctk.CTkTextbox(prog,height=134,corner_radius=11,
            fg_color="#0D1523",border_width=0,font=font(10),
            text_color="#CBD5E5",wrap="word",activate_scrollbars=True)
        self.log.pack(fill="x",padx=18,pady=(0,8))
        self.log.configure(state="disabled")
        self._append_log("게임과 Frosty의 설치 경로를 자동 확인하고 있습니다.")

        # Two independent, optional desktop shortcut checkboxes.
        shortcut_options=ctk.CTkFrame(self.main,fg_color="transparent",height=26)
        shortcut_options.pack(fill="x",pady=(2,10))
        self.frosty_link_checkbox=ctk.CTkCheckBox(
            shortcut_options,text="Frosty 바탕화면 바로가기",
            variable=self.make_frosty_shortcut,checkbox_width=18,checkbox_height=18,
            corner_radius=5,border_width=2,font=font(11),
            text_color="#C4D0E1",fg_color=ACCENT,hover_color=ACCENT_HOVER)
        self.frosty_link_checkbox.pack(side="left",padx=(4,26))
        self.nfs_link_checkbox=ctk.CTkCheckBox(
            shortcut_options,text="한국어 패치 적용 NFS 실행 바로가기",
            variable=self.make_nfs_shortcut,checkbox_width=18,checkbox_height=18,
            corner_radius=5,border_width=2,font=font(11),
            text_color="#C4D0E1",fg_color=ACCENT,hover_color=ACCENT_HOVER)
        self.nfs_link_checkbox.pack(side="left")

        # Three and only three primary actions
        actions=ctk.CTkFrame(self.main,fg_color="transparent",height=48)
        actions.pack(fill="x",pady=(1,5))
        actions.grid_columnconfigure((0,1,2),weight=1,uniform="button")
        self.install_button=ctk.CTkButton(actions,text="설치",height=43,
            font=font(14,"bold"),corner_radius=12,
            fg_color=ACCENT,hover_color=ACCENT_HOVER,
            text_color="#091522",command=self._start_install)
        self.install_button.grid(row=0,column=0,sticky="ew",padx=(0,8))
        self.restore_button=ctk.CTkButton(actions,text="복원",height=43,
            font=font(13,"bold"),corner_radius=12,
            fg_color="#263248",hover_color="#36465F",
            text_color=TEXT,command=self._restore)
        self.restore_button.grid(row=0,column=1,sticky="ew",padx=4)
        self.frosty_button=ctk.CTkButton(actions,text="Frosty 실행",height=43,
            font=font(13,"bold"),corner_radius=12,
            fg_color="#263248",hover_color="#36465F",
            text_color=TEXT,command=self._open_frosty)
        self.frosty_button.grid(row=0,column=2,sticky="ew",padx=(8,0))

        foot=ctk.CTkFrame(self.main,fg_color="transparent",height=1)
        foot.pack(fill="x",pady=(0,0))
        ctk.CTkLabel(foot,text="NFSKR · by StaK_P",font=ctk.CTkFont(
            family="Segoe UI",size=10),text_color=SUBTLE,height=18).pack(side="left")
        self.credits_button=ctk.CTkButton(
            foot,text="크레딧 · 출처",width=93,height=22,corner_radius=6,
            fg_color="transparent",hover_color=PANEL2,text_color=MUTED,
            font=font(10),command=self._open_credits)
        self.credits_button.pack(side="left",padx=(10,0))
        self.feedback_button=ctk.CTkButton(
            foot,text="번역 피드백 ↗",width=103,height=22,corner_radius=6,
            fg_color="transparent",hover_color=PANEL2,text_color=ACCENT,
            font=font(10),command=self._open_translation_feedback)
        self.feedback_button.pack(side="left",padx=(5,0))
        ctk.CTkLabel(foot,text="원본 모드 보존  ·  로컬 병합  ·  되돌리기 지원",
            font=font(10),text_color=SUBTLE,height=18).pack(side="right")

    def _open_credits(self):
        # Credits are informational, never a fourth installation action.
        from nfskr_credits import show_credits
        show_credits(self)

    def _open_project_repository(self):
        from nfskr_credits import _open_link
        _open_link(self,PROJECT_REPOSITORY_URL)

    def _open_translation_feedback(self):
        from nfskr_credits import _open_link
        _open_link(self,TRANSLATION_FEEDBACK_URL)

    def _mod_lines(self,names:list[str]):
        """Placeholder in the same scroll area used for actual checkboxes."""
        for widget in self.mod_list.winfo_children():
            widget.destroy()
        self.mod_vars={}
        self.mod_checkboxes=[]
        label=names[0] if names else "Frosty의 모드 목록을 불러오고 있습니다."
        ctk.CTkLabel(self.mod_list,text=label,anchor="w",height=28,
                     font=font(11),text_color=MUTED).pack(
                     fill="x",padx=13,pady=10)

    def _selected_mod_names(self)->list[str]:
        """Return the exact user selection; an empty list means Korean-only."""
        if not self.snapshot:return []
        # GUI controls are ordered according to this source pack's Frosty data.
        return [x.name for x in self.all_source_mods
                if self.mod_vars.get(x.name) is not None
                and self.mod_vars[x.name].get()]

    def _on_mod_toggled(self,user_action:bool=False):
        if not self.snapshot:return
        names=self._selected_mod_names()
        self.selection_cache[self.snapshot.selected_pack]=set(names)
        self.mod_count.configure(text=f"선택 {len(names)} / {len(self.all_source_mods)}개")
        if user_action and self.install_complete:
            self.install_complete=False
            self._set_progress(0,"설치할 준비가 완료되었습니다.")

    def _render_mod_checkboxes(self,snap):
        from nfskr_composite import selectable_source_mods
        self.all_source_mods=selectable_source_mods(snap)
        for widget in self.mod_list.winfo_children():
            widget.destroy()
        self.mod_vars={}
        self.mod_checkboxes=[]
        chosen=self.selection_cache.get(
            snap.selected_pack,
            {x.name for x in self.all_source_mods if x.enabled})
        if not self.all_source_mods:
            self._mod_lines(["다른 모드를 선택하지 않아 한국어 패치만 설치됩니다."])
            self.mod_count.configure(text="선택 0 / 0개")
            return
        for item in self.all_source_mods:
            var=ctk.BooleanVar(value=(item.name in chosen))
            hint=("(기존 비활성)" if not item.enabled else "")
            label=item.name+("  "+hint if hint else "")
            if len(label)>94:
                label=label[:90]+"…"
            control=ctk.CTkCheckBox(
                self.mod_list,text=label,variable=var,
                command=lambda:self._on_mod_toggled(user_action=True),checkbox_width=18,
                checkbox_height=18,corner_radius=5,border_width=2,
                font=font(10),text_color=TEXT if item.enabled else MUTED,
                fg_color=ACCENT,hover_color=ACCENT_HOVER,
                height=20)
            control.pack(fill="x",padx=10,pady=(1,1),anchor="w")
            self.mod_vars[item.name]=var
            self.mod_checkboxes.append(control)
        self._on_mod_toggled()

    def _on_source_profile_changed(self,value):
        if self.running or self.busy:return
        if self.snapshot is not None and value==self.snapshot.selected_pack:
            return
        self.profile_choice.set(value)
        if self.install_complete:
            self.install_complete=False
            self._set_progress(0,"선택한 프로필의 모드를 불러오고 있습니다.")
        self._status("선택한 프로필의 모드를 불러오고 있습니다.")
        self.reload()

    def _append_log(self,message:str):
        # No raw stack traces or native error messages in the main UI.
        line=str(message).strip()
        if not line:return
        try:
            self.support_log.parent.mkdir(parents=True,exist_ok=True)
            with self.support_log.open("a",encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        except OSError:
            pass
        self.log.configure(state="normal")
        self.log.insert("end","•  "+line+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _status(self,text:str,color:str=ACCENT):
        self.stage.configure(text=text,text_color=color)

    def _set_progress(self,percentage:int,message:str):
        """Reflect real completed work milestones, without any timed animation."""
        if not isinstance(percentage,int) or not 0<=percentage<=100:
            raise ValueError("진행률은 0~100의 정수여야 합니다.")
        self.install_progress=percentage
        self.progress.configure(mode="determinate")
        self.progress.set(percentage/100.0)
        self.percent_label.configure(text=f"{percentage}%")
        self._status(message,GOOD if percentage==100 else ACCENT)

    def reload(self):
        if self.running:return
        if not self.install_complete:
            self._status("경로를 검색하는 중입니다.")
        self.detect_dot.configure(text="●  검색 중",text_color=WARN)
        self.busy=True
        self.profile_dropdown.configure(state="disabled")
        for checkbox in self.mod_checkboxes:
            checkbox.configure(state="disabled")
        self.scan_generation+=1
        generation=self.scan_generation
        requested=self.profile_choice.get()
        threading.Thread(target=self._find_paths,
                         args=(generation,requested),daemon=True).start()

    def _find_paths(self,generation,requested):
        try:
            latest=discover(config=config_path(),preferred_manager=self.manager_override,
                            journal_dir=self.root_dir/"work/merge-tests/setup-gui")
            if self.game_override and (self.game_override/"NFS16.exe").is_file():
                latest.game=self.game_override
            cfg=read_game_config(latest.config)
            choices=selectable_source_packs(cfg)
            picked=(requested if requested in choices else
                    latest.source_pack if latest.source_pack in choices else
                    choices[0] if choices else "")
            if latest.manager and picked:
                snap=snapshot(latest.config,latest.manager,picked)
            else:
                snap=None
            self.msgs.put(("scan",(generation,latest,snap,choices,picked)))
        except Exception as error:
            self.msgs.put(("scan_error",(generation,str(error))))

    def apply_scan(self,data,snap,choices=None,picked=None):
        self.discovery=data
        self.busy=False
        if snap and self.last_source_config_hash != snap.config_sha256:
            self.selection_cache.clear()
            self.last_source_config_hash=snap.config_sha256
        self.snapshot=snap
        cfg=read_game_config(data.config)
        self.update_existing=False
        self.update_error=None
        self.target_profile="NFSKR"
        if snap is not None:
            try:
                self.target_profile,self.update_existing=update_target(
                    cfg.get("Packs",{}),snap.manager_dir/"Mods/NFS16",
                    cfg.get("Options",{}).get("SelectedPack",""))
            except InstallerError as error:
                self.update_error=str(error)
        self.install_button.configure(
            text="업데이트" if self.update_existing else "설치",
            state="disabled" if self.update_error else "normal")
        if choices is None:
            choices=selectable_source_packs(cfg)
        if picked is None:
            picked=snap.selected_pack if snap else (
                data.source_pack if data.source_pack in choices else
                choices[0] if choices else "")
        self.profile_names=list(choices)
        self.profile_dropdown.configure(
            values=self.profile_names or ["선택 가능한 프로필이 없습니다."],
            state="normal" if (self.profile_names and data.manager) else "disabled")
        self.profile_choice.set(
            picked if picked in self.profile_names else
            "선택 가능한 프로필이 없습니다.")
        if data.game:self.game_label.configure(text=compact_path(data.game,76))
        else:self.game_label.configure(text="게임 경로를 찾지 못했습니다.")
        if data.manager:self.manager_label.configure(text=compact_path(data.manager,76))
        else:self.manager_label.configure(text="Frosty 설치 경로를 찾지 못했습니다.")
        healthy=bool(data.game and data.manager and data.source_pack and snap)
        can_install=bool(data.game)
        self.detect_dot.configure(text=("●  확인 완료" if healthy else "●  확인 필요"),
                                  text_color=GOOD if healthy else WARN)
        if not healthy:
            if data.game and not data.manager:
                self.pack_title.configure(
                    text="Frosty가 없습니다. 설치 시 공식 파일을 자동으로 준비합니다.")
                self.mod_count.configure(text="새 프로필")
                self._mod_lines(["기존 모드 없이 한국어 패치만 설치됩니다."])
                self._status("설치 시 Frosty와 글꼴을 자동으로 설치합니다.",GOOD)
                self._append_log(
                    "Frosty Mod Manager가 없습니다. 설치 버튼을 누르면 게임 폴더 안에 공식 1.0.6.3 버전을 자동 설치합니다.")
            elif data.game and data.manager and not data.source_pack:
                self.pack_title.configure(text="Frosty의 신규 게임 프로필이 자동 생성됩니다.")
                self.mod_count.configure(text="새 프로필")
                self._mod_lines(["기존 모드 없이 한국어 패치만 설치됩니다."])
                self._status("설치 시 NFS16 프로필을 자동 생성합니다.",GOOD)
            else:
                self.pack_title.configure(text="설치 경로를 자동으로 확인하지 못했습니다.")
                self.mod_count.configure(text="확인 필요")
                self._mod_lines([])
                self._status("게임 설치 경로를 확인해 주세요.",WARN)
                self._append_log("게임 경로를 자동으로 인식하지 못했습니다. 설치 버튼에서 게임 경로를 선택해 주세요.")
            return
        self.pack_title.configure(text="병합 기준 프로필")
        self._render_mod_checkboxes(snap)
        if self.install_complete:
            self._set_progress(100,"패치 완료")
        else:
            self._set_progress(0,"설치할 준비가 완료되었습니다.")
        self._append_log(
            f"게임 및 Frosty 경로를 확인했습니다. '{snap.selected_pack}' 프로필의 활성 모드 {len(snap.enabled_mods)}개를 자동으로 병합합니다.")
        if data.current_pack and not data.current_pack.isascii():
            self._append_log(
                "이전 한글 경로 프로필이 감지되었습니다. Frosty 심볼릭 링크 오류를 방지하기 위해 영문 내부 프로필 경로로 설치됩니다.")

    def _ask_for_manager(self)->bool:
        filename=filedialog.askopenfilename(
            parent=self,title="FrostyModManager.exe 파일을 선택해 주세요.",
            filetypes=[("Frosty Mod Manager","FrostyModManager.exe"),("실행 파일","*.exe")])
        if not filename:return False
        target=Path(filename).resolve()
        if target.name.lower()!="frostymodmanager.exe":
            messagebox.showerror("경로 확인","FrostyModManager.exe를 선택해 주세요.",parent=self)
            return False
        self.manager_override=target.parent
        self.reload()
        return True

    def _ask_for_game(self)->bool:
        filename=filedialog.askopenfilename(
            parent=self,title="Need for Speed 2015의 NFS16.exe 파일을 선택해 주세요.",
            filetypes=[("Need for Speed 2015","NFS16.exe"),("실행 파일","*.exe")])
        if not filename:return False
        target=Path(filename).resolve()
        if target.name.lower()!="nfs16.exe":
            messagebox.showerror("경로 확인","NFS16.exe 파일을 선택해 주세요.",parent=self)
            return False
        # A mismatched Frosty game path requires normal Frosty setup.
        saved=read_game_config(config_path()).get("GamePath")
        if saved and Path(saved).resolve()!=target.parent:
            messagebox.showwarning("Frosty 게임 경로 확인",
                "설치된 게임을 찾았으나 Frosty에 기록된 경로와 다릅니다.\n"
                "Frosty 설정에서 게임 경로를 지정한 후 다시 설치해 주세요.",parent=self)
            return False
        self.game_override=target.parent
        self.reload()
        return True

    def _ready(self)->bool:
        if self.running or self.busy:return False
        if not self.discovery or not self.discovery.game:
            self._ask_for_game()
            return False
        # Missing Frosty or missing NFS16 pack is now a supported fresh install.
        return True

    def _start_install(self):
        if not self._ready():return
        if self.update_error:
            messagebox.showerror("프로필 갱신 불가",self.update_error,parent=self)
            return
        if installed_processes_running():
            messagebox.showwarning("Frosty 종료 필요",
                "설치 전에 Frosty Mod Manager와 게임을 정상 종료해 주세요.\n"
                "종료 후 다시 설치하시면 변경된 설정을 자동으로 읽습니다.",
                parent=self)
            return
        snap=self.snapshot
        chosen=self._selected_mod_names() if snap else []
        count=len(chosen)
        name=snap.selected_pack if snap else "Default"
        if snap is not None and self.profile_choice.get()!=name:
            self.reload()
            messagebox.showinfo("프로필 확인",
                "선택하신 프로필의 모드 목록이 갱신 중입니다. 잠시 후 다시 설치해 주세요.",
                parent=self)
            return
        if snap is not None:
            try:
                live=snapshot(self.discovery.config,self.discovery.manager,name)
            except (InstallerError,OSError) as error:
                self.reload()
                messagebox.showwarning("원본 모드 재확인",
                    "Frosty 원본 모드를 다시 확인해야 합니다.\n"+str(error),parent=self)
                return
            if live!=snap:
                self.reload()
                messagebox.showinfo("새 모드 감지",
                    "Frosty의 모드 목록이나 파일이 변경됐습니다.\n"
                    "새 목록을 불러온 뒤 업데이트 버튼을 다시 눌러 주세요.",
                    parent=self)
                return
        needs_frosty=not self.discovery.manager
        operation=("기존 '"+self.target_profile+"' 한국어 패치 프로필을 업데이트합니다.\n"
                   if self.update_existing else "새 NFSKR 프로필을 설치합니다.\n")
        confirmation=(
            operation
            +f"'{name}' 원본 프로필에서 선택하신 모드 {count}개를 재병합합니다.\n"
            +("Frosty가 없어 공식 1.0.6.3 버전(약 80MB)을 게임 폴더에 자동 설치합니다.\n" if needs_frosty else "")
            +"기존 합본은 복원할 수 있도록 보존하고, 원본 모드는 수정하지 않습니다.\n\n"
            +"계속하시겠습니까?")
        if not messagebox.askyesno("NFSKR 업데이트" if self.update_existing else "NFSKR 설치",
                                   confirmation,parent=self):
            return
        self.install_complete=False
        self.running=True
        self._set_progress(0,"설치를 준비하고 있습니다.")
        self.install_button.configure(state="disabled")
        self.restore_button.configure(state="disabled")
        self.frosty_button.configure(state="disabled")
        self.profile_dropdown.configure(state="disabled")
        for checkbox in self.mod_checkboxes:
            checkbox.configure(state="disabled")
        self.frosty_link_checkbox.configure(state="disabled")
        self.nfs_link_checkbox.configure(state="disabled")
        self._append_log(f"한국어 패치 설치를 시작했습니다. '{name}' 프로필의 모드 {count}개를 선택했습니다.")
        threading.Thread(target=self._install_worker,
                         args=(self.discovery.manager,self.discovery.config,
                               self.discovery.game,
                               snap.selected_pack if snap else None,
                               chosen,
                               bool(self.make_frosty_shortcut.get()),
                               bool(self.make_nfs_shortcut.get())),daemon=True).start()

    def _install_worker(self,manager,config,game,source,chosen,shortcut_frosty,shortcut_nfs):
        # Keep Frosty, its dependencies, downloaded donor fonts and NFSKR's
        # private native tools together inside the GAME's NFSKR directory.
        # The user-profile folder holds only diagnostic journals and logs.
        previous=os.environ.get("NFSKR_WORKSPACE_ROOT")
        workspace=Path(game)/"NFSKR/Tools"
        os.environ["NFSKR_WORKSPACE_ROOT"]=str(workspace)
        try:
            from nfskr_setup_flow import build_and_optionally_install
            result=build_and_optionally_install(
                 manager=manager,config=config,game=game,source_pack=source,
                 selected_mod_names=chosen,
                 desktop_frosty=shortcut_frosty,desktop_game=shortcut_nfs,
                 install=True,output_root=self.root_dir/"work/merge-tests/setup-gui",
                 log=lambda m:self.msgs.put(("progress",str(m))),
                 progress=lambda percentage,description:self.msgs.put(
                    ("install_stage",(percentage,description))))
            self.msgs.put(("install_success",result))
        except Exception as error:
            self.msgs.put(("install_error",{"message":friendly_error(str(error)),
                       "technical":str(error),"trace":traceback.format_exc()}))
        finally:
            if previous is None:
                os.environ.pop("NFSKR_WORKSPACE_ROOT",None)
            else:
                os.environ["NFSKR_WORKSPACE_ROOT"]=previous

    def _find_restore_journal(self)->Path|None:
        if not self.discovery:return None
        saved=read_game_config(self.discovery.config)
        current=saved.get("Options",{}).get("SelectedPack","")
        for file in journal_files(self.root_dir):
            try:
                data=json.loads(file.read_text(encoding="utf-8"))
                if data.get("new_pack")==current:return file
            except (ValueError,OSError):
                continue
        return None

    def _restore(self):
        if self.running or self.busy:return
        if installed_processes_running():
            messagebox.showwarning("Frosty 종료 필요",
                "복원 전에 Frosty Mod Manager와 게임을 정상 종료해 주세요.",
                parent=self)
            return
        journal=self._find_restore_journal()
        if not journal:
            messagebox.showinfo("복원 안내",
                "현재 선택된 프로필에 대해 복원할 NFSKR 설치 기록이 없습니다.",
                parent=self)
            return
        try:
            item=json.loads(journal.read_text(encoding="utf8"))
            is_update=item.get("operation")=="update"
        except (OSError,ValueError):
            is_update=False
        note=("직전 한국어 패치 버전과 모드 구성을 복원하시겠습니까?\n"
              if is_update else
              "NFSKR 설치 전 프로필과 설정을 복원하시겠습니까?\n")
        if not messagebox.askyesno("이전 패치 복원" if is_update else "이전 프로필 복원",
            note+"원본 모드와 게임 데이터는 그대로 유지됩니다.",
            parent=self):
            return
        try:
            result=rollback_install(journal)
            self._append_log("이전 Frosty 프로필과 설정을 복원했습니다.")
            self.install_complete=False
            self._set_progress(0,"복원이 완료되었습니다.")
            self.reload()
        except Exception as error:
            self._append_log("복원을 완료하지 못했습니다. "+friendly_error(str(error)))
            messagebox.showerror("복원 중단",
                "설정을 안전하게 복원하지 못했습니다.\n"+friendly_error(str(error)),
                parent=self)

    def _open_frosty(self):
        if self.running:return
        if not self.discovery or not self.discovery.manager:
            messagebox.showinfo("Frosty 자동 설치",
                "Frosty Mod Manager가 설치되지 않았습니다. 먼저 설치 버튼을 누르시면 게임 폴더에 자동 설치됩니다.",
                parent=self)
            return
        if not self.discovery.game:
            self._ask_for_game()
            return
        current=read_game_config(self.discovery.config).get("Options",{}).get("SelectedPack","")
        if current and not current.isascii():
            if not messagebox.askyesno("기존 프로필의 한글 경로 문제",
                "현재 선택된 Frosty 프로필에는 한글 경로가 포함되어 있습니다.\n"
                "Frosty 1.0.6.3에서 심볼릭 링크 생성 오류가 발생할 수 있습니다.\n"
                "가능하면 먼저 NFSKR 설치를 완료해 주세요.\n\n"
                "그래도 Frosty를 실행하시겠습니까?",parent=self):
                return
        success,status=start_manager(self.discovery.manager,self.discovery.game)
        if not self.install_complete:
            self._status(status,GOOD if success else WARN)
        self._append_log(status)
        if not success:
            messagebox.showwarning("Frosty 실행",
                status,parent=self)

    def _messages(self):
        try:
            while True:
                kind,data=self.msgs.get_nowait()
                if kind=="scan":
                    generation,latest,snap,choices,picked=data
                    if generation==self.scan_generation:
                        self.apply_scan(latest,snap,choices,picked)
                elif kind=="scan_error":
                    generation,technical=data
                    if generation!=self.scan_generation:
                        continue
                    self.busy=False
                    self.detect_dot.configure(text="●  확인 실패",text_color=WARN)
                    self._status("자동 경로 확인에 실패했습니다.",WARN)
                    self._append_log("게임 및 Frosty 경로를 확인하지 못했습니다. 설치 버튼으로 경로를 지정할 수 있습니다.")
                elif kind=="progress":
                    self._append_log(data)
                    if "글꼴" in data:self._status("한국어 글꼴을 준비하고 있습니다.")
                    elif "병합" in data:self._status("모드 충돌을 자동으로 병합하고 있습니다.")
                    elif "검증" in data:self._status("파일 무결성을 검증하고 있습니다.")
                    elif "프로필" in data:self._status("프로필을 설치하고 있습니다.")
                elif kind=="install_stage":
                    percentage,description=data
                    if self.running and percentage>=self.install_progress:
                        self._set_progress(percentage,description)
                elif kind in ("install_success","install_error"):
                    self.running=False
                    if kind=="install_success":
                        self.install_complete=True
                        self._set_progress(100,"패치 완료")
                    else:
                        # Keep the last verified milestone on errors, not 100%.
                        self.install_complete=False
                        self._status("설치가 중단되었습니다.",WARN)
                    self.install_button.configure(state="normal")
                    self.restore_button.configure(state="normal")
                    self.frosty_button.configure(state="normal")
                    self.profile_dropdown.configure(state="normal" if self.profile_names and self.discovery and self.discovery.manager else "disabled")
                    for checkbox in self.mod_checkboxes:
                        checkbox.configure(state="normal")
                    self.frosty_link_checkbox.configure(state="normal")
                    self.nfs_link_checkbox.configure(state="normal")
                    if kind=="install_success":
                        self.latest_output=Path(data["output"])
                        if data.get("operation")=="update":
                            self._append_log(
                                f"기존 '{data['installed_profile']}' 프로필을 업데이트했습니다. 이전 합본은 복원용으로 보존됩니다.")
                        else:
                            self._append_log(
                                f"새 '{data['installed_profile']}' 프로필을 설치했습니다. 원본 Frosty 프로필은 보존됩니다.")
                        self._append_log("Frosty 실행 버튼으로 게임을 확인해 주세요.")
                        if data.get("created_shortcuts"):
                            self._append_log(f"바탕화면 바로가기 {len(data['created_shortcuts'])}개를 생성했습니다.")
                        if data.get("reused_shortcuts"):
                            self._append_log(f"기존 바탕화면 바로가기 {len(data['reused_shortcuts'])}개를 유지했습니다.")
                        if data.get("shortcut_warnings"):
                            self._append_log("바로가기 생성 일부가 완료되지 않았습니다. 자세한 내용은 진단 로그를 확인해 주세요.")
                        # Keep installed success visible, refresh only the data after.
                        self.after(950,self.reload)
                    else:
                        self._append_log(
                            "안전 검증 또는 파일 처리 중 문제가 발생하여 설치를 중단했습니다.")
                        self._append_log(data["message"])
                        try:
                            with self.support_log.open("a",encoding="utf-8") as f:
                                f.write("\n[상세 진단 정보]\n"+data["technical"]+"\n"+data["trace"]+"\n")
                        except OSError:
                            pass
                        messagebox.showerror("설치 실패",
                            "한국어 패치를 설치하지 못했습니다.\n\n"+data["message"]+
                            "\n\n진단 로그가 로컬에 저장되어 있습니다.",parent=self)
        except queue.Empty:
            pass
        self.after(100,self._messages)

    def _close(self):
        if self.running:
            messagebox.showinfo("설치 진행 중",
                "안전한 설치를 위해 작업이 완료될 때까지 기다려 주세요.",
                parent=self)
            return
        self.destroy()
