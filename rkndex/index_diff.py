#!/usr/bin/env python3
#
# Module to ingest git diffs from web API into PostgreSQL database.
#

import binascii
import datetime
import re
import tempfile
from contextlib import closing

import requests
import psycopg2
import psycopg2.extras
import xml.parsers.expat

from rkndex.const import RKN_EPOCH, ZERO_BINSHA1, BLOCKTYPE_NULL
from rkndex.filediff import read_content_diff, CONTENT_EPILOGUE
from rkndex.pg import PGCopyFrom, bool_nn, datetime_nn, int_nn, str_nn, str_nullable

class DumpParserErr(object):
    __slots__ = ('unknown_attrs', 'unknown_tags', 'duplicate_cdata_tag')
    def __init__(self):
        for key in self.__slots__:
            setattr(self, key, False)

class DumpParser(object):
    def __init__(self, content_cb):
        self.err = DumpParserErr()
        self.content_cb = content_cb
        self.p = xml.parsers.expat.ParserCreate()
        self.p.StartElementHandler = self.open_tag
        self.p.EndElementHandler = self.close_tag
        self.buf = None
        self.tag_ts = None
    register_known_keys = frozenset(('updateTime', 'updateTimeUrgently', 'formatVersion'))
    content_int_keys = frozenset(('id', 'entryType', 'urgencyType'))
    content_str_keys = frozenset(('includeTime', 'ts', 'blockType'))
    content_known_keys = content_int_keys | content_str_keys | frozenset(('hash'))
    content_cdata_tag = frozenset(('url', 'domain', 'ip', 'ipv6', 'ipSubnet', 'ipv6Subnet'))
    decision_str_keys = frozenset(('date', 'number', 'org'))
    def open_tag(self, tag, attr):
        if tag in self.content_cdata_tag:
            self.start_cdata_writer()
            self.tag_ts = attr.get('ts')
            if attr.keys() - {'ts'}:
                self.err.unknown_attrs = True
        elif tag == 'decision':
            for key in self.decision_str_keys:
                self.content['decision_'+key] = attr.get(key)
            if attr.keys() - self.decision_str_keys:
                self.err.unknown_attrs = True
        elif tag == 'content':
            self.content = {
                'id': int(attr['id']),
                'entryType': int(attr['entryType']),
                'urgencyType': None,
                'includeTime': None,
                'ts': None, # content-ts
                'blockType': None,
                'decision_date': None,
                'decision_number': None,
                'decision_org': None,
                'url': {}, # cdata -> tag-ts
                'domain': {},
                'ip': {},
                'ipv6': {},
                'ipSubnet': {},
                'ipv6Subnet': {},
            }
            for tag in self.content_cdata_tag:
                self.content[tag] = {} # cdata -> ts
            value = attr.get('urgencyType')
            self.content['urgencyType'] = int(value) if value is not None else None
            for key in self.content_str_keys:
                self.content[key] = attr.get(key)
            if attr.keys() - self.content_known_keys:
                self.err.unknown_attrs = True
        elif tag == 'reg:register':
            if attr.keys() - self.register_known_keys:
                self.err.unknown_attrs = True
        else:
            self.err.unknown_tags = True
    url_with_path_re = re.compile('[^/:]+://[^/]+/+[^/#]+')
    def close_tag(self, tag):
        if tag in self.content_cdata_tag:
            cdata = self.pop_cdata()
            dest = self.content[tag]
            if cdata in dest:
                self.err.duplicate_cdata_tag = True
            dest[cdata] = self.tag_ts
            self.tag_ts = None
        elif tag == 'content':
            c, self.content = self.content, None
            c['has_domain'] = len(c['domain']) > 0
            c['has_domain_mask'] = any(_.startswith('*.') for _ in c['domain'].keys())
            c['has_url'] = len(c['url']) > 0
            c['has_http'] = any(_.startswith('http:') for _ in c['url'].keys())
            c['has_https'] = any(_.startswith('https:') for _ in c['url'].keys())
            c['has_path'] = any(self.url_with_path_re.match(_) for _ in c['url'].keys())
            c['has_ip'] = sum(len(c[k]) for k in ('ip', 'ipv6', 'ipSubnet', 'ipv6Subnet')) > 0
            if c['blockType'] == BLOCKTYPE_NULL:
                raise ValueError('NULL placeolder conflict', c['blockType'])
            if c['blockType'] is None:
                c['blockType'] = BLOCKTYPE_NULL # NULL-able column is bad for UNIQUE
            self.content_cb(c)
    def start_cdata_writer(self):
        assert self.buf is None
        self.buf = ''
        self.p.CharacterDataHandler = self.on_char_data
    def pop_cdata(self):
        self.p.CharacterDataHandler = None
        ret = self.buf
        self.buf = None
        return ret
    def on_char_data(self, data):
        self.buf += data
    def parse(self, blob, is_final=False):
        self.p.Parse(blob, is_final)

