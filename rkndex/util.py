#!/usr/bin/env python3
#
# Like `rkndex.const', but `rkndex.util'.
#

import functools
import hashlib
import itertools
import time

def save_url(path, session, url):
    r = session.get(url, stream=True)
    r.raise_for_status()
    with open(path, 'wb') as fd:
        for blob in iter(functools.partial(r.raw.read, 65536), b''):
            fd.write(blob)

def file_sha256(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as fd:
        for blob in iter(functools.partial(fd.read, 65536), b''):
            sha.update(blob)
    return sha.digest()

def schedule_every(ops, period):
    op_cycle = itertools.cycle(list(ops))
    while True:
        t = time.monotonic()
        yield next(op_cycle)
        t = time.monotonic() - t
        if t < period:
            time.sleep(period - t)
