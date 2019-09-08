## Files

Bytes    | SHA1                                   | Fname
---------+----------------------------------------+---------
108627448 5a2aaa96d210800ac513adb7241377f2baaad562 xml/1.xml
108630255 09b43e9fef6aa4b8792895f9e44ea1a0a005857f xml/2.xml
108643189 918951ba05e824640492c2d944355edab8c7cf1e xml/3.xml
108658309 7f3d59ce86978a6afc98c3257c7cbd08730a6be4 xml/4.xml
108660684 54fe0eb9141a336758af3207f6666f074dcb29b6 xml/5.xml

## Pseudo-baseline

Ubuntu 16.04, xmllint: using libxml version 20903
  compiled with: Threads Tree Output Push Reader Patterns Writer SAXv1 FTP HTTP
                 DTDValid HTML Legacy C14N Catalog XPath XPointer XInclude
                 Iconv ISO8859X Unicode Regexps Automata Expr Schemas Schematron
                 Modules Debug Zlib Lzma

$ for f in xml/?.xml; do /usr/bin/time xmllint --format - < $f > /dev/null ; done
3.01user 0.32system 0:03.37elapsed 98%CPU (0avgtext+0avgdata 1030536maxresident)k 0inputs+0outputs (0major+256609minor)pagefaults 0swaps
2.99user 0.26system 0:03.29elapsed 98%CPU (0avgtext+0avgdata 1030572maxresident)k 0inputs+0outputs (0major+256621minor)pagefaults 0swaps
2.91user 0.28system 0:03.19elapsed 99%CPU (0avgtext+0avgdata 1030668maxresident)k 0inputs+0outputs (0major+256654minor)pagefaults 0swaps
2.94user 0.28system 0:03.23elapsed 99%CPU (0avgtext+0avgdata 1030892maxresident)k 0inputs+0outputs (0major+256698minor)pagefaults 0swaps
2.90user 0.32system 0:03.23elapsed 99%CPU (0avgtext+0avgdata 1030864maxresident)k 0inputs+0outputs (0major+256706minor)pagefaults 0swaps

$ for f in xml/?.xml; do /usr/bin/time xmllint --xpath '//content/@id' - < $f > /dev/null ; done 
2.10user 0.26system 0:02.39elapsed 99%CPU (0avgtext+0avgdata 1033908maxresident)k 0inputs+0outputs (0major+257576minor)pagefaults 0swaps
2.00user 0.28system 0:02.29elapsed 99%CPU (0avgtext+0avgdata 1033976maxresident)k 0inputs+0outputs (0major+257564minor)pagefaults 0swaps
2.05user 0.29system 0:02.35elapsed 99%CPU (0avgtext+0avgdata 1034004maxresident)k 0inputs+0outputs (0major+257596minor)pagefaults 0swaps
1.92user 0.34system 0:02.27elapsed 99%CPU (0avgtext+0avgdata 1034400maxresident)k 0inputs+0outputs (0major+257664minor)pagefaults 0swaps
2.00user 0.28system 0:02.29elapsed 99%CPU (0avgtext+0avgdata 1034432maxresident)k 0inputs+0outputs (0major+257673minor)pagefaults 0swaps

## expat or etree.ElementTree ?

Ubuntu 16.04, Python 3.5.2

$ for f in xml/?.xml; do /usr/bin/time perf/xml/expat $f; done
2.99user 0.02system 0:03.04elapsed 99%CPU (0avgtext+0avgdata 9468maxresident)k 0inputs+0outputs (0major+1156minor)pagefaults 0swaps
2.88user 0.01system 0:02.91elapsed 99%CPU (0avgtext+0avgdata 9640maxresident)k 0inputs+0outputs (0major+1156minor)pagefaults 0swaps
2.79user 0.01system 0:02.82elapsed 99%CPU (0avgtext+0avgdata 9476maxresident)k 0inputs+0outputs (0major+1155minor)pagefaults 0swaps
2.83user 0.04system 0:02.88elapsed 99%CPU (0avgtext+0avgdata 9504maxresident)k 0inputs+0outputs (0major+1155minor)pagefaults 0swaps
2.88user 0.04system 0:02.95elapsed 98%CPU (0avgtext+0avgdata 9488maxresident)k 0inputs+0outputs (0major+1158minor)pagefaults 0swaps

$ for f in xml/?.xml; do /usr/bin/time perf/xml/etree $f; done
6.94user 0.04system 0:07.07elapsed 98%CPU (0avgtext+0avgdata 16848maxresident)k 0inputs+0outputs (0major+4597minor)pagefaults 0swaps
7.05user 0.03system 0:07.09elapsed 99%CPU (0avgtext+0avgdata 16864maxresident)k 0inputs+0outputs (0major+4339minor)pagefaults 0swaps
6.98user 0.02system 0:07.07elapsed 99%CPU (0avgtext+0avgdata 16800maxresident)k 0inputs+0outputs (0major+4238minor)pagefaults 0swaps
7.00user 0.04system 0:07.05elapsed 99%CPU (0avgtext+0avgdata 16580maxresident)k 0inputs+0outputs (0major+4543minor)pagefaults 0swaps
6.94user 0.01system 0:06.96elapsed 99%CPU (0avgtext+0avgdata 16556maxresident)k 0inputs+0outputs (0major+4132minor)pagefaults 0swaps

$ for f in xml/{1..4}.xml; do /usr/bin/time perf/xml/pseudodelta $f xml/$(( $(basename $f .xml) + 1)).xml /dev/null; done
54.35user 0.12system 0:54.58elapsed 99%CPU (0avgtext+0avgdata 25500maxresident)k 0inputs+0outputs (0major+10889minor)pagefaults 0swaps
55.17user 0.12system 0:55.40elapsed 99%CPU (0avgtext+0avgdata 26152maxresident)k 0inputs+0outputs (0major+12303minor)pagefaults 0swaps
54.36user 0.09system 0:54.54elapsed 99%CPU (0avgtext+0avgdata 26312maxresident)k 0inputs+0outputs (0major+11128minor)pagefaults 0swaps
53.16user 0.09system 0:53.32elapsed 99%CPU (0avgtext+0avgdata 25332maxresident)k 0inputs+0outputs (0major+11847minor)pagefaults 0swaps

## pseudodelta.svg

pyflame -t python3.5 perf/xml/pseudodelta xml/1.xml xml/2.xml /dev/null > pseudodelta.flame
flamegraph.pl < pseudodelta.flame > pseudodelta.svg

Take a look at pseudodelta.svg, etree version spends 68% in ET.tostring and 28% in parsing.

So, replacing etree with expat should reduce time from ~55s to ~6s.
