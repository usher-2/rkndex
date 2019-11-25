`rkndex` is a toolbox to store compact archive of RKN dumps and index it.

## Summary

- fetches data from [usher2/vigruzki](https://github.com/usher-2/vigruzki) and other data sources
- checks `dump.xml` signature against [schors/gost-russian-ca](https://github.com/schors/gost-russian-ca/) bundle and Rostelecom CA
- stores data with git to utilize [xdelta and gzip](https://github.com/git/git/blob/master/Documentation/technical/pack-heuristics.txt) in the simpliest possible way
- indexes the difference between the closest `dump.xml` files using PostgreSQL

## Storage efficiency

86500 `dump.xml` files are stored as 4 GiB git repo as compared to 100 GiB of borg-backed [usher2/vigruzki](https://github.com/usher-2/vigruzki).
