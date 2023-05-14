#!/usr/bin/env python3
#
# Some shared constants.
#

RKN_EPOCH = 1343462400 # Sat Jul 28 12:00:00 MSK 2012
ZERO_XML = b'<?xml version="1.0" encoding="windows-1251"?><reg:register updateTime="2012-07-28T12:00:00+04:00" formatVersion="0.0" xmlns:reg="http://rsoc.ru"></reg:register>'
ZERO_SHA1 = '8f751f87f10251f8f7371826346a3d7d7332a424'
ZERO_BINSHA1 = b'\x8f\x75\x1f\x87\xf1\x02\x51\xf8\xf7\x37\x18\x26\x34\x6a\x3d\x7d\x73\x32\xa4\x24'
ZERO_GIT = '014e3fab9f1ec53d38c5422d9211b6818fdf3a6a'
ZERO_BINGIT = b'\x01\x4e\x3f\xab\x9f\x1e\xc5\x3d\x38\xc5\x42\x2d\x92\x11\xb6\x81\x8f\xdf\x3a\x6a'
BLOCKTYPE_NULL = '<null>'
GITAR_USER_AGENT = 'rkngitar/0.0; https://darkk.net.ru/'
DONOR_POLL_PERIOD = 60
LAST_MODIFIED_EPOCH = 'Thu, 01 Jan 1970 00:00:00 GMT'
HTTP_TIMEOUT = 15.5

BRANCH_100 = 'refs/heads/main-100m'
REMOTE_100 = 'refs/remotes/gh/main'
GH_REF_100 = 'main'
GH_BLOB_LIMIT = 100 * 1024 * 1024 # GitHub max file size

DUMP_ZIP = 'dump.zip'
DUMP_XML = 'dump.xml'
DUMP_SIG = 'dump.xml.sig'
