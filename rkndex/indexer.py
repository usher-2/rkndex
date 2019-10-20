#!/usr/bin/env python3
#
# Module to ingest git log, blobs, diffs from web API and digest them into PostgreSQL database.
#

from rkndex.index_list import main_list
from rkndex.index_diff import main_diff, main_alldiff
