#!/usr/bin/env python3
#
# Module to cache `git log` of rkn.git repo in sqlite3 database.
#

import binascii
import sqlite3
from subprocess import Popen, run, PIPE

RKN_EPOCH = 1343462400 # Sat Jul 28 12:00:00 MSK 2012

class GitarLog(object):
    def __init__(self, git_dir, sqlite_fname='', sqlite_timeout=60):
        self.git_dir = git_dir
        self.db = sqlite3.connect(sqlite_fname, timeout=sqlite_timeout, isolation_level=None)
        self.create_table()
        self.poll_fs()

    def poll_fs(self):
        git_head = self.git_head()
        self.db.execute('BEGIN EXCLUSIVE TRANSACTION')
        with self.db:
            db_head = self.db_head()
            if db_head != git_head:
                self.insert_up_to(db_head, git_head)
                self.update_db_head(git_head)

    def xml_git_by_sha1(self, xml_sha1):
        assert len(xml_sha1) == 20 # should be bytes
        with self.db:
            it = self.db.execute('SELECT xml_git FROM log WHERE xml_sha1 = ? LIMIT 1', (xml_sha1,))
        row = next(it, None)
        return row[0] if row is not None else None

    def dumps_since(self, since, count):
        with self.db:
            it = self.db.execute('''SELECT * FROM log
                WHERE update_time >= ?
                ORDER BY update_time, xml_sha1, sig_sha1
                LIMIT ?''',
                (since, count))
            return [{col[0]: row[idx] for idx, col in enumerate(it.description)} for row in it]

    def close(self):
        self.db.close()
        self.db = None

    def create_table(self):
        # NB, there is no `zip_mtime` here.  That's at least 324 bytes per row,
        # at least ~32 MiB for current set of dumps (+indexes, +overhead).
        self.db.execute('CREATE TABLE IF NOT EXISTS head (commit_hash BLOB NOT NULL)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS log (
    update_time     INTEGER NOT NULL,
    update_time_urgently    INTEGER,
    signing_time    INTEGER NOT NULL,
    xml_mtime       INTEGER,
    sig_mtime       INTEGER,
    xml_md5         BLOB NOT NULL,
    sig_md5         BLOB NOT NULL,
    xml_sha1        BLOB UNIQUE NOT NULL,
    sig_sha1        BLOB NOT NULL,
    xml_git         BLOB NOT NULL,
    sig_git         BLOB NOT NULL,
    xml_sha256      BLOB NOT NULL,
    sig_sha256      BLOB NOT NULL,
    xml_sha512      BLOB NOT NULL,
    sig_sha512      BLOB NOT NULL
)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS log_update_time ON log (update_time)')

    def update_db_head(self, head):
        assert len(head) == 20
        cursor = self.db.execute('UPDATE head SET commit_hash = ?', (head,))
        assert 0 <= cursor.rowcount <= 1
        if cursor.rowcount == 0:
            self.db.execute('INSERT INTO head VALUES(?)', (head,))

    def db_head(self):
        cursor = self.db.execute('SELECT commit_hash FROM head LIMIT 1')
        row = next(cursor, None)
        if row is not None:
            head = row[0]
            assert len(head) == 20
        else:
            head = None
        return head

    def git_head(self):
        head = run(['git', '--git-dir', self.git_dir, 'rev-parse', 'HEAD'], stdout=PIPE, check=True).stdout
        head = binascii.unhexlify(head.strip().decode('ascii'))
        assert len(head) == 20
        return head

    def insert_up_to(self, db_head, uptohead):
        cmd = ['git', '--git-dir', self.git_dir, 'log', '--format=tformat:%b%n. . .']
        if db_head is not None:
            cmd.append(binascii.hexlify(db_head) + b'..' + binascii.hexlify(uptohead))
        else:
            cmd.append(binascii.hexlify(uptohead))
        times_map = {
            'updateTime': 'update_time',
            'updateTimeUrgently': 'update_time_urgently',
            'signingTime': 'signing_time',
            'dump.xml mtime': 'xml_mtime',
            'dump.xml.sig mtime': 'sig_mtime',
        }
        fname_map = {
            'dump.xml': 'xml',
            'dump.xml.sig': 'sig',
        }
        row_keys = {'update_time', 'update_time_urgently', 'signing_time', 'xml_mtime', 'sig_mtime',
                    'xml_md5', 'sig_md5', 'xml_sha1', 'sig_sha1', 'xml_git', 'sig_git',
                    'xml_sha256', 'sig_sha256', 'xml_sha512', 'sig_sha512'}
        row = dict.fromkeys(row_keys)
        proc = Popen(cmd, stdout=PIPE)
        for line in proc.stdout:
            try:
                if line == b'\n': # first/last commit has no body
                    continue
                a, b, c = line.decode('ascii').strip().split(None, 2)
                if c in times_map:
                    v = int(b)
                    if v == RKN_EPOCH:
                        v = None
                    row[times_map[c]] = v
                elif a in ('MD5', 'SHA1', 'GIT', 'SHA256', 'SHA512'):
                    v = binascii.unhexlify(b)
                    row['{}_{}'.format(fname_map[c], a.lower())] = v
                elif a == b == c == '.':
                    if row != dict.fromkeys(row_keys): # first/last commit is 100% empty
                        self.db.execute('INSERT INTO log VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                            row['update_time'], row['update_time_urgently'], row['signing_time'],
                            row['xml_mtime'], row['sig_mtime'], row['xml_md5'], row['sig_md5'],
                            row['xml_sha1'], row['sig_sha1'], row['xml_git'], row['sig_git'],
                            row['xml_sha256'], row['sig_sha256'], row['xml_sha512'], row['sig_sha512']
                        ))
                        row = dict.fromkeys(row_keys)
                else:
                    raise RuntimeError(a, b, c) # 'Bad line in git log' as well
            except Exception as exc:
                raise RuntimeError('Bad line in git log', line, row, exc)
        if proc.wait() != 0:
            raise RuntimeError('git log failure', proc.returncode)
