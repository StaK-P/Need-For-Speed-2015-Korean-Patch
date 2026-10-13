#!/usr/bin/env python3
"""NFSKR Windows installer backend (safe, fail-closed release foundation).

The UI/executable calls this after the real resource merger has produced a
*validated composite* .fbmod representing the exact selected Frosty pack.
Never claims a .fbpack container itself merges resources. This module is
standard-library only, for auditability and reproducible single-file packaging.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import time
import zipfile


class InstallerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModInput:
    name: str
    file: Path
    sha256: str
    size: int
    enabled: bool


@dataclass(frozen=True)
class Snapshot:
    config_path: Path
    manager_dir: Path
    game_path: Path
    selected_pack: str
    source_pack_list: str
    order_setting: str
    config_sha256: str
    enabled_mods: tuple[ModInput, ...]
    disabled_mods: tuple[ModInput, ...]
    replaced_korean_mods: tuple[ModInput, ...]


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def valid_filename(value: str) -> bool:
    return bool(
        value and value == Path(value).name and value not in (".", "..")
        and not any(c in value for c in '<>:"/\\|?*\x00')
        and not value[-1].isspace() and not value[-1] == "."
        and len(value) <= 240
    )


def read_config(path: Path) -> tuple[bytes, dict]:
    raw = path.read_bytes()
    try:
        config = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstallerError(f"Invalid Frosty configuration: {error}") from error
    if not isinstance(config, dict):
        raise InstallerError("Frosty configuration must be a JSON object")
    return raw, config


def snapshot(config_path: Path, manager_dir: Path, source_pack: str | None = None) -> Snapshot:
    config_path = Path(config_path).resolve(strict=True)
    manager_dir = Path(manager_dir).resolve(strict=True)
    raw, config = read_config(config_path)
    try:
        game = config["Games"]["NFS16"]
        selected = source_pack if source_pack is not None else game["Options"]["SelectedPack"]
        packs = game["Packs"]
        source = packs[selected]
        order = config.get("GlobalOptions", {}).get("ApplyModOrder", "List")
        game_path = Path(game["GamePath"])
    except (TypeError, KeyError) as error:
        raise InstallerError(f"Invalid/missing NFS16 Frosty profile data: {error}") from error
    if not isinstance(selected, str) or not selected:
        raise InstallerError("Frosty selected pack is invalid")
    if not isinstance(source, str) or order not in ("List", "Priority"):
        raise InstallerError("Unsupported source mod list or load order")
    if any(item.lower().startswith("nfskr-composite-") and item.endswith(":True")
           for item in source.split("|")):
        raise InstallerError("Generated NFSKR composite is not a valid source pack. Choose your original Frosty mod pack.")
    if not game_path.joinpath("NFS16.exe").is_file():
        raise InstallerError(f"NFS16 game executable missing in {game_path}")
    mod_dir = manager_dir / "Mods" / "NFS16"
    if not mod_dir.is_dir():
        raise InstallerError(f"Frosty NFS16 mod installation folder missing: {mod_dir}")
    enabled: list[ModInput] = []
    disabled: list[ModInput] = []
    replaced: list[ModInput] = []
    seen_names: set[str] = set()
    for item in filter(None, source.split("|")):
        if ":" not in item:
            raise InstallerError(f"Invalid enabled flag in pack item: {item!r}")
        name, state = item.rsplit(":", 1)
        if not valid_filename(name):
            raise InstallerError(f"Invalid mod filename in pack: {name!r}")
        key = name.casefold()
        if key in seen_names:
            raise InstallerError(f"Duplicate mod in Frosty pack: {name}")
        seen_names.add(key)
        if state not in ("True", "False"):
            raise InstallerError(f"Unrecognized mod state: {name}:{state}")
        path = (mod_dir / name).resolve()
        if path.parent != mod_dir.resolve():
            raise InstallerError("Unsafe mod path")
        if not path.is_file():
            # Frosty permits saved missing entries, but installing an incomplete
            # composite would silently drop them. Fail until user resolves.
            raise InstallerError(f"Frosty pack contains missing mod: {name}")
        if path.suffix.lower() != ".fbmod":
            raise InstallerError(f"Frosty collection/legacy mod requires explicit adapter: {name}")
        item_data = ModInput(name, path, digest_file(path), path.stat().st_size, state == "True")
        # Old NFSKR FBMods get REPLACED, never folded into a new translation.
        # Do not treat arbitrary other Korean-language patches as ours.
        if name.lower().startswith(("nfs16-korean-", "nfskr-composite-")):
            if item_data.enabled:
                replaced.append(item_data)
            # Never allow a disabled old Korean patch to be selected as a source.
        else:
            (enabled if item_data.enabled else disabled).append(item_data)
    return Snapshot(
        config_path, manager_dir, game_path, selected, source, order,
        digest_bytes(raw), tuple(enabled), tuple(disabled), tuple(replaced)
    )


def preview(snap: Snapshot) -> dict:
    return {
        "source_pack": snap.selected_pack,
        "load_order": snap.order_setting,
        "manager_directory": str(snap.manager_dir),
        "game_directory": str(snap.game_path),
        "enabled_mods": [
            {"filename": x.name, "sha256": x.sha256, "bytes": x.size}
            for x in snap.enabled_mods
        ],
        "disabled_mods": [
            {"filename": x.name, "sha256": x.sha256, "bytes": x.size}
            for x in snap.disabled_mods
        ],
        "config_sha256": snap.config_sha256,
        "replaced_previous_korean_mods": [
            {"filename": x.name, "sha256": x.sha256} for x in snap.replaced_korean_mods
        ],
        "merger_status": "requires_verified_composite",
    }


def validate_composite_header(mod_file: Path) -> tuple[int, int]:
    with mod_file.open("rb") as stream:
        header = stream.read(130)
    if len(header) < 31 or struct.unpack_from("<Q", header)[0] != 0x01005954534F5246:
        raise InstallerError("Invalid merged Frosty mod magic")
    version = struct.unpack_from("<I", header, 8)[0]
    if version != 5:
        raise InstallerError("Expected a Frosty v5 composite .fbmod")
    name_bytes = header[25:25 + header[24]]
    if name_bytes.decode("ascii", errors="replace") != "NFS16":
        raise InstallerError("Composite was built for a different game")
    ver_pos = 25 + header[24]
    game_version = struct.unpack_from("<i", header, ver_pos)[0]
    if game_version != 366510:
        raise InstallerError("Composite game version mismatch")
    manifest = struct.unpack_from("<q", header, 12)[0]
    count = struct.unpack_from("<i", header, 20)[0]
    if manifest <= 30 or manifest + count * 16 > mod_file.stat().st_size:
        raise InstallerError("Composite has an invalid manifest boundary")
    return version, game_version


def verify_merge_certificate(path: Path, snap: Snapshot,
                             selected_sources: Sequence[ModInput] | None = None) -> tuple[Path, dict]:
    """A certificate MUST be emitted by the real binary merger, not by installer.

    The installer only verifies that a tool reported passing full asset/resource
    checks for the exact config and source-mod byte hashes.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("schema") != "nfskr-composite-v1":
        raise InstallerError("Unsupported merge certificate schema")
    if data.get("status") != "verified":
        raise InstallerError("Merge not verified; refusing installation")
    fallbacks = data.get("untranslated_fallback_count", 0)
    if not isinstance(fallbacks, int) or fallbacks < 0:
        raise InstallerError("Invalid semantic fallback count")
    if fallbacks and data.get("semantic_conflict_policy") != "preserve_mod_text":
        raise InstallerError(
            "Unhandled localization semantics; automatic source-text policy is missing")
    if data.get("source_pack") != snap.selected_pack:
        raise InstallerError("Selected Frosty source pack changed")
    if data.get("source_pack_list") != snap.source_pack_list:
        raise InstallerError("Mod enable states or order changed")
    if data.get("config_sha256") != snap.config_sha256:
        raise InstallerError("Frosty config changed after merge plan")
    sources = tuple(selected_sources) if selected_sources is not None else snap.enabled_mods
    all_known = {x.name.casefold(): x for x in (*snap.enabled_mods, *snap.disabled_mods)}
    if len(sources) != len({x.name.casefold() for x in sources}):
        raise InstallerError("Duplicate selected source mods")
    if any(all_known.get(x.name.casefold()) != x for x in sources):
        raise InstallerError("Selection contains an unrecognized or modified source mod")
    fingerprint = [{"filename": x.name, "sha256": x.sha256} for x in sources]
    if data.get("enabled_mods") != fingerprint:
        raise InstallerError("Installed source .fbmod hashes changed")
    checks = data.get("verified_checks", {})
    required = (
        "frosty_reader", "locale_ebx_chunk_roundtrip",
        "source_resource_coverage", "font_resource_integrity",
        "no_unresolved_conflicts"
    )
    if any(checks.get(name) is not True for name in required):
        raise InstallerError("Merged binary has unverified resource coverage")
    merged_mod = Path(data["merged_fbmod"]).resolve(strict=True)
    if not merged_mod.is_file() or merged_mod.suffix.lower() != ".fbmod":
        raise InstallerError("Merged FBMod missing or wrong extension")
    if digest_file(merged_mod) != data.get("merged_sha256"):
        raise InstallerError("Merged FBMod checksum mismatch")
    validate_composite_header(merged_mod)
    return merged_mod, data


