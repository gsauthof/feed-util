#!/usr/bin/env python3


# betterflix - build feed of IMDB better scored movies newly added to netflix/prime
#
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: © 2022 Georg Sauthoff <mail@gms.tf>


import argparse
import calendar
import datetime
import decimal
import defusedxml.ElementTree
import html5lib
import json
import logging
import os
import pycurl
import re
import sys
import time
import xml.etree.ElementTree as ET


default_treebuilder = 'etree'

ans = '{http://www.w3.org/2005/Atom}'
xns = '{http://www.w3.org/1999/xhtml}'


log = logging.getLogger(__name__)


def setup_logging():
    log_format      = '%(asctime)s - %(levelname)-8s - %(message)s'
    log_date_format = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(format=log_format,
                        datefmt=log_date_format, level=logging.WARNING)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--agent',
                   default='Mozilla/5.0 (X11; Linux x86_64; rv:107.0) Gecko/20100101 Firefox/107.0',
                   help='HTTP user agent (default: %(default)s)')
    p.add_argument('--cache', default=os.environ['HOME'] + '/.cache/betterflix',
                   help='cache directory (default: %(default)s)')
    p.add_argument('--debug', '-d', action='store_true', help='Debug mode - also use cached copy of source feed')
    p.add_argument('--output', '-o', metavar='FILE', default='flix.xml',
                   help='output filename (default: %(default)s)')
    p.add_argument('--prime', action='store_true', help='query Amazon Prime instead of Netflix')
    p.add_argument('--thresh', '-t', type=decimal.Decimal, default=decimal.Decimal('6.5'),
                   help='IMDB average rating threshold for movies to be included, i.e. greater or equal (default: %(default)s)')
    p.add_argument('--url', help='Expliclity specify a RSS source feed URL (default: Netflix or Prime, cf. --prime)')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Enable verbose (debug) logging')
    args     = p.parse_args()
    if args.url is None:
        if args.prime:
            args.url = wse_prime_url
            args.tag = 'prime'
        else:
            args.url = wse_netflix_url
            args.tag = 'netflix'
    else:
        args.tag = 'misc'
    return args


def mk_curl_handle(user_agent):
    def check_size(d_total, d_n, u_total, u_n):
        limit = 5 * 1024 * 1024
        if d_total > limit or d_n > limit:
            return 23 # abort

    c = pycurl.Curl()
    c.setopt(c.USERAGENT, user_agent)
    c.setopt(c.FOLLOWLOCATION, True)

    c.setopt(c.NOPROGRESS, False)
    c.setopt(c.XFERINFOFUNCTION, check_size)

    return c

def download(c, url, filename):
    if not (url.startswith('http://') or url.startswith('https://')):
        raise RuntimeError(f'Unexpected URL scheme: {url}')
    f = open(filename, 'w+b')
    c.setopt(c.WRITEDATA, f)
    c.setopt(c.URL, url)
    log.debug(f'Downloading {url} ...')
    c.perform()
    code = c.getinfo(c.RESPONSE_CODE)
    if code != 200:
        os.unlink(filename)
        raise RuntimeError(f'Downloading {url} failed: {code}')
    f.seek(0)
    return f

san_re = re.compile('[^A-Za-z0-9_-]')

def mk_cache_fn(cache_path, url):
    ofn   = san_re.sub('_', url)
    opath = f'{cache_path}/{ofn}'
    return opath

def cached_download(c, url, cache_path):
    opath = mk_cache_fn(cache_path, url)
    if os.path.exists(opath) and os.path.getsize(opath) > 0:
        log.debug(f'Using cached {opath}')
        return open(opath, 'rb')
    else:
        time.sleep(1)
        return download(c, url, opath)

def unlink_cache(cache_path, url):
    fn = mk_cache_fn(cache_path, url)
    try:
        log.debug(f'Removing: {fn}')
        os.unlink(fn)
    except FileNotFoundError:
        pass


# shared with heiser.py/lwn.py

def clean_cache(cache, protected_days=7):
    assert cache
    for fn in os.listdir(cache):
        filename = '{}/{}'.format(cache, fn)
        # time.time() doesn't necessarily return the UTC unix epoche ...
        delta = (calendar.timegm(time.gmtime())
                 - os.path.getmtime(filename)) / 3600 / 24
        if delta > protected_days:
            log.debug('Removing cached item: ' + filename)
            os.remove(filename)


def parse_imdb_rating(s):
    root = html5lib.parse(s, default_treebuilder)
    es   = root.findall(f'.//{xns}script[@type="application/ld+json"]')
    e    = es[0]
    d    = json.loads(e.text, parse_float=str)
    return d


def parse_imdb_link(s):
    root = html5lib.parse(s, default_treebuilder)
    es  = root.findall(f'.//{xns}a[.="IMDb"]')
    if not es:
        return None
    e = es[0]
    l = e.get('href')
    if not (l.startswith('http://www.imdb.com/') or l.startswith('https://www.imdb.com/')):
        raise RuntimeError(f'IMDB link links weirdly: {l}')
    return l

