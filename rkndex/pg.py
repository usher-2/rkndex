#!/usr/bin/env python3
#
# PostgreSQL toolkit.
#

import datetime
import numbers
from io import BytesIO

from rkndex.const import RKN_EPOCH

class PGCopyFrom(object):
    # Write buffer for COPY command to be able to COPY to several
    # output tables over single postgres session.
    def __init__(self, pgconn, table, wbufsize=2097152, **kwargs):
        # default chunk size is taken as approx. cwnd between some VMs somewhere
        self.__pgconn = pgconn
        self.__table = table
        self.__wbufsize = wbufsize
        self.__kwargs = kwargs
        self.__buf = BytesIO()
    def write(self, line):
        assert len(line) == 0 or line[-1] == 0x0a, line
        pos = self.__buf.tell()
        if pos > 0 and pos + len(line) > self.__wbufsize:
            self.flush()
        self.__buf.write(line)
    def flush(self):
        self.__buf.seek(0)
        with self.__pgconn.cursor() as c:
            c.copy_from(self.__buf, self.__table, **self.__kwargs)
        self.__buf.seek(0)
        self.__buf.truncate()
    def close(self):
        self.flush()
        self.__buf.close()
    @property
    def closed(self):
        return self.__buf.closed

def int_nn(v):
    assert isinstance(v, numbers.Integral)
    return str(v)

def str_nullable(v):
    if v is None:
        return '\\N'
    return str_nn(v)

def str_nn(v):
    assert isinstance(v, str), v
    return v.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

def datetime_nn(v):
    assert isinstance(v, datetime.datetime), v
    return v.isoformat()

def bool_nn(v):
    assert isinstance(v, bool)
    return 'TRUE' if v else 'FALSE'

def rkn_ts_nn(v):
    assert isinstance(v, numbers.Integral) and RKN_EPOCH <= v <= 0x7fffffff, v
    return datetime.datetime.utcfromtimestamp(v).isoformat()

### #!/usr/bin/env python3
### # -*- coding: utf-8 -*-
### 
### import numbers
### import os
### import re
### from io import BytesIO
### 
### BAD_UTF8_RE = re.compile( # https://stackoverflow.com/questions/18673213/detect-remove-unpaired-surrogate-character-in-python-2-gtk
###     ur'''(?x)            # verbose expression (allows comments)
###     (                    # begin group
###     [\ud800-\udbff]      #   match leading surrogate
###     (?![\udc00-\udfff])  #   but only if not followed by trailing surrogate
###     )                    # end group
###     |                    #  OR
###     (                    # begin group
###     (?<![\ud800-\udbff]) #   if not preceded by leading surrogate
###     [\udc00-\udfff]      #   match trailing surrogate
###     )                    # end group
###     |                    #  OR
###     \u0000
###     ''')
### 
### PG_ARRAY_SPECIAL_RE = re.compile('[\t\x0a\x0b\x0c\x0d {},"\\\\]')
### 
### def pg_quote(s):
###     # The following characters must be preceded by a backslash if they
###     # appear as part of a column value: backslash itself, newline, carriage
###     # return, and the current delimiter character.
###     # -- https://www.postgresql.org/docs/9.6/static/sql-copy.html
###     if isinstance(s, basestring):
###         # postgres requires UTF8, it's also unhappy about
###         # - unpaired surrogates https://www.postgresql.org/message-id/20060526134833.GC27513%40svana.org
###         #   example at 2016-04-01/http_requests.06.tar.lz4 | grep myfiona.co.kr
###         # - \u0000 as in ``DETAIL:  \u0000 cannot be converted to text.``
###         #   example at https://github.com/TheTorProject/ooni-pipeline/issues/65
###         if isinstance(s, str):
###             s = unicode(s, 'utf-8')
###         s = BAD_UTF8_RE.sub(u'\ufffd', s).encode('utf-8')
###         return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
###     elif s is None:
###         return '\\N'
###     elif isinstance(s, bool): # WTF: assert isinstance(True, numbers.Number)! (py2 and py3)
###         return 'TRUE' if s else 'FALSE'
###     elif isinstance(s, numbers.Number):
###         return s
###     elif isinstance(s, list):
###         if all(isinstance(el, basestring) for el in s):
###             escaped = []
###             for el in s:
###                 if PG_ARRAY_SPECIAL_RE.search(el):
###                     escaped.append('"' + el.replace('\\', '\\\\').replace('"', '\\"') + '"') # 8-[ ~ ]
###                 else:
###                     escaped.append(el)
###             return pg_quote('{' + ','.join(escaped) + '}') # yes, once more!
###         elif all(isinstance(el, numbers.Number) for el in s):
###             return '{' + ','.join(map(str, s)) + '}'
###         else:
###             raise RuntimeError('Unable to quote list of unknown type', s)
###     else:
###         raise RuntimeError('Unable to quote unknown type', s)
### 
### def _pg_unquote(s): # is used only in the test
###     if not isinstance(s, basestring):
###         raise RuntimeError('Unable to quote unknown type', s)
###     if s != '\\N':
###         return s.decode('string_escape') # XXX: gone in Python3
###     else:
###         return None
### 
### def pg_binquote(s):
###     assert isinstance(s, str)
###     return '\\\\x' + s.encode('hex')
### 
### def pg_uniquote(s):
###     if isinstance(s, str):
###         s = unicode(s, 'utf-8')
###     assert isinstance(s, unicode)
###     return BAD_UTF8_RE.sub(u'\ufffd', s) # `re` is smart enough to return same object in case of no-op
### 
