"""Regression: every NFSKR background subprocess is truly console-hidden.

No installed game or Frosty state is changed.
"""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import subprocess
import time

ROOT=Path(__file__).resolve().parent.parent
FILES=(
    "nfskr_bootstrap.py","nfskr_discovery.py","nfskr_local_assets.py",
    "nfskr_composite.py","verify_nfskr_composite.py",
    "nfskr_installer_core.py","nfskr_shortcuts.py",
)
calls=[]
for name in FILES:
    f=ROOT/"tools"/name
    tree=ast.parse(f.read_text(encoding="utf8"),filename=str(f))
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        callee=node.func
        if not (isinstance(callee,ast.Attribute) and
                isinstance(callee.value,ast.Name) and callee.value.id=="subprocess"
                and callee.attr=="run"):
            continue
        kwargs={x.arg for x in node.keywords}
        if "creationflags" not in kwargs:
            raise AssertionError(f"Installer call without hidden Windows flags: {name}:{node.lineno}")
        calls.append((name,node.lineno))
assert len(calls)>=9,("Unexpected missing subprocess calls",calls)
# Frosty manager Popen is an explicitly requested GUI launch, not background work.
print("NFSKR_ALL_INSTALLER_SUBPROCESSES_HIDDEN",len(calls),calls)

kernel=ctypes.windll.user32
EnumCb=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
count=[]
def enum_window(hwnd,param):
    if kernel.IsWindowVisible(hwnd):
        pid=wintypes.DWORD()
        kernel.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==proc.pid:
            title=ctypes.create_unicode_buffer(256)
            kernel.GetWindowTextW(hwnd,title,256)
            count.append(title.value)
    return True

flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
assert flags==0x08000000,"CREATE_NO_WINDOW unsupported"
proc=subprocess.Popen(["cmd.exe","/D","/C","ping -n 4 127.0.0.1 >nul"],
                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                      creationflags=flags)
try:
    time.sleep(.8)
    kernel.EnumWindows(EnumCb(enum_window),0)
    assert not count,("Console window was visible for hidden child",count)
    out,err=proc.communicate(timeout=15)
    assert proc.returncode==0,(proc.returncode,err)
finally:
    if proc.poll() is None:proc.terminate()
print("NFSKR_BACKGROUND_CMD_WINDOWLESS_PASS",len(calls),"calls",
      "child_pid",proc.pid,flush=True)
