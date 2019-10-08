#!/usr/bin/env python3
#
# Module to create diff of two dump.xml files and emit it via iter_content_diff().
#

import itertools
import functools
import xml.parsers.expat

PROLOGUE = float('-inf')
EPILOGUE = float('+inf')

# Make non-seekable stream buffered to simulate seek() reading from buffer.
class BufferingPipe(object):
    def __init__(self, fd):
        self.off = 0
        self.buf = b''
        self.blist = []
        self.fd = fd
    def read(self, nbytes):
        blob = self.fd.read(nbytes)
        self.blist.append(blob)
        return blob
    def localize_off(self, start, end):
        if self.blist:
            self.buf += b''.join(self.blist)
            self.blist.clear()
        locstart = start - self.off
        locend = end - self.off
        if not (0 <= locstart <= locend <= len(self.buf)):
            raise RuntimeError('Out of range', start, end, self.off, len(self.buf))
        return locstart, locend
    def getbuf(self, start, end):
        locstart, locend = self.localize_off(start, end)
        return self.buf[locstart:locend]
    def drop_to(self, end):
        _, locend = self.localize_off(self.off, end)
        if locend:
            self.off += locend
            self.buf = self.buf[locend:]

# Read dump.xml and slice it into PROLOGUE, <content/> and EPILOGUE.
class ContentSlicer(object):
    def __init__(self, infd):
        self.pipe = BufferingPipe(infd)
        self.acc = {} # PROLOGUE | content.id | EPILOGUE -> blob
        self.acc_last_byte = 0
        self.p = xml.parsers.expat.ParserCreate()
        self.p.StartElementHandler = self.first_content
        self.cur_id = PROLOGUE
        self.cur_start = 0
        self.flush_on_open = False
    def first_content(self, name, attrs):
        if name == 'content':
            self.accflush()
            self.cur_id = int(attrs['id'])
            self.cur_start = self.p.CurrentByteIndex
            self.p.StartElementHandler = self.next_content
            self.p.EndElementHandler = self.close_tag
    def accflush(self):
        self.acc[self.cur_id] = self.pipe.getbuf(self.cur_start, self.p.CurrentByteIndex)
        self.acc_last_byte = self.p.CurrentByteIndex
    def next_content(self, name, attrs):
        if self.flush_on_open:
            assert name == 'content', name
            self.accflush()
            self.flush_on_open = False
        if name == 'content':
            self.cur_id = int(attrs['id'])
            self.cur_start = self.p.CurrentByteIndex
    def close_tag(self, name):
        if name == 'content':
            self.flush_on_open = True # possible whitespace is glued to <content> tree
        elif name == 'reg:register':
            assert self.flush_on_open
            self.accflush()
            self.cur_id = EPILOGUE
            self.cur_start = self.p.CurrentByteIndex
    def pump(self, nbytes):
        blob = self.pipe.read(nbytes)
        self.p.Parse(blob)
        self.pipe.drop_to(self.acc_last_byte)
        return len(blob)
    def close(self): # NB: Parse() fails on empty input
        is_final = True
        self.p.Parse(b'', is_final) # Parse() takes no keyword arguments
        self.accflush()
        self.pipe.drop_to(self.acc_last_byte)
        assert self.acc_last_byte == self.p.CurrentByteIndex == self.pipe.off

# Helper for iter_content_diff()
def pop_common_keys(dict1, dict2):
    l = []
    for k in sorted(dict1.keys() & dict2.keys()):
        v1, v2 = dict1.pop(k), dict2.pop(k)
        if v1 != v2:
            l.append((k, v1, v2))
    return l

# Iterate over differing PROLOGUE, <content/> and EPILOGUE dump.xml bytes from ContentSlicer.
def iter_content_diff(in1, in2):
    cs1 = ContentSlicer(in1)
    cs2 = ContentSlicer(in2)
    for _ in itertools.zip_longest(
        iter(functools.partial(cs1.pump, 65536), 0),
        iter(functools.partial(cs2.pump, 65536), 0)
    ):
        for k, v1 ,v2 in pop_common_keys(cs1.acc, cs2.acc):
            yield k, v1, v2
    cs1.close()
    cs2.close()
    for k, v1, v2 in pop_common_keys(cs1.acc, cs2.acc):
        yield k, v1, v2
    for k in sorted(cs1.acc.keys()):
        yield k, cs1.acc.pop(k), b''
    for k in sorted(cs2.acc.keys()):
        yield k, b'', cs2.acc.pop(k)
