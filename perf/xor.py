#!/usr/bin/env python3
#
# Nano-benchmark to save a bit of CPU xoring SHA1 hashes.

import time
import sys
import os
blobs = [os.urandom(20) for i in range(90000)]

def f1(): # 180 ms
    r = bytearray(20)
    for xml_sha1 in blobs:
        for n in range(20):
            r[n] ^= xml_sha1[n]
    return bytes(r)

def f2(): # 20 ms
    r = 0
    for xml_sha1 in blobs:
        r ^= int.from_bytes(xml_sha1, sys.byteorder)
    return r.to_bytes(20, sys.byteorder)

def f3(): # 15 ms
    r = 0
    byteorder, from_bytes = sys.byteorder, int.from_bytes
    for xml_sha1 in blobs:
        r ^= from_bytes(xml_sha1, byteorder)
    return r.to_bytes(20, byteorder)

assert f1() == f2() == f3()

for f in (f1, f2, f3):
    a = time.monotonic()
    f()
    print(time.monotonic() - a)
