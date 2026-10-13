#!/usr/bin/env python3
"""Inspect locally extracted game fonts; never distribute their bytes with a patch."""
import argparse
import json
import pathlib
import sys

from fontTools.ttLib import TTFont


def count_range(cmap: set[int], first: int, last: int) -> int:
    return sum(first <= value <= last for value in cmap)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-dir", type=pathlib.Path,
                        default=root / "work" / "locale-extract" / "font-files")
    parser.add_argument("--report", type=pathlib.Path,
                        default=root / "work" / "locale-extract" / "font-coverage.json")
    args = parser.parse_args()
    result = []
    for path in sorted(args.font_dir.glob("*.bin")):
        try:
            with TTFont(path, lazy=True) as font:
                codepoints = set((font.getBestCmap() or {}).keys())
                name = font["name"].getDebugName(1) if "name" in font else None
                item = {
                    "file": path.name,
                    "font_family": name,
                    "size_bytes": path.stat().st_size,
                    "mapped_codepoints": len(codepoints),
                    "hangul_syllables": count_range(codepoints, 0xAC00, 0xD7A3),
                    "hangul_jamo": count_range(codepoints, 0x1100, 0x11FF),
                    "cjk_unified": count_range(codepoints, 0x4E00, 0x9FFF),
                    "hiragana": count_range(codepoints, 0x3040, 0x309F),
                    "katakana": count_range(codepoints, 0x30A0, 0x30FF),
                }
        except Exception as exc:
            item = {"file": path.name, "error": str(exc)}
        result.append(item)
        print(
            item["file"],
            "glyphs=" + str(item.get("mapped_codepoints", "-")),
            "Hangul=" + str(item.get("hangul_syllables", "-")),
            "Jamo=" + str(item.get("hangul_jamo", "-")),
            "CJK=" + str(item.get("cjk_unified", "-")),
            "family=" + str(item.get("font_family", "-")),
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if not result or any("error" in item for item in result):
        print("FONT_ANALYSIS_ERRORS", file=sys.stderr)
        return 1
    print("FONT_ANALYSIS_OK", len(result), "fonts", "report=" + str(args.report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
