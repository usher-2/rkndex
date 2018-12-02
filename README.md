# PostgreSQL sharding in 2018

> What is not so great is that the foreign scans will be executed consecutively, not concurrently
-- http://rhaas.blogspot.com/2018/05/built-in-sharding-for-postgresql.html
https://momjian.us/main/writings/pgsql/sharding.pdf
https://www.pgconf.asia/JA/2017/wp-content/uploads/sites/2/2017/12/D2-B1.pdf

# schors API

Auth: `Authorization: Bearer $(gpg --quiet --decrypt --batch <eais-schors.token.gpg)`
Root: `https://eais.example.net/`

## /hot and /get/${id}

- The latest dump.zip file
- The dump.zip with `id` equal to `SHA256(dump.xml)`

## /last?ts=${ts}&c=${count} and /start?ts=${ts}&c=${count}

List ${count} dumps known to the archive

- having `ut` < $ts
- having `ut` > $ts

as a list of alike dicts:

[
  {
    "a": 2,             /* API cache metadata flag: is it archived? */
    "ct": 0,            /* API "cache time" */
    "id": "98a986509763daf944c9bc3c12bb9d0087f1b7e42b83de8e71b61bed99a29b4f",   /* SHA256(dump.xml) */
    "crc": "ffb09187558bd814be9e25df1f61babeac0bbd6358057dc1cc6b96c88f7e0a82",  /* SHA256(<content>.*</content>), dump.xml without root <reg:register/> tag */
    "as": 18824132,     /* size(dump.xml) */
    "m": 1483211342,    /* mtime(dump.xml) from original ZIP */
    "s": 12899378,      /* WAT: original(?) ZIP(?) file size */
    "u": 1522241306,    /* WAT: access(?) time */
    "ut": 1483210680,   /* reg:register attr updateTime */
    "utu": 1483196079   /* reg:register attr updateTimeUrgently */
  },
  ...
]

{
  "a": 2,
  "as": 26759897,
  "ct": 0,
  "crc": "5fed236ce69c1c9e7d5fc9e6f478b1a24858bd0b995f7ea71cb56439651be53b",
  "id": "d4ee713a1ef00ae12600afcadc652341374a120010b54bf08f1958ce849bc3dc",
  "m": 1498886072,
  "s": 4651028,
  "u": 1500389906,
  "ut": 1498885200,
  "utu": 1498835101
}

{
  "a": 1,
  "as": 44392780,
  "crc": "6a75102c21facd1751f15d39ac604a3a03e1acbf63bcc771e770d80f94e09086",
  "ct": 1543079221,
  "id": "39be0d8dac317a0692ba82f1c3048b9113e75142c10f53fee637acd001e14905",
  "m": 1543077172,
  "s": 7300873,
  "u": 1543078621,
  "ut": 1543076940,
  "utu": 1543076940
}



/last?ts=<UNIXTIME> выдаст тебе json с данными по последнему дампу ДО указанного UNIXTIME (в секундах).
/start?ts=<UNIXTIME> по аналогии с last
И там и там "c" есть, (count).

crc - уникальный хэш чувствительных данных
id - уникальный хэш всего дампа (они проставляют туда дату генерации, даже если ничего не менялось)
Сохраняешь его и если crc не меняется - новый не качаешь. Сменился - качай.
a, ct — не обращай внмание. это я пишу есть ли в архиве и cache time
u - access time
ut, utu = updateTime и чтото там urgent updateTime из выгрузки уже
m - mtime из архива
as - размер архива
s - размер файла

# Расчёт `id` & `crc`:

hd = hashlib.sha256()
hda = hashlib.sha256()
_rb = re.compile(rb".*<reg:register.*?>")
_re = re.compile(rb"</reg:register.*?>.*")
....
    with open(myxml, 'rb') as fh:
            s = b''
            p = b''
            fl = 0
            for block in iter(lambda: fh.read(BLOCK_SIZE), b''):
                    hda.update(block)
                    if fl == 0:
                            s += block
                            if _rb.match(s):
                                    hd.update(_rb.sub(b"", s))
                                    fl = 1
                    elif fl == 1:
                            s = p + block
                            if _re.search(s):
                                    hd.update(_re.sub(b"", s))
                                    fl = 2
                            else:
                                    hd.update(p)
                                    p = block
....
    id = hda.hexdigest()
    crc = hd.hexdigest()

# OpenSSL

```
$ openssl cms -inform der -in dump.xml.sig -cmsout -print | grep -A 3 -F 'object: signingTime (1.2.840.113549.1.9.5)'
            object: signingTime (1.2.840.113549.1.9.5)
            value.set:
              UTCTIME:Nov 23 10:53:32 2018 GMT

```


```
time openssl smime -verify -engine gost -CApath /mnt/gost-russian-ca/certs -in dump.xml.sig -inform DER -content dump.xml -out /dev/null -attime 1541746500
engine "gost" set.
Verification successful

user    0m1.716s


time openssl smime -verify -engine gost -CAfile /mnt/gost-russian-ca/certs/ca-certificates.pem -in dump.xml.sig -inform DER -content dump.xml -out /dev/null -attime 1541746500
engine "gost" set.
Verification successful

user    0m2.316s
```
