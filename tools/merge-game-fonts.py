#!/usr/bin/env python3
"""Build local-only composite fonts: untouched NFS 2015 DIN Latin + licensed Korean glyphs.

WARNING: The outputs incorporate proprietary DIN glyphs extracted from the user's
own installed game. NEVER commit, upload or distribute these generated font files
or any .fbmod embedding them. Distribute the script to regenerate locally instead.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from fontTools import subset
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "work/locale-extract/font-files"
DERIVED = ROOT / ".external/fonts/derived"
VENDOR = ROOT / ".external/fonts/vendor"
OUTPUT = ROOT / "work/poc/hybrid-fonts"
DEFAULT_TRANSLATIONS = ROOT / "work/poc/mainmenu-v2-strings.json"

SOURCES = (
    ("cond", "ui_fonts_dinoffcpro-cond.bin", DERIVED / "NFSKR-UI-Text-SemiBold.ttf"),
    ("condmedi", "ui_fonts_dinoffcpro-condmedi.bin", VENDOR / "SUIT-Medium.ttf"),
    ("condbold", "ui_fonts_dinoffcpro-condbold.bin", VENDOR / "SUITE-Heavy.ttf"),
)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as inp:
        for block in iter(lambda: inp.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def latin_signature(font: TTFont, cp: int):
    cmap = font.getBestCmap() or {}
    name = cmap[cp]
    glyph_set = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return font["hmtx"][name], pen.value

def validate_base_latin(orig: TTFont, hybrid: TTFont, label: str) -> int:
    cmap = orig.getBestCmap() or {}
    merged_map = hybrid.getBestCmap() or {}
    # All original Unicode glyphs, including English, numbers and punctuation,
    # must keep exactly the same geometry, advances and side bearings.
    to_validate = sorted(cmap)
    missing = set(to_validate) - set(merged_map)
    if missing:
        raise ValueError(f"{label}: lost {len(missing)} original Latin characters")
    problems = []
    for cp in to_validate:
        if latin_signature(orig, cp) != latin_signature(hybrid, cp):
            problems.append(f"U+{cp:04X}")
    if problems:
        raise ValueError(f"{label}: Latin glyph/metrics modified: {problems[:15]}")
    if orig["head"].unitsPerEm != hybrid["head"].unitsPerEm:
        raise ValueError(f"{label}: original font unitsPerEm changed")
    # Original kerning/layout/hinting binary tables must remain byte-for-byte.
    for name in ("kern", "GSUB", "GPOS", "GDEF", "fpgm", "prep", "cvt "):
        if name in orig:
            if name not in hybrid or orig.getTableData(name) != hybrid.getTableData(name):
                raise ValueError(f"{label}: original font table changed: {name}")
    return len(to_validate)

def get_required_codepoints(path: Path, full_hangul: bool):
    document = json.loads(path.read_text(encoding="utf-8"))
    chars = {ord(c) for e in document["entries"] for c in e["ko"]}
    if full_hangul:
        chars.update(range(0xAC00, 0xD7A4))
        chars.update(range(0x3130, 0x3190))
        chars.update(range(0x1100, 0x1200))
    return chars

def build_one(label: str, base_path: Path, donor_path: Path, wanted: set[int],
              target: Path, tempdir: Path) -> dict:
    with TTFont(str(base_path)) as baseline, TTFont(str(donor_path)) as original_donor:
        original_map = baseline.getBestCmap() or {}
        donor_map = original_donor.getBestCmap() or {}
        needed = {cp for cp in wanted if cp not in original_map}
        missing = needed - set(donor_map)
        if missing:
            print(f"NOTE {label}: donor lacks {len(missing)} characters: " +
                  " ".join(f"U+{cp:04X}" for cp in sorted(missing)[:12]))
        needed &= set(donor_map)
        print(f"SUBSETTING {label}: {len(needed)} added codepoints", flush=True)
        if not needed:
            raise ValueError(f"{label}: there are no Korean glyphs to add")
        options = subset.Options()
        options.layout_features = []  # Korean precomposed syllables don't need extra GSUB.
        options.hinting = False
        options.recalc_bounds = True
        options.recalc_timestamp = False
        sub = subset.Subsetter(options=options)
        sub.populate(unicodes=needed)
        sub.subset(original_donor)
        if original_donor['head'].unitsPerEm != baseline['head'].unitsPerEm:
            scale_upem(original_donor, baseline['head'].unitsPerEm)
        temp_path = tempdir / f"donor-{label}-korean-only.ttf"
        original_donor.save(str(temp_path))

    # Graft only missing Korean glyphs into original DIN, leaving all original
    # font tables, Latin glyph outlines, kern, GPOS and GSUB intact.
    # Generic fontTools Merger is not suitable: it silently drops the old 'kern'
    # table in the NFS DIN fonts and may rename existing composite glyphs.
    with TTFont(str(base_path)) as base, TTFont(str(temp_path)) as donor:
        original_cmap = dict(base.getBestCmap() or {})
        donor_cmap = donor.getBestCmap() or {}
        donor_order = [n for n in donor.getGlyphOrder() if n != ".notdef"]
        existing = set(base.getGlyphOrder())
        rename_map = {}
        for original in donor_order:
            new_name = "nfsKR_" + original
            suffix = 1
            while new_name in existing:
                new_name = "nfsKR_" + original + "_" + str(suffix)
                suffix += 1
            rename_map[original] = new_name
            existing.add(new_name)
        for original in donor_order:
            renamed = rename_map[original]
            glyf = copy.deepcopy(donor["glyf"][original])
            if glyf.isComposite():
                for component in glyf.components:
                    if component.glyphName in rename_map:
                        component.glyphName = rename_map[component.glyphName]
            base["glyf"].glyphs[renamed] = glyf
            base["hmtx"].metrics[renamed] = donor["hmtx"].metrics[original]
        new_order = list(base.getGlyphOrder()) + [rename_map[n] for n in donor_order]
        base.setGlyphOrder(new_order)
        base["maxp"].numGlyphs = len(new_order)
        base["hhea"].numberOfHMetrics = len(new_order)
        count_cmap = 0
        for table in base["cmap"].tables:
            if table.isUnicode() and table.format in (4, 12):
                for cp in sorted(needed):
                    if cp not in original_cmap and cp in donor_cmap:
                        table.cmap[cp] = rename_map[donor_cmap[cp]]
                        count_cmap += 1
        if not count_cmap:
            raise ValueError(f"{label}: no usable Unicode cmap subtable")
        base.recalcBBoxes = True
        base.recalcTimestamp = False
        base.save(str(target))
    with TTFont(str(base_path)) as orig, TTFont(str(target)) as merged:
        original_count = validate_base_latin(orig, merged, label)
        merged_map = merged.getBestCmap() or {}
        absent = needed - set(merged_map)
        if absent:
            raise ValueError(f"{label}: {len(absent)} Korean glyphs not merged")
        families = (orig["name"].getDebugName(1), merged["name"].getDebugName(1))
        print("HYBRID_READY", label, "DIN_LATIN_UNCHANGED", original_count,
              "KOREAN_GLYPHS", len(needed), "FAMILY", families, flush=True)

    return {
        "base": str(base_path),
        "donor": str(donor_path),
        "output": str(target),
        "font_hash": digest(target),
        "base_hash": digest(base_path),
        "donor_hash": digest(donor_path),
        "korean_codepoints": len(needed),
        "latin_checked": original_count,
        "base_family": families[0],
        "output_family": families[1],
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation", type=Path, default=DEFAULT_TRANSLATIONS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--full-hangul", action="store_true",
                        help="Use all Hangul syllables instead of just translated text")
    args = parser.parse_args()

    if not args.translation.is_file():
        raise FileNotFoundError(f"Translation file missing: {args.translation}")
    wanted = get_required_codepoints(args.translation, args.full_hangul)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with tempfile.TemporaryDirectory(dir=str(args.output)) as scratch:
        tmp = Path(scratch)
        for label, original_name, donor in SOURCES:
            base = ORIGINAL / original_name
            if not base.exists() or not donor.exists():
                raise FileNotFoundError(f"Required font missing: {base} or {donor}")
            output = args.output / f"nfs16-din-{label}-ko-local.ttf"
            manifest[label] = build_one(label, base, donor, wanted, output, tmp)
    (args.output / "hybrid-font-manifest.json").write_text(
        json.dumps({"private_local_only": True, "fonts": manifest}, indent=2),
        encoding="utf-8"
    )
    print("ALL_HYBRID_FONTS_READY", len(manifest), flush=True)

if __name__ == "__main__":
    main()
