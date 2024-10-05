#!/usr/bin/env python3

import argparse
import io
import pycurl
import re
import sys


curl = None

def setup_curl(user_agent = None):
    global curl

    def check_size(d_total, d_n, u_total, u_n):
        limit = 1024 * 1024
        if d_total > limit or d_n > limit:
            return 23 # abort

    curl = pycurl.Curl()
    if user_agent is not None:
        curl.setopt(curl.USERAGENT       , user_agent)
    curl.setopt(curl.FOLLOWLOCATION  , True)
    curl.setopt(curl.NOPROGRESS      , False)
    curl.setopt(curl.XFERINFOFUNCTION, check_size)


def fetch(url):
    f = io.BytesIO()
    curl.setopt(curl.WRITEDATA, f)
    curl.setopt(curl.URL, url)
    curl.perform()
    code = curl.getinfo(curl.RESPONSE_CODE)
    if code != 200:
        raise RuntimeError(f'Downloading {url} failed: {code}')
    return f.getvalue().decode()

# try how well it goes when not using an XML parser for once,
# for such a trivial amount of data, in an overengineered and likely stale format, for fun ...

def parse_estr_url(s, prefix):
    i = s.find('<title>EURO-SHORT-TERM-RATE PUBLICATION MESSAGE</title>')
    if i == -1:
        raise RuntimeError("Couldn't find estr url in main feed")
    j = s.index('<link>', i+55, i+100) + 6
    k = s.index('</link>', j)
    url = s[j:k]
    if not url.startswith('https://'):
        raise RuntimeRrror(f"ESTR URL doesn't start with https://")
    if not url.startswith(prefix):
        raise RuntimeError(f'Unexpected domain: {url}')
    return url

kv_ex = re.compile('[A-Za-z0-9._-]+$')

def parse_estr(s):
    i = s.index('<EURO-SHORT-TERM-RATE_MID_PUBLICATION_MESSAGE')
    j = s.index('<CALCULATION_RESULTS>', i) + 21
    k = s.index('\n', j) + 1
    l = s.index('</CALCULATION_RESULTS>', k)
    t = s[k:l]
    xs = t.splitlines()
    h = {}
    for x in xs:
        a = x.index('<') + 1
        b = x.index('>', a)
        c = x.index('<', b+1)
        k = x[a:b]
        if not kv_ex.match(k):
            raise RuntimeError(f'Unexpected key: {k}')
        v = x[b+1:c]
        if not kv_ex.match(v):
            raise RuntimeError(f'Unexpected value: {v}')
        h[k.lower()] = v
    return h

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='https://mid.ecb.europa.eu/rss/mid.xml',
                   help='main ECB feed (default: %(default)s)')
    p.add_argument('--prefix', default='https://mid.ecb.europa.eu/',
                   help='ECB url prefix (default: %(default)s)')
    p.add_argument('--agent', '-a', help='HTTP user agent')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--csv', dest='format', default=0, action='store_const', const=0, help='output CSV (default)')
    g.add_argument('--sql', dest='format', action='store_const', const=1, help='output SQL')
    g.add_argument('--create', dest='format', action='store_const', const=2, help='output SQL table create statement')

    args = p.parse_args()
    return args

columns = ('ref_date', 'pub_date', 'rate', 'initial_volume', 'number_banks', 'number_trnx', 'sh_vol_top_banks', 'pub_mode', 'vol_dist_25', 'vol_dist_75', 'pub_type')

def print_csv(h, o=sys.stdout):
    print(','.join(columns), file=o)
    print(','.join(h[c] for c in columns), file=o)

def print_sql(h, table='estr', o=sys.stdout):
    def quote(k, v):
        xs = ('ref_date', 'pub_date', 'pub_mode', 'pub_type')
        if k in xs:
            return f"'{v}'"
        else:
            return v
    cols = ','.join(columns)
    vs   = ','.join(quote(c, h[c]) for c in columns)
    s = f'INSERT INTO {table}({cols}) VALUES ({vs});'
    print(s, file=o)

def print_create_table(o=sys.stdout):
    print('''CREATE TABLE estr (
    ref_date         timestamp PRIMARY KEY,
    pub_date         timestamp,
    rate             decimal,
    initial_volume   bigint,
    number_banks     bigint,
    number_trnx      bigint,
    sh_vol_top_banks bigint,
    pub_mode         varchar(14),
    vol_dist_25      decimal,
    vol_dist_75      decimal,
    pub_type         varchar(14)
);''')

def main():
    args = parse_args()
    if args.format == 2:
        print_create_table()
        return
    setup_curl(args.agent)
    s = fetch(args.url)
    estr_url = parse_estr_url(s, args.prefix)
    t = fetch(estr_url)
    h = parse_estr(t)
    if args.format == 0:
        print_csv(h)
    elif args.format == 1:
        print_sql(h)
    else:
        raise RuntimeError('Not implemented yet ...')

if __name__ == '__main__':
    sys.exit(main())

