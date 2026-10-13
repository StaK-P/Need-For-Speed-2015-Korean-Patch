#!/usr/bin/env python3
"""Versioned Frosty v1/v3/v5 FBMod parser and v5 writer for NFS16.

The parser operates on EXACT input resource records, verifies index structure,
bounds, bundle layout and payload offsets and NEVER writes source mods. v1-v3
old bundles are discarded only as Frosty's actual 1.0.6.3 reader does; added
bundle references are preserved when converting to current version 5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import struct

MAGIC=0x01005954534F5246
GAME_VERSION=366510

class ModFormatError(ValueError):
    pass


def cstr(data: bytes, at: int, limit: int) -> tuple[str,int]:
    end=data.find(b"\0",at,limit)
    if end<0:
        raise ModFormatError(f"Unterminated string at {at}")
    return data[at:end].decode("utf-8","strict"),end+1


def cwrite(s: str) -> bytes:
    if "\0" in s:raise ModFormatError("NUL in text")
    return s.encode("utf8")+b"\0"


def p32(n: int) -> bytes:
    return struct.pack("<i",n if n<0x80000000 else n-0x100000000)


@dataclass
class Entry:
    kind: int
    name: str
    payload: bytes | None
    size: int=0
    flags: int=0
    handler: int=0
    userdata: str=""
    added_bundles: tuple[int,...]=()
    res_type: int=0
    res_rid: int=0
    res_meta: bytes=b""
    chunk_meta: bytes=b""
    bundle_superhash: int=0
    source: str=""
    def key(self) -> tuple[int,str]:
        return self.kind,self.name.lower()
    def identity(self) -> str:
        return f"{self.kind}:{self.name.lower()}"


@dataclass
class Parsed:
    path: Path
    version: int
    game_version: int
    profile: str
    title: str
    author: str
    category: str
    mod_version: str
    description: str
    link: str
    entries: list[Entry]
    blocks: int
    sha256: str


class Reader:
    def __init__(self,data:bytes,source:str):
        self.b=data;self.src=source;self.at=0;self.limit=len(data)
    def read(self,n:int)->bytes:
        if n<0 or self.at+n>self.limit:
            raise ModFormatError(f"Out-of-bounds read {self.at}+{n}: {self.src}")
        x=self.b[self.at:self.at+n];self.at+=n
        return x
    def byte(self)->int:return self.read(1)[0]
    def int(self)->int:return struct.unpack("<i",self.read(4))[0]
    def uint(self)->int:return struct.unpack("<I",self.read(4))[0]
    def long(self)->int:return struct.unpack("<q",self.read(8))[0]
    def ulong(self)->int:return struct.unpack("<Q",self.read(8))[0]
    def string(self)->str:
        v,self.at=cstr(self.b,self.at,self.limit)
        return v


def parse_mod(path: Path) -> Parsed:
    path=Path(path)
    blob=path.read_bytes()
    if len(blob)<55 or len(blob)>1073741824:
        raise ModFormatError(f"FBMod invalid size: {path}")
    rd=Reader(blob,str(path))
    magic=rd.ulong()
    version=rd.uint()
    if magic!=MAGIC or version not in (1,2,3,4,5):
        raise ModFormatError(f"Unsupported Frosty header {magic:x}, version {version}: {path}")
    manifest=rd.long()
    blocks=rd.int()
    if not(0<blocks<=500000 and 32<=manifest<=len(blob)-blocks*16):
        raise ModFormatError(f"Invalid FBMod manifest: {path}")
    rd.limit=manifest
    prof_len=rd.byte()
    profile=rd.read(prof_len).decode("ascii","strict")
    game=rd.int()
    if profile!="NFS16" or game!=GAME_VERSION:
        raise ModFormatError(f"Wrong Frosty profile/version: {profile}/{game} {path}")
    labels=[rd.string() for _ in range(6 if version>=5 else 5)]
    if version<5:labels.append("")
    total=rd.int()
    if not 0<=total<=200000:
        raise ModFormatError("Implausible FBMod resource count")
    raw=[]
    for _ in range(total):
        kind=rd.byte()
        idx=rd.int()
        if kind not in (0,1,2,3,4):
            raise ModFormatError(f"Unknown resource type {kind}")
        if idx < -1 or idx>=blocks:
            raise ModFormatError(f"Invalid resource index {idx}/{blocks}")
        name=rd.string() if (version>3 or idx!=-1) else ""
        size=flags=handler=0
        userdata=""
        if idx!=-1:
            sha=rd.read(20)
            size=rd.long()
            flags=rd.byte()
            handler=rd.int()
            if version>=3:userdata=rd.string()
            if size<0 or size>2**40:raise ModFormatError("Bad raw resource size")
        bundles=[]
        if version<=3 and idx!=-1:
            # v1-v3 have original bundle IDs and added bundle IDs.
            old=rd.int()
            if old<0 or old>500000:raise ModFormatError("Bad original-bundle count")
            rd.read(old*4)
            new=rd.int()
            if new<0 or new>500000:raise ModFormatError("Bad added-bundle count")
            bundles=[rd.int() for _ in range(new)]
        elif version>3:
            new=rd.int()
            if new<0 or new>500000:raise ModFormatError("Bad bundle list count")
            bundles=[rd.int() for _ in range(new)]
        res_type=res_rid=bundle_super=0
        res_meta=chunk_meta=b""
        if kind==2:
            res_type=rd.uint();res_rid=rd.ulong()
            n=rd.int()
            if n<0 or n>65536:raise ModFormatError("Bad RES metadata size")
            res_meta=rd.read(n)
        elif kind==3:
            chunk_meta=rd.read(24)
        elif kind==4:
            name=rd.string()
            bundle_super=rd.int()
        raw.append(Entry(kind,name,None,size,flags,handler,userdata,tuple(bundles),
                         res_type,res_rid,res_meta,chunk_meta,bundle_super,str(path)))
        raw[-1].__dict__["_payload_index"]=idx
    if rd.at!=manifest:
        raise ModFormatError(f"Resource bytes end {rd.at}, expected manifest {manifest}: {path}")
    rd.limit=len(blob)
    block_start=manifest+16*blocks
    table=[]
    for i in range(blocks):
        offset,length=struct.unpack_from("<qq",blob,manifest+i*16)
        if offset<0 or length<0 or block_start+offset+length>len(blob):
            raise ModFormatError(f"Malformed payload index {i}")
        table.append((block_start+offset,length))
    for entry in raw:
        idx=entry.__dict__.pop("_payload_index")
        if idx>=0:
            start,n=table[idx]
            entry.payload=blob[start:start+n]
            if entry.kind!=0 and not entry.payload:
                raise ModFormatError("Empty modified asset payload")
    # Validate that all references have resolvable names and no unsupported
    # resource would be silently dropped during conversion to v5.
    for entry in raw:
        if entry.kind in (1,2,3,4) and not entry.name:
            raise ModFormatError("Unnamed non-embedded resource")
    return Parsed(path,version,game,profile,*labels,raw,blocks,
                  hashlib.sha256(blob).hexdigest().upper())


def make_mod(entries:list[Entry],dest:Path,title:str,
             version_label:str="1.0-merged-preview",author:str="NFSKR Installer") -> None:
    dest=Path(dest)
    if dest.exists():raise FileExistsError(dest)
    if not entries:raise ModFormatError("Refusing to write empty merged mod")
    header=bytearray(struct.pack("<QIqi",MAGIC,5,-1,-1))
    header+=b"\x05NFS16"+struct.pack("<i",GAME_VERSION)
    for s in (title,author,"Localization",version_label,
              "Locally generated composite for the active Frosty profile.",
              ""):
        header+=cwrite(s)
    table=bytearray(struct.pack("<i",len(entries)))
    chunks:list[bytes]=[]
    for entry in entries:
        if entry.kind not in (0,1,2,3,4):raise ModFormatError("Unexpected resource type")
        idx=-1
        if entry.payload is not None:
            idx=len(chunks)
            chunks.append(entry.payload)
        table+=struct.pack("<Bi",entry.kind,idx)
        # Frosty 1.0.6.3 v5 always stores name, even when no payload.
        table+=cwrite(entry.name)
        if idx!=-1:
            table+=hashlib.sha1(entry.payload).digest()
            table+=struct.pack("<qBi",entry.size,entry.flags,
                               entry.handler if entry.handler<0x80000000 else entry.handler-0x100000000)
            table+=cwrite(entry.userdata)
        table+=struct.pack("<i",len(entry.added_bundles))
        for bid in entry.added_bundles:table+=p32(bid&0xFFFFFFFF)
        if entry.kind==2:
            table+=struct.pack("<IQi",entry.res_type,entry.res_rid,len(entry.res_meta))
            table+=entry.res_meta
        elif entry.kind==3:
            if len(entry.chunk_meta)!=24:
                raise ModFormatError("Chunk must have 24-byte metadata")
            table+=entry.chunk_meta
        elif entry.kind==4:
            table+=cwrite(entry.name)+p32(entry.bundle_superhash&0xFFFFFFFF)
    manifest=len(header)+len(table)
    table_bytes=bytearray()
    rel=0
    for chunk in chunks:
        table_bytes+=struct.pack("<qq",rel,len(chunk))
        rel+=len(chunk)
    header[12:20]=struct.pack("<q",manifest)
    header[20:24]=struct.pack("<i",len(chunks))
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+".writing")
    if tmp.exists():raise FileExistsError(tmp)
    try:
        with tmp.open("wb") as f:
            f.write(header);f.write(table);f.write(table_bytes)
            for chunk in chunks:f.write(chunk)
        expected_size=manifest+len(chunks)*16+rel
        if tmp.stat().st_size!=expected_size:raise ModFormatError("FBMod byte size mismatch")
        tmp.replace(dest)
    finally:
        if tmp.exists():tmp.unlink()
    verify=parse_mod(dest)
    if len(verify.entries)!=len(entries):
        dest.unlink(missing_ok=True)
        raise ModFormatError("FBMod roundtrip resource count mismatch")
    for a,b in zip(entries,verify.entries):
        if (a.kind,a.name,a.payload,a.size,a.flags,a.handler,
            a.added_bundles,a.res_type,a.res_rid,a.res_meta,a.chunk_meta) != \
           (b.kind,b.name,b.payload,b.size,b.flags,b.handler,
            b.added_bundles,b.res_type,b.res_rid,b.res_meta,b.chunk_meta):
            dest.unlink(missing_ok=True)
            raise ModFormatError(f"FBMod resource roundtrip failed: {a.identity()}")
