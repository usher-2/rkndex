#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from subprocess import Popen, PIPE # PIPE is not used but it's handy to import it from here
from contextlib import contextmanager

@contextmanager
def ScopedPopen(*args, **kwargs):
    proc = Popen(*args, **kwargs)
    try:
        yield proc
    finally:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass
