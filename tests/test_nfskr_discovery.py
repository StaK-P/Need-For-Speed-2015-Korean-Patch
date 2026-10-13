import json,time
from pathlib import Path
from nfskr_discovery import discover,source_pack,safe_frosty_profile_name,symlink_preflight
from nfskr_installer_core import snapshot
a=time.monotonic();got=discover(journal_dir=Path.home()/"AppData/Local/NFSKR/work/merge-tests/setup-gui")
print("DISCOVERY",json.dumps({
"manager":str(got.manager),"game":str(got.game),"source_pack":got.source_pack,
"current_pack":got.current_pack,"active":got.mods_enabled,
"disabled":got.mods_disabled,"elapsed":round(time.monotonic()-a,2)},ensure_ascii=True))
assert got.manager and got.game and got.source_pack=="Default"
assert (got.game/"NFS16.exe").is_file()
assert snapshot(got.config,got.manager,got.source_pack).selected_pack=="Default"
print("SAFE_NAME",safe_frosty_profile_name({"한글패치":"a","NFSKR":"b"}))
print("SYMLINK_PREFLIGHT",symlink_preflight(got.game))
