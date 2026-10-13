#!/usr/bin/env python3
"""NFS16 Frostbite localization codec for offline NFSKR 3-way resource merges.

Spec grounded in FrostyFlammenwerfer v0.4.1/Flammen.cs and original NFS16
histogram + string binary chunks. No game bytes/EA fonts are embedded.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import struct

class LocaleCodecError(ValueError):
    pass

try:
    import lz4.block
except ImportError:
    lz4 = None


def decompress_frostbite(buf: bytes) -> bytes:
    at=0;pieces=[]
    if not buf:raise LocaleCodecError("Empty Frostbite compressed payload")
    while at<len(buf):
        if len(buf)-at<8:raise LocaleCodecError("Truncated Frostbite block header")
        length,code,low=struct.unpack_from(">IHH",buf,at);at+=8
        size=low|((code&15)<<16)
        if length<1 or length>0x10000 or size<1 or size>0x100000 or at+size>len(buf):
            raise LocaleCodecError("Frostbite block length/bounds invalid")
        block=buf[at:at+size];at+=size
        kind=code&0xfff0
        if kind==0x0070:
            if len(block)!=length:raise LocaleCodecError("Invalid Frostbite raw block length")
            pieces.append(block)
        elif kind==0x0970:
            if lz4 is None:raise LocaleCodecError("Bundled lz4 runtime is required for LZ4 FBMods")
            expanded=lz4.block.decompress(block,uncompressed_size=length)
            if len(expanded)!=length:raise LocaleCodecError("LZ4 output length mismatch")
            pieces.append(expanded)
        else:
            raise LocaleCodecError(f"Unsupported source Frostbite compression type {kind:04X}")
    return b"".join(pieces)


def compress_frostbite(buf: bytes) -> bytes:
    """Native NFS16-compatible LZ4 blocks; raw fallback when incompressible."""
    if not buf:raise LocaleCodecError("Cannot compress empty binary")
    if lz4 is None:raise LocaleCodecError("Bundled lz4 runtime is required")
    result=bytearray()
    for offset in range(0,len(buf),0x10000):
        block=buf[offset:offset+0x10000]
        compressed=lz4.block.compress(block,store_size=False)
        if len(compressed)>=len(block):
            compressed=block
            code=0x0070
        else:
            code=0x0970
        size=len(compressed)
        if size>0xfffff:raise LocaleCodecError("Frame size too large")
        result+=struct.pack(">IHH",len(block),code|((size>>16)&15),size&65535)
        result+=compressed
    output=bytes(result)
    if decompress_frostbite(output)!=buf:
        raise LocaleCodecError("Compressor roundtrip failed")
    return output


def read_histogram(blob: bytes) -> list[int]:
    if len(blob)<12 or len(blob)%2:raise LocaleCodecError("Malformed NFS16 histogram chunk")
    magic,size,offset=struct.unpack_from("<III",blob)
    if magic!=0x39001 or size!=len(blob)-8 or offset>1000000:
        raise LocaleCodecError("NFS16 histogram magic/size mismatch")
    n=(len(blob)-12)//2
    return list(struct.unpack_from("<"+str(n)+"H",blob,12))


def read_strings(bin_data:bytes,hist_data:bytes) -> dict[str,str]:
    hist=read_histogram(hist_data)
    if len(bin_data)<148:raise LocaleCodecError("NFS16 strings binary too small")
    magic,size,count,index_at,strings_at=struct.unpack_from("<IIIII",bin_data,0)
    if magic!=0x39000:
        raise LocaleCodecError("NFS16 string chunk magic invalid")
    # Several legacy NFS16 mods incorrectly leave the file-size header set to
    # the hash-table boundary (Handling Overhaul 2.0 is an actual example).
    # Flammenwerfer ignores this value and validates the index/payload bounds.
    # Permit the malformed header only when the entire string index decodes.
    # Older mods may drop an ID yet retain the old string-index capacity.
    # The signed source count remains authoritative; allow up to 256 bytes of
    # aligned unused index slots but never an overlap or out-of-bounds table.
    slack=strings_at-(index_at+count*8)
    if count>300000 or index_at<20 or slack<0 or slack>256 or slack%8:
        raise LocaleCodecError("Invalid string index location/count")
    if strings_at+8>len(bin_data):
        raise LocaleCodecError("String blob offset out of range")
    result={}
    for n in range(count):
        sid,offset=struct.unpack_from("<II",bin_data,index_at+8+n*8)
        if sid in result:raise LocaleCodecError("Duplicated string ID in game chunk")
        start=strings_at+8+offset
        if start>=len(bin_data):raise LocaleCodecError("String value offset out of range")
        end=bin_data.find(b"\0",start)
        if end<0:raise LocaleCodecError("Unterminated histogram string")
        data=bin_data[start:end]
        chars=[]
        i=0
        while i<len(data):
            current=data[i]
            if current<128:chars.append(chr(current))
            else:
                if current>=len(hist):raise LocaleCodecError("Missing histogram prefix")
                value=hist[current]
                if value>=128:
                    chars.append(chr(value))
                else:
                    i+=1
                    if i>=len(data) or data[i]<128:
                        raise LocaleCodecError("Invalid histogram shift")
                    ix=(data[i]-128)+(value<<7)
                    if ix>=len(hist):raise LocaleCodecError("Missing shifted histogram character")
                    chars.append(chr(hist[ix]))
            i+=1
        result[f"{sid:08X}"]="".join(chars)
    return result


def write_locale(strings:dict[str,str],section:str="en_us")->tuple[bytes,bytes]:
    """Produce valid histogram + string table with full Unicode-BMP roundtrip.

    Reserve first 128 histogram entries for ASCII identities. Prefix bytes at
    [128:255] contain shift pointers (2,3,...), mapping 128 Unicode characters
    per prefix starting at histogram index 256. This is compatible with native
    game/Flammenwerfer NFS16 shifted-histogram decoding.
    """
    if not strings:raise LocaleCodecError("Refusing empty NFS16 translation chunk")
    cp=set()
    for sid,value in strings.items():
        if len(sid)!=8 or any(c not in "0123456789ABCDEF" for c in sid):
            raise LocaleCodecError("String IDs must be eight uppercase hex digits")
        if "\0" in value or any(ord(c)>0xFFFF for c in value):
            raise LocaleCodecError("NFS16 cannot encode NUL or non-BMP characters")
        cp.update(ord(c) for c in value if ord(c)>=128)
    nonascii=sorted(cp)
    groups=(len(nonascii)+127)//128
    if groups>126:raise LocaleCodecError("Too many distinct unicode glyphs")
    hist=list(range(128))+list(range(2,2+groups))
    hist += [0]*(256-len(hist))
    hist += nonascii
    if len(nonascii)%128:
        hist += [0]*(128-len(nonascii)%128)
    if len(hist)<256:
        raise LocaleCodecError("Bad histogram layout")
    lookup={v:i for i,v in enumerate(nonascii)}
    histogram=bytearray(struct.pack("<III",0x39001,4+len(hist)*2,256+len(nonascii)))
    histogram+=struct.pack("<"+str(len(hist))+"H",*hist)
    index_offset=0x8c
    string_offset=index_offset+len(strings)*8
    header=bytearray(struct.pack("<IIIII",0x39000,0,len(strings),index_offset,string_offset))
    header+=section.encode("ascii")+b"\0"
    if len(header)>index_offset+8:
        raise LocaleCodecError("Header overlaps hash table")
    header+=b"\0"*(index_offset+8-len(header))
    body=bytearray(); pairs=bytearray()
    for sid in sorted(strings,key=lambda s:int(s,16)):
        value=strings[sid]
        pairs+=struct.pack("<II",int(sid,16),len(body))
        for ch in value:
            n=ord(ch)
            if n<128:body.append(n)
            else:
                ix=lookup[n]
                prefix=128+ix//128
                second=128+ix%128
                body+=bytes((prefix,second))
        body.append(0)
    result=header+pairs+body
    struct.pack_into("<I",result,4,len(result)-8)
    out_hist,out_bin=bytes(histogram),bytes(result)
    decoded=read_strings(out_bin,out_hist)
    if decoded!=strings:raise LocaleCodecError("NFS16 merged strings roundtrip mismatch")
    return out_bin,out_hist
