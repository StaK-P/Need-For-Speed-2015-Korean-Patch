#!/usr/bin/env python3
"""NFS 2015 Korean patch: deterministic three-way *text* merge engine.

This is a release-side building block, not a complete FBMod binary merger.
Inputs are per-string decoded tables from the installed game, the other
enabled mods (resolved in Frosty load order), and the Korean translation.
The caller must resolve EBX/chunk/font conflicts and write a valid FBMod.

Fail closed on unsupported changes and preserve source mods byte-for-byte.
Only Python standard-library dependencies; portable packager candidate.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import re
import unicodedata
from pathlib import Path
from typing import Mapping

FORMAT = re.compile(r"\{(?:\d+|[A-Za-z_][A-Za-z_0-9]*)(?::[^{}\r\n]+)?\}|<[^<>\r\n]+>|%(?:\d+\$)?[-+#0]*(?:\d+)?(?:\.\d+)?[sduifxXeEgG]")
TIMER = re.compile(r"\{\d+(?:\.\d+)?-\d+(?:\.\d+)?\}")
SAFE_COSMETIC = re.compile(r"[\s\.,\?!;:'\"“”‘’…\u2013\u2014\-\u00a0]")
EMBEDDED_ICON = re.compile(r"[\ue000-\uf8ff]")
@dataclass(frozen=True)
class MergeItem:
    sid: str
    base: str | None
    external: str | None
    korean: str | None
    result: str | None
    decision: str
    needs_translation: bool = False

def normalized_cosmetic(text: str) -> str:
    return SAFE_COSMETIC.sub("", text).casefold()

def _cosmetic_canonical(text: str, drop_symbols: bool = False) -> str:
    """Normalized English text after safe typography and UI icon corrections.

    This is NOT machine translation. Brand trademarks, diacritics, case,
    whitespace and REP icon substitutions should not discard a confirmed
    Korean translation, even if a third-party mod loses those glyphs.
    """
    text = text.replace("™", "").replace("®", "").replace("©", "")
    text = (text.replace("ø", "o").replace("Ø", "O")
                .replace("æ", "ae").replace("Æ", "AE")
                .replace("ł", "l").replace("Ł", "L").replace("ß","ss"))
    text = "".join(c for c in unicodedata.normalize("NFKD", text)
                   if unicodedata.category(c) != "Mn")
    if drop_symbols:
        text = re.sub(r"[\ue000-\uf8ff]", "", text)
        text = re.sub(r"\bREP\b", "", text, flags=re.I)
    else:
        text = re.sub(r"[\ue000-\uf8ff]", "REP", text)
    return normalized_cosmetic(text)


def _cosmetic_equivalent(base: str, mod: str) -> bool:
    if _cosmetic_canonical(base) == _cosmetic_canonical(mod):
        return True
    if EMBEDDED_ICON.search(base) or EMBEDDED_ICON.search(mod):
        # A third-party mod may strip proprietary REP glyphs, converting
        # them to 'REP', '?', or empty. Preserve the verified Korean icon.
        return _cosmetic_canonical(base,True) == _cosmetic_canonical(mod,True)
    return False


def preserves_markup(base: str, candidate: str) -> bool:
    # Preserve game control/timing/formatting tokens; class and count both matter.
    return (
        sorted(FORMAT.findall(base)) == sorted(FORMAT.findall(candidate))
        and TIMER.findall(base) == TIMER.findall(candidate)
        and EMBEDDED_ICON.findall(base) == EMBEDDED_ICON.findall(candidate)
        and base.count("\r") == candidate.count("\r")
    )

def merge_localization(
    base: Mapping[str, str],
    external: Mapping[str, str],
    korean: Mapping[str, str],
    reviewed: Mapping[str, str] | None = None,
    *, base_deleted_ids: set[str] | None = None
) -> tuple[dict[str, str], list[MergeItem]]:
    """Merge V=game, M=other mods, K=Korean using three-way provenance.

    Priority:
      1) Reviewed exact IDs for modded strings, only when the mod changed them.
      2) Korean when external text unchanged or only safe punctuation changed.
      3) Other mod when Korean is unchanged or mod changed semantic content.
    Semantic conflicts intentionally remain in the other mod's language,
    rather than silently changing game mechanics labels to the wrong meaning.
    Unknown format IDs or missing original IDs stop the merge.
    """
    base_deleted_ids = base_deleted_ids or set()
    reviewed = reviewed or {}
    if not base:
        raise ValueError("No original localization table supplied")
    # New IDs added by external mods are legitimate. Preserve them unchanged
    # unless an explicitly reviewed translation is supplied for that new ID.
    if set(korean) - set(base):
        raise ValueError("Korean patch references unknown original IDs")
    if set(reviewed) - (set(base)|set(external)):
        raise ValueError("Reviewed rules reference absent original/external IDs")
    if set(base_deleted_ids) - set(base):
        raise ValueError("Invalid removed IDs")
    result: dict[str,str] = {}
    items: list[MergeItem] = []
    for sid in sorted(set(base)|set(external), key=lambda s:int(s,16)):
        v=base.get(sid)
        if v is None:
            mod_new=external[sid]
            localized=reviewed.get(sid,mod_new)
            if not isinstance(localized,str) or "\x00" in localized:
                raise ValueError("Invalid external-added localized string "+sid)
            result[sid]=localized
            items.append(MergeItem(sid,None,mod_new,korean.get(sid),localized,
                "external_new_id_translated" if sid in reviewed else "external_new_id"))
            continue
        if sid in base_deleted_ids:
            # Must be explicit, not a silent new KO entry resurrecting deleted content
            items.append(MergeItem(sid,v,None,korean.get(sid),None,"removed_by_external"))
            continue
        m=external.get(sid,v)
        k=korean.get(sid,v)
        rule=reviewed.get(sid)
        if not all(isinstance(s,str) for s in (v,m,k)):
            raise ValueError("Invalid localized text for "+sid)
        if rule is not None:
            if not isinstance(rule,str) or not rule or m==v:
                raise ValueError("Stale/invalid reviewed rule for "+sid)
            if not preserves_markup(m,rule):
                raise ValueError("Reviewed translation alters game placeholders for "+sid)
            choice,why,needs=rule,"reviewed_mod_translation",False
        elif m==v:
            choice,why,needs=k,"korean",False
        elif k==v:
            choice,why,needs=m,"external_only",False
        elif k==m:
            choice,why,needs=k,"same_change",False
        elif _cosmetic_equivalent(v,m):
            choice,why,needs=k,"safe_typography_or_icon_normalization",False
        else:
            choice,why,needs=m,"unresolved_semantic_collision",True
        # The shipped game contains legitimate empty records; keep those intact.
        if (choice == "" and v != "" and m != "") or "\x00" in choice or any(ord(c)>0xffff for c in choice):
            raise ValueError("Invalid output string "+sid)
        result[sid]=choice
        if m!=v or k!=v:
            items.append(MergeItem(sid,v,m,k,choice,why,needs))
    return result,items

def report(items: list[MergeItem]) -> dict:
    from collections import Counter
    decision=Counter(item.decision for item in items)
    manual=[{"id":x.sid,"base":x.base,"external":x.external,"prior_ko":x.korean}
            for x in items if x.needs_translation]
    return {
        "status":"automatically_resolved_with_source_text_fallbacks",
        "decision_counts":dict(decision),
        "manual_review_count":len(manual),
        "manual_review":manual,
        "warnings":["This cannot merge EBX or binary assets without Frosty packaging integration.",
                    "Other mods and their modifications must remain intact.",
                    "A semantic collision is intentionally not auto-translated."],
    }

def dump_report(path: Path, items: list[MergeItem]) -> None:
    path.write_text(json.dumps(report(items),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    raise SystemExit("Library module: integrate with NFSKR mod-merger launcher, not standalone.")
