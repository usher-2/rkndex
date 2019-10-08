#!/usr/bin/env python3
#
# Module to serialize diff between two dump.xml into compressed xdelta3-based blob and read it back.
#

import struct
import gzip

import xdelta3

import rkndex.iterdiff as iterdiff

CONTENT_PROLOGUE = 0xffffffff
CONTENT_EPILOGUE = 0xfffffffe

CDIFF_HEAD = struct.Struct('<IIII') # magic, content_id, len(old), len(new)
MAGIC_RAW = 0x60ba077e
MAGIC_UGLY = 0xbdc11c1e # force-raw due to bug
MAGIC_XDELTA3 = 0xee358f4e
MAGIC_LIST = {MAGIC_RAW, MAGIC_UGLY, MAGIC_XDELTA3}
assert CDIFF_HEAD.size == 16 # unsigned int is 32bit


def write_content_diff(out, in1, in2):
    content_id_map = {
        iterdiff.PROLOGUE: CONTENT_PROLOGUE,
        iterdiff.EPILOGUE: CONTENT_EPILOGUE,
        CONTENT_PROLOGUE: None, # fail-fast on struct.pack
        CONTENT_EPILOGUE: None, # fail-fast on struct.pack
    }
    # Default compresslevel of 9 is okay as gzip costs nothing compared to XML parsing of source.
    # Note, xdelta from b'' may be still smaller than the original blob.
    with gzip.GzipFile(fileobj=out, mode='wb') as gz:
        for k, v1, v2 in iterdiff.iter_content_diff(in1, in2):
            k = content_id_map.get(k, k)
            try:
                delta = xdelta3.encode(v1, v2)
                # FIXME: workaround for bug https://github.com/samuelcolvin/xdelta3-python/issues/2
                try:
                    good = xdelta3.decode(v1, delta) == v2 # Epic Fail if happens.
                except xdelta3.XDeltaError:
                    good = False
                magic = MAGIC_XDELTA3 if good else MAGIC_UGLY
            except xdelta3.NoDeltaFound:
                magic, delta = MAGIC_RAW, None
            blob = delta if magic == MAGIC_XDELTA3 else v2
            gz.write(CDIFF_HEAD.pack(magic, k, len(v1), len(blob)))
            gz.write(v1)
            gz.write(blob)

def read_content_diff(fd):
    with gzip.GzipFile(fileobj=fd, mode='rb') as gz:
        while True:
            head = gz.read(CDIFF_HEAD.size)
            if not head:
                break
            magic, content_id, l1, l2 = CDIFF_HEAD.unpack(head)
            v1 = gz.read(l1)
            v2 = gz.read(l2)
            if magic not in MAGIC_LIST or len(v1) != l1 or len(v2) != l2:
                raise RuntimeError('Bad format', magic, content_id, l1, len(v1), l2, len(v2))
            if magic == MAGIC_XDELTA3:
                v2 = xdelta3.decode(v1, v2)
            yield content_id, v1, v2

def index_content_diff(fd, needle):
    # There is no significant performance difference between bare GzipFile.seek
    # and GzipFile.read + xdelta3.decode.
    for k, v1, v2 in read_content_diff(fd):
        if k == needle:
            return v1, v2
    raise IndexError('content.id not found', needle)
