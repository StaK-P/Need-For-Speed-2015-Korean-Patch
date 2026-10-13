#!/usr/bin/env python3
"""Private QA-only punctuation font harmonization for NFS16 Korean text.

Merge-game-fonts.py originally preserves ALL English DIN glyphs. This explicitly
approved visual-QA variant changes only typographic punctuation in the generated
PRIVATE font, using the respective Korean donor; all letters, numbers, remaining
DIN glyphs and original game resources remain unchanged. No source fonts shared.
"""
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from collections import Counter
import argparse,copy,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent.parent
DERIVED=ROOT/".external/fonts/derived/NFSKR-UI-Text-SemiBold.ttf"
VENDOR=ROOT/".external/fonts/vendor"
SOURCES=(
 ("cond",ROOT/"work/locale-extract/font-files/ui_fonts_dinoffcpro-cond.bin",DERIVED),
 ("condmedi",ROOT/"work/locale-extract/font-files/ui_fonts_dinoffcpro-condmedi.bin",VENDOR/"SUIT-Medium.ttf"),
 ("condbold",ROOT/"work/locale-extract/font-files/ui_fonts_dinoffcpro-condbold.bin",VENDOR/"SUITE-Heavy.ttf"),
)
# Common spoken Korean punctuation. Do not include '<', '>', '{', '}' or controller icons.
PUNCTUATION=(0x0022,0x0027,0x002C,0x002D,0x002E,0x003A,0x003B,
             0x0021,0x003F,0x2013,0x2014,0x2018,0x2019,0x201C,0x201D,0x2026)
UNTOUCHED_LAYOUT=("kern","GSUB","GPOS","GDEF","fpgm","prep","cvt ")
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def signature(ttf,cp):
 cmap=ttf.getBestCmap()
 glyph=cmap[cp]
 pen=DecomposingRecordingPen(ttf.getGlyphSet())
 ttf.getGlyphSet()[glyph].draw(pen)
 return ttf["hmtx"][glyph],pen.value
