#!/usr/bin/env python3
"""Read-only snapshot of real installed Frosty pack. Does NOT install anything."""
from pathlib import Path
import argparse
import json
from nfskr_installer_core import preview, snapshot

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANAGER = ROOT / ".external/frosty/modmanager-ko-1.0.6.3/FrostyModManager"
DEFAULT_CONFIG = Path.home() / "AppData/Local/Frosty/manager_config.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manager", type=Path, default=DEFAULT_MANAGER)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = ap.parse_args()
    plan = preview(snapshot(args.config,args.manager))
    print(json.dumps(plan,ensure_ascii=True,indent=2))
    print("PREFLIGHT_READ_ONLY_SUCCESS")
if __name__ == "__main__":
    main()
