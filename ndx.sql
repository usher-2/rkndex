BEGIN;

-- Everything goes to `public` schema.

CREATE DOMAIN md5 AS bytea check (octet_length(value) = 16);
CREATE DOMAIN sha1 AS bytea check (octet_length(value) = 20);
CREATE DOMAIN sha256 AS bytea check (octet_length(value) = 32);
CREATE DOMAIN sha512 AS bytea check (octet_length(value) = 64);
CREATE DOMAIN size4 AS int4 check (value >= 0);
CREATE DOMAIN rkn_ts AS timestamp without time zone check (value >= '2012-07-28 08:00:00');

CREATE TYPE block_type AS enum (
    'domain',
    'domain-mask',
    'ip',
    'default',
    '<null>' -- BLOCKTYPE_NULL
);

CREATE TYPE tag_type AS enum (
    'domain',
    'url',
    'ip',
    'ipv6',
    'ipSubnet',
    'ipv6Subnet'
);

-- Lists only actual, real files.
CREATE TABLE known_dump (
    update_time             rkn_ts NOT NULL CHECK (update_time > '2012-07-28 08:00:00'),
    update_time_urgently    rkn_ts CHECK (update_time_urgently IS NULL OR update_time_urgently > '2012-07-28 08:00:00'),
    signing_time            rkn_ts NOT NULL CHECK (signing_time > '2012-07-28 08:00:00'),
    xml_mtime               rkn_ts CHECK (xml_mtime IS NULL OR xml_mtime > '2012-07-28 08:00:00'),
    sig_mtime               rkn_ts CHECK (sig_mtime IS NULL OR sig_mtime > '2012-07-28 08:00:00'),
    xml_md5                 md5 NOT NULL,
    sig_md5                 md5 NOT NULL,
    xml_sha1                sha1 NOT NULL,
    sig_sha1                sha1 NOT NULL,
    xml_sha256              sha256 NOT NULL,
    sig_sha256              sha256 NOT NULL,
    xml_sha512              sha512 NOT NULL,
    sig_sha512              sha512 NOT NULL,
    UNIQUE (update_time), -- MAY be eventually wrong
    UNIQUE (xml_sha1, sig_sha1)
);

-- NB: includes fake diff from (update_time = '2012-07-28 08:00:00' and xml_sha1_from = ZERO_SHA1)
-- That's pseudo- MATERIALIZED VIEW that lists diffs from `known_dump`.
CREATE TABLE known_diff (
    update_time_from    rkn_ts NOT NULL,
    update_time_to      rkn_ts NOT NULL CHECK (update_time_to > '2012-07-28 08:00:00'),
    xml_sha1_from       sha1 NOT NULL,
    xml_sha1_to         sha1 NOT NULL,
    UNIQUE (update_time_from, update_time_to, xml_sha1_from, xml_sha1_to)
);

-- NB: content_id may be zero-length for diff bumping update_time
-- NB: non-zero content_id may have no deltas in `content` table when nothing but `ip.ts` is touched.
CREATE TABLE ingested_diff (
    update_time_from            rkn_ts NOT NULL,
    update_time_to              rkn_ts NOT NULL CHECK (update_time_to > '2012-07-28 08:00:00'),
    xml_sha1_from               sha1 NOT NULL,
    xml_sha1_to                 sha1 NOT NULL,
    exc                         boolean NOT NULL,
    unknown_attrs_from          boolean NOT NULL,
    unknown_attrs_to            boolean NOT NULL,
    unknown_tags_from           boolean NOT NULL,
    unknown_tags_to             boolean NOT NULL,
    duplicate_cdata_tag_from    boolean NOT NULL,
    duplicate_cdata_tag_to      boolean NOT NULL,
    UNIQUE (update_time_from, update_time_to, xml_sha1_from, xml_sha1_to)
);

-- The essential difference between inet and cidr data types is that inet accepts
-- values with nonzero bits to the right of the netmask, whereas cidr does not.
-- For example, 192.168.0.1/24 is valid for inet but not for cidr.
-- https://www.postgresql.org/docs/12/datatype-net-types.html#DATATYPE-INET-VS-CIDR
CREATE TABLE content (
    content_id          int4 NOT NULL,
    block_type          block_type NOT NULL,
    has_domain          boolean NOT NULL,
    has_domain_mask     boolean NOT NULL,
    has_url             boolean NOT NULL,
    has_http            boolean NOT NULL,
    has_https           boolean NOT NULL,
    has_path            boolean NOT NULL,
    has_ip              boolean NOT NULL,
    -- references to `known_dump`
    is_deletion         boolean NOT NULL,
    update_time_from    rkn_ts NOT NULL,
    update_time_to      rkn_ts NOT NULL CHECK (update_time_to > '2012-07-28 08:00:00'),
    -- момент времени, с которого возникает необходимость ограничения доступа (к <content/>!!!)
    include_time        timestamp without time zone,
    -- когда произошли последние изменения в реестровой записи (<content/>)
    content_ts          timestamp with time zone,
    -- ABOVE common for whole <content/>
    -- BELOW specific for every <ip/>, <url/>, etc
    -- `tag_ts` ~ когда произошли последние изменения данного объекта (<ip/>, <url/> и т.п.)
    tag_ts              timestamp with time zone,
    tag                 tag_type NOT NULL,
    value               text NOT NULL,
    ip_inet             inet,

    CONSTRAINT both_ip CHECK((tag IN ('url', 'domain')) = (ip_inet IS NULL)),
    CONSTRAINT good_from CHECK(NOT is_deletion OR update_time_from > '2012-07-28 08:00:00'),
    CONSTRAINT from_lt_to CHECK(update_time_from < update_time_to),

    UNIQUE(content_id, block_type, has_domain, has_domain_mask, has_url,
           has_http, has_https, has_path, has_ip,
           tag, value,
           is_deletion, update_time_from),
    UNIQUE(content_id, block_type, has_domain, has_domain_mask, has_url,
           has_http, has_https, has_path, has_ip,
           tag, value,
           is_deletion, update_time_to)
);

CREATE TABLE content_zerodiff (
    content_id          int4 NOT NULL,
    is_deletion         boolean NOT NULL,
    update_time_from    rkn_ts NOT NULL,
    update_time_to      rkn_ts NOT NULL CHECK (update_time_to > '2012-07-28 08:00:00'),
    content_ts          timestamp with time zone,
    include_time        timestamp without time zone,
    CHECK(update_time_from < update_time_to),
    UNIQUE(content_id, is_deletion, update_time_from),
    UNIQUE(content_id, is_deletion, update_time_to)
);

CREATE TABLE content_meta (
    content_id          int4 NOT NULL,
    decision_date       date,
    decision_number     text,
    decision_org        text,
    -- 1 – реестр ЕАИС
    -- 2 – реестр НАП
    -- 3 – реестр 398-ФЗ
    -- 4 – реестр 97-ФЗ (организаторы распространения информации)
    -- 5 – реестр НАП, постоянная блокировка сайтов
    -- 6 – реестр нарушителей прав субъектов персональных данных
    -- 7 – реестр анонимайзеров
    entry_type          int2,
    -- 0 – обычная срочность (в течение суток)
    -- 1 – высокая срочность
    urgency_usual_seen  boolean NOT NULL,
    urgency_high_seen   boolean NOT NULL,
    UNIQUE(content_id, decision_date, decision_number, decision_org, entry_type)
);

END;
