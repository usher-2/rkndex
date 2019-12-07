#!/usr/bin/env python3
#
# Module to serve git data (log, blobs, diffs) via web API.
#

import binascii
import os
import functools
import tempfile
from base64 import standard_b64encode

import diskcache
from flask import Flask, Response, send_file, g, abort
import flask.json
import werkzeug.routing

from rkndex.popen import ScopedPopen, PIPE
from rkndex.gitarlog import GitarLog
from rkndex.filediff import write_content_diff
from rkndex.const import ZERO_BINSHA1, ZERO_BINGIT

app = Flask(__name__)

class Sha1Converter(werkzeug.routing.BaseConverter):
    regex = '[0-9a-f]{40}'
    def to_python(self, value):
        return binascii.unhexlify(value)
    def to_url(self, value):
        return binascii.hexlify(value)

class GitarLogColumns(werkzeug.routing.BaseConverter):
    # Unreserved characters besides alnum are [-._~] per
    # https://tools.ietf.org/html/rfc3986#section-2.3
    __colname = '|'.join(sorted(GitarLog.public_columns))
    regex = '(?:(?:{})~)*(?:{})'.format(__colname, __colname)
    def to_python(self, value):
        return frozenset(value.split('~'))
    def to_url(self, value):
        return '~'.join(sorted(value))

app.url_map.converters['sha1'] = Sha1Converter
app.url_map.converters['log_columns'] = GitarLogColumns

app.config.update({ # defaults
    'GITAR_DIR': os.environ.get('RKNDEX_GIWEB_GITAR_DIR'),
    'GITARLOG_DB': '/tmp/gitar.db',
    # http://www.grantjenks.com/docs/diskcache/api.html#constants
    # https://www.sqlite.org/intern-v-extern-blob.html
    'DISKCACHE_DIR': '/tmp/gitar.cache',
    'DISKCACHE_SIZE_GB': 1.0,
    'SECRET_KEY': os.urandom(32), # unused, so it's dynamic
})
app.config.from_envvar('RKNDEX_GIWEB_SETTINGS')

# @app.before_first_request is delayed till the first request slowing the request down
def init_instance():
    GitarLog(app.config['GITAR_DIR'], app.config['GITARLOG_DB']) # pre-cache data
init_instance()

@app.before_request
def req_init():
    assert 'gitarlog' not in g and 'cache' not in g
    # FIXME: `git rev-parse HEAD` on every request takes several milliseconds
    g.gitlog = GitarLog(app.config['GITAR_DIR'], app.config['GITARLOG_DB'])
    g.cache = diskcache.Cache(
        app.config['DISKCACHE_DIR'],
        size_limit=int(app.config['DISKCACHE_SIZE_GB'] * 1024**3),
        statistics=True,
        eviction_policy='least-recently-used')

@app.teardown_appcontext
def ctx_teardown(ctx):
    for k in ('gitarlog', 'cache'):
        v = g.pop(k, None)
        if v is not None:
            v.close()

def xml_git_by_sha1(xml_sha1: bytes):
    xml_git = g.gitlog.xml_git_by_sha1(xml_sha1)
    if xml_git is None:
        abort(404)
    return xml_git

def git_cat_file(git_obj: bytes):
    return ScopedPopen(['git', '--git-dir', app.config['GITAR_DIR'], 'cat-file', 'blob', binascii.hexlify(git_obj)], stdout=PIPE)

@app.route('/dump_xml/<sha1:xml_sha1>')
def dump_xml(xml_sha1):
    xml_git = xml_git_by_sha1(xml_sha1)
    def generate():
        with git_cat_file(xml_git) as proc:
            for blob in iter(functools.partial(proc.stdout.read, 65536), b''):
                yield blob
            if proc.wait() != 0:
                raise RuntimeError('`git cat-file` failure', xml_git, proc.returncode)
    return Response(generate(), mimetype='application/xml; charset=windows-1251', headers={
        'Content-Disposition': 'attachment; filename=dump_{}.xml'.format(binascii.hexlify(xml_sha1).decode('ascii')),
    })

def open_xdelta_fd(from_sha1: bytes, to_sha1: bytes):
    cache_key = b'XD' + from_sha1 + to_sha1
    if cache_key not in g.cache:
        # FIXME(1): there is no easy way to WRITE a file in `diskcache',
        # the module wants to READ the file itself, so tempfile is used.
        # FIXME(2): disk_min_file_size is not respected for alike pipes.
        # See https://github.com/grantjenks/python-diskcache/issues/11
        # That costs ~15% (~400 MiB) being spent on file tails.
        from_git = xml_git_by_sha1(from_sha1) if from_sha1 != ZERO_BINSHA1 else ZERO_BINGIT
        to_git = xml_git_by_sha1(to_sha1)
        with tempfile.TemporaryFile() as tmp, \
             git_cat_file(from_git) as in1, \
             git_cat_file(to_git) as in2 \
        :
            write_content_diff(tmp, in1.stdout, in2.stdout)
            for xml_sha1, returncode in ((from_sha1, in1.wait()), (to_sha1, in2.wait())):
                if returncode != 0:
                    raise RuntimeError('`git cat-file` failure', xml_sha1, returncode)
            tmp.seek(0)
            g.cache.set(cache_key, tmp, read=True)
    return g.cache.get(cache_key, read=True)

@app.route('/digest_xml_sha1')
def digest_xml_sha1():
    return {'digest_xml_sha1': g.gitlog.digest_xml_sha1().hex()}

@app.route('/xdelta/<sha1:from_sha1>/<sha1:to_sha1>')
def xdelta(from_sha1, to_sha1):
    fd = open_xdelta_fd(from_sha1, to_sha1)
    return send_file(fd, mimetype='application/octet-stream',
        attachment_filename='dump_xml_{}_{}.bindiff.gz'.format(
            binascii.hexlify(from_sha1).decode('ascii'),
            binascii.hexlify(to_sha1).decode('ascii')),
        as_attachment=True)

def hexlify_values(d):
    return {k: binascii.hexlify(v).decode('ascii') if isinstance(v, bytes) else v
            for k, v in d.items()}

# FIXME: jsonl reduces peak memory usage
@app.route('/since_update_time/<int:since>/<int:count>')
def list_since(since, count):
    return {'data': [hexlify_values(x) for x in g.gitlog.dumps_since(since, count)]}
@app.route('/since_update_time/<int:since>/<int:count>/<log_columns:columns>')
def list_since_columns(since, count, columns):
    # FIXME: maybe redirect to canonical order of `columns` to ease HTTP-level caching
    return {'data': [hexlify_values(x) for x in g.gitlog.dumps_since(since, count, columns)]}
