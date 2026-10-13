#!/usr/bin/env python3
"""Build a small Frosty NFS16 .fbmod using Flammenwerfer's UTF-16 localization diff.

No game archives or proprietary font bytes are placed in the repository by this tool.
See docs or scripts for optional font-asset injection once confirmed compatible.
"""
import argparse
import base64
import csv
import dataclasses
import hashlib
import json
import pathlib
import struct
import sys
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_CSV = ROOT / "work/locale-extract/en-strings.csv"
CONFIG = ROOT / "tools/poc-strings.json"
OUT = ROOT / "work/poc/nfs16-korean-text-test.fbmod"
MAGIC = 0x01005954534F5246
VERSION = 5
GAME_VERSION = 366510

@dataclasses.dataclass
class Resource:
    kind: int
    name: str
    payload: Optional[bytes] = None
    original_size: Optional[int] = None
    flags: int = 0
    handler: int = 0
    res_type: int = 0
    res_rid: int = 0
    res_meta: bytes = b""
    userdata: str = ""
    sha1: Optional[bytes] = None

def cstring(value: str) -> bytes:
    if "\x00" in value:
        raise ValueError("NUL cannot be serialized into a Frosty cstring")
    return value.encode("utf-8") + b"\x00"

def u32(value: int) -> bytes:
    return struct.pack("<I", value)

def i32(value: int) -> bytes:
    if 0 <= value <= 0xFFFFFFFF and value >= 0x80000000:
        value -= 0x100000000
    return struct.pack("<i", value)

def u64(value: int) -> bytes:
    return struct.pack("<Q", value)

def i64(value: int) -> bytes:
    return struct.pack("<q", value)

def frost_fvn1(name: str) -> int:
    # FrostyHash.Fnv1.HashString uses DJB-style 5381 / 33 xor.
    result = 5381
    for b in name.encode("ascii"):
        result = ((result * 33) ^ b) & 0xFFFFFFFF
    return result

def make_fs_diff(records: list[tuple[int, str]]) -> bytes:
    assembly_type = (
        "FsLocalizationPlugin.ModifiedFsLocalizationAsset, FsLocalizationPlugin, "
        "Version=0.4.1.0, Culture=neutral, PublicKeyToken=null"
    )
    result = bytearray(cstring(assembly_type))
    result += u32(0xABCD0001)
    result += i32(len(records))
    for id_number, string in records:
        # FsLocalization is UTF-16 BMP; emoji and other non-BMP chars are unsupported.
        if any(ord(ch) > 0xFFFF for ch in string):
            raise ValueError(f"Non-BMP character in {id_number:08X}")
        result += u32(id_number)
        result += string.encode("utf-16-le") + b"\x00\x00"
    return bytes(result)

def load_translation_records(source: pathlib.Path, config: pathlib.Path) -> list[tuple[int, str]]:
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        originals = {row["string_id"].upper(): row["source_text"] for row in csv.DictReader(stream)}
    changes = json.loads(config.read_text(encoding="utf-8"))
    output: list[tuple[int, str]] = []
    ids: set[int] = set()
    for change in changes["entries"]:
        name = change["id"].upper()
        if name not in originals:
            raise ValueError(f"Missing string ID {name}")
        if originals[name] != change["expected_original"]:
            raise ValueError(f"Unexpected original for {name}: {originals[name]!r}")
        value = change["ko"]
        if not value or not isinstance(value, str):
            raise ValueError(f"Empty/non-string translation for {name}")
        number = int(name, 16)
        if number in ids:
            raise ValueError(f"Duplicate translation ID {name}")
        ids.add(number)
        output.append((number, value))
    return output

def serialize_base(record: Resource, index: int) -> bytes:
    result = bytearray(struct.pack("<Bi", record.kind, index))
    result += cstring(record.name)
    if index != -1:
        data = record.payload
        if data is None:
            raise ValueError("Resource data missing")
        sha1 = record.sha1 or hashlib.sha1(data).digest()
        if len(sha1) != 20:
            raise ValueError("Invalid SHA1")
        original_size = record.original_size if record.original_size is not None else len(data)
        result += sha1 + i64(original_size)
        result += struct.pack("<B", record.flags) + i32(record.handler) + cstring(record.userdata)
    result += i32(0)  # no added bundles (vanilla asset already exists)
    if record.kind == 2:  # Res
        result += struct.pack("<IQi", record.res_type, record.res_rid, len(record.res_meta))
        result += record.res_meta
    return bytes(result)

