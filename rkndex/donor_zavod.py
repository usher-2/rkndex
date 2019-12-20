#!/usr/bin/env python3
#
# Fetching data from Zavod donor.
#

import logging
import os
import re
import time
import zipfile

import prometheus_client as prom
import requests

from rkndex.util import save_url, file_sha256
from rkndex.const import DUMP_ZIP, DUMP_XML, DUMP_SIG, GITAR_USER_AGENT

GITAR_ZAVOD_PAGE_SIZE = prom.Gauge('gitar_zavod_page_size', 'Number of files on zavod page')

class DonorZavod(object):
    name = 'zavod'
    def __init__(self, sqlite_db, dir_url):
        self.db = sqlite_db
        self.create_table()
        self.dir_url = dir_url
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': GITAR_USER_AGENT})

    def create_table(self):
        self.db.execute('''CREATE TABLE IF NOT EXISTS zavod (
            zip_fname   TEXT UNIQUE NOT NULL,
            zip_size    INTEGER NOT NULL,
            fetched     INTEGER NOT NULL,
            xml_sha256  BLOB,
            last_seen   INTEGER NOT NULL)''')

    regex = re.compile(r'<a href="((?:registry-|register_)[-0-9_]+\.zip)">\1</a> +[^ ]+ [^ ]+ +(\d+)\r', re.MULTILINE)
    def list_handles(self, limit):
        now = int(time.time())
        self.db.execute('BEGIN EXCLUSIVE TRANSACTION')
        with self.db:
            r = self.s.get(self.dir_url)
            r.raise_for_status()
            page = self.regex.findall(r.text)
            GITAR_ZAVOD_PAGE_SIZE.set(len(page))
            for zip_fname, zip_size in page:
                # ON CONFLICT .. DO UPDATE needs sqlite3.sqlite_version > 3.24.0, but ubuntu:18.04 has 3.22.0
                self.db.execute('''INSERT OR IGNORE INTO zavod (zip_fname, zip_size, fetched, last_seen)
                    VALUES (?, ?, 0, ?)''',
                    (zip_fname, int(zip_size), now))
                self.db.execute('UPDATE zavod SET last_seen = ? WHERE zip_fname = ?',
                    (now, zip_fname))
            self.db.execute('DELETE FROM zavod WHERE last_seen < ?', (now - 86400,)) # maintenance
            it = self.db.execute('''SELECT zip_fname, zip_size FROM zavod
                    WHERE NOT fetched OR xml_sha256 IS NOT NULL AND xml_sha256 NOT IN (
                        SELECT xml_sha256 FROM log) LIMIT ?''', (limit,))
            return list(it)

    def fetch_xml_and_sig(self, tmpdir, handle):
        zip_fname, zip_size = handle
        zip_path = os.path.join(tmpdir, DUMP_ZIP)
        save_url(zip_path, self.s, '{}/{}'.format(self.dir_url, zip_fname))
        logging.info('%s: got %s. %d bytes', self.name, zip_fname, os.path.getsize(zip_path))
        if os.path.getsize(zip_path) != zip_size:
            raise RuntimeError('Truncated zip', zip_fname, zip_size, os.path.getsize(zip_path))
        with zipfile.ZipFile(zip_path, 'r') as zfd:
            zfd.extract(DUMP_SIG, path=tmpdir)
            zfd.extract(DUMP_XML, path=tmpdir)
            xml_binsha256 = file_sha256(os.path.join(tmpdir, DUMP_XML)) # calculated twice...
        self.db.execute('BEGIN EXCLUSIVE TRANSACTION')
        with self.db:
            self.db.execute('UPDATE zavod SET fetched = 1, xml_sha256 = ? WHERE zip_fname = ?',
                (xml_binsha256, zip_fname))
        return xml_binsha256

    @staticmethod
    def sanity_cb(handle, xmlmeta, sigmeta, ut, utu):
        pass
