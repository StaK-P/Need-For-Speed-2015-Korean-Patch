#!/usr/bin/env python3
"""Rebuild EXE and UI icon assets from the user's approved transparent logo."""
from pathlib import Path
from PIL import Image
import hashlib

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/"tools/assets/nfskr-approved-logo.webp"
EXPECTED="2f5f00d38446a1a771047346ae50c7d1937eecc73d2f888918516f7a0a50fa64"
if not SOURCE.is_file() or hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=EXPECTED:
    raise ValueError("Approved NFSKR icon artwork is missing or changed")
with Image.open(SOURCE) as opened:
    original=opened.convert("RGBA")
if original.size!=(128,128) or original.getpixel((0,0))[3]!=0:
    raise ValueError("Approved logo must be 128x128 with transparent outer canvas")
work=ROOT/"work/installer-build"
work.mkdir(parents=True,exist_ok=True)
png=work/"nfskr-logo.png"
ico=work/"nfskr.ico"
original.resize((512,512),Image.Resampling.LANCZOS).save(png,format="PNG",optimize=True)
original.resize((256,256),Image.Resampling.LANCZOS).save(
    ico,format="ICO",
    sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
with Image.open(ico) as result:
    sizes=result.ico.sizes()
    if (16,16) not in sizes or (48,48) not in sizes or (256,256) not in sizes:
        raise ValueError("Missing required Windows icon resolutions")
    if result.ico.getimage((256,256)).getpixel((0,0))[3]!=0:
        raise ValueError("PNG transparency was not preserved in ICO")
print("NFSKR_APPROVED_BRANDING_BUILT",str(ico),str(png),
      "SOURCE_SHA256",EXPECTED,"SIZES",sorted(sizes))