def make_content_iter_from_xdelta(infd):
    acc1, acc2 = {}, {}
    p1 = DumpParser(lambda content: acc1.__setitem__(content['id'], content))
    p2 = DumpParser(lambda content: acc2.__setitem__(content['id'], content))
    def iter_content_from_xdelta():
        seen_epilogue = False
        for content_id, v1, v2 in read_content_diff(infd):
            if content_id == CONTENT_EPILOGUE:
                seen_epilogue = True
            p1.parse(v1)
            p2.parse(v2)
            # SEEMS, xml.parsers.expat does not buffer Parse data and content_cb()
            # is already called when parse() returns... But let's assume it does not.
            for k in acc1.keys() & acc2.keys():
                yield k, acc1.pop(k), acc2.pop(k)
        blob = b'' if seen_epilogue else b'</reg:register>'
        p1.parse(blob, is_final=True)
        p2.parse(blob, is_final=True)
        for k in acc1.keys() & acc2.keys():
            yield k, acc1.pop(k), acc2.pop(k)
        for k in list(acc1.keys()):
            yield k, acc1.pop(k), None
        for k in list(acc2.keys()):
            yield k, None, acc2.pop(k)
    return iter_content_from_xdelta, p1.err, p2.err

def fetch_url(outfd, url):
    with closing(requests.get(url, stream=True)) as r:
        r.raise_for_status()
        for blob in r.iter_content(chunk_size=65536):
            outfd.write(blob)
        outfd.flush()

CONTENT_PREKEY = ('id', 'blockType', 'has_domain', 'has_domain_mask', 'has_url',
                  'has_http', 'has_https', 'has_path', 'has_ip')

def del_commons(c1, c2):
    if c1 is None or c2 is None or any(c1[k] != c2[k] for k in CONTENT_PREKEY):
        return
    # that's the same `id` with same blockType properties
    for tag in DumpParser.content_cdata_tag:
        for cdata, tag_ts in c1[tag].items() & c2[tag].items():
            del c1[tag][cdata], c2[tag][cdata]

def fetch_diff_from_xdelta(giweb, from_sha1: str, to_sha1: str):
    diff = [] # (old, new)
    with tempfile.TemporaryFile() as tmp:
        # It's possible to parse the xdelta on-the-fly, but read_content_diff() already
        # expects `fd` as input stream, so either inversion of control or tmpfile is needed
        fetch_url(tmp, '{}/xdelta/{}/{}'.format(giweb, from_sha1, to_sha1))
        tmp.seek(0)
        iter_content_from_xdelta, err_from, err_to = make_content_iter_from_xdelta(tmp)
        for content_id, c1, c2 in iter_content_from_xdelta():
            assert all(_ is None or _['id'] == content_id for _ in (c1, c2))
            del_commons(c1, c2)
            diff.append((c1, c2))
        # err_from and err_to are now settled available
    return diff, err_from, err_to

