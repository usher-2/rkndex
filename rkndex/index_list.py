#!/usr/bin/env python3
#
# Module to ingest git log into PostgreSQL database.
#

import datetime
import random
from contextlib import closing

import requests

from rkndex.const import RKN_EPOCH, ZERO_BINSHA1
from rkndex.pg import PGCopyFrom

def iter_known_dumps_with_duplicates(giweb):
    with requests.Session() as sess:
        since = 0
        while True:
            page_size = random.randint(4096 - 64, 4096 + 64)
            resp = requests.get('{}/since_update_time/{:d}/{:d}'.format(giweb, since, page_size))
            resp.raise_for_status()
            resp = resp.json()['data']
            for el in resp:
                yield el
                since = max(since, el['update_time'])
            if len(resp) < page_size:
                break

def main_list_valwrap(v):
    if isinstance(v, str):
        return '\\\\x' + v
    elif v is None:
        return '\\N'
    elif RKN_EPOCH < v < 0x7fffffff: # let's introduce 2038-problem here
        return datetime.datetime.utcfromtimestamp(v).isoformat()
    else:
        raise ValueError(v)

def main_list(pgconn, giweb):
    # PGCopyFrom reduces runtime from 20s to 7s compared to row-by-row INSERT
    keys = ('update_time', 'update_time_urgently', 'signing_time', 'xml_mtime', 'sig_mtime',
            'xml_md5', 'sig_md5', 'xml_sha1', 'sig_sha1',
            'xml_sha256', 'sig_sha256', 'xml_sha512', 'sig_sha512')
    with pgconn, pgconn.cursor() as c:
        # NB: there is no `INCLUDING ALL` as the known_dumps actually has duplicates
        c.execute('CREATE TEMPORARY TABLE tmp (LIKE known_dump) ON COMMIT DROP')
        with closing(PGCopyFrom(pgconn, 'tmp')) as wbuf:
            for row in iter_known_dumps_with_duplicates(giweb):
                wbuf.write((
                    '\t'.join(main_list_valwrap(row[k]) for k in keys)
                    + '\n'
                ).encode('ascii'))
        c.execute('''INSERT INTO known_dump TABLE tmp
            ON CONFLICT ON CONSTRAINT known_dump_xml_sha1_sig_sha1_key DO NOTHING''')
        if c.rowcount > 0:
            refresh_known_diff(c)

def refresh_known_diff(cursor):
    # TODO: `known_diff` may be real MATERIALIZED VIEW, but I have no time to write relevant code.
    cursor.execute('''CREATE TEMPORARY TABLE known_xml ON COMMIT DROP AS
    SELECT this_no AS this, this_no + 1 AS next, update_time, xml_sha1
    FROM (
        SELECT row_number() OVER () this_no, update_time, xml_sha1 FROM known_dump
        ORDER BY update_time, xml_sha1, sig_sha1
    ) t;
    INSERT INTO known_xml VALUES (0, 1, %s, %s);
    CREATE UNIQUE INDEX ON known_xml (this);
    CREATE UNIQUE INDEX ON known_xml (next);
    ANALYZE known_xml;
    CREATE TABLE known_diff_new (LIKE known_diff INCLUDING ALL);
    INSERT INTO known_diff_new
    SELECT
        this.update_time AS update_time_from,
        next.update_time AS update_time_to,
        this.xml_sha1 AS xml_sha1_from,
        next.xml_sha1 AS xml_sha1_to
    FROM known_xml AS this JOIN known_xml AS next ON (this.next = next.this);
    ALTER TABLE known_diff RENAME TO known_diff_old;
    ALTER TABLE known_diff_new RENAME TO known_diff;
    DROP TABLE known_diff_old;
    ''', (datetime.datetime.utcfromtimestamp(RKN_EPOCH), ZERO_BINSHA1))
