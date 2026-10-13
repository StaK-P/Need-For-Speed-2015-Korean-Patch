"""Third-party attribution dialog for the standalone NFSKR Windows installer.

Credits intentionally distinguish shipped components, optional downloads and
development-only tools. All links point to the original publishers.
"""
from __future__ import annotations

from dataclasses import dataclass
from tkinter import messagebox
import webbrowser

import customtkinter as ctk


@dataclass(frozen=True)
class Credit:
    group: str
    title: str
    author: str
    purpose: str
    license: str
    source: str
    license_url: str


CREDITS: tuple[Credit, ...] = (
    Credit("모딩 도구", "Frosty Toolsuite 1.0.6.3",
           "CadeEvs / Frosty Toolsuite 기여자",
           "Frosty Mod Manager. 필요 시 원본 릴리스를 별도 다운로드합니다.",
           "CC BY-NC-ND 4.0",
           "https://github.com/CadeEvs/FrostyToolsuite/releases/tag/v1.0.6.3",
           "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
    Credit("모딩 도구", "Frosty Flammenwerfer Plugin",
           "shoushou1106 및 기여자",
           "번역 리소스 제작·검수용 플러그인. 패처 실행 파일에는 포함되지 않습니다.",
           "GPL-3.0",
           "https://github.com/shoushou1106/FrostyFlammenwerferPlugin",
           "https://www.gnu.org/licenses/gpl-3.0.html"),
    Credit("한글 글꼴", "SUIT",
           "SUNN / sun-typeface",
           "한국어 패치의 글꼴 데이터에 사용. 원본 OFL 고지를 동봉합니다.",
           "SIL OFL 1.1",
           "https://github.com/sun-typeface/SUIT",
           "https://github.com/sun-typeface/SUIT/blob/main/LICENSE"),
    Credit("한글 글꼴", "SUITE",
           "SUNN / sun-typeface",
           "한국어 패치의 제목 및 표시용 글꼴에 사용. 원본 OFL 고지를 동봉합니다.",
           "SIL OFL 1.1",
           "https://github.com/sun-typeface/SUITE",
           "https://github.com/sun-typeface/SUITE/blob/main/LICENSE"),
    Credit("한글 글꼴", "Pretendard",
           "길형진 및 Pretendard 기여자",
           "NFSKR 파생 UI 글꼴 제작에 사용. 관련 OFL 고지를 동봉합니다.",
           "SIL OFL 1.1",
           "https://github.com/orioncactus/pretendard",
           "https://github.com/orioncactus/pretendard/blob/main/LICENSE"),
    Credit("프로그램·라이브러리", "CustomTkinter",
           "Tom Schimansky 및 기여자",
           "패처의 다크 테마 및 인터페이스 구성.",
           "MIT",
           "https://github.com/TomSchimansky/CustomTkinter",
           "https://github.com/TomSchimansky/CustomTkinter/blob/master/LICENSE"),
    Credit("프로그램·라이브러리", "Pillow",
           "Pillow 기여자",
           "패처의 로고 및 이미지 처리.",
           "MIT-CMU",
           "https://github.com/python-pillow/Pillow",
           "https://github.com/python-pillow/Pillow/blob/main/LICENSE"),
    Credit("프로그램·라이브러리", "fontTools",
           "Just van Rossum 및 기여자",
           "글꼴 생성·변환·검증.",
           "MIT",
           "https://github.com/fonttools/fonttools",
           "https://github.com/fonttools/fonttools/blob/main/LICENSE"),
    Credit("프로그램·라이브러리", "python-lz4",
           "python-lz4 및 LZ4 기여자",
           "Frostbite 리소스 압축·해제.",
           "BSD-3-Clause (바인딩) / BSD-2-Clause (LZ4)",
           "https://github.com/python-lz4/python-lz4",
           "https://github.com/python-lz4/python-lz4/blob/master/LICENSE"),
    Credit("프로그램·라이브러리", "Python / Tkinter",
           "Python Software Foundation 및 기여자",
           "프로그램 실행 환경과 기본 GUI 구성요소.",
           "PSF License 및 관련 고지",
           "https://www.python.org/",
           "https://docs.python.org/3/license.html"),
    Credit("프로그램·라이브러리", "PyInstaller",
           "PyInstaller 개발자 및 기여자",
           "배포용 단일 EXE 빌드에 사용.",
           "GPL 2.0 + 부트로더 예외 (일부 Apache 2.0)",
           "https://pyinstaller.org/",
           "https://pyinstaller.org/en/stable/license.html"),
    Credit("이미지·브랜드", "GitHub Mark",
           "GitHub",
           "상단에 사용된 공식 GitHub 파비콘 기반 마크. 클릭하면 프로젝트 저장소로 연결됩니다.",
           "GitHub 상표 및 로고 이용 지침",
           "https://github.githubassets.com/favicons/favicon.png",
           "https://brand.github.com/foundations/logo"),
)


_BG = "#0B101B"
_PANEL = "#121A2A"
_PANEL2 = "#172136"
_TEXT = "#F3F6FD"
_MUTED = "#99A8C0"
_BLUE = "#53A9FF"


def _open_link(owner, url: str) -> None:
    """Open only fixed HTTPS publisher links; fall back to clipboard."""
    if not url.startswith("https://"):
        return
    try:
        if webbrowser.open(url, new=2):
            return
    except Exception:
        pass
    try:
        owner.clipboard_clear()
        owner.clipboard_append(url)
        owner.update_idletasks()
        messagebox.showinfo("링크 복사됨",
                            "브라우저를 자동으로 열지 못해 링크를 클립보드에 복사했습니다.",
                            parent=owner)
    except Exception:
        messagebox.showwarning("링크 열기",
                               "브라우저에서 다음 링크를 직접 열어 주세요.\n" + url,
                               parent=owner)


def show_credits(owner) -> None:
    """Open or focus a reusable, scrollable, independently closable window."""
    old = getattr(owner, "_credits_window", None)
    try:
        if old is not None and old.winfo_exists():
            old.lift()
            old.focus_force()
            return
    except Exception:
        pass

    dialog = ctk.CTkToplevel(owner, fg_color=_BG)
    owner._credits_window = dialog
    dialog.title("NFSKR | 크레딧 · 출처")
    dialog.geometry("720x590")
    dialog.minsize(630, 450)
    dialog.transient(owner)

    def close() -> None:
        owner._credits_window = None
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Escape>", lambda _event: close())

    heading = ctk.CTkFrame(dialog, fg_color="transparent")
    heading.pack(fill="x", padx=23, pady=(18, 8))
    ctk.CTkLabel(heading, text="크레딧 · 출처",
                 font=ctk.CTkFont(family="Malgun Gothic", size=20, weight="bold"),
                 text_color=_TEXT).pack(anchor="w")
    ctk.CTkLabel(heading,
                 text="NFSKR의 제작에 사용된 글꼴·도구와 원저작자의 공식 페이지입니다.",
                 font=ctk.CTkFont(family="Malgun Gothic", size=11),
                 text_color=_MUTED).pack(anchor="w", pady=(4, 0))

    body = ctk.CTkScrollableFrame(dialog, fg_color="transparent",
                                  scrollbar_button_color="#3D516E",
                                  scrollbar_button_hover_color="#537296")
    body.pack(fill="both", expand=True, padx=16, pady=(3, 8))

    current_group = None
    for item in CREDITS:
        if item.group != current_group:
            current_group = item.group
            ctk.CTkLabel(body, text=current_group,
                         font=ctk.CTkFont(family="Malgun Gothic", size=13,
                                          weight="bold"),
                         text_color=_BLUE).pack(anchor="w", padx=8, pady=(14, 5))
        card = ctk.CTkFrame(body, fg_color=_PANEL, corner_radius=12)
        card.pack(fill="x", padx=5, pady=4)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=item.title, anchor="w",
                     font=ctk.CTkFont(family="Malgun Gothic", size=13,
                                      weight="bold"),
                     text_color=_TEXT).grid(row=0, column=0, sticky="ew",
                                            padx=(13, 6), pady=(10, 0))
        ctk.CTkLabel(card, text=item.author + "  ·  " + item.license,
                     anchor="w", font=ctk.CTkFont(family="Malgun Gothic", size=10),
                     text_color=_MUTED).grid(row=1, column=0, sticky="ew",
                                              padx=(13, 6), pady=(0, 1))
        ctk.CTkLabel(card, text=item.purpose, anchor="w",
                     font=ctk.CTkFont(family="Malgun Gothic", size=10),
                     text_color=_MUTED, wraplength=455, justify="left").grid(
                         row=2, column=0, sticky="ew", padx=(13, 6), pady=(0, 10))
        links = ctk.CTkFrame(card, fg_color="transparent")
        links.grid(row=0, column=1, rowspan=3, sticky="e", padx=(3, 12))
        ctk.CTkButton(links, text="원본 ↗", width=90, height=27,
                      font=ctk.CTkFont(family="Malgun Gothic", size=11),
                      fg_color="#253952", hover_color="#345779",
                      command=lambda url=item.source: _open_link(dialog, url)
                      ).pack(pady=(0, 5))
        ctk.CTkButton(links, text="라이선스 ↗", width=90, height=27,
                      font=ctk.CTkFont(family="Malgun Gothic", size=11),
                      fg_color=_PANEL2, hover_color="#345779",
                      command=lambda url=item.license_url: _open_link(dialog, url)
                      ).pack()

    footer = ctk.CTkFrame(dialog, fg_color="transparent")
    footer.pack(fill="x", padx=23, pady=(0, 14))
    ctk.CTkLabel(footer,
                 text="비공식 팬 제작 패치입니다. 각 프로젝트의 저작권은 원저작자에게 있습니다.",
                 font=ctk.CTkFont(family="Malgun Gothic", size=10),
                 text_color=_MUTED).pack(side="left")
    ctk.CTkButton(footer, text="닫기", width=72, height=30,
                  fg_color="#263248", hover_color="#36465F",
                  command=close).pack(side="right")
    dialog.after(70, lambda: (dialog.lift(), dialog.focus_force()))
