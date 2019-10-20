#!/bin/sh

sed -i 's,^[^#].*\btrust\b,# disabled # &,' /var/lib/postgresql/data/pg_hba.conf
