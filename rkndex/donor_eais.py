#!/usr/bin/env python3
#
# Fetching data from EAIS donor.
#

import binascii
import logging
import os
import random
import time
import zipfile

import requests

from rkndex.util import save_url
from rkndex.const import DUMP_ZIP, DUMP_XML, DUMP_SIG, GITAR_USER_AGENT, RKN_EPOCH

class DonorEais(object):
    name = 'eais'
    def __init__(self, sqlite_db, fqdn, token, write_token=None):
        self.db = sqlite_db
        self.create_table()
        self.fqdn = fqdn
        self.s = requests.Session()
        self.s.headers.update({
            'Authorization': 'Bearer {:s}'.format(token),
            'User-Agent': GITAR_USER_AGENT,
        })
        self.write_token = write_token

    def create_table(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS eais_fullsync_ts (time INTEGER NOT NULL)')
        if next(self.db.execute('SELECT 1 FROM eais_fullsync_ts LIMIT 1'), None) is None:
            self.db.execute('INSERT INTO eais_fullsync_ts VALUES (0)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS eais (
            update_time             INTEGER NOT NULL,
            update_time_urgently    INTEGER,
            xml_size                INTEGER,
            xml_mtime               INTEGER,
            xml_sha256              BLOB UNIQUE NOT NULL)''')

    def needs_xml_sha256(self, xml_binsha256):
        assert self._fullsync_ts() > 0 and len(xml_binsha256) == 32
        it = self.db.execute('SELECT COUNT(*) FROM eais WHERE xml_sha256 = ?', (xml_binsha256,))
        return next(it)[0] == 0

    def upload(self, zip_path):
        assert self.write_token is not None
        with open(zip_path, 'rb') as fd:
            r = self.s.post('https://{}/upload'.format(self.fqdn),
                headers={'Authorization': 'Bearer {:s}'.format(self.write_token)},
                files={'file': ('dump.zip', fd)})
            r.raise_for_status()

    def list_handles(self, limit):
        self.db.execute('BEGIN EXCLUSIVE TRANSACTION')
        with self.db:
            day_size = random.randint(86400 - 3600, 86400 + 3600)
            now = int(time.time())
            if self._fullsync_ts() + day_size < now:
                self._list_full()
                self.db.execute('UPDATE eais_fullsync_ts SET time = ?', (now, ))
            else:
                self._list_since(self.max_update_time())
            it = self.db.execute('''SELECT update_time, update_time_urgently, xml_size, xml_mtime, xml_sha256
                FROM eais WHERE xml_sha256 NOT IN (SELECT xml_sha256 FROM log) LIMIT ?''', (limit,))
            ret = list(it)
        return ret

    def max_update_time(self):
        return next(self.db.execute('SELECT COALESCE(MAX(update_time), 0) FROM eais'))[0]

    def _fullsync_ts(self):
        return next(self.db.execute('SELECT time FROM eais_fullsync_ts'))[0]

    def _list_full(self):
        self.db.execute('DELETE FROM eais') # resync from scratch
        since, maybe_more = 0, True
        while maybe_more:
            since, maybe_more = self._list_since(since)

    def _list_since(self, since):
        # 4096 entries to get ~ 1 MiB of metadata per round-trip.  Number of
        # entries is randomized to avoid UNLIKELY case when two dumps have the same
        # timestamp and the timestamp falls at the boundary of the "page".
        page_size = random.randint(4096 - 64, 4096 + 64)
        r = self.s.get('https://{}/start?ts={:d}&c={:d}'.format(self.fqdn, since, page_size))
        r.raise_for_status()
        page = r.json()
        for el in page:
            xml_binsha256 = binascii.unhexlify(el['id'])
            # `ts=` arg should be an index on `ut` field of response
            # see README.md for description of the keys
            self.db.execute('INSERT OR IGNORE INTO eais '
                '(update_time, update_time_urgently, xml_size, xml_mtime, xml_sha256) '
                'VALUES(?, ?, ?, ?, ?)', (
                el['ut'], el['utu'], el['as'], el['m'], xml_binsha256))
            since = max(since, el['ut'])
        maybe_more = len(page) == page_size
        return since, maybe_more

    def fetch_xml_and_sig(self, tmpdir, handle):
        _, _, _, xml_mtime, xml_binsha256 = handle
        xml_sha256 = binascii.hexlify(xml_binsha256).decode('ascii')
        zip_path = os.path.join(tmpdir, DUMP_ZIP)
        save_url(zip_path, self.s, 'https://{}/get/{}'.format(self.fqdn, xml_sha256))
        logging.info('%s: got %s. %d bytes, xml_sha256: %s',
                self.name, DUMP_ZIP, os.path.getsize(zip_path), xml_sha256)
        with zipfile.ZipFile(zip_path, 'r') as zfd:
            zfd.extract(DUMP_XML, path=tmpdir)
            xml_path = os.path.join(tmpdir, DUMP_XML)
            os.utime(xml_path, (xml_mtime, xml_mtime))
            zfd.extract(DUMP_SIG, path=tmpdir)
            os.utime(os.path.join(tmpdir, DUMP_SIG), (RKN_EPOCH, RKN_EPOCH))
        return xml_binsha256

    @staticmethod
    def sanity_cb(handle, xmlmeta, sigmeta, ut, utu):
        update_time, update_time_urgently, xml_size, _, xml_binsha256 = handle
        xml_sha256 = binascii.hexlify(xml_binsha256).decode('ascii')
        if xmlmeta['SHA256'] != xml_sha256:
            raise RuntimeError('Bad xml_sha256', xmlmeta['SHA256'], xml_sha256)
        if xmlmeta['size'] != xml_size:
            raise RuntimeError('Bad xml_size', xmlmeta['size'], xml_size)
        if ut.timestamp() != update_time:
            raise RuntimeError('Bad updateTime', ut, update_time)
        if utu.timestamp() != update_time_urgently:
            raise RuntimeError('Bad updateTimeUrgently', utu, update_time_urgently)
