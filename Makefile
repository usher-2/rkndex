.PHONY : \
    build-giweb \
    build-gitar \
    build-u2ex \
    push-giweb \
    push-gitar \
    push-u2ex \
    all

all :
	:

# `tar` is used to avoid adding huge $PWD to context
build-giweb :
	tar cz Dockerfile.rkngiweb rkndex | docker build -t darkk/rkn:giweb -f Dockerfile.rkngiweb -
build-gitar :
	tar cz Dockerfile.rkngitar rkngitar | docker build -t darkk/rkn:gitar -f Dockerfile.rkngitar -
build-u2ex :
	tar cz Dockerfile.rknu2ex usher2_exporter | docker build -t darkk/rkn:u2ex -f Dockerfile.rknu2ex -

push-giweb :
	docker push darkk/rkn:giweb
push-gitar :
	docker push darkk/rkn:gitar
push-u2ex :
	docker push darkk/rkn:u2ex

run-giweb :
	docker run --rm -ti \
	    --net=host \
	    -e RKNDEX_GIWEB_GITAR_DIR=/srv/rkn.git \
	    -e RKNDEX_GIWEB_SETTINGS=/dev/null \
	    -v $$PWD/rkn.git:/srv/rkn.git:ro \
	    darkk/rkn:giweb \
	    gunicorn --bind 127.0.0.1:12283 rkndex.giweb:app