def parse_wse_feed(file):
    d = defusedxml.ElementTree.parse(file, forbid_dtd=True)
    # should be equivalent to the following (modulo more secure):
    #     d = ET.parse(file)
    # However, should be superfluous on newer Python versions that link against expat 2.4.1 or newer
    # cf. https://docs.python.org/3/library/xml.html#xml-vulnerabilities
    root = d.getroot()
    ls   = [ x.text for x in root.findall(f'./channel/item/link') ]
    if len(ls) > 1000:
        raise RuntimeError('Unexepected high number of entries in the westreamt.es feed: {len(ls)}')
    for l in ls:
        if not (l.startswith('https://www.werstreamt.es/') or l.startswith('http://www.werstreamt.es/')):
            raise RuntimeError(f'WSE link links weirdly: {l}')
    return ls


def read_feed_cache(cache_path, tag):
    fn = f'{cache_path}/db-{tag}.json'
    if os.path.exists(fn):
        with open(fn) as f:
            d = json.load(f, parse_float=str)
            if len(d) > 50:
                for k in list(d.keys())[:len(d)-50]:
                    del d[k]
            return d
    else:
        return { 'imdb': {} }

def write_feed_cache(cache_path, tag, d):
    fn = f'{cache_path}/db-{tag}.json'
    with open(fn, 'w') as f:
        json.dump(d, f, indent=4)

wse_netflix_url = 'https://www.werstreamt.es/filme/anbieter-netflix/neu/?rss'
wse_prime_url   = 'https://www.werstreamt.es/filme/anbieter-prime-video/option-flatrate/neu/?rss'

def read_wse_feed(args, c):
    h = read_feed_cache(args.cache, args.tag)

    if not args.debug:
        unlink_cache(args.cache, args.url)
    f  = cached_download(c, args.url, args.cache)
    xs = parse_wse_feed(f)
    xs.reverse()

    now_str = datetime.datetime.utcnow().isoformat() + 'Z'
    changed = False

    for x in xs:
        f = cached_download(c, x, args.cache)
        l = parse_imdb_link(f)
        if not l:
            log.debug(f'No IMDB link for: {x}')
            continue
        f = cached_download(c, l, args.cache)
        d = parse_imdb_rating(f)
        if 'aggregateRating' in d:
            score = decimal.Decimal(d['aggregateRating']['ratingValue'])
        else:
            score = decimal.Decimal(0)

        if score >= args.thresh:
            if d['url'] not in h['imdb']:
                changed             = True
                d['mtime']          = now_str
                h['imdb'][d['url']] = d
            director = d['director'][0]['name'] if 'director' in d else ''
            genre    = ', '.join(d.get('genre', []))
            pub      = d.get('datePublished', 'unk-pub-date')
            log.debug(f'Selected: {d["name"]} ({score}, {pub}) - {director}, {genre}')
    if changed:
        h['mtime'] = now_str
    write_feed_cache(args.cache, args.tag, h)

    return h


def mk_feed(h, tag):
    feed = ET.Element(ans + 'feed')
    name = tag[0].upper() + tag[1:]
    ET.SubElement(feed, ans + 'title').text   = f'New {name} Movies filtered by IMDB score'
    ET.SubElement(feed, ans + 'id').text      = 'urn:uuid:98993562-02c3-4a77-bff4-aa79d471fea2'
    ET.SubElement(feed, ans + 'updated').text = h['mtime']
    for k, d in reversed(h['imdb'].items()):
        url   = 'https://www.imdb.com' + d['url']
        entry = ET.SubElement(feed, ans + 'entry')
        ET.SubElement(entry, ans + 'title').text   = f'{d["name"]} ({d["aggregateRating"]["ratingValue"]})'
        ET.SubElement(entry, ans + 'updated').text = d['mtime']
        ET.SubElement(entry, ans + 'link', rel='alternate', type='text/html', href=url)
        ET.SubElement(entry, ans + 'id').text      = url
        cont = ET.SubElement(entry, ans + 'content', type='text/html')
        ul   = ET.SubElement(cont, xns + 'ul')
        ET.SubElement(ul, xns + 'li').text = 'Published: ' + d.get('datePublished', '')
        ET.SubElement(ul, xns + 'li').text = 'Director: ' + d.get('director', [{'name':''}])[0]['name']
        ET.SubElement(ul, xns + 'li').text = 'Genre: ' + ', '.join(d.get('genre', []))
        ET.SubElement(ul, xns + 'li').text = d.get('description', '')
    return ET.ElementTree(feed)


def main():
    setup_logging()
    args = parse_args()
    ET.register_namespace('', 'http://www.w3.org/2005/Atom')
    if args.verbose:
        log.setLevel(logging.DEBUG)
    os.makedirs(args.cache, exist_ok=True)
    c = mk_curl_handle(args.agent)

    d  = read_wse_feed(args, c)
    ft = mk_feed(d, args.tag)
    ET.indent(ft, space='    ')
    ft.write(args.output)

    c.close()
    clean_cache(args.cache)


if __name__ == '__main__':
    sys.exit(main())