def validate(original,modified,changes,name):
 o=original.getBestCmap() or {}
 n=modified.getBestCmap() or {}
 for cp in o:
  if cp not in changes and n.get(cp)!=o[cp]:
   raise ValueError("Original non-punctuation mapping lost "+name+" "+hex(cp))
 for cp in o:
  if cp not in changes and signature(original,cp)!=signature(modified,cp):
   raise ValueError("Unauthorized original outline or metrics edit "+name+" "+hex(cp))
 for tag in UNTOUCHED_LAYOUT:
  if tag in original and (tag not in modified or original.getTableData(tag)!=modified.getTableData(tag)):
   raise ValueError("Original layout/hinting table changed "+name+" "+tag)
 assert original.getGlyphOrder()==modified.getGlyphOrder()[:len(original.getGlyphOrder())],name
 assert len(set(changes)&set(o))>=10,name
 assert all(cp in n for cp in range(0xAC00,0xD7A4) if cp in (modified.getBestCmap() or {})),name
 return sum(1 for cp in o if cp not in changes)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--base-dir",type=Path,required=True)
 ap.add_argument("--output",type=Path,required=True)
 args=ap.parse_args()
 args.output.mkdir(parents=True,exist_ok=True)
 if args.base_dir.resolve()==args.output.resolve():raise ValueError("Base fonts must stay untouched")
 report={}
 for label,original_path,donor_path in SOURCES:
  source=args.base_dir/f"nfs16-din-{label}-ko-local.ttf"
  out=args.output/source.name
  if not source.is_file() or out.exists():
   raise FileExistsError("Missing base or existing output: "+str(source)+" / "+str(out))
  with TTFont(str(source)) as result, TTFont(str(original_path)) as original, TTFont(str(donor_path)) as donor:
   assert result["head"].unitsPerEm==original["head"].unitsPerEm
   if donor["head"].unitsPerEm!=result["head"].unitsPerEm:
    scale_upem(donor,result["head"].unitsPerEm)
   with TTFont(str(DERIVED)) as other:
    if other["head"].unitsPerEm!=result["head"].unitsPerEm:
     scale_upem(other,result["head"].unitsPerEm)
    cmap=result.getBestCmap() or {}
    dmap=donor.getBestCmap() or {}
    fmap=other.getBestCmap() or {}
    edits={}
    append_glyphs=[]
    for cp in PUNCTUATION:
     if cp not in cmap:continue
     src=donor if cp in dmap else other
     source_name=(src.getBestCmap() or {})[cp]
     old_name=cmap[cp]
     glyf=copy.deepcopy(src["glyf"][source_name])
     if glyf.isComposite():
      # A donor quotation mark may reference donor-only glyph names.
      # Flatten its components into simple TrueType contours first.
      recording=DecomposingRecordingPen(src.getGlyphSet())
      src.getGlyphSet()[source_name].draw(recording)
      pen=TTGlyphPen(None)
      recording.replay(pen)
      glyf=pen.glyph()
      assert not glyf.isComposite(),("Punctuation flatten failed",label,cp)
     # Do not overwrite old_name: non-target Unicode may share it
     # (e.g. U+00AD soft-hyphen shares the hyphen outline).
     new_name=f"nfsKR_PUNC_{cp:04X}"
     if new_name in result["glyf"].glyphs:
      raise ValueError("Duplicate QA punctuation glyph "+new_name)
     result["glyf"].glyphs[new_name]=glyf
     result["hmtx"].metrics[new_name]=src["hmtx"].metrics[source_name]
     append_glyphs.append(new_name)
     for table in result["cmap"].tables:
      if table.isUnicode() and table.format in (4,12) and cp in table.cmap:
       table.cmap[cp]=new_name
     edits[cp]={"codepoint":f"U+{cp:04X}","name":new_name,"donor":donor_path.name if src is donor else DERIVED.name}
    order=list(result.getGlyphOrder())+append_glyphs
    result.setGlyphOrder(order)
    result["maxp"].numGlyphs=len(order)
    result["hhea"].numberOfHMetrics=len(order)
    result.recalcBBoxes=True
    result.recalcTimestamp=False
    result.save(str(out))
  with TTFont(str(original_path)) as orig, TTFont(str(out)) as patched, TTFont(str(source)) as untouched:
   # The original glyph order must remain a strict prefix. New QA punctuation
   # glyphs are appended, not merged into a name used by other Unicode points.
   assert patched.getGlyphOrder()[:len(untouched.getGlyphOrder())]==untouched.getGlyphOrder()
   assert len(patched.getGlyphOrder())==len(untouched.getGlyphOrder())+len(edits)
   assert all(patched.getBestCmap().get(cp)==untouched.getBestCmap().get(cp)
     for cp in untouched.getBestCmap() if cp not in edits)
   for cp in patched.getBestCmap():
    if cp not in edits and signature(untouched,cp)!=signature(patched,cp):
     raise ValueError("Some non-punctuation glyph changed in "+label+" "+hex(cp))
   count=validate(orig,patched,set(edits),label)
   altered=sum(signature(untouched,cp)!=signature(patched,cp) for cp in edits)
   if altered<9:raise ValueError("Punctuation not sufficiently changed for "+label)
   report[label]={"base_sha256":digest(source),"patched_sha256":digest(out),
    "original_latin_except_punctuation_checked":count,
    "approved_punctuation_codepoints":[f"U+{cp:04X}" for cp in edits],
    "modified_punctuation_glyphs":altered,
    "fallback_donor_codepoints":[f"U+{cp:04X}" for cp,v in edits.items() if v["donor"]==DERIVED.name],
    "original_font_tables_unchanged":True}
 (args.output/"punctuation-QA-manifest.json").write_text(
  json.dumps({"private_only":True,"DIN_punctuation_unicode_mappings_intentionally_overridden_for_QA":True,
    "original_alpha_numeric_shapes_preserved":True,"fonts":report},ensure_ascii=False,indent=2)+"\n",encoding="utf8")
 print("NFS2015_PUNCTUATION_QA_FONTS_READY",json.dumps(report,ensure_ascii=True))
if __name__=="__main__":main()
