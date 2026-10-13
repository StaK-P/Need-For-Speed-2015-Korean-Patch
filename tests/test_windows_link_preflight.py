from pathlib import Path
import ctypes, tempfile, os, subprocess, json, winreg, shutil, traceback
folder=Path(r"D:\Games\EA\nfs-2015-korean-patch\work")
result={}
with tempfile.TemporaryDirectory(prefix="nfskr-symlink-preflight-",dir=folder) as path:
 p=Path(path)
 src=p/"source.cas";src.write_bytes(b"NFSKR_LINK_PREFLIGHT")
 dest=p/"created-link.cas"
 try:
  os.symlink(src,dest)
  result["python_symlink"]={"success":dest.is_symlink(),"reads":dest.read_bytes()==src.read_bytes()}
 except OSError as e:
  result["python_symlink"]={"success":False,"error":str(e),"winerror":e.winerror}
 dest.unlink(missing_ok=True)
 cmd=subprocess.run(["cmd.exe","/c",f'mklink "{dest}" "{src}"'],capture_output=True,text=True,encoding="cp949",errors="replace")
 result["mklink"]={"exit_code":cmd.returncode,"stdout":cmd.stdout.strip(),"stderr":cmd.stderr.strip(),"present":dest.is_symlink()}
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock") as k:
 try:result["developer_mode"]=winreg.QueryValueEx(k,"AllowDevelopmentWithoutDevLicense")[0]
 except OSError:result["developer_mode"]="not_set"
print(json.dumps(result,ensure_ascii=True,indent=2))