def select_update_time(c, from_binsha1: bytes, to_binsha1: bytes):
    c.execute('''(SELECT xml_sha1, update_time FROM known_dump
                  WHERE xml_sha1 IN (%s, %s)
                  LIMIT 2)
                 UNION
                 (SELECT xml_sha1, update_time
                  FROM (VALUES (%s, %s)) AS t (xml_sha1, update_time)
                  WHERE xml_sha1 IN (%s, %s))''',
              (from_binsha1, to_binsha1,
               ZERO_BINSHA1, datetime.datetime.utcfromtimestamp(RKN_EPOCH),
               from_binsha1, to_binsha1))
    update_time = {bytes(key): value for key, value in c}
    if len(update_time) != 2:
        raise RuntimeError('Unknown xml_sha1', from_binsha1, to_binsha1, list(update_time.keys()))
    assert update_time[from_binsha1] < update_time[to_binsha1]
    return update_time[from_binsha1], update_time[to_binsha1]

def main_diff(pgconn, giweb, from_sha1: str, to_sha1: str):
    from_binsha1, to_binsha1 = binascii.unhexlify(from_sha1), binascii.unhexlify(to_sha1)
    with pgconn:
        ingest_diff(pgconn, giweb, from_binsha1, to_binsha1)

def main_alldiff(pgconn, giweb):
    from_to = [object()]
    while len(from_to):
        with pgconn, pgconn.cursor() as c:
            c.execute('''SELECT * FROM (
                            SELECT xml_sha1_from, xml_sha1_to FROM known_diff
                            EXCEPT
                            SELECT xml_sha1_from, xml_sha1_to FROM ingested_diff
                         ) t
                         ORDER BY random()
                         LIMIT 100''')
            from_to = list(c)
        for from_binsha1, to_binsha1 in from_to:
            from_binsha1, to_binsha1 = bytes(from_binsha1), bytes(to_binsha1) # memory() otherwise
            with pgconn:
                ingest_diff(pgconn, giweb, from_binsha1, to_binsha1)

def ingest_diff(pgconn, giweb, from_binsha1: bytes, to_binsha1: bytes):
    assert len(from_binsha1) == len(to_binsha1) == 20
    from_sha1, to_sha1 = (binascii.hexlify(_).decode('ascii') for _ in (from_binsha1, to_binsha1))
    with pgconn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
        update_time_from, update_time_to = select_update_time(c, from_binsha1, to_binsha1)
        diff, err_from, err_to = fetch_diff_from_xdelta(giweb, from_sha1, to_sha1)
        with closing(DbWriter(pgconn, update_time_from, update_time_to)) as w:
            for c1, c2 in diff:
                if c1 is None:
                    w.add_content(c2)
                elif c2 is None:
                    w.del_content(c1)
                elif any(c1[k] != c2[k] for k in CONTENT_PREKEY):
                    assert c1['id'] == c2['id'] # blockType and has_* are VERY different
                    w.del_content(c1)
                    w.add_content(c2)
                else: # That's just `ts` difference as per `del_commons()', but it may be zerodiff!
                    w.upd_content(c1, c2)
                for content in (c1, c2):
                    if content is not None:
                        w.upd_meta(content)
        has_exc = False
        c.execute('INSERT INTO ingested_diff VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (update_time_from, update_time_to, from_binsha1, to_binsha1,
             has_exc,
             err_from.unknown_attrs, err_to.unknown_attrs,
             err_from.unknown_tags, err_to.unknown_tags,
             err_from.duplicate_cdata_tag, err_to.duplicate_cdata_tag))

