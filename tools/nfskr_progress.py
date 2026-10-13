"""Milestone-driven NFSKR installer progress, no timers or fake animation.

Each percentage represents work already completed/verified, not elapsed time.
The UI is not allowed to show 100% before the final installation succeeds.
"""
from __future__ import annotations
from collections.abc import Callable


class MilestoneProgress:
    def __init__(self, callback:Callable[[int,str],None]|None=None):
        self.callback=callback
        self.percent=0
        self.history:list[tuple[int,str]]=[]
        if callback is not None:
            self.report(0,"설치를 준비하고 있습니다.")

    def report(self,value:int,message:str):
        if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=100:
            raise ValueError("진행률은 정수 0~100이어야 합니다.")
        if value<self.percent:
            raise ValueError("완료된 설치 단계의 진행률을 되돌릴 수 없습니다.")
        if not isinstance(message,str) or not message.strip():
            raise ValueError("진행 상태 설명이 필요합니다.")
        if value==self.percent and self.history and self.history[-1][1]==message:
            return
        self.percent=value
        self.history.append((value,message))
        if self.callback:
            self.callback(value,message)