def build_mod(resources: list[Resource], output: pathlib.Path, label: str, mod_version: str = "0.0.1-poc") -> None:
    header = bytearray(struct.pack("<QI", MAGIC, VERSION))
    header += i64(-1) + i32(-1)
    # NativeWriter.Write(string) uses a single-byte 7bit length for "NFS16".
    header += b"\x05NFS16" + i32(GAME_VERSION)
    metadata = [label, "NFSKR Patch Project", "Localization", mod_version,
                "NFS 2015 Korean glyph and localized text smoke test. Incomplete development build.",
                "https://github.com/CadeEvs/FrostyToolsuite"]
    for value in metadata:
        header += cstring(value)
    manifests: list[bytes] = []
    blocks = bytearray()
    entries = bytearray(i32(len(resources)))
    for item in resources:
        index = -1
        if item.payload is not None:
            index = len(manifests)
            manifests.append(item.payload)
        entries += serialize_base(item, index)
    for block in manifests:
        blocks += block
    offsets = bytearray()
    data_offset = 0
    for blob in manifests:
        offsets += i64(data_offset) + i64(len(blob))
        data_offset += len(blob)
    manifest_offset = len(header) + len(entries)
    header[12:20] = i64(manifest_offset)
    header[20:24] = i32(len(manifests))
    result = header + entries + offsets + blocks
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_bytes(result)
    tmp.replace(output)
    verify_mod(output, resources, manifests)
    print("FROSTY_MOD_WRITTEN", output, "bytes=", output.stat().st_size,
          "resources=", len(resources), "blobs=", len(manifests))

def verify_mod(path: pathlib.Path, expect: list[Resource], blobs: list[bytes]) -> None:
    raw = path.read_bytes()
    magic, version, offset, count = struct.unpack_from("<QIqI", raw)
    if magic != MAGIC or version != VERSION or count != len(blobs):
        raise ValueError("Broken Frosty mod header")
    if offset >= len(raw):
        raise ValueError("Invalid mod manifest offset")
    expected_offset = offset + count * 16
    for index, blob in enumerate(blobs):
        block_offset, block_size = struct.unpack_from("<qq", raw, offset + index * 16)
        if block_size != len(blob) or raw[expected_offset + block_offset:
                                        expected_offset + block_offset + block_size] != blob:
            raise ValueError("Incorrect payload in manifest index " + str(index))
    print("MANIFEST_VALIDATED", count, "blobs")

def append_font_assets(resources: list[Resource], manifest: pathlib.Path) -> int:
    if not manifest.is_file():
        raise FileNotFoundError(f"Font asset export missing: {manifest}")
    count = 0
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8-sig").splitlines(), 1):
        parts = raw.split("\t")
        if len(parts) != 7:
            raise ValueError(f"Invalid font export manifest at {line_number}: {len(parts)} fields")
        kind, name, restype, resrid, encodedmeta, size, file_name = parts
        compressed = pathlib.Path(file_name)
        if not compressed.is_file():
            raise FileNotFoundError(f"Missing compressed font asset {compressed}")
        data = compressed.read_bytes()
        if not data:
            raise ValueError("Empty font mod payload")
        if kind == "res":
            resources.append(Resource(2, name.lower(), payload=data, original_size=int(size),
                                      res_type=int(restype), res_rid=int(resrid),
                                      res_meta=base64.b64decode(encodedmeta)))
        elif kind == "ebx":
            resources.append(Resource(1, name.lower(), payload=data, original_size=int(size)))
        else:
            raise ValueError("Unknown font asset kind " + kind)
        count += 1
    if count not in (3, 10):
        raise ValueError(f"Expected 3 original-DIN-preserving resources or 10 legacy font assets, found {count}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, default=SOURCE_CSV)
    parser.add_argument("--config", type=pathlib.Path, default=CONFIG)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    parser.add_argument("--font-manifest", type=pathlib.Path, default=None)
    parser.add_argument("--mod-version", default="0.0.1-poc")
    parser.add_argument("--title", default=None)
    args = parser.parse_args()
    records = load_translation_records(args.source, args.config)
    payload = make_fs_diff(records)
    resources = [Resource(0, "Icon")] + [Resource(0, f"Screenshot{i}") for i in range(4)]
    resources.append(Resource(
        1, "localization/textdbs/en_us", payload=payload, handler=frost_fvn1("fsuitextdatabase")
    ))
    if args.font_manifest:
        print("ADDED_FONT_ASSETS", append_font_assets(resources, args.font_manifest))
    title=args.title or ("NFSKR Home Menu + Font PoC" if args.font_manifest else "NFSKR Text PoC")
    build_mod(resources, args.out, title, args.mod_version)
    print("REPLACED_IDS", len(records), "sample:", ", ".join(f"{k:08X}" for k, _ in records[:12]))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("POC_FAILED", type(error).__name__, error, file=sys.stderr)
        raise SystemExit(1)