def unique_pack_name(existing: dict, preferred: str = "NFSKR") -> str:
    # Legacy Frosty 1.0.6.3 saves run.bat as UTF-8 but CMD reads it using
    # the system OEM codepage. Non-ASCII pack paths make mklink fail on NTFS.
    if not preferred.isascii() or not preferred.replace("-","").isalnum():
        raise InstallerError("Frosty 1.0.6.3 requires ASCII internal pack names")
    if preferred not in existing:
        return preferred
    for i in range(2, 1000):
        candidate = f"{preferred}-{i}"
        if candidate not in existing:
            return candidate
    raise InstallerError("Too many existing Korean packs; choose a different name")


def write_fbpack(path: Path, merged_mod: Path, *, pack_name: str,
                 manager_version: str = "1.0.6.3") -> str:
    """Writes native Frosty ZIP container, with actual combined FBMod inside."""
    if not valid_filename(merged_mod.name):
        raise InstallerError("Unsafe combined mod filename")
    validate_composite_header(merged_mod)
    if path.exists():
        raise InstallerError(f"Refusing to overwrite pack archive: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": pack_name,
        "managerVersion": manager_version,
        "version": 1,
        "mods": [merged_mod.name],
    }
    temp = path.with_name(path.name + ".tmp")
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_STORED,
                             allowZip64=True) as archive:
            archive.write(merged_mod, merged_mod.name)
            archive.writestr("manifest.json", json.dumps(
                manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        with zipfile.ZipFile(temp, "r") as archive:
            if sorted(archive.namelist()) != sorted([merged_mod.name, "manifest.json"]):
                raise InstallerError("Invalid .fbpack entry set")
            if archive.testzip() is not None:
                raise InstallerError("Corrupt .fbpack data")
            exported = json.loads(archive.read("manifest.json").decode("utf-8"))
            if exported != manifest:
                raise InstallerError("Frosty pack manifest changed")
            if digest_bytes(archive.read(merged_mod.name)) != digest_file(merged_mod):
                raise InstallerError("FBMod bytes changed within .fbpack")
        temp.replace(path)
        return digest_file(path)
    finally:
        if temp.exists():
            temp.unlink()


def installed_processes_running() -> bool:
    """Windows-only process check; inject a stub for regression tests."""
    import subprocess
    for name in ("FrostyModManager.exe", "NFS16.exe"):
        proc = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, text=True, encoding="cp1252", errors="replace",
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if proc.returncode != 0:
            raise InstallerError("Could not check active game/manager processes")
        if name.casefold() in proc.stdout.casefold():
            return True
    return False



_GENERATED_PACK_NAME = re.compile(r"NFSKR(?:-(?:[2-9]|[1-9][0-9]+))?\Z", re.IGNORECASE)
_GENERATED_MOD_ENTRY = re.compile(
    r"(NFSKR-Composite-([0-9A-Fa-f]{12})\.fbmod):True\Z", re.IGNORECASE
)


def _eligible_generated_pack(name: str, entry: str, mod_dir: Path) -> bool:
    """Only a single intact, NFSKR-produced composite can be replaced.

    Never touch a user's manually composed pack or an altered/corrupt mod.
    """
    if not isinstance(name, str) or not _GENERATED_PACK_NAME.fullmatch(name):
        return False
    if not isinstance(entry, str):
        return False
    match = _GENERATED_MOD_ENTRY.fullmatch(entry)
    if match is None:
        return False
    existing = mod_dir / match.group(1)
    if not existing.is_file() or existing.is_symlink():
        return False
    try:
        if digest_file(existing)[:12].casefold() != match.group(2).casefold():
            return False
        validate_composite_header(existing)
        return True
    except (InstallerError, OSError, ValueError, struct.error):
        return False


def update_target(packs: dict, mod_dir: Path, active: str = "") -> tuple[str, bool]:
    """Re-use active generated NFSKR, else latest valid NFSKR entry.

    A non-generated profile named NFSKR is not owned by us and is preserved.
    New installations still get unique ASCII NFSKR names as needed.
    """
    if active in packs and _GENERATED_PACK_NAME.fullmatch(active) and (
        not _eligible_generated_pack(active, packs[active], mod_dir)
    ):
        raise InstallerError(
            "현재 NFSKR 프로필이 수동으로 변경됐거나 파일 무결성이 다릅니다. "
            "안전을 위해 자동 덮어쓰기를 중단했습니다.")
    if _eligible_generated_pack(active, packs.get(active, ""), mod_dir):
        return active, True
    candidates=[]
    for name, entry in packs.items():
        if _eligible_generated_pack(name,entry,mod_dir):
            number=1 if name.upper()=="NFSKR" else int(name.split("-",1)[1])
            candidates.append((number,name))
    if candidates:
        return max(candidates)[1],True
    return unique_pack_name(packs),False


def _pack_references_mod(packs: dict, filename: str) -> bool:
    """Include enabled and disabled references, not just selected pack."""
    return any(
        any(item.rsplit(":",1)[0].casefold()==filename.casefold()
            for item in value.split("|") if ":" in item)
        for value in packs.values() if isinstance(value,str)
    )

def install_verified(
    snap: Snapshot, certificate: Path, output_directory: Path,
    *, selected_sources: Sequence[ModInput] | None = None,
    is_busy: Callable[[], bool] = installed_processes_running,
) -> dict:
    """Atomically install/refresh one NFSKR profile without accumulating packs.

    A fresh composite gets a content-hash filename; only the generated pack
    pointer changes. The previous FBMod remains intact for rollback. Any
    previous manual packs and third-party mod files are untouched.
    """
    if is_busy():
        raise InstallerError("Close NFS16 and Frosty Manager normally, then retry")
    refreshed = snapshot(snap.config_path, snap.manager_dir, snap.selected_pack)
    if refreshed != snap:
        raise InstallerError("Frosty changed since initial scan; rescan before installing")
    merged_mod, details = verify_merge_certificate(certificate, refreshed, selected_sources)
    original_raw, original_cfg = read_config(snap.config_path)
    game=original_cfg["Games"]["NFS16"]
    packs=game["Packs"]
    original_selected=game["Options"]["SelectedPack"]
    mod_dir=snap.manager_dir/"Mods"/"NFS16"
    new_pack, is_update=update_target(packs,mod_dir,original_selected)
    old_entry=packs.get(new_pack) if is_update else None
    token = digest_file(merged_mod)[:12]
    name = f"NFSKR-Composite-{token}.fbmod"
    installed_path = mod_dir / name
    if installed_path.is_symlink():
        raise InstallerError("Refusing symlink destination for generated FBMod")
    if installed_path.exists() and digest_file(installed_path) != digest_file(merged_mod):
        raise InstallerError("Destination composite exists with different content")
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    archive_path=output_directory/f"NFSKR-{token}.fbpack"
    backup_path=output_directory/f"manager_config.before-{token}.json"
    journal_path=output_directory/f"install-journal-{token}.json"
    if any(p.exists() for p in (archive_path,backup_path,journal_path)):
        raise InstallerError("An existing install artifact has the same fingerprint")

    # Never remove the old generated FBMod at commit: restoring the preceding
    # version must work even after version and selected source mods change.
    with tempfile.TemporaryDirectory(dir=output_directory) as staging_dir:
        staged_mod=Path(staging_dir)/name
        shutil.copy2(merged_mod,staged_mod)
        if digest_file(staged_mod)!=digest_file(merged_mod):
            raise InstallerError("Staged composite hash mismatch")
        staged_fbpack=Path(staging_dir)/"bundle.fbpack"
        write_fbpack(staged_fbpack,staged_mod,pack_name=new_pack)
        updated=json.loads(json.dumps(original_cfg,ensure_ascii=False))
        updated["Games"]["NFS16"]["Packs"][new_pack]=name+":True"
        updated["Games"]["NFS16"]["Options"]["SelectedPack"]=new_pack
        config_staged=Path(staging_dir)/"manager_config.after.json"
        config_staged.write_text(
            json.dumps(updated,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        staged_hash=digest_file(config_staged)
        config_temp=snap.config_path.with_name(snap.config_path.name+".nfskr.tmp")
        if config_temp.exists():
            raise InstallerError("Stale temporary Frosty config detected")
        if is_busy() or digest_bytes(snap.config_path.read_bytes())!=snap.config_sha256:
            raise InstallerError("Frosty running or config changed during preparation")
        created_new=False
        published_archive=False
        published_backup=False
        published_journal=False
        try:
            if not installed_path.exists():
                # Stage in destination directory, then rename without clobbering
                # another file introduced between the two preflight checks.
                mod_temp=mod_dir/(name+".nfskr-staging")
                if mod_temp.exists():
                    raise InstallerError("Stale generated mod staging file exists")
                try:
                    shutil.copyfile(staged_mod,mod_temp)
                    if digest_file(mod_temp)!=digest_file(merged_mod):
                        raise InstallerError("Installed FBMod staging checksum mismatch")
                    if installed_path.exists():
                        raise InstallerError("Another process created the generated FBMod")
                    mod_temp.rename(installed_path)
                    created_new=True
                finally:
                    if mod_temp.exists():
                        mod_temp.unlink()
            if digest_file(installed_path)!=digest_file(merged_mod):
                raise InstallerError("Installed composite differs from approved merger")
            shutil.copyfile(staged_fbpack,archive_path)
            published_archive=True
            backup_path.write_bytes(original_raw)
            published_backup=True
            # A crash after config replacement must leave an already-persisted
            # journal, so prepare it BEFORE atomic config commit.
            original_entry=packs.get(original_selected,"")
            previous_pack=(original_selected if is_update else
                snap.selected_pack if isinstance(original_entry,str) and
                original_entry.casefold().startswith("nfskr-composite-")
                else original_selected)
            previous_file=None
            previous_hash=None
            if is_update:
                previous_file=mod_dir / old_entry.rsplit(":",1)[0]
                previous_hash=digest_file(previous_file)
            journal={
                "schema":"nfskr-install-journal-v1",
                "operation":"update" if is_update else "new",
                "previous_pack":previous_pack,
                "original_selected_pack":original_selected,
                "source_pack":snap.selected_pack,
                "merged_source_mods":details["enabled_mods"],
                "new_pack":new_pack,
                "replaced_pack_entry":old_entry if is_update else None,
                "previous_composite":str(previous_file) if previous_file else None,
                "previous_composite_sha256":previous_hash,
                "frosty_config":str(snap.config_path),
                "original_config_sha256":snap.config_sha256,
                "installed_composite":str(installed_path),
                "installed_composite_sha256":digest_file(installed_path),
                "created_composite":created_new,
                "created_archive":str(archive_path),
                "backup_file":str(backup_path),
                "new_config_sha256":staged_hash,
                "created_at":int(time.time()),
            }
            journal_path.write_text(
                json.dumps(journal,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
            published_journal=True
            if is_busy() or digest_bytes(snap.config_path.read_bytes())!=snap.config_sha256:
                raise InstallerError("Frosty started or config changed before commit")
            shutil.copyfile(config_staged,config_temp)
            if digest_file(config_temp)!=staged_hash:
                raise InstallerError("Staged Frosty config changed during write")
            os.replace(config_temp,snap.config_path)
            written_raw,written=read_config(snap.config_path)
            if digest_bytes(written_raw)!=staged_hash or (
                written["Games"]["NFS16"]["Packs"][new_pack]!=name+":True"
            ) or written["Games"]["NFS16"]["Options"]["SelectedPack"]!=new_pack:
                raise InstallerError("New Korean Frosty pack commit did not verify")
            return journal
        except BaseException:
            if snap.config_path.is_file() and digest_file(snap.config_path)==staged_hash:
                # Another program's concurrent edits must never be erased.
                rollback_tmp=snap.config_path.with_name(
                    snap.config_path.name+".nfskr.commit-recovery.tmp")
                if not rollback_tmp.exists():
                    rollback_tmp.write_bytes(original_raw)
                    os.replace(rollback_tmp,snap.config_path)
            # A concurrent modification means the generated config was NOT
            # restored. Preserve backups, journal, and FBMod for manual recovery.
            recovered=(snap.config_path.is_file() and
                       digest_file(snap.config_path)==snap.config_sha256)
            if recovered:
                if created_new and installed_path.is_file() and (
                    digest_file(installed_path)==digest_file(merged_mod)
                ):
                    installed_path.unlink()
                if published_journal and journal_path.is_file():
                    journal_path.unlink()
                if published_backup and backup_path.is_file():
                    backup_path.unlink()
                if published_archive and archive_path.is_file():
                    archive_path.unlink()
            raise
        finally:
            if config_temp.exists():
                config_temp.unlink()

def rollback_install(
    journal_file: Path,
    *, is_busy: Callable[[], bool] = installed_processes_running,
) -> dict:
    """Undo only this installer revision and retain the previous NFSKR FBMod.

    For in-place updates this restores the previous composite in the same
    pack; for first-time installations it restores the original Frosty pack.
    Never deletes an FBMod still referenced by any restored Frosty profile.
    """
    if is_busy():
        raise InstallerError("Close Frosty and NFS16 normally before rollback")
    journal=json.loads(Path(journal_file).read_text(encoding="utf-8-sig"))
    if journal.get("schema")!="nfskr-install-journal-v1":
        raise InstallerError("Unsupported rollback journal format")
    config=Path(journal["frosty_config"])
    backup=Path(journal["backup_file"])
    installed=Path(journal["installed_composite"])
    if not config.is_file() or not backup.is_file():
        raise InstallerError("Cannot find active config or original backup")
    if digest_file(config)!=journal["new_config_sha256"]:
        raise InstallerError("Frosty config changed after install; refusing unsafe rollback")
    before=backup.read_bytes()
    if digest_bytes(before)!=journal["original_config_sha256"]:
        raise InstallerError("Frosty config backup failed SHA256")
    current=json.loads(config.read_text(encoding="utf-8-sig"))
    selected=current["Games"]["NFS16"]["Options"]["SelectedPack"]
    if selected!=journal["new_pack"]:
        raise InstallerError("Installed Korean profile is no longer selected")
    if current["Games"]["NFS16"]["Packs"].get(journal["new_pack"])!=installed.name+":True":
        raise InstallerError("The generated Korean pack was modified; refusing rollback")
    if installed.is_file() and digest_file(installed)!=journal["installed_composite_sha256"]:
        raise InstallerError("Generated composite changed; refusing rollback")
    operation=journal.get("operation","new")
    if operation not in ("new","update"):
        raise InstallerError("Unsupported NFSKR journal operation")
    if operation=="update":
        before_cfg=json.loads(before.decode("utf-8-sig"))
        expected=journal.get("replaced_pack_entry")
        if before_cfg["Games"]["NFS16"]["Packs"].get(journal["new_pack"])!=expected:
            raise InstallerError("Previous Korean profile entry no longer matches backup")
        prev=Path(journal["previous_composite"])
        if not prev.is_file() or digest_file(prev)!=journal["previous_composite_sha256"]:
            raise InstallerError("Cannot verify previous NFSKR mod for version rollback")
    restore_data=before
    if operation=="new" and journal.get("original_selected_pack")!=journal["previous_pack"]:
        restored=json.loads(before.decode("utf-8-sig"))
        original=journal["previous_pack"]
        if original not in restored["Games"]["NFS16"]["Packs"]:
            raise InstallerError("Original source pack no longer exists in backup")
        restored["Games"]["NFS16"]["Options"]["SelectedPack"]=original
        restore_data=(json.dumps(restored,ensure_ascii=False,indent=2)+"\n").encode("utf8")
    restore_cfg=json.loads(restore_data.decode("utf-8-sig"))
    referenced=_pack_references_mod(restore_cfg["Games"]["NFS16"]["Packs"],installed.name)
    can_delete=(journal.get("created_composite",True) and not referenced)
    tmp=config.with_name(config.name+".nfskr.rollback.tmp")
    if tmp.exists():
        raise InstallerError("Another Frosty rollback temporary file exists")
    try:
        tmp.write_bytes(restore_data)
        if is_busy() or digest_file(config)!=journal["new_config_sha256"]:
            raise InstallerError("Frosty opened or config changed during rollback")
        os.replace(tmp,config)
        removed=False
        if can_delete and installed.is_file() and (
            digest_file(installed)==journal["installed_composite_sha256"]
        ):
            installed.unlink()
            removed=True
        deleted_links=[]
        if journal.get("desktop_shortcuts"):
            from nfskr_shortcuts import remove_owned_shortcuts
            deleted_links=remove_owned_shortcuts(journal["desktop_shortcuts"])
        return {
            "restored_pack":journal["previous_pack"],
            "restored_previous_version":operation=="update",
            "original_config_sha256":journal["original_config_sha256"],
            "generated_fbmod_removed":removed,
            "removed_desktop_shortcuts":deleted_links,
            "fbpack_retained":journal["created_archive"],
        }
    finally:
        if tmp.exists():
            tmp.unlink()
