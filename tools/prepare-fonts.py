#!/usr/bin/env python3
"""Create fixed-weight Korean UI fonts for NFS 2015 (local workspace only).

Derived Pretendard files are renamed because SIL OFL reserves the original family name.
Game-owned font data is never read or included by this script.
"""
import hashlib
import json
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / ".external" / "fonts" / "vendor"
OUTPUT = ROOT / ".external" / "fonts" / "derived"
STATIC_WEIGHTS = (("Medium", 500), ("SemiBold", 600), ("Bold", 700))

def font_sha(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            hasher.update(block)
    return hasher.hexdigest()

def set_renamed_family(font: TTFont, weight_name: str, weight: int) -> None:
    names = font["name"]
    family = "NFSKR UI Text"
    full = family + " " + weight_name
    ps = "NFSKRUIText-" + weight_name
    # Renamed derivatives do not retain Pretendard's reserved family name.
    for platform, encoding, lang in ((3, 1, 0x409), (1, 0, 0)):
        for key, value in (
            (1, family), (2, weight_name), (4, full),
            (6, ps), (16, family), (17, weight_name),
        ):
            names.setName(value, key, platform, encoding, lang)
    font["OS/2"].usWeightClass = weight

def count_hangul(font: TTFont) -> int:
    return sum(0xAC00 <= char <= 0xD7A3 for char in (font.getBestCmap() or {}))

def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = VENDOR / "PretendardVariable.ttf"
    if not source.is_file():
        raise SystemExit("Missing vendor font. Run tools/fetch-fonts.ps1 first.")
    summary = []
    for label, weight in STATIC_WEIGHTS:
        print("INSTANTIATING", label, flush=True)
        variable_font = TTFont(str(source))
        font = instantiateVariableFont(variable_font, {"wght": weight}, inplace=False, updateFontNames=True)
        if "fvar" in font:
            raise ValueError("Expected non-variable font, fvar remains")
        set_renamed_family(font, label, weight)
        target = OUTPUT / ("NFSKR-UI-Text-" + label + ".ttf")
        font.save(str(target))
        font.close()
        variable_font.close()
        with TTFont(str(target)) as check:
            hangul = count_hangul(check)
            if hangul != 11172:
                raise ValueError(f"Incomplete Hangul repertoire ({hangul}) in {target}")
            if "fvar" in check:
                raise ValueError(f"File is still variable: {target}")
        details = {"name": target.name, "weight": weight, "hangul_syllables": hangul,
                   "size_bytes": target.stat().st_size, "sha256": font_sha(target),
                   "family": "NFSKR UI Text", "source": "PretendardVariable.ttf"}
        summary.append(details)
        print("PREPARED", target.name, "Hangul=", hangul, "size=", details["size_bytes"], flush=True)
    (OUTPUT / "derived-manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("DERIVED_FONTS_READY", len(summary))

if __name__ == "__main__":
    main()
