from nfskr_discovery import _running_manager
print("PROC_FIND",_running_manager())
import ctypes
from ctypes import wintypes
psapi=ctypes.WinDLL("psapi",use_last_error=True)
buf=(wintypes.DWORD*4096)();l=wintypes.DWORD()
print("ENUM",psapi.EnumProcesses(ctypes.byref(buf),ctypes.sizeof(buf),ctypes.byref(l)),l.value)
try:
 import psutil
 print("PSUTIL",[(p.pid,p.exe()) for p in psutil.process_iter(['name']) if 'frostymodmanager' in (p.info.get('name') or '').lower()])
except Exception as e:print("PSUTIL ERROR",str(e))