class DbWriter(object):
    def __init__(self, pgconn, update_time_from, update_time_to):
        self.update_time_from = update_time_from
        self.update_time_to = update_time_to
        self.content = PGCopyFrom(pgconn, 'content')
        self.zerodiff = PGCopyFrom(pgconn, 'content_zerodiff')
    def add_content(self, c):
        self.write_content(c, is_deletion=False)
    def del_content(self, c):
        self.write_content(c, is_deletion=True)
    def upd_content(self, c1, c2):
        self.write_content(c1, is_deletion=True)
        self.write_content(c2, is_deletion=False)
        # FIXME: maybe write zerodiff
    def write_content(self, c, is_deletion):
        head = tuple(c[_] for _ in CONTENT_PREKEY) + tuple((
            is_deletion, self.update_time_from, self.update_time_to,
            c['includeTime'], c['ts']))
        for tag in ('url', 'domain'):
            for cdata, tag_ts in c[tag].items():
                tail = (tag_ts, tag, cdata, None)
                self.write_content_row(head + tail)
        for tag in ('ip', 'ipv6', 'ipSubnet', 'ipv6Subnet'):
            for cdata, tag_ts in c[tag].items():
                ip_inet = cdata if len(cdata) else None
                tail = (tag_ts, tag, cdata, ip_inet)
                self.write_content_row(head + tail)
    def write_content_row(self, row):
        types = (
            int_nn, # content_id
            str_nn, # block_type
            bool_nn, bool_nn, bool_nn, bool_nn, bool_nn, bool_nn, bool_nn, # has_*
            bool_nn, # is_deletion
            datetime_nn, datetime_nn, # update_time_from, update_time_to
            str_nullable, str_nullable, # dump.xml gives str, PostgreSQL gets str
            str_nullable, # tag_ts, also str-in-str-out
            str_nn, str_nn, # tag, value
            str_nullable # ip_inet
        )
        assert len(types) == len(row)
        self.content.write(('\t'.join(fn(v) for fn, v in zip(types, row)) + '\n').encode('utf-8'))
    def upd_meta(self, c):
        pass
        # FIXME: must be implemented
    def close(self):
        self.content.close()
        self.zerodiff.close()

### def update_content(pgconn, content_id, update_time_from, update_time_to, c1, c2, cdb, meta):
###     cdata_db_col = 'url'
###     db_key = ('content_id', 'block_type', 'has_domain', 'has_domain_mask', 'has_url',
###               'has_http', 'has_https', 'has_path', 'has_ip', cdata_db_col)
###     db_value = ('update_time_pre', 'update_time_first',
###                 'update_time_last', 'update_time_post',
###                 'tag_ts_min', 'tag_ts_max', 'tag_ts_seen_null',
###                 'content_ts_min', 'content_ts_max', 'content_ts_seen_null',
###                 'include_time_min', 'include_time_max', 'include_time_seen_null')
###     known_db = {(row[_] for _ in db_key): {_: row[_] for _ in db_value}
###                 for row in cdb
###                 if row[cdata_db_col] is not None}
###     cdata_obj_key = 'url'
###     assert all(content is None or content['id'] == content_id for content in (c1, c2))
###     # <content/>-specific part of the primary key
###     k1, k2 = (tuple((content or {}).get(_) for _ in CONTENT_PREKEY) for content in (c1, c2))
###     # cdata -> ts
###     d1, d2 = (_[cdata_obj_key] if _ is not None else {} for _ in (c1, c2))
###     if k1 == k2:
###         for cdata in (d1.keys() | d2.keys()):
###             if cdata not in d1 and cdata in d2: # addition
###             elif cdata in d1 and cdata not in d2: # removal
###             elif cdata in d1 and cdata in d2: # ts change
###             else:
###                 assert False
###     else: # all `d1` ends here and `d2` starts as block_type and related are different
###         for cdata in (d1.keys() | d2.keys()):
###             if cdata not in d1 and cdata in d2: # addition
###             elif cdata in d1 and cdata not in d2: # removal
###             elif cdata in d1 and cdata in d2: # ts change
###             else:
###                 assert False
### 
### 
###     
